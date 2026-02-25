# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-25

### Added
- 6 rate limiting algorithms: Token Bucket, Leaky Bucket, Fixed Window, Sliding Window, Sliding Window Log, GCRA
- 6+ backends: Memory, Redis, PostgreSQL, DynamoDB, MongoDB, Multi-Region
- 4 framework integrations: FastAPI, Flask, Django, aiohttp
- Full observability: Prometheus, StatsD, audit logging, distributed tracing
- Complete testing suite: Mocks, time machine, fixtures, load testing
- Advanced features: Priority limits, quota pooling, adaptive limits, hierarchical limits
- Type-safe with py.typed marker
- Configuration via YAML/JSON files
- Decorator and middleware patterns for all frameworks
