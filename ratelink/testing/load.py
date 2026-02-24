"""
Load and benchmark helpers for rate limiters.

Provides tools to simulate concurrent load and measure performance.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class LoadTestResult:
    total_requests: int
    allowed: int
    denied: int
    duration_seconds: float
    requests_per_second: float
    latencies: List[float]
    errors: int = 0
    
    @property
    def min_latency(self) -> float:
        return min(self.latencies) * 1000 if self.latencies else 0.0
    
    @property
    def max_latency(self) -> float:
        return max(self.latencies) * 1000 if self.latencies else 0.0
    
    @property
    def avg_latency(self) -> float:
        return (sum(self.latencies) / len(self.latencies) * 1000) if self.latencies else 0.0
    
    @property
    def p50_latency(self) -> float:
        return self._percentile(50)
    
    @property
    def p95_latency(self) -> float:
        return self._percentile(95)
    
    @property
    def p99_latency(self) -> float:
        return self._percentile(99)
    
    def _percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * (p / 100))
        return sorted_latencies[min(index, len(sorted_latencies) - 1)] * 1000
    
    def summary(self) -> str:
        return f"""
Load Test Results:
  Total Requests:    {self.total_requests:,}
  Allowed:           {self.allowed:,} ({self.allowed/self.total_requests*100:.1f}%)
  Denied:            {self.denied:,} ({self.denied/self.total_requests*100:.1f}%)
  Errors:            {self.errors:,}
  Duration:          {self.duration_seconds:.2f}s
  Throughput:        {self.requests_per_second:.2f} req/s
  
