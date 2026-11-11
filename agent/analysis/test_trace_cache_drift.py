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

"""Hermetic test verifying checked-in trace_cache_pb2 matches trace_cache.proto schema."""

import os
import re
import unittest

from google.protobuf import descriptor_pool
from google.protobuf import message

try:
  from . import trace_cache_pb2
except ImportError:
  from agent.analysis import trace_cache_pb2


class TraceCacheDriftTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    # Resolve path to trace_cache.proto
    test_srcdir = os.environ.get("TEST_SRCDIR", "")
    workspace = os.environ.get("TEST_WORKSPACE", "_main")
    candidate1 = os.path.join(
        test_srcdir, workspace, "agent/analysis/trace_cache.proto"
    )
    candidate2 = os.path.join(
        os.path.dirname(__file__), "trace_cache.proto"
    )
    candidate3 = os.path.abspath("agent/analysis/trace_cache.proto")
    for cand in [candidate1, candidate2, candidate3]:
      if os.path.exists(cand):
        self.proto_path = cand
        break
    else:
      self.proto_path = candidate2

  @staticmethod
  def _extract_message_blocks(proto_text: str) -> list[tuple[str, str]]:
    """Extracts top-level message (name, body) pairs using balanced braces."""
    # Strip single-line comments before scanning braces.
    cleaned = re.sub(r"//.*", "", proto_text)
    blocks: list[tuple[str, str]] = []
    for match in re.finditer(r"\bmessage\s+(\w+)\s*\{", cleaned):
      msg_name = match.group(1)
      depth = 1
      pos = match.end()
      while pos < len(cleaned) and depth > 0:
        if cleaned[pos] == "{":
          depth += 1
        elif cleaned[pos] == "}":
          depth -= 1
        pos += 1
      blocks.append((msg_name, cleaned[match.end() : pos - 1]))
    return blocks

  def test_proto_messages_and_fields_match_schema(self):
    """Parses trace_cache.proto and asserts all messages & fields exist in trace_cache_pb2."""
    self.assertTrue(
        os.path.exists(self.proto_path),
        f"trace_cache.proto not found at: {self.proto_path}",
    )
    with open(self.proto_path, "r", encoding="utf-8") as f:
      proto_text = f.read()

    message_blocks = self._extract_message_blocks(proto_text)
    self.assertTrue(bool(message_blocks))
    msg_names = {name for name, _ in message_blocks}
    self.assertIn("AnalysisResultProto", msg_names)

    field_pattern = re.compile(
        r"^\s*(?:(?:optional|repeated|required)\s+[\w\.]+|map<[^>;]+>|[\w\.]+)"
        r"\s+(\w+)\s*=\s*(\d+)",
        re.MULTILINE,
    )

    for msg_name, msg_body in message_blocks:
      self.assertTrue(
          hasattr(trace_cache_pb2, msg_name),
          f"Message class {msg_name} from trace_cache.proto is missing in trace_cache_pb2.py",
      )
      cls = getattr(trace_cache_pb2, msg_name)
      self.assertTrue(
          issubclass(cls, message.Message),
          f"{msg_name} is not a valid Protobuf Message subclass",
      )

      field_matches = field_pattern.findall(msg_body)
      self.assertNotEqual(
          len(field_matches),
          0,
          f"No fields parsed from message {msg_name} in trace_cache.proto",
      )
      for field_name, field_num_str in field_matches:
        self.assertIn(
            field_name,
            cls.DESCRIPTOR.fields_by_name,
            f"Field {field_name} in message {msg_name} is missing from trace_cache_pb2 Descriptor",
        )
        self.assertEqual(
            cls.DESCRIPTOR.fields_by_name[field_name].number,
            int(field_num_str),
            f"Field number mismatch for {msg_name}.{field_name}",
        )

  def test_round_trip_serialization(self):
    """Verifies serialization and deserialization on core cache proto."""
    cache = trace_cache_pb2.TraceCacheProto()
    cache.input_source = "test_source"
    cache.trace_count = 42
    cache.generated_at = "2026-09-15T00:00:00Z"
    cache.is_jaeger_trace = True

    node = cache.depgraph.nodes.add()
    node.node_key = "Service.Method"
    node.happens_before.append("Service.Child")
    node.median_start_delay_sec = 0.005

    span = cache.spans.add()
    span.trace_id = "12345"
    span.span_id = "1"
    span.method_name = "Service.Method"
    span.exclusive_drag_sec = 0.010
    span.slack_sec = 0.002
    span.component_deltas.server_app_delta = 0.008

    serialized = cache.SerializeToString()
    deserialized = trace_cache_pb2.TraceCacheProto()
    deserialized.ParseFromString(serialized)

    self.assertEqual(deserialized.input_source, "test_source")
    self.assertEqual(deserialized.trace_count, 42)
    self.assertEqual(deserialized.depgraph.nodes[0].node_key, "Service.Method")
    self.assertEqual(deserialized.spans[0].span_id, "1")
    self.assertAlmostEqual(deserialized.spans[0].exclusive_drag_sec, 0.010)


if __name__ == "__main__":
  unittest.main()
