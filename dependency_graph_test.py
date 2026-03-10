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
from graph import GraphCollection

_TEST_CASES_PATH = "test_cases/"

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

# g6:
# 0 ------------------ A ------------------ 100
#     10 ---------- B ------------- 60           110 - B - 120
#         20 ---- C ---- 30

@pytest.fixture
def graph1():
    with open(_TEST_CASES_PATH + "test_1.json") as f:
        j = json.load(f)
    return CrispGraph(Graph(j, "S1", "one", "file1", False))

@pytest.fixture
def graph2():
    with open(_TEST_CASES_PATH + "test_2.json") as f:
        j2 = json.load(f)
    return CrispGraph(Graph(j2, "S1", "one", "file2", False))

@pytest.fixture
def graph3():
    with open(_TEST_CASES_PATH + "test_3.json") as f:
        j3 = json.load(f)
    return CrispGraph(Graph(j3, "S1", "one", "file3", False))

@pytest.fixture
def graph4():
    with open(_TEST_CASES_PATH + "test_4.json") as f:
        j4 = json.load(f)
    return CrispGraph(Graph(j4, "S1", "one", "file4", False))

def test_single_dependency_graph_g(graph1):
    single_deps = graph1.get_dependency_graph()
    assert len(single_deps.deps) == 3
    assert single_deps.deps["S1.1"].happens_before == set()
    assert single_deps.deps["S1.1"].child_dependents == {"S2.2"}
    assert single_deps.deps["S1.1"].parent_start_delay == [10]
    assert single_deps.deps["S1.1"].parent_end_delay == [40]
    assert single_deps.deps["S2.2"].happens_before == set()
    assert single_deps.deps["S2.2"].child_dependents == {"S3.3"}
    assert single_deps.deps["S2.2"].parent_start_delay == [10]
    assert single_deps.deps["S2.2"].parent_end_delay == [30]
    assert single_deps.deps["S3.3"].happens_before == set()
    assert single_deps.deps["S3.3"].child_dependents == set()
    assert single_deps.deps["S3.3"].parent_start_delay == []
    assert single_deps.deps["S3.3"].parent_end_delay == []

def test_single_dependency_graph_g2(graph2):
    single_deps = graph2.get_dependency_graph()
    assert len(single_deps.deps) == 4
    assert single_deps.deps["S1.1"].happens_before == set()
    assert single_deps.deps["S1.1"].child_dependents == {"S2.2", "S4.2", "S3.2"}
    assert single_deps.deps["S1.1"].parent_start_delay == [5]
    assert single_deps.deps["S1.1"].parent_end_delay == [45]
    assert single_deps.deps["S2.2"].happens_before == {"S4.2"}
    assert single_deps.deps["S2.2"].child_dependents == set()
    assert single_deps.deps["S2.2"].parent_start_delay == []
    assert single_deps.deps["S2.2"].parent_end_delay == []
    assert single_deps.deps["S3.2"].happens_before == {"S4.2", "S2.2"}
    assert single_deps.deps["S3.2"].child_dependents == set()
    assert single_deps.deps["S3.2"].parent_start_delay == []
    assert single_deps.deps["S3.2"].parent_end_delay == []
    assert single_deps.deps["S4.2"].happens_before == set()
    assert single_deps.deps["S4.2"].child_dependents == set()
    assert single_deps.deps["S4.2"].parent_start_delay == []
    assert single_deps.deps["S4.2"].parent_end_delay == []

def test_dependency_asynchronous_spans(graph4):
    deps = graph4.get_dependency_graph()
    assert len(deps.deps) == 4
    assert deps.deps["S1.1"].happens_before == set()
    assert deps.deps["S1.1"].child_dependents == {"S4.2"}
    assert deps.deps["S1.1"].parent_start_delay == [60]
    assert deps.deps["S1.1"].parent_end_delay == [10]
    assert deps.deps["S2.2"].happens_before == set()
    assert deps.deps["S2.2"].child_dependents == {"S3.3"}
    assert deps.deps["S2.2"].parent_start_delay == [10]
    assert deps.deps["S2.2"].parent_end_delay == [10]
    assert deps.deps["S3.3"].happens_before == set()
    assert deps.deps["S3.3"].child_dependents == set()
    assert deps.deps["S3.3"].parent_start_delay == []
    assert deps.deps["S3.3"].parent_end_delay == []
    assert deps.deps["S4.2"].happens_before == set()
    assert deps.deps["S4.2"].child_dependents == set()
    assert deps.deps["S4.2"].parent_start_delay == []
    assert deps.deps["S4.2"].parent_end_delay == []

def test_multiple_dependency_graph(graph1, graph2, graph3):
    graphs_list = [graph1, graph2, graph3]
    collection = GraphCollection(graphs_list=graphs_list)
    multiple_deps = collection.get_dependency_graph()
    assert len(multiple_deps.deps) == 5  # 5 since some are at different depths
    assert multiple_deps.deps["S1.1"].happens_before == set()
    assert multiple_deps.deps["S1.1"].child_dependents == {"S2.2", "S3.2", "S4.2"}
    assert sorted(multiple_deps.deps["S1.1"].parent_start_delay) == [5, 10, 10]
    assert sorted(multiple_deps.deps["S1.1"].parent_end_delay) == [40, 45, 50]
    assert multiple_deps.deps["S2.2"].happens_before == {"S4.2"}
    assert multiple_deps.deps["S2.2"].child_dependents == {"S3.3"}
    assert multiple_deps.deps["S2.2"].parent_start_delay == [10]
    assert multiple_deps.deps["S2.2"].parent_end_delay == [30]
    assert multiple_deps.deps["S3.3"].happens_before == set()
    assert multiple_deps.deps["S3.3"].child_dependents == set()
    assert multiple_deps.deps["S3.3"].parent_start_delay == []
    assert multiple_deps.deps["S3.3"].parent_end_delay == []
    assert multiple_deps.deps["S3.2"].happens_before == {"S4.2"}
    assert multiple_deps.deps["S3.2"].child_dependents == set()
    assert multiple_deps.deps["S3.2"].parent_start_delay == []
    assert multiple_deps.deps["S3.2"].parent_end_delay == []
    assert multiple_deps.deps["S4.2"].happens_before == set()
    assert multiple_deps.deps["S4.2"].child_dependents == set()
    assert multiple_deps.deps["S4.2"].parent_start_delay == []
    assert multiple_deps.deps["S4.2"].parent_end_delay == []
