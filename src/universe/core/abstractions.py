from abc import ABC, abstractmethod
from typing import Tuple, Optional, Awaitable
from .types import RateLimitState

class Algorithm(ABC):
    @abstractmethod
    def allow(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        pass

    @abstractmethod
    async def acquire_async(self, key: str, weight: int = 1) -> Tuple[bool, RateLimitState]:
        pass

    @abstractmethod
    def check(self, key: str) -> RateLimitState:
        pass

    @abstractmethod
    def reset(self, key: Optional[str] = None) -> None:
        pass


class Backend(ABC):
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


class RateLimiter(ABC):
    @abstractmethod
    def allow(self, key: str, weight: int = 1) -> bool:
        pass

    @abstractmethod
    async def acquire(self, key: str, weight: int = 1) -> bool:
        pass

    @abstractmethod
    def peek(self, key: str) -> RateLimitState:
        pass

    @abstractmethod
    def reset(self, key: Optional[str] = None) -> None:
        pass