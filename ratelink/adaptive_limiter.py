import time
import psutil
from typing import Dict, Optional, Any, Callable
from threading import RLock
from collections import deque
from .rate_limiter import RateLimiter
from .core.types import RateLimitState

class AdaptiveRateLimiter:
    def __init__(
        self,
        base_limit: int,
        window: Union[int, str],
        backend: str = "memory",
        backend_options: Optional[Dict[str, Any]] = None,
        algorithm: str = "token_bucket",
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
        error_threshold: float = 0.10, 
        latency_threshold: float = 1.0,
        adaptation_factor: float = 0.5,
        recovery_factor: float = 1.1, 
        check_interval: float = 10.0,
        window_size: int = 100,
    ) -> None:
        self.base_limit = base_limit
        self.current_limit = base_limit
        self.window = window
        self.algorithm = algorithm
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.error_threshold = error_threshold
        self.latency_threshold = latency_threshold
        self.adaptation_factor = adaptation_factor
        self.recovery_factor = recovery_factor
        self.check_interval = check_interval
        self.window_size = window_size
        self._request_results: deque = deque(maxlen=window_size)
        self._request_latencies: deque = deque(maxlen=window_size)
        self._last_check = time.time()
        self._lock = RLock()
        self._limiter = RateLimiter(
            algorithm=algorithm,
            backend=backend,
            backend_options=backend_options or {},
            limit=self.current_limit,
            window=window,
        )
        self._total_requests = 0
        self._total_errors = 0
        self._adaptations = 0

    def allow(self, key: str, weight: int = 1) -> bool:
        with self._lock:
            self._maybe_adapt()
            self._total_requests += 1
            return self._limiter.allow(key, weight=weight)

    def record_success(self, latency: Optional[float] = None) -> None:
        with self._lock:
            self._request_results.append(True)
            if latency is not None:
                self._request_latencies.append(latency)

    def record_error(self, latency: Optional[float] = None) -> None:
        with self._lock:
            self._request_results.append(False)
            self._total_errors += 1
            if latency is not None:
                self._request_latencies.append(latency)

    def _maybe_adapt(self) -> None:
        current_time = time.time()
        if current_time - self._last_check < self.check_interval:
            return
        self._last_check = current_time
        should_reduce = False
        should_increase = False
        reason = []
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent > self.cpu_threshold:
                should_reduce = True
                reason.append(f"CPU={cpu_percent:.1f}%")
        except Exception:
            pass 
        try:
            memory = psutil.virtual_memory()
            if memory.percent > self.memory_threshold:
                should_reduce = True
                reason.append(f"Memory={memory.percent:.1f}%")
        except Exception:
            pass
        if len(self._request_results) >= 10:
            error_count = sum(1 for r in self._request_results if not r)
            error_rate = error_count / len(self._request_results)
            if error_rate > self.error_threshold:
                should_reduce = True
                reason.append(f"ErrorRate={error_rate*100:.1f}%")
            elif error_rate < self.error_threshold / 2:
                should_increase = True
        if len(self._request_latencies) >= 10:
            avg_latency = sum(self._request_latencies) / len(self._request_latencies)
            if avg_latency > self.latency_threshold:
                should_reduce = True
                reason.append(f"Latency={avg_latency:.2f}s")
            elif avg_latency < self.latency_threshold / 2:
                should_increase = True
        if should_reduce and self.current_limit > self.base_limit * 0.1:
            new_limit = int(self.current_limit * self.adaptation_factor)
            new_limit = max(new_limit, int(self.base_limit * 0.1))
            self._adapt_limit(new_limit, "reduce", reason)
        elif should_increase and self.current_limit < self.base_limit:
            new_limit = int(self.current_limit * self.recovery_factor)
            new_limit = min(new_limit, self.base_limit)
            self._adapt_limit(new_limit, "increase", ["recovery"])

    def _adapt_limit(
        self,
        new_limit: int,
        direction: str,
        reasons: list
    ) -> None:
        old_limit = self.current_limit
        self.current_limit = new_limit
        self._adaptations += 1
        self._limiter.reconfigure(limit=new_limit)

    def check(self, key: str) -> RateLimitState:
        state = self._limiter.check(key)
        state.metadata["adaptive"] = True
        state.metadata["base_limit"] = self.base_limit
        state.metadata["current_limit"] = self.current_limit
        state.metadata["adaptations"] = self._adaptations
        return state

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            self._limiter.reset(key)

            if key is None:
                self._request_results.clear()
                self._request_latencies.clear()
                self.current_limit = self.base_limit
                self._total_requests = 0
                self._total_errors = 0

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            error_rate = 0.0
            if len(self._request_results) > 0:
                error_count = sum(1 for r in self._request_results if not r)
                error_rate = error_count / len(self._request_results)

            avg_latency = 0.0
            if len(self._request_latencies) > 0:
                avg_latency = sum(self._request_latencies) / len(self._request_latencies)

            cpu_percent = 0.0
            memory_percent = 0.0

            try:
                cpu_percent = psutil.cpu_percent(interval=0)
                memory_percent = psutil.virtual_memory().percent
            except Exception:
                pass

            return {
                "base_limit": self.base_limit,
                "current_limit": self.current_limit,
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "error_rate": error_rate,
                "avg_latency": avg_latency,
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "adaptations": self._adaptations,
                "window_samples": len(self._request_results),
            }

    def set_thresholds(
        self,
        cpu: Optional[float] = None,
        memory: Optional[float] = None,
        error_rate: Optional[float] = None,
        latency: Optional[float] = None,
    ) -> None:
        with self._lock:
            if cpu is not None:
                self.cpu_threshold = cpu
            if memory is not None:
                self.memory_threshold = memory
            if error_rate is not None:
                self.error_threshold = error_rate
            if latency is not None:
                self.latency_threshold = latency