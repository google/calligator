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
bazel run //:mypy_check
```

## Usage

Calligator can be used to analyze Jaeger trace exports. For example, to identify resource reallocation candidates:

```bash
python3 get_resource_reallocation.py \
    --jaeger_traces_path=path/to/traces.json \
    --resource_utilization_path=path/to/metrics.txt \
    --num_recommendations=5
```

## License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details.

---

This is not an officially supported Google product. This project is not
eligible for the [Google Open Source Software Vulnerability Rewards
Program](https://bughunters.google.com/open-source-security).
