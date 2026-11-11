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

"""Module for exporting trace cache and analysis data in JSON, CSV, and Proto formats."""

import datetime
import functools
import json
import os
from typing import Any, Dict, List

from google.protobuf import json_format  # type: ignore[import-untyped]
from google.protobuf import text_format  # type: ignore[import-untyped]
import numpy as np
import pandas as pd

try:
  from . import trace_cache_pb2
except ImportError:
  from agent.analysis import trace_cache_pb2

from dependency_graph import DependencyGraph
from graph import GraphCollection


def _precise(msg: Any, name: str, default: float = 0.0) -> float:
  """Returns `<name>_f64` if set, else the legacy float32 `<name>`."""
  if msg.HasField(name + "_f64"):
    return getattr(msg, name + "_f64")
  if msg.HasField(name):
    return getattr(msg, name)
  return default


def build_trace_cache_proto(
    collection: GraphCollection,
    dep_graph: DependencyGraph,
    input_source: str = "raw",
) -> trace_cache_pb2.TraceCacheProto:
  """Builds a TraceCacheProto object from GraphCollection and DependencyGraph.

  Args:
    collection: The GraphCollection to convert.
    dep_graph: The DependencyGraph to convert.
    input_source: The source path of the raw traces.

  Returns:
    A built TraceCacheProto message.
  """
  cache_proto = trace_cache_pb2.TraceCacheProto()
  cache_proto.input_source = input_source
  cache_proto.trace_count = len(collection.graphs)
  cache_proto.generated_at = datetime.datetime.now(
      datetime.timezone.utc
  ).isoformat()

  # Populate DependencyGraphProto
  if dep_graph is not None and dep_graph.deps:
    depgraph_proto = cache_proto.depgraph
    for name, dep_node in dep_graph.deps.items():
      n_proto = depgraph_proto.nodes.add()
      n_proto.node_key = name
      n_proto.happens_before.extend(sorted(list(dep_node.happens_before)))
      n_proto.child_dependents.extend(sorted(list(dep_node.child_dependents)))
      n_proto.async_children.extend(sorted(list(dep_node.async_children)))
      if dep_node.parent_start_delay:
        n_proto.median_start_delay_sec = float(
            np.median(dep_node.parent_start_delay)
        )
      if dep_node.parent_end_delay:
        n_proto.median_end_delay_sec = float(
            np.median(dep_node.parent_end_delay)
        )

  # Populate SpanMetricsProto
  for graph in collection.graphs.values():
    if not graph.graph:
      continue

    root_dur = graph.get_duration()
    cp = graph.get_critical_path()
    cp_spans = set(n.sid for n in cp.cp)
    ex_drag = cp.calculate_drag(exclusive=True).drag_per_span
    inc_drag = cp.calculate_drag(exclusive=False).drag_per_span
    slack = cp.calculate_slack(dep_graph).slack_per_span

    for sid, node in graph.graph.nodeHT.items():
      if node is None:
        continue
      span_proto = cache_proto.spans.add()
      span_proto.trace_id = str(graph.trace_id)
      span_proto.span_id = str(node.sid)
      span_proto.parent_rpc_span_id = (
          str(node.parentSpanId) if node.parentSpanId else "0"
      )
      span_proto.method_name = str(node.opName)
      span_proto.server_job = str(node.pid)
      span_proto.start_timestamp_sec = float(node.startTime)
      span_proto.finish_timestamp_sec = float(node.endTime)
      span_proto.duration_sec = float(node.duration)
      span_proto.start_timestamp_sec_f64 = float(node.startTime)
      span_proto.finish_timestamp_sec_f64 = float(node.endTime)
      span_proto.duration_sec_f64 = float(node.duration)

      meta = graph.get_span_metadata(sid)
      cd_proto = span_proto.component_deltas
      if meta.span_components:
        sc = meta.span_components
        cd_proto.server_app_delta = float(sc.get("server_app_delta", 0.0))
        cd_proto.server_app_delta_f64 = float(sc.get("server_app_delta", 0.0))
        cd_proto.client_send_queue_delta = float(
            sc.get("client_send_queue_delta", 0.0)
        )
        cd_proto.server_recv_queue_delta = float(
            sc.get("server_recv_queue_delta", 0.0)
        )
        cd_proto.client_recv_queue_delta = float(
            sc.get("client_recv_queue_delta", 0.0)
        )
        cd_proto.server_send_queue_delta = float(
            sc.get("server_send_queue_delta", 0.0)
        )
        cd_proto.request_network_delta = float(
            sc.get("request_network_delta", 0.0)
        )
        cd_proto.response_network_delta = float(
            sc.get("response_network_delta", 0.0)
        )
      else:
        cd_proto.server_app_delta = float(node.duration)
        cd_proto.server_app_delta_f64 = float(node.duration)

      span_proto.is_critical_path = bool(sid in cp_spans)
      ex_val = float(ex_drag.get(sid, 0.0))
      inc_val = float(inc_drag.get(sid, 0.0))
      slk_val = float(slack.get(sid, 0.0))

      span_proto.exclusive_drag_sec = ex_val
      span_proto.inclusive_drag_sec = inc_val
      span_proto.slack_sec = slk_val
      span_proto.exclusive_drag_sec_f64 = ex_val
      span_proto.inclusive_drag_sec_f64 = inc_val
      span_proto.slack_sec_f64 = slk_val
      span_proto.relative_exclusive_drag = (
          float(ex_val / root_dur) if root_dur > 0 else 0.0
      )
      span_proto.relative_slack = (
          float(slk_val / root_dur) if root_dur > 0 else 0.0
      )
      span_proto.num_descendants = int(meta.num_descendants)

  return cache_proto


