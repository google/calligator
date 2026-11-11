---
name: critical-path-trace-analysis
description: >-
  Analyzes distributed traces, evaluates critical path execution, and simulates
  system latency optimizations. Use when investigating microservice latency
  bottlenecks, ranking RPC methods by exclusive drag, computing latency
  distributions, simulating per-method or per-service speedups, removing socket
  queuing, capping network transit, or authoring custom Python analysis scripts
  using agent/analysis/ libraries. Don't use for non-critical-path trace
  visualizations or live system job monitoring.
---

# Critical Path Trace Analysis & System Optimization Skill

Use this skill when you need to identify microservice latency bottlenecks,
evaluate critical paths, compute exclusive drag distributions, simulate
performance gains from per-method, per-service, or global network/queuing
optimizations, or author custom Python analysis scripts for complex retiming
models.

--------------------------------------------------------------------------------

## 1. High-Level Objectives & Analytical Modes

The trace analysis tool suite (`trace_analyzer.py`) provides four distinct
analytical modes designed to answer specific system performance questions:

### Mode 1: Top-K Exclusive Drag Ranking (`--mode=rank_drag`)

-   **Primary Objective**: **FIND OPTIMIZATION TARGETS**.
-   **What it does**: Ranks RPC methods by their exclusive drag along the
    critical path across traces in configurable latency brackets
    (`--percentile_start`, `--percentile_end`, `--stat`, `--use_cached_drag`).
    `--stat` supports conditional critical-path statistics (`mean`, `p50`,
    `p90`, `p95`, `p99`) as well as unconditional expected drag per trace
    (`expected_per_trace_sec`, total drag divided by the number of traces). By
    default (`--use_cached_drag=True`), `rank_drag` uses the per-span exclusive
    drag stored by `preprocess_traces` on the original full-precision graph.
-   **When to use**: At the start of an investigation to discover which
    microservice methods contribute most directly to end-to-end user-perceived
    request latency.

### Mode 2: Distribution Analysis (`--mode=distribution`)

-   **Primary Objective**: **ANALYZE IMPACT OF PER-METHOD, PER-SERVICE & GLOBAL
    OPTIMIZATIONS ON SPECIFIC METHODS & ROOT REQUEST LATENCY**.
-   **What it does**: Computes cumulative distribution functions (CDFs) of
    execution duration, slack, and exclusive or inclusive drag for a target RPC
    method (`--method`) or service (`--service`).
-   **Supported Optimization Retimings**:
    -   **Per-Method Retiming Optimizations**: Modify specific RPC methods
        (`--retime_spec`, `--retime_method`, `--retime_percent`,
        `--retime_fixed_sec`, `--retime_max_lat_sec`).
    -   **Per-Service Retiming Optimizations**: Modify all RPC methods under a
        service prefix (`--retime_spec`).
    -   **Global Retiming Optimizations**: Remove queuing overhead
        (`--remove_all_queuing=True`) or cap network latency
        (`--cap_network_sec=0.001`).
    -   **Combined Optimizations**: Apply both per-method/service and global
        retiming optimizations together in a single run.
-   **When to use**: To evaluate how speeding up Method A, capping Service B, or
    eliminating socket queuing changes the execution duration, slack, and
    exclusive/inclusive drag distributions of root Method C.

### Mode 3: Percent Improvement Simulation (`--mode=percent_improvement`)

-   **Primary Objective**: **VISUALIZE & QUANTIFY E2E SYSTEM LATENCY REDUCTION
    FOR OPTIMIZATIONS**.
-   **What it does**: Simulates system-wide retiming scenarios for **per-method
    optimizations**, **per-service optimizations**, **global optimizations**, or
    **combined optimizations**. Generates multi-panel CDFs showing original vs
    retimed end-to-end latency, absolute time saved ($\Delta\text{ms}$ /
    $\Delta\text{sec}$), and percent improvement distributions.
-   **Supported Optimization Retimings**: Supports **Per-Method / Service
    Optimizations** (`--retime_spec`, `--retime_method`, `--retime_percent`,
    `--retime_fixed_sec`, `--retime_max_lat_sec`) and **Global Optimizations**
    (`--remove_all_queuing`, `--cap_network_sec`).