Latency (ms):
  Min:               {self.min_latency:.2f}
  Avg:               {self.avg_latency:.2f}
  P50:               {self.p50_latency:.2f}
  P95:               {self.p95_latency:.2f}
  P99:               {self.p99_latency:.2f}
  Max:               {self.max_latency:.2f}
        """.strip()


def simulate_load(
    limiter: Any,
    num_users: int,
    requests_per_user: int,
    key_generator: Optional[Callable[[int], str]] = None,
    weight: int = 1,
    max_workers: Optional[int] = None
) -> LoadTestResult:
    if key_generator is None:
        key_generator = lambda user_id: f"user:{user_id}"
    
    if max_workers is None:
        max_workers = min(num_users, 100)
    
    total_requests = num_users * requests_per_user
    allowed = 0
    denied = 0
    errors = 0
    latencies = []
    
    def make_requests(user_id: int) -> tuple:
        user_allowed = 0
        user_denied = 0
        user_errors = 0
        user_latencies = []
        
        key = key_generator(user_id)
        
        for _ in range(requests_per_user):
            start = time.time()
            try:
                is_allowed, state = limiter.check(key, weight)
                latency = time.time() - start
                
                user_latencies.append(latency)
                
                if is_allowed:
                    user_allowed += 1
                else:
                    user_denied += 1
                    
            except Exception as e:
                user_errors += 1
                latency = time.time() - start
                user_latencies.append(latency)
        
        return user_allowed, user_denied, user_errors, user_latencies
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(make_requests, user_id) for user_id in range(num_users)]
        
        for future in as_completed(futures):
            user_allowed, user_denied, user_errors, user_latencies = future.result()
            allowed += user_allowed
            denied += user_denied
            errors += user_errors
            latencies.extend(user_latencies)
    
    duration = time.time() - start_time
    
    return LoadTestResult(
        total_requests=total_requests,
        allowed=allowed,
        denied=denied,
        duration_seconds=duration,
        requests_per_second=total_requests / duration if duration > 0 else 0,
        latencies=latencies,
        errors=errors
    )


async def simulate_load_async(
    limiter: Any,
    num_users: int,
    requests_per_user: int,
    key_generator: Optional[Callable[[int], str]] = None,
    weight: int = 1
) -> LoadTestResult:
    if key_generator is None:
        key_generator = lambda user_id: f"user:{user_id}"
    
    total_requests = num_users * requests_per_user
    allowed = 0
    denied = 0
    errors = 0
    latencies = []
    
    async def make_requests(user_id: int) -> tuple:
        user_allowed = 0
        user_denied = 0
        user_errors = 0
        user_latencies = []
        
        key = key_generator(user_id)
        
        for _ in range(requests_per_user):
            start = time.time()
            try:
                if hasattr(limiter, 'acheck'):
                    is_allowed, state = await limiter.acheck(key, weight)
                else:
                    is_allowed, state = limiter.check(key, weight)
                
                latency = time.time() - start
                user_latencies.append(latency)
                
                if is_allowed:
                    user_allowed += 1
                else:
                    user_denied += 1
                    
            except Exception as e:
                user_errors += 1
                latency = time.time() - start
                user_latencies.append(latency)
        
        return user_allowed, user_denied, user_errors, user_latencies
    
    start_time = time.time()
    
    tasks = [make_requests(user_id) for user_id in range(num_users)]
    results = await asyncio.gather(*tasks)
    
    for user_allowed, user_denied, user_errors, user_latencies in results:
        allowed += user_allowed
        denied += user_denied
        errors += user_errors
        latencies.extend(user_latencies)
    
    duration = time.time() - start_time
    
    return LoadTestResult(
        total_requests=total_requests,
        allowed=allowed,
        denied=denied,
        duration_seconds=duration,
        requests_per_second=total_requests / duration if duration > 0 else 0,
        latencies=latencies,
        errors=errors
    )


def benchmark_algorithm(
    algorithm_name: str,
    limit: int,
    window: int,
    num_requests: int = 10000,
    backend: Optional[Any] = None
) -> LoadTestResult:
    try:
        from ratelink import RateLimiter
        
        limiter = RateLimiter(
            algorithm=algorithm_name,
            limit=limit,
            window=window,
            backend=backend
        )
        
        return simulate_load(
            limiter,
            num_users=1,
            requests_per_user=num_requests,
            key_generator=lambda _: "benchmark:user"
        )
        
    except ImportError:
        raise ImportError("RateLimiter not available for benchmarking")


def compare_algorithms(
    limit: int = 100,
    window: int = 60,
    num_requests: int = 1000
) -> Dict[str, LoadTestResult]:
    algorithms = [
        'token_bucket',
        'leaky_bucket',
        'fixed_window',
        'sliding_window',
        'sliding_window_log',
    ]
    
    results = {}
    
    for algo in algorithms:
        try:
            result = benchmark_algorithm(algo, limit, window, num_requests)
            results[algo] = result
        except Exception as e:
            print(f"Failed to benchmark {algo}: {e}")
    
    return results

def stress_test(
    limiter: Any,
    duration_seconds: float = 10.0,
    num_workers: int = 10,
    key_generator: Optional[Callable[[int], str]] = None
) -> LoadTestResult:
    if key_generator is None:
        key_generator = lambda worker_id: f"worker:{worker_id}"
    
    allowed = 0
    denied = 0
    errors = 0
    latencies = []
    total_requests = 0
    
    def worker(worker_id: int, stop_time: float) -> tuple:
        worker_allowed = 0
        worker_denied = 0
        worker_errors = 0
        worker_latencies = []
        worker_requests = 0
        
        key = key_generator(worker_id)
        
        while time.time() < stop_time:
            start = time.time()
            try:
                is_allowed, state = limiter.check(key, weight=1)
                latency = time.time() - start
                
                worker_latencies.append(latency)
                worker_requests += 1
                
                if is_allowed:
                    worker_allowed += 1
                else:
                    worker_denied += 1
                    
            except Exception as e:
                worker_errors += 1
                latency = time.time() - start
                worker_latencies.append(latency)
                worker_requests += 1
        
        return worker_allowed, worker_denied, worker_errors, worker_latencies, worker_requests
    
    start_time = time.time()
    stop_time = start_time + duration_seconds
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, worker_id, stop_time) for worker_id in range(num_workers)]
        
        for future in as_completed(futures):
            w_allowed, w_denied, w_errors, w_latencies, w_requests = future.result()
            allowed += w_allowed
            denied += w_denied
            errors += w_errors
            latencies.extend(w_latencies)
            total_requests += w_requests
    
    duration = time.time() - start_time
    
    return LoadTestResult(
        total_requests=total_requests,
        allowed=allowed,
        denied=denied,
        duration_seconds=duration,
        requests_per_second=total_requests / duration if duration > 0 else 0,
        latencies=latencies,
        errors=errors
    )