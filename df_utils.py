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

"""Utility functions for preprocessing and filtering the dataframes."""

import functools
from typing import Any, Dict, List, Optional, Set

import networkx as nx
import pandas as pd

import constants


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
  """Renames the columns of the dataframe if they are present.

  The renamed columns are found in Jaeger traces. The columns are:
  - spanID -> span_id
  - traceID -> trace_id
  - operationName -> server_job
  - processID -> method_name

  Args:
    df: The dataframe to rename the columns of.

  Returns:
    The dataframe with the renamed columns.
  """
  rename_map = {}
  if constants.JAEGER_SPAN_ID in df.columns:
    rename_map[constants.JAEGER_SPAN_ID] = constants.SPAN_ID
  if constants.JAEGER_TRACE_ID in df.columns:
    rename_map[constants.JAEGER_TRACE_ID] = constants.TRACE_ID
  if constants.JAEGER_OPERATION_NAME in df.columns:
    rename_map[constants.JAEGER_OPERATION_NAME] = constants.SERVER_JOB
  if constants.JAEGER_PROCESS_ID in df.columns:
    rename_map[constants.JAEGER_PROCESS_ID] = constants.METHOD_NAME
  if constants.JAEGER_METHOD in df.columns:
    rename_map[constants.JAEGER_METHOD] = constants.METHOD_NAME
  if constants.JAEGER_SERVER_FINISH_TIME in df.columns:
    rename_map[constants.JAEGER_SERVER_FINISH_TIME] = (
        constants.SERVER_FINISH_TIMESTAMP
    )
  if constants.JAEGER_SERVER_START_TIME in df.columns:
    rename_map[constants.JAEGER_SERVER_START_TIME] = (
        constants.SERVER_START_TIMESTAMP
    )
  if constants.JAEGER_CLIENT_FINISH_TIME in df.columns:
    rename_map[constants.JAEGER_CLIENT_FINISH_TIME] = (
        constants.CLIENT_FINISH_TIMESTAMP
    )
  if constants.JAEGER_CLIENT_START_TIME in df.columns:
    rename_map[constants.JAEGER_CLIENT_START_TIME] = (
        constants.CLIENT_START_TIMESTAMP
    )
  if (
      constants.JAEGER_PARENT_SPAN_ID in df.columns
      and constants.PARENT_RPC_SPAN_ID not in df.columns
  ):
    rename_map[constants.JAEGER_PARENT_SPAN_ID] = constants.PARENT_RPC_SPAN_ID
  if rename_map:
    df = df.rename(columns=rename_map)
  return df


def _select_columns(df: pd.DataFrame) -> pd.DataFrame:
  """Selects the columns from the dataframe that are needed for analysis.

  If some of the columns are missing, we will add them. Keep the
  OPTIONAL_COLUMNS if they are present.

  Args:
    df: The dataframe to select the columns from.

  Returns:
    The dataframe with the selected columns.
  """
  columns_to_keep = set(constants.RAW_COLUMNS) | set(constants.OPTIONAL_COLUMNS)
  return df[[col for col in df.columns if col in columns_to_keep]]


def _add_missing_columns(df: pd.DataFrame) -> pd.DataFrame:
  """Adds missing columns to the dataframe."""
  df_copy = df.copy()
  for col in constants.RAW_COLUMNS:
    if col not in df_copy.columns:
      if col == constants.IS_TRUE_ROOT:
        df_copy[col] = False
      elif col in (
          constants.CLIENT_USER,
          constants.CLIENT_JOB,
          constants.SERVER_USER,
          constants.SERVER_JOB,
          constants.METHOD_NAME,
      ):
        df_copy[col] = ''
      elif col == constants.PARENT_RPC_SPAN_ID:
        df_copy[col] = '0'
      else:
        df_copy[col] = 0
  return df_copy


def _drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
  """Drops duplicate rows in the dataframe."""
  subset = [constants.SPAN_ID]
  if constants.TRACE_ID in df.columns:
    subset = [constants.TRACE_ID, constants.SPAN_ID]
  return df.drop_duplicates(subset=subset, keep='first')


def _strip_starting_slashes(df: pd.DataFrame) -> pd.DataFrame:
  """Strips starting slashes from the method name."""
  df = df.copy()
  df[constants.METHOD_NAME] = df[constants.METHOD_NAME].str.lstrip('/')
  return df