-   **When to use**: To quantify total end-to-end latency savings across an
    application trace dataset under per-method speedups, global queuing removal,
    or combined architectural optimizations before committing code changes.

### Mode 4: Transitive Child Methods Summary (`--mode=child_methods`)

-   **Primary Objective**: **MAP TRANSITIVE CALL PATHS & SAMPLE COUNTS**.
-   **What it does**: Lists all unique descendant child methods (direct and
    indirect) transitively called under a target parent method (`--method`) or
    service (`--service`), along with their invocation counts.
-   **When to use**: To explore the downstream call tree structure and call
    counts for a given service or method, helping identify hidden/indirect
    dependencies.

--------------------------------------------------------------------------------

## 2. Global Time Unit Standard & Convention

All core critical path libraries (`agent/analysis`), protobuf schemas
(`trace_cache.proto`), and CLI analysis tools operate strictly under the
**Universal Seconds Standard (`float` seconds)**:

-   **Timestamps & Durations**: `start_timestamp`, `finish_timestamp`, and
    `duration` are stored and manipulated in **seconds**.
-   **Slack & Drag**: `exclusive_drag_sec`, `inclusive_drag_sec`, and
    `slack_sec` are measured in **seconds**.
-   **Component Deltas**: `server_app_delta`, `request_network_delta`,
    `response_network_delta`, and queue deltas are expressed in **seconds**.
-   **Core Retiming APIs**:
    -   `retime_method(graph, method, percent_difference, fixed_difference)`
        accepts `fixed_difference` in **seconds** and returns time saved in
        **seconds**.
    -   `retime_service(graph, service_name, percent_difference,`
        `fixed_difference)` accepts `fixed_difference` in **seconds** and
        returns time saved in **seconds**.
    -   `retime_network_components(graph, component_names, to_value,`
        `span_components_map)` accepts `to_value` in **seconds** and returns
        time saved in **seconds**.
-   **CLI Flags**:
    -   Standard flags: `--retime_fixed_sec`, `--retime_max_lat_sec`,
        `--cap_network_sec` (values in seconds).
    -   Aliases: `--retime_fixed`, `--retime_max_lat`, `--cap_network` (values
        in seconds).
    -   Legacy flags: `--retime_fixed_us`, `--retime_max_lat_us` (microseconds
        converted via $/ 10^6$), `--cap_network_ms` (milliseconds converted via
        $/ 10^3$).
-   **JSON Spec Keys**:
    -   Standard keys: `fixed_diff_sec`, `max_lat_sec` (seconds).
    -   Aliases: `fixed_diff`, `max_lat` (seconds).
    -   Legacy keys: `fixed_diff_us`, `max_lat_us` (microseconds converted to
        seconds).

--------------------------------------------------------------------------------

## 3. Input & Output Specification Matrix

| Stage | Operation | Component | Format | Extensions | Description & Implementation Notes |
| :---- | :-------- | :-------- | :----- | :--------- | :--------------------------------- |
| **Stage 1** | Input | Raw Traces | **Jaeger OpenTelemetry** | `.json`, `.json.gz` | OpenTelemetry / Jaeger JSON trace export loaded via `loader.py`. |
| **Stage 1** | Output Cache | Preprocessed Cache | **Proto** (Recommended ⭐) | `.pb` / `.textproto` | Strongly-typed single-file cache (`TraceCacheProto`) containing `depgraph` and `spans`. |
| **Stage 1** | Output Cache | Preprocessed Cache | **JSON** (Always Available) | `.json` | Hierarchical JSON tree with top-level keys `depgraph` and `spans`. |
| **Stage 2** | Input | Preprocessed Cache Input | **Proto** or **JSON Cache** | `.pb`, `.textproto`, `.json` | Pre-computed dataset loaded **instantly** without graph reconstruction. |
| **Stage 2** | Input | Raw Trace Input | **Jaeger OpenTelemetry** | `.json`, `.json.gz` | Raw trace input loaded directly (reconstructs `DependencyGraph` on the fly). |
| **Stage 2** | Output Mode 1 | Console Read | **Stdout Text Table / JSON** | Terminal output | Formatted table (metrics displayed in milliseconds for human readability) or raw JSON. |
| **Stage 2** | Output Mode 2 | Data Export | **JSON** / **CSV** / **Proto** | `.json`, `.csv`, `.pb` | Machine-readable raw analysis metrics, rankings, quantiles, and distributions in seconds. |
| **Stage 2** | Output Mode 3 | Visual Plot | **Matplotlib Image** | `.png`, `.pdf` | High-resolution PNG or PDF plot figures. |

