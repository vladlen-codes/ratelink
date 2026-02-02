from typing import Optional, Dict, Any, Callable, Union
from datetime import datetime
from .core.types import RateLimitState, AlgorithmType, BackendType
from .core.types import ConfigError, LimitExceeded
from .core.abstractions import Algorithm, Backend
from .algorithms.token_bucket import TokenBucketAlgorithm
from .algorithms.sliding_window import SlidingWindowAlgorithm
from .algorithms.leaky_bucket import LeakyBucketAlgorithm
from .algorithms.fixed_window import FixedWindowAlgorithm
from .algorithms.gcra import GCRAAlgorithm
from .backends.memory import MemoryBackend

try:
    from .backends.redis import RedisBackend
except ImportError:
    RedisBackend = None

try:
    from .backends.postgresql import PostgreSQLBackend
except ImportError:
    PostgreSQLBackend = None

try:
    from .backends.dynamodb import DynamoDBBackend
except ImportError:
    DynamoDBBackend = None

try:
    from .backends.mongodb import MongoDBBackend
except ImportError:
    MongoDBBackend = None

from .backends.multi_region import MultiRegionBackend


class RateLimiter:
    def __init__(
        self,
        algorithm: Union[str, Algorithm],
        backend: Union[str, Backend],
        limit: int,
        window: Union[int, str],
        backend_options: Optional[Dict[str, Any]] = None,
        algorithm_options: Optional[Dict[str, Any]] = None,
        raise_on_limit: bool = False,
    ) -> None:
        self.limit = limit
        self.window = self._parse_window(window)
        self.raise_on_limit = raise_on_limit
        if isinstance(backend, str):
            self.backend = self._create_backend(backend, backend_options or {})
        else:
            self.backend = backend
        if isinstance(algorithm, str):
            self.algorithm = self._create_algorithm(
                algorithm, limit, self.window, algorithm_options or {}
            )
        else:
            self.algorithm = algorithm
        self._hooks: Dict[str, list] = {
            "before_check": [],
            "after_check": [],
            "on_allow": [],
            "on_deny": [],
            "on_error": [],
        }
        self._config = {
            "algorithm": algorithm if isinstance(algorithm, str) else algorithm.__class__.__name__,
            "backend": backend if isinstance(backend, str) else backend.__class__.__name__,
            "limit": limit,
            "window": window,
            "backend_options": backend_options or {},
            "algorithm_options": algorithm_options or {},
            "raise_on_limit": raise_on_limit,
        }

    def _parse_window(self, window: Union[int, str]) -> int:
        if isinstance(window, int):
            return window
        window = window.lower()
        conversions = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
            "week": 604800,
        }
        if window in conversions:
            return conversions[window]
        raise ConfigError(f"Invalid window: {window}")

    def _create_backend(self, backend_type: str, options: Dict[str, Any]) -> Backend:
        backend_type = backend_type.lower()
        if backend_type == "memory":
            return MemoryBackend(**options)
        elif backend_type == "redis":
            if RedisBackend is None:
                raise ConfigError("Redis backend not installed. Install: pip install universal-rate-limiter[redis]")
            return RedisBackend(**options)
        elif backend_type == "postgresql":
            if PostgreSQLBackend is None:
                raise ConfigError("PostgreSQL backend not installed. Install: pip install universal-rate-limiter[postgresql]")
            return PostgreSQLBackend(**options)
        elif backend_type == "dynamodb":
            if DynamoDBBackend is None:
                raise ConfigError("DynamoDB backend not installed. Install: pip install universal-rate-limiter[dynamodb]")
            return DynamoDBBackend(**options)
        elif backend_type == "mongodb":
            if MongoDBBackend is None:
                raise ConfigError("MongoDB backend not installed. Install: pip install universal-rate-limiter[mongodb]")
            return MongoDBBackend(**options)
        else:
            raise ConfigError(f"Unknown backend type: {backend_type}")

    def _create_algorithm(
        self, algorithm_type: str, limit: int, window: int, options: Dict[str, Any]) -> Algorithm:
        algorithm_type = algorithm_type.lower()
        if algorithm_type == "token_bucket":
            return TokenBucketAlgorithm(
                capacity=options.get("capacity", limit),
                refill_rate=options.get("refill_rate", limit / window),
                refill_period=options.get("refill_period", 1.0),
                **{k: v for k, v in options.items() if k not in ["capacity", "refill_rate", "refill_period"]},
            )
        elif algorithm_type == "sliding_window":
            return SlidingWindowAlgorithm(limit=limit, window_seconds=window)
        elif algorithm_type == "leaky_bucket":
            return LeakyBucketAlgorithm(
                capacity=options.get("capacity", limit),
                leak_rate=options.get("leak_rate", limit / window),
                leak_period=options.get("leak_period", 1.0),
            )
        elif algorithm_type == "fixed_window":
            return FixedWindowAlgorithm(limit=limit, window_seconds=window)
        elif algorithm_type == "gcra":
            return GCRAAlgorithm(
                limit=limit,
                period_seconds=window,
                burst=options.get("burst", limit),
            )
        else:
            raise ConfigError(f"Unknown algorithm type: {algorithm_type}")

    def allow(self, key: str, weight: int = 1) -> bool:
        self._run_hooks("before_check", key, weight)
        try:
            allowed, state = self.algorithm.allow(key, weight)
            self._run_hooks("after_check", key, weight, state)
            if allowed:
                self._run_hooks("on_allow", key, weight, state)
                return True
            else:
                self._run_hooks("on_deny", key, weight, state)
                
                if self.raise_on_limit:
                    raise LimitExceeded(
                        f"Rate limit exceeded for {key}",
                        retry_after=state.retry_after,
                    )
                return False
        except Exception as e:
            self._run_hooks("on_error", key, weight, e)
            raise

    async def acquire(self, key: str, weight: int = 1) -> bool:
        self._run_hooks("before_check", key, weight)
        try:
            allowed, state = await self.algorithm.acquire_async(key, weight)
            self._run_hooks("after_check", key, weight, state)
            if allowed:
                self._run_hooks("on_allow", key, weight, state)
                return True
            else:
                self._run_hooks("on_deny", key, weight, state)
                
                if self.raise_on_limit:
                    raise LimitExceeded(
                        f"Rate limit exceeded for {key}",
                        retry_after=state.retry_after,
                    )
                
                return False

        except Exception as e:
            self._run_hooks("on_error", key, weight, e)
            raise

    def check(self, key: str) -> RateLimitState:
        return self.algorithm.check(key)

    async def async_check(self, key: str) -> RateLimitState:
        return self.algorithm.check(key)

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        self.algorithm.reset(key)

    async def async_reset(self, key: Optional[str] = None) -> None:
        self.algorithm.reset(key)

    def register_hook(self, event: str, callback: Callable) -> None:
        if event not in self._hooks:
            raise ValueError(f"Unknown event: {event}")
        self._hooks[event].append(callback)

    def _run_hooks(self, event: str, *args: Any) -> None:
        for callback in self._hooks.get(event, []):
            try:
                callback(*args)
            except Exception:
                pass

    def reconfigure(self, **kwargs: Any) -> None:
        if "limit" in kwargs:
            self.limit = kwargs["limit"]
            self._config["limit"] = kwargs["limit"]

        if "window" in kwargs:
            self.window = self._parse_window(kwargs["window"])
            self._config["window"] = kwargs["window"]

        if "raise_on_limit" in kwargs:
            self.raise_on_limit = kwargs["raise_on_limit"]
            self._config["raise_on_limit"] = kwargs["raise_on_limit"]

        if "limit" in kwargs or "window" in kwargs:
            algorithm_type = self._config["algorithm"]
            if isinstance(algorithm_type, str):
                self.algorithm = self._create_algorithm(
                    algorithm_type,
                    self.limit,
                    self.window,
                    self._config["algorithm_options"],
                )

    def get_config(self) -> Dict[str, Any]:
        return self._config.copy()

    @classmethod
    def from_config(
        cls, config: Union[str, Dict[str, Any]], watch: bool = False
    ) -> "RateLimiter":
        from .config import ConfigLoader
        loader = ConfigLoader()
        config_dict = loader.load(config)
        default_config = config_dict.get("rate_limiting", {}).get("default", {})
        if not default_config:
            raise ConfigError("No default rate limiting configuration found")
        instance = cls(
            algorithm=default_config.get("algorithm", "token_bucket"),
            backend=default_config.get("backend", "memory"),
            limit=default_config.get("limit", 1000),
            window=default_config.get("window", "hour"),
            backend_options=default_config.get("backend_options", {}),
            algorithm_options=default_config.get("algorithm_options", {}),
            raise_on_limit=default_config.get("raise_on_limit", False),
        )
        instance._full_config = config_dict
        if watch and isinstance(config, str):
            loader.watch(config, lambda: instance._reload_config(config))

        return instance

    def _reload_config(self, config_path: str) -> None:
        from .config import ConfigLoader
        loader = ConfigLoader()
        config_dict = loader.load(config_path)
        default_config = config_dict.get("rate_limiting", {}).get("default", {})
        self.reconfigure(
            limit=default_config.get("limit", self.limit),
            window=default_config.get("window", self.window),
        )
        self._full_config = config_dict