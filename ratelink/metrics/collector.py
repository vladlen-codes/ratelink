import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass
class MetricValue:
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class HistogramBucket:
    le: float
    count: int = 0


class MetricsCollector:
    def __init__(
        self,
        histogram_buckets: Optional[List[float]] = None
    ):
        self._lock = Lock()
        
        self._counters: Dict[Tuple[str, ...], float] = defaultdict(float)
        
        self._gauges: Dict[Tuple[str, ...], float] = {}
        
        self._histograms: Dict[Tuple[str, ...], Dict] = defaultdict(
            lambda: {
                "buckets": [HistogramBucket(le=b) for b in self._histogram_buckets],
                "sum": 0.0,
                "count": 0,
            }
        )
        
        if histogram_buckets is None:
            self._histogram_buckets = [
                0.001, 0.005, 0.01, 0.025, 0.05, 0.1,
                0.25, 0.5, 1.0, 2.5, 5.0, 10.0
            ]
        else:
            self._histogram_buckets = sorted(histogram_buckets)
    
    def inc_checks(
        self,
        algorithm: str,
        backend: str,
        result: str
    ) -> None:
        key = ("rate_limit_checks_total", algorithm, backend, result)
        with self._lock:
            self._counters[key] += 1
    
    def inc_violation(
        self,
        algorithm: str,
        backend: str,
        key: str
    ) -> None:
        metric_key = ("rate_limit_violations_total", algorithm, backend, key)
        with self._lock:
            self._counters[metric_key] += 1
    
    def set_remaining(self, key: str, remaining: int) -> None:
        metric_key = ("rate_limit_remaining", key)
        with self._lock:
            self._gauges[metric_key] = float(remaining)
    
    def set_reset_seconds(self, key: str, seconds: float) -> None:
        metric_key = ("rate_limit_reset_seconds", key)
        with self._lock:
            self._gauges[metric_key] = seconds
    
    @contextmanager
    def record_latency(
        self,
        backend: str,
        operation: str
    ) -> Iterator[None]:
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start_time
            self._record_histogram(
                "rate_limit_latency_seconds",
                backend,
                operation,
                duration
            )
    
    def _record_histogram(
        self,
        metric_name: str,
        backend: str,
        operation: str,
        value: float
    ) -> None:
        key = (metric_name, backend, operation)
        with self._lock:
            hist = self._histograms[key]
            hist["sum"] += value
            hist["count"] += 1
            for bucket in hist["buckets"]:
                if value <= bucket.le:
                    bucket.count += 1
    
    def get_counters(self) -> Dict[Tuple[str, ...], float]:
        with self._lock:
            return dict(self._counters)
    
    def get_gauges(self) -> Dict[Tuple[str, ...], float]:
        with self._lock:
            return dict(self._gauges)
    
    def get_histograms(self) -> Dict[Tuple[str, ...], Dict]:
        with self._lock:
            result = {}
            for key, hist in self._histograms.items():
                result[key] = {
                    "buckets": [
                        HistogramBucket(le=b.le, count=b.count)
                        for b in hist["buckets"]
                    ],
                    "sum": hist["sum"],
                    "count": hist["count"],
                }
            return result
    
    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