def _mark_root_rows(df: pd.DataFrame) -> pd.DataFrame:
  """Marks the root rows for each trace_id in a DataFrame as True in the 'is_true_root' column.

  Args:
    df: The DataFrame to modify.

  Returns:
    The DataFrame with the 'is_true_root' column populated.
  """
  df = df.copy()
  if constants.IS_TRUE_ROOT not in df.columns:
    df[constants.IS_TRUE_ROOT] = False

  if constants.REFERENCES in df.columns:
    df.loc[
        df[constants.REFERENCES].apply(
            lambda x: len(x) < 1 if isinstance(x, (list, tuple)) else False
        ),
        constants.IS_TRUE_ROOT,
    ] = True
  if constants.PARENT_RPC_SPAN_ID in df.columns:
    df.loc[
        (df[constants.PARENT_RPC_SPAN_ID] == 0)
        | (df[constants.PARENT_RPC_SPAN_ID] == '0')
        | (df[constants.PARENT_RPC_SPAN_ID].isna()),
        constants.IS_TRUE_ROOT,
    ] = True
  return df


def _extract_parent_span_id_from_references(references: Any) -> Any:
  """Extracts parent span ID from Jaeger span references.

  Args:
    references: The references list or value from a trace span.

  Returns:
    The parent span ID if present, otherwise 0.
  """
  if (
      references
      and isinstance(references, list)
      and references[0]
      and isinstance(references[0], dict)
      and constants.JAEGER_SPAN_ID in references[0]
  ):
    return references[0][constants.JAEGER_SPAN_ID]
  return 0


def _populate_parent_rpc_span_id(df: pd.DataFrame) -> pd.DataFrame:
  """Populates the parent_rpc_span_id column based on the references column.

  Args:
    df: The input DataFrame.

  Returns:
    The DataFrame with the parent_rpc_span_id column populated.
  """
  if constants.REFERENCES in df.columns:
    df[constants.PARENT_RPC_SPAN_ID] = df[constants.REFERENCES].apply(
        _extract_parent_span_id_from_references
    )
  return df


def _set_timestamps(df: pd.DataFrame) -> pd.DataFrame:
  """Sets the client_start_timestamp and client_finish_timestamp to startTime and startTime + duration.

  Args:
    df: The input DataFrame.

  Returns:
    The DataFrame with timestamp columns set.
  """
  if constants.JAEGER_START_TIME in df.columns:
    start_time_seconds = df[constants.JAEGER_START_TIME] / 1000000.0
    duration_seconds = df[constants.JAEGER_DURATION] / 1000000.0
    df[constants.CLIENT_START_TIMESTAMP] = start_time_seconds
    df[constants.CLIENT_FINISH_TIMESTAMP] = (
        start_time_seconds + duration_seconds
    )
    df[constants.SERVER_START_TIMESTAMP] = start_time_seconds
    df[constants.SERVER_FINISH_TIMESTAMP] = (
        start_time_seconds + duration_seconds
    )
    df[constants.REQUEST_NETWORK_DELTA] = 0
    df[constants.RESPONSE_NETWORK_DELTA] = 0
    df[constants.CLIENT_SEND_QUEUE_DELTA] = 0
    df[constants.SERVER_SEND_QUEUE_DELTA] = 0
    df[constants.CLIENT_RECV_QUEUE_DELTA] = 0
    df[constants.SERVER_RECV_QUEUE_DELTA] = 0
    df[constants.SERVER_APP_DELTA] = duration_seconds
  return df


def _get_num_descendants(df: pd.DataFrame) -> pd.DataFrame:
  """Get number of descendants using a graph representation.

  Args:
    df: The input DataFrame with 'span_id' and 'parent_rpc_span_id' columns. It
      is assumed that the DataFrame also has a boolean column 'is_true_root'.

  Returns:
      The DataFrame with the 'num_descendants' column populated.
  """
  if (
      constants.NUM_DESCENDANTS in df.columns
      and df[constants.NUM_DESCENDANTS].notna().all()
  ):
    return df

  graph: nx.DiGraph[Any] = nx.DiGraph()
  graph.add_nodes_from(df[constants.SPAN_ID])

  edges_df = df[
      df[constants.PARENT_RPC_SPAN_ID].notna()
      & (df[constants.PARENT_RPC_SPAN_ID] != 0)
      & (df[constants.PARENT_RPC_SPAN_ID] != '0')
  ]
  graph.add_edges_from(
      edges_df[[constants.PARENT_RPC_SPAN_ID, constants.SPAN_ID]].values
  )

  descendant_counts = {}
  for node in graph.nodes():
    descendants = nx.descendants(graph, node)
    descendant_counts[node] = len(descendants)

  df[constants.NUM_DESCENDANTS] = (
      df[constants.SPAN_ID].map(descendant_counts).fillna(0)
  )
  return df


