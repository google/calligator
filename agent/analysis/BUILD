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
load("@rules_python//python:defs.bzl", "py_library", "py_test")

package(default_visibility = ["//visibility:public"])

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
