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

"""Class for retiming nodes in a graph given a dependency graph."""

from third_party.CRISP import graph as crisp_graph
import dependency_graph
import graph_utils


class Retimer:
  """Class for retiming nodes in a graph given a dependency graph.

  An instance of this class is created for a given dependency graph. With a
  single dependency graph, the retimer class can be used to retime any number of
  nodes in any number of graphs.
  """

  def __init__(self, dep_graph: dependency_graph.DependencyGraph):
    self.dependency_graph = dep_graph

  def __repr__(self):
    return f'Retimer(dependency_graph={self.dependency_graph})'

  def retime_node(
      self,
      g: crisp_graph.Graph,
      node_span_id: str,
      new_start: float,
      new_end: float,
      freeze_starts: bool = True,
  ) -> None:
    """Retimes a node in a graph given a dependency graph.

    using a dependency graph, retime a node in the dependency
    to retime a node, we must
      1. identify the affected node in the graph
      2. retime the node
      3. move all siblings forward or backwards as need be
      4. adjust the parent as need be
      5. call retime_node on the parent

    assumptions for current dependency graph:
      1. the new start and end time of a node do not conflict with its children
      2. nodes only exhibit happens-before relationships
      3. the new start and end times are valid and do not violate the
      relationships in the graph (ex: if A must complete before B can begin, we
      assume that the new_start of A will not violate this dependency
      relationship)
      4. a parent span takes constant time to dispatch and aggregate siblings,
      so if a child span is delayed, we need only adjust the parent span if the
      child is now the latest ending child

    Args:
      g: The graph to retime.
      node_span_id: The span id of the node to retime.
      new_start: The new start time of the node.
      new_end: The new end time of the node.
      freeze_starts: If true, the starts of all nodes will be frozen. This is
        useful for retiming nodes in parallel.
    """
    deps = self.dependency_graph.deps
    node = g.nodeHT[node_span_id]

    # nothing to change
    if new_start == node.startTime and new_end == node.endTime:
      return

    if new_start > new_end:
      raise ValueError(
          f'New start time {new_start} is greater than new end time'
          f' {new_end} for node {node.pid}.{node.opName}.'
      )

    g.retimed = True

    delay = (
        new_end - node.endTime
    )  # positive delay --> ends later, negative delay --> ends sooner

    # this is an estimation of the parent processing time that we will need to
    # maintain if the parent node needs to be retimed
    parent_start_delay = 0
    parent_end_delay = 0
    if node.parentSpanId in g.nodeHT:
      # get the gap between the first child that starts after the parent starts
      # and the parent start time
      parent_node = g.nodeHT[node.parentSpanId]
      children = sorted(parent_node.children, key=lambda child: child.startTime)
      parent_start_delay = (
          children[0].startTime - parent_node.startTime if children else 0
      )

      # get the gap between the last child that ends before the parent ends and
      # the parent end time
      children = sorted(children, key=lambda child: child.endTime)
      non_async_children = [
          child for child in children if child.endTime <= parent_node.endTime
      ]
      parent_end_delay = (
          parent_node.endTime - non_async_children[-1].endTime
          if non_async_children
          else 0
      )

    # adjust self
    original_node_end = node.endTime  # need this to compare with siblings
    node.startTime = new_start
    node.endTime = new_end
    node.duration = new_end - new_start

    # get parent node if there is one
    parent_sid = node.parentSpanId
    if parent_sid in g.nodeHT:
      parent_node = g.nodeHT[parent_sid]
    else:
      # node has no parent to propagate to, so return
      return

    # adjust siblings if the sibling happens after a given node
    # (the happens before relationship means that a node starts after the
    # previous ends)
    node_name = graph_utils.get_node_name(node, g)
    siblings = [
        child for child in parent_node.children if child.sid != node_span_id
    ]
    for sibling in siblings:
      if (
          node_name
          in deps[graph_utils.get_node_name(sibling, g)].happens_before
          and sibling.startTime > original_node_end
      ):
        sibling.startTime += delay
        sibling.endTime += delay
      else:
        # if the sibling does not have a happens before relationship, then we
        # can ignore it because it means that it was deployed independently of
        # the current node so it will not be affected by the delay/rush of the
        # current node
        continue

    # need to find the last sibling that ends before the parent ends and the
    # first sibling that starts after the parent starts
    siblings.append(node)
    first_sibling_after_parent_start = node
    last_sibling_before_parent_end = node

    # get the child dependent siblings from the observed dependency graph
    dependent_siblings = [
        child
        for child in siblings
        if (
            graph_utils.get_node_name(child, g)
            in deps[graph_utils.get_node_name(parent_node, g)].child_dependents
        )
        and child.original_end_time <= parent_node.original_end_time  # type: ignore[attribute-error]
    ]

    if dependent_siblings:
      last_sibling_before_parent_end = max(
          dependent_siblings, key=lambda child: child.endTime
      )

    for sibling in siblings:
      if sibling.startTime >= parent_node.startTime and (
          sibling.startTime < first_sibling_after_parent_start.startTime
      ):
        first_sibling_after_parent_start = sibling
      if sibling.endTime <= parent_node.endTime and (
          sibling.endTime > last_sibling_before_parent_end.endTime
          and (sibling.original_end_time <= parent_node.original_end_time)  # type: ignore[attribute-error]
      ):
        last_sibling_before_parent_end = sibling

    if freeze_starts:
      new_parent_start = parent_node.startTime
    elif parent_start_delay > 0:
      # if the parent has a start delay, then we need to adjust the parent
      # start time to account for the delay
      new_parent_start = (
          first_sibling_after_parent_start.startTime - parent_start_delay
      )
    else:
      # else, we can use the smaller of the original parent start time or the
      # first child start time
      new_parent_start = min(
          parent_node.startTime, first_sibling_after_parent_start.startTime
      )

    if (
        last_sibling_before_parent_end.original_end_time
        > parent_node.original_end_time
    ):  # type: ignore[attribute-error]
      new_parent_end = parent_node.endTime
    else:
      new_parent_end = parent_end_delay + last_sibling_before_parent_end.endTime

    if new_parent_start > new_parent_end:
      return

    # propagate up
    self.retime_node(g, parent_node.sid, new_parent_start, new_parent_end)

    return

  def retime_method(
      self,
      graph: crisp_graph.Graph,
      method: str,
      percent_difference: float | None = None,
      fixed_difference: float | None = None,
  ) -> float:
    """Retimes a method in a graph given a dependency graph."""
    if percent_difference is not None and fixed_difference is not None:
      raise ValueError(
          'Only one of percent_difference or fixed_difference should be set.'
      )
    if percent_difference is None and fixed_difference is None:
      raise ValueError(
          'One of percent_difference or fixed_difference must be set.'
      )

    original_duration = graph.rootNode.duration

    for node in graph.nodeHT.values():
      if (node.pid + '.' + node.opName) == method:
        if percent_difference is not None:
          adjustment_amount = node.duration * percent_difference / 100.0
        else:
          # make sure that if the fixed difference is negative, we don't
          # retime the node backwards
          adjustment_amount = fixed_difference
          if node.endTime + fixed_difference < node.startTime:
            adjustment_amount = node.duration
        self.retime_node(
            graph,
            node.sid,
            node.startTime,
            node.endTime + adjustment_amount,
        )

    return original_duration - graph.rootNode.duration
