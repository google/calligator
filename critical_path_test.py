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
    assert slack.slack_per_span["D"] == 45

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

def _span(span_id, op, pid, start, duration, parent_id=None):
    references = (
        []
        if parent_id is None
        else [{"refType": "CHILD_OF", "traceID": "T", "spanID": parent_id}]
    )
    return {
        "traceID": "T",
        "spanID": span_id,
        "operationName": op,
        "startTime": start,
        "duration": duration,
        "processID": pid,
        "references": references,
    }

@pytest.fixture
def sequential_siblings_with_slight_overlap_graph():
    # R (0-1000) has three sequential, non-overlapping children: A (0-200),
    # B (195-400, a hair earlier than A's end, within the 1% overlap
    # allowance), and C (500-1000). computeCriticalPath always recurses into
    # the highest-endTime child first, so it flattens this onto the cp list
    # as [R, C, B, A] -- C (the first child appended) ends up directly after
    # R, but B (a later chained sibling) does not.
    spans = [
        _span("R", "OR", "S1", 0, 1000),
        _span("A", "OA", "S2", 0, 200, parent_id="R"),
        _span("B", "OB", "S2", 195, 205, parent_id="R"),
        _span("C", "OC", "S2", 500, 500, parent_id="R"),
    ]
    data = {
        "data": [{
            "processes": {
                "S1": {"serviceName": "S1", "tags": []},
                "S2": {"serviceName": "S2", "tags": []},
            },
            "traceID": "T",
            "spans": spans,
        }]
    }
    graph = Graph(data, "S1", "OR", "regression_file", False)
    return CrispGraph(graph)

def test_naive_index_adjacency_parent_would_misreport_chained_sibling_drag(
    sequential_siblings_with_slight_overlap_graph,
):
    """Regression test: calculate_drag must key off node.parent, not cp[i - 1].

    For a parent (R) with 3+ sequential, non-overlapping children,
    computeCriticalPath flattens the children's own subtrees onto the flat
    cp list in end-time order, producing cp = [R, C, B, A] here. For B (a
    chained sibling reached partway through that flattening), cp[i - 1] is
    C -- an unrelated leftover node from a *different* subtree, not B's real
    parent (R is). A drag implementation that used `self.cp[i - 1]` as "the
    parent" would look up C.children (empty, since C is a leaf), incorrectly
    conclude B has no true siblings, and report B's drag as its full,
    uncapped duration (205) -- silently missing the reduction that comes
    from B's real parent (R) and real siblings (A, B, C). The correct answer
    is 200 (205 minus the 5-unit overlap with A).
    """
    cp = sequential_siblings_with_slight_overlap_graph.get_critical_path()
    assert [node.sid for node in cp.cp] == ["R", "C", "B", "A"]

    drag = cp.calculate_drag()

    naive_cp_index_adjacency_b_drag = 205
    assert drag.drag_per_span["B"] != naive_cp_index_adjacency_b_drag
    assert drag.drag_per_span["B"] == 200
    assert drag.drag_per_span["R"] == 1000
    assert drag.drag_per_span["C"] == 600
    assert drag.drag_per_span["A"] == 200
    assert drag.total_drag == 2000

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
