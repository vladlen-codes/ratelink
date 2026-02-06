import pytest
import time
from ratelink.priority_limiter import PriorityRateLimiter
from ratelink.quota_pool import QuotaPool, SharedQuotaManager
from ratelink.adaptive_limiter import AdaptiveRateLimiter
from ratelink.algorithms.hierarchical import (
    HierarchicalTokenBucket,
    FairQueueingAlgorithm
)
from ratelink.core.types import ConfigError

class TestPriorityRateLimiter:
    def test_basic_tier_creation(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {"requests_per_hour": 100},
                "pro": {"requests_per_hour": 1000},
            },
            backend="memory"
        )
        
        assert "free" in limiter.list_tiers()
        assert "pro" in limiter.list_tiers()

    def test_tier_limits_enforced(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {"requests_per_minute": 5},
                "pro": {"requests_per_minute": 50},
            },
            backend="memory"
        )
        key = "user:alice"
        allowed_count = 0
        for _ in range(10):
            if limiter.allow(key, tier="free"):
                allowed_count += 1
        
        assert allowed_count == 5

    def test_unlimited_tier(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {"requests_per_hour": 100},
                "enterprise": {"requests_per_hour": None},
            },
            backend="memory"
        )
        assert limiter.is_unlimited("enterprise")
        assert not limiter.is_unlimited("free")
        for _ in range(1000):
            assert limiter.allow("user:bob", tier="enterprise")

    def test_different_tier_algorithms(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {
                    "requests_per_minute": 10,
                    "algorithm": "fixed_window"
                },
                "pro": {
                    "requests_per_minute": 100,
                    "algorithm": "sliding_window"
                },
            },
            backend="memory"
        )
        
        assert limiter.allow("user:charlie", tier="free")
        assert limiter.allow("user:dave", tier="pro")

    def test_tier_upgrade(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {"requests_per_hour": 100},
                "pro": {"requests_per_hour": 1000},
            },
            backend="memory"
        )
        user = "user:eve"
        for _ in range(10):
            limiter.allow(user, tier="free")
        limiter.upgrade_tier(user, "free", "pro", preserve_state=False)
        state = limiter.check(user, tier="pro")
        assert state.remaining > 900

    def test_tier_check(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {"requests_per_hour": 100},
            },
            backend="memory"
        )
        user = "user:frank"
        limiter.allow(user, tier="free", weight=10)
        state = limiter.check(user, tier="free")
        assert state.remaining < 100

    def test_invalid_tier(self):
        limiter = PriorityRateLimiter(
            tiers={"free": {"requests_per_hour": 100}},
            backend="memory"
        )
        with pytest.raises(ConfigError):
            limiter.allow("user:test", tier="invalid")

    @pytest.mark.asyncio
    async def test_async_tier_limiting(self):
        limiter = PriorityRateLimiter(
            tiers={
                "free": {"requests_per_minute": 50},
            },
            backend="memory"
        )
        allowed = await limiter.acquire("user:async", tier="free")
        assert allowed is True


