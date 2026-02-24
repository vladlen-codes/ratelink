"""
Testing utilities for Ratelink.

Provides mock limiters, time control, assertion helpers, pytest fixtures,
and load testing tools to make testing rate limiters easy and effective.
"""

from .assertions import (
    RateLimitAssertionError,
    assert_allowed,
    assert_denied,
    assert_eventually_allowed,
    assert_limit_equals,
    assert_remaining,
    assert_retry_after,
    assert_state,
    assert_state_contains,
    assert_allows_n_then_denies,
)
from .fixtures import (
    frozen_time,
    limiter_with_time,
    memory_limiter,
    mock_limiter,
    mock_limiter_deny,
    postgres_limiter,
    redis_limiter,
    scripted_limiter,
    time_machine,
)
from .load import (
    LoadTestResult,
    benchmark_algorithm,
    compare_algorithms,
    simulate_load,
    simulate_load_async,
    stress_test,
)
from .mock import MockRateLimiter, ScriptedBehavior
from .time_machine import MonkeyPatchedTimeMachine, TimeMachine, advance_time, freeze_time

__all__ = [
    # Mock
    "MockRateLimiter",
    "ScriptedBehavior",
    # Time Machine
    "TimeMachine",
    "MonkeyPatchedTimeMachine",
    "freeze_time",
    "advance_time",
    # Assertions
    "RateLimitAssertionError",
    "assert_allowed",
    "assert_denied",
    "assert_remaining",
    "assert_state",
    "assert_allows_n_then_denies",
    "assert_retry_after",
    "assert_limit_equals",
    "assert_eventually_allowed",
    "assert_state_contains",
    # Fixtures (imported in conftest.py)
    "mock_limiter",
    "mock_limiter_deny",
    "scripted_limiter",
    "time_machine",
    "frozen_time",
    "memory_limiter",
    "redis_limiter",
    "postgres_limiter",
    "limiter_with_time",
    # Load Testing
    "LoadTestResult",
    "simulate_load",
    "simulate_load_async",
    "benchmark_algorithm",
    "compare_algorithms",
    "stress_test",
]
