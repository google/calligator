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

"""Stage 2 Unified Analysis CLI: Unified tool for all trace analysis modes."""

import collections
import copy
import glob
import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from absl import app
from absl import flags
from absl import logging
import numpy as np
import pandas as pd

import retimer
try:
  from . import data_exporter
  from . import loader
  from . import plot_utils
except ImportError:
  from agent.analysis import data_exporter
  from agent.analysis import loader
  from agent.analysis import plot_utils
from dependency_graph import DependencyGraph
from graph import GraphCollection

FLAGS = flags.FLAGS

# Global Flags
flags.DEFINE_string(
    'trace_path',
    '/tmp/traces_cache.pb',
    'Path to Stage 1 cache (.pb, .textproto, .json) or raw trace file'
    ' (.json).',
)
flags.DEFINE_enum(
    'mode',
    None,
    ['rank_drag', 'distribution', 'percent_improvement', 'child_methods'],
    'Analysis mode to execute.',
    required=True,
)
flags.DEFINE_enum(
    'format', 'table', ['table', 'json', 'csv'], 'Console stdout format.'
)
flags.DEFINE_string('export_data_path', None, 'File path for data export.')
flags.DEFINE_enum(
    'export_format',
    'json',
    ['json', 'csv', 'proto'],
    'Data export format.',
)
flags.DEFINE_string(
    'output_plot_path',
    None,
    'File path for visual Matplotlib plot PNG/PDF.',
)
flags.DEFINE_bool(
    'show_plot', False, 'Display Matplotlib plot figure interactively.'
)
flags.DEFINE_enum(
    'plot_drag_type',
    'exclusive',
    ['exclusive', 'inclusive'],
    'Which drag metric to plot on the positive X-axis of the combined'
    ' Slack/Drag CDF plot.',
)

# Observation Scope Flags
flags.DEFINE_integer('top_k', 10, 'Top K methods to include in rank_drag mode.')
flags.DEFINE_string(
    'method', None, 'Target RPC method for distribution analysis.'
)
flags.DEFINE_string(
    'service', None, 'Target microservice name for distribution analysis.'
)
flags.DEFINE_string(
    'root_method', None, 'Filter traces by root RPC method name.'
)
flags.DEFINE_float(
    'percentile_start',
    0.0,
    'Starting latency percentile for rank_drag (e.g. 90.0).',
)
flags.DEFINE_float(
    'percentile_end',
    100.0,
    'Ending latency percentile for rank_drag (e.g. 95.0).',
)
flags.DEFINE_enum(
    'stat',
    'mean',
    ['mean', 'p50', 'p90', 'p95', 'p99', 'expected_per_trace_sec'],
    'Statistic for rank_drag bar chart. mean/pXX are conditional on the method'
    ' being on the critical path; expected_per_trace_sec is total drag divided'
    ' by the number of traces.',
)
flags.DEFINE_bool(
    'use_cached_drag',
    True,
    'In rank_drag mode on a proto/JSON cache, use the per-span exclusive drag'
    ' stored by preprocess_traces instead of recomputing the critical path'
    ' from the cached spans.',
)
flags.DEFINE_enum(
    'metric',
    'all',
    [
        'all',
        'duration',
        'duration_diff',
        'exclusive_drag',
        'inclusive_drag',
        'slack',
    ],
    'Metric for distribution mode.',
)

# Retiming Optimization Flags
flags.DEFINE_bool('with_retiming', False, 'Enable retiming simulation mode.')
flags.DEFINE_string(
    'retime_spec',
    None,
    'JSON mapping of method names to retiming dicts (e.g.'
    ' {"MethodA": {"percent_diff": -50.0}}).',
)
flags.DEFINE_list('retime_method', [], 'List of method names to retime.')
flags.DEFINE_list(
    'retime_percent',
    [],
    'List of percent differences matching retime_method.',
)
flags.DEFINE_list(
    'retime_fixed_sec',
    [],
    'List of fixed second deltas matching retime_method.',
)
flags.DEFINE_list(
    'retime_fixed',
    [],
    'Alias for --retime_fixed_sec in seconds.',
)
flags.DEFINE_list(
    'retime_fixed_us',
    [],
    'Legacy list of fixed microsecond deltas matching retime_method.',
)
flags.DEFINE_list(
    'retime_max_lat_sec',
    [],
    'List of max latency ceilings in seconds matching retime_method.',
)
flags.DEFINE_list(
    'retime_max_lat',
    [],
    'Alias for --retime_max_lat_sec in seconds.',
)
flags.DEFINE_list(
    'retime_max_lat_us',
    [],
    'Legacy list of max latency ceilings in microseconds matching'
    ' retime_method.',
)
flags.DEFINE_bool(
    'remove_all_queuing',
    False,
    'Remove all queuing deltas across all graph nodes.',
)
flags.DEFINE_float(
    'cap_network_sec',
    None,
    'Cap network transit deltas to a maximum second ceiling.',
)
flags.DEFINE_float(
    'cap_network',
    None,
    'Alias for --cap_network_sec in seconds.',
)
flags.DEFINE_float(
    'cap_network_ms',
    None,
    'Legacy cap network transit deltas to a maximum millisecond ceiling.',
)


