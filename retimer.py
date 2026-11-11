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

from collections.abc import Mapping, Sequence
from typing import Final

from third_party.CRISP import graph as crisp_graph
import dependency_graph
import graph_utils

DEFAULT_COMPONENT_NAMES: Final[tuple[str, ...]] = (
    'request_network_delta',
    'response_network_delta',
    'client_send_queue_delta',
    'server_recv_queue_delta',
    'client_recv_queue_delta',
    'server_send_queue_delta',
)


def _shift_descendants(node: crisp_graph.GraphNode, shift: float) -> None:
  for child in node.children:
    child.startTime += shift
    child.endTime += shift
    _shift_descendants(child, shift)


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

    delay = (
        new_end - node.endTime
    )  # positive delay --> ends later, negative delay --> ends sooner

    parent_start_delay = 0
    parent_end_delay = 0
    if node.parentSpanId in g.nodeHT:
      parent_node = g.nodeHT[node.parentSpanId]
      children = sorted(parent_node.children, key=lambda child: child.startTime)
      parent_start_delay = (
          children[0].startTime - parent_node.startTime if children else 0
      )

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
    original_node_end = node.endTime
    node.startTime = new_start
    node.endTime = new_end
    node.duration = new_end - new_start

    parent_sid = node.parentSpanId
    if parent_sid in g.nodeHT:
      parent_node = g.nodeHT[parent_sid]
    else:
      return

    node_name = graph_utils.get_node_name(node, g)
    siblings = sorted(
        (child for child in parent_node.children if child.sid != node_span_id),
        key=lambda child: child.startTime,
    )

    for sibling in siblings:
      sibling_name = graph_utils.get_node_name(sibling, g)
      sibling_deps = deps.get(sibling_name)
      if (
          sibling_deps
          and node_name in sibling_deps.happens_before
          and sibling.startTime >= original_node_end
      ):
        min_start_time = 0.0
        if sibling_deps.happens_before:
          dep_end_times = []
          sibling_orig_start = graph_utils.get_original_start_time(sibling)
          for other in parent_node.children:
            if other.sid == sibling.sid:
              continue
            if graph_utils.get_original_end_time(other) > sibling_orig_start:
              continue
            other_name = graph_utils.get_node_name(other, g)
            if other_name in sibling_deps.happens_before:
              dep_end_times.append(other.endTime)
          if dep_end_times:
            min_start_time = max(dep_end_times)

        new_start = sibling.startTime + delay
        new_start = max(new_start, min_start_time)
        actual_shift = new_start - sibling.startTime

        sibling.startTime = new_start
        sibling.endTime += actual_shift
        _shift_descendants(sibling, actual_shift)
      else:
        continue

    siblings.append(node)
    first_sibling_after_parent_start = node
    last_sibling_before_parent_end = node

    parent_name = graph_utils.get_node_name(parent_node, g)
    parent_deps = deps.get(parent_name)
    dependent_siblings = [
        child
        for child in siblings
        if (
            parent_deps
            and graph_utils.get_node_name(child, g)
            in parent_deps.child_dependents
        )
        and (
            graph_utils.get_original_end_time(child)
            <= graph_utils.get_original_end_time(parent_node)
        )
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
          and (
              graph_utils.get_original_end_time(sibling)
              <= graph_utils.get_original_end_time(parent_node)
          )
      ):
        last_sibling_before_parent_end = sibling

    if freeze_starts:
      new_parent_start = parent_node.startTime
    elif parent_start_delay > 0:
      new_parent_start = (
          first_sibling_after_parent_start.startTime - parent_start_delay
      )
    else:
      new_parent_start = min(
          parent_node.startTime, first_sibling_after_parent_start.startTime
      )

    if graph_utils.get_original_end_time(
        last_sibling_before_parent_end
    ) > graph_utils.get_original_end_time(parent_node):
      new_parent_end = parent_node.endTime
    else:
      new_parent_end = parent_end_delay + last_sibling_before_parent_end.endTime

    if delay <= 0:
      new_parent_start = min(parent_node.startTime, new_parent_start)
      new_parent_end = min(parent_node.endTime, new_parent_end)

    if new_parent_start > new_parent_end:
      return

    self.retime_node(g, parent_node.sid, new_parent_start, new_parent_end)
    return

  def retime_network_components(
      self,
      graph: crisp_graph.Graph,
      component_names: Sequence[str] | None = None,
      to_value: dict[str, float] | float | None = None,
      span_components_map: (
          Mapping[str | int, Mapping[str, float]] | None
      ) = None,
  ) -> float:
    """Retimes network components in a graph given a dependency graph.

    Args:
      graph: The graph to retime.
      component_names: The names of the components to retime. If None, then
        retime all network components.
      to_value: The target value to retime the network components to. Can be a
        dictionary mapping component names to target values, a single target
        value for all components, or None to retime them to 0.0.
      span_components_map: Mapping from span ID to a mapping of component names
        to values.

    Returns:
      The total amount of time removed from the graph.

    Raises:
      ValueError: If a component name is not a recognized network component.
    """
    root_node = graph.rootNode
    if root_node is None:
      return 0.0

    if component_names is None:
      component_names = DEFAULT_COMPONENT_NAMES

    for component_name in component_names:
      if component_name not in DEFAULT_COMPONENT_NAMES:
        raise ValueError(
            f'Component name {component_name} not a recognized network component.'
        )
    original_duration = root_node.duration

    adjustment_amount = {}

    for span_id, node in graph.nodeHT.items():
      curr_adjustment = 0.0
      components = (
          span_components_map.get(span_id, {}) if span_components_map else {}
      )
      for component_name in component_names:
        if component_name in components:
          if isinstance(to_value, dict):
            target_val = to_value.get(component_name, 0.0)
          elif to_value is not None:
            target_val = to_value
          else:
            target_val = 0.0
          target_val = max(0.0, target_val)
          val = components[component_name]
          curr_adjustment += val - min(val, target_val)
      node_duration = node.duration
      if curr_adjustment > node_duration:
        curr_adjustment = 0.0
      adjustment_amount[span_id] = curr_adjustment

    post_order_nodes = []
    stack = [(root_node, False)]
    while stack:
      curr_node, visited = stack.pop()
      if curr_node is None:
        continue
      if visited:
        post_order_nodes.append(curr_node)
      else:
        stack.append((curr_node, True))
        for child in reversed(list(curr_node.children)):
          if child is not None:
            stack.append((child, False))

    for curr_node in post_order_nodes:
      remaining_duration = curr_node.endTime - curr_node.startTime
      adj = adjustment_amount[curr_node.sid]
      if adj > remaining_duration:
        adj = remaining_duration
      if adj > 0:
        self.retime_node(
            graph,
            curr_node.sid,
            curr_node.startTime,
            curr_node.endTime - adj,
        )

    return original_duration - root_node.duration

  def remove_network_components(
      self,
      graph: crisp_graph.Graph,
      component_names: Sequence[str] | None = None,
      span_components_map: (
          Mapping[str | int, Mapping[str, float]] | None
      ) = None,
  ) -> float:
    """Removes a network component in a graph given a dependency graph.

    Deprecated: Use `retime_network_components` instead.

    Args:
      graph: The graph to retime.
      component_names: The names of the components to remove. If None, then
        remove all network components.
      span_components_map: Mapping from span ID to a mapping of component names
        to values.

    Returns:
      The total amount of time removed from the graph.

    Raises:
      ValueError: If a component name is not a recognized network component.
    """
    return self.retime_network_components(
        graph,
        component_names=component_names,
        to_value=0.0,
        span_components_map=span_components_map,
    )

  def retime_method(
      self,
      graph: crisp_graph.Graph,
      method: str,
      percent_difference: float | None = None,
      fixed_difference: float | None = None,
  ) -> float:
    """Retimes a method in a graph given a dependency graph.

    Args:
      graph: The graph to retime.
      method: The full method name to match (e.g. 'Service.Method').
      percent_difference: Percentage change in duration (e.g. -50.0).
      fixed_difference: Fixed duration change in seconds (e.g. 0.020).

    Returns:
      The total duration reduction in the graph's root node in seconds.
    """
    if percent_difference is not None and fixed_difference is not None:
      raise ValueError(
          'Only one of percent_difference or fixed_difference should be set.'
      )
    if percent_difference is None and fixed_difference is None:
      raise ValueError(
          'One of percent_difference or fixed_difference must be set.'
      )

    root_node = graph.rootNode
    if root_node is None:
      return 0.0

    original_duration = root_node.duration

    for node in graph.nodeHT.values():
      if (node.pid + '.' + node.opName) == method:
        if percent_difference is not None:
          new_end = node.endTime + (node.duration * percent_difference / 100.0)
        else:
          assert fixed_difference is not None
          new_end = node.endTime + fixed_difference
        new_end = max(node.startTime, new_end)
        self.retime_node(
            graph,
            node.sid,
            node.startTime,
            new_end,
        )

    return original_duration - root_node.duration

  def retime_service(
      self,
      graph: crisp_graph.Graph,
      service_name: str,
      percent_difference: float | None = None,
      fixed_difference: float | None = None,
  ) -> float:
    """Retimes all methods of a service in a graph given a dependency graph.

    Args:
      graph: The graph to retime.
      service_name: The service prefix name to match (e.g. 'Service').
      percent_difference: Percentage change in duration (e.g. -50.0).
      fixed_difference: Fixed duration change in seconds (e.g. 0.020).

    Returns:
      The total duration reduction in the graph's root node in seconds.
    """
    if percent_difference is not None and fixed_difference is not None:
      raise ValueError(
          'Only one of percent_difference or fixed_difference should be set.'
      )
    if percent_difference is None and fixed_difference is None:
      raise ValueError(
          'One of percent_difference or fixed_difference must be set.'
      )

    root_node = graph.rootNode
    if root_node is None:
      return 0.0
    original_duration = root_node.duration

    for node in graph.nodeHT.values():
      if node.pid.startswith(service_name):
        if percent_difference is not None:
          new_end = node.endTime + (node.duration * percent_difference / 100.0)
        else:
          assert fixed_difference is not None
          new_end = node.endTime + fixed_difference
        new_end = max(node.startTime, new_end)
        self.retime_node(
            graph,
            node.sid,
            node.startTime,
            new_end,
        )

    return original_duration - root_node.duration