--------------------------------------------------------------------------------

## 4. Retiming Capabilities: Per-Method, Per-Service & Global Retiming

Both `--mode=distribution` and `--mode=percent_improvement` support
comprehensive retiming mechanics:

### A. Comparison: `retime_method` vs `retime_service`

| Dimension / Feature | `retime_method` | `retime_service` |
| :------------------ | :-------------- | :--------------- |
| **Target Scope** | Exact RPC method name (contains `.`, e.g. `Service.Method`) | Prefix microservice name (e.g. `Service`) |
| **Matching Logic** | Exact match: `(node.pid + '.' + node.opName) == method` | Prefix match: `node.pid.startswith(service_name)` |
| **API Signature** | `retime_method(graph, method, percent_difference=None, fixed_difference=None) -> float` | `retime_service(graph, service_name, percent_difference=None, fixed_difference=None) -> float` |
| **Time Unit Standard** | Seconds (float) for `fixed_difference` and return value | Seconds (float) for `fixed_difference` and return value |
| **JSON Spec Key Syntax** | Key contains a dot (`"ContentService.Update"`) | Key without a dot (`"ContentService"`) or explicit `service_name` |
| **Precedence** | Takes precedence over service prefix matches | Applied if no exact method rule matches |
| **End-Time Clamping** | Clamps `new_end = max(node.startTime, new_end)` (Bug B4 safety) | Clamps `new_end = max(node.startTime, new_end)` (Bug B4 safety) |
| **CLI Flags** | `--retime_method`, `--retime_percent`, `--retime_fixed_sec`, `--retime_max_lat_sec` | Specified via `--retime_spec` JSON or service rules |

### B. Per-Method and Per-Service Retiming Specification

Simulate specific RPC method speedups, fixed second reductions, or latency caps:

-   **Inline JSON string**:

    ```bash
    --retime_spec='{"SocialGraph.Follow": {"percent_diff": -50.0}, "StorageService": {"fixed_diff_sec": -0.005}}'
    ```
-   **JSON configuration file**:

    ```bash
    --retime_spec="agent/analysis/example_retime_spec.json"
    ```
-   **Repeated flags**:

    ```bash
    --retime_method="SocialGraph.Follow" --retime_percent="-50.0" --retime_fixed_sec="-0.010"
    ```

**JSON Spec Schema Formats**:

1.  **Mapping of targets to adjustments (Recommended)**:

    -   Keys containing a `.` match exact `method_name`.
    -   Keys without a `.` match prefix `service_name`.

    ```json
    {
      "PostService.UpdatePost": { "percent_diff": -50.0 },
      "StorageService": { "fixed_diff_sec": -0.010 }
    }
    ```

2.  **List of explicit rule objects**:

    ```json
    [
      {
        "method_name": "PostService.UpdatePost",
        "percent_diff": -50.0
      },
      {
        "service_name": "StorageService",
        "fixed_diff_sec": -0.010
      }
    ]
    ```

**Supported Adjustment Parameters**:

-   `percent_diff` (float): Speedup percentage, e.g. `-50.0` for 50% speedup.
-   `fixed_diff_sec` / `fixed_diff` (float): Fixed offset in **seconds** (e.g.
    `-0.010` to subtract 10ms).
-   `max_lat_sec` / `max_lat` (float): Latency cap in **seconds** (e.g. `0.002`
    to cap duration at 2ms).

### C. Global Retiming Optimizations

