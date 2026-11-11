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

import unittest
import immutabledict
import pandas as pd
import df_utils

_FAST_DF_DICT = immutabledict.immutabledict({
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
    "num_children": [2, 1, 0],
    "client_user": ["A", "B", "C"],
    "client_job": ["A", "B", "C"],
    "server_user": ["server_A", "server_B", "server_C"],
    "bad_column": [69, 420, 690],
})

_NOMINAL_DF_DICT = immutabledict.immutabledict({
    "trace_id": [1234567891, 1234567891, 1234567891],
    "span_id": [4, 5, 6],
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
    "server_app_delta": [900, 0.2, 2.5],
    "server_send_queue_delta": [0.1, 0.2, 0.3],
    "response_network_delta": [0.1, 0.2, 0.3],
    "client_recv_queue_delta": [0.1, 0.2, 0.3],
    "num_descendants": [2, 1, 0],
    "num_children": [2, 1, 0],
    "client_user": ["A", "B", "C"],
    "client_job": ["A", "B", "C"],
    "server_user": ["server_A2", "server_B2", "server_C2"],
    "bad_column": [69, 420, 690],
})

_SLOW_DF_DICT = immutabledict.immutabledict({
    "trace_id": [1234567892, 1234567892, 1234567892],
    "span_id": [7, 8, 9],
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
    "server_app_delta": [9000, 100, 2.5],
    "server_send_queue_delta": [0.1, 0.2, 0.3],
    "response_network_delta": [0.1, 0.2, 0.3],
    "client_recv_queue_delta": [0.1, 0.2, 0.3],
    "num_descendants": [2, 1, 0],
    "num_children": [2, 1, 0],
    "client_user": ["A", "B", "C"],
    "client_job": ["A", "B", "C"],
    "server_user": ["server_A3", "server_B3", "server_C3"],
    "bad_column": [69, 420, 690],
})

_INCOMPLETE_DF_DICT = immutabledict.immutabledict({
    "trace_id": [1212, 1212, 7000],
    "SpanID": [1, 2, 1],
    "parent_rpc_span_id": [0, 1, 0],
    "method": ["stuff", "more_stuff", "even_more_stuff"],
    "billable_service": ["android", "youtube", "play"],
})


