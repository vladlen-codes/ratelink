import pytest
import tempfile
import os
from pathlib import Path
from ratelink.config import ConfigLoader, RuleEngine
from ratelink.rate_limiter import RateLimiter
from ratelink.core.types import ConfigError

class TestConfigLoader:
    def test_load_from_dict(self):
        loader = ConfigLoader()
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "token_bucket",
                    "backend": "memory",
                    "limit": 1000,
                    "window": "hour"
                }
            }
        }
        
        loaded = loader.load(config)
        assert loaded["rate_limiting"]["default"]["limit"] == 1000

    def test_load_from_yaml(self):
        loader = ConfigLoader()
        
        yaml_content = """
rate_limiting:
  default:
    algorithm: token_bucket
    backend: memory
    limit: 1000
    window: hour
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            config = loader.load(temp_path)
            assert config["rate_limiting"]["default"]["limit"] == 1000
        finally:
            os.unlink(temp_path)

    def test_load_from_json(self):
        loader = ConfigLoader()
        
        json_content = """{
  "rate_limiting": {
    "default": {
      "algorithm": "sliding_window",
      "backend": "memory",
      "limit": 500,
      "window": "minute"
    }
  }
}"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(json_content)
            temp_path = f.name
        
        try:
            config = loader.load(temp_path)
            assert config["rate_limiting"]["default"]["algorithm"] == "sliding_window"
        finally:
            os.unlink(temp_path)

    def test_load_from_env(self):
        loader = ConfigLoader()
        
        os.environ["RATELINK_ALGORITHM"] = "gcra"
        os.environ["RATELINK_BACKEND"] = "memory"
        os.environ["RATELINK_LIMIT"] = "2000"
        os.environ["RATELINK_WINDOW"] = "day"
        
        try:
            config = loader.load_from_env()
            assert config["rate_limiting"]["default"]["algorithm"] == "gcra"
            assert config["rate_limiting"]["default"]["limit"] == 2000
        finally:
            # Cleanup
            for key in ["RATELINK_ALGORITHM", "RATELINK_BACKEND", "RATELINK_LIMIT", "RATELINK_WINDOW"]:
                os.environ.pop(key, None)

    def test_invalid_yaml(self):
        loader = ConfigLoader()
        
        invalid_yaml = """
rate_limiting:
  default:
    - this is: invalid
    - yaml: structure
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        try:
            with pytest.raises(ConfigError):
                loader.load(temp_path)
        finally:
            os.unlink(temp_path)

    def test_file_not_found(self):
        loader = ConfigLoader()
        with pytest.raises(ConfigError):
            loader.load("nonexistent_file.yaml")

    def test_unsupported_format(self):
        loader = ConfigLoader()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("some content")
            temp_path = f.name
        try:
            with pytest.raises(ConfigError):
                loader.load(temp_path)
        finally:
            os.unlink(temp_path)


class TestRateLimiterFromConfig:
    def test_from_config_dict(self):
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "token_bucket",
                    "backend": "memory",
                    "limit": 100,
                    "window": "minute"
                }
            }
        }
        limiter = RateLimiter.from_config(config)
        assert limiter.limit == 100
        assert limiter.window == 60

    def test_from_config_yaml(self):
        yaml_content = """
rate_limiting:
  default:
    algorithm: sliding_window
    backend: memory
    limit: 500
    window: hour
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        try:
            limiter = RateLimiter.from_config(temp_path)
            assert limiter.limit == 500
            assert limiter.window == 3600
        finally:
            os.unlink(temp_path)

    def test_from_config_missing_default(self):
        config = {
            "rate_limiting": {
                "endpoints": {}
            }
        }
        with pytest.raises(ConfigError):
            RateLimiter.from_config(config)

    def test_from_config_with_endpoints(self):
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "token_bucket",
                    "backend": "memory",
                    "limit": 1000,
                    "window": "hour"
                },
                "endpoints": {
                    "/api/search": {
                        "limit": 100,
                        "window": "minute"
                    }
                }
            }
        }
        limiter = RateLimiter.from_config(config)
        assert limiter._full_config["rate_limiting"]["endpoints"]["/api/search"]["limit"] == 100

    def test_from_config_with_users(self):
        config = {
            "rate_limiting": {
                "default": {
                    "algorithm": "token_bucket",
                    "backend": "memory",
                    "limit": 1000,
                    "window": "hour"
                },
                "users": {
                    "free": {
                        "limit": 100,
                        "window": "hour"
                    },
                    "pro": {
                        "limit": 10000,
                        "window": "hour"
                    }
                }
            }
        }
        limiter = RateLimiter.from_config(config)
        assert limiter._full_config["rate_limiting"]["users"]["free"]["limit"] == 100


