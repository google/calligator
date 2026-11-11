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

# Standard raw column names
TRACE_ID: Final[str] = 'trace_id'
SPAN_ID: Final[str] = 'span_id'
IS_TRUE_ROOT: Final[str] = 'is_true_root'
PARENT_RPC_SPAN_ID: Final[str] = 'parent_rpc_span_id'
METHOD_NAME: Final[str] = 'method_name'
CLIENT_USER: Final[str] = 'client_user'
CLIENT_JOB: Final[str] = 'client_job'
SERVER_USER: Final[str] = 'server_user'
SERVER_JOB: Final[str] = 'server_job'
CLIENT_START_TIMESTAMP: Final[str] = 'client_start_timestamp'
CLIENT_FINISH_TIMESTAMP: Final[str] = 'client_finish_timestamp'
SERVER_START_TIMESTAMP: Final[str] = 'server_start_timestamp'
SERVER_FINISH_TIMESTAMP: Final[str] = 'server_finish_timestamp'
SERVER_APP_DELTA: Final[str] = 'server_app_delta'
NUM_CHILDREN: Final[str] = 'num_children'
NUM_DESCENDANTS: Final[str] = 'num_descendants'
REQUEST_NETWORK_DELTA: Final[str] = 'request_network_delta'
RESPONSE_NETWORK_DELTA: Final[str] = 'response_network_delta'
CLIENT_SEND_QUEUE_DELTA: Final[str] = 'client_send_queue_delta'
SERVER_SEND_QUEUE_DELTA: Final[str] = 'server_send_queue_delta'
CLIENT_RECV_QUEUE_DELTA: Final[str] = 'client_recv_queue_delta'
SERVER_RECV_QUEUE_DELTA: Final[str] = 'server_recv_queue_delta'

RAW_COLUMNS: Final[FrozenSet[str]] = frozenset([
    TRACE_ID,
    SPAN_ID,
    IS_TRUE_ROOT,
    PARENT_RPC_SPAN_ID,
    METHOD_NAME,
    CLIENT_USER,
    CLIENT_JOB,
    SERVER_USER,
    SERVER_JOB,
    CLIENT_START_TIMESTAMP,
    CLIENT_FINISH_TIMESTAMP,
    SERVER_START_TIMESTAMP,
    SERVER_FINISH_TIMESTAMP,
    SERVER_APP_DELTA,
    NUM_CHILDREN,
    NUM_DESCENDANTS,
    REQUEST_NETWORK_DELTA,
    RESPONSE_NETWORK_DELTA,
    CLIENT_SEND_QUEUE_DELTA,
    SERVER_SEND_QUEUE_DELTA,
    CLIENT_RECV_QUEUE_DELTA,
    SERVER_RECV_QUEUE_DELTA,
])

# Optional column names
BILLABLE_SERVICE: Final[str] = 'billable_service'
REFERENCES: Final[str] = 'references'

OPTIONAL_COLUMNS: Final[FrozenSet[str]] = frozenset(
    [BILLABLE_SERVICE, REFERENCES]
)

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

# Legacy camelCase aliases for backward compatibility if needed
PARENT_SPAN_ID: Final[str] = 'parentSpanID'

# Other DataFrame columns
RTT_TIME: Final[str] = 'rtt_time'

# String literals for method renaming
MONGO: Final[str] = 'Mongo'
MMC: Final[str] = 'Mmc'
REDIS: Final[str] = 'Redis'
SUFFIX_MONGODB: Final[str] = '-mongodb'
SUFFIX_MEMCACHED: Final[str] = '-memcached'
SUFFIX_REDIS: Final[str] = '-redis'
SERVICE_SUFFIX: Final[str] = '-service'
