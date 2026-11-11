# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Defines the CrispGraph and GraphCollection classes."""

from collections.abc import Collection
import dataclasses
from typing import Any

import pandas as pd

import constants
from critical_path import CriticalPath
from dependency_graph import DependencyGraph
import df_utils
import graph_utils
from retimer import Retimer
from third_party.CRISP.graph import Graph
from third_party.CRISP.graph import GraphNode


@dataclasses.dataclass(slots=True)
class SpanMetadata:
  """Stores strongly typed domain metadata for a trace span.

  Attributes:
    span_components: Breakdown of RPC latency into component deltas (seconds).
    num_descendants: Transitive count of downstream descendant spans.
    req_size: RPC request payload size in bytes.
    stream: Streaming RPC identifier string.
  """

  span_components: dict[str, float] = dataclasses.field(default_factory=dict)
  num_descendants: int = 0
  req_size: int = 0
  stream: str = ''


def _df_to_jaeger_json(
    df: pd.DataFrame, trace_id: int | str
) -> dict[str, object]:
  """Converts a pandas dataframe to a Jaeger JSON dictionary representation.

  Args:
      df: A pandas dataframe with trace columns.
      trace_id: The trace id.

  Returns:
      A dictionary representing the Jaeger JSON structure.
  """
  jaeger_data = []
  trace_data: dict[str, Any] = {'traceID': trace_id, 'spans': [], 'processes': {}}
  processes = {}
  df = df_utils.get_rtt_time_for_df(df)
  if constants.CLIENT_START_TIMESTAMP in df.columns:
    df = df.sort_values(by=constants.CLIENT_START_TIMESTAMP)
  elif constants.JAEGER_START_TIME in df.columns:
    df = df.sort_values(by=constants.JAEGER_START_TIME)

  for _, row in df.iterrows():
    method_name = row['method_name'] if 'method_name' in row else row.get(constants.JAEGER_OPERATION_NAME, '')
    if '.' in method_name:
      prefix, suffix = method_name.rsplit('.', 1)
      process_id = prefix
      operation_name = suffix
    else:
      process_id = (
          row['server_job']
          if 'server_job' in row and pd.notna(row['server_job'])
          else method_name
      )
      operation_name = method_name
    if process_id not in processes:
      processes[process_id] = {'serviceName': process_id}

    if constants.CLIENT_START_TIMESTAMP in row and row[constants.CLIENT_START_TIMESTAMP] > 0:
      start_time = row[constants.CLIENT_START_TIMESTAMP]
    elif constants.SERVER_START_TIMESTAMP in row:
      start_time = row[constants.SERVER_START_TIMESTAMP]
    else:
      start_time = row.get(constants.JAEGER_START_TIME, 0.0)

    span_id = row['span_id'] if 'span_id' in row else row[constants.JAEGER_SPAN_ID]
    if isinstance(span_id, float) and span_id.is_integer():
      span_id = int(span_id)

    duration = float(row[constants.RTT_TIME]) if constants.RTT_TIME in row else float(row.get(constants.JAEGER_DURATION, 0.0))

    span = {
        'traceID': trace_id,
        'spanID': span_id,
        'operationName': operation_name,
        'startTime': start_time,
        'duration': duration,
        'references': [],
        'warnings': None,
        'processID': process_id,
    }

    parent_span_id = row.get('parent_rpc_span_id', row.get(constants.PARENT_SPAN_ID, 0))
    is_parent_invalid = (
        pd.isna(parent_span_id)
        or parent_span_id is None
        or parent_span_id == 0
        or parent_span_id == '0'
    )

    is_true_root = row.get('is_true_root', False)
    if not is_true_root and not is_parent_invalid:
      if isinstance(parent_span_id, float) and parent_span_id.is_integer():
        parent_span_id = int(parent_span_id)
      span['references'] = [{
          'refType': 'CHILD_OF',
          'traceID': trace_id,
          'spanID': parent_span_id,
      }]

    trace_data['spans'].append(span)

  trace_data['processes'] = dict(processes)
  jaeger_data.append(trace_data)
  return {'data': jaeger_data}


