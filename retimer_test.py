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


def test_retime_network_components_dict(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    span_components_map = {
        "A": {
            "request_network_delta": 10.0,
            "response_network_delta": 5.0,
        }
    }
    to_value_dict = {
        "request_network_delta": 2.0,
        "response_network_delta": 1.0,
    }
    diff = retimer.retime_network_components(
        graph=graph1.graph,
        component_names=["request_network_delta", "response_network_delta"],
        to_value=to_value_dict,
        span_components_map=span_components_map,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 88
    assert diff == 12.0


def test_retime_network_components_float(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    span_components_map = {
        "A": {
            "request_network_delta": 10.0,
            "response_network_delta": 5.0,
        }
    }
    diff = retimer.retime_network_components(
        graph=graph1.graph,
        component_names=["request_network_delta", "response_network_delta"],
        to_value=2.0,
        span_components_map=span_components_map,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 89
    assert diff == 11.0


def test_retime_network_components_none(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    span_components_map = {
        "A": {
            "request_network_delta": 10.0,
            "response_network_delta": 5.0,
        }
    }
    diff = retimer.retime_network_components(
        graph=graph1.graph,
        component_names=["request_network_delta", "response_network_delta"],
        to_value=None,
        span_components_map=span_components_map,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 85
    assert diff == 15.0


def test_remove_network_components_deprecated(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    span_components_map = {
        "A": {
            "request_network_delta": 10.0,
            "response_network_delta": 5.0,
        }
    }
    diff = retimer.remove_network_components(
        graph=graph1.graph,
        component_names=["request_network_delta", "response_network_delta"],
        span_components_map=span_components_map,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 85
    assert diff == 15.0


def test_retime_network_components_min_logic(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    span_components_map = {
        "A": {
            "request_network_delta": 1.0,
            "response_network_delta": 5.0,
        }
    }
    to_value_dict = {
        "request_network_delta": 2.0,
        "response_network_delta": 1.0,
    }
    diff = retimer.retime_network_components(
        graph=graph1.graph,
        component_names=["request_network_delta", "response_network_delta"],
        to_value=to_value_dict,
        span_components_map=span_components_map,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 96
    assert diff == 4.0


def test_sibling_propagation_cap():
    import pandas as pd
    df = pd.DataFrame({
        "trace_id": ["sibling_cap"] * 4,
        "span_id": ["A", "X", "C", "B"],
        "parent_rpc_span_id": ["0", "A", "A", "A"],
        "method_name": ["m1", "m2", "m3", "m4"],
        "server_job": ["j1", "j2", "j3", "j4"],
        "client_start_timestamp": [0.0, 0.0, 10.0, 30.0],
        "client_finish_timestamp": [100.0, 15.0, 29.0, 50.0],
        "server_start_timestamp": [0.0, 0.0, 10.0, 30.0],
        "server_finish_timestamp": [100.0, 15.0, 29.0, 50.0],
        "is_true_root": [True, False, False, False],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_app_delta": [100.0, 15.0, 19.0, 20.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "num_descendants": [3, 0, 0, 0],
    })
    g_cap = graph.CrispGraph.from_dataframe(df)
    retimer_engine = g_cap.get_retimer()

    retimer_engine.retime_node(
        g=g_cap.graph,
        node_span_id="C",
        new_start=0,
        new_end=9,
    )

    assert g_cap.graph.nodeHT["C"].startTime == 0
    assert g_cap.graph.nodeHT["C"].endTime == 9
    assert g_cap.graph.nodeHT["B"].startTime == 15
    assert g_cap.graph.nodeHT["B"].endTime == 35


def test_retime_network_components_clamping():
    import pandas as pd
    df = pd.DataFrame({
        "trace_id": ["clamping"] * 2,
        "span_id": ["A", "B"],
        "parent_rpc_span_id": ["0", "A"],
        "method_name": ["m1", "m2"],
        "server_job": ["j1", "j2"],
        "client_start_timestamp": [0.0, 10.0],
        "client_finish_timestamp": [100.0, 50.0],
        "server_start_timestamp": [0.0, 10.0],
        "server_finish_timestamp": [100.0, 50.0],
        "is_true_root": [True, False],
        "client_send_queue_delta": [0.0, 0.0],
        "request_network_delta": [80.0, 30.0],
        "server_recv_queue_delta": [0.0, 0.0],
        "server_app_delta": [20.0, 10.0],
        "server_send_queue_delta": [0.0, 0.0],
        "response_network_delta": [0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0],
        "num_descendants": [1, 0],
    })
    g_clamp = graph.CrispGraph.from_dataframe(df)
    retimer_engine = g_clamp.get_retimer()

    diff = retimer_engine.retime_network_components(
        graph=g_clamp.graph,
        component_names=["request_network_delta"],
        to_value=-20.0,
        span_components_map=g_clamp.get_span_components_map(),
    )
    assert g_clamp.graph.nodeHT["A"].startTime == 0
    assert g_clamp.graph.nodeHT["A"].endTime == 0
    assert g_clamp.graph.nodeHT["B"].startTime == 10
    assert g_clamp.graph.nodeHT["B"].endTime == 20
    assert diff == 100.0


def test_retime_service(graph1):
    graph1.restore_to_original_timestamps()
    retimer_engine = graph1.get_retimer()
    retimer_engine.retime_service(
        graph=graph1.graph,
        service_name="S1",
        percent_difference=-50,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 50


def test_retime_service_fixed_difference(graph1):
    graph1.restore_to_original_timestamps()
    retimer_engine = graph1.get_retimer()
    retimer_engine.retime_service(
        graph=graph1.graph,
        service_name="S1",
        fixed_difference=20,
    )
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 120


def test_retime_method_positional(graph1):
    graph1.restore_to_original_timestamps()
    retimer_engine = graph1.get_retimer()
    retimer_engine.retime_method(graph1.graph, "S1.one", 10)
    assert graph1.graph.nodeHT["A"].startTime == 0
    assert graph1.graph.nodeHT["A"].endTime == 110


def test_retime_method_clamps_negative_duration():
    import pandas as pd
    df = pd.DataFrame({
        "trace_id": ["clamp_neg"] * 1,
        "span_id": ["A"],
        "parent_rpc_span_id": ["0"],
        "method_name": ["j1.m1"],
        "server_job": ["j1"],
        "client_start_timestamp": [10.0],
        "client_finish_timestamp": [110.0],
        "server_start_timestamp": [10.0],
        "server_finish_timestamp": [110.0],
        "is_true_root": [True],
        "client_send_queue_delta": [0.0],
        "request_network_delta": [0.0],
        "server_recv_queue_delta": [0.0],
        "server_app_delta": [100.0],
        "server_send_queue_delta": [0.0],
        "response_network_delta": [0.0],
        "client_recv_queue_delta": [0.0],
        "num_descendants": [0],
    })
    g_clamp = graph.CrispGraph.from_dataframe(df)
    retimer_engine = g_clamp.get_retimer()

    retimer_engine.retime_method(
        graph=g_clamp.graph,
        method="j1.m1",
        fixed_difference=-150.0,
    )
    assert g_clamp.graph.nodeHT["A"].startTime == 10.0
    assert g_clamp.graph.nodeHT["A"].endTime == 10.0
    assert g_clamp.graph.nodeHT["A"].duration == 0.0


def test_retime_with_missing_dependency_nodes(graph1):
    graph1.restore_to_original_timestamps()
    retimer = graph1.get_retimer()
    # Partially empty/missing dependency graph nodes to ensure no KeyError
    retimer.dependency_graph.deps = {}
    retimer.retime_node(
        g=graph1.graph,
        node_span_id="C",
        new_start=30,
        new_end=60,
        freeze_starts=True,
    )
    assert graph1.graph.nodeHT["C"].startTime == 30
    assert graph1.graph.nodeHT["C"].endTime == 60


def test_retime_repeated_sibling_method_does_not_self_constrain():
    import pandas as pd
    # Parent A (0-100) has child C (10-30, S2) followed by two sequential calls
    # to the same service S3: B1 (30-50, S3) and B2 (60-80, S3).
    # Because B1 and B2 share the node name S3.2, S3.2 appears in its own
    # happens_before set. When C is sped up from 10-30 to 10-20 (-10s),
    # B1 (original start 30) must not be constrained by B2 (original end 80 > 30).
    df = pd.DataFrame({
        "trace_id": ["repeated_sib"] * 4,
        "span_id": ["A", "C", "B1", "B2"],
        "parent_rpc_span_id": ["0", "A", "A", "A"],
        "method_name": ["S1.root", "S2.prep", "S3.work", "S3.work"],
        "server_job": ["S1", "S2", "S3", "S3"],
        "client_start_timestamp": [0.0, 10.0, 30.0, 60.0],
        "client_finish_timestamp": [100.0, 30.0, 50.0, 80.0],
        "server_start_timestamp": [0.0, 10.0, 30.0, 60.0],
        "server_finish_timestamp": [100.0, 30.0, 50.0, 80.0],
        "is_true_root": [True, False, False, False],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_app_delta": [100.0, 20.0, 20.0, 20.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "num_descendants": [3, 0, 0, 0],
    })
    cg = graph.CrispGraph.from_dataframe(df)
    retimer_engine = cg.get_retimer()
    retimer_engine.retime_node(
        g=cg.graph,
        node_span_id="C",
        new_start=10.0,
        new_end=20.0,
    )
    assert cg.graph.nodeHT["B1"].startTime == 20.0
    assert cg.graph.nodeHT["B1"].endTime == 40.0
    assert cg.graph.nodeHT["B2"].startTime == 50.0
    assert cg.graph.nodeHT["B2"].endTime == 70.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
