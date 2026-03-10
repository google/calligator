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

"""Utility functions for working with graphs and their nodes."""

from third_party.CRISP.graph import Graph, GraphNode


def get_graph_depth(node: GraphNode, graph: Graph) -> int:
  """Gets the depth of the graph for a given node.

  Args:
    node: The node to get the depth for.
    graph: The graph we iterate to calculate the depth.

  Returns:
    The depth of the graph for the given node.

  Raises:
    ValueError: If node is None.
  """
  if not node:
    raise ValueError('Node is None.')
  if node.parentSpanId == 0:
    return 1
  # nodeHT is the CRISP graph's dictionary of nodes
  if node.parentSpanId not in graph.nodeHT:
    return 1
  parent_node = graph.nodeHT[node.parentSpanId]
  return 1 + get_graph_depth(parent_node, graph)


def get_node_name(node: GraphNode, graph: Graph) -> str:
  """Gets the name of the node in the graph.

  The name is a combination of the node's method name and its depth in the
  graph.

  Args:
    node: The node to get the name for.
    graph: The graph we iterate to calculate the depth.

  Returns:
    The name of the node in the graph (its method and depth).
  """
  depth = get_graph_depth(node, graph)
  return node.pid + '.' + str(depth)
