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

"""Hermetic test validating SKILL.md YAML frontmatter format."""

import os
import unittest
import yaml


class SkillFrontmatterTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    test_srcdir = os.environ.get("TEST_SRCDIR", "")
    workspace = os.environ.get("TEST_WORKSPACE", "_main")
    candidate1 = os.path.join(
        test_srcdir,
        workspace,
        "agent/skills/critical_path_trace_analysis/SKILL.md",
    )
    candidate2 = os.path.join(os.path.dirname(__file__), "SKILL.md")
    candidate3 = os.path.abspath(
        "agent/skills/critical_path_trace_analysis/SKILL.md"
    )
    for cand in [candidate1, candidate2, candidate3]:
      if os.path.exists(cand):
        self.skill_path = cand
        break
    else:
      self.skill_path = candidate2

  def test_frontmatter_presence_and_fields(self):
    """Verifies that SKILL.md has valid YAML frontmatter with required keys."""
    self.assertTrue(
        os.path.exists(self.skill_path),
        f"SKILL.md not found at: {self.skill_path}",
    )
    with open(self.skill_path, "r", encoding="utf-8") as f:
      content = f.read()

    self.assertTrue(content.startswith("---"), "SKILL.md must start with ---")
    parts = content.split("---", 2)
    self.assertGreaterEqual(
        len(parts), 3, "SKILL.md must contain closing --- for frontmatter"
    )

    frontmatter_raw = parts[1]
    data = yaml.safe_load(frontmatter_raw)
    self.assertIsInstance(data, dict, "Frontmatter must parse into a dictionary")

    self.assertIn("name", data, "Frontmatter missing required key: name")
    self.assertIn(
        "description", data, "Frontmatter missing required key: description"
    )

    self.assertEqual(data["name"], "critical-path-trace-analysis")
    self.assertTrue(
        len(data["description"]) > 20,
        "Description must be meaningful and non-empty",
    )

  def test_github_markdown_table_compatibility(self):
    """Verifies SKILL.md does not use g3doc `: ... :` multiline table continuations."""
    with open(self.skill_path, "r", encoding="utf-8") as f:
      lines = f.readlines()

    for line_no, line in enumerate(lines, start=1):
      stripped = line.strip()
      self.assertFalse(
          stripped.startswith(":") and stripped.endswith(":"),
          f"Line {line_no} uses g3doc ': ... :' table continuation syntax,"
          " which does not render on GitHub.",
      )


if __name__ == "__main__":
  unittest.main()
