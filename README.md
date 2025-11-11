# Async Data Pipeline

A concurrent data processing system that demonstrates advanced Python async programming, resilience patterns, and professional software engineering practices.

> **📚 Deep Dive**: See [ARCHITECTURE.md](ARCHITECTURE.md) for system design, [DECISIONS.md](DECISIONS.md) for trade-off analysis, and [AI_USAGE.md](AI_USAGE.md) for AI tool usage.

## Quick Start (30 seconds)

```bash
# Install dependencies
uv sync

# Run the complete system with Docker
docker compose -f docker/docker-compose.yml up --build

# Or run locally (requires mock servers running)
# Start mock servers
docker compose -f docker/docker-compose.yml up mock-server-1 mock-server-2 mock-server-3 -d

# Run pipeline
uv run python -m src.pipeline.main

# View results
cat out/summary.json
```

## Overview

This pipeline fetches product data from multiple mock e-commerce APIs concurrently, processes and normalizes the data using worker pools, and outputs structured JSON results. The system showcases:

- **Concurrent API Fetching**: Async requests to 3 mock endpoints with rate limiting (5 req/sec per endpoint)
- **Resilience Patterns**: Circuit breakers, exponential backoff retries, graceful degradation
- **Data Processing**: ThreadPoolExecutor-based normalization with unified product schema
- **Memory Management**: Bounded queues prevent memory overflow during processing
- **Monitoring**: Structured logging, performance metrics, and CLI progress indicators

## Architecture

The system consists of three main layers:

1. **FastAPI Mock Servers**: Realistic e-commerce API simulation with configurable behavior
2. **Async Fetching Layer**: Rate limiting, circuit breakers, and retry logic
3. **Processing Layer**: Worker pools for data normalization and metrics calculation

## Requirements

- Python 3.13+
- uv for dependency management
- Docker and Docker Compose (for full system)

## Development

### Running Tests

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/test_rate_limiter.py -v
```

### Code Quality (Optional - Run Before Committing)

```bash
# Format code
uv run black src/ tests/

# Lint code
uv run ruff check src/ tests/

# Type checking
uv run mypy src/
```

### CI/CD

GitHub Actions runs automatically on all PRs:

- ✅ **Test Suite**: All tests must pass
- 📊 **Coverage Report**: Generated and uploaded (no threshold enforced yet)
- 📦 **Artifacts**: HTML coverage reports available for download

**Philosophy**: During early development, we focus on test correctness rather than enforcing coverage thresholds or auto-formatting. This keeps PRs clean and focused on feature implementation.

## Configuration

Configuration follows override precedence: **CLI flags > Environment variables > config.yaml**

Example override:

```bash
# Override rate limit via environment
PIPELINE_RATE_LIMIT_RPS=10 uv run python -m src.pipeline.main

# Override via CLI flag
uv run python -m src.pipeline.main --rate-limit 10
```

Key environment variables:

- `PIPELINE_TIMEOUT`: Total execution timeout (default: 60s)
- `PIPELINE_RATE_LIMIT_RPS`: Requests per second per endpoint (default: 5)
- `PIPELINE_WORKER_POOL_SIZE`: Processing thread count (default: 4)

## Output

The pipeline generates `out/summary.json` with:

- Summary statistics (total products, processing time, success rate)
- Per-source statistics (items fetched, errors, average price)
- Normalized product data with unified schema
- Structured error information

## Resilience Demonstration

See the resilience patterns in action:

```bash
make demo
```

This runs failure scenarios showing:

- Circuit breaker opening after 3 failures
- Exponential backoff retries (0.5s → 1s → 2s)
- Rate limiting at exactly 5 req/sec
- Graceful degradation with partial failures

## Success Criteria

- Process 300+ products from 3 endpoints within 60 seconds
- Maintain 80%+ test coverage with comprehensive error scenario testing
- Handle partial failures gracefully without crashing the entire pipeline
