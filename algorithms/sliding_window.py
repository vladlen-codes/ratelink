import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, List, Tuple, Optional
from ..core.abstractions import Algorithm
from ..core.types import RateLimitState

class SlidingWindowAlgorithm(Algorithm):
    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
        self._lock = RLock()

    def _cleanup_old_requests(self, key: str, current_time: float) -> List[float]:
        cutoff_time = current_time - self.window_seconds
        if key not in self._requests:
            return []
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff_time]
        return self._requests[key]

    def allow(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            requests = self._cleanup_old_requests(key, current_time)
            current_count = len(requests)
            if current_count + weight <= self.limit:
                if key not in self._requests:
                    self._requests[key] = []
                for _ in range(weight):
                    self._requests[key].append(current_time)
                remaining = self.limit - (current_count + weight)
                reset_at = datetime.fromtimestamp(current_time + self.window_seconds)
                state = RateLimitState(
                    limit=self.limit,
                    remaining=remaining,
                    reset_at=reset_at,
                    retry_after=0.0,
                    violated=False,
                    metadata={
                        "algorithm": "sliding_window",
                        "window_seconds": self.window_seconds,
                        "current_count": current_count + weight,
                    },
                )
                return (True, state)
            else:
                if requests:
                    oldest_request = min(requests)
                    retry_after = max(0.0, oldest_request + self.window_seconds - current_time)
                else:
                    retry_after = 0.0
                reset_at = datetime.fromtimestamp(current_time + retry_after)
                state = RateLimitState(
                    limit=self.limit,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                    violated=True,
                    metadata={
                        "algorithm": "sliding_window",
                        "window_seconds": self.window_seconds,
                        "current_count": current_count,
                    },
                )
                return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()
        with self._lock:
            requests = self._cleanup_old_requests(key, current_time)
            current_count = len(requests)
            remaining = max(0, self.limit - current_count)
            if requests:
                oldest_request = min(requests)
                seconds_until_reset = oldest_request + self.window_seconds - current_time
            else:
                seconds_until_reset = self.window_seconds
            reset_at = datetime.fromtimestamp(current_time + max(0, seconds_until_reset))
            return RateLimitState(
                limit=self.limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=0.0 if remaining > 0 else seconds_until_reset,
                violated=remaining == 0,
                metadata={
                    "algorithm": "sliding_window",
                    "current_count": current_count,
                },
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._requests.clear()
            elif key in self._requests:
                del self._requests[key]