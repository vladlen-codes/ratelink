# Ratelink

[![PyPI version](https://badge.fury.io/py/ratelink.svg)](https://badge.fury.io/py/ratelink)
[![Python Versions](https://img.shields.io/pypi/pyversions/ratelink.svg)](https://pypi.org/project/ratelink/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)](https://github.com/vladlen-codes/ratelink)

**Production-ready rate limiting for Python** - Multiple algorithms, backends, and framework integrations with full observability.

## Features

- **6 Algorithms**: Token Bucket, Leaky Bucket, Fixed Window, Sliding Window, Sliding Window Log, GCRA
- **6+ Backends**: Memory, Redis, PostgreSQL, DynamoDB, MongoDB, Multi-Region
- **4 Framework Integrations**: FastAPI, Flask, Django, aiohttp
- **Full Observability**: Prometheus, StatsD, audit logging, distributed tracing
- **Complete Testing Suite**: Mocks, time machine, fixtures, load testing
- **Advanced Features**: Priority limits, quota pooling, adaptive limits, hierarchical limits
- **Production Ready**: Type-safe, tested (>90% coverage), documented

## Quick Start

### Installation

```bash
pip install ratelink
```

### Basic Usage

```python
from ratelink import RateLimiter

# Create a rate limiter
limiter = RateLimiter(
    algorithm="token_bucket",
    limit=100,          # 100 requests
    window=60,          # per 60 seconds
)

# Check if request is allowed
allowed, state = limiter.check("user:123")

if allowed:
    # Process request
    print(f"✅ Allowed! {state['remaining']} remaining")
else:
    # Reject request
    print(f"❌ Rate limited! Retry after {state['retry_after']}s")
```

### With FastAPI

```python
from fastapi import FastAPI
from ratelink import RateLimiter
from ratelink.integration.fastapi import FastAPIRateLimitMiddleware

app = FastAPI()
limiter = RateLimiter(algorithm="token_bucket", limit=100, window=60)

app.add_middleware(
    FastAPIRateLimitMiddleware,
    limiter=limiter
)

@app.get("/api/data")
async def get_data():
    return {"data": [...]}
```

Requests automatically include rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 59
```

### With Redis (Distributed)

```python
import redis
from ratelink import RateLimiter
from ratelink.backends.redis import RedisBackend

client = redis.Redis(host='localhost', port=6379)
backend = RedisBackend(client=client)

limiter = RateLimiter(
    algorithm="sliding_window",
    limit=1000,
    window=3600,
    backend=backend
)
```

## Comparison

| Feature | Ratelink | slowapi | flask-limiter | Other libs |
|---------|----------|---------|---------------|------------|
| Algorithms | 6 | 1 | 1-2 | 1 |
| Backends | 6+ | Memory | Memory/Redis | Memory |
| Frameworks | 4+ | FastAPI | Flask | Varies |
| Observability | Full suite | None | Basic | None |
| Testing Tools | Complete | None | None | None |
| Advanced Features | ✅ | ❌ | ❌ | ❌ |
| Type Safety | 100% | Partial | No | Varies |
| Coverage | >90% | ~60% | ~70% | Varies |

## Algorithms

| Algorithm | Best For | Pros | Cons |
|-----------|----------|------|------|
| **Token Bucket** | General purpose, API rate limiting | Allows bursts, smooth | Requires token tracking |
| **Leaky Bucket** | Traffic shaping, steady flow | Smooth output | No bursts |
| **Fixed Window** | Simple counting, analytics | Simple, fast | Boundary issues |
| **Sliding Window** | Distributed systems | No boundary issues | More complex |
| **Sliding Window Log** | Precision timing | Exact tracking | Higher memory |
| **GCRA** | Telecom, strict timing | Standards compliant | Complex |

## Backends

| Backend | Best For | Latency | Distributed |
|---------|----------|---------|-------------|
| **Memory** | Development, single server | <1μs | ❌ |
| **Redis** | Production, distributed | ~1ms | ✅ |
| **PostgreSQL** | Existing Postgres stack | ~2-5ms | ✅ |
| **DynamoDB** | AWS, serverless | ~10-50ms | ✅ |
| **MongoDB** | Existing Mongo stack | ~2-10ms | ✅ |
| **Multi-Region** | Global apps | Varies | ✅ |

## Framework Support

### FastAPI
```python
from ratelink.integration.fastapi import FastAPIRateLimitMiddleware, rate_limit
```

### Flask
```python
from ratelink.integration.flask import FlaskRateLimiter
```

### Django
```python
from ratelink.integration.django import DjangoRateLimitMiddleware
```

### aiohttp
```python
from ratelink.integration.aiohttp import aiohttp_rate_limit_middleware
```

## Observability

### Prometheus Metrics

```python
from ratelink.observability.metrics import MetricsCollector
from ratelink.integrations.prometheus import PrometheusExporter

metrics = PrometheusExporter()
limiter = RateLimiter(..., metrics_collector=metrics)

# Expose metrics endpoint
@app.get("/metrics")
def metrics_endpoint():
    return Response(metrics.render(), media_type="text/plain")
```

### Audit Logging

```python
from ratelink.observability.logging import AuditLogger

logger = AuditLogger(sink=open("audit.log", "a"), json=True)
limiter = RateLimiter(..., audit_logger=logger)
```

## Testing

```python
from ratelink.testing import MockRateLimiter, TimeMachine, assert_allowed

# Mock for unit tests
limiter = MockRateLimiter(mode='always_allow')

# Time control for deterministic tests
tm = TimeMachine()
tm.freeze()
tm.advance(60)  # Advance 60 seconds instantly

# High-level assertions
assert_allowed(limiter, 'user:123', times=5)
```

## Documentation

- **[Getting Started](docs/getting-started.md)** - Installation and basic usage
- **[API Reference](docs/api-reference/)** - Complete API documentation
- **[Guides](docs/guides/)** - How-to guides and best practices
- **[Examples](docs/examples/)** - Real-world examples
- **[Benchmarks](docs/benchmarks.md)** - Performance comparisons

## Advanced Features

### Priority-Based Rate Limiting

```python
from ratelink.advanced.priority import PriorityRateLimiter

limiter = PriorityRateLimiter(limits={
    "critical": {"limit": 1000, "window": 60},
    "normal": {"limit": 100, "window": 60},
    "low": {"limit": 10, "window": 60},
})
```

### Quota Pooling

```python
from ratelink.advanced.quota import QuotaPool

pool = QuotaPool(total_quota=10000, window=3600)
pool.allocate("user:123", quota=100)
```

### Adaptive Limits

```python
from ratelink.advanced.adaptive import AdaptiveRateLimiter

limiter = AdaptiveRateLimiter(
    base_limit=100,
    adjust_on_error_rate=True,
    max_limit=500,
    min_limit=10
)
```

## Installation Options

```bash
# Basic
pip install ratelink

# With Redis
pip install ratelink[redis]

# With all backends
pip install ratelink[backends]

# With web frameworks
pip install ratelink[frameworks]

# With observability
pip install ratelink[observability]

# Everything
pip install ratelink[all]
```

## 🔧 Configuration

### Environment Variables

```bash
RATELINK_ALGORITHM=token_bucket
RATELINK_LIMIT=100
RATELINK_WINDOW=60
RATELINK_BACKEND=redis
REDIS_URL=redis://localhost:6379
```

### YAML Configuration

```yaml
rate_limiting:
  algorithm: token_bucket
  limit: 100
  window: 60
  backend:
    type: redis
    url: redis://localhost:6379
```

## Real-World Examples

Check out [examples/](examples/) for complete, runnable applications:

- **SaaS Tiers** - Free/Pro/Enterprise rate limits
- **API Gateway** - Multi-tenant API gateway
- **Webhook Processor** - Per-customer webhook limits
- **IoT Ingestion** - Device rate limiting
- **Real-time Apps** - WebSocket rate limiting

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone the repo
git clone https://github.com/your-org/ratelink.git
cd ratelink

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev,all]"

# Run tests
pytest

# Run linting
black .
flake8
mypy ratelink
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Star History

If you find Ratelink useful, please consider giving it a star on GitHub!

## Acknowledgments

Built with inspiration from:
- [django-ratelimit](https://github.com/jsocol/django-ratelimit)
- [slowapi](https://github.com/laurentS/slowapi)
- [flask-limiter](https://github.com/alisaifee/flask-limiter)

With improvements in architecture, features, and production-readiness.

---

**Made with ❤️ for the Python community**