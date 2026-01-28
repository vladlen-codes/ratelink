import pytest
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ratelink.algorithms.sliding_window import SlidingWindowAlgorithm

class TestSlidingWindowAlgorithm:
    def test_initialization(self):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        assert alg.limit == 100
        assert alg.window_seconds == 60

    def test_invalid_initialization(self):
        with pytest.raises(ValueError):
            SlidingWindowAlgorithm(limit=0, window_seconds=60)
        with pytest.raises(ValueError):
            SlidingWindowAlgorithm(limit=100, window_seconds=0)

    def test_first_request_allowed(self, test_key):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        allowed, state = alg.allow(test_key)
        assert allowed is True
        assert state.remaining == 99
        assert state.violated is False

    def test_request_tracking(self, test_key):
        alg = SlidingWindowAlgorithm(limit=10, window_seconds=60)
        for i in range(10):
            allowed, state = alg.allow(test_key)
            assert allowed is True
            assert state.remaining == 9 - i
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.violated is True

    def test_weighted_requests(self, test_key):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        allowed, state = alg.allow(test_key, weight=50)
        assert allowed is True
        assert state.remaining == 50
        allowed, state = alg.allow(test_key, weight=50)
        assert allowed is True
        assert state.remaining == 0

    def test_old_requests_cleanup(self, test_key):
        alg = SlidingWindowAlgorithm(limit=10, window_seconds=0.5)
        for _ in range(10):
            alg.allow(test_key)
        allowed, _ = alg.allow(test_key)
        assert allowed is False
        time.sleep(0.6)
        allowed, state = alg.allow(test_key)
        assert allowed is True

    def test_sliding_nature(self, test_key):
        alg = SlidingWindowAlgorithm(limit=5, window_seconds=1.0)
        for _ in range(5):
            alg.allow(test_key)
        time.sleep(0.5)
        allowed, _ = alg.allow(test_key)
        assert allowed is False
        time.sleep(0.6)
        allowed, state = alg.allow(test_key)
        assert allowed is True

    def test_check_without_recording(self, test_key):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        state1 = alg.check(test_key)
        state2 = alg.check(test_key)
        assert state1.remaining == state2.remaining == 100

    def test_multiple_keys_independent(self, multiple_keys):
        alg = SlidingWindowAlgorithm(limit=5, window_seconds=60)
        for _ in range(5):
            alg.allow(multiple_keys[0])
        allowed, state = alg.allow(multiple_keys[1])
        assert allowed is True
        assert state.remaining == 4

    def test_reset_specific_key(self, test_key):
        alg = SlidingWindowAlgorithm(limit=10, window_seconds=60)
        for _ in range(5):
            alg.allow(test_key)
        alg.reset(test_key)
        state = alg.check(test_key)
        assert state.remaining == 10

    def test_reset_all(self, multiple_keys):
        alg = SlidingWindowAlgorithm(limit=10, window_seconds=60)
        for key in multiple_keys:
            for _ in range(5):
                alg.allow(key)
        alg.reset()
        for key in multiple_keys:
            state = alg.check(key)
            assert state.remaining == 10

    def test_retry_after_calculation(self, test_key):
        alg = SlidingWindowAlgorithm(limit=5, window_seconds=1.0)
        for _ in range(5):
            alg.allow(test_key)
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.retry_after > 0
        assert state.retry_after <= 1.0

    def test_metadata_includes_count(self, test_key):
        alg = SlidingWindowAlgorithm(limit=10, window_seconds=60)
        for i in range(5):
            allowed, state = alg.allow(test_key)
            assert state.metadata["current_count"] == i + 1

    @pytest.mark.asyncio
    async def test_async_allow(self, test_key):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        allowed, state = await alg.acquire_async(test_key)
        assert allowed is True
        assert state.remaining == 99

    def test_thread_safety(self, test_key):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        def make_request():
            return alg.allow(test_key)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(100)))
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 100

    def test_precise_window_tracking(self, test_key):
        alg = SlidingWindowAlgorithm(limit=3, window_seconds=0.3)
        for _ in range(3):
            alg.allow(test_key)
        allowed, _ = alg.allow(test_key)
        assert allowed is False
        time.sleep(0.35)
        allowed, _ = alg.allow(test_key)
        assert allowed is True

    def test_zero_weight_invalid(self, test_key):
        alg = SlidingWindowAlgorithm(limit=100, window_seconds=60)
        with pytest.raises(ValueError):
            alg.allow(test_key, weight=0)