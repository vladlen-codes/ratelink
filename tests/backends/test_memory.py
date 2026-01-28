import pytest
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from ratelink.backends.memory import MemoryBackend

class TestMemoryBackend:
    def test_initialization(self):
        backend = MemoryBackend(ttl_seconds=300)
        assert backend.ttl_seconds == 300

    def test_invalid_initialization(self):
        with pytest.raises(ValueError):
            MemoryBackend(ttl_seconds=0)
        with pytest.raises(ValueError):
            MemoryBackend(cleanup_interval=0)

    def test_check_nonexistent_key(self, test_key):
        backend = MemoryBackend()
        state = backend.check(test_key)
        assert state.limit == 0
        assert state.remaining == 0

    def test_set_and_check(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=99, reset_at=reset_at, retry_after=0.0
        )
        state = backend.check(test_key)
        assert state.limit == 100
        assert state.remaining == 99

    def test_consume(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=100, reset_at=reset_at
        )
        state = backend.consume(test_key, weight=25)
        assert state.remaining == 75
        state = backend.consume(test_key, weight=25)
        assert state.remaining == 50

    def test_peek_doesnt_modify(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=50, reset_at=reset_at
        )
        state1 = backend.peek(test_key)
        state2 = backend.peek(test_key)
        assert state1.remaining == state2.remaining == 50

    def test_reset_specific_key(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=50, reset_at=reset_at
        )
        backend.reset(test_key)

        state = backend.check(test_key)
        assert state.limit == 0

    def test_reset_all(self, multiple_keys):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        for key in multiple_keys:
            backend.set_state(
                key, limit=100, remaining=50, reset_at=reset_at
            )
        backend.reset()
        for key in multiple_keys:
            state = backend.check(key)
            assert state.limit == 0

    def test_ttl_expiration(self, test_key):
        backend = MemoryBackend(ttl_seconds=0.5, cleanup_interval=0.1)
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=50, reset_at=reset_at
        )
        state = backend.check(test_key)
        assert state.remaining == 50
        time.sleep(0.6)
        state = backend.check(test_key)
        assert state.limit == 0

    def test_automatic_cleanup(self, multiple_keys):
        backend = MemoryBackend(ttl_seconds=0.3, cleanup_interval=0.2)
        reset_at = datetime.now() + timedelta(seconds=60)
        for key in multiple_keys:
            backend.set_state(
                key, limit=100, remaining=50, reset_at=reset_at
            )
        time.sleep(0.4)
        backend.check("trigger_cleanup")
        stats = backend.get_stats()
        assert stats["keys_count"] <= 1

    def test_metadata_storage(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        metadata = {"algorithm": "token_bucket", "rate": 10}
        backend.set_state(
            test_key,
            limit=100,
            remaining=50,
            reset_at=reset_at,
            metadata=metadata,
        )
        state = backend.check(test_key)
        assert state.metadata["algorithm"] == "token_bucket"
        assert state.metadata["rate"] == 10

    def test_get_stats(self):
        backend = MemoryBackend(ttl_seconds=300)
        stats = backend.get_stats()
        assert "keys_count" in stats
        assert "ttl_seconds" in stats
        assert stats["ttl_seconds"] == 300

    @pytest.mark.asyncio
    async def test_async_check(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=50, reset_at=reset_at
        )
        state = await backend.check_async(test_key)
        assert state.remaining == 50

    @pytest.mark.asyncio
    async def test_async_consume(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=100, reset_at=reset_at
        )
        state = await backend.consume_async(test_key, weight=25)
        assert state.remaining == 75

    @pytest.mark.asyncio
    async def test_async_reset(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)

        backend.set_state(
            test_key, limit=100, remaining=50, reset_at=reset_at
        )
        await backend.reset_async(test_key)

        state = backend.check(test_key)
        assert state.limit == 0

    def test_thread_safety(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=1000, remaining=1000, reset_at=reset_at
        )
        def consume():
            backend.consume(test_key, weight=1)
        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(lambda _: consume(), range(100)))
        state = backend.check(test_key)
        assert state.remaining == 900

    def test_invalid_weight(self, test_key):
        backend = MemoryBackend()
        reset_at = datetime.now() + timedelta(seconds=60)
        backend.set_state(
            test_key, limit=100, remaining=100, reset_at=reset_at
        )
        with pytest.raises(ValueError):
            backend.consume(test_key, weight=0)