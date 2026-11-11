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

load("@rules_python//python:py_library.bzl", "py_library")
load("@rules_python//python:py_test.bzl", "py_test")
load("@rules_python//python:pip.bzl", "compile_pip_requirements")
load("@rules_mypy//mypy/private:mypy.bzl", "mypy_cli")

package(default_visibility = ["//visibility:public"])

# This target generates/updates your requirements_lock.txt
compile_pip_requirements(
    name = "requirements",
    src = "requirements.txt",
    requirements_txt = "requirements_lock.txt",
)

exports_files(
    glob(["test_cases/*.json"]),
    visibility = ["//visibility:public"],
)

mypy_cli(
    name = "mypy_check",
    deps = [
        ":constants",
        ":critical_path",
        ":dependency_graph",
        ":df_utils",
        ":graph",
        ":graph_utils",
        ":retimer",
        "//agent/analysis:trace_cache_py_pb2",
        "//third_party/CRISP:graph",
        "@pip_deps//attrs:pkg",
        "@pip_deps//immutabledict:pkg",
        "@pip_deps//jinja2:pkg",
        "@pip_deps//networkx:pkg",
        "@pip_deps//pandas:pkg",
        "@pip_deps//pandas_stubs:pkg",
        "@pip_deps//protobuf:pkg",
        "@pip_deps//types_jinja2:pkg",
        "@pip_deps//types_networkx:pkg",
    ],
)

py_library(
    name = "graph",
    srcs = ["graph.py"],
    deps = [
        ":constants",
        ":critical_path",
        ":dependency_graph",
        ":df_utils",
        ":graph_utils",
        ":retimer",
        "//third_party/CRISP:graph",
        "@pip_deps//pandas:pkg",
    ],
)

py_library(
    name = "critical_path",
    srcs = ["critical_path.py"],
    deps = [
        ":dependency_graph",
        ":graph_utils",
        "//third_party/CRISP:graph",
        "@pip_deps//attrs:pkg",
        "@pip_deps//pandas:pkg",
    ],
)

py_library(
    name = "graph_utils",
    srcs = ["graph_utils.py"],
    deps = [
        "//third_party/CRISP:graph",
    ],
)

py_library(
    name = "dependency_graph",
    srcs = ["dependency_graph.py"],
    deps = [
        ":graph_utils",
        "//third_party/CRISP:graph",
    ],
)

py_library(
    name = "retimer",
    srcs = ["retimer.py"],
    deps = [
        ":dependency_graph",
        ":graph_utils",
        "//third_party/CRISP:graph",
        "@pip_deps//pandas:pkg",
    ],
)

py_library(
    name = "constants",
    srcs = ["constants.py"],
    deps = [
    ],
)

py_library(
    name = "df_utils",
    srcs = ["df_utils.py"],
    deps = [
        ":constants",
        "@pip_deps//networkx:pkg",
        "@pip_deps//pandas:pkg",
    ],
)

py_test(
    name = "graph_test",
    srcs = ["graph_test.py"],
    data = [
        "test_cases/test_1.json",
        "test_cases/test_2.json",
        "test_cases/test_3.json",
        "test_cases/test_4.json",
        "test_cases/test_5.json",
        "test_cases/test_6.json",
    ],
    deps = [
        ":graph",
        ":graph_utils",
        "@pip_deps//parameterized:pkg",
        "@pip_deps//pytest:pkg",
        "//third_party/CRISP:graph",
        "@pip_deps//pandas:pkg",
    ],
)

py_test(
    name = "critical_path_test",
    size = "small",
    srcs = ["critical_path_test.py"],
    data = [
        "test_cases/test_1.json",
        "test_cases/test_2.json",
        "test_cases/test_3.json",
        "test_cases/test_4.json",
        "test_cases/test_5.json",
        "test_cases/test_6.json",
    ],
    deps = [
        ":critical_path",
        ":graph",
        "@pip_deps//pandas:pkg",
        "@pip_deps//pytest:pkg",
        "//third_party/CRISP:graph",
    ],
)

py_test(
    name = "dependency_graph_test",
    size = "small",
    srcs = ["dependency_graph_test.py"],
    data = [
        "test_cases/test_1.json",
        "test_cases/test_2.json",
        "test_cases/test_3.json",
        "test_cases/test_4.json",
        "test_cases/test_5.json",
        "test_cases/test_6.json",
    ],
    deps = [
        ":dependency_graph",
        ":graph",
        ":graph_utils",
        "@pip_deps//pytest:pkg",
        "//third_party/CRISP:graph",
    ],
)

py_test(
    name = "retimer_test",
    size = "small",
    srcs = ["retimer_test.py"],
    data = [
        "test_cases/test_1.json",
        "test_cases/test_2.json",
        "test_cases/test_3.json",
        "test_cases/test_4.json",
        "test_cases/test_5.json",
        "test_cases/test_6.json",
    ],
    deps = [
        ":dependency_graph",
        ":graph",
        ":retimer",
        "@pip_deps//pandas:pkg",
        "@pip_deps//pytest:pkg",
        "//third_party/CRISP:graph",
    ],
)

py_test(
    name = "df_utils_test",
    srcs = ["df_utils_test.py"],
    deps = [
        ":df_utils",
        "@pip_deps//pytest:pkg",
        "@pip_deps//immutabledict:pkg",
        "@pip_deps//pandas:pkg",
    ],
)
