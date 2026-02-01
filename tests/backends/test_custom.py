# File: tests/backends/test_custom.py
import pytest
from datetime import datetime, timedelta
from ratelink.backends.custom import CustomBackendInterface
from ratelink.core.types import RateLimitState

class MockCustomBackend(CustomBackendInterface):
    def __init__(self):
        self.store = {}

    def check(self, key: str) -> RateLimitState:
        if key not in self.store:
            return RateLimitState(
                limit=0,
                remaining=0,
                reset_at=datetime.now(),
                retry_after=0.0,
                violated=False,
                metadata={},
            )
        return self.store[key]

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")

        if key not in self.store:
            state = RateLimitState(
                limit=1000,
                remaining=1000 - weight,
                reset_at=datetime.now() + timedelta(seconds=3600),
                retry_after=0.0,
                violated=False,
                metadata={},
            )
            self.store[key] = state
            return state
        state = self.store[key]
        new_remaining = state.remaining - weight

        if new_remaining < 0:
            return RateLimitState(
                limit=state.limit,
                remaining=state.remaining,
                reset_at=state.reset_at,
                retry_after=(state.reset_at - datetime.now()).total_seconds(),
                violated=True,
                metadata=state.metadata,
            )
        new_state = RateLimitState(
            limit=state.limit,
            remaining=new_remaining,
            reset_at=state.reset_at,
            retry_after=0.0,
            violated=False,
            metadata=state.metadata,
        )
        self.store[key] = new_state
        return new_state

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: str = None) -> None:
        if key is None:
            self.store.clear()
        else:
            self.store.pop(key, None)

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: str = None) -> None:
        self.reset(key)


class TestCustomBackendInterface:
    def test_interface_implementation(self):
        backend = MockCustomBackend()
        assert isinstance(backend, CustomBackendInterface)

    def test_check_method(self):
        backend = MockCustomBackend()
        state = backend.check("test:key")
        assert state.limit == 0

    def test_consume_method(self):
        backend = MockCustomBackend()
        state = backend.consume("test:key", weight=10)
        assert state.remaining == 990

    def test_peek_method(self):
        backend = MockCustomBackend()
        backend.consume("test:key", weight=10)
        state1 = backend.peek("test:key")
        state2 = backend.peek("test:key")
        assert state1.remaining == state2.remaining

    def test_reset_method(self):
        backend = MockCustomBackend()
        backend.consume("test:key", weight=10)
        backend.reset("test:key")
        state = backend.check("test:key")
        assert state.limit == 0

    @pytest.mark.asyncio
    async def test_async_methods(self):
        backend = MockCustomBackend()
        state = await backend.consume_async("test:async", weight=5)
        assert state.remaining == 995