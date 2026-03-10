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

"""Utility functions for preprocessing and filtering the dataframes.

The dataframes are built from Jaeger traces.
"""

from typing import Any

import networkx as nx
import pandas as pd

import constants


def _select_columns(df: pd.DataFrame) -> pd.DataFrame:
  """Ensures core columns are present while preserving additional metadata."""
  return _add_missing_columns(df)


def _add_missing_columns(df: pd.DataFrame) -> pd.DataFrame:
  """Adds missing columns to the dataframe."""
  df_copy = df.copy()
  for col in constants.RAW_COLUMNS:
    if col not in df_copy.columns:
      df_copy[col] = pd.NA
  return df_copy


def _drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
  """Drops duplicate rows in the dataframe."""
  return df.drop_duplicates(subset=[constants.JAEGER_SPAN_ID], keep='first')


def _strip_starting_slashes(df: pd.DataFrame) -> pd.DataFrame:
  """Strips starting slashes from the operation name."""
  df = df.copy()
  if constants.JAEGER_OPERATION_NAME in df.columns:
    df[constants.JAEGER_OPERATION_NAME] = df[
        constants.JAEGER_OPERATION_NAME
    ].str.lstrip('/')
  return df


def _populate_parent_rpc_span_id(df: pd.DataFrame) -> pd.DataFrame:
  """Populates the parentSpanID column based on the references column.

  Args:
    df: The input DataFrame.

  Returns:
    The DataFrame with the parentSpanID column populated.
  """

  def _extract_parent_span_id(references):
    if (
        references
        and isinstance(references, list)
        and references[0]
        and isinstance(references[0], dict)
        and constants.JAEGER_SPAN_ID in references[0]
    ):
      return references[0][constants.JAEGER_SPAN_ID]
    else:
      return None

  df[constants.PARENT_SPAN_ID] = df[constants.REFERENCES].apply(
      _extract_parent_span_id
  )
  return df


def _get_num_descendants(df: pd.DataFrame) -> pd.DataFrame:
  """Get number of descendants using a graph representation.

  Args:
    df: The input DataFrame with 'spanID' and 'parentSpanID' columns.

  Returns:
      The DataFrame with the 'numDescendants' column populated.
  """
  if (
      constants.NUM_DESCENDANTS in df.columns
      and df[constants.NUM_DESCENDANTS].notna().all()
  ):
    return df

  graph = nx.DiGraph()

  # Add all nodes directly from the 'spanID' column
  graph.add_nodes_from(df[constants.JAEGER_SPAN_ID])

  # Create a DataFrame of edges by filtering out NaN parentSpanID values
  edges_df = df.dropna(subset=[constants.PARENT_SPAN_ID])
  graph.add_edges_from(
      edges_df[[constants.PARENT_SPAN_ID, constants.JAEGER_SPAN_ID]].values
  )

  descendant_counts = {}
  for node in graph.nodes():
    descendants = nx.descendants(graph, node)
    descendant_counts[node] = len(descendants)

  df[constants.NUM_DESCENDANTS] = (
      df[constants.JAEGER_SPAN_ID].map(descendant_counts).fillna(0)
  )
  return df


def _rename_processes(
    df: pd.DataFrame,
    trace_id_to_process_dict: dict[str, dict[str, dict[str, str]]],
) -> pd.DataFrame:
  """Renames processID in the DataFrame to service names.

  Args:
    df: The DataFrame to modify.
    trace_id_to_process_dict: A dictionary mapping trace ids to process details.

  Returns:
    A new DataFrame with processID renamed to service names.
  """

  def rename_method(row):
    trace_id = row[constants.JAEGER_TRACE_ID]
    if trace_id in trace_id_to_process_dict:
      process_id = row[constants.JAEGER_PROCESS_ID]
      if process_id in trace_id_to_process_dict[trace_id]:
        return trace_id_to_process_dict[trace_id][process_id][
            constants.JAEGER_SERVICE_NAME
        ]
      else:
        return process_id
    else:
      return row[constants.JAEGER_PROCESS_ID]

  df[constants.JAEGER_PROCESS_ID] = df.apply(rename_method, axis=1)
  return df


def _rename_incorrect_methods(df: pd.DataFrame) -> pd.DataFrame:
  """Renames incorrect method names in the DataFrame.

  For DeathStarBench traces, the process names are sometimes too generic.

  Args:
    df: The DataFrame to modify.

  Returns:
    A new DataFrame with renamed process names.
  """
  for job_str, suffix in [
      (constants.MONGO, constants.SUFFIX_MONGODB),
      (constants.MMC, constants.SUFFIX_MEMCACHED),
      (constants.REDIS, constants.SUFFIX_REDIS),
  ]:
    mask = df[constants.JAEGER_OPERATION_NAME].str.contains(job_str)
    df.loc[mask, constants.JAEGER_PROCESS_ID] = df.loc[
        mask, constants.JAEGER_PROCESS_ID
    ].str.replace(constants.SERVICE_SUFFIX, suffix)
  return df


def _remove_server_job_periods(df: pd.DataFrame) -> pd.DataFrame:
  """Removes periods from the operationName column in the DataFrame.

  Args:
    df: The DataFrame to modify.

  Returns:
    A new DataFrame with the operationName column without periods.
  """
  df[constants.JAEGER_OPERATION_NAME] = df[
      constants.JAEGER_OPERATION_NAME
  ].str.replace('.', '')
  return df


