import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from src.algorithms.fixed_window import FixedWindowAlgorithm

class TestFixedWindowAlgorithm:
    def test_initialization(self):
        alg = FixedWindowAlgorithm(limit=100, window_seconds=60)
        assert alg.limit == 100
        assert alg.window_seconds == 60

    def test_invalid_initialization(self):
        with pytest.raises(ValueError):
            FixedWindowAlgorithm(limit=0, window_seconds=60)
        with pytest.raises(ValueError):
            FixedWindowAlgorithm(limit=100, window_seconds=0)

    def test_first_request_allowed(self, test_key):
        alg = FixedWindowAlgorithm(limit=100, window_seconds=60)
        allowed, state = alg.allow(test_key)
        assert allowed is True
        assert state.remaining == 99
        assert state.violated is False

    def test_counting_requests(self, test_key):
        alg = FixedWindowAlgorithm(limit=10, window_seconds=60)
        for i in range(10):
            allowed, state = alg.allow(test_key)
            assert allowed is True
            assert state.remaining == 9 - i
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.violated is True

    def test_weighted_requests(self, test_key):
        alg = FixedWindowAlgorithm(limit=100, window_seconds=60)
        allowed, state = alg.allow(test_key, weight=50)
        assert allowed is True
        assert state.remaining == 50

    def test_window_reset(self, test_key):
        alg = FixedWindowAlgorithm(limit=5, window_seconds=0.5)
        for _ in range(5):
            alg.allow(test_key)
        allowed, _ = alg.allow(test_key)
        assert allowed is False
        time.sleep(0.6)
        allowed, state = alg.allow(test_key)
        assert allowed is True
        assert state.remaining == 4

    def test_window_start_calculation(self, test_key):
        alg = FixedWindowAlgorithm(limit=10, window_seconds=1.0)
        _, state = alg.allow(test_key)
        window_start = state.metadata["window_start"]
        time.sleep(0.1)
        _, state2 = alg.allow(test_key)
        assert state2.metadata["window_start"] == window_start

    def test_check_without_consuming(self, test_key):
        alg = FixedWindowAlgorithm(limit=100, window_seconds=60)
        state1 = alg.check(test_key)
        state2 = alg.check(test_key)
        assert state1.remaining == state2.remaining == 100

    def test_multiple_keys(self, multiple_keys):
        alg = FixedWindowAlgorithm(limit=5, window_seconds=60)
        for _ in range(5):
            alg.allow(multiple_keys[0])
        allowed, state = alg.allow(multiple_keys[1])
        assert allowed is True

    def test_reset_specific_key(self, test_key):
        alg = FixedWindowAlgorithm(limit=10, window_seconds=60)
        for _ in range(5):
            alg.allow(test_key)
        alg.reset(test_key)
        state = alg.check(test_key)
        assert state.remaining == 10

    def test_reset_all(self, multiple_keys):
        alg = FixedWindowAlgorithm(limit=10, window_seconds=60)
        for key in multiple_keys:
            for _ in range(5):
                alg.allow(key)
        alg.reset()
        for key in multiple_keys:
            state = alg.check(key)
            assert state.remaining == 10

    def test_retry_after(self, test_key):
        alg = FixedWindowAlgorithm(limit=5, window_seconds=1.0)
        for _ in range(5):
            alg.allow(test_key)
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert 0 < state.retry_after <= 1.0

    @pytest.mark.asyncio
    async def test_async_allow(self, test_key):
        alg = FixedWindowAlgorithm(limit=100, window_seconds=60)
        allowed, state = await alg.acquire_async(test_key)
        assert allowed is True
        assert state.remaining == 99

    def test_thread_safety(self, test_key):
        alg = FixedWindowAlgorithm(limit=100, window_seconds=60)
        def make_request():
            return alg.allow(test_key)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(100)))
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 100