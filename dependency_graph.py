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

"""Creates a dependency graph for a given graph.

This ensures that the dependency graph information is in a consistent format
such that it can be used by the retiming class.
"""

import collections
from third_party.CRISP.graph import Graph
import graph_utils


class DependencyGraphNode:
  """Stores information about a node in the dependency graph.

  Attributes:
    name: The name of the node.
    happens_before: The set of nodes that the current node depends on before
      starting. These nodes are siblings of the current node.
    child_dependents: The set of child nodes that the current node depends on
      before finishing. These nodes are children of the current node.
    async_children: The set of child nodes that are asynchronous at least once.
    parent_start_delay: The list of delays that the given span waits before
      dispatching children spans. If the current node is always a child span,
      then this will be an empty list.
    parent_end_delay: The list of delays that the given span waits before ending
      after the last child span ends. If the current node is always a child
      span, then this will be an empty list.
  """

  def __init__(self, name: str):
    """Initializes the DependencyGraphNode object.

    Args:
      name: The name of the node.
    """
    self.name = name
    self.happens_before = set()
    self.child_dependents = set()
    self.async_children = set()
    self.parent_start_delay = []
    self.parent_end_delay = []

  def __repr__(self):
    return (
        f'DependencyGraphNode(name={self.name},'
        f' happens_before={self.happens_before},'
        f' child_dependents={self.child_dependents},'
        f' parent_start_delay={self.parent_start_delay},'
        f' parent_end_delay={self.parent_end_delay})'
    )


