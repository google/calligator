from google.protobuf.internal import containers as _containers  # type: ignore[import-untyped]
from google.protobuf import descriptor as _descriptor  # type: ignore[import-untyped]
from google.protobuf import message as _message  # type: ignore[import-untyped]
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DependencyGraphNodeProto(_message.Message):
    __slots__ = ("node_key", "parent_node_key", "happens_before", "child_dependents", "async_children", "median_start_delay_sec", "median_end_delay_sec")
    NODE_KEY_FIELD_NUMBER: _ClassVar[int]
    PARENT_NODE_KEY_FIELD_NUMBER: _ClassVar[int]
    HAPPENS_BEFORE_FIELD_NUMBER: _ClassVar[int]
    CHILD_DEPENDENTS_FIELD_NUMBER: _ClassVar[int]
    ASYNC_CHILDREN_FIELD_NUMBER: _ClassVar[int]
    MEDIAN_START_DELAY_SEC_FIELD_NUMBER: _ClassVar[int]
    MEDIAN_END_DELAY_SEC_FIELD_NUMBER: _ClassVar[int]
    node_key: str
    parent_node_key: str
    happens_before: _containers.RepeatedScalarFieldContainer[str]
    child_dependents: _containers.RepeatedScalarFieldContainer[str]
    async_children: _containers.RepeatedScalarFieldContainer[str]
    median_start_delay_sec: float
    median_end_delay_sec: float
    def __init__(self, node_key: _Optional[str] = ..., parent_node_key: _Optional[str] = ..., happens_before: _Optional[_Iterable[str]] = ..., child_dependents: _Optional[_Iterable[str]] = ..., async_children: _Optional[_Iterable[str]] = ..., median_start_delay_sec: _Optional[float] = ..., median_end_delay_sec: _Optional[float] = ...) -> None: ...

class DependencyGraphProto(_message.Message):
    __slots__ = ("nodes",)
    NODES_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[DependencyGraphNodeProto]
    def __init__(self, nodes: _Optional[_Iterable[_Union[DependencyGraphNodeProto, _Mapping]]] = ...) -> None: ...

class ComponentDeltasProto(_message.Message):
    __slots__ = ("server_app_delta", "client_send_queue_delta", "server_recv_queue_delta", "client_recv_queue_delta", "server_send_queue_delta", "request_network_delta", "response_network_delta", "server_app_delta_f64")
    SERVER_APP_DELTA_FIELD_NUMBER: _ClassVar[int]
    CLIENT_SEND_QUEUE_DELTA_FIELD_NUMBER: _ClassVar[int]
    SERVER_RECV_QUEUE_DELTA_FIELD_NUMBER: _ClassVar[int]
    CLIENT_RECV_QUEUE_DELTA_FIELD_NUMBER: _ClassVar[int]
    SERVER_SEND_QUEUE_DELTA_FIELD_NUMBER: _ClassVar[int]
    REQUEST_NETWORK_DELTA_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_NETWORK_DELTA_FIELD_NUMBER: _ClassVar[int]
    SERVER_APP_DELTA_F64_FIELD_NUMBER: _ClassVar[int]
    server_app_delta: float
    client_send_queue_delta: float
    server_recv_queue_delta: float
    client_recv_queue_delta: float
    server_send_queue_delta: float
    request_network_delta: float
    response_network_delta: float
    server_app_delta_f64: float
    def __init__(self, server_app_delta: _Optional[float] = ..., client_send_queue_delta: _Optional[float] = ..., server_recv_queue_delta: _Optional[float] = ..., client_recv_queue_delta: _Optional[float] = ..., server_send_queue_delta: _Optional[float] = ..., request_network_delta: _Optional[float] = ..., response_network_delta: _Optional[float] = ..., server_app_delta_f64: _Optional[float] = ...) -> None: ...

