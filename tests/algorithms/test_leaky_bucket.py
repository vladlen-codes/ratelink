import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from src.universe.algorithms.leaky_bucket import LeakyBucketAlgorithm

class TestLeakyBucketAlgorithm:
    def test_initialization(self):
        alg = LeakyBucketAlgorithm(capacity=50, leak_rate=10)
        assert alg.capacity == 50
        assert alg.leak_rate == 10
        assert alg.leak_period == 1.0

    def test_invalid_initialization(self):
        with pytest.raises(ValueError):
            LeakyBucketAlgorithm(capacity=0, leak_rate=10)
        with pytest.raises(ValueError):
            LeakyBucketAlgorithm(capacity=50, leak_rate=0)

    def test_first_request_allowed(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=50, leak_rate=10)
        allowed, state = alg.allow(test_key)
        assert allowed is True
        assert state.remaining == 49

    def test_queue_filling(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=10, leak_rate=5)
        for i in range(10):
            allowed, state = alg.allow(test_key)
            assert allowed is True
            assert state.remaining == 9 - i
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.violated is True

    def test_weighted_requests(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=50, leak_rate=10)
        allowed, state = alg.allow(test_key, weight=25)
        assert allowed is True
        assert state.remaining == 25
        allowed, state = alg.allow(test_key, weight=25)
        assert allowed is True
        assert state.remaining == 0

    def test_leaking_over_time(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=10, leak_rate=10, leak_period=0.1)
        for _ in range(10):
            alg.allow(test_key)
        time.sleep(0.15)
        allowed, state = alg.allow(test_key)
        assert allowed is True

    def test_leak_rate_calculation(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=100, leak_rate=10, leak_period=1.0)
        for _ in range(50):
            alg.allow(test_key)
        time.sleep(1.05)
        state = alg.check(test_key)
        assert state.remaining >= 59

    def test_check_without_adding(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=50, leak_rate=10)
        state1 = alg.check(test_key)
        state2 = alg.check(test_key)
        assert state1.remaining == state2.remaining == 50

    def test_multiple_keys(self, multiple_keys):
        alg = LeakyBucketAlgorithm(capacity=10, leak_rate=5)
        for _ in range(10):
            alg.allow(multiple_keys[0])
        allowed, state = alg.allow(multiple_keys[1])
        assert allowed is True
        assert state.remaining == 9

    def test_reset_specific_key(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=10, leak_rate=5)
        for _ in range(5):
            alg.allow(test_key)
        alg.reset(test_key)
        state = alg.check(test_key)
        assert state.remaining == 10

    def test_reset_all(self, multiple_keys):
        alg = LeakyBucketAlgorithm(capacity=10, leak_rate=5)
        for key in multiple_keys:
            for _ in range(5):
                alg.allow(key)
        alg.reset()
        for key in multiple_keys:
            state = alg.check(key)
            assert state.remaining == 10

    def test_retry_after(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=10, leak_rate=10, leak_period=1.0)
        for _ in range(10):
            alg.allow(test_key)
        allowed, state = alg.allow(test_key, weight=2)
        assert allowed is False
        assert 0.15 <= state.retry_after <= 0.25

    @pytest.mark.asyncio
    async def test_async_allow(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=50, leak_rate=10)
        allowed, state = await alg.acquire_async(test_key)
        assert allowed is True
        assert state.remaining == 49

    def test_thread_safety(self, test_key):
        alg = LeakyBucketAlgorithm(capacity=100, leak_rate=50)
        def make_request():
            return alg.allow(test_key)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(100)))
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 100