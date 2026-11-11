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

"""Unit tests for Stage 2 unified trace analyzer tool."""

import collections
import contextlib
import copy
import io
import json
import os
import tempfile
from unittest import mock

from absl import flags
from absl.testing import absltest
import pandas as pd

import df_utils
import retimer
try:
  from . import data_exporter
  from . import loader
  from . import plot_utils
  from . import trace_analyzer
  from . import trace_cache_pb2
except ImportError:
  from agent.analysis import data_exporter
  from agent.analysis import loader
  from agent.analysis import plot_utils
  from agent.analysis import trace_analyzer
  from agent.analysis import trace_cache_pb2
from graph import CrispGraph
from graph import GraphCollection

FLAGS = flags.FLAGS

# Set dummy values for required flags to bypass absl validation
# during test execution
FLAGS.trace_path = 'dummy'
FLAGS.mode = 'rank_drag'


class TraceAnalyzerTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    test_srcdir = os.environ.get("TEST_SRCDIR", "")
    workspace = os.environ.get("TEST_WORKSPACE", "_main")
    candidate1 = os.path.join(test_srcdir, workspace, "test_cases/test_1.json")
    candidate2 = os.path.join(os.path.dirname(__file__), "../../test_cases/test_1.json")
    candidate3 = os.path.abspath("test_cases/test_1.json")
    for cand in [candidate1, candidate2, candidate3]:
      if os.path.exists(cand):
        self.test_data_path = cand
        break
    else:
      self.test_data_path = candidate2
    self.collection, self.depgraph = loader.load_cached_traces(
        self.test_data_path
    )
    self.temp_dir = tempfile.mkdtemp()
    # Reset all configuration flags to default values
    FLAGS.with_retiming = False
    FLAGS.remove_all_queuing = False
    FLAGS.cap_network_sec = None
    FLAGS.cap_network = None
    FLAGS.cap_network_ms = None
    FLAGS.retime_spec = None
    FLAGS.retime_method = []
    FLAGS.retime_percent = []
    FLAGS.retime_fixed_sec = []
    FLAGS.retime_fixed = []
    FLAGS.retime_fixed_us = []
    FLAGS.retime_max_lat_sec = []
    FLAGS.retime_max_lat = []
    FLAGS.retime_max_lat_us = []
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.root_method = None
    FLAGS.percentile_start = 0.0
    FLAGS.percentile_end = 100.0
    FLAGS.metric = 'all'

  def test_execute_rank_drag(self):
    FLAGS.top_k = 5
    FLAGS.stat = 'mean'
    FLAGS.percentile_start = 0.0
    FLAGS.percentile_end = 100.0
    results = trace_analyzer.execute_rank_drag(self.collection)
    self.assertEqual(results['mode'], 'rank_drag')
    self.assertIn('rankings', results)
    self.assertNotEmpty(results['rankings'])
    self.assertNotIn('percentile_start', results)
    self.assertNotIn('percentile_end', results)

  def test_execute_rank_drag_percentiles(self):
    # Filtered range -> percentile metadata present
    FLAGS.percentile_start = 10.0
    FLAGS.percentile_end = 90.0
    results = trace_analyzer.execute_rank_drag(
        self.collection,
        percentile_start=FLAGS.percentile_start,
        percentile_end=FLAGS.percentile_end,
    )
    self.assertEqual(results['percentile_start'], 10.0)
    self.assertEqual(results['percentile_end'], 90.0)

  def _jaeger_parent_end_tie(self) -> dict[str, object]:
    """One trace whose child ends exactly at the root's end (in us).

    With float32-only caches, end = float32(start) + float32(duration) lands
    a few hundred ns after float32(root end), the child is dropped as
    asynchronous, and its whole subtree leaves the critical path.
    """
    tid = 'tie'
    spans = [
        ('1', None, 'root', 'root', 0, 48124380),
        ('2', '1', 'ServiceA', 'ServiceA', 798909, 48124380),
        ('3', '2', 'ServiceB', 'ServiceB', 1763717, 48007303),
        ('4', '1', 'root', 'root [a - b]', 0, 798909),
    ]
    out = []
    for sid, parent, proc, op, start, end in spans:
      out.append({
          'traceID': tid,
          'spanID': sid,
          'operationName': op,
          # Relative microseconds.
          'startTime': start,
          'duration': end - start,
          'references': (
              [{'refType': 'CHILD_OF', 'traceID': tid, 'spanID': parent}]
              if parent
              else []
          ),
          'processID': proc,
      })
    processes = {
        p: {'serviceName': p} for p in ('root', 'ServiceA', 'ServiceB')
    }
    return {'data': [{'traceID': tid, 'spans': out, 'processes': processes}]}

  def _cp_and_drag(self, collection):
    out = {}
    for g in collection.graphs.values():
      cp = g.get_critical_path()
      drag = cp.calculate_drag(exclusive=True).drag_per_span
      out[str(g.trace_id)] = (
          [str(n.sid) for n in cp.cp],
          {str(k): round(v, 9) for k, v in drag.items()},
      )
    return out

  def _round_trip(self, collection, depgraph, legacy_float32_only=False):
    proto = data_exporter.build_trace_cache_proto(collection, depgraph)
    if legacy_float32_only:
      for span in proto.spans:
        for f in (
            'start_timestamp_sec_f64',
            'finish_timestamp_sec_f64',
            'duration_sec_f64',
            'exclusive_drag_sec_f64',
            'inclusive_drag_sec_f64',
            'slack_sec_f64',
        ):
          span.ClearField(f)
        span.component_deltas.ClearField('server_app_delta_f64')
    parsed = trace_cache_pb2.TraceCacheProto()
    parsed.ParseFromString(proto.SerializeToString())
    return GraphCollection(loader.proto_spans_to_df(parsed.spans)), parsed

  def test_cache_round_trip_preserves_critical_path(self):
    collection = GraphCollection(
        df_utils.get_df_from_jaeger_json(self._jaeger_parent_end_tie())
    )
    depgraph = collection.get_dependency_graph()
    original = self._cp_and_drag(collection)
    self.assertIn('2', original['tie'][0])  # ServiceA is on the CP.

    rebuilt, _ = self._round_trip(collection, depgraph)
    self.assertEqual(self._cp_and_drag(rebuilt), original)

  def test_legacy_float32_cache_changes_critical_path(self):
    # Documents the bug that the *_f64 fields fix: a float32-only cache drops
    # the ServiceA subtree and moves its time onto the root.
    collection = GraphCollection(
        df_utils.get_df_from_jaeger_json(self._jaeger_parent_end_tie())
    )
    depgraph = collection.get_dependency_graph()
    rebuilt, _ = self._round_trip(
        collection, depgraph, legacy_float32_only=True
    )
    cp, drag = self._cp_and_drag(rebuilt)['tie']
    self.assertNotIn('2', cp)
    self.assertGreater(drag['1'], 40.0)

  def test_execute_rank_drag_uses_precomputed_drag(self):
    FLAGS.top_k = 10
    FLAGS.stat = 'mean'
    collection = GraphCollection(
        df_utils.get_df_from_jaeger_json(self._jaeger_parent_end_tie())
    )
    depgraph = collection.get_dependency_graph()
    rebuilt, parsed = self._round_trip(
        collection, depgraph, legacy_float32_only=True
    )
    precomputed = {}
    for span in parsed.spans:
      if span.is_critical_path:
        precomputed.setdefault(span.trace_id, {})[
            span.span_id
        ] = span.exclusive_drag_sec
    recomputed = trace_analyzer.execute_rank_drag(rebuilt)
    stored = trace_analyzer.execute_rank_drag(
        rebuilt, precomputed_drag=precomputed
    )
    self.assertEqual(stored['precomputed_drag_traces'], 1)
    self.assertEqual(recomputed['precomputed_drag_traces'], 0)
    by_method = {r['method']: r for r in stored['rankings']}
    self.assertAlmostEqual(
        by_method['ServiceB.ServiceB']['expected_per_trace_sec'], 46.243586, places=4
    )
    self.assertEqual(by_method['ServiceB.ServiceB']['cp_share'], 1.0)
    # Expected drags partition the root duration.
    total = sum(r['expected_per_trace_sec'] for r in stored['rankings'])
    self.assertAlmostEqual(total, stored['root_mean_duration_sec'], places=4)
    recomputed_methods = {r['method'] for r in recomputed['rankings']}
    self.assertNotIn('ServiceB.ServiceB', recomputed_methods)

    proto = data_exporter.build_analysis_result_proto(stored)
    self.assertEqual(proto.rank_drag_result.precomputed_drag_traces, 1)
    proto_by_method = {
        r.method: r for r in proto.rank_drag_result.rankings
    }
    self.assertAlmostEqual(
        proto_by_method['ServiceB.ServiceB'].expected_per_trace_sec,
        46.243586,
        places=4,
    )
    self.assertAlmostEqual(
        proto_by_method['ServiceB.ServiceB'].cp_share, 1.0, places=5
    )
    df_proto = data_exporter._to_dataframe(proto)
    self.assertIn('expected_per_trace_sec', df_proto.columns)
    self.assertIn('cp_share', df_proto.columns)

  def test_load_precomputed_drag_json_cache(self):
    collection = GraphCollection(
        df_utils.get_df_from_jaeger_json(self._jaeger_parent_end_tie())
    )
    depgraph = collection.get_dependency_graph()
    proto = data_exporter.build_trace_cache_proto(collection, depgraph)
    path = os.path.join(self.temp_dir, 'tie_cache.json')
    data_exporter.export_data(proto, path, 'json')
    drag = loader.load_precomputed_drag(path)
    self.assertIn('tie', drag)
    self.assertAlmostEqual(drag['tie']['3'], 46.243586, places=6)
    self.assertEqual(loader.load_precomputed_drag(self.test_data_path), {})

  def test_execute_distribution(self):
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.metric = 'all'
    FLAGS.with_retiming = False
    results = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    self.assertEqual(results['mode'], 'distribution')
    self.assertIn('summary', results)

  def test_execute_distribution_duration_diff(self):
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.metric = 'duration_diff'
    FLAGS.with_retiming = True
    FLAGS.retime_spec = '{"S1": {"percent_diff": -50.0}}'
    results = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    self.assertEqual(results['mode'], 'distribution')
    self.assertIn('duration_diff', results['metrics'])
    diff_data = results['metrics']['duration_diff']
    self.assertNotEmpty(diff_data['retimed'])
    self.assertEqual(diff_data['original'], [0.0] * len(diff_data['retimed']))
    orig_stats = results['summary']['duration_diff']['original_stats']
    self.assertEqual(orig_stats['mean'], 0.0)
    self.assertEqual(orig_stats['p50'], 0.0)
    ret_stats = results['summary']['duration_diff']['retimed_stats']
    self.assertNotEqual(ret_stats['mean'], 0.0)

  def test_execute_distribution_duration_diff_no_retiming(self):
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.metric = 'duration_diff'
    FLAGS.with_retiming = False
    results = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    self.assertEqual(results['mode'], 'distribution')
    self.assertIn('duration_diff', results['metrics'])
    diff_data = results['metrics']['duration_diff']
    self.assertEmpty(diff_data['retimed'])
    self.assertEqual(diff_data['original'], [])
    orig_stats = results['summary']['duration_diff']['original_stats']
    self.assertEqual(orig_stats['mean'], 0.0)
    ret_stats = results['summary']['duration_diff']['retimed_stats']
    self.assertEqual(ret_stats['mean'], 0.0)

  def test_plot_distribution_duration_diff(self):
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.metric = 'duration_diff'
    FLAGS.with_retiming = True
    FLAGS.retime_spec = '{"S1": {"percent_diff": -50.0}}'
    dist_res = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    png_path = os.path.join(self.temp_dir, 'dist_duration_diff.png')
    plot_utils.plot_distribution(dist_res, png_path)
    self.assertTrue(os.path.exists(png_path))

  def test_execute_percent_improvement_with_retiming(self):
    FLAGS.with_retiming = True
    FLAGS.remove_all_queuing = True
    results = trace_analyzer.execute_percent_improvement(
        self.collection, self.depgraph
    )
    self.assertEqual(results['mode'], 'percent_improvement')
    self.assertIn('quantiles', results)
    self.assertIn('mean_percent_improvement', results['quantiles'])

  def test_execute_percent_improvement_trace_id_alignment(self):
    """Verifies that traces are matched by trace_id even if graph dict ordering differs."""
    mock_g1 = mock.create_autospec(CrispGraph, instance=True)
    mock_g1.graph = True
    mock_g1.get_duration.return_value = 10.0

    mock_g2 = mock.create_autospec(CrispGraph, instance=True)
    mock_g2.graph = True
    mock_g2.get_duration.return_value = 20.0

    mock_g1_retimed = mock.create_autospec(CrispGraph, instance=True)
    mock_g1_retimed.graph = True
    mock_g1_retimed.get_duration.return_value = 8.0  # saved 2.0

    mock_g2_retimed = mock.create_autospec(CrispGraph, instance=True)
    mock_g2_retimed.graph = True
    mock_g2_retimed.get_duration.return_value = 15.0  # saved 5.0

    orig_collection = mock.create_autospec(GraphCollection, instance=True)
    orig_collection.graphs = collections.OrderedDict([
        ('trace_1', mock_g1),
        ('trace_2', mock_g2),
    ])

    retimed_collection = mock.create_autospec(GraphCollection, instance=True)
    # Reversed dictionary iteration order
    retimed_collection.graphs = collections.OrderedDict([
        ('trace_2', mock_g2_retimed),
        ('trace_1', mock_g1_retimed),
    ])

    FLAGS.with_retiming = True
    with (
        mock.patch.object(trace_analyzer, 'should_retime', return_value=True),
        mock.patch.object(copy, 'deepcopy', return_value=retimed_collection),
        mock.patch.object(trace_analyzer, 'apply_retimings'),
    ):
      results = trace_analyzer.execute_percent_improvement(
          orig_collection, self.depgraph
      )

    # trace_1: orig=10.0, retimed=8.0, saved=2.0, pct=20%
    # trace_2: orig=20.0, retimed=15.0, saved=5.0, pct=25%
    # mean_percent_improvement should be (20% + 25%) / 2 = 22.5%
    self.assertAlmostEqual(
        results['quantiles']['mean_percent_improvement'], 22.5
    )
    self.assertAlmostEqual(results['quantiles']['saved_mean_sec'], 3.5)


  def test_export_proto_stage2(self):
    FLAGS.top_k = 5
    FLAGS.stat = 'mean'
    rank_res = trace_analyzer.execute_rank_drag(self.collection)

    out_pb = os.path.join(self.temp_dir, 'rank_res.pb')
    out_text = os.path.join(self.temp_dir, 'rank_res.textproto')

    data_exporter.export_data(rank_res, out_pb, export_format='proto')
    data_exporter.export_data(rank_res, out_text, export_format='proto')
    self.assertTrue(os.path.exists(out_pb))
    self.assertTrue(os.path.exists(out_text))

    # Test distribution export
    FLAGS.metric = 'all'
    FLAGS.with_retiming = True
    FLAGS.remove_all_queuing = True
    dist_res = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    dist_pb = os.path.join(self.temp_dir, 'dist_res.pb')
    data_exporter.export_data(dist_res, dist_pb, export_format='proto')
    self.assertTrue(os.path.exists(dist_pb))

  def test_plot_utils(self):
    FLAGS.top_k = 5
    FLAGS.stat = 'mean'
    rank_res = trace_analyzer.execute_rank_drag(self.collection)
    rank_png = os.path.join(self.temp_dir, 'rank.png')
    plot_utils.plot_rank_drag(rank_res, rank_png)
    self.assertTrue(os.path.exists(rank_png))

    FLAGS.metric = 'all'
    FLAGS.with_retiming = True
    dist_res = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    dist_png = os.path.join(self.temp_dir, 'dist.png')
    plot_utils.plot_distribution(dist_res, dist_png)
    self.assertTrue(os.path.exists(dist_png))

    pi_res = trace_analyzer.execute_percent_improvement(
        self.collection, self.depgraph
    )
    pi_png = os.path.join(self.temp_dir, 'pi.png')
    plot_utils.plot_percent_improvement(pi_res, pi_png)
    self.assertTrue(os.path.exists(pi_png))

  def test_combined_retiming_short_and_full_method(self):
    FLAGS.retime_spec = (
        '{"TestService": {"percent_diff": -10.0, "fixed_diff_sec": -0.000005,'
        ' "max_lat_sec": 0.000100}}'
    )
    FLAGS.with_retiming = True
    results = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    self.assertTrue(results['with_retiming'])

  def test_apply_retimings_precedence(self):
    FLAGS.retime_spec = (
        '{"S1": {"percent_diff": -10.0}, "S1.one": {"percent_diff": -50.0}}'
    )
    FLAGS.with_retiming = True

    test_coll = copy.deepcopy(self.collection)
    trace_analyzer.apply_retimings(test_coll, self.depgraph)

    graph = test_coll.graphs['A']
    node_s1_one = graph.graph.nodeHT['A']
    self.assertAlmostEqual(node_s1_one.duration, 50.0 / 1_000_000.0)

  def test_data_exporter_to_dataframe(self):
    # Test converting a rank_drag result dict to DataFrame
    rank_res = trace_analyzer.execute_rank_drag(self.collection)
    df_rank = data_exporter._to_dataframe(rank_res)
    self.assertFalse(df_rank.empty)
    self.assertIn('method', df_rank.columns)
    self.assertIn('exclusive_drag_sec', df_rank.columns)

    # Test converting a distribution result dict to DataFrame
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.metric = 'all'
    FLAGS.with_retiming = True
    FLAGS.retime_spec = '{"S1": {"percent_diff": -50.0}}'
    dist_res = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    df_dist = data_exporter._to_dataframe(dist_res)
    self.assertFalse(df_dist.empty)
    self.assertIn('slack_original', df_dist.columns)
    self.assertIn('slack_retimed', df_dist.columns)

    # Test converting AnalysisResultProto to DataFrame
    proto_rank = data_exporter.build_analysis_result_proto(rank_res)
    df_proto_rank = data_exporter._to_dataframe(proto_rank)
    self.assertFalse(df_proto_rank.empty)
    self.assertEqual(len(df_proto_rank), len(df_rank))

  def test_export_data_csv(self):
    # Test exporting Rank Drag to CSV
    FLAGS.top_k = 5
    FLAGS.stat = 'mean'
    FLAGS.percentile_start = 0.0
    FLAGS.percentile_end = 100.0
    rank_res = trace_analyzer.execute_rank_drag(self.collection)

    out_csv = os.path.join(self.temp_dir, 'rank.csv')
    data_exporter.export_data(rank_res, out_csv, export_format='csv')
    self.assertTrue(os.path.exists(out_csv))
    df = pd.read_csv(out_csv)
    self.assertIn('method', df.columns)

    # Test exporting from Proto
    proto_rank = data_exporter.build_analysis_result_proto(rank_res)
    out_csv_proto = os.path.join(self.temp_dir, 'rank_proto.csv')
    data_exporter.export_data(proto_rank, out_csv_proto, export_format='csv')
    self.assertTrue(os.path.exists(out_csv_proto))
    df_proto = pd.read_csv(out_csv_proto)
    self.assertEqual(len(df), len(df_proto))

  def test_plot_distribution_empty_data(self):
    # Should complete without error when metrics lists are empty
    empty_dist = {
        'mode': 'distribution',
        'metrics': {
            'slack': {'original': [], 'retimed': []},
            'exclusive_drag': {'original': [], 'retimed': []},
        },
    }
    png_path = os.path.join(self.temp_dir, 'empty_dist.png')
    plot_utils.plot_distribution(empty_dist, png_path)
    self.assertFalse(os.path.exists(png_path))

  def test_plot_percent_improvement_empty_data(self):
    empty_pi = {
        'mode': 'percent_improvement',
        'original_durations_sec': [],
    }
    empty_plot = os.path.join(self.temp_dir, 'empty_pi.png')
    plot_utils.plot_percent_improvement(empty_pi, empty_plot)
    self.assertFalse(os.path.exists(empty_plot))

  def test_to_dataframe_single_dispatch_all_types(self):
    # 1. pd.DataFrame
    df_in = pd.DataFrame({'col': [1, 2]})
    df_out = data_exporter._to_dataframe(df_in)
    self.assertIs(df_out, df_in)

    # 2. list of dicts
    list_in = [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]
    df_list = data_exporter._to_dataframe(list_in)
    self.assertLen(df_list, 2)
    self.assertEqual(list(df_list['a']), [1, 3])

    # 3. dict - rank_drag
    dict_rd = {
        'mode': 'rank_drag',
        'rankings': [{'method': 'm1', 'rank': 1}],
    }
    df_rd = data_exporter._to_dataframe(dict_rd)
    self.assertLen(df_rd, 1)
    self.assertEqual(df_rd['method'].iloc[0], 'm1')

    # 3. dict - distribution
    dict_dist = {
        'mode': 'distribution',
        'metrics': {
            'drag': {'original': [1.0], 'retimed': [0.5]},
        },
    }
    df_dist = data_exporter._to_dataframe(dict_dist)
    self.assertEqual(list(df_dist['drag_original']), [1.0])
    self.assertEqual(list(df_dist['drag_retimed']), [0.5])

    # 3. dict - percent_improvement
    dict_pi = {
        'mode': 'percent_improvement',
        'original_durations_sec': [1.0],
        'retimed_durations_sec': [0.5],
        'saved_sec': [0.5],
        'percent_improvements': [50.0],
    }
    df_pi = data_exporter._to_dataframe(dict_pi)
    self.assertLen(df_pi, 1)

    # 3. dict - child_methods
    dict_cm = {
        'mode': 'child_methods',
        'child_methods': [{'child_method': 'cm1', 'count': 5}],
    }
    df_cm = data_exporter._to_dataframe(dict_cm)
    self.assertLen(df_cm, 1)

    # 3. dict - generic and spans
    dict_gen = {'x': 10, 'y': 20}
    df_gen = data_exporter._to_dataframe(dict_gen)
    self.assertLen(df_gen, 1)
    dict_spans = {'spans': [{'span_id': 's1'}, {'span_id': 's2'}]}
    df_spans = data_exporter._to_dataframe(dict_spans)
    self.assertLen(df_spans, 2)

    # 4. TraceCacheProto
    cache_proto = trace_cache_pb2.TraceCacheProto()
    span = cache_proto.spans.add()
    span.trace_id = 't1'
    span.span_id = 's1'
    span.method_name = 'm1'
    span.duration_sec = 0.05
    span.exclusive_drag_sec = 0.01
    span.slack_sec = 0.02
    df_cache = data_exporter._to_dataframe(cache_proto)
    self.assertLen(df_cache, 1)
    self.assertEqual(df_cache['span_id'].iloc[0], 's1')

    # 5. AnalysisResultProto - rank_drag
    proto_rd = trace_cache_pb2.AnalysisResultProto(mode='rank_drag')
    r = proto_rd.rank_drag_result.rankings.add()
    r.rank = 1
    r.method = 'm1'
    r.exclusive_drag_sec = 0.01
    df_proto_rd = data_exporter._to_dataframe(proto_rd)
    self.assertLen(df_proto_rd, 1)
    self.assertEqual(df_proto_rd['method'].iloc[0], 'm1')

    # 5. AnalysisResultProto - distribution
    proto_dist = trace_cache_pb2.AnalysisResultProto(mode='distribution')
    proto_dist.distribution_result.metrics['drag'].original.append(1.0)
    proto_dist.distribution_result.metrics['drag'].retimed.append(0.5)
    df_proto_dist = data_exporter._to_dataframe(proto_dist)
    self.assertEqual(list(df_proto_dist['drag_original']), [1.0])
    self.assertEqual(list(df_proto_dist['drag_retimed']), [0.5])

    # 5. AnalysisResultProto - percent_improvement
    proto_pi = trace_cache_pb2.AnalysisResultProto(mode='percent_improvement')
    proto_pi.percent_improvement_result.original_durations_sec.append(1.0)
    proto_pi.percent_improvement_result.retimed_durations_sec.append(0.5)
    proto_pi.percent_improvement_result.saved_sec.append(0.5)
    proto_pi.percent_improvement_result.percent_improvements.append(50.0)
    df_proto_pi = data_exporter._to_dataframe(proto_pi)
    self.assertLen(df_proto_pi, 1)

    # 5. AnalysisResultProto - child_methods
    proto_cm = trace_cache_pb2.AnalysisResultProto(mode='child_methods')
    cm = proto_cm.child_methods_result.child_methods.add()
    cm.child_method = 'cm1'
    cm.count = 3
    df_proto_cm = data_exporter._to_dataframe(proto_cm)
    self.assertLen(df_proto_cm, 1)

    # 5. AnalysisResultProto - unsupported mode
    proto_bad = trace_cache_pb2.AnalysisResultProto(mode='unsupported')
    with self.assertRaises(ValueError):
      data_exporter._to_dataframe(proto_bad)

    # 6. Unsupported type
    with self.assertRaises(ValueError):
      data_exporter._to_dataframe(12345)

  def test_plot_distribution_all_drag_and_all_slack(self):
    # Test all-drag scenario (all spans have exclusive_drag > 0, slack = 0)
    all_drag_data = {
        'mode': 'distribution',
        'metric_filter': 'all',
        'plot_drag_type': 'exclusive',
        'metrics': {
            'exclusive_drag': {'original': [0.010, 0.020, 0.030]},
            'slack': {'original': [0.0, 0.0, 0.0]},
        },
    }
    all_drag_png = os.path.join(self.temp_dir, 'all_drag.png')
    plot_utils.plot_distribution(all_drag_data, all_drag_png)
    self.assertTrue(os.path.exists(all_drag_png))

    # Test all-slack scenario (all spans have slack > 0, exclusive_drag = 0)
    all_slack_data = {
        'mode': 'distribution',
        'metric_filter': 'all',
        'plot_drag_type': 'exclusive',
        'metrics': {
            'exclusive_drag': {'original': [0.0, 0.0, 0.0]},
            'slack': {'original': [0.010, 0.020, 0.030]},
        },
    }
    all_slack_png = os.path.join(self.temp_dir, 'all_slack.png')
    plot_utils.plot_distribution(all_slack_data, all_slack_png)
    self.assertTrue(os.path.exists(all_slack_png))

    # Test single metric filter scenario
    single_metric_data = {
        'mode': 'distribution',
        'metric_filter': 'duration',
        'metrics': {
            'duration': {
                'original': [0.005, 0.010],
                'retimed': [0.003, 0.008],
            },
        },
    }
    single_metric_png = os.path.join(self.temp_dir, 'single_metric.png')
    plot_utils.plot_distribution(single_metric_data, single_metric_png)
    self.assertTrue(os.path.exists(single_metric_png))

  def _create_multi_trace_collection(self):
    # 3 traces with durations 100, 200, 300
    rows = []
    # Trace A (dur = 100)
    rows.append({
        'trace_id': 'A',
        'span_id': 'A1',
        'parent_rpc_span_id': '0',
        'method_name': 'j1.m1',
        'server_job': 'j1',
        'client_start_timestamp': 0.0,
        'client_finish_timestamp': 100.0 / 1_000_000.0,
        'server_start_timestamp': 0.0,
        'server_finish_timestamp': 100.0 / 1_000_000.0,
        'server_app_delta': 100.0 / 1_000_000.0,
        'request_network_delta': 0.0,
        'response_network_delta': 0.0,
        'client_send_queue_delta': 0.0,
        'server_recv_queue_delta': 0.0,
        'client_recv_queue_delta': 0.0,
        'server_send_queue_delta': 0.0,
        'is_true_root': True,
        'num_descendants': 0,
        'num_children': 0,
        'client_user': 'u',
        'client_job': 'j',
        'server_user': 'su',
    })
    # Trace B (dur = 200)
    rows.append({
        'trace_id': 'B',
        'span_id': 'B1',
        'parent_rpc_span_id': '0',
        'method_name': 'j1.m1',
        'server_job': 'j1',
        'client_start_timestamp': 0.0,
        'client_finish_timestamp': 200.0 / 1_000_000.0,
        'server_start_timestamp': 0.0,
        'server_finish_timestamp': 200.0 / 1_000_000.0,
        'server_app_delta': 200.0 / 1_000_000.0,
        'request_network_delta': 0.0,
        'response_network_delta': 0.0,
        'client_send_queue_delta': 0.0,
        'server_recv_queue_delta': 0.0,
        'client_recv_queue_delta': 0.0,
        'server_send_queue_delta': 0.0,
        'is_true_root': True,
        'num_descendants': 0,
        'num_children': 0,
        'client_user': 'u',
        'client_job': 'j',
        'server_user': 'su',
    })
    # Trace C (dur = 300)
    rows.append({
        'trace_id': 'C',
        'span_id': 'C1',
        'parent_rpc_span_id': '0',
        'method_name': 'j1.m1',
        'server_job': 'j1',
        'client_start_timestamp': 0.0,
        'client_finish_timestamp': 300.0 / 1_000_000.0,
        'server_start_timestamp': 0.0,
        'server_finish_timestamp': 300.0 / 1_000_000.0,
        'server_app_delta': 300.0 / 1_000_000.0,
        'request_network_delta': 0.0,
        'response_network_delta': 0.0,
        'client_send_queue_delta': 0.0,
        'server_recv_queue_delta': 0.0,
        'client_recv_queue_delta': 0.0,
        'server_send_queue_delta': 0.0,
        'is_true_root': True,
        'num_descendants': 0,
        'num_children': 0,
        'client_user': 'u',
        'client_job': 'j',
        'server_user': 'su',
    })
    df = pd.DataFrame(rows)

    df = df_utils.preprocess(df, is_raw=False)
    return GraphCollection(df=df)

  def test_data_exporter_to_dataframe_no_retiming(self):
    FLAGS.method = None
    FLAGS.service = None
    FLAGS.metric = 'all'
    FLAGS.with_retiming = False
    dist_res = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    df_dist = data_exporter._to_dataframe(dist_res)
    self.assertFalse(df_dist.empty)
    self.assertIn('slack_original', df_dist.columns)
    # Check that '_retimed' columns are omitted when retiming is disabled
    for col in df_dist.columns:
      self.assertFalse(col.endswith('_retimed'))

  def test_execute_rank_drag_programmatic_filtering(self):
    collection = self._create_multi_trace_collection()
    # If we filter from 0% to 50% percentile, it should exclude the trace
    # with duration 300.
    # Wait, durations are [100, 200, 300]
    # start_index = max(0, 3 * 0 / 100) = 0
    # end_index = max(0, min(2, int(3 * 50 / 100) - 1))
    #           = max(0, min(2, 1 - 1)) = 0
    # percentile_start_val = durations[0] = 100
    # percentile_end_val = durations[0] = 100
    # So it should only include the trace with duration 100.
    FLAGS.top_k = 5
    FLAGS.stat = 'mean'
    results = trace_analyzer.execute_rank_drag(
        collection,
        percentile_start=0.0,
        percentile_end=50.0,
    )
    self.assertEqual(results['trace_count'], 1)
    # If we filter from 0% to 100% percentile, it should include all 3 traces
    results_all = trace_analyzer.execute_rank_drag(
        collection,
        percentile_start=0.0,
        percentile_end=100.0,
    )
    self.assertEqual(results_all['trace_count'], 3)

  def test_execute_distribution_service_filtering(self):
    collection = self._create_multi_trace_collection()
    # multi trace collection spans have server_job='j1' (opName) and
    # method_name='m1' (pid). This is a generic trace mapping.
    FLAGS.service = 'j1'
    FLAGS.method = None
    FLAGS.metric = 'all'
    results = trace_analyzer.execute_distribution(collection, self.depgraph)
    self.assertEqual(results['mode'], 'distribution')
    # Since all spans have server_job='j1', the summary for duration should
    # not be empty.
    self.assertIn('duration', results['summary'])
    self.assertNotEmpty(results['metrics']['duration']['original'])
    self.assertLen(results['metrics']['duration']['original'], 3)

    # If we filter for a non-existent service, it should be empty
    FLAGS.service = 'non_existent_service'
    results_empty = trace_analyzer.execute_distribution(
        collection, self.depgraph
    )
    self.assertEmpty(results_empty['metrics']['duration']['original'])

  def test_apply_retimings_restore_on_retry(self):
    """Verify apply_retimings restores original timestamps when queuing removal retries."""
    graph = self.collection.graphs['A']
    original_restore = graph.restore_to_original_timestamps
    mock_restore = mock.Mock(wraps=original_restore)
    graph.restore_to_original_timestamps = mock_restore

    original_remove = retimer.Retimer.remove_network_components
    call_count = 0

    def fake_remove_network_components(*args, **kwargs):
      """Side effect function simulating a transient failure on first call."""
      nonlocal call_count
      call_count += 1
      if call_count == 1:
        raise ValueError('Simulated noise error')
      return original_remove(*args, **kwargs)

    FLAGS.remove_all_queuing = True
    with mock.patch.object(
        retimer.Retimer,
        'remove_network_components',
        autospec=True,
        spec_set=True,
        side_effect=fake_remove_network_components,
    ):
      trace_analyzer.apply_retimings(self.collection, self.depgraph)

    mock_restore.assert_called()
    self.assertEqual(call_count, 2)

  def test_apply_retimings_two_field_key_matching(self):
    """Verify two-field key matching rules with exact method precedence."""
    # A (0-100)
    #   B (10-40) [S1.one]
    #   C (40-70) [S1.two]
    #   D (70-90) [S2.one]

    graph_obj = GraphCollection(
        df=df_utils.preprocess(
            pd.DataFrame([
                {
                    'trace_id': 'trace_matching',
                    'span_id': 'A',
                    'parent_rpc_span_id': '0',
                    'method_name': 'root',
                    'server_job': 'S1',
                    'client_start_timestamp': 0.0,
                    'client_finish_timestamp': 100.0 / 1_000_000.0,
                    'server_start_timestamp': 0.0,
                    'server_finish_timestamp': 100.0 / 1_000_000.0,
                    'server_app_delta': 100.0 / 1_000_000.0,
                    'request_network_delta': 0.0,
                    'response_network_delta': 0.0,
                    'client_send_queue_delta': 0.0,
                    'server_recv_queue_delta': 0.0,
                    'client_recv_queue_delta': 0.0,
                    'server_send_queue_delta': 0.0,
                    'is_true_root': True,
                    'num_descendants': 3,
                },
                {
                    'trace_id': 'trace_matching',
                    'span_id': 'B',
                    'parent_rpc_span_id': 'A',
                    'method_name': 'S1.one',
                    'server_job': 'S1',
                    'client_start_timestamp': 10.0 / 1_000_000.0,
                    'client_finish_timestamp': 40.0 / 1_000_000.0,
                    'server_start_timestamp': 10.0 / 1_000_000.0,
                    'server_finish_timestamp': 40.0 / 1_000_000.0,
                    'server_app_delta': 30.0 / 1_000_000.0,
                    'request_network_delta': 0.0,
                    'response_network_delta': 0.0,
                    'client_send_queue_delta': 0.0,
                    'server_recv_queue_delta': 0.0,
                    'client_recv_queue_delta': 0.0,
                    'server_send_queue_delta': 0.0,
                    'is_true_root': False,
                    'num_descendants': 0,
                },
                {
                    'trace_id': 'trace_matching',
                    'span_id': 'C',
                    'parent_rpc_span_id': 'A',
                    'method_name': 'S1.two',
                    'server_job': 'S1',
                    'client_start_timestamp': 40.0 / 1_000_000.0,
                    'client_finish_timestamp': 70.0 / 1_000_000.0,
                    'server_start_timestamp': 40.0 / 1_000_000.0,
                    'server_finish_timestamp': 70.0 / 1_000_000.0,
                    'server_app_delta': 30.0 / 1_000_000.0,
                    'request_network_delta': 0.0,
                    'response_network_delta': 0.0,
                    'client_send_queue_delta': 0.0,
                    'server_recv_queue_delta': 0.0,
                    'client_recv_queue_delta': 0.0,
                    'server_send_queue_delta': 0.0,
                    'is_true_root': False,
                    'num_descendants': 0,
                },
                {
                    'trace_id': 'trace_matching',
                    'span_id': 'D',
                    'parent_rpc_span_id': 'A',
                    'method_name': 'S2.one',
                    'server_job': 'S2',
                    'client_start_timestamp': 70.0 / 1_000_000.0,
                    'client_finish_timestamp': 90.0 / 1_000_000.0,
                    'server_start_timestamp': 70.0 / 1_000_000.0,
                    'server_finish_timestamp': 90.0 / 1_000_000.0,
                    'server_app_delta': 20.0 / 1_000_000.0,
                    'request_network_delta': 0.0,
                    'response_network_delta': 0.0,
                    'client_send_queue_delta': 0.0,
                    'server_recv_queue_delta': 0.0,
                    'client_recv_queue_delta': 0.0,
                    'server_send_queue_delta': 0.0,
                    'is_true_root': False,
                    'num_descendants': 0,
                },
            ]),
            is_raw=False,
        )
    )

    FLAGS.retime_spec = (
        '{"S1": {"percent_diff": -10.0}, "S1.one": {"percent_diff": -50.0}}'
    )
    FLAGS.with_retiming = True

    dep_graph = graph_obj.get_dependency_graph()
    trace_analyzer.apply_retimings(graph_obj, dep_graph)

    graph = graph_obj.graphs['trace_matching']
    node_b = graph.graph.nodeHT['B']
    node_c = graph.graph.nodeHT['C']
    node_d = graph.graph.nodeHT['D']

    # B [S1.one] matches exact S1.one -> -50% -> duration 15
    self.assertAlmostEqual(node_b.duration, 15.0 / 1_000_000.0)
    # C [S1.two] matches prefix S1 -> -10% -> duration 27
    self.assertAlmostEqual(node_c.duration, 27.0 / 1_000_000.0)
    # D [S2.one] does not match -> duration 20
    self.assertAlmostEqual(node_d.duration, 20.0 / 1_000_000.0)



  def test_validate_flags_success(self):
    # Case 1: with_retiming=True with remove_all_queuing=True
    FLAGS.with_retiming = True
    FLAGS.remove_all_queuing = True
    try:
      trace_analyzer.validate_flags()
    except flags.ValidationError as e:
      self.fail(f'validate_flags raised ValidationError unexpectedly: {e}')

    # Case 2: with_retiming=False with no rules
    FLAGS.with_retiming = False
    FLAGS.remove_all_queuing = False
    FLAGS.cap_network_sec = None
    FLAGS.cap_network = None
    FLAGS.cap_network_ms = None
    FLAGS.retime_spec = None
    FLAGS.retime_method = []
    try:
      trace_analyzer.validate_flags()
    except flags.ValidationError as e:
      self.fail(f'validate_flags raised ValidationError unexpectedly: {e}')

    # Case 3: with_retiming=True with cap_network_sec
    FLAGS.with_retiming = True
    FLAGS.remove_all_queuing = False
    FLAGS.cap_network_sec = 0.001
    try:
      trace_analyzer.validate_flags()
    except flags.ValidationError as e:
      self.fail(f'validate_flags raised ValidationError unexpectedly: {e}')
    FLAGS.cap_network_sec = None

  def test_validate_flags_missing_rules_error(self):
    # Case: with_retiming=True but no rules specified
    FLAGS.with_retiming = True
    FLAGS.remove_all_queuing = False
    FLAGS.cap_network_sec = None
    FLAGS.cap_network = None
    FLAGS.cap_network_ms = None
    FLAGS.retime_spec = None
    FLAGS.retime_method = []
    FLAGS.retime_percent = []
    FLAGS.retime_fixed_sec = []
    FLAGS.retime_fixed = []
    FLAGS.retime_fixed_us = []
    FLAGS.retime_max_lat_sec = []
    FLAGS.retime_max_lat = []
    FLAGS.retime_max_lat_us = []
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()

  def test_validate_flags_unused_rules_error(self):
    # Case: with_retiming=False but some rules are specified
    FLAGS.with_retiming = False

    # Test with remove_all_queuing
    FLAGS.remove_all_queuing = True
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.remove_all_queuing = False

    # Test with cap_network_sec
    FLAGS.cap_network_sec = 0.001
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.cap_network_sec = None

    # Test with cap_network alias
    FLAGS.cap_network = 0.001
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.cap_network = None

    # Test with cap_network_ms
    FLAGS.cap_network_ms = 1.0
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.cap_network_ms = None

    # Test with retime_spec
    FLAGS.retime_spec = '{}'
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.retime_spec = None

    # Test with retime_method
    FLAGS.retime_method = ['method']
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.retime_method = []

    # Test with retime_fixed_sec
    FLAGS.retime_fixed_sec = ['0.001']
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.retime_fixed_sec = []

  def test_normalize_rule(self):
    """Tests normalization of time keys to universal seconds."""
    # fixed_diff_sec & max_lat_sec (already seconds)
    r1 = trace_analyzer.normalize_rule(
        {'fixed_diff_sec': 0.02, 'max_lat_sec': 0.05}
    )
    self.assertEqual(r1['fixed_diff_sec'], 0.02)
    self.assertEqual(r1['max_lat_sec'], 0.05)

    # fixed_diff & max_lat (aliases in seconds)
    r2 = trace_analyzer.normalize_rule({'fixed_diff': 0.015, 'max_lat': 0.03})
    self.assertEqual(r2['fixed_diff_sec'], 0.015)
    self.assertEqual(r2['max_lat_sec'], 0.03)
    self.assertNotIn('fixed_diff', r2)
    self.assertNotIn('max_lat', r2)

    # fixed_diff_us & max_lat_us (legacy microseconds)
    r3 = trace_analyzer.normalize_rule(
        {'fixed_diff_us': -10000, 'max_lat_us': 2000}
    )
    self.assertAlmostEqual(r3['fixed_diff_sec'], -0.01)
    self.assertAlmostEqual(r3['max_lat_sec'], 0.002)
    self.assertNotIn('fixed_diff_us', r3)
    self.assertNotIn('max_lat_us', r3)

    # fixed_diff_ms & max_lat_ms (legacy milliseconds)
    r4 = trace_analyzer.normalize_rule(
        {'fixed_diff_ms': 15.0, 'max_lat_ms': 30.0}
    )
    self.assertAlmostEqual(r4['fixed_diff_sec'], 0.015)
    self.assertAlmostEqual(r4['max_lat_sec'], 0.03)
    self.assertNotIn('fixed_diff_ms', r4)
    self.assertNotIn('max_lat_ms', r4)

  def test_parse_retime_rules_seconds_flags(self):
    FLAGS.retime_method = ['S1.one']
    FLAGS.retime_percent = ['-30.0']
    FLAGS.retime_fixed_sec = ['0.010']
    FLAGS.retime_max_lat_sec = ['0.050']
    rules = trace_analyzer.parse_retime_rules()
    self.assertLen(rules, 1)
    self.assertEqual(rules[0]['method_name'], 'S1.one')
    self.assertEqual(rules[0]['percent_diff'], -30.0)
    self.assertEqual(rules[0]['fixed_diff_sec'], 0.010)
    self.assertEqual(rules[0]['max_lat_sec'], 0.050)

  def test_parse_retime_rules_alias_flags(self):
    FLAGS.retime_method = ['S1.one']
    FLAGS.retime_percent = ['-40.0']
    FLAGS.retime_fixed = ['0.020']
    FLAGS.retime_max_lat = ['0.080']
    rules = trace_analyzer.parse_retime_rules()
    self.assertLen(rules, 1)
    self.assertEqual(rules[0]['method_name'], 'S1.one')
    self.assertEqual(rules[0]['percent_diff'], -40.0)
    self.assertEqual(rules[0]['fixed_diff_sec'], 0.020)
    self.assertEqual(rules[0]['max_lat_sec'], 0.080)

  def test_parse_retime_rules_legacy_us_flags(self):
    FLAGS.retime_method = ['S1.one']
    FLAGS.retime_fixed_us = ['20000']
    FLAGS.retime_max_lat_us = ['50000']
    rules = trace_analyzer.parse_retime_rules()
    self.assertLen(rules, 1)
    self.assertEqual(rules[0]['method_name'], 'S1.one')
    self.assertAlmostEqual(rules[0]['fixed_diff_sec'], 0.02)
    self.assertAlmostEqual(rules[0]['max_lat_sec'], 0.05)

  def test_cap_network_seconds_and_legacy(self):
    # Test cap_network_sec in apply_retimings
    FLAGS.with_retiming = True
    FLAGS.cap_network_sec = 0.000010
    coll = copy.deepcopy(self.collection)
    trace_analyzer.apply_retimings(coll, self.depgraph)
    self.assertIsNotNone(coll)
    FLAGS.cap_network_sec = None

    # Test cap_network alias
    FLAGS.cap_network = 0.000010
    coll2 = copy.deepcopy(self.collection)
    trace_analyzer.apply_retimings(coll2, self.depgraph)
    self.assertIsNotNone(coll2)
    FLAGS.cap_network = None

    # Test legacy cap_network_ms
    FLAGS.cap_network_ms = 0.010
    coll3 = copy.deepcopy(self.collection)
    trace_analyzer.apply_retimings(coll3, self.depgraph)
    self.assertIsNotNone(coll3)
    FLAGS.cap_network_ms = None

  def test_execute_child_methods_summary(self):
    # In test_1.json, S1.one is the root, which invokes S2.two, which
    # invokes S3.three.
    FLAGS.method = 'S1.one'
    FLAGS.service = None
    FLAGS.mode = 'child_methods'

    results = trace_analyzer.execute_child_methods_summary(self.collection)
    self.assertEqual(results['mode'], 'child_methods')
    self.assertEqual(results['target_parent'], 'S1.one')
    self.assertEqual(results['parent_match_count'], 1)

    child_methods = [c['child_method'] for c in results['child_methods']]
    self.assertIn('S2.two', child_methods)
    self.assertIn('S3.three', child_methods)

  def test_collect_descendants_cycle_avoidance(self):
    node_a = mock.MagicMock(sid='span_a', pid='S1', opName='m1', children=[])
    node_b = mock.MagicMock(sid='span_b', pid='S2', opName='m2', children=[])
    node_c = mock.MagicMock(sid='span_c', pid='S3', opName='m3', children=[])

    # Form a cycle: A -> B -> C -> A (and self-loop on C -> C)
    node_a.children = [node_b]
    node_b.children = [node_c]
    node_c.children = [node_a, node_c]

    child_counts = {}
    visited = {node_a.sid}

    # Should traverse without recursion error or infinite loop
    trace_analyzer._collect_descendants(node_a, child_counts, visited)

    self.assertEqual(child_counts, {'S2.m2': 1, 'S3.m3': 1})
    self.assertEqual(visited, {'span_a', 'span_b', 'span_c'})

  def test_file_based_retime_spec(self):
    spec_data = {
        'SocialGraph.Follow': {'percent_diff': -50.0},
        'StorageService': {'fixed_diff_us': -10000},
    }
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
      json.dump(spec_data, tmp_file)
      tmp_file_path = tmp_file.name

    try:
      FLAGS.retime_spec = tmp_file_path
      rules = trace_analyzer.parse_retime_rules()
      self.assertLen(rules, 2)

      method_rule = next(
          (
              r
              for r in rules
              if r.get('method_name') == 'SocialGraph.Follow'
          ),
          None,
      )
      self.assertIsNotNone(method_rule)
      self.assertEqual(method_rule['percent_diff'], -50.0)

      service_rule = next(
          (r for r in rules if r.get('service_name') == 'StorageService'), None
      )
      self.assertIsNotNone(service_rule)
      self.assertEqual(service_rule['fixed_diff_sec'], -0.01)
    finally:
      os.remove(tmp_file_path)

  def test_file_based_retime_spec_invalid_json(self):
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
      tmp_file.write('{invalid_json')
      tmp_file_path = tmp_file.name

    try:
      FLAGS.retime_spec = tmp_file_path
      with self.assertRaises(flags.ValidationError):
        trace_analyzer.parse_retime_rules()
    finally:
      os.remove(tmp_file_path)

  def test_parse_retime_rules_target_type_and_prefixes(self):
    FLAGS.retime_spec = json.dumps({
        'dotted.service': {'target_type': 'service', 'percent_diff': -20.0},
        'plain_method': {'target_type': 'method', 'percent_diff': -30.0},
        'service:prefixed.service': {'percent_diff': -40.0},
        'method:prefixed.method': {'percent_diff': -50.0},
    })
    rules = trace_analyzer.parse_retime_rules()
    self.assertLen(rules, 4)

    dotted_svc = next(
        (r for r in rules if r.get('service_name') == 'dotted.service'), None
    )
    self.assertIsNotNone(dotted_svc)
    self.assertEqual(dotted_svc['percent_diff'], -20.0)

    plain_m = next(
        (r for r in rules if r.get('method_name') == 'plain_method'), None
    )
    self.assertIsNotNone(plain_m)
    self.assertEqual(plain_m['percent_diff'], -30.0)

    prefixed_svc = next(
        (r for r in rules if r.get('service_name') == 'prefixed.service'), None
    )
    self.assertIsNotNone(prefixed_svc)
    self.assertEqual(prefixed_svc['percent_diff'], -40.0)

    prefixed_m = next(
        (r for r in rules if r.get('method_name') == 'prefixed.method'), None
    )
    self.assertIsNotNone(prefixed_m)
    self.assertEqual(prefixed_m['percent_diff'], -50.0)

  def test_apply_retimings_matches_op_name(self):
    FLAGS.with_retiming = True
    FLAGS.retime_spec = json.dumps(
        {'one': {'target_type': 'method', 'percent_diff': -50.0}}
    )
    coll = copy.deepcopy(self.collection)
    trace_analyzer.apply_retimings(coll, self.depgraph)
    # Verify method 'one' (full name S1.one) was retimed
    g = coll.graphs['A']
    node = g.graph.nodeHT['A']
    self.assertAlmostEqual(node.duration, 50.0 / 1_000_000.0)

  def test_apply_retimings_error_recovery(self):
    FLAGS.with_retiming = True
    FLAGS.remove_all_queuing = True
    FLAGS.cap_network_sec = 0.01
    FLAGS.retime_spec = json.dumps(
        {'one': {'target_type': 'method', 'percent_diff': -50.0}}
    )
    coll = copy.deepcopy(self.collection)

    with (
        mock.patch.object(
            retimer.Retimer,
            'remove_network_components',
            autospec=True,
            spec_set=True,
            side_effect=ValueError('Queuing removal failed'),
        ),
        mock.patch.object(
            retimer.Retimer,
            'retime_network_components',
            autospec=True,
            spec_set=True,
            side_effect=ValueError('Network capping failed'),
        ),
        self.assertLogs(level='WARNING') as log_output,
    ):
      trace_analyzer.apply_retimings(coll, self.depgraph)
      self.assertGreaterEqual(len(log_output.output), 2)
      # Verify baseline was restored and per-method retiming was re-applied
      node = coll.graphs['A'].graph.nodeHT['A']
      self.assertAlmostEqual(node.duration, 50.0 / 1_000_000.0)

  def test_execute_distribution_inclusive_drag_metric(self):
    FLAGS.method = 'S1.one'
    FLAGS.service = None
    FLAGS.metric = 'inclusive_drag'
    FLAGS.with_retiming = False
    results = trace_analyzer.execute_distribution(
        self.collection, self.depgraph
    )
    self.assertEqual(list(results['metrics'].keys()), ['inclusive_drag'])
    self.assertNotEmpty(results['metrics']['inclusive_drag']['original'])

  def test_print_output_rank_drag_csv_scales_expected_per_trace(self):
    FLAGS.top_k = 5
    FLAGS.stat = 'expected_per_trace_sec'
    FLAGS.format = 'csv'
    rank_res = trace_analyzer.execute_rank_drag(self.collection)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
      trace_analyzer.print_output(rank_res)
    csv_df = pd.read_csv(io.StringIO(buf.getvalue()))
    self.assertIn('expected_per_trace_ms', csv_df.columns)
    self.assertNotIn('expected_per_trace_sec', csv_df.columns)
    by_method_sec = {
        r['method']: r['expected_per_trace_sec'] for r in rank_res['rankings']
    }
    first_row = csv_df.iloc[0]
    self.assertAlmostEqual(
        first_row['expected_per_trace_ms'],
        by_method_sec[first_row['method']] * 1000.0,
        places=6,
    )

    plot_path = os.path.join(self.temp_dir, 'rank_expected.png')
    plot_utils.plot_rank_drag(rank_res, plot_path)
    self.assertTrue(os.path.exists(plot_path))

  def test_main_build_working_directory_and_dotted_root_method(self):
    rel_trace = 'rel_trace.json'
    with open(self.test_data_path, 'rb') as src, open(
        os.path.join(self.temp_dir, rel_trace), 'wb'
    ) as dst:
      dst.write(src.read())

    old_bwd = os.environ.get('BUILD_WORKING_DIRECTORY')
    old_trace = FLAGS.trace_path
    old_mode = FLAGS.mode
    old_root = FLAGS.root_method
    old_export = FLAGS.export_data_path
    old_plot = FLAGS.output_plot_path
    old_retime = FLAGS.with_retiming
    try:
      os.environ['BUILD_WORKING_DIRECTORY'] = self.temp_dir
      FLAGS.trace_path = rel_trace
      FLAGS.mode = 'rank_drag'
      FLAGS.root_method = 'S1.one'
      FLAGS.export_data_path = 'out/rank.json'
      FLAGS.output_plot_path = 'out/rank.png'
      FLAGS.with_retiming = False
      trace_analyzer.main([])
    finally:
      FLAGS.trace_path = old_trace
      FLAGS.mode = old_mode
      FLAGS.root_method = old_root
      FLAGS.export_data_path = old_export
      FLAGS.output_plot_path = old_plot
      FLAGS.with_retiming = old_retime
      if old_bwd is None:
        os.environ.pop('BUILD_WORKING_DIRECTORY', None)
      else:
        os.environ['BUILD_WORKING_DIRECTORY'] = old_bwd

    out_json = os.path.join(self.temp_dir, 'out/rank.json')
    out_png = os.path.join(self.temp_dir, 'out/rank.png')
    self.assertTrue(os.path.exists(out_json))
    self.assertTrue(os.path.exists(out_png))
    with open(out_json, 'r', encoding='utf-8') as f:
      exported = json.load(f)
    self.assertEqual(exported['trace_count'], 1)

  def test_main_rank_drag_with_retiming_applies_rules(self):
    cache_pb = os.path.join(self.temp_dir, 'cache.pb')
    cache_proto = data_exporter.build_trace_cache_proto(
        self.collection, self.depgraph
    )
    data_exporter.export_data(cache_proto, cache_pb, export_format='proto')

    baseline_json = os.path.join(self.temp_dir, 'rank_base.json')
    retimed_json = os.path.join(self.temp_dir, 'rank_retimed.json')

    old_trace = FLAGS.trace_path
    old_mode = FLAGS.mode
    old_export = FLAGS.export_data_path
    old_export_fmt = FLAGS.export_format
    old_retime = FLAGS.with_retiming
    old_spec = FLAGS.retime_spec
    try:
      FLAGS.trace_path = cache_pb
      FLAGS.mode = 'rank_drag'
      FLAGS.export_format = 'json'
      FLAGS.export_data_path = baseline_json
      FLAGS.with_retiming = False
      FLAGS.retime_spec = None
      trace_analyzer.main([])

      FLAGS.export_data_path = retimed_json
      FLAGS.with_retiming = True
      FLAGS.retime_spec = '{"S2.two": {"percent_diff": -90.0}}'
      trace_analyzer.main([])
    finally:
      FLAGS.trace_path = old_trace
      FLAGS.mode = old_mode
      FLAGS.export_data_path = old_export
      FLAGS.export_format = old_export_fmt
      FLAGS.with_retiming = old_retime
      FLAGS.retime_spec = old_spec

    with open(baseline_json, 'r', encoding='utf-8') as f:
      base_data = json.load(f)
    with open(retimed_json, 'r', encoding='utf-8') as f:
      ret_data = json.load(f)

    self.assertEqual(base_data['precomputed_drag_traces'], 1)
    self.assertEqual(ret_data['precomputed_drag_traces'], 0)
    self.assertLess(
        ret_data['root_mean_duration_sec'], base_data['root_mean_duration_sec']
    )

  def test_validate_flags_method_adjustment_and_percentile_bounds(self):
    FLAGS.with_retiming = True
    FLAGS.retime_method = []
    FLAGS.retime_percent = ['-50.0']
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.retime_percent = []

    FLAGS.with_retiming = False
    FLAGS.percentile_start = 95.0
    FLAGS.percentile_end = 90.0
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()

    FLAGS.percentile_start = -1.0
    FLAGS.percentile_end = 100.0
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()

    FLAGS.percentile_start = 0.0
    FLAGS.percentile_end = 101.0
    with self.assertRaises(flags.ValidationError):
      trace_analyzer.validate_flags()
    FLAGS.percentile_end = 100.0


if __name__ == '__main__':
  absltest.main()
