# Calligator

Calligator is a tool for critical path analysis and resource optimization of microservices. It processes Jaeger tracing data to identify bottlenecks, calculate service dependencies, and suggest resource reallocation candidates based on trace timing and system metrics.

## Features

- **Critical Path Analysis**: Automatically identifies the critical path in microservice traces to find the operations directly impacting end-to-end latency.
- **Slack & Drag Calculation**: 
    - **Drag**: Measures how much a specific operation contributes to the critical path.
    - **Slack**: Identifies how much an operation can be delayed without affecting the overall trace duration.
- **Trace Retiming**: Simulates the impact of latency changes (optimizations or regressions) on the end-to-end trace time using a dependency-aware retimer.
- **Resource Reallocation**: Identifies "candidate" services for resource adjustments by combining critical path data with CPU and memory utilization metrics.
- **Jaeger Native Integration**: Standardized on the native Jaeger camelCase schema for easy ingestion of standard Jaeger JSON exports.
- **CRISP Library Integration**: Leverages the CRISP library for advanced graph-based critical path summaries and flamegraph generation.

## Getting Started

### Prerequisites

- [Bazel](https://bazel.build/install) (for building and testing)
- Python 3.9+
- Python dependencies (managed via Bazel/pip)

### Running Tests

To verify the installation and core logic, run the test suite using Bazel:

```bash
bazel test //...
```

### Type Checking

To run static type checking:

```bash
bazel run //:mypy_check -- \
    constants.py critical_path.py dependency_graph.py df_utils.py \
    graph.py graph_utils.py retimer.py \
    agent/analysis/loader.py agent/analysis/data_exporter.py \
    agent/analysis/plot_utils.py agent/analysis/preprocess_traces.py \
    agent/analysis/trace_analyzer.py
```

## Usage

### Resource Reallocation

Calligator can be used to analyze Jaeger trace exports and identify resource reallocation candidates:

```bash
python3 get_resource_reallocation.py \
    --jaeger_traces_path=path/to/traces.json \
    --resource_utilization_path=path/to/metrics.txt \
    --num_recommendations=5
```

### Two-Stage Trace Analysis CLI & Agent Skill

Calligator also includes a two-stage CLI suite under `agent/analysis/` for critical path bottleneck ranking, metric distributions, per-method/per-service/global retiming simulations, and transitive child-method summaries:

1. **Stage 1 — Preprocess Raw Traces (`//agent/analysis:preprocess_traces`)**:

```bash
bazel run //agent/analysis:preprocess_traces -- \
    --input_path="test_cases/test_1.json" \
    --cache_output_path="/tmp/traces_cache.pb" \
    --cache_format=proto
```

2. **Stage 2 — Run Unified Trace Queries (`//agent/analysis:trace_analyzer`)**:

```bash
bazel run //agent/analysis:trace_analyzer -- \
    --trace_path="/tmp/traces_cache.pb" \
    --mode=rank_drag \
    --top_k=10 \
    --stat=mean \
    --format=table
```

See [`agent/analysis/example_analysis_queries.sh`](agent/analysis/example_analysis_queries.sh) for runnable end-to-end examples across all four modes (`rank_drag`, `distribution`, `percent_improvement`, and `child_methods`) and [`agent/skills/critical_path_trace_analysis/SKILL.md`](agent/skills/critical_path_trace_analysis/SKILL.md) for full CLI, protobuf schema, and custom scripting documentation.

## License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details.

---

This is not an officially supported Google product. This project is not
eligible for the [Google Open Source Software Vulnerability Rewards
Program](https://bughunters.google.com/open-source-security).
