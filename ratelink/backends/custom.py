from abc import ABC, abstractmethod
from typing import Optional
from ..core.types import RateLimitState

class CustomBackendInterface(ABC):
    @abstractmethod
    def check(self, key: str) -> RateLimitState:
        pass

    @abstractmethod
    def consume(self, key: str, weight: int) -> RateLimitState:
        pass

    @abstractmethod
    def peek(self, key: str) -> RateLimitState:
        pass

    @abstractmethod
    def reset(self, key: Optional[str] = None) -> None:
        pass

    @abstractmethod
    async def check_async(self, key: str) -> RateLimitState:
        pass

    @abstractmethod
    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        pass

    @abstractmethod
    async def peek_async(self, key: str) -> RateLimitState:
        pass

    @abstractmethod
    async def reset_async(self, key: Optional[str] = None) -> None:
        pass

class MemcachedBackend(CustomBackendInterface):
    def __init__(self, servers=None):
        if servers is None:
            servers = ['127.0.0.1:11211']

        try:
            import memcache
            self.client = memcache.Client(servers)
        except ImportError:
            raise ImportError(
                "python-memcached not installed. "
                "Install with: pip install python-memcached"
            )

    def check(self, key: str) -> RateLimitState:
        from datetime import datetime
        value = self.client.get(f"ratelimit:{key}")
        if value is None:
            return RateLimitState(
                limit=0,
                remaining=0,
                reset_at=datetime.now(),
                retry_after=0.0,
                violated=False,
                metadata={"backend": "memcached"},
            )
        parts = value.split(":")
        limit_value = int(parts[0])
        remaining = int(parts[1])
        reset_timestamp = float(parts[2])
        reset_at = datetime.fromtimestamp(reset_timestamp)
        retry_after = max(0.0, reset_timestamp - datetime.now().timestamp())
        return RateLimitState(
            limit=limit_value,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after if remaining <= 0 else 0.0,
            violated=remaining <= 0,
            metadata={"backend": "memcached"},
        )

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")
        
        from datetime import datetime, timedelta

        memkey = f"ratelimit:{key}"

        remaining = self.client.decr(memkey, weight)

        if remaining is None:
            limit_value = 10000
            remaining = limit_value - weight
            reset_at = datetime.now() + timedelta(seconds=3600)
            value = f"{limit_value}:{remaining}:{reset_at.timestamp()}"
            self.client.set(memkey, value, time=3600)
            return RateLimitState(
                limit=limit_value,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=0.0,
                violated=False,
                metadata={"backend": "memcached"},
            )
        return self.check(key)

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self.client.flush_all()
        else:
            self.client.delete(f"ratelimit:{key}")

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)