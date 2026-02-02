import os
import yaml
import json
from typing import Dict, Any, Optional, Union, Callable, List
from pathlib import Path
from datetime import time as datetime_time

try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    class BaseModel:
        pass
from .core.types import ConfigError

if PYDANTIC_AVAILABLE:
    class BackendConfig(BaseModel):
        type: str = Field(..., description="Backend type (memory, redis, postgresql, etc.)")
        options: Dict[str, Any] = Field(default_factory=dict, description="Backend-specific options")

    class AlgorithmConfig(BaseModel):
        type: str = Field(..., description="Algorithm type (token_bucket, sliding_window, etc.)")
        options: Dict[str, Any] = Field(default_factory=dict, description="Algorithm-specific options")

    class TimeRangeConfig(BaseModel):
        start: str = Field(..., description="Start time (HH:MM)")
        end: str = Field(..., description="End time (HH:MM)")
        limit: int = Field(..., description="Limit for this time range")
        window: Union[int, str] = Field(..., description="Window size")

        @validator("start", "end")
        def validate_time_format(cls, v: str) -> str:
            try:
                hours, minutes = v.split(":")
                h, m = int(hours), int(minutes)
                if not (0 <= h < 24 and 0 <= m < 60):
                    raise ValueError
                return v
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid time format: {v}. Expected HH:MM")

    class EndpointConfig(BaseModel):
        algorithm: Optional[str] = None
        backend: Optional[str] = None
        limit: int
        window: Union[int, str]
        algorithm_options: Dict[str, Any] = Field(default_factory=dict)
        backend_options: Dict[str, Any] = Field(default_factory=dict)
        time_ranges: List[TimeRangeConfig] = Field(default_factory=list)

    class UserTierConfig(BaseModel):
        limit: Optional[int] = None
        window: Union[int, str] = "hour"
        algorithm: Optional[str] = None
        backend: Optional[str] = None

    class DefaultConfig(BaseModel):
        algorithm: str = "token_bucket"
        backend: str = "memory"
        limit: int = 1000
        window: Union[int, str] = "hour"
        backend_options: Dict[str, Any] = Field(default_factory=dict)
        algorithm_options: Dict[str, Any] = Field(default_factory=dict)
        raise_on_limit: bool = False

    class RateLimitingConfig(BaseModel):
        default: DefaultConfig
        endpoints: Dict[str, EndpointConfig] = Field(default_factory=dict)
        users: Dict[str, UserTierConfig] = Field(default_factory=dict)

    class RootConfig(BaseModel):
        rate_limiting: RateLimitingConfig


class ConfigLoader:
    def __init__(self) -> None:
        self._watchers: Dict[str, Callable] = {}

    def load(self, source: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(source, dict):
            return self._validate_config(source)
        source_path = Path(source)
        
        if not source_path.exists():
            raise ConfigError(f"Config file not found: {source}")

        if source_path.suffix in [".yaml", ".yml"]:
            return self._load_yaml(source_path)
        elif source_path.suffix == ".json":
            return self._load_json(source_path)
        else:
            raise ConfigError(f"Unsupported config format: {source_path.suffix}")

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r") as f:
                config = yaml.safe_load(f)
            return self._validate_config(config)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load YAML: {e}")

    def _load_json(self, path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r") as f:
                config = json.load(f)
            return self._validate_config(config)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load JSON: {e}")

    def load_from_env(self, prefix: str = "RATELIMIT_") -> Dict[str, Any]:
        config: Dict[str, Any] = {
            "rate_limiting": {
                "default": {},
                "endpoints": {},
                "users": {},
            }
        }

        default = config["rate_limiting"]["default"]
        if f"{prefix}ALGORITHM" in os.environ:
            default["algorithm"] = os.environ[f"{prefix}ALGORITHM"]

        if f"{prefix}BACKEND" in os.environ:
            default["backend"] = os.environ[f"{prefix}BACKEND"]

        if f"{prefix}LIMIT" in os.environ:
            default["limit"] = int(os.environ[f"{prefix}LIMIT"])

        if f"{prefix}WINDOW" in os.environ:
            default["window"] = os.environ[f"{prefix}WINDOW"]
        backend_options = {}
        for key, value in os.environ.items():
            if key.startswith(f"{prefix}BACKEND_"):
                option_name = key[len(f"{prefix}BACKEND_"):].lower()
                backend_options[option_name] = value

        if backend_options:
            default["backend_options"] = backend_options

        return self._validate_config(config)

    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if not PYDANTIC_AVAILABLE:
            return config
        try:
            validated = RootConfig(**config)
            return validated.dict()
        except Exception as e:
            raise ConfigError(f"Invalid configuration: {e}")

    def watch(self, path: Union[str, Path], callback: Callable) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            raise ConfigError(
                "File watching requires watchdog library. "
                "Install with: pip install watchdog"
            )
        path = Path(path)
        class ConfigChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path == str(path.absolute()):
                    callback()

        observer = Observer()
        observer.schedule(ConfigChangeHandler(), str(path.parent), recursive=False)
        observer.start()
        self._watchers[str(path)] = observer


class RuleEngine:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.rate_limiting = config.get("rate_limiting", {})

    def get_limit_for_endpoint(
        self, endpoint: str, default_limit: int, default_window: Union[int, str]
    ) -> tuple[int, Union[int, str]]:
        endpoints = self.rate_limiting.get("endpoints", {})

        if endpoint in endpoints:
            endpoint_config = endpoints[endpoint]
            return endpoint_config["limit"], endpoint_config["window"]

        return default_limit, default_window

    def get_limit_for_user(
        self, user_tier: str, default_limit: int, default_window: Union[int, str]
    ) -> tuple[Optional[int], Union[int, str]]:
        users = self.rate_limiting.get("users", {})
        if user_tier in users:
            user_config = users[user_tier]
            limit = user_config.get("limit", default_limit)
            window = user_config.get("window", default_window)
            return limit, window
        return default_limit, default_window

    def get_limit_for_time(
        self, endpoint: str, current_time: Optional[datetime_time] = None
    ) -> Optional[tuple[int, Union[int, str]]]:
        from datetime import datetime
        if current_time is None:
            current_time = datetime.now().time()
        endpoints = self.rate_limiting.get("endpoints", {})
        if endpoint not in endpoints:
            return None
        endpoint_config = endpoints[endpoint]
        time_ranges = endpoint_config.get("time_ranges", [])
        for time_range in time_ranges:
            start = self._parse_time(time_range["start"])
            end = self._parse_time(time_range["end"])
            if self._time_in_range(current_time, start, end):
                return time_range["limit"], time_range["window"]
        return None

    def _parse_time(self, time_str: str) -> datetime_time:
        from datetime import datetime

        return datetime.strptime(time_str, "%H:%M").time()

    def _time_in_range(
        self, current: datetime_time, start: datetime_time, end: datetime_time) -> bool:
        if start <= end:
            return start <= current <= end
        else:
            return current >= start or current <= end