# Async Data Pipeline

A production-ready concurrent data processing system demonstrating advanced Python async programming, resilience patterns, and professional software engineering practices.

> **📚 Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md) • [DECISIONS.md](DECISIONS.md) • [AI_USAGE.md](AI_USAGE.md)

## Quick Start (30 seconds)

```bash
# Install dependencies
uv sync

# Start mock API servers
docker compose -f docker/docker-compose.yml up -d

# Run pipeline
uv run python -m src.pipeline.main

# View results
cat out/summary.json

# Stop servers when done
docker compose -f docker/docker-compose.yml down
```

## Overview

This pipeline fetches product data from multiple mock e-commerce APIs concurrently, processes and normalizes the data using worker pools, and outputs structured JSON results. The system showcases:

- **Concurrent API Fetching**: Async requests to 3 mock endpoints with rate limiting (5 req/sec per endpoint)
- **Resilience Patterns**: Circuit breakers, exponential backoff retries, graceful degradation
- **Flexible Data Normalization**: Handles heterogeneous schemas (nested objects, string prices, missing fields)
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

### CI/CD

GitHub Actions runs automatically on all PRs:

- ✅ **Test Suite**: All tests must pass (194 tests)
- 📊 **Coverage Report**: 91.6% coverage (exceeds 80% requirement)
- 📦 **Artifacts**: HTML coverage reports available for download

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

✅ **Performance**: Process 300+ products from 3 endpoints within 60 seconds  
✅ **Quality**: 91.6% test coverage (exceeds 80% requirement) with 194 comprehensive tests  
✅ **Resilience**: Handle partial failures gracefully with circuit breakers and retries  
✅ **Production-Ready**: Structured logging, bounded queues, graceful shutdown

## Project Structure

```
async-data-pipeline/
├── src/
│   ├── pipeline/          # Orchestration and CLI
│   ├── fetcher/           # Async fetching with resilience
│   ├── processor/         # Data processing and normalization
│   ├── mock_servers/      # FastAPI mock APIs
│   └── models/            # Data models and configuration
├── tests/
│   ├── unit/              # Fast unit tests (172 tests)
│   ├── integration/       # E2E tests (22 tests)
│   ├── fixtures/          # Deterministic test data
│   └── test_performance.py # Performance benchmarks (15 tests)
├── docker/                # Docker compose configurations
├── config/                # Configuration files
└── out/                   # Pipeline output (summary.json)
```

## Documentation

- **[REQUIREMENTS.md](REQUIREMENTS.md)**: Complete requirements with acceptance criteria
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System design and component overview
- **[DECISIONS.md](DECISIONS.md)**: Technical decisions and tradeoffs
- **[AI_USAGE.md](AI_USAGE.md)**: AI tool usage transparency
