import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from ratelink.src.algorithms.gcra import GCRAAlgorithm


class TestGCRAAlgorithm:
    def test_initialization(self):
        alg = GCRAAlgorithm(limit=100, period_seconds=60)
        assert alg.limit == 100
        assert alg.period_seconds == 60
        assert alg.burst == 100

    def test_custom_burst(self):
        alg = GCRAAlgorithm(limit=100, period_seconds=60, burst=50)
        assert alg.burst == 50

    def test_invalid_initialization(self):
        with pytest.raises(ValueError):
            GCRAAlgorithm(limit=0, period_seconds=60)
        with pytest.raises(ValueError):
            GCRAAlgorithm(limit=100, period_seconds=0)

    def test_first_request_allowed(self, test_key):
        alg = GCRAAlgorithm(limit=100, period_seconds=60)
        allowed, state = alg.allow(test_key)
        assert allowed is True
        assert state.violated is False

    def test_emission_interval(self):
        alg = GCRAAlgorithm(limit=100, period_seconds=60)
        assert alg.emission_interval == 0.6

    def test_rate_limiting(self, test_key):
        alg = GCRAAlgorithm(limit=10, period_seconds=1.0, burst=5)
        for i in range(5):
            allowed, state = alg.allow(test_key)
            assert allowed is True
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert state.retry_after > 0

    def test_weighted_requests(self, test_key):
        alg = GCRAAlgorithm(limit=100, period_seconds=60, burst=50)
        allowed, state = alg.allow(test_key, weight=25)
        assert allowed is True
        allowed, state = alg.allow(test_key, weight=25)
        assert allowed is True

    def test_tat_tracking(self, test_key):
        alg = GCRAAlgorithm(limit=10, period_seconds=1.0)
        _, state = alg.allow(test_key)
        tat1 = state.metadata["tat"]
        _, state = alg.allow(test_key)
        tat2 = state.metadata["tat"]
        assert tat2 > tat1

    def test_burst_allowance(self, test_key):
        alg = GCRAAlgorithm(limit=100, period_seconds=10, burst=10)
        for i in range(10):
            allowed, _ = alg.allow(test_key)
            assert allowed is True

    def test_check_without_consuming(self, test_key):
        alg = GCRAAlgorithm(limit=100, period_seconds=60)
        alg.allow(test_key)
        state1 = alg.check(test_key)
        state2 = alg.check(test_key)
        assert state1.metadata["tat"] == state2.metadata["tat"]

    def test_multiple_keys(self, multiple_keys):
        alg = GCRAAlgorithm(limit=10, period_seconds=1.0, burst=3)
        for _ in range(3):
            alg.allow(multiple_keys[0])
        allowed, state = alg.allow(multiple_keys[1])
        assert allowed is True

    def test_reset_specific_key(self, test_key):
        alg = GCRAAlgorithm(limit=10, period_seconds=1.0)
        for _ in range(5):
            alg.allow(test_key)
        alg.reset(test_key)
        state = alg.check(test_key)
        assert state.remaining > 0

    def test_reset_all(self, multiple_keys):
        alg = GCRAAlgorithm(limit=10, period_seconds=1.0)
        for key in multiple_keys:
            alg.allow(key)
        alg.reset()
        for key in multiple_keys:
            state = alg.check(key)
            assert state.remaining > 0

    def test_retry_after_accuracy(self, test_key):
        alg = GCRAAlgorithm(limit=10, period_seconds=1.0, burst=2)
        for _ in range(2):
            alg.allow(test_key)
        allowed, state = alg.allow(test_key)
        assert allowed is False
        assert 0.05 <= state.retry_after <= 0.15

    @pytest.mark.asyncio
    async def test_async_allow(self, test_key):
        alg = GCRAAlgorithm(limit=100, period_seconds=60)
        allowed, state = await alg.acquire_async(test_key)
        assert allowed is True

    def test_thread_safety(self, test_key):
        alg = GCRAAlgorithm(limit=100, period_seconds=10, burst=100)
        def make_request():
            return alg.allow(test_key)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(100)))
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 100