class SpanMetricsProto(_message.Message):
    __slots__ = ("trace_id", "span_id", "parent_rpc_span_id", "method_name", "server_job", "start_timestamp_sec", "finish_timestamp_sec", "duration_sec", "component_deltas", "is_critical_path", "exclusive_drag_sec", "inclusive_drag_sec", "slack_sec", "relative_exclusive_drag", "relative_slack", "num_descendants", "start_timestamp_sec_f64", "finish_timestamp_sec_f64", "duration_sec_f64", "exclusive_drag_sec_f64", "inclusive_drag_sec_f64", "slack_sec_f64")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_RPC_SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    METHOD_NAME_FIELD_NUMBER: _ClassVar[int]
    SERVER_JOB_FIELD_NUMBER: _ClassVar[int]
    START_TIMESTAMP_SEC_FIELD_NUMBER: _ClassVar[int]
    FINISH_TIMESTAMP_SEC_FIELD_NUMBER: _ClassVar[int]
    DURATION_SEC_FIELD_NUMBER: _ClassVar[int]
    COMPONENT_DELTAS_FIELD_NUMBER: _ClassVar[int]
    IS_CRITICAL_PATH_FIELD_NUMBER: _ClassVar[int]
    EXCLUSIVE_DRAG_SEC_FIELD_NUMBER: _ClassVar[int]
    INCLUSIVE_DRAG_SEC_FIELD_NUMBER: _ClassVar[int]
    SLACK_SEC_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_EXCLUSIVE_DRAG_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_SLACK_FIELD_NUMBER: _ClassVar[int]
    NUM_DESCENDANTS_FIELD_NUMBER: _ClassVar[int]
    START_TIMESTAMP_SEC_F64_FIELD_NUMBER: _ClassVar[int]
    FINISH_TIMESTAMP_SEC_F64_FIELD_NUMBER: _ClassVar[int]
    DURATION_SEC_F64_FIELD_NUMBER: _ClassVar[int]
    EXCLUSIVE_DRAG_SEC_F64_FIELD_NUMBER: _ClassVar[int]
    INCLUSIVE_DRAG_SEC_F64_FIELD_NUMBER: _ClassVar[int]
    SLACK_SEC_F64_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    span_id: str
    parent_rpc_span_id: str
    method_name: str
    server_job: str
    start_timestamp_sec: float
    finish_timestamp_sec: float
    duration_sec: float
    component_deltas: ComponentDeltasProto
    is_critical_path: bool
    exclusive_drag_sec: float
    inclusive_drag_sec: float
    slack_sec: float
    relative_exclusive_drag: float
    relative_slack: float
    num_descendants: int
    start_timestamp_sec_f64: float
    finish_timestamp_sec_f64: float
    duration_sec_f64: float
    exclusive_drag_sec_f64: float
    inclusive_drag_sec_f64: float
    slack_sec_f64: float
    def __init__(self, trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., parent_rpc_span_id: _Optional[str] = ..., method_name: _Optional[str] = ..., server_job: _Optional[str] = ..., start_timestamp_sec: _Optional[float] = ..., finish_timestamp_sec: _Optional[float] = ..., duration_sec: _Optional[float] = ..., component_deltas: _Optional[_Union[ComponentDeltasProto, _Mapping]] = ..., is_critical_path: _Optional[bool] = ..., exclusive_drag_sec: _Optional[float] = ..., inclusive_drag_sec: _Optional[float] = ..., slack_sec: _Optional[float] = ..., relative_exclusive_drag: _Optional[float] = ..., relative_slack: _Optional[float] = ..., num_descendants: _Optional[int] = ..., start_timestamp_sec_f64: _Optional[float] = ..., finish_timestamp_sec_f64: _Optional[float] = ..., duration_sec_f64: _Optional[float] = ..., exclusive_drag_sec_f64: _Optional[float] = ..., inclusive_drag_sec_f64: _Optional[float] = ..., slack_sec_f64: _Optional[float] = ...) -> None: ...

