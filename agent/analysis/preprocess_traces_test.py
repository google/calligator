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

"""Unit tests for Stage 1 trace preprocessing pipeline."""

import json
import os
import tempfile

from absl import flags
from absl.testing import absltest

try:
  from . import data_exporter
  from . import loader
  from . import preprocess_traces
  from . import trace_cache_pb2
except ImportError:
  from agent.analysis import data_exporter
  from agent.analysis import loader
  from agent.analysis import preprocess_traces
  from agent.analysis import trace_cache_pb2

FLAGS = flags.FLAGS
FLAGS.input_path = 'dummy'
FLAGS.cache_output_path = 'dummy'


class PreprocessTracesTest(absltest.TestCase):

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
    self.temp_dir = tempfile.mkdtemp()

  def test_main_cli_execution(self):
    output_pb = os.path.join(self.temp_dir, 'cli_output.pb')
    old_input = FLAGS.input_path
    old_output = FLAGS.cache_output_path
    old_format = FLAGS.cache_format
    old_max = FLAGS.max_traces
    try:
      FLAGS.input_path = self.test_data_path
      FLAGS.cache_output_path = output_pb
      FLAGS.cache_format = 'proto'
      FLAGS.max_traces = 10
      preprocess_traces.main([])
    finally:
      FLAGS.input_path = old_input
      FLAGS.cache_output_path = old_output
      FLAGS.cache_format = old_format
      FLAGS.max_traces = old_max

    self.assertTrue(os.path.exists(output_pb))
    coll, dep = loader.load_cached_traces(output_pb)
    self.assertNotEmpty(coll.graphs)
    self.assertIsNotNone(dep)

  def test_preprocess_and_export_proto(self):
    collection, depgraph = loader.load_cached_traces(self.test_data_path)
    self.assertNotEmpty(collection.graphs)
    self.assertIsNotNone(depgraph)

    cache_proto = data_exporter.build_trace_cache_proto(
        collection, depgraph, input_source=self.test_data_path
    )
    self.assertLen(collection.graphs, cache_proto.trace_count)
    self.assertNotEmpty(cache_proto.spans)

    output_pb = os.path.join(self.temp_dir, 'cache.pb')
    data_exporter.export_data(cache_proto, output_pb, export_format='proto')
    self.assertTrue(os.path.exists(output_pb))

    # Read back proto cache
    reloaded_coll, reloaded_dep = loader.load_cached_traces(output_pb)
    self.assertEqual(len(reloaded_coll.graphs), len(collection.graphs))
    self.assertIsNotNone(reloaded_dep)

    # Test textproto export and reload
    output_textproto = os.path.join(self.temp_dir, 'cache.textproto')
    data_exporter.export_data(
        cache_proto, output_textproto, export_format='proto'
    )
    self.assertTrue(os.path.exists(output_textproto))

    reloaded_coll_text, reloaded_dep_text = loader.load_cached_traces(
        output_textproto
    )
    self.assertEqual(len(reloaded_coll_text.graphs), len(collection.graphs))
    self.assertIsNotNone(reloaded_dep_text)

  def test_preprocess_and_export_json(self):
    collection, depgraph = loader.load_cached_traces(self.test_data_path)
    cache_proto = data_exporter.build_trace_cache_proto(
        collection, depgraph, input_source=self.test_data_path
    )

    output_json = os.path.join(self.temp_dir, 'cache.json')
    data_exporter.export_data(cache_proto, output_json, export_format='json')
    self.assertTrue(os.path.exists(output_json))

    # Read back JSON cache
    reloaded_coll, _ = loader.load_cached_traces(output_json)
    self.assertEqual(len(reloaded_coll.graphs), len(collection.graphs))

  def test_detect_input_format(self):
    self.assertEqual(
        loader.detect_input_format('foo.pb', ['foo.pb']),
        'PROTO_CACHE_BINARY',
    )
    self.assertEqual(
        loader.detect_input_format('foo.textproto', ['foo.textproto']),
        'PROTO_CACHE_TEXT',
    )


    # Test JSON formats
    jaeger_json = os.path.join(self.temp_dir, 'jaeger.json')
    with open(jaeger_json, 'w') as f:
      json.dump({'data': []}, f)
    self.assertEqual(
        loader.detect_input_format(jaeger_json, [jaeger_json]),
        'JAEGER_RAW_JSON',
    )

    cache_json = os.path.join(self.temp_dir, 'cache.json')
    with open(cache_json, 'w') as f:
      json.dump({'spans': []}, f)
    self.assertEqual(
        loader.detect_input_format(cache_json, [cache_json]),
        'JSON_CACHE',
    )

  def test_load_cached_traces_gzip_json(self):
    """Verifies transparent reading of gzip-compressed .json.gz trace files."""
    import gzip
    with open(self.test_data_path, 'rb') as f_in:
      raw_data = f_in.read()

    gz_path = os.path.join(self.temp_dir, 'traces.json.gz')
    with gzip.open(gz_path, 'wb') as f_out:
      f_out.write(raw_data)

    self.assertEqual(
        loader.detect_input_format(gz_path, [gz_path]),
        'JAEGER_RAW_JSON',
    )
    coll, dep = loader.load_cached_traces(gz_path)
    self.assertGreater(len(coll.graphs), 0)
    self.assertIsNotNone(dep)


  def test_detect_input_format_invalid_json(self):
    bad_json = os.path.join(self.temp_dir, 'corrupt.json')
    with open(bad_json, 'w') as f:
      f.write('{ invalid json content')
    with self.assertRaises(ValueError) as ctx:
      loader.detect_input_format(bad_json, [bad_json])
    self.assertIn('Failed to parse JSON file', str(ctx.exception))

  def test_loader_glob_failures(self):
    non_existent = os.path.join(self.temp_dir, 'missing*.pb')
    with self.assertRaises(FileNotFoundError):
      loader.load_cached_traces(non_existent)

  def test_depgraph_proto_to_obj_none(self):
    dep = loader.depgraph_proto_to_obj(None)
    self.assertIsNotNone(dep)
    self.assertEqual(dep.deps, {})

  def test_proto_and_dict_spans_to_df_empty(self):
    df_proto = loader.proto_spans_to_df([])
    self.assertTrue(df_proto.empty)
    df_dict = loader.dict_spans_to_df([])
    self.assertTrue(df_dict.empty)

  def test_corrupt_cache_files_raise_value_error(self):
    bad_pb = os.path.join(self.temp_dir, 'bad.pb')
    with open(bad_pb, 'wb') as f:
      f.write(b'\xff\xff\xff\xff')
    with self.assertRaises(ValueError):
      loader.load_cached_traces(bad_pb)

    bad_text = os.path.join(self.temp_dir, 'bad.textproto')
    with open(bad_text, 'w') as f:
      f.write('invalid text proto content {{{')
    with self.assertRaises(ValueError):
      loader.load_cached_traces(bad_text)

    bad_json = os.path.join(self.temp_dir, 'bad_cache.json')
    with open(bad_json, 'w') as f:
      f.write('{"spans": [ {invalid json')
    with self.assertRaises(ValueError):
      loader.load_cached_traces(bad_json)

  def test_invalid_cache_proto_validation(self):
    proto = trace_cache_pb2.TraceCacheProto()
    with self.assertRaises(ValueError) as ctx:
      loader.validate_cache_proto(proto)
    self.assertIn('contains no spans', str(ctx.exception))

    span = proto.spans.add()
    span.span_id = '123'
    with self.assertRaises(ValueError) as ctx:
      loader.validate_cache_proto(proto)
    self.assertIn('missing a valid dependency graph', str(ctx.exception))

    proto.depgraph.nodes.add(node_key='A')
    with self.assertRaises(ValueError) as ctx:
      loader.validate_cache_proto(proto)
    self.assertIn('missing pre-computed exclusive_drag_sec', str(ctx.exception))

    span.exclusive_drag_sec = 0.000010
    with self.assertRaises(ValueError) as ctx:
      loader.validate_cache_proto(proto)
    self.assertIn('missing pre-computed slack_sec', str(ctx.exception))

  def test_invalid_cache_json_validation(self):
    with self.assertRaises(ValueError):
      loader.validate_cache_json({})

    with self.assertRaises(ValueError):
      loader.validate_cache_json({'spans': [{'span_id': '1'}]})

    content = {
        'spans': [{'span_id': '1'}],
        'depgraph': {'nodes': [{'node_key': 'A'}]},
    }
    with self.assertRaises(ValueError) as ctx:
      loader.validate_cache_json(content)
    self.assertIn('missing pre-computed exclusive_drag_sec', str(ctx.exception))

    # *_f64-only fields satisfy both proto and JSON cache validation
    f64_proto = trace_cache_pb2.TraceCacheProto()
    f64_proto.depgraph.nodes.add(node_key='A')
    f64_span = f64_proto.spans.add(
        span_id='1', exclusive_drag_sec_f64=0.01, slack_sec_f64=0.0
    )
    self.assertFalse(f64_span.HasField('exclusive_drag_sec'))
    loader.validate_cache_proto(f64_proto)

    loader.validate_cache_json({
        'spans': [{
            'span_id': '1',
            'exclusive_drag_sec_f64': 0.01,
            'slack_sec_f64': 0.0,
        }],
        'depgraph': {'nodes': [{'node_key': 'A'}]},
    })

  def test_build_working_directory_relative_paths(self):
    rel_input = 'rel_input.json'
    with open(self.test_data_path, 'rb') as src, open(
        os.path.join(self.temp_dir, rel_input), 'wb'
    ) as dst:
      dst.write(src.read())

    old_input = FLAGS.input_path
    old_output = FLAGS.cache_output_path
    old_format = FLAGS.cache_format
    old_bwd = os.environ.get('BUILD_WORKING_DIRECTORY')
    try:
      os.environ['BUILD_WORKING_DIRECTORY'] = self.temp_dir
      FLAGS.input_path = rel_input
      FLAGS.cache_output_path = 'sub/rel_cache.pb'
      FLAGS.cache_format = 'proto'
      preprocess_traces.main([])
    finally:
      FLAGS.input_path = old_input
      FLAGS.cache_output_path = old_output
      FLAGS.cache_format = old_format
      if old_bwd is None:
        os.environ.pop('BUILD_WORKING_DIRECTORY', None)
      else:
        os.environ['BUILD_WORKING_DIRECTORY'] = old_bwd

    expected_out = os.path.join(self.temp_dir, 'sub/rel_cache.pb')
    self.assertTrue(os.path.exists(expected_out))

  def test_spans_to_df_drops_null_spans(self):
    # 1. Dict spans with null fields: corrupted trace t1 is dropped, valid
    # trace t2 is retained.
    spans_data = [
        {
            'trace_id': 't1',
            'span_id': 's1',
            'method_name': 'm1',
            'server_job': 'job1',
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
            'component_deltas': {'server_app_delta': 1.0},
        },
        {
            'trace_id': 't1',
            'span_id': 's2',
            'method_name': None,
            'server_job': None,
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
        },
        {
            'trace_id': 't1',
            'span_id': 's3',
            'method_name': 'm3',
            'server_job': 'job1',
            'start_timestamp_sec': None,
            'finish_timestamp_sec': 2.0,
        },
        {
            'trace_id': 't2',
            'span_id': 's4',
            'method_name': 'm4',
            'server_job': 'job2',
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
            'component_deltas': {'server_app_delta': 1.0},
        },
        {
            'trace_id': 't2',
            'span_id': 's5',
            'method_name': 'm5',
            'server_job': 'job2',
            'start_timestamp_sec': 2.0,
            'finish_timestamp_sec': 3.0,
            'component_deltas': {'server_app_delta': 1.0},
        },
    ]
    df = loader.dict_spans_to_df(spans_data)
    self.assertLen(df, 2)
    self.assertEqual(list(df['span_id']), ['s4', 's5'])
    self.assertEqual(list(df['trace_id'].unique()), ['t2'])

    # 2. Proto spans with missing fields: corrupted trace t1 is dropped, valid
    # trace t2 is retained.
    proto1 = trace_cache_pb2.SpanMetricsProto(
        trace_id='t1',
        span_id='p1',
        method_name='m1',
        server_job='job1',
        start_timestamp_sec=1.0,
        finish_timestamp_sec=2.0,
    )
    proto2 = trace_cache_pb2.SpanMetricsProto(
        trace_id='t1',
        span_id='p2',
        # method_name and server_job missing
        start_timestamp_sec=1.0,
        finish_timestamp_sec=2.0,
    )
    proto3 = trace_cache_pb2.SpanMetricsProto(
        trace_id='t1',
        span_id='p3',
        method_name='m3',
        server_job='job1',
        # start_timestamp_sec missing
        finish_timestamp_sec=2.0,
    )
    proto4 = trace_cache_pb2.SpanMetricsProto(
        trace_id='t2',
        span_id='p4',
        method_name='m4',
        server_job='job2',
        start_timestamp_sec=1.0,
        finish_timestamp_sec=2.0,
    )
    proto5 = trace_cache_pb2.SpanMetricsProto(
        trace_id='t2',
        span_id='p5',
        method_name='m5',
        server_job='job2',
        start_timestamp_sec=2.0,
        finish_timestamp_sec=3.0,
    )
    df_proto = loader.proto_spans_to_df(
        [proto1, proto2, proto3, proto4, proto5]
    )
    self.assertLen(df_proto, 2)
    self.assertEqual(list(df_proto['span_id']), ['p4', 'p5'])
    self.assertEqual(list(df_proto['trace_id'].unique()), ['t2'])

  def test_spans_to_df_method_name_resolution(self):
    spans_data = [
        # Case 1: Both job and method, not prefixed
        {
            'trace_id': 't1',
            'span_id': 's1',
            'method_name': 'm1',
            'server_job': 'job1',
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
        },
        # Case 2: Both job and method, already prefixed
        {
            'trace_id': 't1',
            'span_id': 's2',
            'method_name': 'job1.m2',
            'server_job': 'job1',
            'start_timestamp_sec': 2.0,
            'finish_timestamp_sec': 3.0,
        },
        # Case 3: Only method, dotted
        {
            'trace_id': 't2',
            'span_id': 's3',
            'method_name': 'job2.m3',
            'server_job': None,
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
        },
        # Case 4: Only method, not dotted
        {
            'trace_id': 't2',
            'span_id': 's4',
            'method_name': 'm4',
            'server_job': None,
            'start_timestamp_sec': 2.0,
            'finish_timestamp_sec': 3.0,
        },
        # Case 5: Only job
        {
            'trace_id': 't3',
            'span_id': 's5',
            'method_name': None,
            'server_job': 'job3',
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
        },
        # Case 6: Neither (corrupted trace, should be dropped)
        {
            'trace_id': 't4',
            'span_id': 's6',
            'method_name': None,
            'server_job': None,
            'start_timestamp_sec': 1.0,
            'finish_timestamp_sec': 2.0,
        },
    ]
    df = loader.dict_spans_to_df(spans_data)
    # t4 dropped because method_name is None
    self.assertNotIn('t4', df['trace_id'].values)

    s1_row = df[df['span_id'] == 's1'].iloc[0]
    self.assertEqual(s1_row['method_name'], 'job1.m1')
    self.assertEqual(s1_row['server_job'], 'job1')

    s2_row = df[df['span_id'] == 's2'].iloc[0]
    self.assertEqual(s2_row['method_name'], 'job1.m2')
    self.assertEqual(s2_row['server_job'], 'job1')

    s3_row = df[df['span_id'] == 's3'].iloc[0]
    self.assertEqual(s3_row['method_name'], 'job2.m3')
    self.assertEqual(s3_row['server_job'], 'job2')

    s4_row = df[df['span_id'] == 's4'].iloc[0]
    self.assertEqual(s4_row['method_name'], 'm4')
    self.assertEqual(s4_row['server_job'], '')

    s5_row = df[df['span_id'] == 's5'].iloc[0]
    self.assertEqual(s5_row['method_name'], 'job3')
    self.assertEqual(s5_row['server_job'], 'job3')


if __name__ == '__main__':
  absltest.main()
