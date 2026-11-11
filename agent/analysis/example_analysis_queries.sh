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
# Example Analysis Queries Script
# Demonstrates Stage 1 Preprocessing and Stage 2 Unified Analysis using open-source Bazel.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

INPUT_TRACE="${REPO_ROOT}/test_cases/test_1.json"
TMP_DIR="/tmp/calligator_example_run"
CACHE_PB="${TMP_DIR}/demo_cache.pb"
TARGET_METHOD="S2.two"
TARGET_SERVICE="S2"
TARGET_ROOT_METHOD="S1.one"

mkdir -p "${TMP_DIR}"

echo "======================================================================"
echo " Starting Calligator Trace Analysis Suite Demonstration "
echo "======================================================================"

cd "${REPO_ROOT}"

# 1. Stage 1 Preprocessing CLI
echo "==> Running Stage 1 Preprocessing Cache Generation..."
bazel run //agent/analysis:preprocess_traces -- \
  --input_path="${INPUT_TRACE}" \
  --cache_output_path="${CACHE_PB}" \
  --cache_format=proto \
  --max_traces=100

# 2. Stage 2 Analysis: Mode 1 - Top-K Exclusive Drag Ranking
echo "==> Running Stage 2 Mode 1: Top-K Exclusive Drag Ranking..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=rank_drag \
  --top_k=5 \
  --stat=mean \
  --format=table \
  --export_data_path="${TMP_DIR}/top_drag.json" \
  --output_plot_path="${TMP_DIR}/top_drag.png"

# 3. Stage 2 Analysis: Query 2A: Targeted Method-Level Retiming via CLI Flags (Mode 2, Inclusive Drag)
echo "==> Running Stage 2 Query 2A: Targeted Method-Level Retiming via CLI Flags..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=distribution \
  --metric=all \
  --with_retiming=True \
  --retime_method="${TARGET_METHOD}" \
  --retime_percent=-50 \
  --plot_drag_type=inclusive \
  --format=table \
  --export_data_path="${TMP_DIR}/dist_method.json" \
  --output_plot_path="${TMP_DIR}/dist_method.png"

# 4. Stage 2 Analysis: Query 2B: Service-Level Retiming via Inline JSON String (Mode 2, Inclusive Drag)
echo "==> Running Stage 2 Query 2B: Service-Level Retiming via Inline JSON String..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=distribution \
  --metric=all \
  --with_retiming=True \
  --retime_spec="{\"${TARGET_SERVICE}\": {\"fixed_diff_sec\": -0.000010}}" \
  --plot_drag_type=inclusive \
  --format=table \
  --export_data_path="${TMP_DIR}/dist_service_inline.json" \
  --output_plot_path="${TMP_DIR}/dist_service_inline.png"

# 5. Stage 2 Analysis: Query 2C: Combined Service and Method Retiming via JSON Spec File (Mode 2, Inclusive Drag)
echo "==> Running Stage 2 Query 2C: Combined Service and Method Retiming via JSON Spec File..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=distribution \
  --metric=all \
  --with_retiming=True \
  --retime_spec="${SCRIPT_DIR}/example_retime_spec.json" \
  --plot_drag_type=inclusive \
  --format=table \
  --export_data_path="${TMP_DIR}/dist_combined_file.json" \
  --output_plot_path="${TMP_DIR}/dist_combined_file.png"

# 6. Stage 2 Analysis: Query 2D: Non-Root Method-Level Distribution (Exclusive Drag) (Mode 2)
echo "==> Running Stage 2 Query 2D: Non-Root Method-Level Distribution (Exclusive Drag)..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=distribution \
  --metric=all \
  --method="${TARGET_METHOD}" \
  --with_retiming=True \
  --retime_method="${TARGET_METHOD}" \
  --retime_percent=-50 \
  --plot_drag_type=exclusive \
  --format=table \
  --export_data_path="${TMP_DIR}/dist_nonroot_exclusive.json" \
  --output_plot_path="${TMP_DIR}/dist_nonroot_exclusive.png"

# 7. Stage 2 Analysis: Query 2E: Non-Root Method-Level Distribution (Inclusive Drag) (Mode 2)
echo "==> Running Stage 2 Query 2E: Non-Root Method-Level Distribution (Inclusive Drag)..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=distribution \
  --metric=all \
  --method="${TARGET_METHOD}" \
  --with_retiming=True \
  --retime_method="${TARGET_METHOD}" \
  --retime_percent=-50 \
  --plot_drag_type=inclusive \
  --format=table \
  --export_data_path="${TMP_DIR}/dist_nonroot_inclusive.json" \
  --output_plot_path="${TMP_DIR}/dist_nonroot_inclusive.png"

# 8. Stage 2 Analysis: Query 3: Percent Improvement Simulation (Mode 3)
echo "==> Running Stage 2 Query 3: Percent Improvement Simulation..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=percent_improvement \
  --with_retiming=True \
  --remove_all_queuing=True \
  --cap_network_sec=0.001 \
  --format=table \
  --export_data_path="${TMP_DIR}/improvement.json" \
  --output_plot_path="${TMP_DIR}/improvement.png"

# 9. Stage 2 Analysis: Query 4: Child Methods Summary for Root (Mode 4)
echo "==> Running Stage 2 Query 4: Child Methods Summary for Root Method (${TARGET_ROOT_METHOD})..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=child_methods \
  --method="${TARGET_ROOT_METHOD}" \
  --format=table \
  --export_data_path="${TMP_DIR}/child_methods_root.json"

# 10. Stage 2 Analysis: Query 5: Non-Root Child Methods Summary for Service (Mode 4)
echo "==> Running Stage 2 Query 5: Child Methods Summary for Non-Root Service (${TARGET_SERVICE})..."
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="${CACHE_PB}" \
  --mode=child_methods \
  --service="${TARGET_SERVICE}" \
  --format=table \
  --export_data_path="${TMP_DIR}/child_methods_service.json"

echo ""
echo "======================================================================"
echo " Demonstration Completed Successfully! "
echo " Output artifacts saved to: ${TMP_DIR}"
echo "======================================================================"
