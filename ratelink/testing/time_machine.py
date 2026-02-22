import time
from typing import Optional

class TimeMachine:
    def __init__(self):
        self._frozen = False
        self._frozen_time: Optional[float] = None
        self._offset: float = 0.0
        self._base_time: Optional[float] = None
    
    def freeze(self, at: Optional[float] = None):
        if at is None:
            at = time.time() + self._offset
        
        self._frozen = True
        self._frozen_time = at
    
    def unfreeze(self):
        if self._frozen and self._frozen_time is not None:
            real_now = time.time()
            self._offset = self._frozen_time - real_now
        
        self._frozen = False
        self._frozen_time = None
    
    def advance(self, seconds: float):
        if self._frozen and self._frozen_time is not None:
            self._frozen_time += seconds
        else:
            self._offset += seconds
    
    def rewind(self, seconds: float):
        self.advance(-seconds)
    
    def time(self) -> float:
        if self._frozen and self._frozen_time is not None:
            return self._frozen_time
        else:
            return time.time() + self._offset
    
    def reset(self):
        self._frozen = False
        self._frozen_time = None
        self._offset = 0.0
        self._base_time = None
    
    def set_time(self, timestamp: float):
        self._frozen = True
        self._frozen_time = timestamp
    
    def travel_to(self, timestamp: float):
        self.set_time(timestamp)
    
    def get_offset(self) -> float:
        if self._frozen and self._frozen_time is not None:
            return self._frozen_time - time.time()
        else:
            return self._offset
    
    def is_frozen(self) -> bool:
        return self._frozen
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.reset()
        return False

class MonkeyPatchedTimeMachine(TimeMachine):
    def __init__(self):
        super().__init__()
        self._original_time = None
    
    def __enter__(self):
        import time as time_module
        self._original_time = time_module.time
        time_module.time = self.time
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._original_time is not None:
            import time as time_module
            time_module.time = self._original_time
        
        self.reset()
        return False

def freeze_time(at: Optional[float] = None):
    tm = TimeMachine()
    tm.freeze(at)
    return tm

def advance_time(seconds: float):
    tm = TimeMachine()
    tm.freeze()
    tm.advance(seconds)
    return tm