def _compute_stats(vals: List[float]) -> Dict[str, float]:
  """Computes summary statistics for a numeric list.

  Args:
    vals: A list of numeric values.

  Returns:
    A dictionary mapping statistic names to their computed values.
  """
  if not vals:
    return {
        'mean': 0.0,
        'std': 0.0,
        'p50': 0.0,
        'p90': 0.0,
        'p95': 0.0,
        'p99': 0.0,
    }
  arr = np.array(vals)
  return {
      'mean': float(np.mean(arr)),
      'std': float(np.std(arr)),
      'p50': float(np.percentile(arr, 50)),
      'p90': float(np.percentile(arr, 90)),
      'p95': float(np.percentile(arr, 95)),
      'p99': float(np.percentile(arr, 99)),
  }


def validate_flags() -> None:
  """Validates retiming flags to prevent silent failures."""
  has_cap_network = (
      FLAGS.cap_network_sec is not None
      or FLAGS.cap_network is not None
      or FLAGS.cap_network_ms is not None
  )
  has_retime_fixed = (
      bool(FLAGS.retime_fixed_sec)
      or bool(FLAGS.retime_fixed)
      or bool(FLAGS.retime_fixed_us)
  )
  has_retime_max_lat = (
      bool(FLAGS.retime_max_lat_sec)
      or bool(FLAGS.retime_max_lat)
      or bool(FLAGS.retime_max_lat_us)
  )
  has_rules = (
      FLAGS.remove_all_queuing
      or has_cap_network
      or bool(FLAGS.retime_spec)
      or bool(FLAGS.retime_method)
      or bool(FLAGS.retime_percent)
      or has_retime_fixed
      or has_retime_max_lat
  )
  if FLAGS.with_retiming and not has_rules:
    raise flags.ValidationError(
        '--with_retiming=True requires at least one retiming rule (e.g.,'
        ' --remove_all_queuing, --cap_network_sec, --retime_spec, or'
        ' --retime_method).'
    )
  if not FLAGS.with_retiming and has_rules:
    raise flags.ValidationError(
        'Retiming rules are specified, but --with_retiming is False. Set'
        ' --with_retiming=True to enable simulation.'
    )
  if (
      FLAGS.with_retiming
      and (
          bool(FLAGS.retime_percent)
          or has_retime_fixed
          or has_retime_max_lat
      )
      and not FLAGS.retime_method
  ):
    raise flags.ValidationError(
        '--retime_percent, --retime_fixed*, and --retime_max_lat* require'
        ' specifying --retime_method.'
    )
  if FLAGS.percentile_start < 0.0 or FLAGS.percentile_start > 100.0:
    raise flags.ValidationError(
        '--percentile_start must be between 0.0 and 100.0.'
    )
  if FLAGS.percentile_end < 0.0 or FLAGS.percentile_end > 100.0:
    raise flags.ValidationError(
        '--percentile_end must be between 0.0 and 100.0.'
    )
  if FLAGS.percentile_start > FLAGS.percentile_end:
    raise flags.ValidationError(
        '--percentile_start cannot exceed --percentile_end.'
    )


def should_retime() -> bool:
  """Checks if any retiming flags or with_retiming are specified.

  Returns:
    True if retiming is enabled or specified, False otherwise.
  """
  return FLAGS.with_retiming


def normalize_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
  """Normalizes time keys in a retiming rule into universal seconds."""
  new_rule = copy.deepcopy(rule)
  if 'fixed_diff_sec' in new_rule:
    new_rule['fixed_diff_sec'] = float(new_rule['fixed_diff_sec'])
  elif 'fixed_diff' in new_rule:
    new_rule['fixed_diff_sec'] = float(new_rule['fixed_diff'])
    del new_rule['fixed_diff']
  elif 'fixed_diff_us' in new_rule:
    new_rule['fixed_diff_sec'] = float(new_rule['fixed_diff_us']) / 1000000.0
    del new_rule['fixed_diff_us']
  elif 'fixed_diff_ms' in new_rule:
    new_rule['fixed_diff_sec'] = float(new_rule['fixed_diff_ms']) / 1000.0
    del new_rule['fixed_diff_ms']

  if 'max_lat_sec' in new_rule:
    new_rule['max_lat_sec'] = float(new_rule['max_lat_sec'])
  elif 'max_lat' in new_rule:
    new_rule['max_lat_sec'] = float(new_rule['max_lat'])
    del new_rule['max_lat']
  elif 'max_lat_us' in new_rule:
    new_rule['max_lat_sec'] = float(new_rule['max_lat_us']) / 1000000.0
    del new_rule['max_lat_us']
  elif 'max_lat_ms' in new_rule:
    new_rule['max_lat_sec'] = float(new_rule['max_lat_ms']) / 1000.0
    del new_rule['max_lat_ms']

  return new_rule


def _resolve_input_path(path: str) -> str:
  """Resolves relative input paths against BUILD_WORKING_DIRECTORY under bazel run."""
  if not path or os.path.isabs(path):
    return path
  build_wd = os.environ.get('BUILD_WORKING_DIRECTORY')
  if build_wd:
    candidate = os.path.join(build_wd, path)
    if os.path.exists(candidate) or glob.glob(candidate):
      return candidate
    if os.path.exists(path) or glob.glob(path):
      return path
    return candidate
  return path


