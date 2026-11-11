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

"""Defines the CriticalPath, Slack, and Drag classes."""

import collections
import attrs
from dependency_graph import DependencyGraph
import graph_utils
from third_party.CRISP.graph import Graph
from third_party.CRISP.graph import GraphNode


@attrs.define(frozen=True)
class Slack:
  """Class to store slack for a critical path.

  Attributes:
    slack_per_span: A mapping from span id to the slack for that span.
    total_slack: The total slack for the critical path.
  """

  slack_per_span: dict[str, float]
  total_slack: float


@attrs.define(frozen=True)
class Drag:
  """Class to store drag for a critical path.

  Attributes:
    drag_per_span: A mapping from span id to the drag for that span.
    total_drag: The total drag for the critical path.
  """

  drag_per_span: dict[str, float]
  total_drag: float


class CriticalPath:
  """Class to store critical path data."""

  def __init__(self, graph: Graph, start_node: GraphNode | None = None):
    """Initializes the CriticalPath object.

    Args:
      graph: The graph to find the critical path for.
      start_node: The node to start the critical path from. If None, uses the
        graph's root node.

    Attributes:
      graph: The graph to find the critical path for.
      start_node: The node to start the critical path from.
      cp: The critical path.
      slack: The slack for each span in the graph.
      drag: The drag for each span in the graph.
    """
    self.graph = graph
    self.start_node = start_node if start_node else graph.rootNode
    if self.start_node is None:
      raise ValueError('Graph has no root node and no start node specified.')
    self.cp = graph.computeCriticalPath(self.start_node)
    self.slack: Slack | None = None
    self.drag: Drag | None = None
    self.exclusive_drag: Drag | None = None

  def __repr__(self):
    return f'CriticalPath(cp={self.cp})'

  def __str__(self):
    cp_string = ''.join(f'{node.pid} -> ' for node in self.cp)
    return cp_string[:-4]

  def _compute_earliest_start_times(
      self,
      curr_node: GraphNode,
      earliest_start_times: dict[str, float],
      deps: DependencyGraph,
  ) -> None:
    """Computes the earliest start times for each node in the graph."""
    if (
        curr_node.parentSpanId
        and curr_node.parentSpanId in self.graph.nodeHT
        and curr_node != self.start_node
    ):
      parent_node = self.graph.nodeHT[curr_node.parentSpanId]
    else:
      parent_node = None

    if not parent_node:
      earliest_start_times[curr_node.sid] = curr_node.startTime
      return

    siblings = list(parent_node.children)
    siblings.sort(key=lambda x: x.startTime)
    if curr_node not in siblings or not siblings:
      return

    first_sibling_start_time = siblings[0].startTime
    node_name = graph_utils.get_node_name(curr_node, self.graph)
    node_deps = deps.deps.get(node_name)
    curr_happens_before = node_deps.happens_before if node_deps else set()
    if curr_happens_before:
      previous_happens_before_node = None
      for sibling in siblings:
        sibling_name = graph_utils.get_node_name(sibling, self.graph)
        if sibling.sid == curr_node.sid:
          break
        elif (
            sibling_name in curr_happens_before
            and sibling.endTime < curr_node.startTime
        ):
          previous_happens_before_node = sibling
      earliest_start_times[curr_node.sid] = (
          previous_happens_before_node.endTime
          if previous_happens_before_node
          else first_sibling_start_time
      )
    else:
      earliest_start_times[curr_node.sid] = first_sibling_start_time

  def _compute_latest_start_times(
      self,
      curr_node: GraphNode,
      latest_start_times: dict[str, float],
      critical_end_times: dict[str, float],
  ) -> None:
    """Computes the latest start times for each node in the graph."""
    cp_end_time = critical_end_times[curr_node.sid]
    if curr_node.sid not in latest_start_times:
      latest_start_times[curr_node.sid] = cp_end_time - curr_node.duration

  def _get_subgraph_nodes(self) -> list[str]:
    """Returns list of span IDs for the subtree rooted at start_node.

    Includes both synchronous and asynchronous descendants.
    """
    subgraph_nodes = []
    for span_id, node in self.graph.nodeHT.items():
      curr = node
      while curr:
        if curr == self.start_node:
          subgraph_nodes.append(span_id)
          break
        if not curr.parentSpanId or curr.parentSpanId not in self.graph.nodeHT:
          break
        curr = self.graph.nodeHT[curr.parentSpanId]
    return subgraph_nodes

  def calculate_slack(
      self, dependency_graph: DependencyGraph | None = None
  ) -> Slack:
    """Calculates the slack for each node in the graph.

    To compute slack, we need the earliest start time (the time that a task can
    start given the dependencies), and the latest start time (the time a task
    can start without delaying the critical path).

    Slack = Latest Start Time - Earliest Start Time

    If Slack == 0: The task is on the critical path.

    If Slack > 0: The task is not on the critical path, and can be delayed
    without delaying the critical path.

    Args:
      dependency_graph: The dependency graph to use for the slack calculation
        inferred from the graph or collection. If None, will use the dependency
        graph for the current critical path. Note: this is determined by
        heuristics, so any errors in the dependency graph will be propagated.

    Returns:
      A Slack object containing the slack for each node in the graph.
    """
    if self.slack:
      return self.slack

    cp = self.cp
    slack = {}

    if not dependency_graph:
      dependency_graph = DependencyGraph(self.graph)

    subgraph_nodes = self._get_subgraph_nodes()

    critical_end_times = {}
    for node in cp:
      if (
          node.parentSpanId
          and node.parentSpanId in self.graph.nodeHT
          and node != self.start_node
      ):
        parent_node = self.graph.nodeHT[node.parentSpanId]
      else:
        parent_node = None
      critical_end_times[node.sid] = node.endTime
      if parent_node:
        for child in parent_node.children:
          if child.endTime < node.endTime:
            critical_end_times[child.sid] = node.endTime
    for span_id in subgraph_nodes:
      if span_id not in critical_end_times:
        node = self.graph.nodeHT[span_id]
        if (
            node.parentSpanId
            and node.parentSpanId in self.graph.nodeHT
            and node != self.start_node
        ):
          parent_node = self.graph.nodeHT[node.parentSpanId]
        else:
          parent_node = None
        critical_end_times[span_id] = (
            parent_node.endTime if parent_node else node.endTime
        )

    earliest_start_times: dict[str, float] = {}
    latest_start_times: dict[str, float] = {}

    for span_id in subgraph_nodes:
      node = self.graph.nodeHT[span_id]
      self._compute_earliest_start_times(
          node, earliest_start_times, dependency_graph
      )
      self._compute_latest_start_times(
          node, latest_start_times, critical_end_times
      )

    for span_id in subgraph_nodes:
      parent_node = self.graph.nodeHT[span_id]
      if not parent_node.children:
        continue

      siblings_by_name = collections.defaultdict(list)
      for sibling in parent_node.children:
        sib_name = graph_utils.get_node_name(sibling, self.graph)
        siblings_by_name[sib_name].append(sibling)

      sorted_siblings = sorted(
          parent_node.children, key=lambda x: x.startTime, reverse=True
      )
      for child in sorted_siblings:
        child_name = graph_utils.get_node_name(child, self.graph)
        child_deps = dependency_graph.deps.get(child_name)
        if not child_deps or not child_deps.happens_before:
          continue

        for dep_name in child_deps.happens_before:
          if dep_name in siblings_by_name:
            for sibling in siblings_by_name[dep_name]:
              if sibling.sid == child.sid:
                continue
              if (
                  sibling.sid in latest_start_times
                  and child.sid in latest_start_times
              ):
                latest_start_times[sibling.sid] = min(
                    latest_start_times[sibling.sid],
                    latest_start_times[child.sid] - sibling.duration,
                )

    for span_id in subgraph_nodes:
      node = self.graph.nodeHT[span_id]
      if (
          node not in cp
          and node.sid in latest_start_times
          and node.sid in earliest_start_times
      ):
        slack[node.sid] = (
            latest_start_times[node.sid] - earliest_start_times[node.sid]
        )
      else:
        slack[node.sid] = 0

    total_slack = sum(slack.values())
    self.slack = Slack(slack, total_slack)
    return self.slack

  def _get_exclusive_cp_time(self) -> dict[GraphNode, float]:
    """Gets the exclusive time for a node in the critical path."""
    cp = self.cp
    exclusive_cp_time: dict[GraphNode, float] = collections.defaultdict(float)

    for node in reversed(cp):
      exclusive_cp_time[node] += node.duration
      parent = node.parent
      if parent and node != self.start_node:
        exclusive_cp_time[parent] -= node.duration

    return exclusive_cp_time

  def get_exclusive_time(self, node: GraphNode) -> float:
    """Gets the exclusive time for a node in the graph."""
    children = list(node.children)
    if not children:
      return node.duration
    children.sort(key=lambda node: node.startTime)
    curr_exclusive_time = node.duration
    child_exclusive_time = 0
    curr_end = 0
    for child in children:
      if child.startTime < node.startTime:
        continue
      if child.endTime > node.endTime:
        continue
      if child.startTime > curr_end:
        curr_end = child.endTime
        child_exclusive_time += child.duration
      else:
        child_exclusive_time += child.endTime - curr_end
        curr_end = child.endTime
    return curr_exclusive_time - child_exclusive_time

  def calculate_drag(self, exclusive: bool = False) -> Drag:
    """Calculates the drag for each node in the graph.

    For nodes that are not on the critical path, drag is 0.
    For nodes that are on the critical path, drag is the amount of time that
    the node contributes to the critical path. The maximum possible drag for a
    node on the critical path is its duration.

    The exclusive drag is the amount of time that a node contributes to the
    critical path without considering the drag of its children. This is
    equivalent to the overlap of the drag and the critical path.

    Drag is the amount of time that a node contributes to the critical path.

    Args:
      exclusive: Whether to calculate the exclusive drag or the inclusive drag.

    Returns:
      A Drag object containing the drag for each node in the graph.
    """
    if not exclusive and self.drag:
      return self.drag

    if exclusive and self.exclusive_drag:
      return self.exclusive_drag

    drag = {}
    exclusive_cp_time = self._get_exclusive_cp_time()

    for i, node in enumerate(self.cp):
      if i == 0:
        if exclusive:
          drag[node.sid] = exclusive_cp_time[node]
        else:
          drag[node.sid] = node.duration
      else:
        parent = node.parent
        if not parent:
          if exclusive:
            drag[node.sid] = exclusive_cp_time[node]
          else:
            drag[node.sid] = node.duration
        else:
          siblings = parent.children
          if len(siblings) == 1 or not siblings:
            if exclusive:
              drag[node.sid] = exclusive_cp_time[node]
            else:
              drag[node.sid] = node.duration
          else:
            sorted_siblings = sorted(
                siblings, key=lambda x: x.endTime, reverse=True
            )
            node_idx = next(
                (
                    index
                    for index, sibling in enumerate(sorted_siblings)
                    if sibling.sid == node.sid
                ),
                None,
            )
            if node_idx == len(sorted_siblings) - 1 or node_idx is None:
              if exclusive:
                drag[node.sid] = exclusive_cp_time[node]
              else:
                drag[node.sid] = node.duration
            else:
              next_sibling = sorted_siblings[node_idx + 1]
              if exclusive:
                if i + 1 < len(self.cp):
                  child_cp_end_time = self.cp[i + 1].endTime
                  child_cp_start_time = self.cp[i + 1].startTime
                  drag_val = node.endTime - max(
                      child_cp_end_time, next_sibling.endTime
                  )
                  if child_cp_start_time > next_sibling.endTime:
                    drag_val += child_cp_start_time - next_sibling.endTime
                  drag[node.sid] = drag_val
                else:
                  drag[node.sid] = node.endTime - next_sibling.endTime
              else:
                drag[node.sid] = node.endTime - next_sibling.endTime

      # Bounding drag calculations
      if node.sid in drag:
        if exclusive:
          drag[node.sid] = max(
              0.0, min(drag[node.sid], self.get_exclusive_time(node))
          )
        else:
          drag[node.sid] = max(0.0, min(drag[node.sid], node.duration))

    if exclusive:
      total_drag = sum(drag.values())
      self.exclusive_drag = Drag(drag, total_drag)
      return self.exclusive_drag

    total_drag = sum(drag.values())
    self.drag = Drag(drag, total_drag)
    return self.drag

  def get_slack_per_method(
      self, dependency_graph: DependencyGraph | None = None
  ) -> dict[str, list[float]]:
    """Gets the slack per method for spans not on the critical path."""
    slack_obj = self.slack
    if slack_obj is None:
      if not dependency_graph:
        dependency_graph = DependencyGraph(self.graph)
      slack_obj = self.calculate_slack(dependency_graph=dependency_graph)
    slack_per_method = collections.defaultdict(list)
    for span, slack in slack_obj.slack_per_span.items():
      node = self.graph.nodeHT[span]
      method_name = f'{node.pid}.{node.opName}' if node.pid else node.opName
      slack_per_method[method_name].append(slack)
    return slack_per_method

  def get_drag_per_method(
      self, exclusive: bool = False
  ) -> dict[str, list[float]]:
    """Gets the drag per method for the critical path."""
    drag_obj = self.calculate_drag(exclusive=exclusive)
    drag_per_method = collections.defaultdict(list)
    for span, drag in drag_obj.drag_per_span.items():
      node = self.graph.nodeHT[span]
      method_name = f'{node.pid}.{node.opName}' if node.pid else node.opName
      drag_per_method[method_name].append(drag)
    return drag_per_method

  def get_contribution_by_method(
      self, percent: bool = True
  ) -> dict[str, float]:
    """Gets the contribution of each method to the critical path.

    Args:
      percent: Whether to return the contribution as a percentage of the total
        critical path duration or as an absolute duration.

    Returns:
      A dictionary mapping method names to the contribution of that method to
      the critical path.
    """
    cp_contribution_by_method = {}
    exclusive_cp_time = self._get_exclusive_cp_time()

    for node, duration in exclusive_cp_time.items():
      op = self.graph.canonicalOpName(node)
      if percent:
        if self.start_node and self.start_node.duration > 0:
          cp_contribution = (duration / self.start_node.duration) * 100
        else:
          cp_contribution = 0.0
      else:
        cp_contribution = duration
      if op not in cp_contribution_by_method:
        cp_contribution_by_method[op] = 0.0
      cp_contribution_by_method[op] += cp_contribution

    return cp_contribution_by_method
