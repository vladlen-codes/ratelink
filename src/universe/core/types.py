from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional


class AlgorithmType(Enum):
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    LEAKY_BUCKET = "leaky_bucket"
    FIXED_WINDOW = "fixed_window"
    GCRA = "gcra"


class BackendType(Enum):
    MEMORY = "memory"
    REDIS = "redis"
    POSTGRESQL = "postgresql"
    DYNAMODB = "dynamodb"
    MONGODB = "mongodb"


class WindowType(Enum):
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


@dataclass
class RateLimitState:
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: float
    violated: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError("limit must be non-negative")
        if self.remaining < 0:
            self.remaining = 0


@dataclass
class RateLimitResult:
    allowed: bool
    state: RateLimitState
    metadata: Dict[str, Any] = field(default_factory=dict)

class RateLimitException(Exception):
    pass


class LimitExceeded(RateLimitException):
    pass

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BackendError(RateLimitException):
    pass


class ConfigError(RateLimitException):
    pass


class TimeoutError(RateLimitException):
    pass