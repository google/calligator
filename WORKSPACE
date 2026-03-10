workspace(name = "calligator")

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

# Rules Python
http_archive(
    name = "rules_python",
    sha256 = "b857476e43c29926068abe8b67abd2b51b7b7c7283c7c2c9c75971e2c91c5b8d",
    strip_prefix = "rules_python-0.31.0",
    url = "https://github.com/bazelbuild/rules_python/releases/download/v0.31.0/rules_python-0.31.0.tar.gz",
)
load("@rules_python//python:repositories.bzl", "py_repositories")
py_repositories()

# MyPy
http_archive(
    name = "bazel_mypy",
    sha256 = "f73a465160842c7526e4e845f84b6f1ded6b92c4c2c2051287c2b3e51b3d605c",
    strip_prefix = "bazel-mypy-0.2.0",
    url = "https://github.com/bazelbuild/bazel-mypy/archive/refs/tags/0.2.0.tar.gz",
)
load("@bazel_mypy//:repositories.bzl", "bazel_mypy_repositories")
bazel_mypy_repositories()

# Pip Dependencies
load("@rules_python//python:pip.bzl", "pip_parse")
pip_parse(
    name = "pip_deps",
    requirements_lock = "//:requirements.txt",
)
load("@pip_deps//:requirements.bzl", "install_deps")
install_deps()

load("@bazel_mypy//:pip_extensions.bzl", "mypy_requirement")
mypy_requirement("//:requirements.txt")