@functools.singledispatch
def _to_dataframe(data: Any) -> pd.DataFrame:
  """Converts input data (dict, list, DataFrame, or Proto) into a Pandas DataFrame.

  Args:
    data: The input data to convert. Can be a DataFrame, TraceCacheProto,
      AnalysisResultProto, dictionary, or list.

  Returns:
    A pandas DataFrame containing the converted data.

  Raises:
    ValueError: If the data type or AnalysisResultProto mode is unsupported.
  """
  raise ValueError(f"Cannot convert data of type {type(data)} to DataFrame.")


@_to_dataframe.register(pd.DataFrame)
def _dataframe_to_df(data: pd.DataFrame) -> pd.DataFrame:
  """Returns the input DataFrame directly."""
  return data


@_to_dataframe.register(trace_cache_pb2.TraceCacheProto)
def _trace_cache_proto_to_df(
    data: trace_cache_pb2.TraceCacheProto,
) -> pd.DataFrame:
  """Converts a TraceCacheProto message into a pandas DataFrame."""
  rows = []
  for span in data.spans:
    cd = span.component_deltas
    server_app_delta = _precise(span, "duration_sec", 0.0)
    if span.HasField("component_deltas") and (
        cd.HasField("server_app_delta") or cd.HasField("server_app_delta_f64")
    ):
      server_app_delta = _precise(cd, "server_app_delta", 0.0)
    rows.append({
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "parent_rpc_span_id": span.parent_rpc_span_id,
        "method_name": span.method_name,
        "server_job": span.server_job,
        "start_timestamp": _precise(span, "start_timestamp_sec", 0.0),
        "finish_timestamp": _precise(span, "finish_timestamp_sec", 0.0),
        "duration_sec": _precise(span, "duration_sec", 0.0),
        "is_critical_path": span.is_critical_path,
        "exclusive_drag_sec": _precise(span, "exclusive_drag_sec", 0.0),
        "inclusive_drag_sec": _precise(span, "inclusive_drag_sec", 0.0),
        "slack_sec": _precise(span, "slack_sec", 0.0),
        "relative_exclusive_drag": span.relative_exclusive_drag,
        "relative_slack": span.relative_slack,
        "num_descendants": (
            span.num_descendants
            if span.HasField("num_descendants")
            else (1000 if span.parent_rpc_span_id in ("0", "", "None") else 1)
        ),
        "server_app_delta": server_app_delta,
        "request_network_delta": (
            cd.request_network_delta
            if span.HasField("component_deltas")
            else 0.0
        ),
        "response_network_delta": (
            cd.response_network_delta
            if span.HasField("component_deltas")
            else 0.0
        ),
        "client_send_queue_delta": (
            cd.client_send_queue_delta
            if span.HasField("component_deltas")
            else 0.0
        ),
        "server_recv_queue_delta": (
            cd.server_recv_queue_delta
            if span.HasField("component_deltas")
            else 0.0
        ),
        "client_recv_queue_delta": (
            cd.client_recv_queue_delta
            if span.HasField("component_deltas")
            else 0.0
        ),
        "server_send_queue_delta": (
            cd.server_send_queue_delta
            if span.HasField("component_deltas")
            else 0.0
        ),
    })
  return pd.DataFrame(rows)