def _resolve_output_path(path: Optional[str]) -> Optional[str]:
  """Resolves relative output paths against BUILD_WORKING_DIRECTORY under bazel run."""
  if not path or os.path.isabs(path):
    return path
  build_wd = os.environ.get('BUILD_WORKING_DIRECTORY')
  if build_wd:
    return os.path.join(build_wd, path)
  return path


def parse_retime_rules() -> List[Dict[str, Any]]:
  """Parses and returns the retiming rules from the flag.

  Returns:
    A list of normalized retiming rule dictionaries.
  """
  rules = []
  if FLAGS.retime_spec:
    spec_path = FLAGS.retime_spec
    build_wd = os.environ.get('BUILD_WORKING_DIRECTORY')
    if build_wd and not os.path.isabs(spec_path):
      candidate = os.path.join(build_wd, spec_path)
      if os.path.exists(candidate) or not os.path.exists(spec_path):
        spec_path = candidate

    spec_content = FLAGS.retime_spec
    is_file = os.path.exists(spec_path)
    if is_file:
      try:
        with open(spec_path, 'r') as f:
          spec_content = f.read()
      except IOError as e:
        raise flags.ValidationError(
            f'Failed to read retime_spec file {spec_path}: {e}'
        ) from e

    try:
      parsed = json.loads(spec_content)
    except json.JSONDecodeError as e:
      source_desc = f"file '{spec_path}'" if is_file else 'JSON string'
      raise flags.ValidationError(
          f'Failed to parse retime_spec from {source_desc}: {e}'
      ) from e

    if isinstance(parsed, list):
      for item in parsed:
        if isinstance(item, dict):
          rules.append(normalize_rule(item))
    elif isinstance(parsed, dict):
      for key, val in parsed.items():
        if isinstance(val, dict):
          if 'service_name' in val or 'method_name' in val:
            rules.append(normalize_rule(val))
          else:
            rule = copy.deepcopy(val)
            target_type = val.get('target_type')
            if key.startswith('service:'):
              rule['service_name'] = key[len('service:') :]
            elif key.startswith('method:'):
              rule['method_name'] = key[len('method:') :]
            elif target_type == 'service':
              rule['service_name'] = key
            elif target_type == 'method':
              rule['method_name'] = key
            elif '.' in key:
              rule['method_name'] = key
            else:
              rule['service_name'] = key
            rules.append(normalize_rule(rule))

  if FLAGS.retime_method:
    fixed_list = []
    if FLAGS.retime_fixed_sec:
      fixed_list = [float(v) for v in FLAGS.retime_fixed_sec]
    elif FLAGS.retime_fixed:
      fixed_list = [float(v) for v in FLAGS.retime_fixed]
    elif FLAGS.retime_fixed_us:
      fixed_list = [float(v) / 1000000.0 for v in FLAGS.retime_fixed_us]

    max_lat_list = []
    if FLAGS.retime_max_lat_sec:
      max_lat_list = [float(v) for v in FLAGS.retime_max_lat_sec]
    elif FLAGS.retime_max_lat:
      max_lat_list = [float(v) for v in FLAGS.retime_max_lat]
    elif FLAGS.retime_max_lat_us:
      max_lat_list = [float(v) / 1000000.0 for v in FLAGS.retime_max_lat_us]

    for i, method_name in enumerate(FLAGS.retime_method):
      rule = {'method_name': method_name}
      if i < len(FLAGS.retime_percent):
        rule['percent_diff'] = float(FLAGS.retime_percent[i])
      if i < len(fixed_list):
        rule['fixed_diff_sec'] = fixed_list[i]
      if i < len(max_lat_list):
        rule['max_lat_sec'] = max_lat_list[i]
      rules.append(rule)

  for r in rules:
    if 'service_name' in r and 'method_name' in r:
      raise ValueError(
          f'Rule cannot specify both service_name and method_name: {r}'
      )
  return rules


def _apply_per_method_retimings_to_graph(
    graph: Any,
    node_to_rule: Dict[str, Dict[str, Any]],
    retimer_engine: retimer.Retimer,
) -> None:
  """Applies per-method retiming specifications to matched nodes in the graph."""
  for node_sid, spec in node_to_rule.items():
    node = graph.graph.nodeHT[node_sid]
    pct = spec.get('percent_diff', None)
    fixed = spec.get('fixed_diff_sec', None)
    max_lat = spec.get('max_lat_sec', None)

    pct_val = pct if pct is not None else 0.0
    fixed_val = fixed if fixed is not None else 0.0

    target_duration = node.duration * (1.0 + pct_val / 100.0) + fixed_val
    target_duration = max(0.0, target_duration)

    if max_lat is not None:
      target_duration = min(target_duration, max_lat)

    diff = target_duration - node.duration
    if diff != 0.0:
      retimer_engine.retime_node(
          graph.graph, node.sid, node.startTime, node.endTime + diff
      )


