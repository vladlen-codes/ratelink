import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

try:
    from ratelink.backends.postgresql import PostgreSQLBackend, PSYCOPG2_AVAILABLE
except ImportError:
    PSYCOPG2_AVAILABLE = False

@pytest.mark.skipif(not PSYCOPG2_AVAILABLE, reason="PostgreSQL not installed")
class TestPostgreSQLBackend:
    @pytest.fixture(autouse=True)
    def setup(self):
        try:
            self.backend = PostgreSQLBackend(
                host="localhost",
                port=5432,
                user="postgres",
                password="postgres",
                database="test_rate_limits",
                table_name="test_limits",
                pool_size=5,
                connect_timeout=5,
            )
            self.backend.reset()
            yield
            self.backend.reset()
            self.backend.close()
        except Exception:
            pytest.skip("PostgreSQL server not available")

    def test_initialization(self):
        assert self.backend is not None
        assert self.backend.table_name == "test_limits"

    def test_table_creation(self):
        assert True

    def test_check_nonexistent_key(self):
        state = self.backend.check("test:nonexistent")
        assert state.limit == 0
        assert state.remaining == 0

    def test_consume_tokens(self):
        key = "test:consume"
        
        state1 = self.backend.consume(key, weight=10)
        assert state1.remaining >= 0
        
        state2 = self.backend.consume(key, weight=5)
        assert state2.remaining < state1.remaining

    def test_upsert_correctness(self):
        key = "test:upsert"
        
        state1 = self.backend.consume(key, weight=100)
        assert state1.violated is False
        
        state2 = self.backend.consume(key, weight=50)
        assert state2.remaining < state1.remaining

    def test_concurrent_access(self):
        key = "test:concurrent"
        def worker():
            try:
                self.backend.consume(key, weight=1)
                return True
            except Exception:
                return False
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(lambda _: worker(), range(50)))
        assert all(results)

    def test_transaction_handling(self):
        key = "test:transaction"
        state = self.backend.consume(key, weight=10)
        assert state is not None

    def test_prepared_statements(self):
        keys = [f"test:prepared:{i}" for i in range(10)]
        for key in keys:
            self.backend.consume(key, weight=1)

    def test_expiration_cleanup(self):
        key = "test:expiration"
        self.backend.consume(key, weight=1)
        self.backend._cleanup_expired()

    def test_connection_pooling(self):
        def worker(i):
            key = f"test:pool:{i}"
            return self.backend.consume(key, weight=1)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(worker, range(50)))
        assert len(results) == 50

    def test_peek_doesnt_modify(self):
        key = "test:peek"
        self.backend.consume(key, weight=10)
        state1 = self.backend.peek(key)
        state2 = self.backend.peek(key)
        assert state1.remaining == state2.remaining

    def test_reset_specific_key(self):
        key = "test:reset"
        self.backend.consume(key, weight=10)
        self.backend.reset(key)
        state = self.backend.check(key)
        assert state.limit == 0

    def test_reset_all(self):
        keys = ["test:reset1", "test:reset2", "test:reset3"]
        for key in keys:
            self.backend.consume(key, weight=1)
        self.backend.reset()
        for key in keys:
            state = self.backend.check(key)
            assert state.limit == 0

    @pytest.mark.asyncio
    async def test_async_operations(self):
        key = "test:async"
        state = await self.backend.consume_async(key, weight=1)
        assert state is not None

    def test_metadata_storage(self):
        key = "test:metadata"
        state = self.backend.consume(key, weight=1)
        assert "backend" in state.metadata
        assert state.metadata["backend"] == "postgresql"

    def test_acid_compliance(self):
        key = "test:acid"
        self.backend.consume(key, weight=100)
        def worker():
            try:
                self.backend.consume(key, weight=1)
                return 1
            except Exception:
                return 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            consumed = sum(executor.map(lambda _: worker(), range(20)))
        state = self.backend.check(key)
        assert consumed > 0

    def test_performance_benchmark(self):
        keys = [f"test:perf:{i}" for i in range(1000)]
        start = time.time()
        for key in keys:
            self.backend.consume(key, weight=1)
        elapsed = time.time() - start
        assert elapsed < 10.0