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

import immutabledict
import pandas as pd
import pytest
import df_utils
import constants

_FAST_DF_DICT = immutabledict.immutabledict({
    constants.JAEGER_TRACE_ID: ["t1", "t1", "t1"],
    constants.JAEGER_SPAN_ID: ["s1", "s2", "s3"],
    constants.PARENT_SPAN_ID: [None, "s1", "s2"],
    constants.JAEGER_PROCESS_ID: ["A", "B", "C"],
    constants.JAEGER_OPERATION_NAME: ["opA", "opB", "opC"],
    constants.JAEGER_START_TIME: [0.0, 20.0, 30.0],
    constants.JAEGER_DURATION: [100.0, 60.0, 40.0],
    constants.NUM_DESCENDANTS: [2, 1, 0],
    "bad_column": [69, 420, 690],
})

_NOMINAL_DF_DICT = immutabledict.immutabledict({
    constants.JAEGER_TRACE_ID: ["t2", "t2", "t2"],
    constants.JAEGER_SPAN_ID: ["s4", "s5", "s6"],
    constants.PARENT_SPAN_ID: [None, "s4", "s5"],
    constants.JAEGER_PROCESS_ID: ["A", "B", "C"],
    constants.JAEGER_OPERATION_NAME: ["opA", "opB", "opC"],
    constants.JAEGER_START_TIME: [0.0, 20.0, 30.0],
    constants.JAEGER_DURATION: [200.0, 60.0, 40.0],
    constants.NUM_DESCENDANTS: [2, 1, 0],
    "bad_column": [69, 420, 690],
})

_SLOW_DF_DICT = immutabledict.immutabledict({
    constants.JAEGER_TRACE_ID: ["t3", "t3", "t3"],
    constants.JAEGER_SPAN_ID: ["s7", "s8", "s9"],
    constants.PARENT_SPAN_ID: [None, "s7", "s8"],
    constants.JAEGER_PROCESS_ID: ["A", "B", "C"],
    constants.JAEGER_OPERATION_NAME: ["opA", "opB", "opC"],
    constants.JAEGER_START_TIME: [0.0, 20.0, 30.0],
    constants.JAEGER_DURATION: [300.0, 60.0, 40.0],
    constants.NUM_DESCENDANTS: [2, 1, 0],
    "bad_column": [69, 420, 690],
})

_INCOMPLETE_DF_DICT = immutabledict.immutabledict({
    constants.JAEGER_TRACE_ID: ["t4", "t4", "t5"],
    constants.JAEGER_SPAN_ID: ["s10", "s11", "s12"],
    constants.PARENT_SPAN_ID: [None, "s10", None],
    constants.JAEGER_PROCESS_ID: ["stuff", "more_stuff", "even_more_stuff"],
    "references": [[], [{"spanID": "s10"}], []],
})

@pytest.fixture
def fast_df():
    return pd.DataFrame(dict(_FAST_DF_DICT))

@pytest.fixture
def nominal_df():
    return pd.DataFrame(dict(_NOMINAL_DF_DICT))

@pytest.fixture
def slow_df():
    return pd.DataFrame(dict(_SLOW_DF_DICT))

@pytest.fixture
def all_df(fast_df, nominal_df, slow_df):
    return pd.concat([fast_df, nominal_df, slow_df], ignore_index=True)

@pytest.fixture
def incomplete_df():
    return pd.DataFrame(dict(_INCOMPLETE_DF_DICT))

def test_get_all_root_methods(fast_df, all_df):
    root_methods_fast = df_utils.get_all_root_methods(df=fast_df)
    assert root_methods_fast == {"A"}
    root_methods_all = df_utils.get_all_root_methods(df=all_df)
    assert root_methods_all == {"A"}

def test_get_percentile_span_ids(fast_df, all_df):
    span_ids_fast = df_utils.get_percentile_span_ids(
        df=fast_df, percentile_start=0, percentile_end=100
    )
    assert span_ids_fast == ["s1"]
    span_ids_all = df_utils.get_percentile_span_ids(
        df=all_df, percentile_start=0, percentile_end=100
    )
    # durations: 100, 200, 300. spanIDs: s1, s4, s7.
    assert span_ids_all == ["s1", "s4", "s7"]

def test_filter_df(all_df):
    df = df_utils.filter_df(
        df=all_df,
        by_column=constants.JAEGER_PROCESS_ID,
        by_column_value="A",
        include_whole_trace=False,
    )
    assert df.shape[0] == 3
    assert df[constants.JAEGER_PROCESS_ID].iloc[0] == "A"
    assert df[constants.JAEGER_PROCESS_ID].iloc[1] == "A"
    assert df[constants.JAEGER_PROCESS_ID].iloc[2] == "A"

def test_preprocess_df(all_df):
    df = df_utils.preprocess(df=all_df)
    # Total rows = 9
    assert df.shape[0] == 9
    assert "bad_column" not in df.columns
    assert df[constants.JAEGER_TRACE_ID].nunique() == 3
    assert df[constants.JAEGER_PROCESS_ID].iloc[0] == "A"

def test_preprocess_df_with_references(incomplete_df):
    df = df_utils.preprocess(df=incomplete_df)
    assert constants.PARENT_SPAN_ID in df.columns
    # Check if parentSpanID was populated from references for s11
    assert df[df[constants.JAEGER_SPAN_ID] == "s11"][constants.PARENT_SPAN_ID].iloc[0] == "s10"