class TraceCacheProto(_message.Message):
    __slots__ = ("input_source", "trace_count", "generated_at", "is_jaeger_trace", "depgraph", "spans")
    INPUT_SOURCE_FIELD_NUMBER: _ClassVar[int]
    TRACE_COUNT_FIELD_NUMBER: _ClassVar[int]
    GENERATED_AT_FIELD_NUMBER: _ClassVar[int]
    IS_JAEGER_TRACE_FIELD_NUMBER: _ClassVar[int]
    DEPGRAPH_FIELD_NUMBER: _ClassVar[int]
    SPANS_FIELD_NUMBER: _ClassVar[int]
    input_source: str
    trace_count: int
    generated_at: str
    is_jaeger_trace: bool
    depgraph: DependencyGraphProto
    spans: _containers.RepeatedCompositeFieldContainer[SpanMetricsProto]
    def __init__(self, input_source: _Optional[str] = ..., trace_count: _Optional[int] = ..., generated_at: _Optional[str] = ..., is_jaeger_trace: _Optional[bool] = ..., depgraph: _Optional[_Union[DependencyGraphProto, _Mapping]] = ..., spans: _Optional[_Iterable[_Union[SpanMetricsProto, _Mapping]]] = ...) -> None: ...

class MethodDragRankingProto(_message.Message):
    __slots__ = ("rank", "method", "exclusive_drag_sec", "relative_drag", "mean", "std", "p50", "p90", "p95", "p99", "expected_per_trace_sec", "cp_share")
    RANK_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    EXCLUSIVE_DRAG_SEC_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_DRAG_FIELD_NUMBER: _ClassVar[int]
    MEAN_FIELD_NUMBER: _ClassVar[int]
    STD_FIELD_NUMBER: _ClassVar[int]
    P50_FIELD_NUMBER: _ClassVar[int]
    P90_FIELD_NUMBER: _ClassVar[int]
    P95_FIELD_NUMBER: _ClassVar[int]
    P99_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_PER_TRACE_SEC_FIELD_NUMBER: _ClassVar[int]
    CP_SHARE_FIELD_NUMBER: _ClassVar[int]
    rank: int
    method: str
    exclusive_drag_sec: float
    relative_drag: float
    mean: float
    std: float
    p50: float
    p90: float
    p95: float
    p99: float
    expected_per_trace_sec: float
    cp_share: float
    def __init__(self, rank: _Optional[int] = ..., method: _Optional[str] = ..., exclusive_drag_sec: _Optional[float] = ..., relative_drag: _Optional[float] = ..., mean: _Optional[float] = ..., std: _Optional[float] = ..., p50: _Optional[float] = ..., p90: _Optional[float] = ..., p95: _Optional[float] = ..., p99: _Optional[float] = ..., expected_per_trace_sec: _Optional[float] = ..., cp_share: _Optional[float] = ...) -> None: ...

class RankDragResultProto(_message.Message):
    __slots__ = ("top_k", "stat", "percentile_start", "percentile_end", "trace_count", "root_mean_duration_sec", "rankings", "precomputed_drag_traces")
    TOP_K_FIELD_NUMBER: _ClassVar[int]
    STAT_FIELD_NUMBER: _ClassVar[int]
    PERCENTILE_START_FIELD_NUMBER: _ClassVar[int]
    PERCENTILE_END_FIELD_NUMBER: _ClassVar[int]
    TRACE_COUNT_FIELD_NUMBER: _ClassVar[int]
    ROOT_MEAN_DURATION_SEC_FIELD_NUMBER: _ClassVar[int]
    RANKINGS_FIELD_NUMBER: _ClassVar[int]
    PRECOMPUTED_DRAG_TRACES_FIELD_NUMBER: _ClassVar[int]
    top_k: int
    stat: str
    percentile_start: float
    percentile_end: float
    trace_count: int
    root_mean_duration_sec: float
    rankings: _containers.RepeatedCompositeFieldContainer[MethodDragRankingProto]
    precomputed_drag_traces: int
    def __init__(self, top_k: _Optional[int] = ..., stat: _Optional[str] = ..., percentile_start: _Optional[float] = ..., percentile_end: _Optional[float] = ..., trace_count: _Optional[int] = ..., root_mean_duration_sec: _Optional[float] = ..., rankings: _Optional[_Iterable[_Union[MethodDragRankingProto, _Mapping]]] = ..., precomputed_drag_traces: _Optional[int] = ...) -> None: ...