@_to_dataframe.register(trace_cache_pb2.AnalysisResultProto)
def _analysis_result_proto_to_df(
    data: trace_cache_pb2.AnalysisResultProto,
) -> pd.DataFrame:
  """Converts an AnalysisResultProto message into a pandas DataFrame."""
  mode = data.mode
  if mode == "rank_drag":
    rd = data.rank_drag_result
    rows = []
    for r in rd.rankings:
      rows.append({
          "rank": r.rank,
          "method": r.method,
          "exclusive_drag_sec": r.exclusive_drag_sec,
          "relative_drag": r.relative_drag,
          "expected_per_trace_sec": r.expected_per_trace_sec,
          "cp_share": r.cp_share,
          "mean": r.mean,
          "std": r.std,
          "p50": r.p50,
          "p90": r.p90,
          "p95": r.p95,
          "p99": r.p99,
      })
    return pd.DataFrame(rows)
  elif mode == "distribution":
    dist = data.distribution_result
    df_data = {}
    for m_name, m_val in dist.metrics.items():
      original_vals = list(m_val.original)
      if original_vals:
        df_data[f"{m_name}_original"] = original_vals
      retimed_vals = list(m_val.retimed)
      if retimed_vals:
        df_data[f"{m_name}_retimed"] = retimed_vals
    return pd.DataFrame(df_data)
  elif mode == "percent_improvement":
    pi = data.percent_improvement_result
    df_data = {
        "original_durations_sec": list(pi.original_durations_sec),
        "retimed_durations_sec": list(pi.retimed_durations_sec),
        "saved_sec": list(pi.saved_sec),
        "percent_improvements": list(pi.percent_improvements),
    }
    return pd.DataFrame(df_data)
  elif mode == "child_methods":
    cm = data.child_methods_result
    rows = []
    for item in cm.child_methods:
      rows.append({
          "child_method": item.child_method,
          "count": item.count,
      })
    return pd.DataFrame(rows)
  raise ValueError(f"Unsupported AnalysisResultProto mode: {mode}")


@_to_dataframe.register(dict)
def _dict_to_df(data: Dict[str, Any]) -> pd.DataFrame:
  """Converts a dictionary into a pandas DataFrame."""
  mode = data.get("mode", "")
  if mode == "rank_drag" and "rankings" in data:
    return pd.DataFrame(data["rankings"])
  elif mode == "distribution" and "metrics" in data:
    df_data = {}
    for m_name, m_val in data["metrics"].items():
      original_vals = m_val.get("original", [])
      if original_vals is not None and len(original_vals) > 0:
        df_data[f"{m_name}_original"] = original_vals
      retimed_vals = m_val.get("retimed", [])
      if retimed_vals is not None and len(retimed_vals) > 0:
        df_data[f"{m_name}_retimed"] = retimed_vals
    return pd.DataFrame(df_data)
  elif mode == "percent_improvement" and "percent_improvements" in data:
    df_data = {
        "original_durations_sec": data.get("original_durations_sec", []),
        "retimed_durations_sec": data.get("retimed_durations_sec", []),
        "saved_sec": data.get("saved_sec", []),
        "percent_improvements": data.get("percent_improvements", []),
    }
    return pd.DataFrame(df_data)
  elif mode == "child_methods" and "child_methods" in data:
    return pd.DataFrame(data["child_methods"])

  if "rankings" in data:
    return pd.DataFrame(data["rankings"])
  if "spans" in data:
    return pd.DataFrame(data["spans"])
  if "quantiles" in data:
    return pd.DataFrame([data["quantiles"]])
  return pd.DataFrame([data])


