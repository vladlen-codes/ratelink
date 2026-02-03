import pytest
import tempfile
import os
from ratelink import RateLimiter
from ratelink.core.types import LimitExceeded


class TestIntegrationScenarios:
    def test_api_gateway_scenario(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window="minute"
        )
        user_id = "user:123"
        for i in range(50):
            allowed = limiter.allow(user_id)
            assert allowed is True
        state = limiter.check(user_id)
        assert state.remaining < 100

    def test_multi_tier_users(self):
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "fixed_window",
                    "backend": "memory",
                    "limit": 100,
                    "window": "hour"
                },
                "users": {
                    "free": {"limit": 10, "window": "hour"},
                    "pro": {"limit": 1000, "window": "hour"},
                    "enterprise": {"limit": None, "window": "hour"}
                }
            }
        }
        limiter = RateLimiter.from_config(config)
        assert limiter._full_config["rate_limiting"]["users"]["free"]["limit"] == 10
        assert limiter._full_config["rate_limiting"]["users"]["enterprise"]["limit"] is None

    def test_endpoint_specific_limits(self):
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "sliding_window",
                    "backend": "memory",
                    "limit": 1000,
                    "window": "hour"
                },
                "endpoints": {
                    "/api/search": {
                        "limit": 100,
                        "window": "minute"
                    },
                    "/api/write": {
                        "limit": 10,
                        "window": "minute"
                    }
                }
            }
        }
        
        limiter = RateLimiter.from_config(config)
        assert limiter._full_config["rate_limiting"]["endpoints"]["/api/search"]["limit"] == 100
        assert limiter._full_config["rate_limiting"]["endpoints"]["/api/write"]["limit"] == 10

    def test_peak_hours_limiting(self):
        from datetime import time as datetime_time
        
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "token_bucket",
                    "backend": "memory",
                    "limit": 1000,
                    "window": "hour"
                },
                "endpoints": {
                    "/api/data": {
                        "limit": 1000,
                        "window": "hour",
                        "time_ranges": [
                            {
                                "start": "09:00",
                                "end": "17:00",
                                "limit": 100,
                                "window": "minute"
                            }
                        ]
                    }
                }
            }
        }
        
        limiter = RateLimiter.from_config(config)        
        time_ranges = limiter._full_config["rate_limiting"]["endpoints"]["/api/data"]["time_ranges"]
        assert len(time_ranges) == 1
        assert time_ranges[0]["limit"] == 100

    def test_hook_based_logging(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=10,
            window=60
        )
        log = []
        def log_request(key, weight, state):
            log.append({
                "key": key,
                "allowed": not state.violated,
                "remaining": state.remaining
            })
        limiter.register_hook("after_check", log_request)
        for i in range(5):
            limiter.allow(f"user:{i}")
        assert len(log) == 5

    def test_dynamic_reconfiguration(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        for _ in range(10):
            limiter.allow("user:dynamic")

        limiter.reconfigure(limit=200)
        
        assert limiter.limit == 200

    def test_graceful_degradation(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=5,
            window=60,
            raise_on_limit=False
        )
        
        key = "user:graceful"

        for _ in range(5):
            limiter.allow(key)
        allowed = limiter.allow(key)
        assert allowed is False

    def test_strict_enforcement(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=3,
            window=60,
            raise_on_limit=True
        )
        
        key = "user:strict"
    
        for _ in range(3):
            limiter.allow(key)
        with pytest.raises(LimitExceeded):
            limiter.allow(key)

    @pytest.mark.asyncio
    async def test_async_workflow(self):
        limiter = RateLimiter(
            algorithm="sliding_window",
            backend="memory",
            limit=50,
            window=60
        )
        
        key = "async:workflow"

        for i in range(10):
            allowed = await limiter.acquire(key)
            assert allowed is True

        state = await limiter.async_check(key)
        assert state.remaining < 50
        
        await limiter.async_reset(key)

    def test_config_hot_reload_structure(self):
        yaml_content = """
rate_limiting:
  default:
    algorithm: token_bucket
    backend: memory
    limit: 100
    window: minute
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        try:
            limiter = RateLimiter.from_config(temp_path, watch=False)
            assert limiter.limit == 100
        finally:
            os.unlink(temp_path)

    def test_environment_based_config(self):
        os.environ["RATELIMIT_ALGORITHM"] = "gcra"
        os.environ["RATELIMIT_BACKEND"] = "memory"
        os.environ["RATELIMIT_LIMIT"] = "500"
        os.environ["RATELIMIT_WINDOW"] = "minute"
        
        try:
            from ratelink.config import ConfigLoader
            
            loader = ConfigLoader()
            config = loader.load_from_env()
            
            limiter = RateLimiter.from_config(config)
            assert limiter.limit == 500
        finally:
            for key in ["RATELIMIT_ALGORITHM", "RATELIMIT_BACKEND", "RATELIMIT_LIMIT", "RATELIMIT_WINDOW"]:
                os.environ.pop(key, None)

    def test_weighted_api_calls(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=60
        )
        
        user = "user:weighted"
        
        for _ in range(5):
            limiter.allow(user, weight=1)
        
        limiter.allow(user, weight=10)
        limiter.allow(user, weight=20)
        state = limiter.check(user)
        assert state.remaining < 100

    def test_burst_handling(self):
        limiter = RateLimiter(
            algorithm="token_bucket",
            backend="memory",
            limit=100,
            window=10,
            algorithm_options={"capacity": 100}
        )
        
        key = "burst:traffic"
        
        allowed_count = 0
        for _ in range(50):
            if limiter.allow(key):
                allowed_count += 1
        assert allowed_count > 0


class TestRealWorldPatterns:
    def test_rate_limit_headers(self):
        limiter = RateLimiter(
            algorithm="sliding_window",
            backend="memory",
            limit=1000,
            window="hour"
        )
        
        key = "api:client"
        limiter.allow(key, weight=10)
        
        state = limiter.check(key)
        
        headers = {
            "X-RateLimit-Limit": state.limit,
            "X-RateLimit-Remaining": state.remaining,
            "X-RateLimit-Reset": state.reset_at.isoformat()
        }
        
        assert headers["X-RateLimit-Limit"] > 0
        assert headers["X-RateLimit-Remaining"] >= 0

    def test_circuit_breaker_pattern(self):
        limiter = RateLimiter(
            algorithm="fixed_window",
            backend="memory",
            limit=10,
            window=60
        )
        
        service = "external:api"
        failures = []
        
        def on_deny_hook(key, weight, state):
            failures.append(state.retry_after)
        
        limiter.register_hook("on_deny", on_deny_hook)
        
        for _ in range(10):
            limiter.allow(service)

        limiter.allow(service)
        assert len(failures) > 0