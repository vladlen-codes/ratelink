import asyncio
import functools
from typing import Any, Callable, Optional
from ratelink.utils.key_generators import KeyGeneratorFunc, by_ip

class RateLimitExceeded(Exception):    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float = 0.0,
        limit: int = 0,
        remaining: int = 0
    ):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining


def rate_limit(
    limiter: Any,
    limit: Optional[int] = None,
    window: Optional[int] = None,
    key_generator: Optional[KeyGeneratorFunc] = None
):
    if key_generator is None:
        key_generator = by_ip()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            request = _extract_request(args, kwargs)
            
            if request is None:
                return await func(*args, **kwargs)
            
            key = key_generator(request)
            
            if limit is not None and window is not None:
                pass
            
            state = limiter.check(key)
            
            if state.violated:
                raise RateLimitExceeded(
                    retry_after=state.retry_after,
                    limit=state.limit,
                    remaining=state.remaining
                )
            
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            request = _extract_request(args, kwargs)
            
            if request is None:
                return func(*args, **kwargs)
            
            key = key_generator(request)
            
            state = limiter.check(key)
            
            if state.violated:
                raise RateLimitExceeded(
                    retry_after=state.retry_after,
                    limit=state.limit,
                    remaining=state.remaining
                )
            
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def _extract_request(args: tuple, kwargs: dict) -> Optional[Any]:
    for key in ['request', 'req']:
        if key in kwargs:
            return kwargs[key]
    
    if args:
        first_arg = args[0]
        if hasattr(first_arg, 'headers') or hasattr(first_arg, 'META'):
            return first_arg
    
    return None