@_to_dataframe.register(list)
def _list_to_df(data: List[Any]) -> pd.DataFrame:
  """Converts a list into a pandas DataFrame."""
  return pd.DataFrame(data)


def _dict_to_stats_proto(
    stats_dict: Dict[str, float],
) -> trace_cache_pb2.MetricStatsProto:
  """Converts a dictionary of summary statistics into a MetricStatsProto.

  Args:
    stats_dict: A dictionary containing stats like 'mean', 'std', etc.

  Returns:
    A populated MetricStatsProto message.
  """
  msg = trace_cache_pb2.MetricStatsProto()
  if "mean" in stats_dict:
    msg.mean = float(stats_dict["mean"])
  if "std" in stats_dict:
    msg.std = float(stats_dict["std"])
  if "p50" in stats_dict:
    msg.p50 = float(stats_dict["p50"])
  if "p90" in stats_dict:
    msg.p90 = float(stats_dict["p90"])
  if "p95" in stats_dict:
    msg.p95 = float(stats_dict["p95"])
  if "p99" in stats_dict:
    msg.p99 = float(stats_dict["p99"])
  return msg


def build_analysis_result_proto(
    data: Dict[str, Any],
) -> trace_cache_pb2.AnalysisResultProto:
  """Builds an AnalysisResultProto object from a Stage 2 result dictionary.

  Args:
    data: A dictionary containing the Stage 2 analysis results.

  Returns:
    A built AnalysisResultProto message.
  """
  res_proto = trace_cache_pb2.AnalysisResultProto()
  mode = data.get("mode", "")
  res_proto.mode = mode

  if mode == "rank_drag":
    rd = res_proto.rank_drag_result
    rd.top_k = int(data.get("top_k", 0))
    rd.stat = str(data.get("stat", ""))
    if "percentile_start" in data:
      rd.percentile_start = float(data["percentile_start"])
    if "percentile_end" in data:
      rd.percentile_end = float(data["percentile_end"])
    rd.trace_count = int(data.get("trace_count", 0))
    rd.root_mean_duration_sec = float(data.get("root_mean_duration_sec", 0.0))
    rd.precomputed_drag_traces = int(data.get("precomputed_drag_traces", 0))
    for r in data.get("rankings", []):
      r_proto = rd.rankings.add()
      r_proto.rank = int(r.get("rank", 0))
      r_proto.method = str(r.get("method", ""))
      r_proto.exclusive_drag_sec = float(r.get("exclusive_drag_sec", 0.0))
      r_proto.relative_drag = float(r.get("relative_drag", 0.0))
      r_proto.mean = float(r.get("mean", 0.0))
      r_proto.std = float(r.get("std", 0.0))
      r_proto.p50 = float(r.get("p50", 0.0))
      r_proto.p90 = float(r.get("p90", 0.0))
      r_proto.p95 = float(r.get("p95", 0.0))
      r_proto.p99 = float(r.get("p99", 0.0))
      r_proto.expected_per_trace_sec = float(
          r.get("expected_per_trace_sec", 0.0)
      )
      r_proto.cp_share = float(r.get("cp_share", 0.0))

  elif mode == "distribution":
    dist = res_proto.distribution_result
    if data.get("target_method"):
      dist.target_method = str(data["target_method"])
    if data.get("target_service"):
      dist.target_service = str(data["target_service"])
    dist.with_retiming = bool(data.get("with_retiming", False))
    dist.metric_filter = str(data.get("metric_filter", ""))

    for m_name, values in data.get("metrics", {}).items():
      m_val_proto = dist.metrics[m_name]
      m_val_proto.original.extend(
          [float(v) for v in values.get("original", [])]
      )
      m_val_proto.retimed.extend([float(v) for v in values.get("retimed", [])])

    for m_name, s_dict in data.get("summary", {}).items():
      m_sum_proto = dist.summary[m_name]
      if "original_stats" in s_dict:
        m_sum_proto.original_stats.CopyFrom(
            _dict_to_stats_proto(s_dict["original_stats"])
        )
      if "retimed_stats" in s_dict:
        m_sum_proto.retimed_stats.CopyFrom(
            _dict_to_stats_proto(s_dict["retimed_stats"])
        )

  elif mode == "percent_improvement":
    pi = res_proto.percent_improvement_result
    pi.trace_count = int(data.get("trace_count", 0))
    pi.with_retiming = bool(data.get("with_retiming", False))
    pi.original_durations_sec.extend(
        [float(v) for v in data.get("original_durations_sec", [])]
    )
    pi.retimed_durations_sec.extend(
        [float(v) for v in data.get("retimed_durations_sec", [])]
    )
    pi.saved_sec.extend([float(v) for v in data.get("saved_sec", [])])
    pi.percent_improvements.extend(
        [float(v) for v in data.get("percent_improvements", [])]
    )

    if "quantiles" in data:
      q = data["quantiles"]
      q_proto = pi.quantiles
      q_proto.orig_mean_sec = float(q.get("orig_mean_sec", 0.0))
      q_proto.retimed_mean_sec = float(q.get("retimed_mean_sec", 0.0))
      q_proto.saved_mean_sec = float(q.get("saved_mean_sec", 0.0))
      q_proto.mean_percent_improvement = float(
          q.get("mean_percent_improvement", 0.0)
      )
      q_proto.p50_percent_improvement = float(
          q.get("p50_percent_improvement", 0.0)
      )
      q_proto.p90_percent_improvement = float(
          q.get("p90_percent_improvement", 0.0)
      )
      q_proto.p95_percent_improvement = float(
          q.get("p95_percent_improvement", 0.0)
      )
      q_proto.p99_percent_improvement = float(
          q.get("p99_percent_improvement", 0.0)
      )

  elif mode == "child_methods":
    cm = res_proto.child_methods_result
    cm.target_parent = str(data.get("target_parent", ""))
    cm.parent_match_count = int(data.get("parent_match_count", 0))
    for item in data.get("child_methods", []):
      item_proto = cm.child_methods.add()
      item_proto.child_method = str(item.get("child_method", ""))
      item_proto.count = int(item.get("count", 0))

  return res_proto