class CrispGraph:
  """Class to store graph data for a single trace.

  Attributes:
    graph: The graph object.
    trace_id: The trace id.
    cp: The critical path.
    async_span_ids: The asynchronous span ids.
    span_metadata: The mapping of span id to metadata.
  """

  def __init__(self, crisp_graph: Graph):
    self.trace_id: str | int = crisp_graph.filename
    self.async_span_ids: set[str | int] = set()
    self.span_metadata: dict[str | int, SpanMetadata] = {}
    self._retimed: bool = False
    self.graph: Graph = crisp_graph
    self._remove_asynchronous_spans()
    self.cp: CriticalPath | None = None

  @classmethod
  def from_dataframe(cls, df: pd.DataFrame) -> 'CrispGraph':
    """Initializes the Graph object with a pandas dataframe."""
    trace_id_col = 'trace_id' if 'trace_id' in df.columns else constants.JAEGER_TRACE_ID
    if len(set(df[trace_id_col])) != 1:
      raise ValueError('The dataframe must contain only one trace id.')

    trace_id = df[trace_id_col].iloc[0]

    curr_json = _df_to_jaeger_json(df, trace_id)
    if not curr_json['data']:
      raise (ValueError('No data found for trace id: %s' % trace_id))

    root_span_id = df_utils.get_root_span_id(df)
    span_id_col = 'span_id' if 'span_id' in df.columns else constants.JAEGER_SPAN_ID
    root_row = df[df[span_id_col] == root_span_id].iloc[0]
    root_method_name = (
        root_row['method_name']
        if 'method_name' in root_row
        else root_row.get(constants.JAEGER_OPERATION_NAME, '')
    )
    if '.' in root_method_name:
      sn, op = root_method_name.rsplit('.', 1)
    else:
      sn = (
          root_row['server_job']
          if 'server_job' in root_row and pd.notna(root_row['server_job'])
          else root_method_name
      )
      op = root_method_name

    graph = Graph(
        curr_json,
        sn,
        op,
        trace_id,
        False,
        sanitize_overflowing_children=False,
    )

    crisp_graph = cls(graph)
    crisp_graph._add_span_metadata(df)
    return crisp_graph

  def __repr__(self) -> str:
    return f'CrispGraph(trace_id={self.trace_id})'

  def _add_span_metadata(self, df: pd.DataFrame) -> None:
    """Adds span metadata to the graph."""
    if self.graph is None:
      return

    span_id_col = 'span_id' if 'span_id' in df.columns else constants.JAEGER_SPAN_ID
    for i in range(len(df)):
      row = df.iloc[i]
      span_id = row[span_id_col]
      if span_id not in self.graph.nodeHT:
        continue

      span_components: dict[str, float] = {}
      req_size: int = 0
      num_descendants: int = 0
      stream: str = ''

      if 'request_size' in row.index:
        try:
          req_size = int(row['request_size'])
        except (ValueError, TypeError):
          req_size = 0
      if 'num_descendants' in row.index:
        try:
          num_descendants = int(row['num_descendants'])
        except (ValueError, TypeError):
          num_descendants = 1
      for col in [
          'request_network_delta',
          'response_network_delta',
          'client_send_queue_delta',
          'server_recv_queue_delta',
          'client_recv_queue_delta',
          'server_send_queue_delta',
          'server_app_delta',
      ]:
        if col in row.index:
          try:
            value = float(row[col])
          except (ValueError, TypeError):
            value = 0.0
          span_components[col] = value

      if 'stream' in row.index and isinstance(row['stream'], str):
        stream = row['stream']

      self.span_metadata[span_id] = SpanMetadata(
          span_components=span_components,
          num_descendants=num_descendants,
          req_size=req_size,
          stream=stream,
      )

  def get_span_metadata(self, span_id: str | int) -> SpanMetadata:
    """Gets the metadata for a given span ID."""
    return self.span_metadata.get(span_id, SpanMetadata())

  def get_span_components(self, span_id: str | int) -> dict[str, float]:
    """Gets the span components for a given span ID."""
    return self.get_span_metadata(span_id).span_components

  def get_num_descendants(self, span_id: str | int) -> int:
    """Gets the number of descendants for a given span ID."""
    return self.get_span_metadata(span_id).num_descendants

  def get_span_components_map(self) -> dict[str | int, dict[str, float]]:
    """Gets the dictionary mapping span IDs to their span components."""
    return {
        sid: meta.span_components for sid, meta in self.span_metadata.items()
    }

  def _remove_asynchronous_spans(self) -> None:
    """Removes asynchronous spans from a node's children."""
    if self.graph is None:
      return
    for span_id, node in self.graph.nodeHT.items():
      if node is None:
        continue
      if node.parentSpanId in self.graph.nodeHT:
        parent_node = self.graph.nodeHT[node.parentSpanId]
        if parent_node is None:
          continue
        if parent_node.endTime < node.endTime and node in parent_node.children:
          self.async_span_ids.add(span_id)
          del parent_node.children[node]

  def restore_to_original_timestamps(self) -> None:
    """Restores the graph to its original timestamps."""
    if self.graph is None:
      return
    self._retimed = False
    for node in self.graph.nodeHT.values():
      if node is None:
        continue
      node.startTime = graph_utils.get_original_start_time(node)
      node.endTime = graph_utils.get_original_end_time(node)
      node.duration = node.endTime - node.startTime

  def is_retimed(self) -> bool:
    """Checks if the graph has been retimed."""
    if self.graph is None:
      return False
    if self._retimed:
      return True
    for node in self.graph.nodeHT.values():
      if node is None:
        continue
      if node.startTime != node.originalStartTime:
        return True
      if node.endTime != node.originalStartTime + node.originalDuration:
        return True
    return False

  def get_critical_path(self) -> CriticalPath:
    """Gets the critical path for the graph."""
    if self.is_retimed():
      return CriticalPath(self.graph)
    if not self.cp:
      self.cp = CriticalPath(self.graph)
    return self.cp

  def get_critical_path_for_node(
      self, node_or_span_id: str | int | GraphNode
  ) -> CriticalPath:
    """Gets the critical path for a specific node in the graph."""
    if isinstance(node_or_span_id, GraphNode):
      node: GraphNode | None = node_or_span_id
      corresponding_node = self.get_node_from_span_id(node_or_span_id.sid)
      if corresponding_node is not node_or_span_id:
        raise ValueError(
            f'Node with span_id {node_or_span_id.sid} does not belong to this graph.'
        )
    else:
      node = self.get_node_from_span_id(node_or_span_id)
      if node is None:
        raise ValueError(
            f'Node with span_id {node_or_span_id} not found in graph.'
        )
    return CriticalPath(self.graph, start_node=node)

  def get_nodes_by_method(self, method_name: str) -> list[GraphNode]:
    """Returns all nodes in the graph matching the given method name."""
    if not self.graph:
      return []
    return [
        node
        for node in self.graph.nodeHT.values()
        if node.pid == method_name
        or f'{node.pid}.{node.opName}' == method_name
        or self.graph.canonicalOpName(node) == method_name
    ]

  def get_root_method(self) -> str:
    """Returns the root method name and an empty string if the graph is None."""
    if not self.graph or not self.graph.rootNode:
      return ''
    assert self.graph.rootNode is not None
    return self.graph.rootNode.pid

  def get_duration(self) -> float:
    """Gets the duration of the root node for the graph."""
    if not self.graph or not self.graph.rootNode:
      return 0
    assert self.graph.rootNode is not None
    return self.graph.rootNode.duration

  def get_node_from_span_id(self, span_id: str | int) -> GraphNode | None:
    """Returns node from the graph given a span id and None if not found."""
    if not self.graph:
      return None
    if span_id in self.graph.nodeHT:
      return self.graph.nodeHT[span_id]
    if isinstance(span_id, str):
      try:
        int_span_id = int(span_id)
      except ValueError:
        pass
      else:
        if int_span_id in self.graph.nodeHT:
          return self.graph.nodeHT[int_span_id]
    elif isinstance(span_id, int):
      str_span_id = str(span_id)
      if str_span_id in self.graph.nodeHT:
        return self.graph.nodeHT[str_span_id]
    return None

  def get_exclusive_durations(self) -> dict[str | int, float]:
    """Gets the exclusive durations for each node in the graph."""
    exclusive_times = {}
    if self.graph is None:
      return exclusive_times
    for node in self.graph.nodeHT.values():
      children = list(node.children)
      if not children:
        exclusive_times[node.sid] = node.duration
        continue
      children.sort(key=lambda node: node.startTime)
      curr_exclusive_time = node.duration
      child_exclusive_time = 0
      curr_end = 0
      for child in children:
        if child.startTime < node.startTime:
          continue
        if child.endTime > node.endTime:
          break
        if child.startTime > curr_end:
          curr_end = child.endTime
          child_exclusive_time += child.duration
        else:
          child_exclusive_time += child.endTime - curr_end
          curr_end = child.endTime
      exclusive_times[node.sid] = curr_exclusive_time - child_exclusive_time
    return exclusive_times

  def get_leaf_nodes(self) -> Collection[GraphNode]:
    """Gets the leaf nodes for the graph."""
    leaf_nodes = []
    if self.graph is None:
      return leaf_nodes
    for node in self.graph.nodeHT.values():
      if node is None:
        continue
      if not node.children:
        leaf_nodes.append(node)
    return leaf_nodes

  def get_dependency_graph(self) -> DependencyGraph:
    """Gets the dependency graph for the graph."""
    if not self.graph:
      raise ValueError('Graph is None.')
    return DependencyGraph(graph=self.graph)

  def get_retimer(self) -> Retimer:
    """Gets the retimer for the graph."""
    if not self.graph:
      raise ValueError('Graph is None.')
    return Retimer(self.get_dependency_graph())


