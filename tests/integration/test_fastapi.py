import pytest

try:
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from ratelink.integration.fastapi import (
        FastAPIRateLimitMiddleware,
        rate_limit,
    )
    from ratelink.utils.key_generators import by_ip, by_route, composite_key

from mock_limiter import MockRateLimiter

@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestFastAPIMiddleware:    
    def test_middleware_allows_request(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter,
            key_generator=by_ip()
        )
        
        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
    
    def test_middleware_blocks_request(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=False)
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter,
            key_generator=by_ip()
        )
        
        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 429
        assert "error" in response.json()
        assert response.json()["error"] == "Rate limit exceeded"
        assert "Retry-After" in response.headers
    
    def test_middleware_skip_paths(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=False)
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter,
            skip_paths=["/health"]
        )
        
        @app.get("/health")
        async def health():
            return {"status": "healthy"}
        
        @app.get("/api")
        async def api():
            return {"data": []}
        
        client = TestClient(app)
        
        response = client.get("/health")
        assert response.status_code == 200
        
        response = client.get("/api")
        assert response.status_code == 429
    
    def test_middleware_custom_key_generator(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter,
            key_generator=by_route()
        )
        
        @app.get("/endpoint1")
        async def endpoint1():
            return {"n": 1}
        
        @app.get("/endpoint2")
        async def endpoint2():
            return {"n": 2}
        
        client = TestClient(app)
        client.get("/endpoint1")
        client.get("/endpoint2")
        
        assert len(limiter.check_calls) == 2
        key1, key2 = limiter.check_calls[0][0], limiter.check_calls[1][0]
        assert key1 != key2
        assert "route" in key1
        assert "route" in key2

@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestFastAPIDecorator:    
    def test_decorator_allows_request(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        @app.get("/test")
        @rate_limit(limiter, key_generator=by_ip())
        async def test_endpoint(request: Request):
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_decorator_blocks_request(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=False)
        
        @app.get("/test")
        @rate_limit(limiter, key_generator=by_ip())
        async def test_endpoint(request: Request):
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 429
        assert "error" in response.json()
    
    def test_decorator_per_endpoint_limits(self):
        app = FastAPI()
        limiter_strict = MockRateLimiter(should_allow=False)
        limiter_lenient = MockRateLimiter(should_allow=True)
        
        @app.get("/strict")
        @rate_limit(limiter_strict, key_generator=by_ip())
        async def strict_endpoint(request: Request):
            return {"endpoint": "strict"}
        
        @app.get("/lenient")
        @rate_limit(limiter_lenient, key_generator=by_ip())
        async def lenient_endpoint(request: Request):
            return {"endpoint": "lenient"}
        
        client = TestClient(app)
        
        response = client.get("/strict")
        assert response.status_code == 429
        
        response = client.get("/lenient")
        assert response.status_code == 200
    
    def test_decorator_composite_key(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        @app.get("/test")
        @rate_limit(limiter, key_generator=composite_key(by_ip(), by_route()))
        async def test_endpoint(request: Request):
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert len(limiter.check_calls) == 1
        key = limiter.check_calls[0][0]
        assert "ip:" in key
        assert "route:" in key
    
    def test_decorator_without_request(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        @app.get("/test")
        @rate_limit(limiter, key_generator=by_ip())
        async def test_endpoint():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code in [200, 429]
    
    def test_response_headers_on_success(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True, state={
            'allowed': True,
            'remaining': 75,
            'limit': 100,
            'retry_after': 0,
            'reset_after': 45.0
        })
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter
        )
        
        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "75"
    
    def test_retry_after_header_format(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=False, state={
            'allowed': False,
            'remaining': 0,
            'limit': 100,
            'retry_after': 45.7,
        })
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter
        )
        
        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "45"
        assert response.json()["retry_after"] == 45.7


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestFastAPIAsync:    
    def test_async_endpoint_with_decorator(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        @app.get("/async")
        @rate_limit(limiter)
        async def async_endpoint(request: Request):
            return {"async": True}
        
        client = TestClient(app)
        response = client.get("/async")
        
        assert response.status_code == 200
        assert response.json() == {"async": True}
    
    def test_middleware_doesnt_block_async(self):
        app = FastAPI()
        limiter = MockRateLimiter(should_allow=True)
        
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            limiter=limiter
        )
        
        call_order = []
        
        @app.get("/test")
        async def test_endpoint():
            call_order.append("endpoint")
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert "endpoint" in call_order