import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Dict, Optional, Tuple
from ..core.abstractions import Backend
from ..core.types import RateLimitState, BackendError

class MultiRegionBackend(Backend):
    def __init__(
        self,
        regions: Dict[str, Backend],
        global_coordinator: Backend,
        local_cache_ttl: int = 60,
        failover_mode: str = "local_cache",
        sync_interval: float = 1.0,
        max_cache_size: int = 10000,
    ) -> None:
        if not regions:
            raise ValueError("At least one region required")
        self.regions = regions
        self.global_coordinator = global_coordinator
        self.local_cache_ttl = local_cache_ttl
        self.failover_mode = failover_mode
        self.sync_interval = sync_interval
        self.max_cache_size = max_cache_size
        self._cache: Dict[str, Tuple[RateLimitState, float]] = {}
        self._cache_lock = RLock()
        self._last_sync: Dict[str, float] = {}

    def _get_region_backend(self, region: Optional[str]) -> Backend:
        if region is None:
            region = next(iter(self.regions.keys()))

        if region not in self.regions:
            raise ValueError(f"Unknown region: {region}")
        return self.regions[region]

    def _get_from_cache(self, key: str) -> Optional[RateLimitState]:
        with self._cache_lock:
            if key in self._cache:
                state, timestamp = self._cache[key]
                if time.time() - timestamp < self.local_cache_ttl:
                    return state
                else:
                    del self._cache[key]
        return None

    def _update_cache(self, key: str, state: RateLimitState) -> None:
        with self._cache_lock:
            if len(self._cache) >= self.max_cache_size:
                sorted_items = sorted(
                    self._cache.items(), key=lambda x: x[1][1]
                )
                to_remove = len(sorted_items) // 10
                for old_key, _ in sorted_items[:to_remove]:
                    del self._cache[old_key]
            self._cache[key] = (state, time.time())

    def _should_sync_global(self, key: str) -> bool:
        current_time = time.time()
        last_sync = self._last_sync.get(key, 0)
        return (current_time - last_sync) >= self.sync_interval

    def _sync_to_global(self, key: str, state: RateLimitState) -> None:
        try:
            self.global_coordinator.consume(key, weight=0)
            self._last_sync[key] = time.time()
        except Exception:
            pass

    def allow(
        self, key: str, weight: int = 1, region: Optional[str] = None) -> Tuple[bool, RateLimitState]:
        cached_state = self._get_from_cache(key)
        if cached_state is not None and cached_state.remaining >= weight:
            return (True, cached_state)
        try:
            regional_backend = self._get_region_backend(region)
            regional_state = regional_backend.consume(key, weight)
            self._update_cache(key, regional_state)
            if self._should_sync_global(key):
                self._sync_to_global(key, regional_state)
            return (not regional_state.violated, regional_state)
        except BackendError as e:
            return self._handle_failover(key, weight, e)

    def _handle_failover(
        self, key: str, weight: int, error: Exception) -> Tuple[bool, RateLimitState]:
        if self.failover_mode == "local_cache":
            cached_state = self._get_from_cache(key)
            if cached_state is not None:
                if cached_state.remaining >= weight:
                    return (True, cached_state)
            default_state = RateLimitState(
                limit=1000,
                remaining=1000 - weight,
                reset_at=datetime.now() + timedelta(seconds=60),
                retry_after=0.0,
                violated=False,
                metadata={"backend": "multi_region", "failover": True},
            )
            self._update_cache(key, default_state)
            return (True, default_state)

        elif self.failover_mode == "deny":
            error_state = RateLimitState(
                limit=0,
                remaining=0,
                reset_at=datetime.now(),
                retry_after=60.0,
                violated=True,
                metadata={"backend": "multi_region", "error": str(error)},
            )
            return (False, error_state)

        elif self.failover_mode == "allow":
            permissive_state = RateLimitState(
                limit=1000000,
                remaining=1000000,
                reset_at=datetime.now() + timedelta(seconds=3600),
                retry_after=0.0,
                violated=False,
                metadata={"backend": "multi_region", "failover": True},
            )
            return (True, permissive_state)
        else:
            raise ValueError(f"Unknown failover mode: {self.failover_mode}")

    def check(self, key: str, region: Optional[str] = None) -> RateLimitState:
        cached_state = self._get_from_cache(key)
        if cached_state is not None:
            return cached_state
        try:
            regional_backend = self._get_region_backend(region)
            state = regional_backend.check(key)
            self._update_cache(key, state)
            return state
        except BackendError:
            if cached_state is not None:
                return cached_state
            return RateLimitState(
                limit=0,
                remaining=0,
                reset_at=datetime.now(),
                retry_after=0.0,
                violated=False,
                metadata={"backend": "multi_region", "error": True},
            )

    def consume(self, key: str, weight: int) -> RateLimitState:
        allowed, state = self.allow(key, weight)
        return state

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None, region: Optional[str] = None) -> None:
        with self._cache_lock:
            if key is None:
                self._cache.clear()
                self._last_sync.clear()
            else:
                self._cache.pop(key, None)
                self._last_sync.pop(key, None)
        regions_to_reset = (
            [self.regions[region]] if region else self.regions.values()
        )
        for backend in regions_to_reset:
            try:
                backend.reset(key)
            except Exception:
                pass
        try:
            self.global_coordinator.reset(key)
        except Exception:
            pass

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)

    def get_stats(self) -> Dict[str, Any]:
        with self._cache_lock:
            return {
                "cache_size": len(self._cache),
                "max_cache_size": self.max_cache_size,
                "regions": list(self.regions.keys()),
                "cache_ttl": self.local_cache_ttl,
                "sync_interval": self.sync_interval,
                "failover_mode": self.failover_mode,
            }

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._last_sync.clear()