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
from third_party.CRISP.graph import Graph, GraphNode

import graph_utils
from dependency_graph import DependencyGraph


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

  def __init__(self, graph: Graph):
    """Initializes the CriticalPath object.

    Args:
      graph: The graph to find the critical path for.

    Attributes:
      graph: The graph to find the critical path for.
      cp: The critical path.
      slack: The slack for each span in the graph.
      drag: The drag for each span in the graph.
    """
    self.graph = graph
    self.cp = graph.findCriticalPath()
    self.slack = None
    self.drag = None
    self.exclusive_drag = None

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
    # the earliest start time of a node is the soonest it can start without
    # violating happens-before relationships and the parent start delay
    # by default we will say that the soonest a child node can start is the time
    # that the earliest of its children starts, but we may ammend this when we
    # analyze a given node's siblings

    # if the curr_node has no happen-before relationships, then the earliest it
    # can start is the time that the parent is ready to start handling children,
    # (aka the time it starts its first child)
    if curr_node.parentSpanId and curr_node.parentSpanId in self.graph.nodeHT:
      parent_node = self.graph.nodeHT[curr_node.parentSpanId]
    else:
      parent_node = None

    if not parent_node:
      # if the node has no parent, then the earliest it can start is when it is
      # currently starting
      earliest_start_times[curr_node.sid] = curr_node.startTime
      return

    siblings = list(parent_node.children)
    siblings.sort(key=lambda x: x.startTime)
    if curr_node not in siblings or not siblings:
      # curr node not in siblings so it must be an asynchronous span
      return

    # get the first sibling start time since they are sorted
    first_sibling_start_time = siblings[0].startTime
    curr_happens_before = deps.deps[
        graph_utils.get_node_name(curr_node, self.graph)  # type: ignore[attribute-error]
    ].happens_before
    if curr_happens_before:
      previous_happens_before_node = None
      # go through siblings and find the happens before node that is closest
      # to the current node but happens before the current node
      for sibling in siblings:
        sibling_name = graph_utils.get_node_name(sibling, self.graph)  # type: ignore[attribute-error]
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
    """Computes the latest start times for each node in the graph.

    Args:
      curr_node: The current node to compute the latest start time for.
      latest_start_times: A dictionary mapping span ids to the latest start
        times for those spans.
      critical_end_times: A dictionary mapping span ids to the critical end
        times for those spans.
    """
    # the latest start time for the current node is the end time of the critical
    # path - the time between the start and end of the current node
    # this is the scenario where the current node is the last node to finish
    # and the critical path ends at the end of this node
    cp_end_time = critical_end_times[curr_node.sid]
    if curr_node.sid not in latest_start_times:
      # case where node finishes right before the critical path end time
      latest_start_times[curr_node.sid] = cp_end_time - curr_node.duration

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

    (see documentation for full definition)

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

    # for each node, you need to get the earliest and latest start times
    # earliest start time comes from the parent span's earliest start
    # earliest end comes from the sibling in a group of siblings that is on the
    # critical path
    # to find the latest start time for a node, find the sibling that is on the
    # critical path if any are
    # if none of the siblings are on the critical path, use parent's end time

    earliest_start_times = {}
    latest_start_times = {}

    # traverse the CP to find the critical end times for each node
    critical_end_times = {}
    for node in cp:
      parent_node = (
          self.graph.nodeHT[node.parentSpanId]
          if node.parentSpanId and node.parentSpanId in self.graph.nodeHT
          else None
      )
      critical_end_times[node.sid] = node.endTime
      if parent_node:
        for child in parent_node.children:
          if child.endTime < node.endTime:
            critical_end_times[child.sid] = node.endTime
    for span_id, node in self.graph.nodeHT.items():
      if span_id not in critical_end_times:
        parent_node = (
            self.graph.nodeHT[node.parentSpanId]
            if node.parentSpanId and node.parentSpanId in self.graph.nodeHT
            else None
        )
        critical_end_times[span_id] = (
            parent_node.endTime if parent_node else node.endTime
        )

    for _, node in self.graph.nodeHT.items():
      self._compute_earliest_start_times(
          node, earliest_start_times, dependency_graph
      )
      self._compute_latest_start_times(
          node, latest_start_times, critical_end_times
      )

    for node in self.graph.nodeHT.values():
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
    exclusive_cp_time = collections.defaultdict(float)

    # iterate through the cp and subtract the time of the children from the
    # current node's time to get the exclusive time
    for node in reversed(cp):
      exclusive_cp_time[node] += node.duration
      parent = node.parent
      if parent:
        exclusive_cp_time[parent] -= node.duration

    return exclusive_cp_time

  def get_exclusive_time(self, node: GraphNode) -> float:
    """Gets the exclusive time for a node in the graph.

    Args:
      node: The node to get the exclusive time for.

    Returns:
      The exclusive time for the node. The exclusive time for a node is the
      amount of time that the node is executing without any children overlapping
      with it.
    """
    children = list(node.children)
    if not children:
      return node.duration
    # else subtract children time from current span (this ignores async spans)
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
        # child does not overlap with the last child then add the entire time
        curr_end = child.endTime
        child_exclusive_time += child.duration
      else:
        # child end does overlap with the last child, so only add the diff
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
    (see documentation for full definition)

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

    # go through all nodes in the cp, those not in the cp have 0 drag
    for i, node in enumerate(self.cp):

      # root node is always on the critical path
      # if the node is the root node, then its drag is the exclusive cp time
      # or the duration if not exclusive
      if i == 0:
        if exclusive:
          drag[node.sid] = exclusive_cp_time[node]
        else:
          drag[node.sid] = node.duration
        continue

      # Use node.parent (always correct), not self.cp[i - 1]: computeCriticalPath
      # flattens each qualifying sibling's own subtree onto the flat cp list in
      # sequence, so for a parent with 3+ sequential non-overlapping children,
      # cp[i - 1] for the second-or-later chained sibling is an unrelated
      # leftover node from the *previous* sibling's subtree, not this node's
      # real parent. See CriticalPathTest for a regression case that would
      # otherwise silently misreport drag for such a node.
      parent = node.parent
      siblings = parent.children if parent else []

      # if the node has no siblings
      if len(siblings) == 1 or not siblings:
        if exclusive:
          drag[node.sid] = exclusive_cp_time[node]
        else:
          drag[node.sid] = node.duration
        continue

      # sort the siblings by reversed end time
      sorted_siblings = sorted(siblings, key=lambda x: x.endTime)[::-1]

      # find the index of the current node in the sorted siblings list
      node_idx = next(
          (
              index
              for index, sibling in enumerate(sorted_siblings)
              if sibling.sid == node.sid
          ),
          None,
      )

      # the last sibling is always on the critical path
      if node_idx == len(sorted_siblings) - 1 or node_idx is None:
        if exclusive:
          drag[node.sid] = exclusive_cp_time[node]
        else:
          drag[node.sid] = node.duration
        continue

      # assumes happens-before relationship for all siblings
      # finds the sibling that finishes before the current node as the
      # replacement for the current node on the critical path
      next_sibling = sorted_siblings[node_idx + 1]
      if exclusive:
        # get the overlap between the inclusive drag and the critical path
        # get the end time of the child's critical path end time and subtract
        # it from the current node's end time to get the overlap.
        #
        # Recompute node's own critical-path-continuing child directly from
        # node.children instead of relying on self.cp[i + 1]. In practice
        # self.cp[i + 1] is always node's own top child already (computeCriticalPath
        # places it immediately after node when node has children), so this is a
        # defensive simplification rather than a change in behavior -- it removes
        # the implicit dependency on that ordering invariant instead of leaving it
        # unstated, without needing to special-case node being a chained sibling.
        own_cp_children = sorted(node.children, key=lambda c: c.endTime)[::-1]
        if own_cp_children:
          own_cp_child = own_cp_children[0]
          child_cp_end_time = own_cp_child.endTime
          child_cp_start_time = own_cp_child.startTime
          drag[node.sid] = node.endTime - max(
              child_cp_end_time, next_sibling.endTime
          )
          if child_cp_start_time > next_sibling.endTime:
            drag[node.sid] += child_cp_start_time - next_sibling.endTime
        else:
          drag[node.sid] = node.endTime - next_sibling.endTime
      else:
        drag[node.sid] = node.endTime - next_sibling.endTime

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
    if not self.slack:
      if not dependency_graph:
        dependency_graph = DependencyGraph(self.graph)
      self.calculate_slack(dependency_graph=dependency_graph)
    slack_per_method = collections.defaultdict(list)
    for span, slack in self.slack.slack_per_span.items():  # type: ignore[attribute-error]
      node = self.graph.nodeHT[span]
      slack_per_method[node.pid].append(slack)
    return slack_per_method

  def get_drag_per_method(
      self, exclusive: bool = False
  ) -> dict[str, list[float]]:
    """Gets the drag per method for the critical path."""
    self.calculate_drag(exclusive=exclusive)
    drag_per_method = collections.defaultdict(list)
    drag_per_span_dict = (
        self.exclusive_drag.drag_per_span  # type: ignore[attribute-error]
        if exclusive
        else self.drag.drag_per_span  # type: ignore[attribute-error]
    )
    for span, drag in drag_per_span_dict.items():  # type: ignore[attribute-error]
      node = self.graph.nodeHT[span]
      drag_per_method[node.pid].append(drag)
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
    metrics = self.graph.getMetrics(self.cp)
    for op, duration in metrics.opTimeExclusive.items():
      if percent:
        cp_contribution = (duration / self.graph.rootNode.duration) * 100
      else:
        cp_contribution = duration
      if op not in cp_contribution_by_method:
        cp_contribution_by_method[op] = 0
      # do not average the contributions so we know what the impact is per
      # method in total
      cp_contribution_by_method[op] += cp_contribution

    return cp_contribution_by_method
