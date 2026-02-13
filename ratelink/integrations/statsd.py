import socket
import time
from contextlib import contextmanager
from threading import Lock
from typing import Dict, Iterator, Optional

from ratelink.observability.metrics import MetricsCollector


class StatsDExporter(MetricsCollector):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8125,
        prefix: str = "rate_limiter",
        max_packet_size: int = 512,
        sample_rate: float = 1.0
    ):
        super().__init__()
        self._host = host
        self._port = port
        self._prefix = prefix.rstrip(".")
        self._max_packet_size = max_packet_size
        self._sample_rate = sample_rate
        
        self._socket: Optional[socket.socket] = None
        self._socket_lock = Lock()
        
        self._send_failures = 0
        self._last_error: Optional[Exception] = None
    
    def _get_socket(self) -> socket.socket:
        if self._socket is None:
            with self._socket_lock:
                if self._socket is None:
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._socket.setblocking(False)
        return self._socket
    
    def _send(self, metric: str) -> None:
        try:
            sock = self._get_socket()
            data = metric.encode("utf-8")
            
            if len(data) > self._max_packet_size:
                data = data[:self._max_packet_size]
            
            sock.sendto(data, (self._host, self._port))
        except Exception as e:
            self._send_failures += 1
            self._last_error = e
    
    def _format_tags(self, tags: Dict[str, str]) -> str:
        if not tags:
            return ""
        tag_list = [f"{k}:{v}" for k, v in sorted(tags.items())]
        return f"|#{','.join(tag_list)}"
    
    def _format_metric(
        self,
        name: str,
        value: float,
        metric_type: str,
        tags: Optional[Dict[str, str]] = None,
        sample_rate: Optional[float] = None
    ) -> str:
        full_name = f"{self._prefix}.{name}"
        rate = sample_rate or self._sample_rate
        
        metric = f"{full_name}:{value}|{metric_type}"
        
        if rate < 1.0:
            metric += f"|@{rate}"
        
        if tags:
            metric += self._format_tags(tags)
        
        return metric
    
    def inc_checks(
        self,
        algorithm: str,
        backend: str,
        result: str
    ) -> None:
        super().inc_checks(algorithm, backend, result)
        
        metric = self._format_metric(
            "checks",
            1,
            "c",
            tags={
                "algorithm": algorithm,
                "backend": backend,
                "result": result
            }
        )
        self._send(metric)
    
    def inc_violation(
        self,
        algorithm: str,
        backend: str,
        key: str
    ) -> None:
        super().inc_violation(algorithm, backend, key)
        
        metric = self._format_metric(
            "violations",
            1,
            "c",
            tags={
                "algorithm": algorithm,
                "backend": backend,
                "key": key
            }
        )
        self._send(metric)
    
    def set_remaining(self, key: str, remaining: int) -> None:
        super().set_remaining(key, remaining)
        
        metric = self._format_metric(
            "remaining",
            remaining,
            "g",
            tags={"key": key}
        )
        self._send(metric)
    
    def set_reset_seconds(self, key: str, seconds: float) -> None:
        super().set_reset_seconds(key, seconds)
        
        metric = self._format_metric(
            "reset_seconds",
            seconds,
            "g",
            tags={"key": key}
        )
        self._send(metric)
    
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
            duration_ms = duration * 1000

            self._record_histogram(
                "rate_limit_latency_seconds",
                backend,
                operation,
                duration
            )
            
            metric = self._format_metric(
                "latency",
                duration_ms,
                "ms",
                tags={
                    "backend": backend,
                    "operation": operation
                }
            )
            self._send(metric)
    
    def close(self) -> None:
        if self._socket:
            with self._socket_lock:
                if self._socket:
                    self._socket.close()
                    self._socket = None
    
    def get_stats(self) -> Dict:
        return {
            "send_failures": self._send_failures,
            "last_error": str(self._last_error) if self._last_error else None
        }
    
    def __del__(self):
        self.close()