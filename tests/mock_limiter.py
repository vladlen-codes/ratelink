from datetime import datetime, timedelta
from ratelink.core.types import RateLimitState


class MockRateLimiter:    
    def __init__(self, should_allow=True, state=None):
        self.should_allow = should_allow
        if state is not None:
            self._state = state
        else:
            self._state = RateLimitState(
                limit=100,
                remaining=50 if should_allow else 0,
                reset_at=datetime.now() + timedelta(seconds=60),
                retry_after=0.0 if should_allow else 30.0,
                violated=not should_allow,
            )
        self.check_calls = []
    
    def check(self, key, weight=1):
        self.check_calls.append((key, weight))
        return self._state
    
    def allow(self, key, weight=1):
        self.check_calls.append((key, weight))
        return self.should_allow
    
    def reset(self):
        self.check_calls = []