class DependencyGraph:
  """Defines the dependency graph for a given graph.

  Attributes:
    deps: A dictionary mapping node name to DependencyGraphNode.
  """

  def __init__(
      self,
      graph: Graph | None = None,
      graphs: list[Graph] | None = None,
  ):
    """Initializes the DependencyGraph object.

    Args:
      graph: The graph to get the dependencies for.
      graphs: The list of graphs to get the dependencies for.

    Raises:
      ValueError: If graph and graphs are both None.
    """
    # check that at least one of graph or graphs is not None
    if graph is None and graphs is None:
      raise ValueError('Graph or graphs must not be None.')

    if graph is not None:
      self.deps = self.get_dependencies(graph)
    else:
      self.deps = self.get_aggregate_dependencies(graphs)

  def __repr__(self):
    return f'DependencyGraph(deps={self.deps})'

  @classmethod
  def get_dependencies(cls, graph: Graph) -> dict[str, DependencyGraphNode]:
    """Gets the dependencies for a single graph.

    Args:
      graph: The graph to get the dependencies for.

    Returns:
      A dictionary mapping node name to DependencyGraphNode.

    Raises:
      ValueError: If graph is None.
    """
    deps = {}

    if graph is None:
      raise ValueError('Graph must not be None.')

    for node in graph.nodeHT.values():
      node_name = graph_utils.get_node_name(node, graph)
      if node_name not in deps:
        deps[node_name] = DependencyGraphNode(node_name)

      # check if this node is an asynchronous span, if it is asynchronous,
      # then add it to the async_children of the parent
      if node.parentSpanId in graph.nodeHT:
        parent_node = graph.nodeHT[node.parentSpanId]
        parent_node_name = graph_utils.get_node_name(parent_node, graph)
        if node.endTime > parent_node.endTime:
          if parent_node_name not in deps:
            deps[parent_node_name] = DependencyGraphNode(parent_node_name)
          deps[parent_node_name].async_children.add(node_name)
          if node_name in deps[parent_node_name].child_dependents:
            deps[parent_node_name].child_dependents.remove(node_name)

      if not node.children:
        continue

      children = list(node.children)
      children = sorted(children, key=lambda child: child.startTime)

      # the delay between the parent's start time and the first child's start
      # time
      parent_start_delay = children[0].startTime - node.startTime

      children = sorted(children, key=lambda child: child.endTime)
      # the delay between the last child's end time and the parent's end time
      parent_end_delay = node.endTime - children[-1].endTime

      deps[node_name].parent_start_delay.append(parent_start_delay)
      deps[node_name].parent_end_delay.append(parent_end_delay)

      children = sorted(children, reverse=True, key=lambda child: child.endTime)

      # go through all children sorted by reversed end time
      for i, child in enumerate(children):
        child_node_name = graph_utils.get_node_name(child, graph)
        # Check if child finishes before its parent ends, if so, add it to the
        # set of child dependents. If the child is already in the async_children
        # of the parent, then do not add it to the child dependents.
        if (
            child.endTime < node.endTime
            and child_node_name not in deps[node_name].async_children
        ):
          deps[node_name].child_dependents.add(child_node_name)

        if child_node_name not in deps:
          # create a node for the child if it does not already exist
          deps[child_node_name] = DependencyGraphNode(child_node_name)

        # Get the happens before relationship for the child by iterating
        # through all children that end before the current child starts.
        # Skip the first child because no node happens before it.
        if i != len(children) - 1:
          for j in range(i + 1, len(children)):
            # make sure that the child finishes before the current child starts
            if children[j].endTime < child.startTime:
              # Add to the happens before set of the current child
              deps[child_node_name].happens_before.add(
                  graph_utils.get_node_name(children[j], graph)
              )

    return deps

  @classmethod
  def get_aggregate_dependencies(
      cls,
      graphs: list[Graph],
  ) -> dict[str, DependencyGraphNode]:
    """Gets aggregated dependencies for a list of graphs.

    With many graphs, aggregate them to get more accurate dependency
    information.
    How do we aggregate multiple dependency relationships?
      - For happens-before relationships, we will pick the minimum
      happens-before relationships so, if one set is {A, B, C} and another is
      {B, C, D}, then we know that the given node only has the happens-before
      relationship consistently for nodes B and C.If a synchronization point
      exists, then this will infer it automatically since it will exclude spans
      that are possibly parallelizable.
      - For parent start/end delay relationships, we will pick the smallest
      value from multiple graphs.
      - We cannot use span IDs since that is unique to each graph, so we will
      need to use the node's pid.opName.

    Args:
      graphs: The graphs of graphs to get the dependencies for.

    Returns:
      A dictionary mapping node name to DependencyGraphNode.
    """
    # use this to keep track of sibling nodes seen for a given node
    sibling_nodes_seen = collections.defaultdict(set)

    aggregate_dependencies = {}
    for graph in graphs:
      dependencies = DependencyGraph.get_dependencies(graph)
      for node_name, dependency in dependencies.items():

        # if we have not seen this node before, we can just add all of its deps
        if node_name not in aggregate_dependencies:
          aggregate_dependencies[node_name] = dependency

          for happens_before_node in dependency.happens_before:
            sibling_nodes_seen[node_name].add(happens_before_node)

          continue

        # else, aggregate!

        # update happens before relationships (one counter example means no
        # happens before relationship)
        updated_hb_set = set()
        for potential_happens_before_node in dependency.happens_before:
          # rule 1
          if (
              potential_happens_before_node
              in aggregate_dependencies[node_name].happens_before
          ):
            updated_hb_set.add(potential_happens_before_node)
          # rule 3
          elif (
              potential_happens_before_node not in sibling_nodes_seen[node_name]
          ):
            updated_hb_set.add(potential_happens_before_node)
            sibling_nodes_seen[node_name].add(potential_happens_before_node)

        for potential_happens_before_node in aggregate_dependencies[
            node_name
        ].happens_before:
          # rule 3
          if potential_happens_before_node not in dependencies:
            updated_hb_set.add(potential_happens_before_node)

        aggregate_dependencies[node_name].happens_before = updated_hb_set

        for potential_child_node in dependency.child_dependents:
          if (
              potential_child_node
              not in aggregate_dependencies[node_name].async_children
          ):
            aggregate_dependencies[node_name].child_dependents.add(
                potential_child_node
            )

        # update async children (one async example means all are async)
        for potential_async_child_node in dependency.async_children:
          aggregate_dependencies[node_name].async_children.add(
              potential_async_child_node
          )
          if (
              potential_async_child_node
              in aggregate_dependencies[node_name].child_dependents
          ):
            aggregate_dependencies[node_name].child_dependents.remove(
                potential_async_child_node
            )

        # append parent start/end delays
        aggregate_dependencies[node_name].parent_start_delay.extend(
            dependency.parent_start_delay
        )
        aggregate_dependencies[node_name].parent_end_delay.extend(
            dependency.parent_end_delay
        )

    return aggregate_dependencies
