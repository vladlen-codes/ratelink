from .core.types import (
    AlgorithmType,
    BackendType,
    WindowType,
    RateLimitState,
    RateLimitResult,
    RateLimitException,
    LimitExceeded,
    BackendError,
    ConfigError,
    TimeoutError,
)

from .core.abstractions import Algorithm, Backend, RateLimiter

from .algorithms.token_bucket import TokenBucketAlgorithm
from .algorithms.sliding_window import SlidingWindowAlgorithm
from .algorithms.leaky_bucket import LeakyBucketAlgorithm
from .algorithms.fixed_window import FixedWindowAlgorithm
from .algorithms.gcra import GCRAAlgorithm

from .backends.memory import MemoryBackend
from .backends.multi_region import MultiRegionBackend
from .backends.custom import CustomBackendInterface

try:
    from .backends.redis import RedisBackend
except ImportError:
    pass

try:
    from .backends.postgresql import PostgreSQLBackend
except ImportError:
    pass

try:
    from .backends.dynamodb import DynamoDBBackend
except ImportError:
    pass

try:
    from .backends.mongodb import MongoDBBackend
except ImportError:
    pass

__version__ = "0.2.0"

__all__ = [
    "AlgorithmType",
    "BackendType",
    "WindowType",
    "RateLimitState",
    "RateLimitResult",
    "RateLimitException",
    "LimitExceeded",
    "BackendError",
    "ConfigError",
    "TimeoutError",
    "Algorithm",
    "Backend",
    "RateLimiter",
    "TokenBucketAlgorithm",
    "SlidingWindowAlgorithm",
    "LeakyBucketAlgorithm",
    "FixedWindowAlgorithm",
    "GCRAAlgorithm",
    "MemoryBackend",
    "MultiRegionBackend",
    "CustomBackendInterface",
    "RedisBackend",
    "PostgreSQLBackend",
    "DynamoDBBackend",
    "MongoDBBackend",
]
