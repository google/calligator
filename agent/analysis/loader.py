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

"""Module for loading trace datasets in Proto or JSON format."""

import glob
import gzip
import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from google.protobuf import json_format  # type: ignore[import-untyped]
from google.protobuf import text_format  # type: ignore[import-untyped]
import pandas as pd

try:
  from . import trace_cache_pb2
except ImportError:
  from agent.analysis import trace_cache_pb2

import df_utils
from dependency_graph import DependencyGraph
from dependency_graph import DependencyGraphNode
from graph import GraphCollection

_F64_SUFFIX = '_f64'


def _precise_or_none(msg: Any, name: str) -> Optional[float]:
  """Returns `<name>_f64` if set, else the legacy float32 `<name>`, else None.

  The float32 fields cannot represent microsecond timestamps exactly, and a
  graph rebuilt from them can have a different critical path from the
  original (children whose rounded end passes the parent's end are dropped as
  asynchronous). Writers since 2026-10 also fill the double-precision copies.

  Args:
    msg: A SpanMetricsProto or ComponentDeltasProto message.
    name: The legacy float32 field name.

  Returns:
    The most precise value stored for the field, or None if unset.
  """
  if msg.HasField(name + _F64_SUFFIX):
    return getattr(msg, name + _F64_SUFFIX)
  if msg.HasField(name):
    return getattr(msg, name)
  return None


def _precise_dict_value(d: Mapping[str, Any], name: str) -> Any:
  """Dict (JSON cache) counterpart of _precise_or_none."""
  value = d.get(name + _F64_SUFFIX)
  return d.get(name) if value is None else value


def depgraph_proto_to_obj(
    depgraph_proto: Optional[trace_cache_pb2.DependencyGraphProto],
) -> DependencyGraph:
  """Converts a DependencyGraphProto message into a DependencyGraph object.

  Args:
    depgraph_proto: The dependency graph proto message to convert.

  Returns:
    A reconstructed DependencyGraph object.
  """
  dep_graph = DependencyGraph.__new__(DependencyGraph)
  deps = {}
  if depgraph_proto is not None:
    for node_item in depgraph_proto.nodes:
      key = node_item.node_key
      hb = set(node_item.happens_before)
      cd = set(node_item.child_dependents)
      ac = set(node_item.async_children)
      s_delay = (
          [node_item.median_start_delay_sec]
          if node_item.HasField('median_start_delay_sec')
          else []
      )
      e_delay = (
          [node_item.median_end_delay_sec]
          if node_item.HasField('median_end_delay_sec')
          else []
      )

      node = DependencyGraphNode(key)
      node.happens_before = hb
      node.child_dependents = cd
      node.async_children = ac
      node.parent_start_delay = s_delay
      node.parent_end_delay = e_delay
      deps[key] = node

  dep_graph.deps = deps
  return dep_graph


_depgraph_proto_to_obj = depgraph_proto_to_obj


