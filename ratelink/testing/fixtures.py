import pytest
from ratelink.testing.mock import MockRateLimiter, ScriptedBehavior
from ratelink.testing.time_machine import TimeMachine

slow = pytest.mark.slow
integration = pytest.mark.integration
redis_required = pytest.mark.redis_required
postgres_required = pytest.mark.postgres_required

@pytest.fixture
def mock_limiter():
    return MockRateLimiter(mode='always_allow')

@pytest.fixture
def mock_limiter_deny():
    return MockRateLimiter(mode='always_deny')

@pytest.fixture
def scripted_limiter():
    behavior = ScriptedBehavior()
    limiter = MockRateLimiter(mode='scripted', behavior=behavior)
    return limiter, behavior

@pytest.fixture
def time_machine():
    tm = TimeMachine()
    yield tm
    tm.reset()

@pytest.fixture
def frozen_time(time_machine):
    time_machine.freeze()
    return time_machine

@pytest.fixture
def memory_limiter():
    try:
        from ratelink import RateLimiter
        from ratelink.backends.memory import MemoryBackend
        
        backend = MemoryBackend()
        limiter = RateLimiter(
            algorithm="token_bucket",
            limit=100,
            window=60,
            backend=backend
        )
        return limiter
    except ImportError:
        pytest.skip("RateLimiter not available")

@pytest.fixture
@redis_required
def redis_limiter():
    try:
        import redis
        from ratelink import RateLimiter
        from ratelink.backends.redis import RedisBackend
        client = redis.Redis(host='localhost', port=6379, db=0)
        client.ping()
        backend = RedisBackend(client=client)
        limiter = RateLimiter(
            algorithm="token_bucket",
            limit=100,
            window=60,
            backend=backend
        )   
        yield limiter
        client.flushdb()
    except (ImportError, redis.ConnectionError):
        pytest.skip("Redis not available")

@pytest.fixture
@postgres_required
def postgres_limiter():
    try:
        import psycopg2
        from ratelink import RateLimiter
        from ..backends.postgresql import PostgresBackend
        
        conn = psycopg2.connect(
            host='localhost',
            database='ratelink_test',
            user='postgres',
            password='postgres'
        )
        
        backend = PostgresBackend(connection=conn)
        limiter = RateLimiter(
            algorithm="token_bucket",
            limit=100,
            window=60,
            backend=backend
        )
        yield limiter
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE rate_limits")
        conn.commit()
        conn.close()
    except (ImportError, psycopg2.OperationalError):
        pytest.skip("PostgreSQL not available")

@pytest.fixture(params=['memory', 'redis', 'postgres'])
def any_limiter(request):
    backend_type = request.param
    if backend_type == 'memory':
        return request.getfixturevalue('memory_limiter')
    elif backend_type == 'redis':
        return request.getfixturevalue('redis_limiter')
    elif backend_type == 'postgres':
        return request.getfixturevalue('postgres_limiter')

@pytest.fixture
def limiter_with_time(memory_limiter, time_machine):
    time_machine.freeze()
    return memory_limiter, time_machine

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "redis_required: marks tests that require Redis"
    )
    config.addinivalue_line(
        "markers", "postgres_required: marks tests that require PostgreSQL"
    )