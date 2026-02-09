import logging
from collections import defaultdict
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Protocol

HookCallback = Callable[..., None]

class HookContext(Protocol):    
    event: str
    timestamp: float


class HookManager:    
    def __init__(
        self,
        catch_exceptions: bool = True,
        logger: Optional[logging.Logger] = None
    ):
        self._hooks: Dict[str, List[HookCallback]] = defaultdict(list)
        self._lock = Lock()
        self._catch_exceptions = catch_exceptions
        self._logger = logger or logging.getLogger("rate_limiter.hooks")
        self._stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"called": 0, "failed": 0}
        )
    
    def register(
        self,
        event: str,
        callback: HookCallback,
        prepend: bool = False
    ) -> None:
        with self._lock:
            if prepend:
                self._hooks[event].insert(0, callback)
            else:
                self._hooks[event].append(callback)
    
    def unregister(
        self,
        event: str,
        callback: HookCallback
    ) -> bool:
        with self._lock:
            try:
                self._hooks[event].remove(callback)
                return True
            except ValueError:
                return False
    
    def fire(
        self,
        event: str,
        **kwargs: Any
    ) -> None:
        with self._lock:
            callbacks = list(self._hooks.get(event, []))
        
        if not callbacks:
            return

        for callback in callbacks:
            try:
                callback(**kwargs)
                self._stats[event]["called"] += 1
            except Exception as e:
                self._stats[event]["failed"] += 1
                
                if self._catch_exceptions:
                    self._logger.error(
                        f"Hook callback failed for event '{event}': {e}",
                        exc_info=True
                    )
                else:
                    raise
    
    def clear(self, event: Optional[str] = None) -> None:
        with self._lock:
            if event:
                self._hooks[event].clear()
            else:
                self._hooks.clear()
    
    def list_hooks(self, event: str) -> List[HookCallback]:
        with self._lock:
            return list(self._hooks.get(event, []))
    
    def get_stats(self) -> Dict[str, Dict[str, int]]:
        return dict(self._stats)


class HookBuilder:
    @staticmethod
    def create_violation_alert(
        alert_func: Callable[[str, Dict[str, Any]], None]
    ) -> HookCallback:
        def hook(key: str, **kwargs):
            alert_func(key, kwargs)
        return hook
    
    @staticmethod
    def create_metrics_aggregator(
        window_seconds: int = 60
    ) -> tuple[HookCallback, Callable[[], Dict]]:
        import time
        from collections import deque
        
        events = deque()
        lock = Lock()
        
        def hook(**kwargs):
            with lock:
                events.append((time.time(), kwargs))
                cutoff = time.time() - window_seconds
                while events and events[0][0] < cutoff:
                    events.popleft()
        
        def get_stats():
            with lock:
                return {
                    "total_events": len(events),
                    "window_seconds": window_seconds,
                }
        
        return hook, get_stats
    
    @staticmethod
    def create_circuit_breaker(
        threshold: int,
        window_seconds: int,
        callback: Callable[[], None]
    ) -> HookCallback:
        import time
        from collections import deque
        
        violations = deque()
        lock = Lock()
        tripped = False
        
        def hook(**kwargs):
            nonlocal tripped
            
            with lock:
                now = time.time()
                violations.append(now)
                
                cutoff = now - window_seconds
                while violations and violations[0] < cutoff:
                    violations.popleft()
                
                if not tripped and len(violations) >= threshold:
                    tripped = True
                    try:
                        callback()
                    except Exception:
                        pass
        
        return hook