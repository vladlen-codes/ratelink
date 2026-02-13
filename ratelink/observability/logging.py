import json
import logging
import sys
from datetime import datetime, timezone
from io import TextIOBase
from threading import Lock
from typing import Any, Dict, Optional, TextIO


class AuditLogger:
    def __init__(
        self,
        sink: Optional[TextIO] = None,
        json: bool = True,
        level: int = logging.INFO,
        log_limit_checks: bool = True,
        log_violations: bool = True,
        log_config_changes: bool = True,
        include_timestamp: bool = True,
        include_hostname: bool = False
    ):
        self._sink = sink or sys.stdout
        self._json = json
        self._level = level
        self._log_limit_checks = log_limit_checks
        self._log_violations = log_violations
        self._log_config_changes = log_config_changes
        self._include_timestamp = include_timestamp
        self._include_hostname = include_hostname       
        self._lock = Lock()
    
        if not json:
            self._logger = logging.getLogger("rate_limiter.audit")
            self._logger.setLevel(level)
            
            if not self._logger.handlers:
                handler = logging.StreamHandler(self._sink)
                formatter = logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(message)s"
                )
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)
        else:
            self._logger = None
        
        self._hostname: Optional[str] = None
        if include_hostname:
            import socket
            try:
                self._hostname = socket.gethostname()
            except Exception:
                self._hostname = "unknown"
    
    def _get_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()
    
    def _write_json(self, event: Dict[str, Any]) -> None:
        if self._include_timestamp:
            event["timestamp"] = self._get_timestamp()
        
        if self._hostname:
            event["hostname"] = self._hostname
        
        with self._lock:
            line = json.dumps(event, default=str)
            self._sink.write(line + "\n")
            self._sink.flush()
    
    def _write_text(self, message: str) -> None:
        if self._logger:
            self._logger.info(message)
        else:
            with self._lock:
                if self._include_timestamp:
                    timestamp = self._get_timestamp()
                    message = f"{timestamp} {message}"
                self._sink.write(message + "\n")
                self._sink.flush()
    
    def log_check(
        self,
        key: str,
        state: Dict[str, Any],
        algorithm: str,
        backend: str,
        weight: int,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        if not self._log_limit_checks:
            return
        
        if self._json:
            event = {
                "event": "rate_limit_check",
                "key": key,
                "algorithm": algorithm,
                "backend": backend,
                "allowed": state.get("allowed", False),
                "remaining": state.get("remaining", 0),
                "limit": state.get("limit", 0),
                "weight": weight,
                "retry_after": state.get("retry_after", 0.0),
            }
            
            if extra:
                event["extra"] = extra
            
            self._write_json(event)
        else:
            allowed_str = "ALLOWED" if state.get("allowed") else "DENIED"
            message = (
                f"rate_limit_check key={key} algorithm={algorithm} "
                f"backend={backend} {allowed_str} "
                f"remaining={state.get('remaining', 0)}/{state.get('limit', 0)} "
                f"weight={weight}"
            )
            self._write_text(message)
    
    def log_violation(
        self,
        key: str,
        state: Dict[str, Any],
        algorithm: str,
        backend: str,
        weight: int,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        if not self._log_violations:
            return
        
        if self._json:
            event = {
                "event": "rate_limit_violation",
                "key": key,
                "algorithm": algorithm,
                "backend": backend,
                "remaining": state.get("remaining", 0),
                "limit": state.get("limit", 0),
                "weight": weight,
                "retry_after": state.get("retry_after", 0.0),
            }
            
            if extra:
                event["extra"] = extra
            
            self._write_json(event)
        else:
            message = (
                f"rate_limit_violation key={key} algorithm={algorithm} "
                f"backend={backend} "
                f"remaining={state.get('remaining', 0)}/{state.get('limit', 0)} "
                f"weight={weight} retry_after={state.get('retry_after', 0.0)}s"
            )
            self._write_text(message)
    
    def log_config_change(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
        reason: Optional[str] = None
    ) -> None:
        if not self._log_config_changes:
            return
        
        if self._json:
            event = {
                "event": "config_change",
                "old_config": old,
                "new_config": new,
            }
            
            if reason:
                event["reason"] = reason
            
            self._write_json(event)
        else:
            message = f"config_change from={old} to={new}"
            if reason:
                message += f" reason={reason}"
            self._write_text(message)
    
    def log_custom(
        self,
        event_type: str,
        data: Dict[str, Any]
    ) -> None:
        if self._json:
            event = {"event": event_type, **data}
            self._write_json(event)
        else:
            message = f"{event_type} {data}"
            self._write_text(message)
    
    def close(self) -> None:
        if self._sink and self._sink not in (sys.stdout, sys.stderr):
            if isinstance(self._sink, TextIOBase):
                self._sink.close()