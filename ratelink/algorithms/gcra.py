import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, Tuple, Optional
from ..core.abstractions import Algorithm
from ..core.types import RateLimitState

class GCRAAlgorithm(Algorithm):
    def __init__(self, limit: int, period_seconds: float, burst: Optional[int] = None) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        self.limit = limit
        self.period_seconds = period_seconds
        self.burst = burst if burst is not None else limit
        self.emission_interval = period_seconds / limit
        self.burst_allowance = self.emission_interval * self.burst
        self._tats: Dict[str, float] = {}
        self._lock = RLock()

    def allow(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            tat = self._tats.get(key, current_time)
            new_tat = max(tat, current_time) + (self.emission_interval * weight)
            allow_at = new_tat - self.burst_allowance
            if current_time >= allow_at:
                self._tats[key] = new_tat
                time_since_tat = current_time - tat
                if time_since_tat > 0:
                    tokens_recovered = time_since_tat / self.emission_interval
                    remaining = min(self.burst, int(tokens_recovered))
                else:
                    remaining = 0
                reset_at = datetime.fromtimestamp(new_tat)
                state = RateLimitState(
                    limit=self.limit,
                    remaining=max(0, remaining),
                    reset_at=reset_at,
                    retry_after=0.0,
                    violated=False,
                    metadata={
                        "algorithm": "gcra",
                        "tat": new_tat,
                        "emission_interval": self.emission_interval,
                    },
                )
                return (True, state)
            else:
                retry_after = allow_at - current_time
                reset_at = datetime.fromtimestamp(allow_at)
                state = RateLimitState(
                    limit=self.limit,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                    violated=True,
                    metadata={
                        "algorithm": "gcra",
                        "tat": tat,
                        "emission_interval": self.emission_interval,
                    },
                )
                return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()
        with self._lock:
            tat = self._tats.get(key, current_time)
            if current_time >= tat:
                remaining = self.burst
                retry_after = 0.0
            else:
                time_until_tat = tat - current_time
                slots_used = int(time_until_tat / self.emission_interval)
                remaining = max(0, self.burst - slots_used)
                retry_after = time_until_tat if remaining == 0 else 0.0
            reset_at = datetime.fromtimestamp(max(tat, current_time))
            return RateLimitState(
                limit=self.limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                violated=remaining == 0,
                metadata={
                    "algorithm": "gcra",
                    "tat": tat,
                },
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._tats.clear()
            elif key in self._tats:
                del self._tats[key]