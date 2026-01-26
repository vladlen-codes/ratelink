import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, Optional, Any
from ..core.abstractions import Backend
from ..core.types import RateLimitState


class MemoryBackend(Backend):
    def __init__(self, ttl_seconds: Optional[float] = None, cleanup_interval: float = 60.0) -> None:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if cleanup_interval <= 0:
            raise ValueError("cleanup_interval must be positive")
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval = cleanup_interval
        self._store: Dict[str, Dict[str, Any]] = {}
        self._last_cleanup = time.time()
        self._lock = RLock()

    def _cleanup_expired(self) -> None:
        if self.ttl_seconds is None:
            return
        current_time = time.time()
        if current_time - self._last_cleanup < self.cleanup_interval:
            return
        expired_keys = []
        for key, data in self._store.items():
            if current_time - data["timestamp"] > self.ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            del self._store[key]
        self._last_cleanup = current_time

    def _get_data(self, key: str) -> Optional[Dict[str, Any]]:
        if key not in self._store:
            return None
        data = self._store[key]
        if self.ttl_seconds is not None:
            current_time = time.time()
            if current_time - data["timestamp"] > self.ttl_seconds:
                del self._store[key]
                return None
        return data

    def check(self, key: str) -> RateLimitState:
        with self._lock:
            self._cleanup_expired()
            data = self._get_data(key)
            if data is None:
                current_time = time.time()
                return RateLimitState(
                    limit=0,
                    remaining=0,
                    reset_at=datetime.fromtimestamp(current_time),
                    retry_after=0.0,
                    violated=False,
                    metadata={},
                )
            return RateLimitState(
                limit=data["limit"],
                remaining=data["remaining"],
                reset_at=data["reset_at"],
                retry_after=data["retry_after"],
                violated=data["violated"],
                metadata=data.get("metadata", {}),
            )

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")
        current_time = time.time()
        with self._lock:
            self._cleanup_expired()
            data = self._get_data(key)
            if data is None:
                data = {
                    "limit": weight,
                    "remaining": 0,
                    "reset_at": datetime.fromtimestamp(current_time + 60),
                    "retry_after": 0.0,
                    "violated": False,
                    "timestamp": current_time,
                    "metadata": {},
                }
            else:
                data["remaining"] = max(0, data["remaining"] - weight)
                data["timestamp"] = current_time
            self._store[key] = data
            return RateLimitState(
                limit=data["limit"],
                remaining=data["remaining"],
                reset_at=data["reset_at"],
                retry_after=data["retry_after"],
                violated=data["violated"],
                metadata=data.get("metadata", {}),
            )

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            elif key in self._store:
                del self._store[key]

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)

    def set_state(
        self,
        key: str,
        limit: int,
        remaining: int,
        reset_at: datetime,
        retry_after: float = 0.0,
        violated: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._store[key] = {
                "limit": limit,
                "remaining": remaining,
                "reset_at": reset_at,
                "retry_after": retry_after,
                "violated": violated,
                "timestamp": time.time(),
                "metadata": metadata or {},
            }

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            self._cleanup_expired()
            return {
                "keys_count": len(self._store),
                "ttl_seconds": self.ttl_seconds,
                "cleanup_interval": self.cleanup_interval,
            }