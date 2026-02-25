import os
from enum import Enum
from typing import Optional

import redis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ratelink import RateLimiter
from ratelink.backends.redis import RedisBackend
from ratelink.integrations.fastapi import FastAPIRateLimitMiddleware, rate_limit
from ratelink.integrations.prometheus import PrometheusExporter
from ratelink.observability.logging import AuditLogger
from ratelink.utils.key_generators import by_api_key, composite_key


class UserTier(str, Enum):
    """User subscription tiers."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

TIER_LIMITS = {
    UserTier.FREE: {"limit": 100, "window": 3600},
    UserTier.PRO: {"limit": 1000, "window": 3600},
    UserTier.ENTERPRISE: {"limit": 10000, "window": 3600},
}

USER_DATABASE = {
    "free_user_123": UserTier.FREE,
    "pro_user_456": UserTier.PRO,
    "enterprise_user_789": UserTier.ENTERPRISE,
}


def get_user_tier(api_key: str) -> UserTier:
    return USER_DATABASE.get(api_key, UserTier.FREE)

app = FastAPI(
    title="SaaS API with Tiered Rate Limiting",
    description="Example API with Free, Pro, and Enterprise tiers",
    version="1.0.0"
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)
backend = RedisBackend(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
)

metrics = PrometheusExporter()

audit_logger = AuditLogger(
    sink=open("saas_audit.log", "a"),
    json=True,
    log_violations=True,
    log_config_changes=True
)

tier_limiters = {}
for tier, config in TIER_LIMITS.items():
    tier_limiters[tier] = RateLimiter(
        algorithm="sliding_window",
        limit=config["limit"],
        window=config["window"],
        backend=backend,
    )

global_limiter = RateLimiter(
    algorithm="token_bucket",
    limit=10000,
    window=3600,
    backend=backend,
)

def get_user_limiter(request: Request) -> RateLimiter:
    api_key = request.headers.get("X-API-Key", "")
    tier = get_user_tier(api_key)
    return tier_limiters[tier]

app.add_middleware(
    FastAPIRateLimitMiddleware,
    limiter=global_limiter,
    key_generator=by_api_key(),
    skip_paths=["/health", "/metrics", "/docs", "/openapi.json"]
)

@app.get("/health")
async def health():
    try:
        redis_client.ping()
        redis_status = "healthy"
    except:
        redis_status = "unhealthy"
    
    return {
        "status": "ok",
        "redis": redis_status
    }

@app.get("/metrics")
async def prometheus_metrics():
    return PlainTextResponse(metrics.render())

@app.get("/api/data")
async def get_data(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    tier = get_user_tier(x_api_key)
    
    limiter = tier_limiters[tier]
    state = limiter.check(f"user:{x_api_key}")
    
    if state.violated:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "tier": tier,
                "limit": state.limit,
                "retry_after": state.retry_after,
                "upgrade_url": "/pricing"
            },
            headers={
                "Retry-After": str(int(state.retry_after)),
                "X-RateLimit-Limit": str(state.limit),
                "X-RateLimit-Remaining": "0",
            }
        )
    
    return {
        "data": ["item1", "item2", "item3"],
        "tier": tier,
        "rate_limit": {
            "limit": state.limit,
            "remaining": state.remaining,
            "reset_after": state.retry_after
        }
    }


@app.post("/api/upload")
@rate_limit(
    tier_limiters[UserTier.PRO],
    limit=100,
    window=3600,
    key_generator=by_api_key()
)
async def upload_data(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):

    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    tier = get_user_tier(x_api_key)
    
    if tier == UserTier.FREE:
        raise HTTPException(
            status_code=403,
            detail="Upgrade to Pro or Enterprise to use upload feature"
        )
    
    return {
        "status": "uploaded",
        "tier": tier
    }


@app.get("/api/analytics")
async def get_analytics(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):

    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    tier = get_user_tier(x_api_key)
    
    if tier != UserTier.ENTERPRISE:
        raise HTTPException(
            status_code=403,
            detail="Enterprise plan required for analytics"
        )
    
    limiter = tier_limiters[UserTier.ENTERPRISE]
    state = limiter.check(f"user:{x_api_key}:analytics")
    
    if state.violated:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"},
            headers={"Retry-After": str(int(state.retry_after))}
        )
    
    return {
        "analytics": {
            "total_requests": 12345,
            "error_rate": 0.01,
            "avg_latency_ms": 45
        }
    }

@app.get("/pricing")
async def pricing():
    return {
        "tiers": [
            {
                "name": "Free",
                "rate_limit": "100 requests/hour",
                "price": "$0/month",
                "features": ["Basic API access"]
            },
            {
                "name": "Pro",
                "rate_limit": "1,000 requests/hour",
                "price": "$49/month",
                "features": [
                    "10x more requests",
                    "Upload API",
                    "Priority support"
                ]
            },
            {
                "name": "Enterprise",
                "rate_limit": "10,000 requests/hour",
                "price": "$499/month",
                "features": [
                    "100x more requests",
                    "Analytics API",
                    "Dedicated support",
                    "SLA guarantee"
                ]
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)