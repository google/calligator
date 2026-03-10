"""The CRISP library computes and presents the critical path summary from Jaeger microservice traces."""

load("@rules_python//python:py_library.bzl", "py_library")
load("@rules_python//python:py_binary.bzl", "py_binary")
load("@rules_python//python:py_test.bzl", "py_test")

exports_files(["LICENSE"])

py_library(
    name = "__init__",
    srcs = ["__init__.py"],
    deps = [
        ":flamegraph",
        ":graph",
    ],
)

py_library(
    name = "graph",
    srcs = ["graph.py"],
    visibility = ["//visibility:public"],
    deps = [
    ],
)

filegroup(
    name = "flamegraph_scripts",
    srcs = [
        "difffolded.pl",
        "flamegraph.pl",
    ],
)

py_library(
    name = "flamegraph",
    srcs = [
        "flamegraph.py",
    ],
    data = [
        ":flamegraph_scripts",
    ],
    deps = [
        ":graph",
        "@pip_deps//pandas:pkg",
    ],
)

py_binary(
    name = "process",
    srcs = ["process.py"],
    data = [":flamegraph_scripts"],
    deps = [
        ":flamegraph",
        ":graph",
        "@pip_deps//jinja2:pkg",
        "@pip_deps//matplotlib:pkg",
        "@pip_deps//pandas:pkg",
    ],
)

py_test(
    name = "test_flamegraph",
    srcs = ["tests/test_flamegraph.py"],
    deps = [
        ":flamegraph",
        "@pip_deps//pytest:pkg",
    ],  
)
