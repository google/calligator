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
from third_party.CRISP import graph as crisp_graph
import graph

_TEST_CASES_PATH = "test_cases/"

@pytest.fixture(scope="module")
def graph1():
    with open(_TEST_CASES_PATH + "test_1.json") as f:
        j = json.load(f)
    return graph.CrispGraph(crisp_graph.Graph(j, "S1", "one", "file1", False))

@pytest.fixture(scope="module")
def graph4():
    with open(_TEST_CASES_PATH + "test_4.json") as f:
        j4 = json.load(f)
    return graph.CrispGraph(crisp_graph.Graph(j4, "S1", "one", "file4", False))

# g:
# 0 ------------------ A ------------------ 100
#     10 ---------- B ------------- 60
#         20 ---- C ---- 30

# g4:
# 0 ------------------ A ------------------ 100
#                                                 110 ------ B ---- 160
#                                                   120 ---- C -- 150
#                         60 ---- D -- 90

def test_retime_node_g(graph1):
    """Test retiming where the new start time conflicts with the parent start delay."""
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    retimer.retime_node(
        g=graph1.graph,
        node_span_id="C",
        new_start=30,
        new_end=60,
        freeze_starts=True,
    )
    assert graph1.graph.nodeHT["C"].startTime == 30
    assert graph1.graph.nodeHT["C"].endTime == 60
    assert graph1.graph.nodeHT["B"].startTime == 10
    assert graph1.graph.nodeHT["B"].endTime == 90
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 130

def test_retime_node_g_freeze_starts(graph1):
    """Test retiming where the new start time conflicts with the parent start delay."""
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    retimer.retime_node(
        g=graph1.graph,
        node_span_id="C",
        new_start=30,
        new_end=60,
        freeze_starts=True,
    )
    assert graph1.graph.nodeHT["C"].startTime == 30
    assert graph1.graph.nodeHT["C"].endTime == 60
    assert graph1.graph.nodeHT["B"].startTime == 10
    assert graph1.graph.nodeHT["A"].startTime == 0

def test_retime_with_async_spans(graph4):
    graph4.restore_to_original_timestamps()
    retimer = graph4.get_retimer()
    retimer.retime_node(g=graph4.graph, node_span_id="A", new_start=0, new_end=95)
    assert graph4.graph.nodeHT["A"].startTime == 0
    assert graph4.graph.nodeHT["A"].endTime == 95
    assert graph4.graph.nodeHT["B"].startTime == 110
    assert graph4.graph.nodeHT["B"].endTime == 160
    assert graph4.graph.nodeHT["C"].startTime == 120
    assert graph4.graph.nodeHT["C"].endTime == 150
    assert graph4.graph.nodeHT["D"].startTime == 60
    assert graph4.graph.nodeHT["D"].endTime == 90

def test_retime_with_async_spans_2(graph4):
    graph4.restore_to_original_timestamps()
    retimer = graph4.get_retimer()
    retimer.retime_node(
        g=graph4.graph,
        node_span_id="D",
        new_start=50,
        new_end=80,
        freeze_starts=True,
    )
    assert graph4.graph.nodeHT["A"].startTime == 0
    assert graph4.graph.nodeHT["A"].endTime == 90
    assert graph4.graph.nodeHT["B"].startTime == 110
    assert graph4.graph.nodeHT["B"].endTime == 160
    assert graph4.graph.nodeHT["C"].startTime == 120
    assert graph4.graph.nodeHT["C"].endTime == 150
    assert graph4.graph.nodeHT["D"].startTime == 50
    assert graph4.graph.nodeHT["D"].endTime == 80

def test_retime_with_async_spans_3(graph4):
    graph4.restore_to_original_timestamps()
    retimer = graph4.get_retimer()
    retimer.retime_node(
        g=graph4.graph,
        node_span_id="C",
        new_start=130,
        new_end=160,
    )
    assert graph4.graph.nodeHT["A"].startTime == 0
    assert graph4.graph.nodeHT["A"].endTime == 100
    assert graph4.graph.nodeHT["B"].startTime == 110
    assert graph4.graph.nodeHT["B"].endTime == 170
    assert graph4.graph.nodeHT["C"].startTime == 130
    assert graph4.graph.nodeHT["C"].endTime == 160
    assert graph4.graph.nodeHT["D"].startTime == 60
    assert graph4.graph.nodeHT["D"].endTime == 90

def test_retime_method_percent_difference_g(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    retimer.retime_method(graph=graph1.graph, method="S1.one", percent_difference=10)
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 110
    assert graph1.graph.nodeHT["B"].startTime == 10
    assert graph1.graph.nodeHT["B"].endTime == 60
    assert graph1.graph.nodeHT["C"].startTime == 20
    assert graph1.graph.nodeHT["C"].endTime == 30

def test_retime_method_fixed_difference_g(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    retimer.retime_method(graph=graph1.graph, method="S1.one", fixed_difference=20)
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 120
    assert graph1.graph.nodeHT["B"].startTime == 10
    assert graph1.graph.nodeHT["B"].endTime == 60
    assert graph1.graph.nodeHT["C"].startTime == 20
    assert graph1.graph.nodeHT["C"].endTime == 30

def test_retime_method_fixed_difference_shrink_floors_g(graph1):
    """A shrink bigger than a node's own duration must floor at 0, not grow it.

    C is 20-30 (duration 10); fixed_difference=-50 asks for more shrink than
    C has room for, so it should floor at 20-20 (duration 0) rather than
    flipping into a growth.
    """
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    retimer.retime_method(
        graph=graph1.graph, method="S3.three", fixed_difference=-50
    )
    assert graph1.graph.nodeHT["C"].startTime == 20
    assert graph1.graph.nodeHT["C"].endTime == 20
    assert graph1.graph.nodeHT["C"].duration == 0
    # The floored -10 delay (not the requested -50) propagates to B and A.
    assert graph1.graph.nodeHT["B"].startTime == 10
    assert graph1.graph.nodeHT["B"].endTime == 50
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 90
