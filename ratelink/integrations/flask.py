import functools
from typing import Any, Callable, Optional, Union
from flask import Flask, jsonify, make_response, request as flask_request
from ratelink.utils.key_generators import KeyGeneratorFunc, by_ip

def parse_rate_limit_string(rate_string: str) -> tuple:
    rate_string = rate_string.lower().strip()
    
    if '/' in rate_string:
        parts = rate_string.split('/')
        limit = int(parts[0].strip())
        period = parts[1].strip()
    elif ' per ' in rate_string:
        parts = rate_string.split(' per ')
        limit = int(parts[0].strip())
        period = parts[1].strip()
    else:
        raise ValueError(f"Invalid rate limit format: {rate_string}")
    
    period_map = {
        'second': 1,
        'seconds': 1,
        'minute': 60,
        'minutes': 60,
        'hour': 3600,
        'hours': 3600,
        'day': 86400,
        'days': 86400,
    }
    
    window = period_map.get(period)
    if window is None:
        raise ValueError(f"Unknown period: {period}")
    
    return limit, window


class FlaskRateLimiter:
    def __init__(
        self,
        app: Optional[Flask] = None,
        limiter: Optional[Any] = None,
        key_func: Optional[KeyGeneratorFunc] = None,
        default_limits: Optional[list] = None
    ):
        self.limiter = limiter
        self.key_func = key_func or by_ip()
        self.default_limits = default_limits or []
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        self.app = app
        
        if self.default_limits:
            @app.before_request
            def check_global_limits():
                key = self.key_func(flask_request)
                
                for limit_str in self.default_limits:
                    limit, window = parse_rate_limit_string(limit_str)
                    state = self.limiter.check(key)
                    
                    if state.violated:
                        return self._make_error_response(state)
                
                return None
    
    def limit(
        self,
        limit_value: Union[str, int],
        key_func: Optional[KeyGeneratorFunc] = None,
        per_method: bool = False
    ) -> Callable:
        if isinstance(limit_value, str):
            limit, window = parse_rate_limit_string(limit_value)
        else:
            limit = limit_value
            window = None
        
        key_function = key_func or self.key_func
        
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                key = key_function(flask_request)
                if per_method:
                    key = f"{key}:{flask_request.method}"
                state = self.limiter.check(key)
                if state.violated:
                    return self._make_error_response(state)
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def _make_error_response(self, state):
        retry_after = state.retry_after
        
        response = make_response(
            jsonify({
                "error": "Rate limit exceeded",
                "limit": state.limit,
                "remaining": 0,
                "retry_after": retry_after
            }),
            429
        )
        
        response.headers['Retry-After'] = str(int(retry_after))
        response.headers['X-RateLimit-Limit'] = str(state.limit)
        response.headers['X-RateLimit-Remaining'] = '0'
        
        return response
    
    def exempt(self, func: Callable) -> Callable:
        func._rate_limit_exempt = True
        return func
    
    def reset(self, key: str):
        if hasattr(self.limiter, 'reset'):
            self.limiter.reset(key)


def flask_rate_limit(
    limit_value: Union[str, int],
    limiter: Any,
    key_func: Optional[KeyGeneratorFunc] = None
) -> Callable:
    if isinstance(limit_value, str):
        limit, window = parse_rate_limit_string(limit_value)
    else:
        limit = limit_value
        window = None
    
    if key_func is None:
        key_func = by_ip()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = key_func(flask_request)
            allowed, state = limiter.check(key)
            
            if not allowed:
                retry_after = state.get('retry_after', 0)
                response = make_response(
                    jsonify({
                        "error": "Rate limit exceeded",
                        "retry_after": retry_after
                    }),
                    429
                )
                response.headers['Retry-After'] = str(int(retry_after))
                return response
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator