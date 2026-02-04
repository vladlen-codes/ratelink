from typing import Dict, Optional, Any, Union
from .rate_limiter import RateLimiter
from .core.types import RateLimitState
from .core.types import ConfigError

class PriorityRateLimiter:
    def __init__(
        self,
        tiers: Dict[str, Dict[str, Any]],
        backend: str = "memory",
        backend_options: Optional[Dict[str, Any]] = None,
        default_tier: str = "free",
    ) -> None:
        self.tiers = tiers
        self.backend = backend
        self.backend_options = backend_options or {}
        self.default_tier = default_tier
        self._limiters: Dict[str, Optional[RateLimiter]] = {}
        for tier_name, tier_config in tiers.items():
            self._limiters[tier_name] = self._create_tier_limiter(tier_name, tier_config)

    def _create_tier_limiter(
        self, tier_name: str, config: Dict[str, Any]
    ) -> Optional[RateLimiter]:
        if config.get("requests_per_hour") is None and \
           config.get("requests_per_minute") is None and \
           config.get("requests_per_day") is None:
            return None

        if "requests_per_hour" in config:
            limit = config["requests_per_hour"]
            window = 3600
        elif "requests_per_minute" in config:
            limit = config["requests_per_minute"]
            window = 60
        elif "requests_per_day" in config:
            limit = config["requests_per_day"]
            window = 86400
        else:
            raise ConfigError(f"Tier {tier_name} must specify a rate limit")

        algorithm = config.get("algorithm", "token_bucket")

        algorithm_options = {}
        if "burst" in config:
            algorithm_options["capacity"] = config["burst"]

        return RateLimiter(
            algorithm=algorithm,
            backend=self.backend,
            backend_options=self.backend_options,
            limit=limit,
            window=window,
            algorithm_options=algorithm_options,
        )

    def allow(
        self,
        key: str,
        tier: Optional[str] = None,
        weight: int = 1
    ) -> bool:
        tier = tier or self.default_tier

        if tier not in self._limiters:
            raise ConfigError(f"Unknown tier: {tier}")

        limiter = self._limiters[tier]

        if limiter is None:
            return True

        tier_key = f"{tier}:{key}"
        return limiter.allow(tier_key, weight=weight)

    async def acquire(
        self,
        key: str,
        tier: Optional[str] = None,
        weight: int = 1
    ) -> bool:
        tier = tier or self.default_tier
        if tier not in self._limiters:
            raise ConfigError(f"Unknown tier: {tier}")

        limiter = self._limiters[tier]

        if limiter is None:
            return True

        tier_key = f"{tier}:{key}"
        return await limiter.acquire(tier_key, weight=weight)

    def check(self, key: str, tier: Optional[str] = None) -> RateLimitState:
        tier = tier or self.default_tier
        if tier not in self._limiters:
            raise ConfigError(f"Unknown tier: {tier}")

        limiter = self._limiters[tier]

        if limiter is None:
            from datetime import datetime
            return RateLimitState(
                limit=999999999,
                remaining=999999999,
                reset_at=datetime.now(),
                retry_after=0.0,
                violated=False,
                metadata={"tier": tier, "unlimited": True},
            )

        tier_key = f"{tier}:{key}"
        return limiter.check(tier_key)

    def reset(self, key: str, tier: Optional[str] = None) -> None:
        if tier is None:
            for tier_limiter in self._limiters.values():
                if tier_limiter is not None:
                    tier_limiter.reset(key)
        else:
            if tier not in self._limiters:
                raise ConfigError(f"Unknown tier: {tier}")

            limiter = self._limiters[tier]
            if limiter is not None:
                tier_key = f"{tier}:{key}"
                limiter.reset(tier_key)

    def get_tier_config(self, tier: str) -> Dict[str, Any]:
        if tier not in self.tiers:
            raise ConfigError(f"Unknown tier: {tier}")

        return self.tiers[tier].copy()

    def list_tiers(self) -> list:
        return list(self.tiers.keys())

    def is_unlimited(self, tier: str) -> bool:
        if tier not in self._limiters:
            raise ConfigError(f"Unknown tier: {tier}")
        return self._limiters[tier] is None

    def upgrade_tier(
        self,
        key: str,
        from_tier: str,
        to_tier: str,
        preserve_state: bool = False
    ) -> None:
        if from_tier not in self._limiters:
            raise ConfigError(f"Unknown tier: {from_tier}")
        if to_tier not in self._limiters:
            raise ConfigError(f"Unknown tier: {to_tier}")
        if not preserve_state:
            self.reset(key, tier=from_tier)
        else:
            old_limiter = self._limiters[from_tier]
            new_limiter = self._limiters[to_tier]
            if old_limiter is not None and new_limiter is not None:
                old_key = f"{from_tier}:{key}"
                state = old_limiter.check(old_key)
                if state.limit > 0:
                    usage_pct = (state.limit - state.remaining) / state.limit
                    new_config = self.tiers[to_tier]
                    new_limit = new_config.get("requests_per_hour") or \
                                new_config.get("requests_per_minute") or \
                                new_config.get("requests_per_day")
                    if new_limit:
                        consumed = int(new_limit * usage_pct)
                        if consumed > 0:
                            new_key = f"{to_tier}:{key}"
                            new_limiter.allow(new_key, weight=consumed)
            self.reset(key, tier=from_tier)