class GraphCollection:
  """A collection of graphs for multiple traces.

  Attributes:
    graphs: A dictionary mapping trace id to graph.
    root_methods: A set of root method names.
  """

  def __init__(
      self,
      df: pd.DataFrame | None = None,
      graphs_list: Collection[CrispGraph] | None = None,
      max_traces: int = 1000,
  ):
    self.graphs: dict[str | int, CrispGraph] = {}
    self.root_methods: set[str] = set()

    if df is None and graphs_list is None:
      raise ValueError('At least one of df and graphs_list must not be None.')

    if df is not None and graphs_list:
      raise ValueError('Both df and graphs_list cannot be set.')

    i = 0
    if df is not None and not df.empty:
      trace_id_col = 'trace_id' if 'trace_id' in df.columns else constants.JAEGER_TRACE_ID
      for _, group in df.groupby(trace_id_col):
        cg = CrispGraph.from_dataframe(group)
        self.graphs[cg.trace_id] = cg
        i += 1
        if i == max_traces:
          print(
              f'Reached max traces of {max_traces}, did not complete reading'
              ' all traces in the dataframe.'
          )
          break

    elif graphs_list:
      for graph in graphs_list:
        self.graphs[graph.trace_id] = graph
        i += 1
        if i > max_traces:
          print(
              f'Reached max traces of {max_traces}, did not complete reading'
              ' all traces in the graphs list.'
          )
          break

    self.root_methods = self.get_root_methods()

  def __repr__(self):
    return f'GraphCollection(graphs={self.graphs})'

  def get_graph(self, trace_id: str | int) -> CrispGraph:
    """Gets the graph for a given trace id."""
    return self.graphs[trace_id]

  def get_root_methods(self) -> set[str]:
    """Gets the root method names for all graphs in the collection."""
    root_methods = set()
    for graph in self.graphs.values():
      root_method = graph.get_root_method()
      if root_method:
        root_methods.add(root_method)
    return root_methods

  def get_graphs_subset(
      self,
      root_method_name: str | None = None,
      trace_ids: Collection[str | int] | None = None,
      percentile_start: float = 0,
      percentile_end: float = 100,
  ) -> Collection[CrispGraph]:
    """Gets a subset of graphs for a root method, trace_id, or percentile."""
    if percentile_start < 0 or percentile_start > 100:
      raise ValueError('Percentile start must be between 0 and 100.')
    if percentile_end < 0 or percentile_end > 100:
      raise ValueError('Percentile end must be between 0 and 100.')

    subset = list(self.graphs.values())

    if root_method_name is not None:
      subset = [
          graph
          for graph in subset
          if graph.get_root_method() == root_method_name
          or (
              graph.graph is not None
              and graph.graph.rootNode is not None
              and (
                  f'{graph.graph.rootNode.pid}.{graph.graph.rootNode.opName}'
                  == root_method_name
                  or graph.graph.canonicalOpName(graph.graph.rootNode)
                  == root_method_name
              )
          )
      ]

    if trace_ids is not None:
      subset = [graph for graph in subset if graph.trace_id in trace_ids]

    if percentile_start != 0.0 or percentile_end != 100.0:
      if len(subset) <= 1:
        return subset
      subset_sorted = sorted(subset, key=lambda g: g.get_duration())
      start_index = int(len(subset_sorted) * percentile_start / 100.0)
      end_index = int(len(subset_sorted) * percentile_end / 100.0)

      allowed_graphs = set(subset_sorted[start_index:end_index])
      return [graph for graph in subset if graph in allowed_graphs]

    return subset

  def restore_to_original_timestamps(self) -> None:
    """Restores the graphs to their original timestamps."""
    for graph in self.graphs.values():
      graph.restore_to_original_timestamps()

  def get_dependency_graph(self) -> DependencyGraph:
    """Gets the dependency graph for all graphs in the collection."""
    graphs = [
        graph.graph for graph in self.graphs.values() if graph.graph is not None
    ]
    return DependencyGraph(graphs=graphs)

  def get_retimer(self) -> Retimer:
    """Gets the retimer for all graphs in the collection."""
    return Retimer(self.get_dependency_graph())

  def get_most_average_drag_by_method(
      self, start_method_name: str | None = None
  ) -> list[tuple[str, float]]:
    """Gets the most average drag by method for a collection of graphs."""
    drag_by_method: dict[str, list[float]] = {}
    for graph in self.graphs.values():
      if start_method_name:
        nodes = graph.get_nodes_by_method(start_method_name)
        if not nodes:
          continue
        for node in nodes:
          critical_path = graph.get_critical_path_for_node(node)
          drag = critical_path.calculate_drag(exclusive=True)
          for span_id, drag_value in drag.drag_per_span.items():
            method = graph.graph.nodeHT[span_id].pid
            if method not in drag_by_method:
              drag_by_method[method] = []
            drag_by_method[method].append(drag_value)
      else:
        critical_path = graph.get_critical_path()
        drag = critical_path.calculate_drag(exclusive=True)
        for span_id, drag_value in drag.drag_per_span.items():
          method = graph.graph.nodeHT[span_id].pid
          if method not in drag_by_method:
            drag_by_method[method] = []
          drag_by_method[method].append(drag_value)
    most_drag = []
    for method, drag_values in drag_by_method.items():
      most_drag.append((method, sum(drag_values) / len(drag_values)))
    most_drag.sort(key=lambda x: x[1], reverse=True)
    return most_drag

  def get_most_average_slack_by_method(
      self, start_method_name: str | None = None
  ) -> list[tuple[str, float]]:
    """Gets the most average slack by method for a collection of graphs."""
    slack_by_method: dict[str, list[float]] = {}
    for graph in self.graphs.values():
      if start_method_name:
        nodes = graph.get_nodes_by_method(start_method_name)
        if not nodes:
          continue
        for node in nodes:
          critical_path = graph.get_critical_path_for_node(node)
          slack = critical_path.calculate_slack()
          for span_id, slack_value in slack.slack_per_span.items():
            method = graph.graph.nodeHT[span_id].pid
            if method not in slack_by_method:
              slack_by_method[method] = []
            slack_by_method[method].append(slack_value)
      else:
        critical_path = graph.get_critical_path()
        slack = critical_path.calculate_slack()
        for span_id, slack_value in slack.slack_per_span.items():
          method = graph.graph.nodeHT[span_id].pid
          if method not in slack_by_method:
            slack_by_method[method] = []
          slack_by_method[method].append(slack_value)
    most_slack = []
    for method, slack_values in slack_by_method.items():
      most_slack.append((method, sum(slack_values) / len(slack_values)))
    most_slack.sort(key=lambda x: x[1], reverse=True)
    return most_slack