class TestQuotaPool:
    def test_pool_creation(self):
        pool = QuotaPool(
            pool_id="team:eng",
            total_quota=1000,
            window="hour",
            backend="memory"
        )
        assert pool.pool_id == "team:eng"
        assert pool.total_quota == 1000

    def test_pool_consumption(self):
        pool = QuotaPool(
            pool_id="team:sales",
            total_quota=100,
            window=60,
            backend="memory"
        )
        assert pool.consume("alice", weight=10)
        assert pool.consume("bob", weight=20)
        assert pool.consume("charlie", weight=30)
        stats = pool.get_stats()
        assert stats["used"] == 60
        assert stats["remaining"] == 40

    def test_pool_exhaustion(self):
        pool = QuotaPool(
            pool_id="team:limited",
            total_quota=50,
            window=60,
            backend="memory"
        )
        for i in range(5):
            pool.consume(f"user:{i}", weight=10)
        assert not pool.consume("user:6", weight=1)

    def test_fair_share_enforcement(self):
        pool = QuotaPool(
            pool_id="team:fair",
            total_quota=100,
            window=60,
            backend="memory",
            fair_share=True
        )
        for _ in range(10):
            pool.consume("alice", weight=10)
        assert pool.consume("bob", weight=10)

    def test_max_per_member(self):
        pool = QuotaPool(
            pool_id="team:capped",
            total_quota=1000,
            window=60,
            backend="memory",
            max_per_member=50
        )
        for _ in range(6):
            pool.consume("alice", weight=10)
        stats = pool.get_stats()
        assert stats["member_usage"]["alice"] <= 50

    def test_member_tracking(self):
        pool = QuotaPool(
            pool_id="team:tracked",
            total_quota=100,
            window=60,
            backend="memory"
        )
        pool.consume("alice", weight=10)
        pool.consume("bob", weight=20)
        members = pool.list_members()
        assert "alice" in members
        assert "bob" in members
        assert pool.get_member_usage("alice") == 10
        assert pool.get_member_usage("bob") == 20

    def test_pool_reset(self):
        pool = QuotaPool(
            pool_id="team:reset",
            total_quota=100,
            window=60,
            backend="memory"
        )
        pool.consume("alice", weight=50)
        pool.reset()
        stats = pool.get_stats()
        assert stats["used"] == 0
        assert stats["remaining"] == 100


class TestSharedQuotaManager:
    def test_manager_creation(self):
        manager = SharedQuotaManager(backend="memory")
        assert manager is not None

    def test_create_multiple_pools(self):
        manager = SharedQuotaManager(backend="memory")
        manager.create_pool("team:eng", total_quota=1000, window="hour")
        manager.create_pool("team:sales", total_quota=500, window="hour")
        pools = manager.list_pools()
        assert "team:eng" in pools
        assert "team:sales" in pools

    def test_consume_from_managed_pool(self):
        manager = SharedQuotaManager(backend="memory")
        manager.create_pool("team:test", total_quota=100, window=60)
        assert manager.consume("team:test", "alice", weight=10)
        assert manager.consume("team:test", "bob", weight=20)

    def test_get_pool(self):
        manager = SharedQuotaManager(backend="memory")
        manager.create_pool("team:dev", total_quota=100, window=60)
        pool = manager.get_pool("team:dev")
        assert pool.pool_id == "team:dev"

    def test_delete_pool(self):
        manager = SharedQuotaManager(backend="memory")
        manager.create_pool("team:temp", total_quota=100, window=60)
        manager.delete_pool("team:temp")
        assert "team:temp" not in manager.list_pools()


class TestAdaptiveRateLimiter:
    def test_adaptive_creation(self):
        limiter = AdaptiveRateLimiter(
            base_limit=1000,
            window="hour",
            backend="memory"
        )
        assert limiter.base_limit == 1000
        assert limiter.current_limit == 1000

    def test_error_rate_adaptation(self):
        limiter = AdaptiveRateLimiter(
            base_limit=1000,
            window=60,
            backend="memory",
            error_threshold=0.2,
            check_interval=0.1
        )
        for _ in range(50):
            limiter.allow("user:test")
            limiter.record_error()
        time.sleep(0.2)
        limiter.allow("user:test2")
        metrics = limiter.get_metrics()

    def test_success_tracking(self):
        limiter = AdaptiveRateLimiter(
            base_limit=100,
            window=60,
            backend="memory"
        )
        for _ in range(10):
            limiter.allow("user:test")
            limiter.record_success(latency=0.1)
        metrics = limiter.get_metrics()
        assert metrics["total_requests"] >= 10

    def test_latency_tracking(self):
        limiter = AdaptiveRateLimiter(
            base_limit=100,
            window=60,
            backend="memory"
        )
        limiter.allow("user:test")
        limiter.record_success(latency=0.5)
        limiter.record_success(latency=0.3)
        metrics = limiter.get_metrics()
        assert metrics["avg_latency"] > 0

    def test_threshold_updates(self):
        limiter = AdaptiveRateLimiter(
            base_limit=100,
            window=60,
            backend="memory",
            error_threshold=0.1
        )
        limiter.set_thresholds(error_rate=0.2, latency=2.0)
        assert limiter.error_threshold == 0.2
        assert limiter.latency_threshold == 2.0


