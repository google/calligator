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
import pytest
from third_party.CRISP.graph import Graph
from graph import CrispGraph

_TEST_CASES_PATH = "test_cases/"

@pytest.fixture(scope="module")
def graph1():
    with open(_TEST_CASES_PATH + "test_1.json") as f:
        j = json.load(f)
    return CrispGraph(Graph(j, "S1", "one", "file1", False))

@pytest.fixture(scope="module")
def graph2():
    with open(_TEST_CASES_PATH + "test_2.json") as f:
        j2 = json.load(f)
    return CrispGraph(Graph(j2, "S1", "one", "file2", False))

@pytest.fixture(scope="module")
def graph3():
    with open(_TEST_CASES_PATH + "test_3.json") as f:
        j3 = json.load(f)
    return CrispGraph(Graph(j3, "S1", "one", "file3", False))

@pytest.fixture(scope="module")
def graph4():
    with open(_TEST_CASES_PATH + "test_4.json") as f:
        j4 = json.load(f)
    return CrispGraph(Graph(j4, "S1", "one", "file4", False))

@pytest.fixture(scope="module")
def graph5():
    with open(_TEST_CASES_PATH + "test_5.json") as f:
        j5 = json.load(f)
    return CrispGraph(Graph(j5, "S1", "one", "file5", False))

@pytest.fixture(scope="module")
def graph6():
    with open(_TEST_CASES_PATH + "test_6.json") as f:
        j6 = json.load(f)
    return CrispGraph(Graph(j6, "S1", "one", "file6", False))

# g:
# 0 ------------------ A ------------------ 100
#     10 ---------- B ------------- 60
#         20 ---- C ---- 30

# g2:
# 0 ------------------ A ------------------ 100
#   5 - D - 9 10 --- B -- 40 45 -- C - 55

# g3:
# 0 ------------------ A ------------------ 100
#   10 - C -- 20 --- B -- 50

# g4:
# 0 ------------------ A ------------------ 100
#                                                 110 ------ B ---- 160
#                                                   120 ---- C -- 150
#                         60 ---- D -- 90

# g5:
# 0 ------------------ A ------------------ 100
#    10 -------- B ----------60
#               45 -- C -- 55
#   5 - D - 15

def test_critical_path_g(graph1):
    cp = graph1.get_critical_path()
    vals = ["A", "B", "C"]
    assert [node.sid for node in cp.cp] == vals

def test_critical_path_g2(graph2):
    cp = graph2.get_critical_path()
    vals = ["A", "C", "B", "D"]
    assert [node.sid for node in cp.cp] == vals

def test_critical_path_g3(graph3):
    cp = graph3.get_critical_path()
    vals = ["A", "B", "C"]
    assert [node.sid for node in cp.cp] == vals

def test_critical_path_g4(graph4):
    """Tests critical path computation for a graph with asynchronous spans."""
    cp = graph4.get_critical_path()
    vals = ["A", "D"]
    assert [node.sid for node in cp.cp] == vals

def test_critical_path_g5(graph5):
    """Tests critical path computation for a graph with asynchronous spans."""
    cp = graph5.get_critical_path()
    vals = ["A", "B"]
    assert [node.sid for node in cp.cp] == vals

def test_slack_on_cp_g(graph1):
    cp = graph1.get_critical_path()
    slack = cp.calculate_slack()
    assert slack.slack_per_span["A"] == 0
    assert slack.slack_per_span["B"] == 0
    assert slack.slack_per_span["C"] == 0
    assert slack.total_slack == 0

def test_slack_off_cp_g5(graph5):
    """Tests slack computation for a graph with some spans not on the critical path."""
    cp = graph5.get_critical_path()
    slack = cp.calculate_slack()
    assert slack.slack_per_span["A"] == 0
    assert slack.slack_per_span["B"] == 0
    assert slack.slack_per_span["C"] == 35
    assert slack.slack_per_span["D"] == 35

def test_drag_g(graph1):
    """Tests drag computation for a graph with all spans on the critical path."""
    cp = graph1.get_critical_path()
    drag = cp.calculate_drag()
    assert drag.drag_per_span["A"] == 100
    assert drag.drag_per_span["B"] == 50
    assert drag.drag_per_span["C"] == 10
    assert drag.total_drag == 160

def test_exclusive_drag_g(graph1):
    """Tests exclusive drag computation for a graph with all spans on the critical path."""
    cp = graph1.get_critical_path()
    exclusive_drag = cp.calculate_drag(exclusive=True)
    assert exclusive_drag.drag_per_span["A"] == 50
    assert exclusive_drag.drag_per_span["B"] == 40
    assert exclusive_drag.drag_per_span["C"] == 10
    assert exclusive_drag.total_drag == 100

