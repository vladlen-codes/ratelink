from typing import Optional

try:
    from prometheus_client import Counter, Gauge, Histogram, REGISTRY, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from .collector import MetricsCollector


class PrometheusExporter(MetricsCollector):
    def __init__(
        self,
        namespace: str = "rate_limiter",
        registry=None
    ):
        if not PROMETHEUS_AVAILABLE:
            raise ImportError(
                "prometheus_client is required for PrometheusExporter. "
                "Install with: pip install prometheus-client"
            )
        
        super().__init__()
        
        self._namespace = namespace
        self._registry = registry or REGISTRY

        self._prom_checks = Counter(
            f"{namespace}_checks_total",
            "Total number of rate limit checks",
            ["algorithm", "backend", "result"],
            registry=self._registry
        )
        
        self._prom_violations = Counter(
            f"{namespace}_violations_total",
            "Total number of rate limit violations",
            ["algorithm", "backend", "key"],
            registry=self._registry
        )
        
        self._prom_remaining = Gauge(
            f"{namespace}_remaining",
            "Remaining capacity for rate limit key",
            ["key"],
            registry=self._registry
        )
        
        self._prom_reset_seconds = Gauge(
            f"{namespace}_reset_seconds",
            "Seconds until rate limit reset",
            ["key"],
            registry=self._registry
        )
        
        self._prom_latency = Histogram(
            f"{namespace}_latency_seconds",
            "Latency of rate limiting operations",
            ["backend", "operation"],
            buckets=[
                0.001, 0.005, 0.01, 0.025, 0.05, 0.1,
                0.25, 0.5, 1.0, 2.5, 5.0, 10.0
            ],
            registry=self._registry
        )
    
    def inc_checks(
        self,
        algorithm: str,
        backend: str,
        result: str
    ) -> None:
        super().inc_checks(algorithm, backend, result)
        self._prom_checks.labels(
            algorithm=algorithm,
            backend=backend,
            result=result
        ).inc()
    
    def inc_violation(
        self,
        algorithm: str,
        backend: str,
        key: str
    ) -> None:
        super().inc_violation(algorithm, backend, key)
        self._prom_violations.labels(
            algorithm=algorithm,
            backend=backend,
            key=key
        ).inc()
    
    def set_remaining(self, key: str, remaining: int) -> None:
        super().set_remaining(key, remaining)
        self._prom_remaining.labels(key=key).set(remaining)
    
    def set_reset_seconds(self, key: str, seconds: float) -> None:
        super().set_reset_seconds(key, seconds)
        self._prom_reset_seconds.labels(key=key).set(seconds)
    
    def _record_histogram(
        self,
        metric_name: str,
        backend: str,
        operation: str,
        value: float
    ) -> None:
        super()._record_histogram(metric_name, backend, operation, value)
        self._prom_latency.labels(
            backend=backend,
            operation=operation
        ).observe(value)
    
    def render(self) -> str:
        return generate_latest(self._registry).decode("utf-8")
    
    def get_metrics_response(self) -> bytes:
        return generate_latest(self._registry)


def create_prometheus_exporter(
    namespace: str = "rate_limiter",
    registry=None
) -> Optional[PrometheusExporter]:
    if not PROMETHEUS_AVAILABLE:
        return None
    
    return PrometheusExporter(namespace=namespace, registry=registry)
