from typing import Any, Callable, Optional
from aiohttp import web
from ratelink.utils.key_generators import KeyGeneratorFunc, by_ip

def aiohttp_rate_limit_middleware(
    limiter: Any,
    key_func: Optional[KeyGeneratorFunc] = None,
    skip_paths: Optional[set] = None
):
    if key_func is None:
        key_func = by_ip()
    
    if skip_paths is None:
        skip_paths = set()
    
    @web.middleware
    async def middleware(request, handler):
        if request.path in skip_paths:
            return await handler(request)
        
        key = key_func(request)
        
        allowed, state = limiter.check(key)
        
        if not allowed:
            retry_after = state.get('retry_after', 0)
            return web.json_response(
                {
                    "error": "Rate limit exceeded",
                    "limit": state.get('limit', 0),
                    "remaining": 0,
                    "retry_after": retry_after
                },
                status=429,
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(state.get('limit', 0)),
                    "X-RateLimit-Remaining": "0",
                }
            )
        
        response = await handler(request)
        
        response.headers['X-RateLimit-Limit'] = str(state.get('limit', 0))
        response.headers['X-RateLimit-Remaining'] = str(state.get('remaining', 0))
        
        return response
    
    return middleware

def rate_limit(
    limiter: Any,
    key_func: Optional[KeyGeneratorFunc] = None
) -> Callable:
    if key_func is None:
        key_func = by_ip()
    
    def decorator(handler: Callable) -> Callable:
        async def wrapper(request):
            key = key_func(request)
            
            allowed, state = limiter.check(key)
            
            if not allowed:
                retry_after = state.get('retry_after', 0)
                return web.json_response(
                    {
                        "error": "Rate limit exceeded",
                        "limit": state.get('limit', 0),
                        "remaining": 0,
                        "retry_after": retry_after
                    },
                    status=429,
                    headers={
                        "Retry-After": str(int(retry_after)),
                        "X-RateLimit-Limit": str(state.get('limit', 0)),
                        "X-RateLimit-Remaining": "0",
                    }
                )
            
            return await handler(request)
        
        return wrapper
    
    return decorator

class AIOHTTPRateLimiter:
    def __init__(
        self,
        limiter: Any,
        key_func: Optional[KeyGeneratorFunc] = None,
        skip_paths: Optional[set] = None
    ):
        self.limiter = limiter
        self.key_func = key_func or by_ip()
        self.skip_paths = skip_paths or set()
    
    @property
    def middleware(self):
        return aiohttp_rate_limit_middleware(
            self.limiter,
            key_func=self.key_func,
            skip_paths=self.skip_paths
        )
    
    def limit(self, key_func: Optional[KeyGeneratorFunc] = None) -> Callable:
        actual_key_func = key_func or self.key_func
        return rate_limit(self.limiter, key_func=actual_key_func)
    
    def skip(self, path: str):
        self.skip_paths.add(path)
    
    def exempt(self, handler: Callable) -> Callable:
        handler._rate_limit_exempt = True
        return handler

async def error_handler(request, exc):
    if isinstance(exc, RateLimitExceeded):
        return web.json_response(
            {
                "error": "Rate limit exceeded",
                "retry_after": exc.retry_after
            },
            status=429,
            headers={"Retry-After": str(int(exc.retry_after))}
        )
    raise exc

class RateLimitExceeded(Exception):    
    def __init__(self, state: dict):
        self.state = state
        self.retry_after = state.get('retry_after', 0)
        self.limit = state.get('limit', 0)
        self.remaining = state.get('remaining', 0)
        super().__init__(f"Rate limit exceeded. Retry after {self.retry_after}s")