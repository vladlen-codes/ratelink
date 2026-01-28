import pytest
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ratelink.algorithms.token_bucket import TokenBucketAlgorithm

class TestTokenBucketAlgorithm:
    def test_initialization(self):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10)
        assert alg.capacity == 100
        assert alg.refill_rate == 10
        assert alg.refill_period == 1.0

    def test_invalid_initialization(self):
        with pytest.raises(ValueError):
            TokenBucketAlgorithm(capacity=0, refill_rate=10)
        with pytest.raises(ValueError):
            TokenBucketAlgorithm(capacity=100, refill_rate=0)
        with pytest.raises(ValueError):
            TokenBucketAlgorithm(capacity=100, refill_rate=10, refill_period=-1)

    def test_first_request_allowed(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10)
        allowed, state = alg.allow(test_key)
        assert allowed is True
        assert state.violated is False
        assert state.remaining == 99
        assert state.limit == 100

    def test_consume_tokens(self, test_key):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=5)
        for i in range(10):
            allowed, state = alg.allow(test_key)
            assert allowed is True
            assert state.remaining == 9 - i
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.violated is True

    def test_weighted_consumption(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10)

        allowed, state = alg.allow(test_key, weight=50)
        assert allowed is True
        assert state.remaining == 50

        allowed, state = alg.allow(test_key, weight=50)
        assert allowed is True
        assert state.remaining == 0

        allowed, state = alg.allow(test_key, weight=1)
        assert allowed is False

    def test_token_refill(self, test_key):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=10, refill_period=0.1)
        for _ in range(10):
            alg.allow(test_key)
        time.sleep(0.15)
        allowed, state = alg.allow(test_key)
        assert allowed is True

    def test_refill_rate_calculation(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10, refill_period=1.0)
        alg.allow(test_key, weight=50)
        time.sleep(1.05)
        state = alg.check(test_key)
        assert state.remaining >= 59

    def test_max_capacity_refill(self, test_key):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=100, refill_period=0.1)
        alg.allow(test_key)
        time.sleep(0.3)
        state = alg.check(test_key)
        assert state.remaining <= 10

    def test_check_without_consumption(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10)
        state1 = alg.check(test_key)
        state2 = alg.check(test_key)
        assert state1.remaining == state2.remaining

    def test_multiple_keys(self, multiple_keys):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=5)
        for _ in range(10):
            alg.allow(multiple_keys[0])
        allowed, state = alg.allow(multiple_keys[1])
        assert allowed is True
        assert state.remaining == 9

    def test_reset_specific_key(self, test_key):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=5)
        alg.allow(test_key, weight=5)
        alg.reset(test_key)
        state = alg.check(test_key)
        assert state.remaining == 10

    def test_reset_all_keys(self, multiple_keys):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=5)
        for key in multiple_keys:
            alg.allow(key, weight=5)
        alg.reset()
        for key in multiple_keys:
            state = alg.check(key)
            assert state.remaining == 10

    def test_retry_after(self, test_key):
        alg = TokenBucketAlgorithm(capacity=10, refill_rate=10, refill_period=1.0)
        for _ in range(10):
            alg.allow(test_key)
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.retry_after > 0
        assert state.retry_after <= 0.1

    @pytest.mark.asyncio
    async def test_async_allow(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10)
        allowed, state = await alg.acquire_async(test_key)
        assert allowed is True
        assert state.remaining == 99

    def test_thread_safety(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=50)
        def make_request():
            return alg.allow(test_key)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(100)))
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 100

    def test_initial_tokens(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10, initial_tokens=50)
        state = alg.check(test_key)
        assert state.remaining == 50

    def test_zero_weight_invalid(self, test_key):
        alg = TokenBucketAlgorithm(capacity=100, refill_rate=10)
        with pytest.raises(ValueError):
            alg.allow(test_key, weight=0)