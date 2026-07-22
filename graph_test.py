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
import pandas as pd
from third_party.CRISP.graph import Graph
from graph import CrispGraph, GraphCollection
import constants
import pytest

_TEST_CASES_PATH = "test_cases/"

def test_crisp_graph_init_with_dataframe():
    df = pd.DataFrame({
        constants.JAEGER_TRACE_ID: ["t1", "t1", "t1"],
        constants.JAEGER_SPAN_ID: ["s1", "s2", "s3"],
        constants.PARENT_SPAN_ID: [None, "s1", "s2"],
        constants.JAEGER_PROCESS_ID: ["A", "B", "C"],
        constants.JAEGER_OPERATION_NAME: ["opA", "opB", "opC"],
        constants.JAEGER_START_TIME: [0.0, 20.0, 30.0],
        constants.JAEGER_DURATION: [100.0, 60.0, 40.0],
        constants.NUM_DESCENDANTS: [2, 1, 0],
        "extra_metadata_1": [0.1, 2.0, 0.3],
        "extra_metadata_2": ["val1", "val2", "val3"],
    })
    graph = CrispGraph.from_dataframe(df)

    # ValidateNodes
    assert graph.trace_id == "t1"
    assert graph.graph is not None
    assert graph.graph.rootNode.pid == "A"
    assert graph.graph.rootNode.opName == "opA"
    assert graph.graph.rootNode.sid == "s1"
    assert graph.graph.nodeHT["s2"].pid == "B"
    assert graph.graph.nodeHT["s2"].opName == "opB"
    assert graph.graph.nodeHT["s2"].sid == "s2"
    assert graph.graph.nodeHT["s3"].pid == "C"
    assert graph.graph.nodeHT["s3"].opName == "opC"
    assert graph.graph.nodeHT["s3"].sid == "s3"
    assert graph.graph.nodeHT["s2"].parentSpanId == "s1"
    assert graph.graph.nodeHT["s3"].parentSpanId == "s2"

    # ValidateSpanComponents
    assert graph.graph.nodeHT["s1"].span_components["extra_metadata_1"] == 0.1
    assert graph.graph.nodeHT["s1"].span_components["extra_metadata_2"] == "val1"
    assert graph.graph.nodeHT["s2"].span_components["extra_metadata_1"] == 2.0
    assert graph.graph.nodeHT["s2"].span_components["extra_metadata_2"] == "val2"

@pytest.fixture
def graph1():
    with open(_TEST_CASES_PATH + "test_1.json") as f:
        json1 = json.load(f)
    return CrispGraph(Graph(json1, "S1", "one", "file1", False))

@pytest.fixture
def graph2():
    with open(_TEST_CASES_PATH + "test_2.json") as f:
        json2 = json.load(f)
    return CrispGraph(Graph(json2, "S1", "one", "file2", False))

@pytest.fixture
def graph4():
    with open(_TEST_CASES_PATH + "test_4.json") as f:
        json4 = json.load(f)
    return CrispGraph(Graph(json4, "S1", "one", "file4", False))

def test_crisp_graph_init_with_crisp_graph(graph1):
    assert graph1.trace_id == "file1"
    assert graph1.graph is not None
    assert graph1.graph.rootNode.pid == "S1"
    assert graph1.graph.rootNode.opName == "one"
    assert graph1.graph.rootNode.sid == "A"
    assert graph1.graph.nodeHT["B"].pid == "S2"
    assert graph1.graph.nodeHT["B"].opName == "two"
    assert graph1.graph.nodeHT["B"].sid == "B"
    assert graph1.graph.nodeHT["C"].pid == "S3"
    assert graph1.graph.nodeHT["C"].opName == "three"
    assert graph1.graph.nodeHT["C"].sid == "C"
    assert graph1.graph.nodeHT["B"].parentSpanId == "A"
    assert graph1.graph.nodeHT["C"].parentSpanId == "B"

def test_exclusive_graph_durations_g(graph1):
    exclusive_durations = graph1.get_exclusive_durations()
    assert exclusive_durations["A"] == 50
    assert exclusive_durations["B"] == 40
    assert exclusive_durations["C"] == 10

def test_get_exclusive_durations_g4(graph4):
    exclusive_durations = graph4.get_exclusive_durations()
    assert exclusive_durations["A"] == 70
    assert exclusive_durations["B"] == 20
    assert exclusive_durations["C"] == 30
    assert exclusive_durations["D"] == 30

def test_remove_asynchronous_spans(graph4):
    # check that asynchronous span is removed
    assert len(graph4.graph.nodeHT["A"].children) == 1

def test_get_root_method(graph1):
    assert graph1.get_root_method() == "S1"

def test_get_leaf_nodes(graph4):
    leaf_nodes = graph4.get_leaf_nodes()
    assert len(leaf_nodes) == 2
    # Order might not be guaranteed, so check set equality
    leaf_pids = {node.pid for node in leaf_nodes}
    assert leaf_pids == {"S3", "S4"}

def test_get_duration(graph1, graph4):
    assert graph1.get_duration() == 100
    assert graph4.get_duration() == 100

# --- GraphCollection Tests ---

@pytest.fixture
def collection(graph1, graph2):
    graphs_list = [graph1, graph2]
    return GraphCollection(graphs_list=graphs_list)

def test_init_collection(collection, graph1, graph2):
    assert len(collection.graphs) == 2
    assert collection.graphs["file1"].trace_id == "file1"
    assert collection.graphs["file2"].trace_id == "file2"
    assert collection.root_methods == {"S1"}

def test_get_root_methods(collection):
    root_methods = collection.get_root_methods()
    assert root_methods == {"S1"}

def test_get_most_average_drag_by_method(collection):
    most_average_drag_by_method = collection.get_most_average_drag_by_method()
    # S2's average is 35.5, not 35.0: graph2's B node is a chained sibling of
    # A (cp2 = [A, C, B, D]), so its exclusive drag depends on
    # CriticalPath.calculate_drag() correctly resolving B's parent as A (via
    # node.parent) rather than as cp[i - 1] (C, a leaf with no real
    # relationship to B). See critical_path_test.py's
    # test_naive_index_adjacency_parent_would_misreport_chained_sibling_drag
    # for the isolated regression case.
    assert most_average_drag_by_method == [
        ("S1", 53.0),
        ("S2", 35.5),
        ("S3", 12.5),
        ("S4", 4.0),
    ]

def test_get_most_average_slack_by_method(collection):
    most_average_slack_by_method = collection.get_most_average_slack_by_method()
    assert most_average_slack_by_method == [
        ("S1", 0.0),
        ("S2", 0.0),
        ("S3", 0.0),
        ("S4", 0.0),
    ]