class TestRuleEngine:
    def test_get_limit_for_endpoint(self):
        config = {
            "rate_limiting": {
                "endpoints": {
                    "/api/search": {
                        "limit": 50,
                        "window": "minute"
                    }
                }
            }
        }
        engine = RuleEngine(config)
        limit, window = engine.get_limit_for_endpoint("/api/search", 1000, "hour")
        assert limit == 50
        assert window == "minute"

    def test_get_limit_for_endpoint_default(self):
        config = {"rate_limiting": {"endpoints": {}}}
        engine = RuleEngine(config)
        limit, window = engine.get_limit_for_endpoint("/api/unknown", 1000, "hour")
        assert limit == 1000
        assert window == "hour"

    def test_get_limit_for_user(self):
        config = {
            "rate_limiting": {
                "users": {
                    "free": {
                        "limit": 100,
                        "window": "hour"
                    },
                    "pro": {
                        "limit": 5000,
                        "window": "hour"
                    }
                }
            }
        }
        engine = RuleEngine(config)
        limit, window = engine.get_limit_for_user("free", 1000, "day")
        assert limit == 100
        assert window == "hour"

    def test_get_limit_for_user_unlimited(self):
        config = {
            "rate_limiting": {
                "users": {
                    "enterprise": {
                        "limit": None,
                        "window": "hour"
                    }
                }
            }
        }
        engine = RuleEngine(config)
        limit, window = engine.get_limit_for_user("enterprise", 1000, "hour")
        assert limit is None
        assert window == "hour"

    def test_get_limit_for_time(self):
        from datetime import time as datetime_time
        config = {
            "rate_limiting": {
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
                            },
                            {
                                "start": "17:00",
                                "end": "09:00",
                                "limit": 500,
                                "window": "hour"
                            }
                        ]
                    }
                }
            }
        }
        engine = RuleEngine(config)
        result = engine.get_limit_for_time("/api/data", datetime_time(10, 30))
        assert result is not None
        limit, window = result
        assert limit == 100
        result = engine.get_limit_for_time("/api/data", datetime_time(20, 0))
        assert result is not None
        limit, window = result
        assert limit == 500

    def test_time_range_crossing_midnight(self):
        from datetime import time as datetime_time
        config = {
            "rate_limiting": {
                "endpoints": {
                    "/api/night": {
                        "limit": 1000,
                        "window": "hour",
                        "time_ranges": [
                            {
                                "start": "22:00",
                                "end": "06:00",
                                "limit": 50,
                                "window": "hour"
                            }
                        ]
                    }
                }
            }
        }
        engine = RuleEngine(config)
        result = engine.get_limit_for_time("/api/night", datetime_time(23, 0))
        assert result is not None
        
        result = engine.get_limit_for_time("/api/night", datetime_time(2, 0))
        assert result is not None
        
        result = engine.get_limit_for_time("/api/night", datetime_time(12, 0))
        assert result is None


class TestConfigValidation:
    def test_valid_time_format(self):
        try:
            from pydantic import ValidationError
            from ratelink.config import TimeRangeConfig
            
            config = TimeRangeConfig(
                start="09:00",
                end="17:00",
                limit=100,
                window="hour"
            )
            assert config.start == "09:00"
        except ImportError:
            pytest.skip("Pydantic not installed")

    def test_invalid_time_format(self):
        try:
            from pydantic import ValidationError
            from ratelink.config import TimeRangeConfig
            
            with pytest.raises(ValidationError):
                TimeRangeConfig(
                    start="25:00",
                    end="17:00",
                    limit=100,
                    window="hour"
                )
        except ImportError:
            pytest.skip("Pydantic not installed")