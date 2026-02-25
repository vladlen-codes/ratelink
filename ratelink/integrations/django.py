import functools
from typing import Any, Callable, Optional
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string
from ratelink.utils.key_generators import KeyGeneratorFunc, by_ip

class DjangoRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
        config = getattr(settings, 'RATE_LIMITING', {})
        
        default = config.get('DEFAULT', {})
        self.default_limit = default.get('limit')
        self.default_window = default.get('window')
        
        key_func_path = config.get('KEY_FUNC')
        if key_func_path:
            self.key_func = import_string(key_func_path)()
        else:
            self.key_func = by_ip()
        
        self.skip_paths = set(config.get('SKIP_PATHS', []))
        
        limiter_path = config.get('LIMITER')
        if limiter_path:
            self.limiter = import_string(limiter_path)
        else:
            try:
                from myapp.rate_limiter import limiter
                self.limiter = limiter
            except ImportError:
                self.limiter = None
    
    def __call__(self, request):
        if self.limiter is None:
            return self.get_response(request)
        
        if request.path in self.skip_paths:
            return self.get_response(request)
        
        if hasattr(request, 'resolver_match') and request.resolver_match:
            func = request.resolver_match.func
            if hasattr(func, '_rate_limit_exempt'):
                return self.get_response(request)
        
        key = self.key_func(request)
        
        state = self.limiter.check(key)
        
        if state.violated:
            return self._make_error_response(state)
        
        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(state.limit)
        response['X-RateLimit-Remaining'] = str(state.remaining)
        
        return response
    
    def _make_error_response(self, state) -> JsonResponse:
        retry_after = state.retry_after
        
        response = JsonResponse({
            "error": "Rate limit exceeded",
            "limit": state.limit,
            "remaining": 0,
            "retry_after": retry_after
        }, status=429)
        
        response['Retry-After'] = str(int(retry_after))
        response['X-RateLimit-Limit'] = str(state.limit)
        response['X-RateLimit-Remaining'] = '0'
        
        return response


def django_rate_limit(
    limiter: Any = None,
    limit: Optional[int] = None,
    window: Optional[int] = None,
    key_func: Optional[KeyGeneratorFunc] = None
) -> Callable:
    if key_func is None:
        key_func = by_ip()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            actual_limiter = limiter
            if actual_limiter is None:
                try:
                    from myapp.rate_limiter import limiter as global_limiter
                    actual_limiter = global_limiter
                except ImportError:
                    # No limiter available, skip
                    return func(request, *args, **kwargs)
            
            key = key_func(request)
            
            state = actual_limiter.check(key)
            
            if state.violated:
                retry_after = state.retry_after
                response = JsonResponse({
                    "error": "Rate limit exceeded",
                    "limit": state.limit,
                    "remaining": 0,
                    "retry_after": retry_after
                }, status=429)
                
                response['Retry-After'] = str(int(retry_after))
                response['X-RateLimit-Limit'] = str(state.limit)
                response['X-RateLimit-Remaining'] = '0'
                
                return response
            
            return func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator


def rate_limit_exempt(func: Callable) -> Callable:
    func._rate_limit_exempt = True
    return func


class RateLimitMixin:
    rate_limit_limiter = None
    rate_limit_key_func = None
    rate_limit = None
    rate_window = None
    
    @method_decorator(django_rate_limit)
    def dispatch(self, request, *args, **kwargs):
        if self.rate_limit_limiter:
            key_func = self.rate_limit_key_func or by_ip()
            key = key_func(request)
            
            allowed, state = self.rate_limit_limiter.check(key)
            
            if not allowed:
                retry_after = state.get('retry_after', 0)
                response = JsonResponse({
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after
                }, status=429)
                response['Retry-After'] = str(int(retry_after))
                return response
        
        return super().dispatch(request, *args, **kwargs)


def get_rate_limiter_from_settings():
    config = getattr(settings, 'RATE_LIMITING', {})
    limiter_path = config.get('LIMITER')
    
    if limiter_path:
        return import_string(limiter_path)
    
    return None