def _rename_processes(
    df: pd.DataFrame,
    trace_id_to_process_dict: Optional[
        Dict[str, Dict[str, Dict[str, str]]]
    ] = None,
) -> pd.DataFrame:
  """Renames method_name in the DataFrame based on the trace_id_to_process_dict.

  Args:
    df: The DataFrame to modify.
    trace_id_to_process_dict: A dictionary mapping trace ids to process names.

  Returns:
    A new DataFrame with renamed method_names.
  """
  if not trace_id_to_process_dict:
    return df

  df[constants.METHOD_NAME] = df.apply(
      _resolve_jaeger_method_name,
      trace_id_to_process_dict=trace_id_to_process_dict,
      axis=1,
  )
  return df


def _resolve_jaeger_method_name(
    row: pd.Series,
    trace_id_to_process_dict: Dict[str, Dict[str, Dict[str, str]]],
) -> str:
  """Resolves the Jaeger service name to use as method_name for a row.

  Args:
    row: A pandas Series representing a trace span row.
    trace_id_to_process_dict: A dictionary mapping trace ids to process names.

  Returns:
    The resolved method/service name string.
  """
  trace_id = row[constants.TRACE_ID]
  if trace_id in trace_id_to_process_dict:
    old_name = row[constants.METHOD_NAME]
    return trace_id_to_process_dict[trace_id][old_name][
        constants.JAEGER_SERVICE_NAME
    ]
  print(f'trace_id {trace_id} not in trace_id_to_process_dict')
  return row[constants.METHOD_NAME]


_rename_methods = _rename_processes


def _rename_incorrect_methods(df: pd.DataFrame) -> pd.DataFrame:
  """Renames incorrect method names in the DataFrame.

  For DeathStarBench traces, the method names are incorrect since they are
  always implemented by the client. For example, all compose-review-service
  spans, including the memcached and mongodb spans, have the method name
  compose-review-service. This function renames these spans to the correct
  method name.

  Args:
    df: The DataFrame to modify.

  Returns:
    A new DataFrame with renamed method names.
  """
  for job_str, suffix in [
      (constants.MONGO, constants.SUFFIX_MONGODB),
      (constants.MMC, constants.SUFFIX_MEMCACHED),
      (constants.REDIS, constants.SUFFIX_REDIS),
  ]:
    mask = df[constants.SERVER_JOB].str.contains(job_str)
    df.loc[mask, constants.METHOD_NAME] = df.loc[
        mask, constants.METHOD_NAME
    ].str.replace(constants.SERVICE_SUFFIX, suffix)
  return df


def _remove_server_job_periods(df: pd.DataFrame) -> pd.DataFrame:
  """Removes periods from the server_job column in the DataFrame.

  Args:
    df: The DataFrame to modify.

  Returns:
    A new DataFrame with the server_job column without periods.
  """
  df[constants.SERVER_JOB] = df[constants.SERVER_JOB].str.replace('.', '', regex=False)
  return df


def _unify_jaeger_names(df: pd.DataFrame) -> pd.DataFrame:
  """Unifies Jaeger method_name and server_job to match standard layout.

  Args:
    df: The input DataFrame.

  Returns:
    A new DataFrame with unified Jaeger names.
  """
  df = df.copy()
  service = df[constants.METHOD_NAME].copy()
  method = df[constants.SERVER_JOB].copy()
  df[constants.METHOD_NAME] = service + '.' + method
  df[constants.SERVER_JOB] = service
  return df


