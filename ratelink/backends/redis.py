import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from ..core.abstractions import Backend
from ..core.types import RateLimitState
from ..core.types import BackendError

try:
    import redis
    from redis.connection import ConnectionPool
    from redis.cluster import RedisCluster
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
try:
    import aioredis
    AIOREDIS_AVAILABLE = True
except ImportError:
    AIOREDIS_AVAILABLE = False

CONSUME_SCRIPT = """
local key = KEYS[1]
local weight = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local current_time = tonumber(ARGV[4])

local current = redis.call('GET', key)

if current == false then
    -- Initialize new key
    local remaining = limit - weight
    if remaining >= 0 then
        redis.call('SET', key, remaining)
        redis.call('EXPIRE', key, ttl)
        return {remaining, current_time + ttl, 1}  -- success
    else
        return {limit, current_time + ttl, 0}  -- denied
    end
else
    -- Update existing key
    local remaining = tonumber(current) - weight
    if remaining >= 0 then
        redis.call('DECRBY', key, weight)
        local key_ttl = redis.call('TTL', key)
        return {remaining, current_time + key_ttl, 1}  -- success
    else
        local key_ttl = redis.call('TTL', key)
        return {tonumber(current), current_time + key_ttl, 0}  -- denied
    end
end
"""


class RedisBackend(Backend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ssl: bool = False,
        cluster_mode: bool = False,
        startup_nodes: Optional[List[Dict[str, Any]]] = None,
        connection_pool_size: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        max_connections: int = 50,
        default_ttl: int = 3600,
    ) -> None:
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis library not installed. Install with: pip install redis"
            )
        self.default_ttl = default_ttl
        self.cluster_mode = cluster_mode
        if cluster_mode:
            if not startup_nodes:
                raise ValueError("startup_nodes required for cluster_mode")
            self.client = RedisCluster(
                startup_nodes=startup_nodes,
                decode_responses=False,
                skip_full_coverage_check=True,
                socket_timeout=socket_timeout,
                socket_connect_timeout=socket_connect_timeout,
                retry_on_timeout=retry_on_timeout,
                max_connections=max_connections,
            )
        else:
            pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                ssl=ssl,
                max_connections=max_connections,
                socket_timeout=socket_timeout,
                socket_connect_timeout=socket_connect_timeout,
                retry_on_timeout=retry_on_timeout,
                decode_responses=False,
            )
            self.client = redis.Redis(connection_pool=pool)
        self.consume_script = self.client.register_script(CONSUME_SCRIPT)
        try:
            self.client.ping()
        except Exception as e:
            raise BackendError(f"Failed to connect to Redis: {e}")

    def _build_key(self, key: str) -> str:
        return f"ratelimit:{key}"

    def check(self, key: str) -> RateLimitState:
        try:
            redis_key = self._build_key(key)
            pipe = self.client.pipeline()
            pipe.get(redis_key)
            pipe.ttl(redis_key)
            results = pipe.execute()
            current = results[0]
            ttl = results[1]
            if current is None:
                current_time = time.time()
                return RateLimitState(
                    limit=0,
                    remaining=0,
                    reset_at=datetime.fromtimestamp(current_time + self.default_ttl),
                    retry_after=0.0,
                    violated=False,
                    metadata={"backend": "redis"},
                )
            remaining = int(current)
            current_time = time.time()
            if ttl < 0:
                ttl = self.default_ttl
            reset_at = datetime.fromtimestamp(current_time + ttl)
            return RateLimitState(
                limit=remaining,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=0.0 if remaining > 0 else float(ttl),
                violated=remaining <= 0,
                metadata={"backend": "redis", "ttl": ttl},
            )
        except Exception as e:
            raise BackendError(f"Redis check failed: {e}")

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")
        try:
            redis_key = self._build_key(key)
            current_time = time.time()
            result = self.consume_script(
                keys=[redis_key],
                args=[weight, 1000000, self.default_ttl, int(current_time)],
            )
            remaining = int(result[0])
            reset_timestamp = float(result[1])
            allowed = bool(result[2])
            reset_at = datetime.fromtimestamp(reset_timestamp)
            retry_after = 0.0 if allowed else (reset_timestamp - current_time)
            return RateLimitState(
                limit=1000000,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=max(0.0, retry_after),
                violated=not allowed,
                metadata={"backend": "redis", "atomic": True},
            )
        except Exception as e:
            raise BackendError(f"Redis consume failed: {e}")

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        try:
            if key is None:
                cursor = 0
                pattern = self._build_key("*")
                while True:
                    cursor, keys = self.client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    if keys:
                        self.client.delete(*keys)
                    if cursor == 0:
                        break
            else:
                redis_key = self._build_key(key)
                self.client.delete(redis_key)
        except Exception as e:
            raise BackendError(f"Redis reset failed: {e}")

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)

    def health_check(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass