# File: tests/test_rate_limiter.py
import pytest
import time
from ratelink.rate_limiter import RateLimiter
from ratelink.core.types import LimitExceeded, ConfigError


class TestRateLimiterBasic:
    def test_simple_creation(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        assert limiter.limit == 100
        assert limiter.window == 60

    def test_string_window(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window="minute"
        )
        
        assert limiter.window == 60

    def test_invalid_window(self):
        with pytest.raises(ConfigError):
            RateLimiter(
                algorithm="token_bucket",
                backend="memory",
                limit=100,
                window="invalid"
            )

    def test_allow_request(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=10,
            window=60
        )
        for i in range(10):
            assert limiter.allow(f"key:{i}") is True

    def test_deny_request(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=5,
            window=60
        )
        key = "test:deny"
        for _ in range(5):
            assert limiter.allow(key) is True
        assert limiter.allow(key) is False

    def test_raise_on_limit(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=3,
            window=60,
            raise_on_limit=True
        )
        key = "test:raise"
        for _ in range(3):
            limiter.allow(key)
        with pytest.raises(LimitExceeded) as exc_info:
            limiter.allow(key)
        assert exc_info.value.retry_after is not None

    def test_check_method(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        key = "test:check"
        limiter.allow(key, weight=10)
        state = limiter.check(key)
        assert state.remaining < 100

    def test_peek_method(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        key = "test:peek"
        limiter.allow(key, weight=5)
        state1 = limiter.peek(key)
        state2 = limiter.peek(key)
        assert state1.remaining == state2.remaining

    def test_reset_method(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=10,
            window=60
        )
        key = "test:reset"
        for _ in range(5):
            limiter.allow(key)
        limiter.reset(key)        
        state = limiter.check(key)
        assert state.remaining == 10 or state.limit == 0

    @pytest.mark.asyncio
    async def test_async_acquire(self):
        limiter = RateLimiter(
            algorithm="sliding_window",
            backend="memory",
            limit=50,
            window=60
        )
        allowed = await limiter.acquire("test:async")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_async_check(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        key = "test:async_check"
        await limiter.acquire(key, weight=10)
        state = await limiter.async_check(key)
        assert state.remaining < 100

    @pytest.mark.asyncio
    async def test_async_reset(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        key = "test:async_reset"
        await limiter.acquire(key, weight=50)
        await limiter.async_reset(key)

class TestRateLimiterAlgorithms:
    def test_token_bucket_algorithm(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=10
        )
        assert limiter.allow("key:tb") is True

    def test_sliding_window_algorithm(self):
        limiter = RateLimiter(
            algorithm="sliding_window",
            backend="memory",
            limit=50,
            window=60
        )
        assert limiter.allow("key:sw") is True

    def test_leaky_bucket_algorithm(self):
        limiter = RateLimiter(
            algorithm="leaky_bucket",
            backend="memory",
            limit=30,
            window=10
        )
        assert limiter.allow("key:lb") is True

    def test_fixed_window_algorithm(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=20,
            window=60
        )
        assert limiter.allow("key:fw") is True

    def test_gcra_algorithm(self):
        limiter = RateLimiter(
            algorithm="gcra",
            backend="memory",
            limit=100,
            window=60
        )
        assert limiter.allow("key:gcra") is True

    def test_invalid_algorithm(self):
        with pytest.raises(ConfigError):
            RateLimiter(
                algorithm="invalid_algo",
                backend="memory",
                limit=100,
                window=60
            )

class TestRateLimiterBackends:
    def test_memory_backend(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        assert limiter.allow("key:mem") is True

    def test_invalid_backend(self):
        with pytest.raises(ConfigError):
            RateLimiter(
                algorithm="token_bucket",
                backend="invalid_backend",
                limit=100,
                window=60
            )

class TestRateLimiterHooks:
    def test_register_hook(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=10,
            window=60
        )
        called = []
        def on_allow_hook(key, weight, state):
            called.append("allowed")
        limiter.register_hook("on_allow", on_allow_hook)
        limiter.allow("test:hook")
        assert "allowed" in called

    def test_on_deny_hook(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=2,
            window=60
        )
        denied = []
        def on_deny_hook(key, weight, state):
            denied.append(key)
        limiter.register_hook("on_deny", on_deny_hook)
        key = "test:deny_hook"
        limiter.allow(key)
        limiter.allow(key)
        limiter.allow(key)
        assert key in denied

    def test_before_check_hook(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        checks = []
        def before_check(key, weight):
            checks.append((key, weight))
        limiter.register_hook("before_check", before_check)
        limiter.allow("test:before", weight=5)
        assert ("test:before", 5) in checks

    def test_invalid_hook_event(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        with pytest.raises(ValueError):
            limiter.register_hook("invalid_event", lambda: None)


class TestRateLimiterConfiguration:
    def test_get_config(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window="hour"
        )
        config = limiter.get_config()
        assert config["algorithm"] == "token_bucket"
        assert config["backend"] == "memory"
        assert config["limit"] == 100

    def test_reconfigure_limit(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        
        limiter.reconfigure(limit=200)
        assert limiter.limit == 200

    def test_reconfigure_window(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        limiter.reconfigure(window=120)
        assert limiter.window == 120

    def test_reconfigure_raise_on_limit(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=10,
            window=60,
            raise_on_limit=False
        )
        limiter.reconfigure(raise_on_limit=True)
        assert limiter.raise_on_limit is True


class TestRateLimiterWeight:
    def test_weighted_requests(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        ) 
        key = "test:weight"
        limiter.allow(key, weight=50)
        state = limiter.check(key)
        assert state.remaining < 100

    def test_heavy_weight_denied(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=10,
            window=60
        )
        key = "test:heavy"
        allowed = limiter.allow(key, weight=20)
        assert allowed is False