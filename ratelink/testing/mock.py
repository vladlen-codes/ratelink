from typing import Any, Callable, Dict, List, Optional, Tuple

class MockRateLimiter:
    def __init__(
        self,
        mode: str = 'always_allow',
        behavior: Optional[Callable] = None,
        default_state: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        window: int = 60
    ):
        if mode not in ['always_allow', 'always_deny', 'scripted']:
            raise ValueError(f"Invalid mode: {mode}")
        
        self.mode = mode
        self.behavior = behavior
        self.limit = limit
        self.window = window
        
        self.default_state = default_state or {
            'allowed': True,
            'remaining': 50,
            'limit': limit,
            'window': window,
            'retry_after': 0.0,
            'reset_after': window,
        }
        
        self.call_count = 0
        self.last_key: Optional[str] = None
        self.last_weight: int = 1
        self.call_history: List[Dict[str, Any]] = []
        
        self.key_counts: Dict[str, int] = {}
    
    def check(self, key: str, weight: int = 1) -> Tuple[bool, Dict[str, Any]]:
        self.call_count += 1
        self.last_key = key
        self.last_weight = weight
        self.key_counts[key] = self.key_counts.get(key, 0) + 1
        
        if self.mode == 'always_allow':
            allowed = True
            state = self._create_state(True, key, weight)
        elif self.mode == 'always_deny':
            allowed = False
            state = self._create_state(False, key, weight)
        elif self.mode == 'scripted':
            if self.behavior is None:
                raise ValueError("Scripted mode requires behavior function")
            allowed, state = self.behavior(key, weight)
        else:
            raise ValueError(f"Invalid mode: {self.mode}")
        
        self.call_history.append({
            'key': key,
            'weight': weight,
            'allowed': allowed,
            'state': state.copy(),
            'call_number': self.call_count
        })
        
        return allowed, state
    
    def _create_state(self, allowed: bool, key: str, weight: int) -> Dict[str, Any]:
        state = self.default_state.copy()
        state['allowed'] = allowed
        
        if not allowed:
            state['remaining'] = 0
            state['retry_after'] = 30.0
        
        return state
    
    def reset(self):
        self.call_count = 0
        self.last_key = None
        self.last_weight = 1
        self.call_history = []
        self.key_counts = {}
    
    def get_calls_for_key(self, key: str) -> List[Dict[str, Any]]:
        return [call for call in self.call_history if call['key'] == key]
    
    def set_mode(self, mode: str):
        if mode not in ['always_allow', 'always_deny', 'scripted']:
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode
    
    def set_behavior(self, behavior: Callable):
        self.behavior = behavior
        if self.mode != 'scripted':
            self.mode = 'scripted'
    
    def get_key_count(self, key: str) -> int:
        return self.key_counts.get(key, 0)
    
    def was_called_with(self, key: str, weight: int = 1) -> bool:
        for call in self.call_history:
            if call['key'] == key and call['weight'] == weight:
                return True
        return False
    
    def get_last_call(self) -> Optional[Dict[str, Any]]:
        return self.call_history[-1] if self.call_history else None
    
    def set_default_state(self, **kwargs):
        self.default_state.update(kwargs)


class ScriptedBehavior:
    def __init__(self):
        self.steps: List[Tuple[str, int, Dict]] = []
        self.current_step = 0
        self.step_count = 0
    
    def allow_n_times(self, n: int, state: Optional[Dict] = None):
        self.steps.append(('allow', n, state or {}))
        return self
    
    def deny_n_times(self, n: int, state: Optional[Dict] = None):
        self.steps.append(('deny', n, state or {}))
        return self
    
    def always_allow(self, state: Optional[Dict] = None):
        self.steps.append(('allow', float('inf'), state or {}))
        return self
    
    def always_deny(self, state: Optional[Dict] = None):
        self.steps.append(('deny', float('inf'), state or {}))
        return self
    
    def __call__(self, key: str, weight: int = 1) -> Tuple[bool, Dict[str, Any]]:
        if not self.steps:
            return True, {'remaining': 100, 'limit': 100}
        
        if self.current_step >= len(self.steps):
            action, _, state = self.steps[-1]
        else:
            action, count, state = self.steps[self.current_step]
        
        self.step_count += 1
        if self.current_step < len(self.steps):
            _, count, _ = self.steps[self.current_step]
            if self.step_count > count:
                self.current_step += 1
                self.step_count = 1
                if self.current_step < len(self.steps):
                    action, _, state = self.steps[self.current_step]
        
        allowed = action == 'allow'
        response_state = {
            'allowed': allowed,
            'remaining': 50 if allowed else 0,
            'limit': 100,
            'retry_after': 0.0 if allowed else 30.0,
        }
        response_state.update(state)
        
        return allowed, response_state
    
    def reset(self):
        self.current_step = 0
        self.step_count = 0