Simulate system-wide infrastructure optimizations:

-   `--remove_all_queuing=True`: Sets all queuing deltas (`client_send`,
    `server_recv`, `client_recv`, `server_send`) to `0.0` across all spans.
-   `--cap_network_sec=0.001`: Caps network transit deltas (`request_network`,
    `response_network`) to a maximum ceiling of $1.0\text{ms}$
    ($0.001\text{s}$).

--------------------------------------------------------------------------------

## 5. Authoring Custom Python Analysis Scripts

When a retiming scenario requires complex conditional logic, dynamic latency
models, or custom dependency graph transformations beyond CLI flags, author a
custom Python script using the underlying `agent/analysis` libraries.

### Runnable Multi-Scenario Python Script Template

Create a script (e.g. `custom_trace_experiment.py`):

```python
"""Custom trace retiming experiment script demonstrating multi-scenario simulation."""

from collections.abc import Sequence
from absl import app
from absl import flags
import numpy as np

from agent.analysis import loader
import retimer

FLAGS = flags.FLAGS
flags.DEFINE_string(
    'trace_path',
    None,
    'Path to cached Proto (.pb), JSON (.json) dataset.',
    required=True,
)


def main(argv: Sequence[str]) -> None:
  del argv

  # 1. Load cached trace graphs and pre-computed dependency graph
  collection, depgraph = loader.load_cached_traces(FLAGS.trace_path)
  retimer_engine = retimer.Retimer(depgraph)

  # Baseline E2E Latency
  baseline_durations = [
      g.get_duration() for g in collection.graphs.values() if g.graph
  ]
  baseline_mean = float(np.mean(baseline_durations)) if baseline_durations else 0.0
  print(f'Baseline Mean E2E Latency: {baseline_mean * 1000.0:.3f} ms')

  # ---------------------------------------------------------------------------
  # Scenario A: Exact RPC Method Retiming (-50% on PostService.UpdatePost)
  # ---------------------------------------------------------------------------
  collection_method, _ = loader.load_cached_traces(FLAGS.trace_path)
  retimer_method = retimer.Retimer(depgraph)
  for graph in collection_method.graphs.values():
    if not graph.graph:
      continue
    retimer_method.retime_method(
        graph=graph.graph,
        method='PostService.UpdatePost',
        percent_difference=-50.0,
    )
  durations_a = [
      g.get_duration() for g in collection_method.graphs.values() if g.graph
  ]
  print(f'Scenario A (Method -50%) Mean Latency: {np.mean(durations_a) * 1000.0:.3f} ms')

  # ---------------------------------------------------------------------------
  # Scenario B: Service-Level Prefix Retiming (-10ms on StorageService in seconds)
  # ---------------------------------------------------------------------------
  collection_service, _ = loader.load_cached_traces(FLAGS.trace_path)
  retimer_service = retimer.Retimer(depgraph)
  for graph in collection_service.graphs.values():
    if not graph.graph:
      continue
    retimer_service.retime_service(
        graph=graph.graph,
        service_name='StorageService',
        fixed_difference=-0.010,
    )
  durations_b = [
      g.get_duration() for g in collection_service.graphs.values() if g.graph
  ]
  print(f'Scenario B (Service -10ms) Mean Latency: {np.mean(durations_b) * 1000.0:.3f} ms')

  # ---------------------------------------------------------------------------
  # Scenario C: Global Network Retiming (Cap Network Transit to 1.0ms: 0.001s)
  # ---------------------------------------------------------------------------
  collection_network, _ = loader.load_cached_traces(FLAGS.trace_path)
  retimer_network = retimer.Retimer(depgraph)
  for graph in collection_network.graphs.values():
    if not graph.graph:
      continue
    span_comps = graph.get_span_components_map()
    retimer_network.retime_network_components(
        graph=graph.graph,
        component_names=['request_network_delta', 'response_network_delta'],
        to_value=0.001,
        span_components_map=span_comps,
    )
  durations_c = [
      g.get_duration() for g in collection_network.graphs.values() if g.graph
  ]
  print(f'Scenario C (Cap Network 1ms) Mean Latency: {np.mean(durations_c) * 1000.0:.3f} ms')


if __name__ == '__main__':
  app.run(main)
```

