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
from .core.abstractions import Algorithm, Backend, RateLimiter as RateLimiterABC
from .algorithms.token_bucket import TokenBucketAlgorithm
from .algorithms.sliding_window import SlidingWindowAlgorithm
from .algorithms.leaky_bucket import LeakyBucketAlgorithm
from .algorithms.fixed_window import FixedWindowAlgorithm
from .algorithms.gcra import GCRAAlgorithm
from .algorithms.hierarchical import HierarchicalTokenBucket, FairQueueingAlgorithm
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
from .rate_limiter import RateLimiter
from .config import ConfigLoader, RuleEngine
from .priority_limiter import PriorityRateLimiter
from .quota_pool import QuotaPool, SharedQuotaManager
from .adaptive_limiter import AdaptiveRateLimiter

__version__ = "0.4.0"

__all__ = [
    "RateLimiter",
    "ConfigLoader",
    "RuleEngine",
    "PriorityRateLimiter",
    "QuotaPool",
    "SharedQuotaManager",
    "AdaptiveRateLimiter",
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
    "RateLimiterABC",
    "TokenBucketAlgorithm",
    "SlidingWindowAlgorithm",
    "LeakyBucketAlgorithm",
    "FixedWindowAlgorithm",
    "GCRAAlgorithm",
    "HierarchicalTokenBucket",
    "FairQueueingAlgorithm",
    "MemoryBackend",
    "MultiRegionBackend",
    "CustomBackendInterface",
    "RedisBackend",
    "PostgreSQLBackend",
    "DynamoDBBackend",
    "MongoDBBackend",
]