def get_rtt_time_for_df(df: pd.DataFrame) -> pd.DataFrame:
  """Gets the round trip time for a given dataframe.

  Args:
    df: The dataframe to get the round trip time for.

  Returns:
    The dataframe with the rtt_time column populated.
  """
  sum_of_components = (
      df[constants.REQUEST_NETWORK_DELTA]
      + df[constants.RESPONSE_NETWORK_DELTA]
      + df[constants.CLIENT_SEND_QUEUE_DELTA]
      + df[constants.SERVER_SEND_QUEUE_DELTA]
      + df[constants.CLIENT_RECV_QUEUE_DELTA]
      + df[constants.SERVER_RECV_QUEUE_DELTA]
      + df[constants.SERVER_APP_DELTA]
  )

  client_delta = (
      df[constants.CLIENT_FINISH_TIMESTAMP]
      - df[constants.CLIENT_START_TIMESTAMP]
  )
  df[constants.RTT_TIME] = sum_of_components.fillna(0).combine(
      client_delta.fillna(0), max
  )

  return df


def validate_raw_dataframe(df: pd.DataFrame, is_jaeger: bool) -> None:
  """Validates that a raw trace dataframe has all required fields and they are valid.

  Args:
    df: The raw trace DataFrame.
    is_jaeger: Whether the DataFrame is from Jaeger format.
  """
  if is_jaeger:
    required_jaeger = [
        constants.JAEGER_TRACE_ID,
        constants.JAEGER_SPAN_ID,
        constants.JAEGER_START_TIME,
        constants.JAEGER_DURATION,
    ]
    for col in required_jaeger:
      if col not in df.columns:
        raise ValueError(f'Required Jaeger column missing: {col}')
  else:
    required_cols = [
        constants.TRACE_ID,
        constants.SPAN_ID,
        constants.METHOD_NAME,
        constants.SERVER_JOB,
        constants.SERVER_APP_DELTA,
        constants.REQUEST_NETWORK_DELTA,
        constants.RESPONSE_NETWORK_DELTA,
        constants.CLIENT_SEND_QUEUE_DELTA,
        constants.SERVER_SEND_QUEUE_DELTA,
        constants.CLIENT_RECV_QUEUE_DELTA,
        constants.SERVER_RECV_QUEUE_DELTA,
        constants.CLIENT_START_TIMESTAMP,
        constants.CLIENT_FINISH_TIMESTAMP,
    ]
    numeric_cols = [
        constants.SERVER_APP_DELTA,
        constants.REQUEST_NETWORK_DELTA,
        constants.RESPONSE_NETWORK_DELTA,
        constants.CLIENT_SEND_QUEUE_DELTA,
        constants.SERVER_SEND_QUEUE_DELTA,
        constants.CLIENT_RECV_QUEUE_DELTA,
        constants.SERVER_RECV_QUEUE_DELTA,
        constants.CLIENT_START_TIMESTAMP,
        constants.CLIENT_FINISH_TIMESTAMP,
    ]

    for col in required_cols:
      if col not in df.columns:
        raise ValueError(f'Required column missing: {col}')
      if (
          not df.empty
          and col in numeric_cols
          and not pd.api.types.is_numeric_dtype(df[col])
      ):
        raise ValueError(f'Column {col} must be numeric type')


def _drop_traces_with_nulls(
    df: pd.DataFrame, is_jaeger_trace: bool = False
) -> pd.DataFrame:
  """Drops entire traces if any span contains a null in required columns.

  Args:
    df: The input DataFrame.
    is_jaeger_trace: Whether the DataFrame is from a Jaeger trace.

  Returns:
    A DataFrame with corrupted traces completely removed.
  """
  if df.empty:
    return df.copy()

  if is_jaeger_trace:
    trace_id_col = (
        constants.JAEGER_TRACE_ID
        if constants.JAEGER_TRACE_ID in df.columns
        else constants.TRACE_ID
    )
    candidate_cols = [
        constants.JAEGER_TRACE_ID,
        constants.JAEGER_SPAN_ID,
        constants.JAEGER_START_TIME,
        constants.JAEGER_DURATION,
        constants.JAEGER_OPERATION_NAME,
        constants.JAEGER_PROCESS_ID,
        constants.JAEGER_METHOD,
    ]
  else:
    trace_id_col = constants.TRACE_ID
    candidate_cols = [
        constants.TRACE_ID,
        constants.SPAN_ID,
        constants.METHOD_NAME,
        constants.SERVER_JOB,
        constants.CLIENT_START_TIMESTAMP,
        constants.CLIENT_FINISH_TIMESTAMP,
        constants.SERVER_APP_DELTA,
        constants.REQUEST_NETWORK_DELTA,
        constants.RESPONSE_NETWORK_DELTA,
        constants.CLIENT_SEND_QUEUE_DELTA,
        constants.SERVER_SEND_QUEUE_DELTA,
        constants.CLIENT_RECV_QUEUE_DELTA,
        constants.SERVER_RECV_QUEUE_DELTA,
    ]

  cols_to_check = [col for col in candidate_cols if col in df.columns]
  if not cols_to_check or trace_id_col not in df.columns:
    return df.copy()

  null_mask = df[cols_to_check].isna().any(axis=1)
  corrupted_trace_ids = set(df.loc[null_mask, trace_id_col].dropna().unique())

  valid_mask = df[trace_id_col].notna() & (
      ~df[trace_id_col].isin(corrupted_trace_ids)
  )
  return df[valid_mask].copy()


