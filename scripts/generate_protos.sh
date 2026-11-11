#!/usr/bin/env bash
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
#
# Generate Python protobuf bindings and type stubs for Calligator.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

PROTOC_BIN=""
if [[ -x "${REPO_ROOT}/bazel-bin/external/protobuf+/protoc" ]]; then
  PROTOC_BIN="${REPO_ROOT}/bazel-bin/external/protobuf+/protoc"
elif [[ -x "${REPO_ROOT}/bazel-bin/external/com_google_protobuf/protoc" ]]; then
  PROTOC_BIN="${REPO_ROOT}/bazel-bin/external/com_google_protobuf/protoc"
elif command -v bazel >/dev/null 2>&1; then
  echo "Building hermetic protoc via Bazel..."
  bazel build @protobuf//:protoc
  if [[ -x "${REPO_ROOT}/bazel-bin/external/protobuf+/protoc" ]]; then
    PROTOC_BIN="${REPO_ROOT}/bazel-bin/external/protobuf+/protoc"
  elif [[ -x "${REPO_ROOT}/bazel-bin/external/com_google_protobuf/protoc" ]]; then
    PROTOC_BIN="${REPO_ROOT}/bazel-bin/external/com_google_protobuf/protoc"
  fi
fi

if [[ -z "${PROTOC_BIN}" ]] && command -v protoc >/dev/null 2>&1; then
  PROTOC_BIN="protoc"
fi

if [[ -n "${PROTOC_BIN}" ]]; then
  echo "Using protoc at: ${PROTOC_BIN}"
  "${PROTOC_BIN}" --python_out=. --pyi_out=. agent/analysis/trace_cache.proto
elif python3 -m grpc_tools.protoc --help >/dev/null 2>&1; then
  echo "Using python3 -m grpc_tools.protoc"
  python3 -m grpc_tools.protoc -I. --python_out=. --pyi_out=. agent/analysis/trace_cache.proto
else
  echo "Error: neither bazel, protoc, nor grpc_tools.protoc is available." >&2
  exit 1
fi

python3 - << 'EOF'
pyi_path = "agent/analysis/trace_cache_pb2.pyi"
with open(pyi_path, "r", encoding="utf-8") as f:
  lines = f.readlines()
updated = []
for line in lines:
  if line.startswith("from google.protobuf") and "# type: ignore" not in line:
    line = line.rstrip("\n") + "  # type: ignore[import-untyped]\n"
  updated.append(line)
with open(pyi_path, "w", encoding="utf-8") as f:
  f.writelines(updated)
EOF

echo "Successfully generated Python protobuf bindings:"
echo "  - agent/analysis/trace_cache_pb2.py"
echo "  - agent/analysis/trace_cache_pb2.pyi"
