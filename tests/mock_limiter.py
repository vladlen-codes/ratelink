class MockRateLimiter:    
    def __init__(self, should_allow=True, state=None):
        self.should_allow = should_allow
        self.state = state or {
            'allowed': should_allow,
            'remaining': 50 if should_allow else 0,
            'limit': 100,
            'retry_after': 0 if should_allow else 30.0,
            'reset_after': 60.0
        }
        self.check_calls = []
    
    def check(self, key, weight=1):
        self.check_calls.append((key, weight))
        return self.should_allow, self.state
    
    def reset(self):
        self.check_calls = []