def proto_spans_to_df(
    spans: Sequence[trace_cache_pb2.SpanMetricsProto],
) -> pd.DataFrame:
  """Converts a sequence of SpanMetricsProto messages into a Pandas DataFrame.

  Args:
    spans: A sequence of SpanMetricsProto messages.

  Returns:
    A preprocessed DataFrame containing span details.
  """
  if not spans:
    return pd.DataFrame()
  rows = []
  for span in spans:
    tid = span.trace_id if span.HasField('trace_id') and span.trace_id else None
    sid = span.span_id if span.HasField('span_id') and span.span_id else None
    if (
        span.HasField('parent_rpc_span_id')
        and span.parent_rpc_span_id
        and span.parent_rpc_span_id != 'None'
    ):
      parent_sid = span.parent_rpc_span_id
    else:
      parent_sid = '0'
    method = (
        span.method_name
        if span.HasField('method_name') and span.method_name
        else None
    )
    job = (
        span.server_job
        if span.HasField('server_job') and span.server_job
        else None
    )

    start = _precise_or_none(span, 'start_timestamp_sec')
    finish = _precise_or_none(span, 'finish_timestamp_sec')
    num_desc = (
        span.num_descendants if span.HasField('num_descendants') else None
    )

    if span.HasField('component_deltas'):
      cd = span.component_deltas
      app = _precise_or_none(cd, 'server_app_delta')
      if app is None and finish is not None and start is not None:
        app = finish - start

      req_net = (
          cd.request_network_delta
          if cd.HasField('request_network_delta')
          else 0.0
      )
      resp_net = (
          cd.response_network_delta
          if cd.HasField('response_network_delta')
          else 0.0
      )
      cs_q = (
          cd.client_send_queue_delta
          if cd.HasField('client_send_queue_delta')
          else 0.0
      )
      sr_q = (
          cd.server_recv_queue_delta
          if cd.HasField('server_recv_queue_delta')
          else 0.0
      )
      cr_q = (
          cd.client_recv_queue_delta
          if cd.HasField('client_recv_queue_delta')
          else 0.0
      )
      ss_q = (
          cd.server_send_queue_delta
          if cd.HasField('server_send_queue_delta')
          else 0.0
      )
    else:
      app = finish - start if finish is not None and start is not None else None
      req_net = 0.0
      resp_net = 0.0
      cs_q = 0.0
      sr_q = 0.0
      cr_q = 0.0
      ss_q = 0.0

    is_root = parent_sid in ('0', '', 'None')
    if num_desc is None:
      num_desc = 1000 if is_root else 1

    server_job = (
        job
        if job
        else (method.split('.')[0] if method and '.' in method else '')
    )
    if job and method:
      if method.startswith(f'{job}.'):
        method_name = method
      else:
        method_name = f'{job}.{method}'
    elif method:
      method_name = method
    elif job:
      method_name = job
    else:
      method_name = None

    rows.append({
        'trace_id': tid,
        'span_id': sid,
        'parent_rpc_span_id': parent_sid,
        'method_name': method_name,
        'server_job': server_job,
        'client_start_timestamp': start,
        'client_finish_timestamp': finish,
        'server_start_timestamp': start,
        'server_finish_timestamp': finish,
        'server_app_delta': app,
        'request_network_delta': req_net,
        'response_network_delta': resp_net,
        'client_send_queue_delta': cs_q,
        'server_recv_queue_delta': sr_q,
        'client_recv_queue_delta': cr_q,
        'server_send_queue_delta': ss_q,
        'is_true_root': is_root,
        'num_descendants': num_desc,
    })
  df = pd.DataFrame(rows)
  return df_utils.preprocess(df, is_jaeger_trace=False, is_raw=False)


