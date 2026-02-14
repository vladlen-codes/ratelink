from typing import Any, Callable, List, Optional

KeyGeneratorFunc = Callable[[Any], str]

def by_ip() -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        if hasattr(request, 'client') and hasattr(request.client, 'host'):
            return f"ip:{request.client.host}"
        
        if hasattr(request, 'remote_addr'):
            return f"ip:{request.remote_addr}"
        
        if hasattr(request, 'META'):
            xff = request.META.get('HTTP_X_FORWARDED_FOR')
            if xff:
                ip = xff.split(',')[0].strip()
                return f"ip:{ip}"
            return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
        
        if hasattr(request, 'remote'):
            return f"ip:{request.remote}"
        
        return "ip:unknown"
    
    return get_key

def by_user_id(user_attr: str = "user") -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        user = getattr(request, user_attr, None)
        
        if user is None:
            return "user:anonymous"
        
        user_id = None
        for attr in ['id', 'pk', 'user_id', 'username']:
            if hasattr(user, attr):
                user_id = getattr(user, attr)
                break
        
        if callable(user):
            user = user()
            for attr in ['id', 'pk', 'username']:
                if hasattr(user, attr):
                    user_id = getattr(user, attr)
                    break
        
        if user_id is None:
            user_id = str(user)
        
        return f"user:{user_id}"
    
    return get_key


def by_api_key(header_name: str = "X-API-Key") -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        if hasattr(request, 'headers'):
            api_key = request.headers.get(header_name)
            if api_key:
                return f"apikey:{api_key}"
        
        if hasattr(request, 'META'):
            meta_key = f"HTTP_{header_name.upper().replace('-', '_')}"
            api_key = request.META.get(meta_key)
            if api_key:
                return f"apikey:{api_key}"
        
        return "apikey:missing"
    
    return get_key

def by_route() -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        if hasattr(request, 'url') and hasattr(request.url, 'path'):
            return f"route:{request.url.path}"
        
        if hasattr(request, 'path'):
            return f"route:{request.path}"
        
        if hasattr(request, 'path'):
            return f"route:{request.path}"
        
        if hasattr(request, 'path'):
            return f"route:{request.path}"
        
        return "route:unknown"
    
    return get_key

def by_endpoint() -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        if hasattr(request, 'scope'):
            endpoint = request.scope.get('endpoint')
            if endpoint:
                name = getattr(endpoint, '__name__', str(endpoint))
                return f"endpoint:{name}"
            route = request.scope.get('route')
            if route and hasattr(route, 'name'):
                return f"endpoint:{route.name}"
        
        if hasattr(request, 'endpoint'):
            return f"endpoint:{request.endpoint}"
        
        if hasattr(request, 'resolver_match'):
            match = request.resolver_match
            if match:
                return f"endpoint:{match.url_name or match.view_name}"
        
        return "endpoint:unknown"
    
    return get_key


def composite_key(*funcs: KeyGeneratorFunc) -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        parts = []
        for func in funcs:
            part = func(request)
            parts.append(part)
        return ":".join(parts)
    
    return get_key

def by_session(session_key: str = "session_id") -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        if hasattr(request, 'session'):
            session = request.session
            if hasattr(session, 'get'):
                session_id = session.get(session_key)
                if session_id:
                    return f"session:{session_id}"
            if hasattr(session, 'session_key'):
                return f"session:{session.session_key}"
        
        if hasattr(request, 'cookies'):
            session_id = request.cookies.get(session_key)
            if session_id:
                return f"session:{session_id}"
        
        return "session:unknown"
    
    return get_key

def custom_key(extractor: Callable[[Any], str], prefix: str = "custom") -> KeyGeneratorFunc:
    def get_key(request: Any) -> str:
        value = extractor(request)
        return f"{prefix}:{value}"
    
    return get_key