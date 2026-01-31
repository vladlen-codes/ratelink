# File: src/universal_rate_limiter/backends/postgresql.py
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..core.abstractions import Backend
from ..core.types import RateLimitState
from ..core.types import BackendError

try:
    import psycopg2
    from psycopg2 import pool, extras
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False


class PostgreSQLBackend(Backend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        database: str = "postgres",
        table_name: str = "rate_limits",
        pool_size: int = 10,
        max_overflow: int = 20,
        ssl_mode: str = "prefer",
        connect_timeout: int = 10,
        auto_create_table: bool = True,
        cleanup_interval: int = 3600,
    ) -> None:
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 not installed. Install with: pip install psycopg2-binary"
            )

        self.table_name = table_name
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=pool_size,
                maxconn=pool_size + max_overflow,
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                sslmode=ssl_mode,
                connect_timeout=connect_timeout,
            )
        except Exception as e:
            raise BackendError(f"Failed to create PostgreSQL pool: {e}")
        if auto_create_table:
            self._create_table()
        conn = self.pool.getconn()
        try:
            conn.cursor().execute("SELECT 1")
        except Exception as e:
            raise BackendError(f"PostgreSQL health check failed: {e}")
        finally:
            self.pool.putconn(conn)

    def _create_table(self) -> None:
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    key VARCHAR(255) PRIMARY KEY,
                    limit_value INTEGER NOT NULL,
                    remaining INTEGER NOT NULL,
                    reset_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB,
                    
                    CONSTRAINT remaining_valid CHECK (remaining >= 0),
                    CONSTRAINT limit_positive CHECK (limit_value > 0)
                )
            """)
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_reset_at 
                ON {self.table_name}(reset_at)
            """)

            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated_at 
                ON {self.table_name}(updated_at)
            """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise BackendError(f"Failed to create table: {e}")
        finally:
            self.pool.putconn(conn)

    def _cleanup_expired(self) -> None:
        current_time = time.time()
        if current_time - self._last_cleanup < self.cleanup_interval:
            return
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {self.table_name} WHERE reset_at < CURRENT_TIMESTAMP"
            )
            conn.commit()
            self._last_cleanup = current_time
        except Exception:
            conn.rollback()
        finally:
            self.pool.putconn(conn)

    def check(self, key: str) -> RateLimitState:
        self._cleanup_expired()
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
            cursor.execute(
                f"""
                SELECT limit_value, remaining, reset_at, metadata
                FROM {self.table_name}
                WHERE key = %s AND reset_at > CURRENT_TIMESTAMP
                """,
                (key,),
            )
            row = cursor.fetchone()
            if row is None:
                return RateLimitState(
                    limit=0,
                    remaining=0,
                    reset_at=datetime.now(),
                    retry_after=0.0,
                    violated=False,
                    metadata={"backend": "postgresql"},
                )
            reset_at = row["reset_at"]
            remaining = row["remaining"]
            retry_after = 0.0
            if remaining <= 0:
                retry_after = (reset_at - datetime.now()).total_seconds()
            return RateLimitState(
                limit=row["limit_value"],
                remaining=remaining,
                reset_at=reset_at,
                retry_after=max(0.0, retry_after),
                violated=remaining <= 0,
                metadata=row["metadata"] or {"backend": "postgresql"},
            )
        except Exception as e:
            raise BackendError(f"PostgreSQL check failed: {e}")
        finally:
            self.pool.putconn(conn)

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")
        self._cleanup_expired()
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
            cursor.execute(
                f"""
                UPDATE {self.table_name}
                SET remaining = remaining - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE key = %s 
                    AND reset_at > CURRENT_TIMESTAMP
                    AND remaining >= %s
                RETURNING limit_value, remaining, reset_at, metadata
                """,
                (weight, key, weight),
            )
            row = cursor.fetchone()
            if row is not None:
                conn.commit()
                return RateLimitState(
                    limit=row["limit_value"],
                    remaining=row["remaining"],
                    reset_at=row["reset_at"],
                    retry_after=0.0,
                    violated=False,
                    metadata=row["metadata"] or {"backend": "postgresql"},
                )
            else:
                cursor.execute(
                    f"""
                    SELECT limit_value, remaining, reset_at, metadata
                    FROM {self.table_name}
                    WHERE key = %s AND reset_at > CURRENT_TIMESTAMP
                    """,
                    (key,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    reset_at = existing["reset_at"]
                    retry_after = (reset_at - datetime.now()).total_seconds()
                    return RateLimitState(
                        limit=existing["limit_value"],
                        remaining=existing["remaining"],
                        reset_at=reset_at,
                        retry_after=max(0.0, retry_after),
                        violated=True,
                        metadata=existing["metadata"] or {"backend": "postgresql"},
                    )
                else:
                    limit_value = 10000  # Default limit
                    remaining = limit_value - weight
                    reset_at = datetime.now() + timedelta(seconds=3600)
                    cursor.execute(
                        f"""
                        INSERT INTO {self.table_name} 
                        (key, limit_value, remaining, reset_at, metadata)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        (
                            key,
                            limit_value,
                            remaining,
                            reset_at,
                            json.dumps({"backend": "postgresql"}),
                        ),
                    )
                    conn.commit()
                    return RateLimitState(
                        limit=limit_value,
                        remaining=remaining,
                        reset_at=reset_at,
                        retry_after=0.0,
                        violated=False,
                        metadata={"backend": "postgresql"},
                    )
        except Exception as e:
            conn.rollback()
            raise BackendError(f"PostgreSQL consume failed: {e}")
        finally:
            self.pool.putconn(conn)

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor()
            if key is None:
                cursor.execute(f"TRUNCATE TABLE {self.table_name}")
            else:
                cursor.execute(f"DELETE FROM {self.table_name} WHERE key = %s", (key,))
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise BackendError(f"PostgreSQL reset failed: {e}")
        finally:
            self.pool.putconn(conn)

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)

    def close(self) -> None:
        try:
            self.pool.closeall()
        except Exception:
            pass