def preprocess(
    df: pd.DataFrame,
    is_jaeger_trace: bool = False,
    trace_id_to_process_dict: Optional[
        Dict[str, Dict[str, Dict[str, str]]]
    ] = None,
    is_raw: bool = True,
) -> pd.DataFrame:
  """Preprocesses the dataframe.

  Args:
    df: The dataframe to preprocess.
    is_jaeger_trace: Whether the dataframe is from a Jaeger trace.
    trace_id_to_process_dict: A dictionary mapping trace ids to process names.
    is_raw: Whether the dataframe is a raw input (requires validation).

  Returns:
    The preprocessed dataframe.
  """
  if trace_id_to_process_dict is not None:
    is_jaeger_trace = True
  elif constants.JAEGER_SPAN_ID in df.columns and constants.SPAN_ID not in df.columns:
    is_jaeger_trace = True

  df = _drop_traces_with_nulls(df, is_jaeger_trace=is_jaeger_trace)
  if is_raw:
    validate_raw_dataframe(df, is_jaeger_trace)

  transformations: List[Any] = []
  if is_jaeger_trace:
    if trace_id_to_process_dict is None:
      raise ValueError(
          'trace_id_to_process_dict must be provided for Jaeger traces.'
      )

    transformations = [
        _rename_columns,
        _populate_parent_rpc_span_id,
        _add_missing_columns,
        _mark_root_rows,
        _set_timestamps,
        _get_num_descendants,
        functools.partial(
            _rename_processes,
            trace_id_to_process_dict=trace_id_to_process_dict,
        ),
        _rename_incorrect_methods,
        _remove_server_job_periods,
        _unify_jaeger_names,
        _drop_duplicates,
        _strip_starting_slashes,
        _select_columns,
        get_rtt_time_for_df,
    ]
  else:
    transformations = [
        _rename_columns,
        _add_missing_columns,
        _mark_root_rows,
        _get_num_descendants,
        _drop_duplicates,
        _strip_starting_slashes,
        _select_columns,
        get_rtt_time_for_df,
    ]

  for f in transformations:
    df = f(df)
  return df


def get_df_from_jaeger_json(data_json: Dict[str, Any]) -> pd.DataFrame:
  """Gets a dataframe from a Jaeger json file.

  Args:
    data_json: The json file from Jaeger.

  Returns:
    The dataframe from the Jaeger json file.
  """
  entries: List[Dict[str, Any]] = data_json[constants.JAEGER_DATA]
  trace_id_to_process_dict: Dict[str, Dict[str, Dict[str, str]]] = {}
  new_data: List[Dict[str, Any]] = []
  for entry in entries:
    for span in entry[constants.JAEGER_SPANS]:
      new_data.append(span)
    trace_id = entry[constants.JAEGER_TRACE_ID]
    trace_id_to_process_dict[trace_id] = entry[constants.JAEGER_PROCESSES]
  df = pd.DataFrame(new_data)
  return preprocess(
      df,
      is_jaeger_trace=True,
      trace_id_to_process_dict=trace_id_to_process_dict,
  )


def get_all_root_methods(df: pd.DataFrame) -> Set[str]:
  """Gets the root nodes in the dataframe.

  Root nodes are found by finding the span with the greatest number of
  descendants.

  Args:
    df: The dataframe to get the root methods from.

  Returns:
    A set of root method names.
  """
  root_methods = set()
  for _, group in df.groupby(constants.TRACE_ID):
    root_span_id = get_root_span_id(group)
    root_methods.add(
        group[group[constants.SPAN_ID] == root_span_id][
            constants.METHOD_NAME
        ].iloc[0]
    )
  return root_methods