def apply_retimings(collection: GraphCollection, depgraph: Any) -> None:
  """Applies per-method and global retimings to each graph in collection.

  Args:
    collection: The GraphCollection to retime.
    depgraph: The DependencyGraph used for retiming.
  """
  retimer_engine = retimer.Retimer(depgraph)
  rules = parse_retime_rules()

  # Determine network cap in seconds
  cap_network_sec_val = None
  if FLAGS.cap_network_sec is not None:
    cap_network_sec_val = float(FLAGS.cap_network_sec)
  elif FLAGS.cap_network is not None:
    cap_network_sec_val = float(FLAGS.cap_network)
  elif FLAGS.cap_network_ms is not None:
    cap_network_sec_val = float(FLAGS.cap_network_ms) / 1000.0

  # Apply per-method retimings
  for graph in collection.graphs.values():
    if not graph.graph:
      continue

    node_to_rule = {}
    for node in list(graph.graph.nodeHT.values()):
      if node is None:
        continue

      node_service = node.pid
      node_method_full = node.pid + '.' + node.opName

      matched_method_rule = None
      matched_service_rule = None

      for rule in rules:
        if 'method_name' in rule:
          if (
              rule['method_name'] == node_method_full
              or rule['method_name'] == node.opName
          ):
            matched_method_rule = rule
        elif 'service_name' in rule:
          if node_service.startswith(rule['service_name']):
            matched_service_rule = rule

      rule_to_apply = (
          matched_method_rule if matched_method_rule else matched_service_rule
      )
      if rule_to_apply:
        node_to_rule[node.sid] = rule_to_apply

    _apply_per_method_retimings_to_graph(graph, node_to_rule, retimer_engine)

    # Apply global infrastructure retimings
    if FLAGS.remove_all_queuing or cap_network_sec_val is not None:
      queuing_comps = [
          'client_send_queue_delta',
          'server_recv_queue_delta',
          'client_recv_queue_delta',
          'server_send_queue_delta',
      ]
      network_comps = ['request_network_delta', 'response_network_delta']
      span_comps_map = graph.get_span_components_map()
      if FLAGS.remove_all_queuing:
        try:
          retimer_engine.remove_network_components(
              graph.graph,
              component_names=queuing_comps,
              span_components_map=span_comps_map,
          )
        except ValueError as e:
          logging.warning(
              'Direct queuing removal failed, falling back to scaled removal:'
              ' %s',
              e,
          )
          # B3: restore original timestamps
          graph.restore_to_original_timestamps()
          # Re-apply per-method retimings
          _apply_per_method_retimings_to_graph(
              graph, node_to_rule, retimer_engine
          )

          # If measured queuing deltas exceed span duration on noisy traces,
          # scale components to fit span duration.
          scaled_comps_map = copy.deepcopy(span_comps_map)
          for sid, node in graph.graph.nodeHT.items():
            if not node or sid not in scaled_comps_map:
              continue
            comps = scaled_comps_map[sid]
            comp_sum = sum(comps.get(c, 0.0) for c in queuing_comps)
            if comp_sum >= node.duration and node.duration > 0:
              scale = 0.95 * node.duration / comp_sum
              for c in queuing_comps:
                if c in comps:
                  comps[c] *= scale
          try:
            retimer_engine.remove_network_components(
                graph.graph,
                component_names=queuing_comps,
                span_components_map=scaled_comps_map,
            )
          except ValueError as err:
            logging.warning('Failed to remove queuing components: %s', err)
            graph.restore_to_original_timestamps()
            _apply_per_method_retimings_to_graph(
                graph, node_to_rule, retimer_engine
            )

      if cap_network_sec_val is not None:
        try:
          retimer_engine.retime_network_components(
              graph.graph,
              component_names=network_comps,
              to_value=cap_network_sec_val,
              span_components_map=span_comps_map,
          )
        except ValueError as e:
          logging.warning('Failed to cap network components: %s', e)
          graph.restore_to_original_timestamps()
          _apply_per_method_retimings_to_graph(
              graph, node_to_rule, retimer_engine
          )


