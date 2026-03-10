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
from typing import Any

from third_party.CRISP.graph import Graph, GraphNode
import pandas as pd

import constants
import df_utils
from critical_path import CriticalPath
from dependency_graph import DependencyGraph
from retimer import Retimer


def _df_to_jaeger_json(df: pd.DataFrame, trace_id: int | str) -> dict[str, Any]:
  """Converts a pandas dataframe to a Jaeger JSON dictionary representation.

  Args:
      df: A pandas dataframe with native Jaeger columns.
      trace_id: The trace id.

  Returns:
      A dictionary representing the Jaeger JSON structure.
  """
  jaeger_data = []
  trace_data = {'traceID': trace_id, 'spans': [], 'processes': {}}
  processes = {}
  # sort the rows by start time
  df = df.sort_values(by=constants.JAEGER_START_TIME)
  for _, row in df.iterrows():
    process_id = row[constants.JAEGER_PROCESS_ID]
    operation_name = row[constants.JAEGER_OPERATION_NAME]
    processes[process_id] = {}
    processes[process_id]['serviceName'] = process_id

    span = {
        'traceID': trace_id,
        'spanID': row[constants.JAEGER_SPAN_ID],
        'operationName': operation_name,
        'startTime': row[constants.JAEGER_START_TIME],
        'duration': float(row[constants.JAEGER_DURATION]),
        'references': [],
        'warnings': None,
        'processID': process_id,
    }

    if (
        constants.PARENT_SPAN_ID in row
        and row[constants.PARENT_SPAN_ID]
        and row[constants.PARENT_SPAN_ID] != 0
    ):
      span['references'] = [{
          'refType': 'CHILD_OF',
          'traceID': trace_id,
          'spanID': row[constants.PARENT_SPAN_ID],
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
  """

  def __init__(self, crisp_graph: Graph):
    self.trace_id = crisp_graph.filename
    self.async_span_ids = set()
    self.graph = crisp_graph
    self._remove_asynchronous_spans()
    self._add_original_timestamps()
    self.cp = None

  @classmethod
  def from_dataframe(cls, df: pd.DataFrame) -> 'CrispGraph':
    """Initializes the Graph object with a pandas dataframe."""

    # if there are multiple traceids in the dataframe, return an error
    if len(set(df[constants.JAEGER_TRACE_ID])) != 1:
      raise ValueError('The dataframe must contain only one trace id.')

    trace_id = df[constants.JAEGER_TRACE_ID].iloc[0]

    curr_json = _df_to_jaeger_json(df, trace_id)
    if not curr_json['data']:
      raise (ValueError('No data found for trace id: %s' % trace_id))

    root_span_id = df_utils.get_root_span_id(df)
    root_row = df[df[constants.JAEGER_SPAN_ID] == root_span_id]
    sn = root_row[constants.JAEGER_PROCESS_ID].iloc[0]
    op = root_row[constants.JAEGER_OPERATION_NAME].iloc[0]

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
    """Adds span metadata to the graph.

    Args:
      df: A pandas dataframe.
    """
    if self.graph is None:
      return

    # Columns that are already handled or should not be in span_components
    excluded_columns = set(constants.RAW_COLUMNS) | {constants.REFERENCES}

    for i in range(len(df)):
      row = df.iloc[i]
      span_id = row[constants.JAEGER_SPAN_ID]
      if span_id not in self.graph.nodeHT:
        continue
      curr_node = self.graph.nodeHT[span_id]
      if curr_node is None:
        continue
      curr_node.span_components = {}
      for col in df.columns:
        if col not in excluded_columns:
          curr_node.span_components[col] = row[col]

  def _remove_asynchronous_spans(self) -> None:
    """Removes asynchronous spans from a node's children.

    We identify asynchronous spans as spans that end after their parent span
    completes.
    """
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

  def _add_original_timestamps(self) -> None:
    """Adds original timestamps to the graph."""
    if self.graph is None:
      return
    for _, node in self.graph.nodeHT.items():
      if node is None:
        continue
      node.original_start_time = node.startTime
      node.original_end_time = node.endTime

  def restore_to_original_timestamps(self) -> None:
    """Restores the graph to its original timestamps."""
    if self.graph is None:
      return
    self.graph.retimed = False
    for _, node in self.graph.nodeHT.items():
      if node is None:
        continue
      node.startTime = node.original_start_time
      node.endTime = node.original_end_time
      node.duration = node.endTime - node.startTime

  def is_retimed(self) -> bool:
    """Checks if the graph has been retimed."""
    if self.graph is None:
      return False
    try:
      return self.graph.retimed  # type: ignore[attribute-error]
    except AttributeError:
      for _, node in self.graph.nodeHT.items():
        if node is None:
          continue
        if not hasattr(node, 'original_start_time'):
          return False
        if not hasattr(node, 'original_end_time'):
          return False
        if node.startTime != node.original_start_time:
          return True
        if node.endTime != node.original_end_time:
          return True
      return False

  def get_critical_path(self) -> CriticalPath:
    """Gets the critical path for the graph."""
    if self.is_retimed():
      return CriticalPath(self.graph)
    if not self.cp:
      self.cp = CriticalPath(self.graph)
    return self.cp

  def get_root_method(self) -> str:
    """Returns the root method name and an empty string if the graph is None."""
    if not self.graph:
      return ''
    return self.graph.rootNode.pid

  def get_duration(self) -> float:
    """Gets the duration of the root node for the graph."""
    if not self.graph:
      return 0
    return self.graph.rootNode.duration

  def get_node_from_span_id(self, span_id: str) -> GraphNode | None:
    """Returns node from the graph given a span id and None if not found.

    Args:
      span_id: The span id.
    """
    if not self.graph:
      return None
    return self.graph.nodeHT[span_id]

  def get_exclusive_durations(self) -> dict[str, float]:
    """Gets the exclusive durations for each node in the graph.

    Returns:
      A dictionary mapping span ids to exclusive durations.

    Raises:
      ValueError: If the graph is None.
    """
    exclusive_times = {}
    if self.graph is None:
      return exclusive_times
    for node in self.graph.nodeHT.values():
      children = list(node.children)
      if not children:
        exclusive_times[node.sid] = node.duration
        continue
      # else subtract children time from current span (this ignores async spans)
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
          # child does not overlap with the last child then add the entire time
          curr_end = child.endTime
          child_exclusive_time += child.duration
        else:
          # child end does overlap with the last child, so only add the diff
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
    """Gets the dependency graph for the graph.

    Returns:
      The dependency graph generated from the graph.

    Raises:
      ValueError: If the graph is None.
    """
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
    """Initializes the GraphCollection object.

    Args:
      df: A pandas dataframe with the columns specified in the docstring.
      graphs_list: A list of CrispGraph objects.
      max_traces: The maximum number of traces to read.

    Raises:
      ValueError: If both df and graphs_list are None or if both df and
      graphs_list are set.

    Returns:
      A GraphCollection object.
    """
    self.graphs = {}
    self.root_methods = set()

    # check that at least one of df and graphs_list is not None
    if df is None and graphs_list is None:
      raise ValueError('At least one of df and graphs_list must not be None.')

    if df is not None and graphs_list:
      raise ValueError('Both df and graphs_list cannot be set.')

    i = 0

    # if we are given a dataframe
    if df is not None and not df.empty:  # type: ignore[attribute-error]
      for trace_id, group in df.groupby(constants.JAEGER_TRACE_ID):
        self.graphs[trace_id] = CrispGraph.from_dataframe(group)
        i += 1
        if i == max_traces:
          print(
              f'Reached max traces of {max_traces}, did not complete reading'
              ' all traces in the dataframe.'
          )
          break

    # if we are given a list of graphs
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

  def get_graph(self, trace_id: str) -> CrispGraph:
    """Gets the graph for a given trace id."""
    return self.graphs[trace_id]

  def get_root_methods(self) -> set[str]:
    """Gets the root method names for all graphs in the collection."""
    root_methods = set()
    for graph in self.graphs.values():
      if not graph.graph:
        continue
      root_node = graph.graph.rootNode  # type: ignore[attribute-error]
      if root_node is not None:
        root_method_name = root_node.pid
        root_methods.add(root_method_name)
    return root_methods

  def get_graphs_subset(
      self,
      root_method_name: str | None = None,
      trace_ids: Collection[str] | None = None,
      percentile_start: float = 0,
      percentile_end: float = 100,
  ) -> Collection[CrispGraph]:
    """Gets a subset of graphs for a root method, trace_id, or percentile.

    Args:
      root_method_name: The name of the root method to filter by. If None,
        include all root methods.
      trace_ids: The trace ids to filter by. If None, include all trace ids.
      percentile_start: The start percentile to filter by. Must be between 0 and
        100.
      percentile_end: The end percentile to filter by. Must be between 0 and
        100.

    Returns:
      A collection of graphs that match the filters.

    Raises:
      ValueError: If percentile_start or percentile_end is not between 0 and
      100.
    """
    if percentile_start < 0 or percentile_start > 100:
      raise ValueError('Percentile start must be between 0 and 100.')
    if percentile_end < 0 or percentile_end > 100:
      raise ValueError('Percentile end must be between 0 and 100.')

    subset = list(self.graphs.values())

    # first filter by the root_method_name
    if root_method_name is not None:
      subset = [
          graph
          for graph in subset
          if graph.get_root_method() == root_method_name
      ]

    # then filter by the trace_ids
    if trace_ids is not None:
      subset = [graph for graph in subset if graph.trace_id in trace_ids]

    # then filter by the percentile range
    if percentile_start != 0 or percentile_end != 100:
      durations = [graph.get_duration() for graph in subset]
      if len(durations) <= 1:
        return subset
      durations = sorted(durations)
      start_index = max(0, int(len(durations) * percentile_start / 100))
      end_index = min(
          len(durations) - 1, int(len(durations) * percentile_end / 100)
      )

      percentile_start_value = durations[start_index]
      percentile_end_value = durations[end_index]
      subset = [
          graph
          for graph in subset
          if percentile_start_value
          <= graph.get_duration()
          <= percentile_end_value
      ]

    # return what is remaining
    return subset

  def restore_to_original_timestamps(self) -> None:
    """Restores the graphs to their original timestamps."""
    for graph in self.graphs.values():
      graph.restore_to_original_timestamps()

  def get_dependency_graph(self) -> DependencyGraph:
    """Gets the dependency graph for all graphs in the collection."""
    graphs = [graph.graph for graph in self.graphs.values()]
    return DependencyGraph(graphs=graphs)  # type: ignore[wrong-arg-types]

  def get_retimer(self) -> Retimer:
    """Gets the retimer for all graphs in the collection."""
    return Retimer(self.get_dependency_graph())

  def get_most_average_drag_by_method(self) -> list[tuple[str, float]]:
    """Gets the most average drag by method for a collection of graphs."""
    drag_by_method = {}
    for graph in self.graphs.values():
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

  def get_most_average_slack_by_method(self) -> list[tuple[str, float]]:
    """Gets the most average slack by method for a collection of graphs."""
    slack_by_method = {}
    for graph in self.graphs.values():
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
