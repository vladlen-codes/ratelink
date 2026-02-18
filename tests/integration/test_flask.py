import pytest

try:
    from flask import Flask
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

if FLASK_AVAILABLE:
    from ratelink.integration.flask import (
        FlaskRateLimiter,
        flask_rate_limit,
        parse_rate_limit_string,
    )
    from ratelink.utils.key_generators import by_ip, by_route

from mock_limiter import MockRateLimiter


class TestParseRateLimitString:
    def test_parse_per_minute(self):
        limit, window = parse_rate_limit_string("100 per minute")
        assert limit == 100
        assert window == 60
    
    def test_parse_slash_format(self):
        limit, window = parse_rate_limit_string("100/minute")
        assert limit == 100
        assert window == 60
    
    def test_parse_per_hour(self):
        limit, window = parse_rate_limit_string("1000 per hour")
        assert limit == 1000
        assert window == 3600
    
    def test_parse_per_day(self):
        limit, window = parse_rate_limit_string("10000 per day")
        assert limit == 10000
        assert window == 86400
    
    def test_parse_per_second(self):
        limit, window = parse_rate_limit_string("10 per second")
        assert limit == 10
        assert window == 1
    
    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_rate_limit_string("invalid")
    
    def test_unknown_period_raises(self):
        with pytest.raises(ValueError):
            parse_rate_limit_string("100 per week")


@pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask not installed")
class TestFlaskRateLimiter:    
    def test_extension_initialization(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=True)
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        assert flask_limiter.limiter == limiter
        assert flask_limiter.app == app
    
    def test_limit_decorator_allows_request(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=True)
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/test")
        @flask_limiter.limit("100 per minute")
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 200
    
    def test_limit_decorator_blocks_request(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=False)
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/test")
        @flask_limiter.limit("100 per minute")
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 429
            assert b"Rate limit exceeded" in response.data
    
    def test_custom_key_function(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=True)
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/test")
        @flask_limiter.limit("100 per minute", key_func=by_route())
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert len(limiter.check_calls) > 0
            assert "route:" in limiter.check_calls[0][0]
    
    def test_per_method_limiting(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=True)
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/test", methods=['GET', 'POST'])
        @flask_limiter.limit("100 per minute", per_method=True)
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            limiter.reset()
            client.get("/test")
            get_key = limiter.check_calls[0][0]
            
            limiter.reset()
            client.post("/test")
            post_key = limiter.check_calls[0][0]
            
            assert get_key != post_key
            assert ":GET" in get_key or "GET" in get_key
            assert ":POST" in post_key or "POST" in post_key
    
    def test_exempt_decorator(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=False)
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/limited")
        @flask_limiter.limit("100 per minute")
        def limited_route():
            return {"status": "ok"}
        
        @app.route("/exempt")
        @flask_limiter.exempt
        def exempt_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/limited")
            assert response.status_code == 429
            
            response = client.get("/exempt")
            assert response.status_code == 200
    
    def test_retry_after_header(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=False, state={
            'allowed': False,
            'remaining': 0,
            'limit': 100,
            'retry_after': 30.0
        })
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/test")
        @flask_limiter.limit("100 per minute")
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert response.headers["Retry-After"] == "30"
    
    def test_rate_limit_headers(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=False, state={
            'allowed': False,
            'remaining': 0,
            'limit': 100,
            'retry_after': 30.0
        })
        flask_limiter = FlaskRateLimiter(app, limiter)
        
        @app.route("/test")
        @flask_limiter.limit("100 per minute")
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert response.headers["X-RateLimit-Limit"] == "100"
            assert response.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask not installed")
class TestFlaskStandaloneDecorator:
    def test_standalone_decorator_allows(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=True)
        
        @app.route("/test")
        @flask_rate_limit("100 per minute", limiter)
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 200
    
    def test_standalone_decorator_blocks(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=False)
        
        @app.route("/test")
        @flask_rate_limit("100 per minute", limiter)
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 429
    
    def test_standalone_with_custom_key(self):
        app = Flask(__name__)
        limiter = MockRateLimiter(should_allow=True)
        
        @app.route("/test")
        @flask_rate_limit("100 per minute", limiter, key_func=by_route())
        def test_route():
            return {"status": "ok"}
        
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert len(limiter.check_calls) > 0