def filter_df(
    df: pd.DataFrame,
    by_column: str,
    by_column_value: str,
    include_whole_trace: bool = True,
) -> pd.DataFrame:
  """Filters a dataframe by a column and value.

  Args:
    df: The dataframe to filter.
    by_column: The column to filter by.
    by_column_value: The value to filter by.
    include_whole_trace: Whether to include the whole trace or just the rows
      that have the value in the column.

  Returns:
    The filtered dataframe.
  """
  if by_column not in df.columns:
    raise ValueError(f'Column {by_column} not in dataframe.')
  if by_column_value not in df[by_column].unique():
    raise ValueError(f'Value {by_column_value} not in column {by_column}.')
  if not include_whole_trace:
    return df[df[by_column] == by_column_value]
  trace_ids = set(
      row[constants.TRACE_ID]
      for _, row in df.iterrows()
      if row[by_column] == by_column_value
  )
  return df[df[constants.TRACE_ID].isin(trace_ids)]


def get_root_span_id(df: pd.DataFrame) -> str:
  """Gets the root span id for a df by finding the true root or the span with the most descendants."""
  if len(set(df[constants.TRACE_ID])) != 1:
    raise ValueError('The dataframe must contain only one trace id.')

  if constants.IS_TRUE_ROOT in df.columns:
    true_roots = df[df[constants.IS_TRUE_ROOT]]
    if not true_roots.empty:
      return true_roots.iloc[0][constants.SPAN_ID]

  potential_roots = []
  for _, row in df.iterrows():
    num_desc = (
        row[constants.NUM_DESCENDANTS]
        if pd.notna(row[constants.NUM_DESCENDANTS])
        else 0
    )
    potential_roots.append((row[constants.SPAN_ID], num_desc))
  potential_roots.sort(key=lambda x: x[1], reverse=True)
  return potential_roots[0][0]


def get_percentile_span_ids(
    df: pd.DataFrame,
    percentile_start: float,
    percentile_end: float = 100,
    by_method: str = '',
) -> List[str]:
  """Gets the span_ids for a given percentile range for a dataframe.

  Args:
    df: The dataframe to get the span ids from.
    percentile_start: The start of the percentile range.
    percentile_end: The end of the percentile range.
    by_method: The method to get the percentile range for. If empty, then we
      will get the percentile range for the root method.

  Returns:
    A list of span ids.
  """
  if percentile_start < 0 or percentile_start > 100:
    raise ValueError('Percentile start must be between 0 and 100.')
  if percentile_end < 0 or percentile_end > 100:
    raise ValueError('Percentile end must be between 0 and 100.')
  if by_method and by_method not in df[constants.METHOD_NAME].unique():
    raise ValueError(f'Method {by_method} not in dataframe.')

  span_duration_pairs = []
  for _, group in df.groupby(constants.TRACE_ID):
    if not by_method:
      root_span_id = get_root_span_id(group)
      row = group[group[constants.SPAN_ID] == root_span_id].iloc[0]
      span_duration_pairs.append((
          row[constants.SPAN_ID],
          row[constants.CLIENT_FINISH_TIMESTAMP]
          - row[constants.CLIENT_START_TIMESTAMP],
      ))
    else:
      for _, row in group.iterrows():
        if row[constants.METHOD_NAME] == by_method:
          span_duration_pairs.append((
              row[constants.SPAN_ID],
              row[constants.CLIENT_FINISH_TIMESTAMP]
              - row[constants.CLIENT_START_TIMESTAMP],
          ))
  if not span_duration_pairs:
    return []

  span_duration_pairs = sorted(span_duration_pairs, key=lambda x: x[1])
  n = len(span_duration_pairs)
  start_idx = max(0, min(int(n * percentile_start / 100), n - 1))
  raw_end = int(n * percentile_end / 100) - 1 if percentile_end > 0 else 0
  end_idx = max(start_idx, min(max(0, raw_end), n - 1))
  percentile_start_value = span_duration_pairs[start_idx][1]
  percentile_end_value = span_duration_pairs[end_idx][1]

  spans = []
  for span, duration in span_duration_pairs:
    if duration >= percentile_start_value and duration <= percentile_end_value:
      spans.append(span)
  return spans

