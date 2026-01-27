# Ratelink
A production-grade rate limiter module with 5+ algorithms (Token Bucket, Sliding Window, Leaky Bucket, etc.) with multi-backend support (Redis, memory, distributed).

## Purpose
This module will be used to control and limit the rate of operations (like API requests, function calls, or resource access) to prevent system overload, ensure fair resource usage, and protect against abuse.

## Features
- 5 Rate Limiting Algorithms: Token Bucket, Sliding Window, Leaky Bucket, Fixed Window, GCRA
- High Performance: <1ms latency per operation
- Thread-Safe: Concurrent access support
- Async/Await: Full async support for all operations
- Type Hints: 100% type annotated
- Zero Dependencies: Core library has no external dependencies
- Extensible: Easy to add custom algorithms and backends

### Key Use Cases
- API Rate Limiting - Limit how many requests a user/client can make per time period
- Resource Protection - Prevent system overload by throttling resource-intensive operations
- Fair Usage Enforcement - Ensure equitable access to shared resources
- DoS Protection - Mitigate denial-of-service attacks

### Contributing
- Fork the repository
- Create a feature branch (git checkout -b feature/amazing-feature)
- Make your changes
- Run tests (make test)
- Run all quality checks (make all)
- Commit your changes (git commit -m 'Add amazing feature')
- Push to the branch (git push origin feature/amazing-feature)
- Open a Pull Request
