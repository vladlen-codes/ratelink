import pytest
import time
from datetime import datetime, timedelta
from ratelink.backends.multi_region import MultiRegionBackend
from ratelink.backends.memory import MemoryBackend


class TestMultiRegionBackend:
    @pytest.fixture
    def setup_backends(self):
        regions = {
            "us-east": MemoryBackend(),
            "eu-west": MemoryBackend(),
            "ap-south": MemoryBackend(),
        }
        global_coordinator = MemoryBackend()
        backend = MultiRegionBackend(
            regions=regions,
            global_coordinator=global_coordinator,
            local_cache_ttl=60,
            failover_mode="local_cache",
        )
        return backend

    def test_initialization(self, setup_backends):
        backend = setup_backends
        assert backend is not None
        assert len(backend.regions) == 3
        assert backend.global_coordinator is not None

    def test_region_routing(self, setup_backends):
        backend = setup_backends
        allowed1, state1 = backend.allow("test:key", region="us-east")
        assert allowed1 is True
        allowed2, state2 = backend.allow("test:key", region="eu-west")
        assert allowed2 is True

    def test_local_cache_hit(self, setup_backends):
        backend = setup_backends
        key = "test:cache"
        start1 = time.time()
        backend.allow(key, region="us-east")
        time1 = time.time() - start1
        start2 = time.time()
        backend.allow(key, region="us-east")
        time2 = time.time() - start2
        assert time2 <= time1 * 2

    def test_failover_mechanism(self):
        from ratelink.core.types import BackendError

        class FailingBackend(MemoryBackend):
            def consume(self, key, weight):
                raise BackendError("Simulated failure")
        backend = MultiRegionBackend(
            regions={"us": FailingBackend()},
            global_coordinator=MemoryBackend(),
            failover_mode="local_cache",
        )
        allowed, state = backend.allow("test:failover", region="us")
        assert allowed is True
        assert state.metadata.get("failover") is True

    def test_failover_deny_mode(self):
        from ratelink.core.types import BackendError

        class FailingBackend(MemoryBackend):
            def consume(self, key, weight):
                raise BackendError("Simulated failure")
        backend = MultiRegionBackend(
            regions={"us": FailingBackend()},
            global_coordinator=MemoryBackend(),
            failover_mode="deny",
        )
        allowed, state = backend.allow("test:deny", region="us")
        assert allowed is False
        assert state.violated is True

    def test_failover_allow_mode(self):
        from ratelink.core.types import BackendError
        
        class FailingBackend(MemoryBackend):
            def consume(self, key, weight):
                raise BackendError("Simulated failure")
        backend = MultiRegionBackend(
            regions={"us": FailingBackend()},
            global_coordinator=MemoryBackend(),
            failover_mode="allow",
        )
        allowed, state = backend.allow("test:allow", region="us")
        assert allowed is True

    def test_cache_consistency(self, setup_backends):
        backend = setup_backends
        key = "test:consistency"
        for i in range(10):
            backend.allow(key, region="us-east")
        cached = backend._get_from_cache(key)
        assert cached is not None

    def test_multiple_regions_independent(self, setup_backends):
        backend = setup_backends
        key = "test:independent"
        backend.allow(key, region="us-east", weight=100)
        backend.allow(key, region="eu-west", weight=50)
        us_state = backend.check(key, region="us-east")
        eu_state = backend.check(key, region="eu-west")
        assert us_state is not None
        assert eu_state is not None

    def test_get_stats(self, setup_backends):
        backend = setup_backends
        stats = backend.get_stats()
        assert "cache_size" in stats
        assert "regions" in stats
        assert len(stats["regions"]) == 3

    def test_clear_cache(self, setup_backends):
        backend = setup_backends
        backend.allow("test:clear1")
        backend.allow("test:clear2")
        backend.clear_cache()
        stats = backend.get_stats()
        assert stats["cache_size"] == 0

    @pytest.mark.asyncio
    async def test_async_operations(self, setup_backends):
        backend = setup_backends
        state = await backend.consume_async("test:async", weight=1)
        assert state is not None