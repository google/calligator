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

load("@rules_proto//proto:defs.bzl", "proto_library")
load("@rules_python//python:defs.bzl", "py_binary", "py_library", "py_test")

package(default_visibility = ["//visibility:public"])

exports_files(["example_retime_spec.json"])

proto_library(
    name = "trace_cache_proto",
    srcs = ["trace_cache.proto"],
)

py_library(
    name = "trace_cache_py_pb2",
    srcs = [
        "trace_cache_pb2.py",
    ],
    data = [
        "trace_cache_pb2.pyi",
    ],
    deps = [
        "@pip_deps//protobuf:pkg",
    ],
)

py_library(
    name = "loader",
    srcs = ["loader.py"],
    deps = [
        ":trace_cache_py_pb2",
        "//:dependency_graph",
        "//:df_utils",
        "//:graph",
        "@pip_deps//pandas:pkg",
        "@pip_deps//protobuf:pkg",
    ],
)

py_library(
    name = "plot_utils",
    srcs = ["plot_utils.py"],
    deps = [
        "@pip_deps//matplotlib:pkg",
        "@pip_deps//numpy:pkg",
    ],
)

py_library(
    name = "data_exporter",
    srcs = ["data_exporter.py"],
    deps = [
        ":trace_cache_py_pb2",
        "//:dependency_graph",
        "//:graph",
        "@pip_deps//numpy:pkg",
        "@pip_deps//pandas:pkg",
        "@pip_deps//protobuf:pkg",
    ],
)

py_library(
    name = "preprocess_traces_lib",
    srcs = ["preprocess_traces.py"],
    deps = [
        ":data_exporter",
        ":loader",
        "@pip_deps//absl_py:pkg",
    ],
)

py_binary(
    name = "preprocess_traces",
    srcs = ["preprocess_traces.py"],
    deps = [
        ":preprocess_traces_lib",
        "@pip_deps//numpy:pkg",
        "@pip_deps//pandas:pkg",
    ],
)

py_library(
    name = "trace_analyzer_lib",
    srcs = ["trace_analyzer.py"],
    deps = [
        ":data_exporter",
        ":loader",
        ":plot_utils",
        "//:dependency_graph",
        "//:graph",
        "//:retimer",
        "@pip_deps//absl_py:pkg",
        "@pip_deps//numpy:pkg",
        "@pip_deps//pandas:pkg",
    ],
)

py_binary(
    name = "trace_analyzer",
    srcs = ["trace_analyzer.py"],
    data = ["example_retime_spec.json"],
    deps = [
        ":trace_analyzer_lib",
        "@pip_deps//numpy:pkg",
        "@pip_deps//pandas:pkg",
    ],
)

py_test(
    name = "trace_cache_drift_test",
    srcs = ["test_trace_cache_drift.py"],
    main = "test_trace_cache_drift.py",
    data = ["trace_cache.proto"],
    deps = [
        ":trace_cache_py_pb2",
        "@pip_deps//protobuf:pkg",
    ],
)

py_test(
    name = "preprocess_traces_test",
    srcs = ["preprocess_traces_test.py"],
    data = ["//:test_cases/test_1.json"],
    deps = [
        ":data_exporter",
        ":loader",
        ":preprocess_traces_lib",
        ":trace_cache_py_pb2",
        "@pip_deps//absl_py:pkg",
    ],
)

py_test(
    name = "trace_analyzer_test",
    srcs = ["trace_analyzer_test.py"],
    data = ["//:test_cases/test_1.json"],
    deps = [
        ":data_exporter",
        ":loader",
        ":plot_utils",
        ":trace_analyzer_lib",
        ":trace_cache_py_pb2",
        "//:df_utils",
        "//:graph",
        "//:retimer",
        "@pip_deps//absl_py:pkg",
        "@pip_deps//pandas:pkg",
    ],
)
