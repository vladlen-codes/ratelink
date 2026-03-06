# Contributing to Ratelink

Thank you for your interest in contributing to Ratelink! This guide will help you get started.

## Code of Conduct

Be respectful, inclusive, and constructive. We're here to build great software together.

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/vladlen-codes/ratelink/issues) first
2. Use the bug report template
3. Include:
   - Python version
   - Ratelink version
   - Minimal reproducible example
   - Expected vs actual behavior
   - Relevant logs/tracebacks

### Suggesting Features

1. Check [discussions](https://github.com/vladlen-codes/ratelink/discussions) first
2. Open an issue with `[Feature Request]` prefix
3. Describe:
   - Use case and motivation
   - Proposed API/behavior
   - Alternatives considered
   - Willingness to implement

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add/update tests
5. Update documentation
6. Run quality checks (see below)
7. Commit with clear messages
8. Push and create a PR

## Development Setup

### Prerequisites

- Python 3.7+
- Git
- (Optional) Docker for Redis/PostgreSQL

### Setup Steps

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/ratelink.git
cd ratelink

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev,all]"

# Install pre-commit hooks (optional but recommended)
pre-commit install
```

### Project Structure

```
ratelink/
├── ratelink/              # Source code
│   ├── algorithms/        # Rate limiting algorithms
│   ├── backends/          # Storage backends
│   ├── core/              # Core RateLimiter class
│   ├── advanced/          # Advanced features
│   ├── observability/     # Metrics, logging, tracing
│   ├── integration/       # Framework integrations
│   ├── utils/             # Key generators, decorators
│   └── testing/           # Testing utilities
│
├── tests/                 # Test suites
│   ├── algorithms/
│   ├── backends/
│   ├── core/
│   ├── advanced/
│   ├── observability/
│   ├── integration/
│   └── testing/
│
├── docs/                  # Documentation
├── examples/              # Example applications
├── benchmarks/            # Performance benchmarks
└── pyproject.toml         # Project configuration
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/algorithms/test_token_bucket.py

# Run with coverage
pytest --cov=ratelink --cov-report=html

# Run specific markers
pytest -m "not slow"              # Skip slow tests
pytest -m integration             # Only integration tests
pytest -m redis_required          # Tests requiring Redis
```

### Code Quality

We use several tools to maintain code quality:

```bash
# Format code with black
black ratelink tests

# Check formatting
black --check ratelink tests

# Lint with flake8
flake8 ratelink tests

# Type check with mypy
mypy ratelink

# Security check with bandit
bandit -r ratelink

# Run all checks
./scripts/quality-check.sh  # If available
```

### Code Style

- **Black**: Line length 100, Python 3.7+ target
- **Type hints**: Required for all public APIs
- **Docstrings**: Google style for all public functions/classes
- **Imports**: Organized with isort (black compatible)

### Testing Guidelines

1. **Coverage**: Aim for >90% coverage on new code
2. **Test Types**:
   - Unit tests for algorithms and backends
   - Integration tests for framework integrations
   - Functional tests for end-to-end scenarios
3. **Markers**: Use appropriate pytest markers
   ```python
   @pytest.mark.slow
   @pytest.mark.integration
   @pytest.mark.redis_required
   ```
4. **Fixtures**: Use provided fixtures from `ratelink.testing.fixtures`
5. **Assertions**: Use helper assertions from `ratelink.testing.assertions`

### Documentation

Documentation is as important as code:

1. **Docstrings**: All public APIs must have docstrings
   ```python
   def check(self, key: str, weight: int = 1) -> Tuple[bool, Dict[str, Any]]:
       """
       Check if a request should be allowed.
       
       Args:
           key: Rate limit key (e.g., "user:123")
           weight: Request weight (default: 1)
       
       Returns:
           Tuple of (allowed, state) where:
           - allowed: True if request allowed, False otherwise
           - state: Dict with remaining, limit, retry_after, etc.
       
       Example:
           >>> limiter = RateLimiter(algorithm="token_bucket", limit=100, window=60)
           >>> allowed, state = limiter.check("user:123")
           >>> if allowed:
           ...     process_request()
       """
   ```

2. **Markdown Docs**: Update relevant docs in `docs/`
3. **Examples**: Add runnable examples for new features
4. **Changelog**: Add entry to `CHANGELOG.md`

### Commit Messages

Use clear, descriptive commit messages:

```
feat: Add support for custom key extractors
fix: Correct token bucket refill calculation
docs: Update FastAPI integration guide
test: Add tests for sliding window algorithm
refactor: Simplify Redis backend connection handling
```

Prefixes:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Tests
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance tasks

### Pull Request Process

1. **Title**: Clear, descriptive (`feat: Add MongoDB backend`)
2. **Description**: 
   - What and why
   - Link to related issues
   - Breaking changes (if any)
3. **Checklist**:
   - [ ] Tests added/updated
   - [ ] Documentation updated
   - [ ] Changelog updated
   - [ ] All checks passing
4. **Review**: Address feedback constructively
5. **Merge**: Squash and merge (we'll handle this)

## Code Review Guidelines

### For Contributors

- Be open to feedback
- Respond to comments
- Ask questions if unclear
- Keep PRs focused and reasonably sized

### For Reviewers

- Be constructive and specific
- Explain the "why" not just "what"
- Approve when ready, request changes when needed
- Respond promptly

## Testing Integration with Services

### Redis

```bash
# Start Redis with Docker
docker run -d -p 6379:6379 redis

# Run Redis tests
pytest -m redis_required
```

### PostgreSQL

```bash
# Start PostgreSQL with Docker
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres

# Run PostgreSQL tests
pytest -m postgres_required
```

### All Services

```bash
# Use docker-compose (if available)
docker-compose up -d

# Run all integration tests
pytest -m integration
```

## Release Process (Maintainers Only)

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Run full test suite
4. Build: `python -m build`
5. Test on TestPyPI
6. Publish to PyPI: `twine upload dist/*`
7. Tag release: `git tag v1.0.0`
8. Create GitHub release

## Questions?

- **General Questions**: [GitHub Discussions](https://github.com/vladlen-codes/ratelink/discussions)
- **Bug Reports**: [GitHub Issues](https://github.com/vladlen-codes/ratelink/issues)
- **Security Issues**: Email vladlen.codes@gmail.com (do not open public issues)

## Recognition

Contributors are listed in:
- GitHub contributors page
- Release notes
- Documentation acknowledgments

Thank you for contributing to Ratelink! 🎉
