import pytest
import time
from datetime import datetime, timedelta

try:
    from ratelink.backends.mongodb import MongoDBBackend, PYMONGO_AVAILABLE
except ImportError:
    PYMONGO_AVAILABLE = False

@pytest.mark.skipif(not PYMONGO_AVAILABLE, reason="MongoDB not installed")
class TestMongoDBBackend:
    @pytest.fixture(autouse=True)
    def setup(self):
        try:
            self.backend = MongoDBBackend(
                connection_string="mongodb://localhost:27017/",
                database="test_rate_limits",
                collection="test_limits",
            )
            self.backend.reset()
            yield
            self.backend.reset()
            self.backend.close()
        except Exception:
            pytest.skip("MongoDB server not available")

    def test_initialization(self):
        assert self.backend is not None
        assert self.backend.collection is not None

    def test_collection_creation(self):
        indexes = list(self.backend.collection.list_indexes())
        assert len(indexes) > 0

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

    def test_ttl_indexes(self):
        key = "test:ttl"
        state = self.backend.consume(key, weight=1)
        assert state.reset_at > datetime.now()

    def test_document_structure(self):
        key = "test:structure"
        self.backend.consume(key, weight=1)
        doc = self.backend.collection.find_one({"key": key})
        assert doc is not None
        assert "key" in doc
        assert "limit_value" in doc
        assert "remaining" in doc
        assert "reset_at" in doc

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
        assert state.metadata["backend"] == "mongodb"

    def test_performance(self):
        keys = [f"test:perf:{i}" for i in range(200)]
        start = time.time()
        for key in keys:
            self.backend.consume(key, weight=1)
        elapsed = time.time() - start
        assert elapsed < 10.0