--------------------------------------------------------------------------------

## 6. Triple Output Mode Guidelines for Agents

-   **Console Stdout Mode (`--format=table` or `--format=json`)**: Prints
    results directly to terminal output. Use when you want to quickly read
    analytical numbers in your response context without managing files.
-   **File Data Export Mode (`--export_data_path=/path/to/data.json`)**: Exports
    raw JSON, CSV, Proto to disk. Use when performing programmatic
    multi-step data processing or saving large result sets.
-   **File Visual Plot Mode (`--output_plot_path=/path/to/plot.png`)**: Saves
    Matplotlib figures to disk. Use when generating visual artifacts for human
    users.

--------------------------------------------------------------------------------

## 7. Step-by-Step Execution Guide

### Step 1: Preprocess Raw Traces (Stage 1)

Convert raw trace dumps into an optimized, hermetic binary cache (`/tmp/traces_cache.pb`):

```bash
bazel run //agent/analysis:preprocess_traces -- \
  --input_path="traces/application_traces.json" \
  --cache_output_path="/tmp/traces_cache.pb" \
  --cache_format=proto \
  --max_traces=1000
```

### Step 2: Rank Bottlenecks to Find Optimization Targets (`--mode=rank_drag`)

Execute discovery analysis across the dataset to uncover top bottleneck RPC methods ranked by exclusive drag along the critical path:

```bash
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="/tmp/traces_cache.pb" \
  --mode=rank_drag \
  --top_k=10 \
  --percentile_start=90.0 \
  --percentile_end=95.0 \
  --stat=mean \
  --format=table \
  --export_data_path="/tmp/top_drag.json" \
  --output_plot_path="/tmp/top_drag.png"
```

### Step 3: Analyze Retiming Impact on Specific Methods & Services (`--mode=distribution`)

Target the top bottleneck RPC method `<TargetMethod>` discovered in Step 2 (e.g. `Dispatcher.Search`, `SocialGraph.Follow`, or `PostService.CreatePost`) or target service `<TargetService>`:

```bash
# Per-Method Retiming Impact (with Exclusive Drag Plot)
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="/tmp/traces_cache.pb" \
  --mode=distribution \
  --method="<TargetMethod>" \
  --metric=all \
  --with_retiming=True \
  --retime_spec='{"<BottleneckMethod>": {"percent_diff": -50.0}, "StorageService.Fetch": {"max_lat_sec": 0.002}}' \
  --plot_drag_type=exclusive \
  --format=table \
  --export_data_path="/tmp/dist.json" \
  --output_plot_path="/tmp/exclusive_dist.png"

# Per-Method Retiming Impact (with Inclusive Drag Plot)
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="/tmp/traces_cache.pb" \
  --mode=distribution \
  --method="<TargetMethod>" \
  --metric=all \
  --with_retiming=True \
  --retime_spec="agent/analysis/example_retime_spec.json" \
  --plot_drag_type=inclusive \
  --format=table \
  --export_data_path="/tmp/inclusive_dist.json" \
  --output_plot_path="/tmp/inclusive_dist.png"

# Global Retiming Impact (Queuing Removed)
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="/tmp/traces_cache.pb" \
  --mode=distribution \
  --method="<TargetMethod>" \
  --metric=all \
  --with_retiming=True \
  --remove_all_queuing=True \
  --format=table \
  --export_data_path="/tmp/dist_queuing.json" \
  --output_plot_path="/tmp/dist_queuing.png"
```

### Step 4: Quantify E2E Latency Reduction & Percent Improvement (`--mode=percent_improvement`)

Simulate full system performance improvements by speeding up bottleneck methods identified in Step 2, removing queuing, or capping network latency:

```bash
# Per-Method & Global Retiming Percent Improvement
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="/tmp/traces_cache.pb" \
  --mode=percent_improvement \
  --with_retiming=True \
  --retime_spec='{"<BottleneckMethod>": {"percent_diff": -50.0}}' \
  --remove_all_queuing=True \
  --cap_network_sec=0.001 \
  --format=table \
  --export_data_path="/tmp/improvement.json" \
  --output_plot_path="/tmp/improvement.png"
```