def test_exclusive_drag_g4(graph4):
    """Tests exclusive drag computation for a graph with asynchronous spans."""
    cp = graph4.get_critical_path()
    exclusive_drag = cp.calculate_drag(exclusive=True)
    assert exclusive_drag.drag_per_span["A"] == 70
    assert exclusive_drag.drag_per_span["D"] == 30
    assert exclusive_drag.total_drag == 100

def test_contribution_to_cp_g(graph1):
    """Tests contribution to critical path computation for a graph."""
    cp = graph1.get_critical_path()
    cp_contribution_percents = cp.get_contribution_by_method(percent=True)
    cp_contribution = cp.get_contribution_by_method(percent=False)
    assert cp_contribution["[S1] one"] == 50
    assert cp_contribution_percents["[S1] one"] == 50
    assert cp_contribution["[S2] two"] == 40
    assert cp_contribution_percents["[S2] two"] == 40
    assert cp_contribution["[S3] three"] == 10
    assert cp_contribution_percents["[S3] three"] == 10


def test_parent_lookup_and_drag_bounding():
    import pandas as pd
    df = pd.DataFrame({
        "trace_id": ["b1_bug"] * 3,
        "span_id": ["A", "B", "C"],
        "parent_rpc_span_id": ["0", "A", "A"],
        "method_name": ["m1", "m2", "m3"],
        "server_job": ["j1", "j2", "j3"],
        "client_start_timestamp": [0.0, 10.0, 50.0],
        "client_finish_timestamp": [100.0, 40.0, 60.0],
        "server_start_timestamp": [0.0, 10.0, 50.0],
        "server_finish_timestamp": [100.0, 40.0, 60.0],
        "is_true_root": [True, False, False],
        "client_send_queue_delta": [0.0, 0.0, 0.0],
        "request_network_delta": [0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0],
        "server_app_delta": [100.0, 30.0, 10.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0],
        "num_descendants": [2, 0, 0],
    })
    graph_obj = CrispGraph.from_dataframe(df)
    cp = graph_obj.get_critical_path()

    # Assert parent lookup resolves A (not C) for child B.
    node_b = graph_obj.get_node_from_span_id("B")
    assert node_b is not None
    assert node_b.parent.sid == "A"

    # Verify critical path
    assert [n.sid for n in cp.cp] == ["A", "C", "B"]

    # Calculate drag
    drag = cp.calculate_drag(exclusive=False)

    # Assert B's drag is capped to 30, and C's drag is capped to 10
    assert drag.drag_per_span.get("B", 0.0) == 30.0
    assert drag.drag_per_span.get("C", 0.0) == 10.0


def test_complex_sibling_slack_propagation():
    from dependency_graph import DependencyGraph
    test_json = {
        "data": [{
            "processes": {
                "S1": {"serviceName": "S1"},
                "S2": {"serviceName": "S2"},
                "S3": {"serviceName": "S3"},
                "S4": {"serviceName": "S4"},
                "S5": {"serviceName": "S5"},
                "S6": {"serviceName": "S6"},
                "S7": {"serviceName": "S7"},
            },
            "traceID": "trace_complex_slack",
            "spans": [
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "A",
                    "operationName": "one",
                    "startTime": 0,
                    "duration": 200,
                    "processID": "S1",
                    "references": [],
                },
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "CP_CHILD",
                    "operationName": "seven",
                    "startTime": 10,
                    "duration": 180,
                    "processID": "S7",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_complex_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "B",
                    "operationName": "two",
                    "startTime": 10,
                    "duration": 20,
                    "processID": "S2",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_complex_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "C",
                    "operationName": "three",
                    "startTime": 40,
                    "duration": 20,
                    "processID": "S3",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_complex_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "D",
                    "operationName": "four",
                    "startTime": 70,
                    "duration": 20,
                    "processID": "S4",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_complex_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "E",
                    "operationName": "five",
                    "startTime": 100,
                    "duration": 20,
                    "processID": "S5",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_complex_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_complex_slack",
                    "spanID": "F",
                    "operationName": "six",
                    "startTime": 130,
                    "duration": 20,
                    "processID": "S6",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_complex_slack",
                        "spanID": "A",
                    }],
                },
            ],
        }]
    }
    graph_obj = CrispGraph(
        Graph(test_json, "S1", "one", "test_complex_slack", False)
    )
    dep_graph = DependencyGraph(graph_obj.graph)
    dep_graph.deps["S3.2"].happens_before.add("S2.2")
    dep_graph.deps["S4.2"].happens_before.add("S3.2")
    dep_graph.deps["S5.2"].happens_before.add("S4.2")
    dep_graph.deps["S6.2"].happens_before.add("S5.2")

    cp = graph_obj.get_critical_path()
    slack_obj = cp.calculate_slack(dep_graph)

    assert slack_obj.slack_per_span.get("B", 0.0) == 80.0
    assert slack_obj.slack_per_span.get("C", 0.0) == 80.0
    assert slack_obj.slack_per_span.get("D", 0.0) == 70.0
    assert slack_obj.slack_per_span.get("E", 0.0) == 60.0
    assert slack_obj.slack_per_span.get("F", 0.0) == 50.0