class MetricStatsProto(_message.Message):
    __slots__ = ("mean", "std", "p50", "p90", "p95", "p99")
    MEAN_FIELD_NUMBER: _ClassVar[int]
    STD_FIELD_NUMBER: _ClassVar[int]
    P50_FIELD_NUMBER: _ClassVar[int]
    P90_FIELD_NUMBER: _ClassVar[int]
    P95_FIELD_NUMBER: _ClassVar[int]
    P99_FIELD_NUMBER: _ClassVar[int]
    mean: float
    std: float
    p50: float
    p90: float
    p95: float
    p99: float
    def __init__(self, mean: _Optional[float] = ..., std: _Optional[float] = ..., p50: _Optional[float] = ..., p90: _Optional[float] = ..., p95: _Optional[float] = ..., p99: _Optional[float] = ...) -> None: ...

class MetricValuesProto(_message.Message):
    __slots__ = ("original", "retimed")
    ORIGINAL_FIELD_NUMBER: _ClassVar[int]
    RETIMED_FIELD_NUMBER: _ClassVar[int]
    original: _containers.RepeatedScalarFieldContainer[float]
    retimed: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, original: _Optional[_Iterable[float]] = ..., retimed: _Optional[_Iterable[float]] = ...) -> None: ...

class MetricSummaryProto(_message.Message):
    __slots__ = ("original_stats", "retimed_stats")
    ORIGINAL_STATS_FIELD_NUMBER: _ClassVar[int]
    RETIMED_STATS_FIELD_NUMBER: _ClassVar[int]
    original_stats: MetricStatsProto
    retimed_stats: MetricStatsProto
    def __init__(self, original_stats: _Optional[_Union[MetricStatsProto, _Mapping]] = ..., retimed_stats: _Optional[_Union[MetricStatsProto, _Mapping]] = ...) -> None: ...

class DistributionResultProto(_message.Message):
    __slots__ = ("target_method", "target_service", "with_retiming", "metric_filter", "metrics", "summary")
    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: MetricValuesProto
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[MetricValuesProto, _Mapping]] = ...) -> None: ...
    class SummaryEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: MetricSummaryProto
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[MetricSummaryProto, _Mapping]] = ...) -> None: ...
    TARGET_METHOD_FIELD_NUMBER: _ClassVar[int]
    TARGET_SERVICE_FIELD_NUMBER: _ClassVar[int]
    WITH_RETIMING_FIELD_NUMBER: _ClassVar[int]
    METRIC_FILTER_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    target_method: str
    target_service: str
    with_retiming: bool
    metric_filter: str
    metrics: _containers.MessageMap[str, MetricValuesProto]
    summary: _containers.MessageMap[str, MetricSummaryProto]
    def __init__(self, target_method: _Optional[str] = ..., target_service: _Optional[str] = ..., with_retiming: _Optional[bool] = ..., metric_filter: _Optional[str] = ..., metrics: _Optional[_Mapping[str, MetricValuesProto]] = ..., summary: _Optional[_Mapping[str, MetricSummaryProto]] = ...) -> None: ...

class ImprovementQuantilesProto(_message.Message):
    __slots__ = ("orig_mean_sec", "retimed_mean_sec", "saved_mean_sec", "mean_percent_improvement", "p50_percent_improvement", "p90_percent_improvement", "p95_percent_improvement", "p99_percent_improvement")
    ORIG_MEAN_SEC_FIELD_NUMBER: _ClassVar[int]
    RETIMED_MEAN_SEC_FIELD_NUMBER: _ClassVar[int]
    SAVED_MEAN_SEC_FIELD_NUMBER: _ClassVar[int]
    MEAN_PERCENT_IMPROVEMENT_FIELD_NUMBER: _ClassVar[int]
    P50_PERCENT_IMPROVEMENT_FIELD_NUMBER: _ClassVar[int]
    P90_PERCENT_IMPROVEMENT_FIELD_NUMBER: _ClassVar[int]
    P95_PERCENT_IMPROVEMENT_FIELD_NUMBER: _ClassVar[int]
    P99_PERCENT_IMPROVEMENT_FIELD_NUMBER: _ClassVar[int]
    orig_mean_sec: float
    retimed_mean_sec: float
    saved_mean_sec: float
    mean_percent_improvement: float
    p50_percent_improvement: float
    p90_percent_improvement: float
    p95_percent_improvement: float
    p99_percent_improvement: float
    def __init__(self, orig_mean_sec: _Optional[float] = ..., retimed_mean_sec: _Optional[float] = ..., saved_mean_sec: _Optional[float] = ..., mean_percent_improvement: _Optional[float] = ..., p50_percent_improvement: _Optional[float] = ..., p90_percent_improvement: _Optional[float] = ..., p95_percent_improvement: _Optional[float] = ..., p99_percent_improvement: _Optional[float] = ...) -> None: ...

