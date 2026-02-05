import time
from typing import Dict, Tuple, Optional, List
from threading import RLock
from datetime import datetime, timedelta
from ..core.abstractions import Algorithm
from ..core.types import RateLimitState

class HierarchicalTokenBucket(Algorithm):
    def __init__(
        self,
        global_limit: int,
        tenant_limit: int,
        user_limit: int,
        refill_rate: float,
        refill_period: float = 1.0,
    ) -> None:
        if global_limit <= 0 or tenant_limit <= 0 or user_limit <= 0:
            raise ValueError("All limits must be positive")
        if refill_rate <= 0 or refill_period <= 0:
            raise ValueError("Refill rate and period must be positive")
        self.global_limit = global_limit
        self.tenant_limit = tenant_limit
        self.user_limit = user_limit
        self.refill_rate = refill_rate
        self.refill_period = refill_period
        self._global_bucket: Tuple[float, float] = (global_limit, time.time())
        self._tenant_buckets: Dict[str, Tuple[float, float]] = {}
        self._user_buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = RLock()

    def _refill_bucket(
        self,
        current_tokens: float,
        last_refill: float,
        capacity: int,
        current_time: float
    ) -> float:
        time_passed = current_time - last_refill
        if time_passed > 0:
            tokens_to_add = (time_passed / self.refill_period) * self.refill_rate
            current_tokens = min(capacity, current_tokens + tokens_to_add)
        return current_tokens

    def allow(
        self,
        key: str,
        weight: int = 1,
        tenant: Optional[str] = None
    ) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            global_tokens, global_last = self._global_bucket
            global_tokens = self._refill_bucket(
                global_tokens, global_last, self.global_limit, current_time
            )
            if global_tokens < weight:
                return self._create_denial_response(
                    "global", self.global_limit, global_tokens, current_time
                )
            if tenant:
                if tenant not in self._tenant_buckets:
                    self._tenant_buckets[tenant] = (self.tenant_limit, current_time)

                tenant_tokens, tenant_last = self._tenant_buckets[tenant]
                tenant_tokens = self._refill_bucket(
                    tenant_tokens, tenant_last, self.tenant_limit, current_time
                )
                if tenant_tokens < weight:
                    return self._create_denial_response(
                        f"tenant:{tenant}", self.tenant_limit, tenant_tokens, current_time
                    )
            if key not in self._user_buckets:
                self._user_buckets[key] = (self.user_limit, current_time)
            user_tokens, user_last = self._user_buckets[key]
            user_tokens = self._refill_bucket(
                user_tokens, user_last, self.user_limit, current_time
            )
            if user_tokens < weight:
                return self._create_denial_response(
                    f"user:{key}", self.user_limit, user_tokens, current_time
                )
            global_tokens -= weight
            user_tokens -= weight
            self._global_bucket = (global_tokens, current_time)
            self._user_buckets[key] = (user_tokens, current_time)
            if tenant:
                tenant_tokens -= weight
                self._tenant_buckets[tenant] = (tenant_tokens, current_time)

            reset_at = datetime.fromtimestamp(
                current_time + (self.user_limit / self.refill_rate)
            )
            state = RateLimitState(
                limit=self.user_limit,
                remaining=int(user_tokens),
                reset_at=reset_at,
                retry_after=0.0,
                violated=False,
                metadata={
                    "algorithm": "hierarchical_token_bucket",
                    "global_remaining": int(global_tokens),
                    "tenant_remaining": int(tenant_tokens) if tenant else None,
                    "user_remaining": int(user_tokens),
                },
            )
            return (True, state)

    def _create_denial_response(
        self,
        level: str,
        limit: int,
        remaining: float,
        current_time: float
    ) -> Tuple[bool, RateLimitState]:
        tokens_needed = 1 - remaining
        retry_after = (tokens_needed / self.refill_rate) * self.refill_period
        reset_at = datetime.fromtimestamp(current_time + retry_after)

        state = RateLimitState(
            limit=limit,
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after=retry_after,
            violated=True,
            metadata={
                "algorithm": "hierarchical_token_bucket",
                "denied_at_level": level,
            },
        )

        return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()

        with self._lock:
            if key not in self._user_buckets:
                self._user_buckets[key] = (self.user_limit, current_time)

            user_tokens, user_last = self._user_buckets[key]
            user_tokens = self._refill_bucket(
                user_tokens, user_last, self.user_limit, current_time
            )

            global_tokens, global_last = self._global_bucket
            global_tokens = self._refill_bucket(
                global_tokens, global_last, self.global_limit, current_time
            )

            reset_at = datetime.fromtimestamp(
                current_time + (self.user_limit / self.refill_rate)
            )

            return RateLimitState(
                limit=self.user_limit,
                remaining=int(user_tokens),
                reset_at=reset_at,
                retry_after=0.0,
                violated=False,
                metadata={
                    "algorithm": "hierarchical_token_bucket",
                    "global_remaining": int(global_tokens),
                },
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                current_time = time.time()
                self._global_bucket = (self.global_limit, current_time)
                self._tenant_buckets.clear()
                self._user_buckets.clear()
            else:
                self._user_buckets.pop(key, None)


class FairQueueingAlgorithm(Algorithm):
    def __init__(
        self,
        global_limit: int,
        window_seconds: float,
        weights: Optional[Dict[str, float]] = None,
        max_per_key: Optional[int] = None,
    ) -> None:
        if global_limit <= 0:
            raise ValueError("global_limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.global_limit = global_limit
        self.window_seconds = window_seconds
        self.weights = weights or {}
        self.max_per_key = max_per_key
        self._key_counts: Dict[str, List[float]] = {}
        self._lock = RLock()

    def _cleanup_old_requests(self, key: str, current_time: float) -> List[float]:
        cutoff_time = current_time - self.window_seconds
        if key not in self._key_counts:
            return []
        self._key_counts[key] = [
            ts for ts in self._key_counts[key] if ts > cutoff_time
        ]
        return self._key_counts[key]

    def allow(
        self,
        key: str,
        weight: int = 1,
        weight_class: Optional[str] = None
    ) -> Tuple[bool, RateLimitState]:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            requests = self._cleanup_old_requests(key, current_time)
            total_requests = sum(
                len(self._cleanup_old_requests(k, current_time))
                for k in self._key_counts
            )
            if total_requests >= self.global_limit:
                return self._create_denial_response(
                    "global_limit", current_time
                )
            if self.max_per_key and len(requests) >= self.max_per_key:
                return self._create_denial_response(
                    "per_key_limit", current_time
                )
            num_active_keys = len([k for k in self._key_counts if self._key_counts[k]])
            fair_share = self.global_limit / max(1, num_active_keys)
            weight_multiplier = self.weights.get(weight_class or "default", 1.0)
            adjusted_fair_share = fair_share * weight_multiplier
            if len(requests) >= adjusted_fair_share:
                return self._create_denial_response(
                    "fair_share_exceeded", current_time
                )
            if key not in self._key_counts:
                self._key_counts[key] = []

            for _ in range(weight):
                self._key_counts[key].append(current_time)

            remaining = int(adjusted_fair_share - len(self._key_counts[key]))
            reset_at = datetime.fromtimestamp(current_time + self.window_seconds)

            state = RateLimitState(
                limit=int(adjusted_fair_share),
                remaining=max(0, remaining),
                reset_at=reset_at,
                retry_after=0.0,
                violated=False,
                metadata={
                    "algorithm": "fair_queuing",
                    "weight_class": weight_class,
                    "fair_share": fair_share,
                },
            )

            return (True, state)

    def _create_denial_response(
        self,
        reason: str,
        current_time: float
    ) -> Tuple[bool, RateLimitState]:
        """Create denial response."""
        reset_at = datetime.fromtimestamp(current_time + self.window_seconds)

        state = RateLimitState(
            limit=self.global_limit,
            remaining=0,
            reset_at=reset_at,
            retry_after=self.window_seconds,
            violated=True,
            metadata={
                "algorithm": "fair_queuing",
                "denial_reason": reason,
            },
        )

        return (False, state)

    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        return self.allow(key, weight)

    def check(self, key: str) -> RateLimitState:
        current_time = time.time()

        with self._lock:
            requests = self._cleanup_old_requests(key, current_time)

            num_active_keys = len([k for k in self._key_counts if self._key_counts[k]])
            fair_share = self.global_limit / max(1, num_active_keys)

            remaining = int(fair_share - len(requests))
            reset_at = datetime.fromtimestamp(current_time + self.window_seconds)

            return RateLimitState(
                limit=int(fair_share),
                remaining=max(0, remaining),
                reset_at=reset_at,
                retry_after=0.0,
                violated=remaining <= 0,
                metadata={"algorithm": "fair_queuing"},
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._key_counts.clear()
            else:
                self._key_counts.pop(key, None)