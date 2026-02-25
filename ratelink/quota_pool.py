from typing import Dict, Optional, List, Any, Union
from threading import RLock
from datetime import datetime, timedelta
from .rate_limiter import RateLimiter
from .core.types import RateLimitState
from .core.types import ConfigError

class QuotaPool:
    def __init__(
        self,
        pool_id: str,
        total_quota: int,
        window: Union[int, str],
        backend: str = "memory",
        backend_options: Optional[Dict[str, Any]] = None,
        fair_share: bool = True,
        max_per_member: Optional[int] = None,
        rollover: bool = False,
        rollover_percent: float = 0.5,
    ) -> None:
        self.pool_id = pool_id
        self.total_quota = total_quota
        self.window = self._parse_window(window)
        self.fair_share = fair_share
        self.max_per_member = max_per_member
        self.rollover = rollover
        self.rollover_percent = max(0.0, min(1.0, rollover_percent))
        self._pool_limiter = RateLimiter(
            algorithm="token_bucket",
            backend=backend,
            backend_options=backend_options or {},
            limit=total_quota,
            window=self.window,
        )

        self._member_usage: Dict[str, int] = {}
        self._lock = RLock()

        self._last_window_start: Optional[datetime] = None
        self._rollover_quota = 0

    def _parse_window(self, window: Union[int, str]) -> int:
        if isinstance(window, int):
            return window

        conversions = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
            "week": 604800,
        }

        return conversions.get(window.lower(), 3600)

    def consume(
        self,
        member_id: str,
        weight: int = 1,
        force: bool = False
    ) -> bool:
        with self._lock:
            if self.fair_share and not force:
                if not self._check_fair_share(member_id, weight):
                    return False
            if self.max_per_member is not None and not force:
                current_usage = self._member_usage.get(member_id, 0)
                if current_usage + weight > self.max_per_member:
                    return False
            if self._pool_limiter.allow(self.pool_id, weight=weight):
                self._member_usage[member_id] = \
                    self._member_usage.get(member_id, 0) + weight
                return True

            return False

    def _check_fair_share(self, member_id: str, weight: int) -> bool:
        state = self._pool_limiter.check(self.pool_id)
        total_used = state.limit - state.remaining
        if total_used == 0:
            return True

        member_usage = self._member_usage.get(member_id, 0)
        num_members = len(self._member_usage) or 1

        fair_share = total_used / num_members

        tolerance = fair_share * 0.2
        return (member_usage + weight) <= (fair_share + tolerance)

    def check(self, member_id: Optional[str] = None) -> RateLimitState:
        with self._lock:
            state = self._pool_limiter.check(self.pool_id)
            if member_id:
                state.metadata["member_usage"] = self._member_usage.get(member_id, 0)
                state.metadata["member_id"] = member_id

            state.metadata["pool_id"] = self.pool_id
            state.metadata["total_quota"] = self.total_quota

            return state

    def reset(self) -> None:
        with self._lock:
            if self.rollover:
                self._handle_rollover()
            self._pool_limiter.reset(self.pool_id)
            self._member_usage.clear()
            self._last_window_start = datetime.now()

    def _handle_rollover(self) -> None:
        state = self._pool_limiter.check(self.pool_id)
        unused = state.remaining

        if unused > 0:
            rollover_amount = int(unused * self.rollover_percent)
            self._rollover_quota = rollover_amount

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            state = self._pool_limiter.check(self.pool_id)

            return {
                "pool_id": self.pool_id,
                "total": state.limit,
                "used": state.limit - state.remaining,
                "remaining": state.remaining,
                "members": len(self._member_usage),
                "member_usage": self._member_usage.copy(),
                "reset_at": state.reset_at,
                "fair_share": self.fair_share,
                "max_per_member": self.max_per_member,
                "rollover_enabled": self.rollover,
                "rollover_quota": self._rollover_quota,
            }

    def get_member_usage(self, member_id: str) -> int:
        with self._lock:
            return self._member_usage.get(member_id, 0)

    def list_members(self) -> List[str]:
        with self._lock:
            return list(self._member_usage.keys())

    def remove_member(self, member_id: str) -> None:
        with self._lock:
            self._member_usage.pop(member_id, None)


class SharedQuotaManager:
    def __init__(
        self,
        backend: str = "memory",
        backend_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.backend = backend
        self.backend_options = backend_options or {}
        self._pools: Dict[str, QuotaPool] = {}
        self._lock = RLock()

    def create_pool(
        self,
        pool_id: str,
        total_quota: int,
        window: Union[int, str],
        **kwargs: Any
    ) -> QuotaPool:
        with self._lock:
            if pool_id in self._pools:
                raise ConfigError(f"Pool already exists: {pool_id}")

            pool = QuotaPool(
                pool_id=pool_id,
                total_quota=total_quota,
                window=window,
                backend=self.backend,
                backend_options=self.backend_options,
                **kwargs
            )

            self._pools[pool_id] = pool
            return pool

    def get_pool(self, pool_id: str) -> QuotaPool:
        with self._lock:
            if pool_id not in self._pools:
                raise ConfigError(f"Pool not found: {pool_id}")
            return self._pools[pool_id]

    def consume(
        self,
        pool_id: str,
        member_id: str,
        weight: int = 1
    ) -> bool:
        pool = self.get_pool(pool_id)
        return pool.consume(member_id, weight=weight)

    def list_pools(self) -> List[str]:
        with self._lock:
            return list(self._pools.keys())

    def delete_pool(self, pool_id: str) -> None:
        with self._lock:
            self._pools.pop(pool_id, None)