class PercentImprovementResultProto(_message.Message):
    __slots__ = ("trace_count", "with_retiming", "original_durations_sec", "retimed_durations_sec", "saved_sec", "percent_improvements", "quantiles")
    TRACE_COUNT_FIELD_NUMBER: _ClassVar[int]
    WITH_RETIMING_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_DURATIONS_SEC_FIELD_NUMBER: _ClassVar[int]
    RETIMED_DURATIONS_SEC_FIELD_NUMBER: _ClassVar[int]
    SAVED_SEC_FIELD_NUMBER: _ClassVar[int]
    PERCENT_IMPROVEMENTS_FIELD_NUMBER: _ClassVar[int]
    QUANTILES_FIELD_NUMBER: _ClassVar[int]
    trace_count: int
    with_retiming: bool
    original_durations_sec: _containers.RepeatedScalarFieldContainer[float]
    retimed_durations_sec: _containers.RepeatedScalarFieldContainer[float]
    saved_sec: _containers.RepeatedScalarFieldContainer[float]
    percent_improvements: _containers.RepeatedScalarFieldContainer[float]
    quantiles: ImprovementQuantilesProto
    def __init__(self, trace_count: _Optional[int] = ..., with_retiming: _Optional[bool] = ..., original_durations_sec: _Optional[_Iterable[float]] = ..., retimed_durations_sec: _Optional[_Iterable[float]] = ..., saved_sec: _Optional[_Iterable[float]] = ..., percent_improvements: _Optional[_Iterable[float]] = ..., quantiles: _Optional[_Union[ImprovementQuantilesProto, _Mapping]] = ...) -> None: ...

class ChildMethodCountProto(_message.Message):
    __slots__ = ("child_method", "count")
    CHILD_METHOD_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    child_method: str
    count: int
    def __init__(self, child_method: _Optional[str] = ..., count: _Optional[int] = ...) -> None: ...

class ChildMethodsResultProto(_message.Message):
    __slots__ = ("target_parent", "parent_match_count", "child_methods")
    TARGET_PARENT_FIELD_NUMBER: _ClassVar[int]
    PARENT_MATCH_COUNT_FIELD_NUMBER: _ClassVar[int]
    CHILD_METHODS_FIELD_NUMBER: _ClassVar[int]
    target_parent: str
    parent_match_count: int
    child_methods: _containers.RepeatedCompositeFieldContainer[ChildMethodCountProto]
    def __init__(self, target_parent: _Optional[str] = ..., parent_match_count: _Optional[int] = ..., child_methods: _Optional[_Iterable[_Union[ChildMethodCountProto, _Mapping]]] = ...) -> None: ...

class AnalysisResultProto(_message.Message):
    __slots__ = ("mode", "rank_drag_result", "distribution_result", "percent_improvement_result", "child_methods_result")
    MODE_FIELD_NUMBER: _ClassVar[int]
    RANK_DRAG_RESULT_FIELD_NUMBER: _ClassVar[int]
    DISTRIBUTION_RESULT_FIELD_NUMBER: _ClassVar[int]
    PERCENT_IMPROVEMENT_RESULT_FIELD_NUMBER: _ClassVar[int]
    CHILD_METHODS_RESULT_FIELD_NUMBER: _ClassVar[int]
    mode: str
    rank_drag_result: RankDragResultProto
    distribution_result: DistributionResultProto
    percent_improvement_result: PercentImprovementResultProto
    child_methods_result: ChildMethodsResultProto
    def __init__(self, mode: _Optional[str] = ..., rank_drag_result: _Optional[_Union[RankDragResultProto, _Mapping]] = ..., distribution_result: _Optional[_Union[DistributionResultProto, _Mapping]] = ..., percent_improvement_result: _Optional[_Union[PercentImprovementResultProto, _Mapping]] = ..., child_methods_result: _Optional[_Union[ChildMethodsResultProto, _Mapping]] = ...) -> None: ...
