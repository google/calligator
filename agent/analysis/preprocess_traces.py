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

"""Stage 1 Preprocessing CLI: Ingests raw trace files and pre-computes cache datasets."""

import glob
import os
from typing import Sequence

from absl import app
from absl import flags

try:
  from . import data_exporter
  from . import loader
except ImportError:
  from agent.analysis import data_exporter
  from agent.analysis import loader

FLAGS = flags.FLAGS

flags.DEFINE_string(
    "input_path",
    None,
    "Path to raw trace file (Jaeger OpenTelemetry .json or .pb cache).",
    required=True,
)
flags.DEFINE_string(
    "cache_output_path",
    "/tmp/traces_cache.pb",
    "Output file path for preprocessed cache dataset (.pb, .textproto,"
    " or .json).",
)
flags.DEFINE_enum(
    "cache_format",
    "proto",
    ["proto", "json"],
    "Export format for Stage 1 cache dataset.",
)
flags.DEFINE_integer(
    "max_traces", 1000, "Maximum number of traces to ingest and process."
)


def _resolve_input_path(path: str) -> str:
  """Resolves relative input paths against BUILD_WORKING_DIRECTORY under bazel run."""
  if not path or os.path.isabs(path):
    return path
  build_wd = os.environ.get("BUILD_WORKING_DIRECTORY")
  if build_wd:
    candidate = os.path.join(build_wd, path)
    if os.path.exists(candidate) or glob.glob(candidate):
      return candidate
    if os.path.exists(path) or glob.glob(path):
      return path
    return candidate
  return path


def _resolve_output_path(path: str) -> str:
  """Resolves relative output paths against BUILD_WORKING_DIRECTORY under bazel run."""
  if not path or os.path.isabs(path):
    return path
  build_wd = os.environ.get("BUILD_WORKING_DIRECTORY")
  if build_wd:
    return os.path.join(build_wd, path)
  return path


def main(argv: Sequence[str]) -> None:
  del argv  # Unused.

  input_path = _resolve_input_path(FLAGS.input_path)
  cache_output_path = _resolve_output_path(FLAGS.cache_output_path)

  print(f"Ingesting trace dataset from: {input_path}...")
  collection, depgraph = loader.load_cached_traces(
      input_path, max_traces=FLAGS.max_traces
  )

  print(
      "Pre-computing critical path, drag, slack, and component deltas for"
      f" {len(collection.graphs)} traces..."
  )

  cache_proto = data_exporter.build_trace_cache_proto(
      collection=collection,
      dep_graph=depgraph,
      input_source=input_path,
  )

  print(
      f"Exporting preprocessed cache ({FLAGS.cache_format}) to:"
      f" {cache_output_path}"
  )

  data_exporter.export_data(
      data=cache_proto,
      export_path=cache_output_path,
      export_format=FLAGS.cache_format,
  )

  root_methods = sorted(list(collection.get_root_methods()))
  total_spans = len(cache_proto.spans)

  print("\n=== Stage 1 Trace Preprocessing Complete ===")
  print(f"Input Source       : {input_path}")
  print(f"Traces Processed   : {len(collection.graphs)}")
  print(f"Total Spans        : {total_spans}")
  print(f"Root Method(s)     : {', '.join(root_methods)}")
  print(f"Cache Export Path  : {cache_output_path}")
  print(f"Cache Format       : {FLAGS.cache_format}")


if __name__ == "__main__":
  app.run(main)