class UtilsTest(unittest.TestCase):

  def test_get_all_root_methods(self):
    fast_df = pd.DataFrame(dict(_FAST_DF_DICT))
    nominal_df = pd.DataFrame(dict(_NOMINAL_DF_DICT))
    slow_df = pd.DataFrame(dict(_SLOW_DF_DICT))
    all_df = pd.concat([fast_df, nominal_df, slow_df], ignore_index=True)
    root_methods = df_utils.get_all_root_methods(df=fast_df)
    self.assertEqual(root_methods, {"A.foo"})
    root_methods = df_utils.get_all_root_methods(df=all_df)
    self.assertEqual(root_methods, {"A.foo"})

  def test_get_rtt_time_for_df(self):
    fast_df = pd.DataFrame(dict(_FAST_DF_DICT))
    rtt_time = df_utils.get_rtt_time_for_df(df=fast_df)
    self.assertAlmostEqual(rtt_time["rtt_time"].iloc[0], 100, delta=0.00001)
    self.assertAlmostEqual(rtt_time["rtt_time"].iloc[1], 53, delta=0.00001)
    self.assertAlmostEqual(rtt_time["rtt_time"].iloc[2], 10, delta=0.00001)

  def test_get_percentile_span_ids(self):
    fast_df = pd.DataFrame(dict(_FAST_DF_DICT))
    nominal_df = pd.DataFrame(dict(_NOMINAL_DF_DICT))
    slow_df = pd.DataFrame(dict(_SLOW_DF_DICT))
    all_df = pd.concat([fast_df, nominal_df, slow_df], ignore_index=True)
    span_ids = df_utils.get_percentile_span_ids(
        df=fast_df, percentile_start=0, percentile_end=100
    )
    self.assertEqual(span_ids, [1])
    span_ids = df_utils.get_percentile_span_ids(
        df=all_df, percentile_start=0, percentile_end=100
    )
    self.assertEqual(span_ids, [1, 4, 7])

  def test_filter_df(self):
    fast_df = pd.DataFrame(dict(_FAST_DF_DICT))
    nominal_df = pd.DataFrame(dict(_NOMINAL_DF_DICT))
    slow_df = pd.DataFrame(dict(_SLOW_DF_DICT))
    all_df = pd.concat([fast_df, nominal_df, slow_df], ignore_index=True)
    df = df_utils.filter_df(
        df=all_df,
        by_column="method_name",
        by_column_value="A.foo",
        include_whole_trace=False,
    )
    self.assertEqual(df.shape[0], 3)
    self.assertEqual(df["method_name"].iloc[0], "A.foo")
    self.assertEqual(df["method_name"].iloc[1], "A.foo")
    self.assertEqual(df["method_name"].iloc[2], "A.foo")

  def test_preprocess_df(self):
    fast_df = pd.DataFrame(dict(_FAST_DF_DICT))
    nominal_df = pd.DataFrame(dict(_NOMINAL_DF_DICT))
    slow_df = pd.DataFrame(dict(_SLOW_DF_DICT))
    all_df = pd.concat([fast_df, nominal_df, slow_df], ignore_index=True)
    df = df_utils.preprocess(df=all_df)
    with self.subTest("number_of_rows"):
      self.assertEqual(df.shape[0], 9)
    with self.subTest("column_names"):
      self.assertNotIn("bad_column", df.columns)
    with self.subTest("duplicates"):
      self.assertEqual(df["trace_id"].nunique(), 3)
    with self.subTest("starting slashes"):
      self.assertEqual(df["method_name"].iloc[0], "A.foo")

  def test_preprocess_df_with_optional_columns(self):
    incomplete_df = pd.DataFrame(dict(_INCOMPLETE_DF_DICT))
    df = df_utils.preprocess(df=incomplete_df, is_raw=False)
    self.assertIn("billable_service", df.columns)
    self.assertEqual(len(df.columns), 24)

  def test_validate_raw_dataframe_failures(self):
    # 1. Missing required column
    bad_df_missing_col = pd.DataFrame({
        "trace_id": [1],
        "span_id": [1],
        "server_job": ["A"],
        "server_app_delta": [1.0],
        "request_network_delta": [0.0],
        "response_network_delta": [0.0],
        "client_send_queue_delta": [0.0],
        "server_send_queue_delta": [0.0],
        "client_recv_queue_delta": [0.0],
        "server_recv_queue_delta": [0.0],
    })
    with self.assertRaises(ValueError) as ctx:
      df_utils.preprocess(bad_df_missing_col, is_raw=True)
    self.assertIn("Required column missing", str(ctx.exception))

    # 1b. Reloading preprocessed data without raw timestamps
    bad_df_preprocessed = pd.DataFrame({
        "trace_id": [1],
        "span_id": [1],
        "method_name": ["A"],
        "server_job": ["A"],
        "server_app_delta": [1.0],
        "request_network_delta": [0.0],
        "response_network_delta": [0.0],
        "client_send_queue_delta": [0.0],
        "server_send_queue_delta": [0.0],
        "client_recv_queue_delta": [0.0],
        "server_recv_queue_delta": [0.0],
    })
    with self.assertRaises(ValueError) as ctx:
      df_utils.preprocess(bad_df_preprocessed, is_raw=True)
    self.assertIn(
        "Required column missing: client_start_timestamp",
        str(ctx.exception),
    )

    # 1c. Missing required column (Jaeger)
    bad_jaeger_missing_col = pd.DataFrame({
        "traceID": ["t1"],
        "spanID": ["s1"],
        "startTime": [1000],
    })
    with self.assertRaises(ValueError) as ctx:
      df_utils.preprocess(
          bad_jaeger_missing_col, is_jaeger_trace=True, is_raw=True
      )
    self.assertIn("Required Jaeger column missing", str(ctx.exception))

    # 2. Numeric column has non-numeric type
    bad_df_non_numeric = pd.DataFrame({
        "trace_id": [1],
        "span_id": [1],
        "method_name": ["A.foo"],
        "server_job": ["A"],
        "server_app_delta": ["not_a_float!"],
        "request_network_delta": [0.0],
        "response_network_delta": [0.0],
        "client_send_queue_delta": [0.0],
        "server_send_queue_delta": [0.0],
        "client_recv_queue_delta": [0.0],
        "server_recv_queue_delta": [0.0],
        "client_start_timestamp": [10.0],
        "client_finish_timestamp": [20.0],
    })
    with self.assertRaises(ValueError) as ctx:
      df_utils.preprocess(bad_df_non_numeric, is_raw=True)
    self.assertIn("must be numeric type", str(ctx.exception))

  def test_preprocess_df_drops_null_rows(self):
    # 1. Null in delta / metric column: corrupted trace is dropped, valid trace
    # is preserved.
    df_with_null_metric = pd.DataFrame({
        "trace_id": [1, 1, 2, 2],
        "span_id": [1, 2, 3, 4],
        "method_name": ["A.foo", "A.bar", "B.foo", "B.bar"],
        "server_job": ["A", "A", "B", "B"],
        "server_app_delta": [1.0, float("nan"), 1.0, 2.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_start_timestamp": [10.0, 10.0, 10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0, 20.0, 20.0],
    })
    processed_df = df_utils.preprocess(df_with_null_metric, is_raw=True)
    self.assertEqual(len(processed_df), 2)
    self.assertEqual(set(processed_df["span_id"]), {3, 4})
    self.assertEqual(list(processed_df["trace_id"].unique()), [2])

    # 2. Null in structural column: corrupted trace is dropped, valid trace is
    # preserved.
    df_with_null_structural = pd.DataFrame({
        "trace_id": [1, 1, 2, 2],
        "span_id": [1, 2, 3, 4],
        "method_name": ["A.foo", None, "B.foo", "B.bar"],
        "server_job": ["A", "A", "B", "B"],
        "server_app_delta": [1.0, 2.0, 1.0, 2.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_start_timestamp": [10.0, 10.0, 10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0, 20.0, 20.0],
    })
    processed_df = df_utils.preprocess(df_with_null_structural, is_raw=True)
    self.assertEqual(len(processed_df), 2)
    self.assertEqual(set(processed_df["span_id"]), {3, 4})
    self.assertEqual(list(processed_df["trace_id"].unique()), [2])

    # 3. All rows contain nulls: returns empty DataFrame without error and
    # intact schema.
    bad_df_all_null = pd.DataFrame({
        "trace_id": [1, 2],
        "span_id": [1, 2],
        "method_name": [None, "B.bar"],
        "server_job": ["A", None],
        "server_app_delta": [1.0, 2.0],
        "request_network_delta": [0.0, 0.0],
        "response_network_delta": [0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0],
        "client_start_timestamp": [10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0],
    })
    processed_df = df_utils.preprocess(bad_df_all_null, is_raw=True)
    self.assertEqual(len(processed_df), 0)
    self.assertIn("trace_id", processed_df.columns)
    self.assertIn("rtt_time", processed_df.columns)

    # 4. Jaeger JSON containing null span: corrupted trace is dropped, valid
    # trace preserved.
    jaeger_json_with_null = {
        "data": [
            {
                "traceID": "trace_1",
                "processes": {"p1": {"serviceName": "service_A"}},
                "spans": [
                    {
                        "traceID": "trace_1",
                        "spanID": "span_1",
                        "operationName": "op_A",
                        "startTime": 1000000,
                        "duration": 2000000,
                        "processID": "p1",
                        "references": [],
                    },
                    {
                        "traceID": "trace_1",
                        "spanID": "span_2",
                        "operationName": None,
                        "startTime": 1000000,
                        "duration": 2000000,
                        "processID": "p1",
                    },
                ],
            },
            {
                "traceID": "trace_2",
                "processes": {"p1": {"serviceName": "service_B"}},
                "spans": [
                    {
                        "traceID": "trace_2",
                        "spanID": "span_3",
                        "operationName": "op_B1",
                        "startTime": 1000000,
                        "duration": 2000000,
                        "processID": "p1",
                        "references": [],
                    },
                    {
                        "traceID": "trace_2",
                        "spanID": "span_4",
                        "operationName": "op_B2",
                        "startTime": 1000000,
                        "duration": 2000000,
                        "processID": "p1",
                    },
                ],
            },
        ]
    }
    df_jaeger = df_utils.get_df_from_jaeger_json(jaeger_json_with_null)
    self.assertEqual(len(df_jaeger), 2)
    self.assertEqual(set(df_jaeger["span_id"]), {"span_3", "span_4"})
    self.assertEqual(list(df_jaeger["trace_id"].unique()), ["trace_2"])

    # 5. Null in span_id: corrupted trace is dropped, valid trace preserved
    df_with_null_span_id = pd.DataFrame({
        "trace_id": [1, 1, 2, 2],
        "span_id": [1, None, 3, 4],
        "method_name": ["A.foo", "A.bar", "B.foo", "B.bar"],
        "server_job": ["A", "A", "B", "B"],
        "server_app_delta": [1.0, 2.0, 1.0, 2.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_start_timestamp": [10.0, 10.0, 10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0, 20.0, 20.0],
    })
    processed_df = df_utils.preprocess(df_with_null_span_id, is_raw=True)
    self.assertEqual(len(processed_df), 2)
    self.assertEqual(set(processed_df["span_id"]), {3, 4})
    self.assertEqual(list(processed_df["trace_id"].unique()), [2])

    # 6. Null in timestamp: corrupted trace is dropped, valid trace preserved
    df_with_null_timestamp = pd.DataFrame({
        "trace_id": [1, 1, 2, 2],
        "span_id": [1, 2, 3, 4],
        "method_name": ["A.foo", "A.bar", "B.foo", "B.bar"],
        "server_job": ["A", "A", "B", "B"],
        "server_app_delta": [1.0, 2.0, 1.0, 2.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_start_timestamp": [10.0, float("nan"), 10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0, 20.0, 20.0],
    })
    processed_df = df_utils.preprocess(df_with_null_timestamp, is_raw=True)
    self.assertEqual(len(processed_df), 2)
    self.assertEqual(set(processed_df["span_id"]), {3, 4})
    self.assertEqual(list(processed_df["trace_id"].unique()), [2])

    # 7. Non-raw dataframe with nulls: corrupted trace is dropped, valid trace
    # preserved.
    df_non_raw_with_nulls = pd.DataFrame({
        "trace_id": [1, 1, 2, 2],
        "span_id": [1, 2, 3, 4],
        "method_name": ["A.foo", None, "B.foo", "B.bar"],
    })
    processed_df = df_utils.preprocess(df_non_raw_with_nulls, is_raw=False)
    self.assertEqual(len(processed_df), 2)
    self.assertEqual(set(processed_df["span_id"]), {3, 4})
    self.assertEqual(list(processed_df["trace_id"].unique()), [2])

    # 8. Nulls in optional columns do not cause the trace to be dropped
    df_with_optional_nulls = pd.DataFrame({
        "trace_id": [1, 1, 2, 2],
        "span_id": [1, 2, 3, 4],
        "method_name": ["A.foo", "A.bar", "B.foo", "B.bar"],
        "server_job": ["A", "A", "B", "B"],
        "server_app_delta": [1.0, 2.0, 1.0, 2.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0],
        "client_start_timestamp": [10.0, 10.0, 10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0, 20.0, 20.0],
        "billable_service": [None, "service_1", "service_2", None],
        "references": [None, [], None, [{"spanID": "ref_1"}]],
    })
    processed_df = df_utils.preprocess(df_with_optional_nulls, is_raw=True)
    self.assertEqual(len(processed_df), 4)
    self.assertEqual(set(processed_df["span_id"]), {1, 2, 3, 4})
    self.assertIn("billable_service", processed_df.columns)
    self.assertIn("references", processed_df.columns)

  def test_drop_traces_with_nulls_direct_edge_cases(self):
    # 1. Empty DataFrame returns empty DataFrame
    empty_df = pd.DataFrame()
    self.assertTrue(df_utils._drop_traces_with_nulls(empty_df).empty)

    # 2. Missing trace_id column returns copy untouched
    no_trace_id_df = pd.DataFrame(
        {"span_id": [1, 2], "method_name": ["A", None]}
    )
    res = df_utils._drop_traces_with_nulls(no_trace_id_df)
    self.assertEqual(len(res), 2)

    # 3. No candidate columns present returns copy untouched
    no_candidates_df = pd.DataFrame({"unrelated_col": [1, 2]})
    res = df_utils._drop_traces_with_nulls(no_candidates_df)
    self.assertEqual(len(res), 2)

    # 4. Null trace_id in a row is dropped, while valid traces are retained
    df_null_tid = pd.DataFrame({
        "trace_id": [1, 1, None, 2, 2],
        "span_id": [1, 2, 3, 4, 5],
        "method_name": ["A.m1", "A.m2", "B.m3", "C.m4", "C.m5"],
        "server_job": ["A", "A", "B", "C", "C"],
        "server_app_delta": [1.0, 2.0, 1.0, 1.0, 2.0],
        "request_network_delta": [0.0, 0.0, 0.0, 0.0, 0.0],
        "response_network_delta": [0.0, 0.0, 0.0, 0.0, 0.0],
        "client_send_queue_delta": [0.0, 0.0, 0.0, 0.0, 0.0],
        "server_send_queue_delta": [0.0, 0.0, 0.0, 0.0, 0.0],
        "client_recv_queue_delta": [0.0, 0.0, 0.0, 0.0, 0.0],
        "server_recv_queue_delta": [0.0, 0.0, 0.0, 0.0, 0.0],
        "client_start_timestamp": [10.0, 10.0, 10.0, 10.0, 10.0],
        "client_finish_timestamp": [20.0, 20.0, 20.0, 20.0, 20.0],
    })
    res = df_utils._drop_traces_with_nulls(df_null_tid)
    self.assertEqual(len(res), 4)
    self.assertEqual(set(res["span_id"]), {1, 2, 4, 5})
    self.assertEqual(set(res["trace_id"]), {1, 2})

    # 5. Direct Jaeger traces with null candidate fields (e.g. duration)
    df_jaeger = pd.DataFrame({
        "traceID": ["t1", "t1", "t2", "t2"],
        "spanID": ["s1", "s2", "s3", "s4"],
        "startTime": [1000, 1000, 1000, 1000],
        "duration": [2000, None, 2000, 2000],
        "operationName": ["op1", "op2", "op3", "op4"],
    })
    res_jaeger = df_utils._drop_traces_with_nulls(
        df_jaeger, is_jaeger_trace=True
    )
    self.assertEqual(len(res_jaeger), 2)
    self.assertEqual(set(res_jaeger["spanID"]), {"s3", "s4"})
    self.assertEqual(list(res_jaeger["traceID"].unique()), ["t2"])

  def test_preprocess_empty_dataframe(self):
    empty_df = pd.DataFrame(
        columns=[
            "trace_id",
            "span_id",
            "method_name",
            "server_job",
            "server_app_delta",
            "request_network_delta",
            "response_network_delta",
            "client_send_queue_delta",
            "server_send_queue_delta",
            "client_recv_queue_delta",
            "server_recv_queue_delta",
            "client_start_timestamp",
            "client_finish_timestamp",
        ]
    )
    processed_df = df_utils.preprocess(empty_df, is_raw=True)
    self.assertEqual(len(processed_df), 0)

  def test_get_df_from_jaeger_json(self):
    jaeger_json = {
        "data": [{
            "traceID": "trace_1",
            "processes": {"p1": {"serviceName": "service_A"}},
            "spans": [{
                "traceID": "trace_1",
                "spanID": "span_1",
                "operationName": "op_A",
                "startTime": 1000000,
                "duration": 2000000,
                "processID": "p1",
                "references": [],
            }],
        }]
    }
    df = df_utils.get_df_from_jaeger_json(jaeger_json)

    self.assertIn(df_utils.constants.CLIENT_START_TIMESTAMP, df.columns)
    self.assertAlmostEqual(
        df[df_utils.constants.CLIENT_START_TIMESTAMP].iloc[0], 1.0
    )
    self.assertAlmostEqual(
        df[df_utils.constants.CLIENT_FINISH_TIMESTAMP].iloc[0], 3.0
    )
    self.assertAlmostEqual(
        df[df_utils.constants.SERVER_START_TIMESTAMP].iloc[0], 1.0
    )
    self.assertAlmostEqual(
        df[df_utils.constants.SERVER_FINISH_TIMESTAMP].iloc[0], 3.0
    )
    self.assertAlmostEqual(df[df_utils.constants.SERVER_APP_DELTA].iloc[0], 2.0)

  def test_get_num_descendants_parent_pointing_outside_trace(self):
    """Verifies handling of parent_rpc_span_id pointing to a span not present in trace."""
    df = pd.DataFrame({
        "trace_id": ["t1", "t1", "t1"],
        "span_id": ["A", "B", "C"],
        "parent_rpc_span_id": ["0", "MISSING_PARENT", "A"],
        "is_true_root": [True, False, False],
    })
    result_df = df_utils._get_num_descendants(df)
    self.assertEqual(result_df[df_utils.constants.NUM_DESCENDANTS].iloc[0], 1)  # A has child C
    self.assertEqual(result_df[df_utils.constants.NUM_DESCENDANTS].iloc[1], 0)  # B has 0 descendants
    self.assertEqual(result_df[df_utils.constants.NUM_DESCENDANTS].iloc[2], 0)  # C has 0 descendants

  def test_get_root_span_id_multiple_roots(self):
    """Verifies root selection when multiple spans have is_true_root=True or no parents."""
    df = pd.DataFrame({
        "trace_id": ["t1", "t1", "t1"],
        "span_id": ["A", "B", "C"],
        "parent_rpc_span_id": ["0", "0", "A"],
        "is_true_root": [True, True, False],
        "num_descendants": [1, 0, 0],
    })
    # When true_roots exists, it returns the first true root in df
    root_sid = df_utils.get_root_span_id(df)
    self.assertEqual(root_sid, "A")

  def test_get_num_descendants_cyclic_spans(self):
    """Verifies that cyclic span relationships do not cause infinite loops."""
    df = pd.DataFrame({
        "trace_id": ["t1", "t1"],
        "span_id": ["A", "B"],
        "parent_rpc_span_id": ["B", "A"],
        "is_true_root": [False, False],
    })
    result_df = df_utils._get_num_descendants(df)
    # Both A and B are in a 2-cycle, so each has 1 descendant (the other node)
    self.assertEqual(result_df[df_utils.constants.NUM_DESCENDANTS].iloc[0], 1)
    self.assertEqual(result_df[df_utils.constants.NUM_DESCENDANTS].iloc[1], 1)

  def test_get_percentile_span_ids_empty(self):
    """Verifies that an empty dataframe returns an empty list without IndexError."""
    empty_df = pd.DataFrame(columns=[
        df_utils.constants.TRACE_ID,
        df_utils.constants.SPAN_ID,
        df_utils.constants.PARENT_RPC_SPAN_ID,
        df_utils.constants.METHOD_NAME,
        df_utils.constants.CLIENT_START_TIMESTAMP,
        df_utils.constants.CLIENT_FINISH_TIMESTAMP,
        df_utils.constants.IS_TRUE_ROOT,
        df_utils.constants.NUM_DESCENDANTS,
    ])
    spans = df_utils.get_percentile_span_ids(empty_df, 0, 100)
    self.assertEqual(spans, [])

  def test_get_percentile_span_ids_zero_end(self):
    """Verifies percentile_end=0 selects minimum duration instead of wrapping to maximum."""
    df = pd.DataFrame({
        df_utils.constants.TRACE_ID: ["t1", "t2", "t3"],
        df_utils.constants.SPAN_ID: ["s1", "s2", "s3"],
        df_utils.constants.PARENT_RPC_SPAN_ID: ["0", "0", "0"],
        df_utils.constants.METHOD_NAME: ["m1", "m1", "m1"],
        df_utils.constants.CLIENT_START_TIMESTAMP: [0.0, 0.0, 0.0],
        df_utils.constants.CLIENT_FINISH_TIMESTAMP: [10.0, 20.0, 30.0],
        df_utils.constants.IS_TRUE_ROOT: [True, True, True],
        df_utils.constants.NUM_DESCENDANTS: [0, 0, 0],
    })
    spans = df_utils.get_percentile_span_ids(df, 0, 0)
    self.assertEqual(spans, ["s1"])

  def test_get_percentile_span_ids_equal_percentiles(self):
    """Verifies percentile_start == percentile_end returns spans at that percentile."""
    df = pd.DataFrame({
        df_utils.constants.TRACE_ID: ["t1", "t2", "t3"],
        df_utils.constants.SPAN_ID: ["s1", "s2", "s3"],
        df_utils.constants.PARENT_RPC_SPAN_ID: ["0", "0", "0"],
        df_utils.constants.METHOD_NAME: ["m1", "m1", "m1"],
        df_utils.constants.CLIENT_START_TIMESTAMP: [0.0, 0.0, 0.0],
        df_utils.constants.CLIENT_FINISH_TIMESTAMP: [10.0, 20.0, 30.0],
        df_utils.constants.IS_TRUE_ROOT: [True, True, True],
        df_utils.constants.NUM_DESCENDANTS: [0, 0, 0],
    })
    spans = df_utils.get_percentile_span_ids(df, 50, 50)
    self.assertEqual(spans, ["s2"])

  def test_get_percentile_span_ids_single_item(self):
    """Verifies single-item dataframe returns the item without index wrapping."""
    df = pd.DataFrame({
        df_utils.constants.TRACE_ID: ["t1"],
        df_utils.constants.SPAN_ID: ["s1"],
        df_utils.constants.PARENT_RPC_SPAN_ID: ["0"],
        df_utils.constants.METHOD_NAME: ["m1"],
        df_utils.constants.CLIENT_START_TIMESTAMP: [0.0],
        df_utils.constants.CLIENT_FINISH_TIMESTAMP: [10.0],
        df_utils.constants.IS_TRUE_ROOT: [True],
        df_utils.constants.NUM_DESCENDANTS: [0],
    })
    spans = df_utils.get_percentile_span_ids(df, 0, 50)
    self.assertEqual(spans, ["s1"])

  def test_get_percentile_span_ids_inverted(self):
    """Verifies inverted percentiles clamp end_idx to start_idx safely."""
    df = pd.DataFrame({
        df_utils.constants.TRACE_ID: ["t1", "t2", "t3"],
        df_utils.constants.SPAN_ID: ["s1", "s2", "s3"],
        df_utils.constants.PARENT_RPC_SPAN_ID: ["0", "0", "0"],
        df_utils.constants.METHOD_NAME: ["m1", "m1", "m1"],
        df_utils.constants.CLIENT_START_TIMESTAMP: [0.0, 0.0, 0.0],
        df_utils.constants.CLIENT_FINISH_TIMESTAMP: [10.0, 20.0, 30.0],
        df_utils.constants.IS_TRUE_ROOT: [True, True, True],
        df_utils.constants.NUM_DESCENDANTS: [0, 0, 0],
    })
    spans = df_utils.get_percentile_span_ids(df, 90, 10)
    self.assertEqual(spans, ["s3"])

  def test_drop_duplicates_across_traces(self):
    """Verifies spans with identical span_id across different traces are preserved."""
    jaeger_json = {
        "data": [
            {
                "traceID": "trace_1",
                "processes": {"p1": {"serviceName": "service_A"}},
                "spans": [{
                    "traceID": "trace_1",
                    "spanID": "1",
                    "operationName": "op_A",
                    "startTime": 1000000,
                    "duration": 2000000,
                    "processID": "p1",
                    "references": [],
                }],
            },
            {
                "traceID": "trace_2",
                "processes": {"p1": {"serviceName": "service_A"}},
                "spans": [{
                    "traceID": "trace_2",
                    "spanID": "1",
                    "operationName": "op_A",
                    "startTime": 1000000,
                    "duration": 3000000,
                    "processID": "p1",
                    "references": [],
                }],
            },
        ]
    }
    df = df_utils.get_df_from_jaeger_json(jaeger_json)
    self.assertEqual(len(df), 2)
    self.assertEqual(df[df_utils.constants.TRACE_ID].nunique(), 2)


if __name__ == "__main__":
  unittest.main()