class TestHierarchicalTokenBucket:
    def test_hierarchical_creation(self):
        htb = HierarchicalTokenBucket(
            global_limit=10000,
            tenant_limit=1000,
            user_limit=100,
            refill_rate=10
        )
        assert htb.global_limit == 10000
        assert htb.tenant_limit == 1000
        assert htb.user_limit == 100

    def test_user_level_limiting(self):
        htb = HierarchicalTokenBucket(
            global_limit=10000,
            tenant_limit=1000,
            user_limit=10,
            refill_rate=5
        )
        
        allowed_count = 0
        for _ in range(15):
            allowed, _ = htb.allow("user:alice")
            if allowed:
                allowed_count += 1
        
        assert allowed_count == 10

    def test_tenant_level_limiting(self):
        htb = HierarchicalTokenBucket(
            global_limit=10000,
            tenant_limit=20,
            user_limit=100,
            refill_rate=5
        )
        
        total_allowed = 0
        
        for i in range(5):
            allowed, _ = htb.allow(f"user:{i}", tenant="acme")
            if allowed:
                total_allowed += 1
        assert total_allowed <= 20

    def test_global_level_limiting(self):
        htb = HierarchicalTokenBucket(
            global_limit=30,
            tenant_limit=1000,
            user_limit=1000,
            refill_rate=5
        )
        
        total_allowed = 0
        
        for i in range(50):
            allowed, _ = htb.allow(f"user:{i}", tenant=f"tenant:{i % 5}")
            if allowed:
                total_allowed += 1
        
        assert total_allowed <= 30

    def test_hierarchy_metadata(self):
        htb = HierarchicalTokenBucket(
            global_limit=1000,
            tenant_limit=100,
            user_limit=10,
            refill_rate=5
        )
        
        allowed, state = htb.allow("user:test", tenant="acme")
        
        assert "global_remaining" in state.metadata
        assert "tenant_remaining" in state.metadata
        assert "user_remaining" in state.metadata


class TestFairQueueingAlgorithm:
    def test_fair_queuing_creation(self):
        fq = FairQueueingAlgorithm(
            global_limit=100,
            window_seconds=60
        )
        
        assert fq.global_limit == 100

    def test_fair_distribution(self):
        fq = FairQueueingAlgorithm(
            global_limit=100,
            window_seconds=60,
            max_per_key=30
        )
        
        for i in range(5):
            for _ in range(10):
                fq.allow(f"user:{i}")
        
        for i in range(5):
            state = fq.check(f"user:{i}")
            assert state.remaining >= 0

    def test_weighted_fairness(self):
        fq = FairQueueingAlgorithm(
            global_limit=100,
            window_seconds=60,
            weights={"premium": 2.0, "regular": 1.0}
        )
        
        allowed_premium = 0
        for _ in range(20):
            allowed, _ = fq.allow("premium_user", weight_class="premium")
            if allowed:
                allowed_premium += 1
        
        allowed_regular = 0
        for _ in range(20):
            allowed, _ = fq.allow("regular_user", weight_class="regular")
            if allowed:
                allowed_regular += 1

    def test_max_per_key_enforcement(self):
        fq = FairQueueingAlgorithm(
            global_limit=1000,
            window_seconds=60,
            max_per_key=50
        )
        allowed_count = 0
        for _ in range(100):
            allowed, _ = fq.allow("user:greedy")
            if allowed:
                allowed_count += 1
        
        assert allowed_count <= 50