def execute_rank_drag(
    collection: GraphCollection,
    percentile_start: float = 0.0,
    percentile_end: float = 100.0,
    precomputed_drag: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> Dict[str, Any]:
  """Ranks RPC methods by exclusive drag along the critical path.

  Per method, `mean`/`p50`/... are over the critical-path spans of that method
  (conditional on the method being on the critical path).
  `expected_per_trace_sec` is the total drag of the method divided by the
  number of traces, and `cp_share` is the share of traces where the method is
  on the critical path. Expected drags partition the mean root duration.

  Args:
    collection: The GraphCollection to analyze.
    percentile_start: The start percentile of the subset analyzed.
    percentile_end: The end percentile of the subset analyzed.
    precomputed_drag: Optional {trace_id: {span_id: exclusive drag}} stored by
      preprocess_traces. When a trace is present here and not retimed, its
      stored drag is used instead of recomputing the critical path.

  Returns:
    A dictionary containing the rank drag analysis results.
  """
  if percentile_start > 0.0 or percentile_end < 100.0:
    subset = collection.get_graphs_subset(
        percentile_start=percentile_start,
        percentile_end=percentile_end,
    )
    collection = GraphCollection(graphs_list=subset)

  drag_by_method: Dict[str, List[float]] = {}
  total_by_method: Dict[str, float] = collections.defaultdict(float)
  traces_on_cp_by_method: collections.Counter[str] = collections.Counter()
  root_durations = []
  n_precomputed = 0

  for graph in collection.graphs.values():
    if not graph.graph:
      continue
    root_durations.append(graph.get_duration())
    stored = (precomputed_drag or {}).get(str(graph.trace_id))
    if stored is not None and not graph.is_retimed():
      n_precomputed += 1
      drag_per_span = stored
      nodes = {str(k): v for k, v in graph.graph.nodeHT.items()}
    else:
      drag_per_span = (
          graph.get_critical_path().calculate_drag(exclusive=True).drag_per_span
      )
      nodes = graph.graph.nodeHT
    methods_on_cp = set()
    for span_id, drag_value in drag_per_span.items():
      node = nodes.get(span_id)
      if not node:
        continue
      method = node.pid + '.' + node.opName
      if method not in drag_by_method:
        drag_by_method[method] = []
      drag_by_method[method].append(drag_value)
      total_by_method[method] += drag_value
      methods_on_cp.add(method)
    traces_on_cp_by_method.update(methods_on_cp)

  root_mean_duration = float(np.mean(root_durations)) if root_durations else 1.0
  n_traces = len(root_durations)

  method_stats = []
  for method, drag_vals in drag_by_method.items():
    stats = _compute_stats(drag_vals)
    stats['method'] = method
    stats['exclusive_drag_sec'] = stats['mean']
    stats['relative_drag'] = (
        stats['mean'] / root_mean_duration if root_mean_duration > 0 else 0.0
    )
    stats['expected_per_trace_sec'] = (
        total_by_method[method] / n_traces if n_traces else 0.0
    )
    stats['cp_share'] = (
        traces_on_cp_by_method[method] / n_traces if n_traces else 0.0
    )
    method_stats.append(stats)

  sort_stat = (
      FLAGS.stat
      if FLAGS.stat
      in ['mean', 'p50', 'p90', 'p95', 'p99', 'expected_per_trace_sec']
      else 'mean'
  )
  method_stats.sort(key=lambda x: x[sort_stat], reverse=True)

  top_methods = method_stats[: FLAGS.top_k]
  for idx, item in enumerate(top_methods):
    item['rank'] = idx + 1

  res = {
      'mode': 'rank_drag',
      'top_k': FLAGS.top_k,
      'stat': sort_stat,
      'trace_count': len(collection.graphs),
      'root_mean_duration_sec': root_mean_duration,
      'precomputed_drag_traces': n_precomputed,
      'rankings': top_methods,
  }
  if percentile_start > 0.0 or percentile_end < 100.0:
    res['percentile_start'] = percentile_start
    res['percentile_end'] = percentile_end
  return res


def _collect_distribution_metrics(
    collection: GraphCollection,
    depgraph: Optional[DependencyGraph] = None,
    target_method: Optional[str] = None,
    target_service: Optional[str] = None,
) -> Tuple[List[float], List[float], List[float], List[float]]:
  """Collects duration, drag, and slack metrics from a collection state.

  Args:
    collection: The GraphCollection to collect metrics from.
    depgraph: The DependencyGraph used for slack calculation.
    target_method: Optional method name to filter on.
    target_service: Optional service name to filter on.

  Returns:
    A tuple of (durations, exclusive_drags, inclusive_drags, slacks).
  """
  durations, ex_drags, in_drags, slacks = [], [], [], []
  for g in collection.graphs.values():
    if not g.graph:
      continue
    cp = g.get_critical_path()
    ex_drag = cp.calculate_drag(exclusive=True).drag_per_span
    in_drag = cp.calculate_drag(exclusive=False).drag_per_span
    slk = cp.calculate_slack(depgraph).slack_per_span

    for sid, node in g.graph.nodeHT.items():
      if node is None:
        continue
      node_service = node.pid
      node_method_full = node.pid + '.' + node.opName

      if target_method and node_method_full != target_method:
        continue
      if target_service and node_service != target_service:
        continue
      if (
          not target_method
          and not target_service
          and (g.graph.rootNode is None or sid != g.graph.rootNode.sid)
      ):
        continue

      durations.append(node.duration)
      ex_drags.append(ex_drag.get(sid, 0.0))
      in_drags.append(in_drag.get(sid, 0.0))
      slacks.append(slk.get(sid, 0.0))
  return durations, ex_drags, in_drags, slacks


def execute_distribution(
    collection: GraphCollection, depgraph: Any
) -> Dict[str, Any]:
  """Analyzes impact of retimings on execution duration, slack, and drag.

  Args:
    collection: The GraphCollection to analyze.
    depgraph: The DependencyGraph used for slack calculation.

  Returns:
    A dictionary containing the distribution analysis results.
  """
  target_method = FLAGS.method
  target_service = FLAGS.service

  # Capture original
  orig_dur, orig_ex_drag, orig_in_drag, orig_slk = (
      _collect_distribution_metrics(
          collection,
          depgraph,
          target_method=target_method,
          target_service=target_service,
      )
  )

  retimed_dur: List[float] = []
  retimed_ex_drag: List[float] = []
  retimed_in_drag: List[float] = []
  retimed_slk: List[float] = []
  do_retime = should_retime()
  if do_retime:
    retimed_collection = copy.deepcopy(collection)
    apply_retimings(retimed_collection, depgraph)
    (
        retimed_dur,
        retimed_ex_drag,
        retimed_in_drag,
        retimed_slk,
    ) = _collect_distribution_metrics(
        retimed_collection,
        depgraph,
        target_method=target_method,
        target_service=target_service,
    )

  diff_dur = []
  if orig_dur and retimed_dur and len(orig_dur) == len(retimed_dur):
    diff_dur = [r - o for o, r in zip(orig_dur, retimed_dur)]

  all_metrics = {
      'duration': {'original': orig_dur, 'retimed': retimed_dur},
      'exclusive_drag': {'original': orig_ex_drag, 'retimed': retimed_ex_drag},
      'inclusive_drag': {'original': orig_in_drag, 'retimed': retimed_in_drag},
      'slack': {'original': orig_slk, 'retimed': retimed_slk},
      'duration_diff': {'original': [0.0] * len(diff_dur), 'retimed': diff_dur},
  }

  selected_metrics = {}
  if FLAGS.metric == 'all':
    selected_metrics = all_metrics
  else:
    if FLAGS.metric in all_metrics:
      selected_metrics[FLAGS.metric] = all_metrics[FLAGS.metric]

  summary = {}
  for m_name, values in selected_metrics.items():
    summary[m_name] = {
        'original_stats': _compute_stats(values['original']),
        'retimed_stats': _compute_stats(values['retimed']),
    }

  return {
      'mode': 'distribution',
      'target_method': target_method,
      'target_service': target_service,
      'with_retiming': do_retime,
      'metric_filter': FLAGS.metric,
      'metrics': selected_metrics,
      'summary': summary,
      'plot_drag_type': FLAGS.plot_drag_type,
  }


def execute_percent_improvement(
    collection: GraphCollection, depgraph: Any
) -> Dict[str, Any]:
  """Simulates system-wide retiming scenarios and computes percent improvements.

  Args:
    collection: The GraphCollection to analyze.
    depgraph: The DependencyGraph used for retiming.

  Returns:
    A dictionary containing the percent improvement analysis results.
  """
  retimed_collection = collection
  do_retime = should_retime()
  if do_retime:
    retimed_collection = copy.deepcopy(collection)
    apply_retimings(retimed_collection, depgraph)

  orig_graphs = {tid: g for tid, g in collection.graphs.items() if g.graph}
  retimed_graphs = {
      tid: g for tid, g in retimed_collection.graphs.items() if g.graph
  }
  common_trace_ids = [tid for tid in orig_graphs if tid in retimed_graphs]
  orig_durations = [orig_graphs[tid].get_duration() for tid in common_trace_ids]
  retimed_durations = [
      retimed_graphs[tid].get_duration() for tid in common_trace_ids
  ]

  saved_sec = [o - r for o, r in zip(orig_durations, retimed_durations)]
  percent_improvements = [
      (o - r) / o * 100.0 if o > 0 else 0.0
      for o, r in zip(orig_durations, retimed_durations)
  ]

  quantiles = {
      'orig_mean_sec': (
          float(np.mean(orig_durations)) if orig_durations else 0.0
      ),
      'retimed_mean_sec': (
          float(np.mean(retimed_durations)) if retimed_durations else 0.0
      ),
      'saved_mean_sec': float(np.mean(saved_sec)) if saved_sec else 0.0,
      'mean_percent_improvement': (
          float(np.mean(percent_improvements)) if percent_improvements else 0.0
      ),
      'p50_percent_improvement': (
          float(np.percentile(percent_improvements, 50))
          if percent_improvements
          else 0.0
      ),
      'p90_percent_improvement': (
          float(np.percentile(percent_improvements, 90))
          if percent_improvements
          else 0.0
      ),
      'p95_percent_improvement': (
          float(np.percentile(percent_improvements, 95))
          if percent_improvements
          else 0.0
      ),
      'p99_percent_improvement': (
          float(np.percentile(percent_improvements, 99))
          if percent_improvements
          else 0.0
      ),
  }

  return {
      'mode': 'percent_improvement',
      'trace_count': len(orig_durations),
      'with_retiming': do_retime,
      'original_durations_sec': orig_durations,
      'retimed_durations_sec': retimed_durations,
      'saved_sec': saved_sec,
      'percent_improvements': percent_improvements,
      'quantiles': quantiles,
  }


def _collect_descendants(
    node: Any, child_counts: Dict[str, int], visited: Set[Any]
) -> None:
  """Recursively collects descendant child methods and frequencies under a node.

  Args:
    node: The current GraphNode whose children are being traversed.
    child_counts: Dictionary mapping method name (pid.opName) to invocation
      count.
    visited: Set of visited span IDs (sid) to prevent cycles.
  """
  for child_node in node.children:
    if child_node.sid in visited:
      continue
    visited.add(child_node.sid)
    child_method_full = child_node.pid + '.' + child_node.opName
    child_counts[child_method_full] = child_counts.get(child_method_full, 0) + 1
    _collect_descendants(child_node, child_counts, visited)


def execute_child_methods_summary(
    collection: GraphCollection,
) -> Dict[str, Any]:
  """Lists all descendant child methods (direct and indirect) called under a parent."""
  target_method = FLAGS.method
  target_service = FLAGS.service

  if not target_method and not target_service:
    raise flags.ValidationError(
        'mode=child_methods requires specifying either --method or --service.'
    )
  if target_method and target_service:
    raise flags.ValidationError(
        'Cannot specify both --method and --service for child_methods mode.'
    )

  child_counts: Dict[str, int] = {}
  parent_match_count = 0

  for graph in collection.graphs.values():
    if not graph.graph:
      continue
    for node in graph.graph.nodeHT.values():
      if not node:
        continue

      # Match parent
      is_match = False
      node_method_full = node.pid + '.' + node.opName
      if target_method and node_method_full == target_method:
        is_match = True
      elif target_service and node.pid == target_service:
        is_match = True

      if is_match:
        parent_match_count += 1
        visited = {node.sid}
        _collect_descendants(node, child_counts, visited)

  # Convert to list sorted by count desc
  sorted_children = []
  for method, count in sorted(
      child_counts.items(), key=lambda x: x[1], reverse=True
  ):
    sorted_children.append({'child_method': method, 'count': count})

  return {
      'mode': 'child_methods',
      'target_parent': target_method or target_service,
      'parent_match_count': parent_match_count,
      'child_methods': sorted_children,
  }


def print_output(results: Dict[str, Any]) -> None:
  """Prints output to console in table, json, or csv format.

  Args:
    results: The analysis results dictionary to print.
  """
  out_format = FLAGS.format

  if out_format == 'json':
    print(json.dumps(results, indent=2))
    return

  mode = results.get('mode')

  if mode == 'rank_drag':
    rankings = results.get('rankings', [])
    if out_format == 'csv':
      df = pd.DataFrame(rankings)
      cols_to_scale = [
          'exclusive_drag_sec',
          'expected_per_trace_sec',
          'mean',
          'std',
          'p50',
          'p90',
          'p95',
          'p99',
      ]
      for col in cols_to_scale:
        if col in df.columns:
          df[col] = df[col] * 1000.0
      rename_map = {
          'exclusive_drag_sec': 'exclusive_drag_ms',
          'expected_per_trace_sec': 'expected_per_trace_ms',
          'mean': 'mean_ms',
          'std': 'std_ms',
          'p50': 'p50_ms',
          'p90': 'p90_ms',
          'p95': 'p95_ms',
          'p99': 'p99_ms',
      }
      df.rename(columns=rename_map, inplace=True)
      print(df.to_csv(index=False))
    else:
      print(f'\n=== Exclusive Drag Ranking (Top {results["top_k"]}) ===')
      if rankings:
        df = pd.DataFrame(rankings)
        cols = [
            'rank',
            'method',
            'exclusive_drag_sec',
            'relative_drag',
            'expected_per_trace_sec',
            'cp_share',
            'p50',
            'p90',
            'p95',
            'p99',
        ]
        df_display = df[[c for c in cols if c in df.columns]].copy()
        if 'relative_drag' in df_display.columns:
          df_display['relative_drag'] = df_display['relative_drag'] * 100.0

        if 'cp_share' in df_display.columns:
          df_display['cp_share'] = df_display['cp_share'] * 100.0
        # Scale to ms for printing
        for c in [
            'exclusive_drag_sec',
            'expected_per_trace_sec',
            'p50',
            'p90',
            'p95',
            'p99',
        ]:
          if c in df_display.columns:
            df_display[c] = df_display[c] * 1000.0

        rename_map = {
            'exclusive_drag_sec': 'exclusive_drag (ms)',
            'relative_drag': 'relative_drag (%)',
            'expected_per_trace_sec': 'expected_per_trace (ms)',
            'cp_share': 'cp_share (%)',
            'p50': 'p50 (ms)',
            'p90': 'p90 (ms)',
            'p95': 'p95 (ms)',
            'p99': 'p99 (ms)',
        }
        df_display.rename(columns=rename_map, inplace=True)
        print(df_display.to_string(index=False, float_format='%.6f'))

  elif mode == 'distribution':
    summary = results.get('summary', {})
    if out_format == 'csv':
      rows = []
      for metric, s_dict in summary.items():
        o = s_dict['original_stats']
        r = s_dict['retimed_stats']
        rows.append({
            'metric': metric,
            'orig_mean_ms': o['mean'] * 1000.0,
            'retimed_mean_ms': r['mean'] * 1000.0,
            'orig_p95_ms': o['p95'] * 1000.0,
            'retimed_p95_ms': r['p95'] * 1000.0,
        })
      print(pd.DataFrame(rows).to_csv(index=False))
    else:
      print('\n=== Metric Distribution Analysis ===')
      for metric, s_dict in summary.items():
        o = s_dict['original_stats']
        r = s_dict['retimed_stats']
        print(f'\nMetric: {metric}')
        print(
            f'  Original : Mean={o["mean"]*1000.0:.2f}ms,'
            f' p50={o["p50"]*1000.0:.2f}ms, p95={o["p95"]*1000.0:.2f}ms,'
            f' p99={o["p99"]*1000.0:.2f}ms'
        )
        if results.get('with_retiming'):
          print(
              f'  Retimed  : Mean={r["mean"]*1000.0:.2f}ms,'
              f' p50={r["p50"]*1000.0:.2f}ms, p95={r["p95"]*1000.0:.2f}ms,'
              f' p99={r["p99"]*1000.0:.2f}ms'
          )

  elif mode == 'percent_improvement':
    q = results.get('quantiles', {})
    if out_format == 'csv':
      q_ms = copy.deepcopy(q)
      for k in ['orig_mean_sec', 'retimed_mean_sec', 'saved_mean_sec']:
        if k in q_ms:
          q_ms[k] = q_ms[k] * 1000.0
      rename_map = {
          'orig_mean_sec': 'orig_mean_ms',
          'retimed_mean_sec': 'retimed_mean_ms',
          'saved_mean_sec': 'saved_mean_ms',
      }
      df = pd.DataFrame([q_ms])
      df.rename(columns=rename_map, inplace=True)
      print(df.to_csv(index=False))
    else:
      print('\n=== End-to-End Latency Retiming Percent Improvement ===')
      print(f'Traces Evaluated            : {results["trace_count"]}')
      print(f'Original Mean E2E Latency   : {q["orig_mean_sec"]*1000.0:.2f} ms')
      print(
          f'Retimed Mean E2E Latency    : {q["retimed_mean_sec"]*1000.0:.2f} ms'
      )
      print(
          f'Mean Absolute Time Saved    : {q["saved_mean_sec"]*1000.0:.2f} ms'
      )
      print(
          f'Mean Percent Improvement    : {q["mean_percent_improvement"]:.2f}%'
      )
      print(
          f'p50 Percent Improvement     : {q["p50_percent_improvement"]:.2f}%'
      )
      print(
          f'p95 Percent Improvement     : {q["p95_percent_improvement"]:.2f}%'
      )
      print(
          f'p99 Percent Improvement     : {q["p99_percent_improvement"]:.2f}%'
      )

  elif mode == 'child_methods':
    child_methods = results.get('child_methods', [])
    if out_format == 'csv':
      print(pd.DataFrame(child_methods).to_csv(index=False))
    else:
      print(
          f'\n=== Child Methods for Parent: {results["target_parent"]} (Parent'
          f' Matches: {results["parent_match_count"]}) ==='
      )
      if child_methods:
        df = pd.DataFrame(child_methods)
        print(df.to_string(index=False))
      else:
        print('No child methods found.')


def main(argv: Sequence[str]) -> None:
  del argv  # Unused.
  validate_flags()

  trace_path = _resolve_input_path(FLAGS.trace_path)
  export_data_path = _resolve_output_path(FLAGS.export_data_path)
  output_plot_path = _resolve_output_path(FLAGS.output_plot_path)

  collection, depgraph = loader.load_cached_traces(trace_path)

  # Filter collection if requested
  if FLAGS.mode == 'rank_drag':
    if FLAGS.root_method:
      subset = collection.get_graphs_subset(
          root_method_name=FLAGS.root_method,
      )
      collection = GraphCollection(graphs_list=subset)
  else:
    if (
        FLAGS.root_method
        or FLAGS.percentile_start > 0
        or FLAGS.percentile_end < 100
    ):
      subset = collection.get_graphs_subset(
          root_method_name=FLAGS.root_method,
          percentile_start=FLAGS.percentile_start,
          percentile_end=FLAGS.percentile_end,
      )
      collection = GraphCollection(graphs_list=subset)

  results = {}
  if FLAGS.mode == 'rank_drag':
    rank_collection = collection
    if should_retime():
      rank_collection = copy.deepcopy(collection)
      apply_retimings(rank_collection, depgraph)
    precomputed_drag = (
        loader.load_precomputed_drag(trace_path)
        if FLAGS.use_cached_drag and not should_retime()
        else None
    )
    results = execute_rank_drag(
        rank_collection,
        percentile_start=FLAGS.percentile_start,
        percentile_end=FLAGS.percentile_end,
        precomputed_drag=precomputed_drag,
    )
  elif FLAGS.mode == 'distribution':
    results = execute_distribution(collection, depgraph)
  elif FLAGS.mode == 'percent_improvement':
    results = execute_percent_improvement(collection, depgraph)
  elif FLAGS.mode == 'child_methods':
    results = execute_child_methods_summary(collection)

  # Console Stdout Output
  print_output(results)

  # File Data Export Mode
  if export_data_path:
    data_exporter.export_data(
        data=results,
        export_path=export_data_path,
        export_format=FLAGS.export_format,
    )

  # File Visual Plot Mode
  if output_plot_path or FLAGS.show_plot:
    if FLAGS.mode == 'rank_drag':
      plot_utils.plot_rank_drag(
          results, output_plot_path, show_plot=FLAGS.show_plot
      )
    elif FLAGS.mode == 'distribution':
      plot_utils.plot_distribution(
          results, output_plot_path, show_plot=FLAGS.show_plot
      )
    elif FLAGS.mode == 'percent_improvement':
      plot_utils.plot_percent_improvement(
          results, output_plot_path, show_plot=FLAGS.show_plot
      )


if __name__ == '__main__':
  app.run(main)