def preprocess(
    df: pd.DataFrame,
    trace_id_to_process_dict: (
        dict[str, dict[str, dict[str, str]]] | None
    ) = None,
) -> pd.DataFrame:
  """Preprocesses the dataframe.

  Args:
    df: The dataframe to preprocess.
    trace_id_to_process_dict: A dictionary mapping trace ids to process names.

  Returns:
    The preprocessed dataframe.
  """

  transformations = [
      _add_missing_columns,
      _populate_parent_rpc_span_id,
      _get_num_descendants,
      _rename_processes,
      _rename_incorrect_methods,
      _remove_server_job_periods,
      _drop_duplicates,
      _strip_starting_slashes,
      _select_columns,
  ]

  df.fillna(0)
  for f in transformations:
    if f is _rename_processes:
      if trace_id_to_process_dict:
        df = _rename_processes(df, trace_id_to_process_dict)
    else:
      df = f(df)
  return df


def get_df_from_jaeger_json(data_json: dict[str, Any]) -> pd.DataFrame:
  """Gets a dataframe from a Jaeger json file.

  Args:
    data_json: The json file from Jaeger.

  Returns:
    The dataframe from the Jaeger json file.
  """
  data_json = data_json[constants.JAEGER_DATA]
  trace_id_to_process_dict = {}
  new_data = []
  for entry in data_json:
    for span in entry[constants.JAEGER_SPANS]:
      new_data.append(span)
    trace_id = entry[constants.JAEGER_TRACE_ID]
    trace_id_to_process_dict[trace_id] = entry[constants.JAEGER_PROCESSES]
  df = pd.DataFrame(new_data)
  df = preprocess(
      df,
      trace_id_to_process_dict=trace_id_to_process_dict,
  )
  return df


def get_all_root_methods(df: pd.DataFrame) -> set[str]:
  """Gets the root nodes in the dataframe.

  Root nodes are found by finding the span with the greatest number of
  descendants.

  Args:
    df: The dataframe to get the root methods from.

  Returns:
    A set of root method names.
  """
  root_methods = set()
  for _, group in df.groupby(constants.JAEGER_TRACE_ID):
    root_span_id = get_root_span_id(group)
    root_methods.add(
        group[group[constants.JAEGER_SPAN_ID] == root_span_id][
            constants.JAEGER_PROCESS_ID
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
  # if we are not including the whole trace, we only want to include the rows
  # that have the value in the column
  if not include_whole_trace:
    return df[df[by_column] == by_column_value]
  # else, we need to find the trace ids that have the value in the column
  trace_ids = set(
      row[constants.JAEGER_TRACE_ID]
      for _, row in df.iterrows()
      if row[by_column] == by_column_value
  )
  return df[df[constants.JAEGER_TRACE_ID].isin(trace_ids)]


def get_root_span_id(df: pd.DataFrame) -> str:
  """Gets the root span id for a df by the span with the most descendants."""
  # if there are multiple traceids in the dataframe, return an error
  if len(set(df[constants.JAEGER_TRACE_ID])) != 1:
    raise ValueError('The dataframe must contain only one trace id.')
  potential_roots = []
  for _, row in df.iterrows():
    potential_roots.append(
        (row[constants.JAEGER_SPAN_ID], row[constants.NUM_DESCENDANTS])
    )
  potential_roots.sort(key=lambda x: x[1], reverse=True)
  # return the span id with the most descendants
  return potential_roots[0][0]


def get_percentile_span_ids(
    df: pd.DataFrame,
    percentile_start: float,
    percentile_end: float = 100,
    by_method: str = '',
) -> list[str]:
  """Gets the span_ids for a given percentile range for a dataframe.

  If no by_method name is supplied, then we will compute the percentile range
  for the root method, otherwise, we will compute the percentile range for the
  given method.

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
  if by_method and by_method not in df[constants.JAEGER_PROCESS_ID].unique():
    raise ValueError(f'Method {by_method} not in dataframe.')

  span_duration_pairs = []
  for _, group in df.groupby(constants.JAEGER_TRACE_ID):
    if not by_method:
      root_span_id = get_root_span_id(group)
      # find the first row with the exact span id and append to
      # span_duration_pairs
      row = group[group[constants.JAEGER_SPAN_ID] == root_span_id].iloc[0]
      span_duration_pairs.append((
          row[constants.JAEGER_SPAN_ID],
          row[constants.JAEGER_DURATION],
      ))
    else:
      for _, row in group.iterrows():
        if row[constants.JAEGER_PROCESS_ID] == by_method:
          span_duration_pairs.append((
              row[constants.JAEGER_SPAN_ID],
              row[constants.JAEGER_DURATION],
          ))
  span_duration_pairs = sorted(span_duration_pairs, key=lambda x: x[1])
  percentile_start_value = span_duration_pairs[
      int(len(span_duration_pairs) * percentile_start / 100)
  ][1]

  percentile_end_value = span_duration_pairs[
      int(len(span_duration_pairs) * percentile_end / 100) - 1
  ][1]

  spans = []
  for span, duration in span_duration_pairs:
    if duration >= percentile_start_value and duration <= percentile_end_value:
      spans.append(span)
  return spans