def export_data(
    data: Any, export_path: str, export_format: str = "json"
) -> None:
  """Exports data to the specified path in json, csv, or proto format.

  Args:
    data: The data object to export.
    export_path: The file path to write the output to.
    export_format: The format to export ('json', 'csv', 'proto').
  """
  if not export_path:
    return

  export_format = export_format.lower()

  # Create parent directories if needed
  parent_dir = os.path.dirname(export_path)
  if parent_dir:
    os.makedirs(parent_dir, exist_ok=True)

  if export_format == "json":
    if isinstance(
        data,
        (trace_cache_pb2.TraceCacheProto, trace_cache_pb2.AnalysisResultProto),
    ):
      try:
        serialized = json_format.MessageToDict(
            data,
            always_print_fields_with_no_presence=True,
            preserving_proto_field_name=True,
        )
      except TypeError:
        serialized = json_format.MessageToDict(  # type: ignore[call-arg]
            data,
            including_default_value_fields=True,
            preserving_proto_field_name=True,
        )
    elif isinstance(data, pd.DataFrame):
      serialized = data.to_dict(orient="records")
    else:
      serialized = data
    with open(export_path, "w", encoding="utf-8") as f:
      json.dump(serialized, f, indent=2)

  elif export_format == "csv":
    df = _to_dataframe(data)
    with open(export_path, "w", encoding="utf-8") as f:
      df.to_csv(f, index=False)

  elif export_format == "proto":
    if isinstance(
        data,
        (trace_cache_pb2.TraceCacheProto, trace_cache_pb2.AnalysisResultProto),
    ):
      proto_msg = data
    elif isinstance(data, dict) and "mode" in data:
      proto_msg = build_analysis_result_proto(data)
    else:
      raise ValueError(
          "Exporting to proto requires TraceCacheProto, AnalysisResultProto, or"
          " Stage 2 result dict."
      )

    if export_path.endswith(".textproto"):
      with open(export_path, "w", encoding="utf-8") as f:
        f.write(text_format.MessageToString(proto_msg))
    else:
      with open(export_path, "wb") as f:
        f.write(proto_msg.SerializeToString())

  else:
    raise ValueError(f"Unsupported export format: {export_format}")