def test_get_slack_and_drag_per_method(graph1):
    cp = graph1.get_critical_path()
    slack_per_method = cp.get_slack_per_method()
    assert "S1.one" in slack_per_method
    assert slack_per_method["S1.one"] == [0.0]

    drag_per_method = cp.get_drag_per_method(exclusive=False)
    assert "S1.one" in drag_per_method
    assert drag_per_method["S1.one"] == [100.0]

    exclusive_drag_per_method = cp.get_drag_per_method(exclusive=True)
    assert "S1.one" in exclusive_drag_per_method
    assert exclusive_drag_per_method["S1.one"] == [50.0]


def test_sibling_drag_walk_parent_fix():
    # A (0-100)
    #   B (10-60)
    #   C (40-90)
    test_json = {
        "data": [{
            "processes": {
                "S1": {"serviceName": "S1"},
                "S2": {"serviceName": "S2"},
                "S3": {"serviceName": "S3"},
            },
            "traceID": "trace_sibling",
            "spans": [
                {
                    "traceID": "trace_sibling",
                    "spanID": "A",
                    "operationName": "one",
                    "startTime": 0,
                    "duration": 100,
                    "processID": "S1",
                    "references": [],
                },
                {
                    "traceID": "trace_sibling",
                    "spanID": "B",
                    "operationName": "two",
                    "startTime": 10,
                    "duration": 50,
                    "processID": "S2",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_sibling",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_sibling",
                    "spanID": "C",
                    "operationName": "three",
                    "startTime": 40,
                    "duration": 50,
                    "processID": "S3",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_sibling",
                        "spanID": "A",
                    }],
                },
            ],
        }]
    }
    graph_obj = CrispGraph(Graph(test_json, "S1", "one", "test_sibling", False))
    cp = graph_obj.get_critical_path()

    # Calculate exclusive drag
    ex_drag = cp.calculate_drag(exclusive=True)
    # B ends at 60, next sibling C ends at 90. Drag val = 60 - 90 = -30, clamped to 0.0.
    assert ex_drag.drag_per_span.get("B", 0.0) == 0.0

    # Calculate inclusive drag
    inc_drag = cp.calculate_drag(exclusive=False)
    assert inc_drag.drag_per_span.get("B", 0.0) == 0.0


def test_sibling_slack_propagation():
    from dependency_graph import DependencyGraph
    test_json = {
        "data": [{
            "processes": {
                "S1": {"serviceName": "S1"},
                "S2": {"serviceName": "S2"},
                "S3": {"serviceName": "S3"},
                "S4": {"serviceName": "S4"},
            },
            "traceID": "trace_slack",
            "spans": [
                {
                    "traceID": "trace_slack",
                    "spanID": "A",
                    "operationName": "one",
                    "startTime": 0,
                    "duration": 100,
                    "processID": "S1",
                    "references": [],
                },
                {
                    "traceID": "trace_slack",
                    "spanID": "D",
                    "operationName": "four",
                    "startTime": 10,
                    "duration": 80,
                    "processID": "S4",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_slack",
                    "spanID": "B",
                    "operationName": "two",
                    "startTime": 10,
                    "duration": 20,
                    "processID": "S2",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_slack",
                    "spanID": "C",
                    "operationName": "three",
                    "startTime": 40,
                    "duration": 20,
                    "processID": "S3",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_slack",
                        "spanID": "A",
                    }],
                },
            ],
        }]
    }
    graph_obj = CrispGraph(Graph(test_json, "S1", "one", "test_slack", False))

    dep_graph = DependencyGraph(graph_obj.graph)
    dep_graph.deps["S3.2"].happens_before.add("S2.2")

    cp = graph_obj.get_critical_path()
    slack_obj = cp.calculate_slack(dep_graph)
    assert slack_obj.slack_per_span.get("B", 0.0) == 40.0


