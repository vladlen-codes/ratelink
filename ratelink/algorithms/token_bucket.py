import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, Tuple, Optional
from ..core.abstractions import Algorithm
from ..core.types import RateLimitState

class TokenBucketAlgorithm(Algorithm):
    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        refill_period: float = 1.0,
        initial_tokens: Optional[int] = None) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")
        if refill_period <= 0:
            raise ValueError("refill_period must be positive")
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.refill_period = refill_period
        self.initial_tokens = initial_tokens if initial_tokens is not None else capacity
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = RLock()

    def _refill_tokens(self, key: str, current_time: float) -> Tuple[float, float]:
        if key not in self._buckets:
            return (self.initial_tokens, current_time)
        tokens, last_refill = self._buckets[key]
        time_passed = current_time - last_refill
        if time_passed > 0:
            tokens_to_add = (time_passed / self.refill_period) * self.refill_rate
            tokens = min(self.capacity, tokens + tokens_to_add)
        return (tokens, current_time)

    def allow(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            tokens, last_refill = self._refill_tokens(key, current_time)
            if tokens >= weight:
                tokens -= weight
                self._buckets[key] = (tokens, current_time)
                tokens_needed = self.capacity - tokens
                seconds_to_full = (tokens_needed / self.refill_rate) * self.refill_period
                reset_at = datetime.fromtimestamp(current_time + seconds_to_full)
                state = RateLimitState(
                    limit=self.capacity,
                    remaining=int(tokens),
                    reset_at=reset_at,
                    retry_after=0.0,
                    violated=False,
                    metadata={"algorithm": "token_bucket", "refill_rate": self.refill_rate},
                )
                return (True, state)
            else:
                self._buckets[key] = (tokens, current_time)
                tokens_needed = weight - tokens
                retry_after = (tokens_needed / self.refill_rate) * self.refill_period
                reset_at = datetime.fromtimestamp(current_time + retry_after)
                state = RateLimitState(
                    limit=self.capacity,
                    remaining=int(tokens),
                    reset_at=reset_at,
                    retry_after=retry_after,
                    violated=True,
                    metadata={"algorithm": "token_bucket", "refill_rate": self.refill_rate},
                )
                return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()
        with self._lock:
            tokens, _ = self._refill_tokens(key, current_time)
            tokens_needed = self.capacity - tokens
            seconds_to_full = (tokens_needed / self.refill_rate) * self.refill_period
            reset_at = datetime.fromtimestamp(current_time + seconds_to_full)
            return RateLimitState(
                limit=self.capacity,
                remaining=int(tokens),
                reset_at=reset_at,
                retry_after=0.0,
                violated=False,
                metadata={"algorithm": "token_bucket"},
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            elif key in self._buckets:
                del self._buckets[key]