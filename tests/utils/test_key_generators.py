import pytest

from ratelink.utils.key_generators import (
    by_api_key,
    by_endpoint,
    by_ip,
    by_route,
    by_session,
    by_user_id,
    composite_key,
    custom_key,
)


class FakeRequest:    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeClient:    
    def __init__(self, host):
        self.host = host


class FakeURL:    
    def __init__(self, path):
        self.path = path


class FakeUser:    
    def __init__(self, id=None, username=None):
        self.id = id
        self.username = username


class TestByIP:    
    def test_fastapi_request(self):
        request = FakeRequest(client=FakeClient("192.168.1.1"))
        key_gen = by_ip()
        
        assert key_gen(request) == "ip:192.168.1.1"
    
    def test_flask_request(self):
        request = FakeRequest(remote_addr="10.0.0.1")
        key_gen = by_ip()
        
        assert key_gen(request) == "ip:10.0.0.1"
    
    def test_django_request(self):
        request = FakeRequest(META={"REMOTE_ADDR": "172.16.0.1"})
        key_gen = by_ip()
        
        assert key_gen(request) == "ip:172.16.0.1"
    
    def test_django_request_with_proxy(self):
        request = FakeRequest(
            META={
                "HTTP_X_FORWARDED_FOR": "203.0.113.1, 198.51.100.1",
                "REMOTE_ADDR": "172.16.0.1"
            }
        )
        key_gen = by_ip()
        
        assert key_gen(request) == "ip:203.0.113.1"
    
    def test_aiohttp_request(self):
        request = FakeRequest(remote="192.0.2.1")
        key_gen = by_ip()
        
        assert key_gen(request) == "ip:192.0.2.1"
    
    def test_unknown_request_type(self):
        request = FakeRequest()
        key_gen = by_ip()
        
        assert key_gen(request) == "ip:unknown"


class TestByUserID:
    
    def test_user_with_id(self):
        request = FakeRequest(user=FakeUser(id=123))
        key_gen = by_user_id()
        
        assert key_gen(request) == "user:123"
    
    def test_user_with_username(self):
        user = FakeUser(username="alice")
        delattr(user, 'id')
        request = FakeRequest(user=user)
        key_gen = by_user_id()
        
        assert key_gen(request) == "user:alice"
    
    def test_no_user(self):
        request = FakeRequest()
        key_gen = by_user_id()
        
        assert key_gen(request) == "user:anonymous"
    
    def test_custom_user_attr(self):
        request = FakeRequest(current_user=FakeUser(id=456))
        key_gen = by_user_id(user_attr="current_user")
        
        assert key_gen(request) == "user:456"


class TestByAPIKey:
    
    def test_fastapi_request(self):
        request = FakeRequest(headers={"X-API-Key": "abc123"})
        key_gen = by_api_key()
        
        assert key_gen(request) == "apikey:abc123"
    
    def test_django_request(self):
        request = FakeRequest(META={"HTTP_X_API_KEY": "xyz789"})
        key_gen = by_api_key()
        
        assert key_gen(request) == "apikey:xyz789"
    
    def test_custom_header_name(self):
        request = FakeRequest(headers={"Authorization": "Bearer token123"})
        key_gen = by_api_key(header_name="Authorization")
        
        assert key_gen(request) == "apikey:Bearer token123"
    
    def test_missing_api_key(self):
        request = FakeRequest(headers={})
        key_gen = by_api_key()
        
        assert key_gen(request) == "apikey:missing"


class TestByRoute:
    
    def test_fastapi_request(self):
        request = FakeRequest(url=FakeURL("/api/users"))
        key_gen = by_route()
        
        assert key_gen(request) == "route:/api/users"
    
    def test_flask_request(self):
        request = FakeRequest(path="/api/posts")
        key_gen = by_route()
        
        assert key_gen(request) == "route:/api/posts"
    
    def test_django_request(self):
        request = FakeRequest(path="/admin/users/")
        key_gen = by_route()
        
        assert key_gen(request) == "route:/admin/users/"


class TestByEndpoint:
    
    def test_flask_request(self):
        request = FakeRequest(endpoint="api.get_users")
        key_gen = by_endpoint()
        
        assert key_gen(request) == "endpoint:api.get_users"
    
    def test_unknown_request(self):
        request = FakeRequest()
        key_gen = by_endpoint()
        
        assert key_gen(request) == "endpoint:unknown"


class TestCompositeKey:
    
    def test_combine_ip_and_route(self):
        request = FakeRequest(
            client=FakeClient("192.168.1.1"),
            url=FakeURL("/api/data")
        )
        key_gen = composite_key(by_ip(), by_route())
        
        assert key_gen(request) == "ip:192.168.1.1:route:/api/data"
    
    def test_combine_multiple_keys(self):
        request = FakeRequest(
            user=FakeUser(id=123),
            path="/api/search",
            headers={"X-API-Key": "abc"}
        )
        key_gen = composite_key(by_user_id(), by_route(), by_api_key())
        
        result = key_gen(request)
        assert "user:123" in result
        assert "route:/api/search" in result
        assert "apikey:abc" in result


class TestBySession:
    
    def test_flask_request(self):
        class FakeSession(dict):
            session_key = "session123"
        
        request = FakeRequest(session=FakeSession({"session_id": "abc123"}))
        key_gen = by_session()
        
        assert key_gen(request) == "session:session123"
    
    def test_cookie_based_session(self):
        request = FakeRequest(cookies={"session_id": "cookie123"})
        key_gen = by_session()
        
        assert key_gen(request) == "session:cookie123"
    
    def test_no_session(self):
        request = FakeRequest()
        key_gen = by_session()
        
        assert key_gen(request) == "session:unknown"


class TestCustomKey:
    
    def test_custom_extractor(self):
        def get_org_id(request):
            return request.headers.get("X-Org-Id", "default")
        
        request = FakeRequest(headers={"X-Org-Id": "org-123"})
        key_gen = custom_key(get_org_id, prefix="org")
        
        assert key_gen(request) == "org:org-123"
    
    def test_custom_extractor_with_default(self):
        def get_tenant(request):
            return getattr(request, 'tenant', 'shared')
        
        request = FakeRequest()
        key_gen = custom_key(get_tenant, prefix="tenant")
        
        assert key_gen(request) == "tenant:shared"