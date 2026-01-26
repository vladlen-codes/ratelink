import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, Tuple, Optional
from ..core.abstractions import Algorithm
from ..core.types import RateLimitState


class FixedWindowAlgorithm(Algorithm):
    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: Dict[str, Tuple[int, float]] = {}
        self._lock = RLock()

    def _get_window_start(self, current_time: float) -> float:
        return (current_time // self.window_seconds) * self.window_seconds

    def _get_current_window(self, key: str, current_time: float) -> Tuple[int, float]:
        window_start = self._get_window_start(current_time)
        if key not in self._windows:
            return (0, window_start)
        count, last_window_start = self._windows[key]
        if window_start > last_window_start:
            return (0, window_start)

        return (count, window_start)

    def allow(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            count, window_start = self._get_current_window(key, current_time)
            if count + weight <= self.limit:
                new_count = count + weight
                self._windows[key] = (new_count, window_start)
                remaining = self.limit - new_count
                window_end = window_start + self.window_seconds
                reset_at = datetime.fromtimestamp(window_end)
                state = RateLimitState(
                    limit=self.limit,
                    remaining=remaining,
                    reset_at=reset_at,
                    retry_after=0.0,
                    violated=False,
                    metadata={
                        "algorithm": "fixed_window",
                        "window_seconds": self.window_seconds,
                        "window_start": window_start,
                        "current_count": new_count,
                    },
                )
                return (True, state)
            else:
                window_end = window_start + self.window_seconds
                retry_after = window_end - current_time
                reset_at = datetime.fromtimestamp(window_end)

                state = RateLimitState(
                    limit=self.limit,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                    violated=True,
                    metadata={
                        "algorithm": "fixed_window",
                        "window_seconds": self.window_seconds,
                        "window_start": window_start,
                        "current_count": count,
                    },
                )
                return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()
        with self._lock:
            count, window_start = self._get_current_window(key, current_time)
            remaining = max(0, self.limit - count)
            window_end = window_start + self.window_seconds
            reset_at = datetime.fromtimestamp(window_end)
            retry_after = 0.0 if remaining > 0 else window_end - current_time

            return RateLimitState(
                limit=self.limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                violated=remaining == 0,
                metadata={
                    "algorithm": "fixed_window",
                    "current_count": count,
                },
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._windows.clear()
            elif key in self._windows:
                del self._windows[key]