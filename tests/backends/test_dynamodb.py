import pytest
import time
from datetime import datetime, timedelta

try:
    from ratelink.backends.dynamodb import DynamoDBBackend, BOTO3_AVAILABLE
except ImportError:
    BOTO3_AVAILABLE = False

@pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
class TestDynamoDBBackend:
    @pytest.fixture(autouse=True)
    def setup(self):
        try:
            self.backend = DynamoDBBackend(
                region="us-east-1",
                table_name="test_rate_limits",
                endpoint_url="http://localhost:8000",
                aws_access_key_id="test",
                aws_secret_access_key="test",
            )
            self.backend.reset()
            yield
            self.backend.reset()
        except Exception:
            pytest.skip("DynamoDB not available (local or AWS)")

    def test_initialization(self):
        assert self.backend is not None
        assert self.backend.table_name == "test_rate_limits"

    def test_table_creation(self):
        assert self.backend.table is not None

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

    def test_ttl_functionality(self):
        key = "test:ttl"
        state = self.backend.consume(key, weight=1)
        assert state.reset_at > datetime.now()

    def test_conditional_writes(self):
        key = "test:conditional"
        state1 = self.backend.consume(key, weight=100)
        assert not state1.violated
        state2 = self.backend.consume(key, weight=50)
        assert state2.remaining < state1.remaining

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
        assert state.metadata["backend"] == "dynamodb"

    def test_performance(self):
        keys = [f"test:perf:{i}" for i in range(100)]
        start = time.time()
        for key in keys:
            self.backend.consume(key, weight=1)
        elapsed = time.time() - start
        assert elapsed < 15.0