### Step 5: Transitive Child Methods Summary (`--mode=child_methods`)

Summarize descendant calls under a target parent method `<ParentMethod>`:

```bash
bazel run //agent/analysis:trace_analyzer -- \
  --trace_path="/tmp/traces_cache.pb" \
  --mode=child_methods \
  --method="<ParentMethod>" \
  --format=table
```

--------------------------------------------------------------------------------

## 8. Protocol Buffer Schema (`agent/analysis/trace_cache.proto`)

```protobuf
syntax = "proto2";

package calligator.agent.analysis;

message DependencyGraphNodeProto {
  optional string node_key = 1;
  optional string parent_node_key = 2;
  repeated string happens_before = 3;
  repeated string child_dependents = 4;
  repeated string async_children = 5;
  optional float median_start_delay_sec = 6;
  optional float median_end_delay_sec = 7;
}

message DependencyGraphProto {
  repeated DependencyGraphNodeProto nodes = 1;
}

message ComponentDeltasProto {
  optional float server_app_delta = 1;
  optional float client_send_queue_delta = 2;
  optional float server_recv_queue_delta = 3;
  optional float client_recv_queue_delta = 4;
  optional float server_send_queue_delta = 5;
  optional float request_network_delta = 6;
  optional float response_network_delta = 7;
  // Double-precision copy of server_app_delta. Readers prefer it when set.
  optional double server_app_delta_f64 = 8;
}

message SpanMetricsProto {
  optional string trace_id = 1;
  optional string span_id = 2;
  optional string parent_rpc_span_id = 3;
  optional string method_name = 4;
  optional string server_job = 5;
  optional float start_timestamp_sec = 6;
  optional float finish_timestamp_sec = 7;
  optional float duration_sec = 8;
  optional ComponentDeltasProto component_deltas = 9;
  optional bool is_critical_path = 10;
  optional float exclusive_drag_sec = 11;
  optional float inclusive_drag_sec = 12;
  optional float slack_sec = 13;
  optional float relative_exclusive_drag = 14;
  optional float relative_slack = 15;
  optional int32 num_descendants = 16;
  optional double start_timestamp_sec_f64 = 17;
  optional double finish_timestamp_sec_f64 = 18;
  optional double duration_sec_f64 = 19;
  optional double exclusive_drag_sec_f64 = 20;
  optional double inclusive_drag_sec_f64 = 21;
  optional double slack_sec_f64 = 22;
}

message TraceCacheProto {
  optional string input_source = 1;
  optional int64 trace_count = 2;
  optional string generated_at = 3;
  optional bool is_jaeger_trace = 4;
  optional DependencyGraphProto depgraph = 5;
  repeated SpanMetricsProto spans = 6;
}

// Stage 2 Analysis Output Protos

message MethodDragRankingProto {
  optional int32 rank = 1;
  optional string method = 2;
  optional float exclusive_drag_sec = 3;
  optional float relative_drag = 4;
  optional float mean = 5;
  optional float std = 6;
  optional float p50 = 7;
  optional float p90 = 8;
  optional float p95 = 9;
  optional float p99 = 10;
  optional float expected_per_trace_sec = 11;
  optional float cp_share = 12;
}

message RankDragResultProto {
  optional int32 top_k = 1;
  optional string stat = 2;
  optional float percentile_start = 3;
  optional float percentile_end = 4;
  optional int64 trace_count = 5;
  optional float root_mean_duration_sec = 6;
  repeated MethodDragRankingProto rankings = 7;
  optional int64 precomputed_drag_traces = 8;
}

message MetricStatsProto {
  optional float mean = 1;
  optional float std = 2;
  optional float p50 = 3;
  optional float p90 = 4;
  optional float p95 = 5;
  optional float p99 = 6;
}

message MetricValuesProto {
  repeated float original = 1 [packed = true];
  repeated float retimed = 2 [packed = true];
}

message MetricSummaryProto {
  optional MetricStatsProto original_stats = 1;
  optional MetricStatsProto retimed_stats = 2;
}

message DistributionResultProto {
  optional string target_method = 1;
  optional string target_service = 2;
  optional bool with_retiming = 3;
  optional string metric_filter = 4;
  map<string, MetricValuesProto> metrics = 5;
  map<string, MetricSummaryProto> summary = 6;
}

message ImprovementQuantilesProto {
  optional float orig_mean_sec = 1;
  optional float retimed_mean_sec = 2;
  optional float saved_mean_sec = 3;
  optional float mean_percent_improvement = 4;
  optional float p50_percent_improvement = 5;
  optional float p90_percent_improvement = 6;
  optional float p95_percent_improvement = 7;
  optional float p99_percent_improvement = 8;
}

message PercentImprovementResultProto {
  optional int64 trace_count = 1;
  optional bool with_retiming = 2;
  repeated float original_durations_sec = 3 [packed = true];
  repeated float retimed_durations_sec = 4 [packed = true];
  repeated float saved_sec = 5 [packed = true];
  repeated float percent_improvements = 6 [packed = true];
  optional ImprovementQuantilesProto quantiles = 7;
}

message ChildMethodCountProto {
  optional string child_method = 1;
  optional int32 count = 2;
}

message ChildMethodsResultProto {
  optional string target_parent = 1;
  optional int32 parent_match_count = 2;
  repeated ChildMethodCountProto child_methods = 3;
}

message AnalysisResultProto {
  optional string mode = 1;
  oneof result {
    RankDragResultProto rank_drag_result = 2;
    DistributionResultProto distribution_result = 3;
    PercentImprovementResultProto percent_improvement_result = 4;
    ChildMethodsResultProto child_methods_result = 5;
  }
}
```