def test_sequential_siblings_drag():
    import pandas as pd
    df = pd.DataFrame({
        "trace_id": ["seq_siblings"] * 4,
        "span_id": ["A", "B", "C", "D"],
        "parent_rpc_span_id": ["0", "A", "A", "B"],
        "method_name": ["m1", "m2", "m3", "m4"],
        "server_job": ["j1", "j2", "j3", "j4"],
        "client_start_timestamp": [0.0, 10.0, 50.0, 20.0],
        "client_finish_timestamp": [100.0, 50.0, 90.0, 40.0],
        "server_start_timestamp": [0.0, 10.0, 50.0, 20.0],
        "server_finish_timestamp": [100.0, 50.0, 90.0, 40.0],
        "is_true_root": [True, False, False, False],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_app_delta": [100.0, 40.0, 40.0, 20.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "num_descendants": [3, 1, 0, 0],
    })
    graph_obj = CrispGraph.from_dataframe(df)
    cp = graph_obj.get_critical_path()

    assert "C" in [n.sid for n in cp.cp]

    drag = cp.calculate_drag(exclusive=False)
    assert drag.drag_per_span["C"] == 40.0


def test_critical_path_for_node(graph1, graph2):
    cp = graph1.get_critical_path_for_node("B")
    vals = ["B", "C"]
    assert [node.sid for node in cp.cp] == vals

    node_b = graph1.get_node_from_span_id("B")
    assert node_b is not None
    cp_from_node = graph1.get_critical_path_for_node(node_b)
    assert [node.sid for node in cp_from_node.cp] == vals

    node_from_g2 = graph2.get_node_from_span_id("B")
    assert node_from_g2 is not None
    with pytest.raises(ValueError):
        graph1.get_critical_path_for_node(node_from_g2)

    cp_contribution_percents = cp.get_contribution_by_method(percent=True)
    assert cp_contribution_percents["[S2] two"] == 80.0
    assert cp_contribution_percents["[S3] three"] == 20.0
    assert "[S1] one" not in cp_contribution_percents


def test_slack_for_node(graph6):
    """Tests slack computation starting from a specific node."""
    cp = graph6.get_critical_path_for_node("B")
    slack = cp.calculate_slack()
    assert "A" not in slack.slack_per_span
    assert "B2" not in slack.slack_per_span
    assert "B" in slack.slack_per_span
    assert "C" in slack.slack_per_span
    assert slack.slack_per_span["B"] == 0
    assert slack.slack_per_span["C"] == 0


def test_drag_for_node(graph6):
    """Tests drag computation starting from a specific node."""
    cp = graph6.get_critical_path_for_node("B")
    drag = cp.calculate_drag(exclusive=True)
    assert "A" not in drag.drag_per_span
    assert "B2" not in drag.drag_per_span
    assert "B" in drag.drag_per_span
    assert drag.drag_per_span["B"] == 40


def test_slack_for_node_with_sibling_dependencies():
    """Tests slack computation for subtrees where siblings have dependencies."""
    from dependency_graph import DependencyGraph
    test_json = {
        "data": [{
            "processes": {
                "S1": {"serviceName": "S1"},
                "S2": {"serviceName": "S2"},
                "S3": {"serviceName": "S3"},
            },
            "traceID": "trace_subgraph_slack",
            "spans": [
                {
                    "traceID": "trace_subgraph_slack",
                    "spanID": "A",
                    "operationName": "one",
                    "startTime": 0,
                    "duration": 100,
                    "processID": "S1",
                    "references": [],
                },
                {
                    "traceID": "trace_subgraph_slack",
                    "spanID": "B",
                    "operationName": "two",
                    "startTime": 10,
                    "duration": 30,
                    "processID": "S2",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_subgraph_slack",
                        "spanID": "A",
                    }],
                },
                {
                    "traceID": "trace_subgraph_slack",
                    "spanID": "C",
                    "operationName": "three",
                    "startTime": 50,
                    "duration": 30,
                    "processID": "S3",
                    "references": [{
                        "refType": "CHILD_OF",
                        "traceID": "trace_subgraph_slack",
                        "spanID": "A",
                    }],
                },
            ],
        }]
    }
    graph_obj = CrispGraph(
        Graph(test_json, "S1", "one", "test_subgraph_slack", False)
    )
    dep_graph = DependencyGraph(graph_obj.graph)
    dep_graph.deps["S3.2"].happens_before.add("S2.2")

    cp = graph_obj.get_critical_path_for_node("B")
    slack_obj = cp.calculate_slack(dep_graph)
    assert "B" in slack_obj.slack_per_span
    assert "A" not in slack_obj.slack_per_span
    assert "C" not in slack_obj.slack_per_span


def test_sibling_drag_walk_parent_lookup_and_capping():
    test_parent_lookup_and_drag_bounding()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