def dict_spans_to_df(spans: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
  """Converts a sequence of dictionary spans into a Pandas DataFrame.

  Args:
    spans: A sequence of dictionaries representing span metrics.

  Returns:
    A preprocessed DataFrame containing span details.
  """
  if not spans:
    return pd.DataFrame()
  rows = []
  for span in spans:
    tid = span.get('trace_id')
    sid = span.get('span_id')
    parent_sid = span.get('parent_rpc_span_id')
    if not parent_sid or parent_sid == 'None':
      parent_sid = '0'
    else:
      parent_sid = str(parent_sid)

    method = span.get('method_name')
    job = span.get('server_job')

    start_raw = _precise_dict_value(span, 'start_timestamp_sec')
    if start_raw is None:
      start_raw = span.get('start_timestamp')
    start = float(start_raw) if start_raw is not None else None

    finish_raw = _precise_dict_value(span, 'finish_timestamp_sec')
    if finish_raw is None:
      finish_raw = span.get('finish_timestamp')
    finish = float(finish_raw) if finish_raw is not None else None

    cd = span.get('component_deltas')
    if cd is None:
      cd = {}
    app_raw = _precise_dict_value(cd, 'server_app_delta')
    if app_raw is not None:
      app = float(app_raw)
    elif finish is not None and start is not None:
      app = finish - start
    else:
      app = None

    req_net = (
        float(cd['request_network_delta'])
        if cd.get('request_network_delta') is not None
        else 0.0
    )
    resp_net = (
        float(cd['response_network_delta'])
        if cd.get('response_network_delta') is not None
        else 0.0
    )
    cs_q = (
        float(cd['client_send_queue_delta'])
        if cd.get('client_send_queue_delta') is not None
        else 0.0
    )
    sr_q = (
        float(cd['server_recv_queue_delta'])
        if cd.get('server_recv_queue_delta') is not None
        else 0.0
    )
    cr_q = (
        float(cd['client_recv_queue_delta'])
        if cd.get('client_recv_queue_delta') is not None
        else 0.0
    )
    ss_q = (
        float(cd['server_send_queue_delta'])
        if cd.get('server_send_queue_delta') is not None
        else 0.0
    )
    num_desc = span.get('num_descendants', None)

    is_root = parent_sid in ('0', '', 'None')
    if num_desc is None:
      num_desc = 1000 if is_root else 1

    server_job = (
        job
        if job
        else (method.split('.')[0] if method and '.' in method else '')
    )
    if job and method:
      if method.startswith(f'{job}.'):
        method_name = method
      else:
        method_name = f'{job}.{method}'
    elif method:
      method_name = method
    elif job:
      method_name = job
    else:
      method_name = None

    rows.append({
        'trace_id': tid,
        'span_id': sid,
        'parent_rpc_span_id': parent_sid,
        'method_name': method_name,
        'server_job': server_job,
        'client_start_timestamp': start,
        'client_finish_timestamp': finish,
        'server_start_timestamp': start,
        'server_finish_timestamp': finish,
        'server_app_delta': app,
        'request_network_delta': req_net,
        'response_network_delta': resp_net,
        'client_send_queue_delta': cs_q,
        'server_recv_queue_delta': sr_q,
        'client_recv_queue_delta': cr_q,
        'server_send_queue_delta': ss_q,
        'is_true_root': is_root,
        'num_descendants': num_desc,
    })
  df = pd.DataFrame(rows)
  return df_utils.preprocess(df, is_jaeger_trace=False, is_raw=False)


def spans_to_df(spans: Any) -> pd.DataFrame:
  """Converts SpanMetricsProto sequence or dict sequence into a Pandas DataFrame.

  Args:
    spans: A sequence of spans (either proto messages or dictionaries).

  Returns:
    A preprocessed DataFrame containing span details.
  """
  if not spans:
    return pd.DataFrame()
  if isinstance(spans[0], trace_cache_pb2.SpanMetricsProto):
    return proto_spans_to_df(spans)
  return dict_spans_to_df(spans)


def detect_input_format(trace_path: str, matched_files: List[str]) -> str:
  """Detects the format of the trace file safely.

  Args:
    trace_path: The user-specified trace path (which may be a directory).
    matched_files: The list of resolved files from the glob pattern.

  Returns:
    A string identifying the format (e.g., 'PROTO_CACHE_BINARY').
  """
  if not matched_files:
    raise ValueError(f'No matched files for format detection: {trace_path}')

  first_file = matched_files[0]

  if first_file.endswith('.pb'):
    return 'PROTO_CACHE_BINARY'
  if first_file.endswith('.textproto'):
    return 'PROTO_CACHE_TEXT'

  if first_file.endswith('.json') or first_file.endswith('.json.gz'):
    head = b''
    open_fn = gzip.open if first_file.endswith('.gz') else open
    try:
      with open_fn(first_file, 'rb') as f:
        head = f.read(1024)
    except (IOError, OSError) as e:
      raise ValueError(f'Failed to read JSON file {first_file}: {e}') from e

    if b'"data"' in head:
      return 'JAEGER_RAW_JSON'
    if b'"spans"' in head or b'"depgraph"' in head:
      return 'JSON_CACHE'

    # Fallback: parse completely
    try:
      with open_fn(first_file, 'rb') as f:
        content = json.load(f)
    except (IOError, OSError, json.JSONDecodeError) as e:
      raise ValueError(f'Failed to parse JSON file {first_file}: {e}') from e

    if isinstance(content, dict):
      if 'data' in content:
        return 'JAEGER_RAW_JSON'
      if 'spans' in content or 'depgraph' in content:
        return 'JSON_CACHE'
    elif isinstance(content, list):
      return 'JSON_CACHE'

  raise ValueError(f'Could not determine format of trace path: {trace_path}')


def validate_cache_proto(cache_proto: trace_cache_pb2.TraceCacheProto) -> None:
  """Validates that a TraceCacheProto is complete and contains required fields.

  Args:
    cache_proto: The TraceCacheProto message to validate.
  """
  if not cache_proto.spans:
    raise ValueError('Cache proto contains no spans')
  if not cache_proto.HasField('depgraph') or not cache_proto.depgraph.nodes:
    raise ValueError(
        'Cache proto is missing a valid dependency graph (depgraph)'
    )
  for span in cache_proto.spans:
    if not (
        span.HasField('exclusive_drag_sec')
        or span.HasField('exclusive_drag_sec_f64')
    ):
      raise ValueError(
          f'Span {span.span_id} is missing pre-computed exclusive_drag_sec'
      )
    if not (span.HasField('slack_sec') or span.HasField('slack_sec_f64')):
      raise ValueError(f'Span {span.span_id} is missing pre-computed slack_sec')


def validate_cache_json(content: Dict[str, Any]) -> None:
  """Validates that a JSON cache dictionary is complete and contains required fields.

  Args:
    content: The JSON cache dictionary to validate.
  """
  if 'spans' not in content or not content['spans']:
    raise ValueError('JSON cache is missing spans or it is empty')
  if (
      'depgraph' not in content
      or 'nodes' not in content['depgraph']
      or not content['depgraph']['nodes']
  ):
    raise ValueError(
        'JSON cache is missing a valid dependency graph (depgraph.nodes)'
    )
  for span in content['spans']:
    span_id = span.get('span_id')
    if (
        'exclusive_drag_sec' not in span
        and 'exclusive_drag_sec_f64' not in span
    ):
      raise ValueError(
          f'Span {span_id} is missing pre-computed exclusive_drag_sec'
      )
    if 'slack_sec' not in span and 'slack_sec_f64' not in span:
      raise ValueError(f'Span {span_id} is missing pre-computed slack_sec')


def load_cached_traces(
    trace_path: str, max_traces: int = 1000
) -> Tuple[GraphCollection, DependencyGraph]:
  """Loads trace dataset from Proto (.pb, .textproto) or JSON (.json, .json.gz).

  Args:
    trace_path: Path to the input dataset file.
    max_traces: Maximum number of traces to load.

  Returns:
    A tuple of (GraphCollection, DependencyGraph).

  Raises:
    FileNotFoundError: If the trace file or glob pattern does not match any
      files.
    ValueError: If format detection fails or format is unsupported.
  """
  try:
    matched_files = sorted(glob.glob(trace_path))
  except Exception as e:
    raise FileNotFoundError(
        f'Error resolving glob pattern {trace_path}: {e}'
    ) from e

  if not matched_files:
    raise FileNotFoundError(
        f'Trace file or glob pattern does not match any files: {trace_path}'
    )

  fmt = detect_input_format(trace_path, matched_files)
  load_path = matched_files[0]

  if fmt == 'PROTO_CACHE_BINARY':
    cache_proto = trace_cache_pb2.TraceCacheProto()
    try:
      with open(load_path, 'rb') as f:
        cache_proto.ParseFromString(f.read())
    except Exception as e:
      raise ValueError(
          f'Failed to parse binary proto cache file {load_path}: {e}'
      ) from e
    validate_cache_proto(cache_proto)
    df = proto_spans_to_df(cache_proto.spans)
    collection = GraphCollection(df, max_traces=max_traces)
    depgraph = depgraph_proto_to_obj(cache_proto.depgraph)
    return collection, depgraph

  elif fmt == 'PROTO_CACHE_TEXT':
    cache_proto = trace_cache_pb2.TraceCacheProto()
    try:
      with open(load_path, 'r', encoding='utf-8') as f:
        text_format.Parse(f.read(), cache_proto)
    except Exception as e:
      raise ValueError(
          f'Failed to parse textproto cache file {load_path}: {e}'
      ) from e
    validate_cache_proto(cache_proto)
    df = proto_spans_to_df(cache_proto.spans)
    collection = GraphCollection(df, max_traces=max_traces)
    depgraph = depgraph_proto_to_obj(cache_proto.depgraph)
    return collection, depgraph

  elif fmt == 'JSON_CACHE':
    cache_proto = trace_cache_pb2.TraceCacheProto()
    open_fn = gzip.open if load_path.endswith('.gz') else open
    try:
      with open_fn(load_path, 'rt', encoding='utf-8') as f:
        json_format.Parse(f.read(), cache_proto, ignore_unknown_fields=True)
    except Exception as e:
      raise ValueError(
          f'Failed to parse JSON cache file {load_path}: {e}'
      ) from e
    validate_cache_proto(cache_proto)
    df = proto_spans_to_df(cache_proto.spans)
    collection = GraphCollection(df, max_traces=max_traces)
    depgraph = depgraph_proto_to_obj(cache_proto.depgraph)
    return collection, depgraph

  elif fmt == 'JAEGER_RAW_JSON':
    open_fn = gzip.open if load_path.endswith('.gz') else open
    try:
      with open_fn(load_path, 'rt', encoding='utf-8') as f:
        content = json.load(f)
    except Exception as e:
      raise ValueError(
          f'Failed to parse Jaeger JSON file {load_path}: {e}'
      ) from e
    df = df_utils.get_df_from_jaeger_json(content)
    collection = GraphCollection(df, max_traces=max_traces)
    depgraph = collection.get_dependency_graph()
    return collection, depgraph

  else:
    raise ValueError(f'Unknown format {fmt} for trace path: {trace_path}')


def load_precomputed_drag(trace_path: str) -> Dict[str, Dict[str, float]]:
  """Reads the per-span exclusive drag that preprocess_traces stored.

  The stored drag was computed on the original (full-precision) graph. Use it
  instead of recomputing the critical path from cached spans, which for
  float32-only caches can give a different critical path.

  Args:
    trace_path: Path to a proto (.pb, .textproto) or JSON (.json, .json.gz) cache.

  Returns:
    {trace_id: {span_id: exclusive_drag_sec}} for critical-path spans, or an
    empty dict if `trace_path` is not a cache (e.g. raw Jaeger JSON).
  """
  matched_files = sorted(glob.glob(trace_path))
  if not matched_files:
    return {}
  fmt = detect_input_format(trace_path, matched_files)
  load_path = matched_files[0]
  cache_proto = trace_cache_pb2.TraceCacheProto()
  if fmt == 'PROTO_CACHE_BINARY':
    with open(load_path, 'rb') as f:
      cache_proto.ParseFromString(f.read())
  elif fmt == 'PROTO_CACHE_TEXT':
    with open(load_path, 'r', encoding='utf-8') as f:
      text_format.Parse(f.read(), cache_proto)
  elif fmt == 'JSON_CACHE':
    open_fn = gzip.open if load_path.endswith('.gz') else open
    with open_fn(load_path, 'rt', encoding='utf-8') as f:
      json_format.Parse(f.read(), cache_proto, ignore_unknown_fields=True)
  else:
    return {}
  drag: Dict[str, Dict[str, float]] = {}
  for span in cache_proto.spans:
    if not span.is_critical_path:
      continue
    value = _precise_or_none(span, 'exclusive_drag_sec')
    drag.setdefault(str(span.trace_id), {})[str(span.span_id)] = (
        float(value) if value is not None else 0.0
    )
  return drag
