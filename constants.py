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

"""Constants used in dataframe utility functions."""

from typing import Final, FrozenSet

# Jaeger column names / keys
JAEGER_SPAN_ID: Final[str] = 'spanID'
JAEGER_TRACE_ID: Final[str] = 'traceID'
JAEGER_OPERATION_NAME: Final[str] = 'operationName'
JAEGER_PROCESS_ID: Final[str] = 'processID'
JAEGER_METHOD: Final[str] = 'method'
JAEGER_SERVER_FINISH_TIME: Final[str] = 'server_finish_time'
JAEGER_SERVER_START_TIME: Final[str] = 'server_start_time'
JAEGER_CLIENT_FINISH_TIME: Final[str] = 'client_finish_time'
JAEGER_CLIENT_START_TIME: Final[str] = 'client_start_time'
JAEGER_PARENT_SPAN_ID: Final[str] = 'parent_span_id'
JAEGER_START_TIME: Final[str] = 'startTime'
JAEGER_DURATION: Final[str] = 'duration'
JAEGER_DATA: Final[str] = 'data'
JAEGER_SPANS: Final[str] = 'spans'
JAEGER_PROCESSES: Final[str] = 'processes'
JAEGER_SERVICE_NAME: Final[str] = 'serviceName'

# Tool-calculated constants in camelCase
NUM_DESCENDANTS: Final[str] = 'numDescendants'
PARENT_SPAN_ID: Final[str] = 'parentSpanID'

RAW_COLUMNS: Final[FrozenSet[str]] = frozenset([
    JAEGER_TRACE_ID,
    JAEGER_SPAN_ID,
    PARENT_SPAN_ID,
    JAEGER_PROCESS_ID,
    JAEGER_OPERATION_NAME,
    JAEGER_START_TIME,
    JAEGER_DURATION,
    NUM_DESCENDANTS,
])

# Optional column names
REFERENCES: Final[str] = 'references'

OPTIONAL_COLUMNS: Final[FrozenSet[str]] = frozenset([REFERENCES])

# String literals for method renaming
MONGO: Final[str] = 'Mongo'
MMC: Final[str] = 'Mmc'
REDIS: Final[str] = 'Redis'
SUFFIX_MONGODB: Final[str] = '-mongodb'
SUFFIX_MEMCACHED: Final[str] = '-memcached'
SUFFIX_REDIS: Final[str] = '-redis'
SERVICE_SUFFIX: Final[str] = '-service'
