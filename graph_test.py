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

import json
import unittest

import pandas as pd
from parameterized import parameterized

from third_party.CRISP.graph import Graph
from graph import CrispGraph
from graph import GraphCollection
import graph_utils

_TEST_CASES_PATH = "test_cases/"

# g:
# 0 ------------------ A ------------------ 100
#     10 ---------- B ------------- 60
#         20 ---- C ---- 30

# g4:
# 0 ------------------ A ------------------ 100
#                                                 110 ------ B ---- 160
#                                                   120 ---- C -- 150
#                         60 ---- D -- 90


class CrispGraphTest(unittest.TestCase):

  def test_init_with_dataframe(self):
    df = pd.DataFrame({
        "trace_id": [1234567890, 1234567890, 1234567890],
        "span_id": [1, 2, 3],
        "parent_rpc_span_id": [0, 1, 2],
        "method_name": ["A.foo", "B.bar", "C.baz"],
        "server_job": ["A", "B", "C"],
        "client_start_timestamp": [0.0, 20.0, 30.0],
        "client_finish_timestamp": [100.0, 60.0, 40.0],
        "server_start_timestamp": [1.2, 2.2, 3.2],
        "server_finish_timestamp": [1.3, 2.3, 3.3],
        "is_true_root": [True, False, False],
        "client_send_queue_delta": [0.1, 2.0, 0.3],
        "request_network_delta": [2.0, 0.2, 0.3],
        "server_recv_queue_delta": [7, 50, 3],
        "server_app_delta": [90, 0.2, 2.5],
        "server_send_queue_delta": [0.1, 0.2, 0.3],
        "response_network_delta": [0.1, 0.2, 0.3],
        "client_recv_queue_delta": [0.1, 0.2, 0.3],
        "num_descendants": [2, 1, 0],
    })
    graph = CrispGraph.from_dataframe(df)
    with self.subTest("ValidateNodes"):
      self.assertEqual(graph.trace_id, 1234567890)
      self.assertIsNotNone(graph.graph)
      self.assertEqual(graph.graph.rootNode.pid, "A")
      self.assertEqual(graph.graph.rootNode.opName, "foo")
      self.assertEqual(graph.graph.rootNode.sid, 1)
      self.assertEqual(graph.graph.nodeHT[2].pid, "B")
      self.assertEqual(graph.graph.nodeHT[2].opName, "bar")
      self.assertEqual(graph.graph.nodeHT[2].sid, 2)
      self.assertEqual(graph.graph.nodeHT[3].pid, "C")
      self.assertEqual(graph.graph.nodeHT[3].opName, "baz")
      self.assertEqual(graph.graph.nodeHT[3].sid, 3)
      self.assertEqual(graph.graph.nodeHT[2].parentSpanId, 1)
      self.assertEqual(graph.graph.nodeHT[3].parentSpanId, 2)
    with self.subTest("ValidateSpanComponents"):
      span_components_1 = graph.get_span_components(1)
      self.assertEqual(span_components_1["client_send_queue_delta"], 0.1)
      self.assertEqual(span_components_1["request_network_delta"], 2.0)
      self.assertEqual(span_components_1["server_recv_queue_delta"], 7.0)
      self.assertEqual(span_components_1["server_app_delta"], 90)
      self.assertEqual(span_components_1["server_send_queue_delta"], 0.1)
      self.assertEqual(span_components_1["response_network_delta"], 0.1)
      self.assertEqual(span_components_1["client_recv_queue_delta"], 0.1)
    with self.subTest("ValidateGraphUtilsAccessors"):
      node1 = graph.graph.nodeHT[1]
      self.assertEqual(graph_utils.get_original_start_time(node1), 1.2)
      self.assertEqual(graph_utils.get_original_end_time(node1), 101.2)
      self.assertEqual(
          graph.get_span_components(1)["request_network_delta"], 2.0
      )
      self.assertEqual(graph.get_num_descendants(1), 2)

  @parameterized.expand([
      (
          "multiple_dots",
          [
              "com.example.service.root_op",
              "com.example.service.sub.child_op",
          ],
          ["com.example.service", "com.example.service.sub"],
          ("com.example.service", "root_op"),
          ("com.example.service.sub", "child_op"),
      ),
      (
          "no_dot_uses_server_job",
          ["foo", "bar"],
          ["service_root", "service_child"],
          ("service_root", "foo"),
          ("service_child", "bar"),
      ),
  ])
  def test_init_with_dataframe_method_name_parsing(
      self,
      name: str,
      method_names: list[str],
      server_jobs: list[str],
      expected_root: tuple[str, str],
      expected_child: tuple[str, str],
  ):
    df = pd.DataFrame({
        "trace_id": [12345, 12345],
        "span_id": [1, 2],
        "parent_rpc_span_id": [0, 1],
        "method_name": method_names,
        "server_job": server_jobs,
        "client_start_timestamp": [0.0, 20.0],
        "client_finish_timestamp": [100.0, 60.0],
        "server_start_timestamp": [1.0, 2.0],
        "server_finish_timestamp": [1.0, 2.0],
        "is_true_root": [True, False],
        "client_send_queue_delta": [0.0, 0.0],
        "request_network_delta": [0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0],
        "server_app_delta": [100.0, 40.0],
        "server_send_queue_delta": [0.0, 0.0],
        "response_network_delta": [0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0],
        "num_descendants": [1, 0],
    })
    graph = CrispGraph.from_dataframe(df)
    self.assertIsNotNone(graph.graph)
    self.assertIsNotNone(graph.graph.rootNode)
    self.assertEqual(graph.graph.rootNode.pid, expected_root[0])
    self.assertEqual(graph.graph.rootNode.opName, expected_root[1])
    self.assertEqual(graph.graph.nodeHT[2].pid, expected_child[0])
    self.assertEqual(graph.graph.nodeHT[2].opName, expected_child[1])

  def test_init_with_crisp_graph(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    self.assertEqual(graph.trace_id, "file1")
    self.assertIsNotNone(graph.graph)
    self.assertEqual(graph.graph.rootNode.pid, "S1")
    self.assertEqual(graph.graph.rootNode.opName, "one")
    self.assertEqual(graph.graph.rootNode.sid, "A")
    self.assertEqual(graph.graph.nodeHT["B"].pid, "S2")
    self.assertEqual(graph.graph.nodeHT["B"].opName, "two")
    self.assertEqual(graph.graph.nodeHT["B"].sid, "B")
    self.assertEqual(graph.graph.nodeHT["C"].pid, "S3")
    self.assertEqual(graph.graph.nodeHT["C"].opName, "three")
    self.assertEqual(graph.graph.nodeHT["C"].sid, "C")
    self.assertEqual(graph.graph.nodeHT["B"].parentSpanId, "A")
    self.assertEqual(graph.graph.nodeHT["C"].parentSpanId, "B")

  def test_exclusive_graph_durations_g(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    exclusive_durations = graph.get_exclusive_durations()
    self.assertEqual(exclusive_durations["A"], 50)
    self.assertEqual(exclusive_durations["B"], 40)
    self.assertEqual(exclusive_durations["C"], 10)

  def test_get_exclusive_durations_g4(self):
    with open(_TEST_CASES_PATH + "test_4.json") as f:
      json4 = json.load(f)
    graph4 = CrispGraph(Graph(json4, "S1", "one", "file4", False))
    exclusive_durations = graph4.get_exclusive_durations()
    self.assertEqual(exclusive_durations["A"], 70)
    self.assertEqual(exclusive_durations["B"], 20)
    self.assertEqual(exclusive_durations["C"], 30)
    self.assertEqual(exclusive_durations["D"], 30)

  def test_remove_asynchronous_spans(self):
    with open(_TEST_CASES_PATH + "test_4.json") as f:
      json4 = json.load(f)
    graph4 = CrispGraph(Graph(json4, "S1", "one", "file4", False))
    self.assertEqual(len(graph4.graph.nodeHT["A"].children), 1)

  def test_get_root_method(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    self.assertEqual(graph.get_root_method(), "S1")

  def test_get_leaf_nodes(self):
    with open(_TEST_CASES_PATH + "test_4.json") as f:
      json4 = json.load(f)
    graph4 = CrispGraph(Graph(json4, "S1", "one", "file4", False))
    leaf_nodes = graph4.get_leaf_nodes()
    self.assertEqual(len(leaf_nodes), 2)
    self.assertEqual(leaf_nodes[0].pid, "S3")
    self.assertEqual(leaf_nodes[1].pid, "S4")

  def test_get_duration(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    with open(_TEST_CASES_PATH + "test_4.json") as f:
      json4 = json.load(f)
    graph4 = CrispGraph(Graph(json4, "S1", "one", "file4", False))
    self.assertEqual(graph.get_duration(), 100)
    self.assertEqual(graph4.get_duration(), 100)

  def test_is_retimed_and_restore_timestamps(self):
    df = pd.DataFrame({
        "trace_id": [1],
        "span_id": ["A"],
        "parent_rpc_span_id": [0],
        "method_name": ["S.foo"],
        "server_job": ["S"],
        "client_start_timestamp": [10.0],
        "client_finish_timestamp": [50.0],
        "server_start_timestamp": [10.0],
        "server_finish_timestamp": [50.0],
        "is_true_root": [True],
        "client_send_queue_delta": [0.0],
        "request_network_delta": [0.0],
        "server_recv_queue_delta": [0.0],
        "server_app_delta": [40.0],
        "server_send_queue_delta": [0.0],
        "response_network_delta": [0.0],
        "client_recv_queue_delta": [0.0],
        "num_descendants": [0],
    })
    cg = CrispGraph.from_dataframe(df)
    self.assertFalse(cg.is_retimed())

    node = cg.graph.nodeHT["A"]
    node.startTime = 20.0
    self.assertTrue(cg.is_retimed())

    cg.restore_to_original_timestamps()
    self.assertFalse(cg.is_retimed())
    self.assertEqual(node.startTime, 10.0)
    self.assertEqual(node.endTime, 50.0)
    self.assertEqual(node.duration, 40.0)

    cg._retimed = True
    self.assertTrue(cg.is_retimed())
    cg.restore_to_original_timestamps()
    self.assertFalse(cg.is_retimed())


class GraphCollectionTest(unittest.TestCase):

  def test_init_collection(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    with open(_TEST_CASES_PATH + "test_2.json") as f:
      json2 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    graph2 = CrispGraph(Graph(json2, "S1", "one", "file2", False))
    graphs_list = [graph, graph2]
    collection = GraphCollection(graphs_list=graphs_list)
    self.assertEqual(len(collection.graphs), 2)
    self.assertEqual(collection.graphs["file1"].trace_id, "file1")
    self.assertEqual(collection.graphs["file2"].trace_id, "file2")
    self.assertEqual(collection.root_methods, {"S1"})

  def test_get_root_methods(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    with open(_TEST_CASES_PATH + "test_2.json") as f:
      json2 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    graph2 = CrispGraph(Graph(json2, "S1", "one", "file2", False))
    graphs_list = [graph, graph2]
    collection = GraphCollection(graphs_list=graphs_list)
    root_methods = collection.get_root_methods()
    self.assertEqual(root_methods, {"S1"})

  def test_get_nodes_by_method(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    nodes = graph.get_nodes_by_method("S2")
    self.assertEqual(len(nodes), 1)
    self.assertEqual(nodes[0].sid, "B")

    # Test canonical op name matching
    nodes_canonical = graph.get_nodes_by_method("[S2] two")
    self.assertEqual(len(nodes_canonical), 1)
    self.assertEqual(nodes_canonical[0].sid, "B")

    # Test Service.Method matching and get_graphs_subset root_method_name
    nodes_dotted = graph.get_nodes_by_method("S2.two")
    self.assertEqual(len(nodes_dotted), 1)
    self.assertEqual(nodes_dotted[0].sid, "B")

    collection = GraphCollection(graphs_list=[graph])
    self.assertEqual(
        len(collection.get_graphs_subset(root_method_name="S1.one")), 1
    )
    self.assertEqual(
        len(collection.get_graphs_subset(root_method_name="S1.other")), 0
    )

  def test_get_most_average_drag_by_method(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    with open(_TEST_CASES_PATH + "test_2.json") as f:
      json2 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    graph2 = CrispGraph(Graph(json2, "S1", "one", "file2", False))
    graphs_list = [graph, graph2]
    collection = GraphCollection(graphs_list=graphs_list)
    most_average_drag_by_method = collection.get_most_average_drag_by_method()
    self.assertEqual(
        most_average_drag_by_method,
        [("S1", 53.0), ("S2", 35.0), ("S3", 10.0), ("S4", 4.0)],
    )

  def test_get_most_average_drag_by_method_with_start_method(self):
    with open(_TEST_CASES_PATH + "test_6.json") as f:
      json6 = json.load(f)
    graph6 = CrispGraph(Graph(json6, "S1", "one", "file6", False))
    collection = GraphCollection(graphs_list=[graph6])
    drag_s2 = collection.get_most_average_drag_by_method(start_method_name="S2")
    self.assertEqual(dict(drag_s2)["S2"], 25.0)
    self.assertEqual(dict(drag_s2)["S3"], 10.0)

  def test_get_most_average_slack_by_method(self):
    with open(_TEST_CASES_PATH + "test_1.json") as f:
      json1 = json.load(f)
    with open(_TEST_CASES_PATH + "test_2.json") as f:
      json2 = json.load(f)
    graph = CrispGraph(Graph(json1, "S1", "one", "file1", False))
    graph2 = CrispGraph(Graph(json2, "S1", "one", "file2", False))
    graphs_list = [graph, graph2]
    collection = GraphCollection(graphs_list=graphs_list)
    most_average_slack_by_method = collection.get_most_average_slack_by_method()
    self.assertEqual(
        most_average_slack_by_method,
        [("S1", 0.0), ("S2", 0.0), ("S3", 0.0), ("S4", 0.0)],
    )

  def test_get_most_average_slack_by_method_with_start_method(self):
    with open(_TEST_CASES_PATH + "test_6.json") as f:
      json6 = json.load(f)
    graph6 = CrispGraph(Graph(json6, "S1", "one", "file6", False))
    collection = GraphCollection(graphs_list=[graph6])
    slack_s2 = collection.get_most_average_slack_by_method(
        start_method_name="S2"
    )
    self.assertNotIn("S1", dict(slack_s2))
    self.assertEqual(dict(slack_s2)["S2"], 0.0)
    self.assertEqual(dict(slack_s2)["S3"], 0.0)

  def _create_graph_with_duration(self, trace_id, duration):
    df = pd.DataFrame({
        "trace_id": [trace_id],
        "span_id": [1],
        "parent_rpc_span_id": [0],
        "method_name": ["A.foo"],
        "server_job": ["A"],
        "client_start_timestamp": [0.0],
        "client_finish_timestamp": [float(duration)],
        "server_start_timestamp": [0.0],
        "server_finish_timestamp": [float(duration)],
        "is_true_root": [True],
        "client_send_queue_delta": [0.0],
        "request_network_delta": [0.0],
        "server_recv_queue_delta": [0.0],
        "server_app_delta": [float(duration)],
        "server_send_queue_delta": [0.0],
        "response_network_delta": [0.0],
        "client_recv_queue_delta": [0.0],
        "num_descendants": [0],
    })
    return CrispGraph.from_dataframe(df)

  def test_get_graphs_subset_percentile_boundaries(self):
    graphs = [self._create_graph_with_duration(i, i * 10) for i in range(1, 11)]
    collection = GraphCollection(graphs_list=graphs)

    subset_90 = collection.get_graphs_subset(
        percentile_start=0, percentile_end=90
    )
    self.assertEqual(len(subset_90), 9)
    subset_durations = sorted([g.get_duration() for g in subset_90])
    self.assertEqual(
        subset_durations, [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    )

    subset_10_90 = collection.get_graphs_subset(
        percentile_start=10, percentile_end=90
    )
    self.assertEqual(len(subset_10_90), 8)
    subset_durations_10_90 = sorted([g.get_duration() for g in subset_10_90])
    self.assertEqual(
        subset_durations_10_90, [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    )

  def test_get_graphs_subset_duplicate_durations(self):
    durations = [10.0, 10.0, 10.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    graphs = [
        self._create_graph_with_duration(i, d) for i, d in enumerate(durations)
    ]
    collection = GraphCollection(graphs_list=graphs)

    subset = collection.get_graphs_subset(
        percentile_start=10.0, percentile_end=90.0
    )
    self.assertEqual(len(subset), 8)
    subset_durations = sorted([g.get_duration() for g in subset])
    self.assertEqual(
        subset_durations, [10.0, 10.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    )


if __name__ == "__main__":
  unittest.main()
