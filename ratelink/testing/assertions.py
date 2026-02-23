from typing import Any, Dict, Optional

class RateLimitAssertionError(AssertionError):
    pass

def assert_allowed(
    limiter: Any,
    key: str,
    weight: int = 1,
    times: int = 1,
    message: Optional[str] = None
):
    for i in range(times):
        allowed, state = limiter.check(key, weight)
        if not allowed:
            error_msg = message or (
                f"Expected key '{key}' to be allowed on attempt {i+1}/{times}, "
                f"but it was denied. State: {state}"
            )
            raise RateLimitAssertionError(error_msg)

def assert_denied(
    limiter: Any,
    key: str,
    weight: int = 1,
    message: Optional[str] = None
):
    allowed, state = limiter.check(key, weight)
    if allowed:
        error_msg = message or (
            f"Expected key '{key}' to be denied, but it was allowed. "
            f"State: {state}"
        )
        raise RateLimitAssertionError(error_msg)

def assert_remaining(
    limiter: Any,
    key: str,
    expected: int,
    tolerance: int = 0,
    message: Optional[str] = None
):
    allowed, state = limiter.check(key, weight=0)  # Weight 0 = peek without consuming
    remaining = state.get('remaining', 0)
    if tolerance > 0:
        if not (expected - tolerance <= remaining <= expected + tolerance):
            error_msg = message or (
                f"Expected key '{key}' to have {expected} remaining "
                f"(±{tolerance}), but got {remaining}. State: {state}"
            )
            raise RateLimitAssertionError(error_msg)
    else:
        if remaining != expected:
            error_msg = message or (
                f"Expected key '{key}' to have {expected} remaining, "
                f"but got {remaining}. State: {state}"
            )
            raise RateLimitAssertionError(error_msg)

def assert_state(
    limiter: Any,
    key: str,
    message: Optional[str] = None,
    **expected_values
):
    allowed, state = limiter.check(key, weight=0)  # Peek
    mismatches = []
    for key_name, expected_value in expected_values.items():
        actual_value = state.get(key_name)
        
        if actual_value != expected_value:
            mismatches.append(
                f"  {key_name}: expected {expected_value}, got {actual_value}"
            )
    if mismatches:
        error_msg = message or (
            f"State mismatch for key '{key}':\n" + "\n".join(mismatches) +
            f"\nFull state: {state}"
        )
        raise RateLimitAssertionError(error_msg)

def assert_allows_n_then_denies(
    limiter: Any,
    key: str,
    n: int,
    weight: int = 1,
    message: Optional[str] = None
):
    try:
        assert_allowed(limiter, key, weight=weight, times=n)
    except RateLimitAssertionError as e:
        error_msg = message or f"Expected {n} allowed requests, but failed: {e}"
        raise RateLimitAssertionError(error_msg)    
    try:
        assert_denied(limiter, key, weight=weight)
    except RateLimitAssertionError as e:
        error_msg = message or f"Expected denial after {n} requests, but was allowed: {e}"
        raise RateLimitAssertionError(error_msg)

def assert_retry_after(
    limiter: Any,
    key: str,
    min_seconds: float = 0,
    max_seconds: Optional[float] = None,
    message: Optional[str] = None
):
    allowed, state = limiter.check(key, weight=0)
    retry_after = state.get('retry_after', 0)
    if retry_after < min_seconds:
        error_msg = message or (
            f"Expected retry_after >= {min_seconds}, but got {retry_after}"
        )
        raise RateLimitAssertionError(error_msg)
    
    if max_seconds is not None and retry_after > max_seconds:
        error_msg = message or (
            f"Expected retry_after <= {max_seconds}, but got {retry_after}"
        )
        raise RateLimitAssertionError(error_msg)

def assert_limit_equals(
    limiter: Any,
    key: str,
    expected_limit: int,
    message: Optional[str] = None
):
    allowed, state = limiter.check(key, weight=0)
    
    actual_limit = state.get('limit', 0)
    
    if actual_limit != expected_limit:
        error_msg = message or (
            f"Expected limit of {expected_limit}, but got {actual_limit}"
        )
        raise RateLimitAssertionError(error_msg)

def assert_eventually_allowed(
    limiter: Any,
    key: str,
    time_machine: Any,
    max_advance: float = 300,
    step: float = 1,
    weight: int = 1,
    message: Optional[str] = None
):
    total_advanced = 0
    
    while total_advanced < max_advance:
        allowed, state = limiter.check(key, weight=weight)
        
        if allowed:
            return 

        time_machine.advance(step)
        total_advanced += step
    
    error_msg = message or (
        f"Key '{key}' was not allowed even after advancing {max_advance}s"
    )
    raise RateLimitAssertionError(error_msg)

def assert_state_contains(
    limiter: Any,
    key: str,
    *expected_keys: str,
    message: Optional[str] = None
):
    allowed, state = limiter.check(key, weight=0)    
    missing_keys = [k for k in expected_keys if k not in state]
    
    if missing_keys:
        error_msg = message or (
            f"State for key '{key}' is missing keys: {missing_keys}. "
            f"State: {state}"
        )
        raise RateLimitAssertionError(error_msg)