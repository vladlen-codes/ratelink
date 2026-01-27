import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, Tuple, Optional
from collections import deque
from ..core.abstractions import Algorithm
from ..core.types import RateLimitState

class LeakyBucketAlgorithm(Algorithm):
    def __init__(self, capacity: int, leak_rate: float, leak_period: float = 1.0) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if leak_rate <= 0:
            raise ValueError("leak_rate must be positive")
        if leak_period <= 0:
            raise ValueError("leak_period must be positive")
        self.capacity = capacity
        self.leak_rate = leak_rate
        self.leak_period = leak_period
        self._buckets: Dict[str, Tuple[deque, float]] = {}
        self._lock = RLock()

    def _leak_bucket(self, key: str, current_time: float) -> deque:
        if key not in self._buckets:
            return deque()
        queue, last_leak = self._buckets[key]
        time_passed = current_time - last_leak
        if time_passed > 0:
            leaks = int((time_passed / self.leak_period) * self.leak_rate)
            for _ in range(min(leaks, len(queue))):
                queue.popleft()
            self._buckets[key] = (queue, current_time)

        return queue

    def allow(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            queue = self._leak_bucket(key, current_time)
            current_size = len(queue)
            if current_size + weight <= self.capacity:
                if key not in self._buckets:
                    self._buckets[key] = (deque(), current_time)

                queue, _ = self._buckets[key]
                for _ in range(weight):
                    queue.append(current_time)

                self._buckets[key] = (queue, current_time)

                remaining = self.capacity - (current_size + weight)

                # Calculate when bucket will be empty
                time_to_empty = (len(queue) / self.leak_rate) * self.leak_period
                reset_at = datetime.fromtimestamp(current_time + time_to_empty)

                state = RateLimitState(
                    limit=self.capacity,
                    remaining=remaining,
                    reset_at=reset_at,
                    retry_after=0.0,
                    violated=False,
                    metadata={
                        "algorithm": "leaky_bucket",
                        "leak_rate": self.leak_rate,
                        "queue_size": len(queue),
                    },
                )
                return (True, state)
            else:
                items_to_leak = (current_size + weight) - self.capacity
                retry_after = (items_to_leak / self.leak_rate) * self.leak_period
                reset_at = datetime.fromtimestamp(current_time + retry_after)
                state = RateLimitState(
                    limit=self.capacity,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                    violated=True,
                    metadata={
                        "algorithm": "leaky_bucket",
                        "leak_rate": self.leak_rate,
                        "queue_size": current_size,
                    },
                )
                return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()
        with self._lock:
            queue = self._leak_bucket(key, current_time)
            current_size = len(queue)
            remaining = max(0, self.capacity - current_size)
            if current_size > 0:
                time_to_empty = (current_size / self.leak_rate) * self.leak_period
            else:
                time_to_empty = 0.0
            reset_at = datetime.fromtimestamp(current_time + time_to_empty)
            return RateLimitState(
                limit=self.capacity,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=0.0 if remaining > 0 else time_to_empty,
                violated=remaining == 0,
                metadata={
                    "algorithm": "leaky_bucket",
                    "queue_size": current_size,
                },
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            elif key in self._buckets:
                del self._buckets[key]