--------------------------------------------------------------------------------

## 9. Output Metrics & Column Definitions

When reading Rank Drag ASCII tables or checking data exports, understand the
following metrics and column names:

-   **`exclusive_drag_sec` (`exclusive_drag (ms)`)**: The **mean absolute
    exclusive drag** in seconds (displayed in milliseconds in console tables),
    conditional on the method appearing on the critical path. Exclusive drag is
    the duration of time a span spent executing on the critical path that cannot
    be run in parallel with its siblings or child nodes. It represents the
    direct latency reduction in the root trace when this specific method is
    optimized.
-   **`relative_drag (%)`**: The **mean relative drag percentage**. It
    represents the proportion of overall request latency contributed by this
    method's conditional mean exclusive drag, computed as:

    $$
    \text{relative\_drag (\%)} = \left(\frac{\text{Mean Exclusive Drag (sec)}}{\text{Mean Overall Root Duration (sec)}}\right) \times 100
    $$

    This allows you to quickly identify which components have the highest
    relative return-on-investment (ROI) for optimization when on the critical
    path.
-   **`expected_per_trace_sec` (`expected_per_trace (ms)`)**: The
    **unconditional expected exclusive drag per trace** in seconds (displayed in
    milliseconds in console tables), computed as the total exclusive drag of the
    method across all analyzed traces divided by the total number of analyzed
    traces. Expected drags across all methods partition the mean root duration.
-   **`cp_share (%)` (`cp_share`)**: The **critical-path share percentage**
    (stored as a fraction in $[0, 1]$ in JSON exports and displayed as a
    percentage in console tables), representing the proportion of analyzed
    traces in which the method appears on the critical path.
-   **Percentile Columns (`p50`, `p90`, `p95`, `p99`)**: The absolute exclusive
    drag times at specific percentiles across critical-path spans of the method,
    measured in **seconds** (displayed in milliseconds in console tables). These
    help identify if a method's bottleneck is a consistent latency shift (seen
    in `p50`) or tail-latency outliers (visible in `p99`).

--------------------------------------------------------------------------------

## 10. Skill Verification

To verify this skill definition, build its target:

```bash
bazel test //agent/skills/critical_path_trace_analysis:skill_frontmatter_test
```
