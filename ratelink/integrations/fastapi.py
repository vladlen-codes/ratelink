import functools
from typing import Any, Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from ratelink.utils.key_generators import KeyGeneratorFunc, by_ip

class FastAPIRateLimitMiddleware(BaseHTTPMiddleware):    
    def __init__(
        self,
        app,
        limiter: Any,
        key_generator: Optional[KeyGeneratorFunc] = None,
        skip_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.limiter = limiter
        self.key_generator = key_generator or by_ip()
        self.skip_paths = set(skip_paths or [])
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.skip_paths:
            return await call_next(request)
        
        key = self.key_generator(request)
        
        state = self.limiter.check(key)
        
        if state.violated:
            retry_after = state.retry_after
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": state.limit,
                    "remaining": 0,
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(state.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(retry_after))
                }
            )
        
        response = await call_next(request)
        
        response.headers["X-RateLimit-Limit"] = str(state.limit)
        response.headers["X-RateLimit-Remaining"] = str(state.remaining)
        if state.retry_after:
            response.headers["X-RateLimit-Reset"] = str(int(state.retry_after))
        
        return response


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
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if request is None and 'request' in kwargs:
                request = kwargs['request']
            
            if request is None:
                return await func(*args, **kwargs)

            key = key_generator(request)
            
            state = limiter.check(key)
            
            if state.violated:
                retry_after = state.retry_after
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "limit": state.limit,
                        "remaining": 0,
                        "retry_after": retry_after
                    },
                    headers={
                        "Retry-After": str(int(retry_after)),
                        "X-RateLimit-Limit": str(state.limit),
                        "X-RateLimit-Remaining": "0",
                    }
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator

class RateLimitExceeded(Exception):
    def __init__(self, state: dict):
        self.state = state
        self.retry_after = state.get('retry_after', 0)
        self.limit = state.get('limit', 0)
        self.remaining = state.get('remaining', 0)
        super().__init__(f"Rate limit exceeded. Retry after {self.retry_after}s")

def setup_exception_handler(app):
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "limit": exc.limit,
                "remaining": exc.remaining,
                "retry_after": exc.retry_after
            },
            headers={
                "Retry-After": str(int(exc.retry_after)),
                "X-RateLimit-Limit": str(exc.limit),
                "X-RateLimit-Remaining": str(exc.remaining),
            }
        )