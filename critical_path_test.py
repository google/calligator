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
