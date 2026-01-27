import pytest
import time
from datetime import datetime, timedelta

@pytest.fixture
def current_time():
    return time.time()

@pytest.fixture
def future_time():
    return time.time() + 10

@pytest.fixture
def past_time():
    return time.time() - 10

@pytest.fixture
def test_key():
    return "test:key:123"

@pytest.fixture
def multiple_keys():
    return ["test:key:1", "test:key:2", "test:key:3"]

@pytest.fixture
def wait_for_refill():
    def _wait(seconds: float) -> None:
        time.sleep(seconds)
    return _wait