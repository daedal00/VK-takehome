# Docker Deployment Guide

This guide explains how to run the Async Data Pipeline using Docker and Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+

## Quick Start

Run the complete system (3 mock servers + pipeline):

```bash
docker compose up --build
```

This will:

1. Build the Docker image with Python 3.13 and uv
2. Start 3 mock API servers on ports 8001, 8002, 8003
3. Wait for all servers to be healthy
4. Run the pipeline to fetch and process data
5. Generate `out/summary.json` with results

## Architecture

```
┌─────────────────┐
│  mock-server-1  │ :8001
└────────┬────────┘
         │
┌────────┴────────┐
│  mock-server-2  │ :8002
└────────┬────────┘
         │
┌────────┴────────┐
│  mock-server-3  │ :8003
└────────┬────────┘
         │
    ┌────┴─────┐
    │ pipeline │
    └──────────┘
         │
    ┌────┴─────┐
    │ out/     │
    └──────────┘
```

## Running Individual Components

### Run Only Mock Servers

```bash
docker compose up mock-server-1 mock-server-2 mock-server-3
```

### Run Pipeline Against Running Servers

```bash
# In one terminal
docker compose up mock-server-1 mock-server-2 mock-server-3

# In another terminal
docker compose up pipeline
```

### Run Pipeline with Custom Configuration

```bash
docker compose run --rm pipeline \
  python -m src.pipeline.main \
  --timeout 120 \
  --rate-limit 10 \
  --log-level DEBUG
```

## Configuration

### Environment Variables

Override configuration via environment variables in `docker-compose.yml`:

```yaml
environment:
  - PIPELINE_TIMEOUT=120
  - PIPELINE_RATE_LIMIT_RPS=10
  - PIPELINE_WORKER_POOL_SIZE=8
  - PIPELINE_LOG_LEVEL=DEBUG
```

### Mock Server Configuration

Each mock server can be configured independently:

```yaml
environment:
  - SERVER_NAME=api1
  - SERVER_PORT=8001
  - RANDOM_SEED=42 # For deterministic behavior
  - ERROR_RATE=0.1 # 10% error rate
  - EXTRA_LATENCY_MS=0 # Additional latency
  - PAGES=5 # Number of pages
  - ITEMS_PER_PAGE=20 # Items per page
```

## Health Checks

All mock servers include health check endpoints:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

The pipeline waits for all servers to be healthy before starting.

## Output

Results are written to `./out/summary.json` via volume mount:

```yaml
volumes:
  - ./out:/app/out
```

## Networking

All services communicate via the `pipeline-network` bridge network:

- Mock servers are accessible by service name (e.g., `http://mock-server-1:8001`)
- Pipeline uses `config/config.docker.yaml` with docker service names

## Troubleshooting

### View Logs

```bash
# All services
docker compose logs

# Specific service
docker compose logs pipeline
docker compose logs mock-server-1

# Follow logs
docker compose logs -f pipeline
```

### Check Service Health

```bash
docker compose ps
```

### Rebuild After Code Changes

```bash
docker compose up --build
```

### Clean Up

```bash
# Stop and remove containers
docker compose down

# Remove volumes
docker compose down --volumes

# Remove images
docker compose down --rmi all
```

## Development Workflow

1. Make code changes
2. Rebuild and test:
   ```bash
   docker compose up --build
   ```
3. Check output:
   ```bash
   cat out/summary.json
   ```
4. View logs if needed:
   ```bash
   docker compose logs pipeline
   ```

## Production Considerations

For production deployment:

1. **Use specific image tags** instead of `latest`
2. **Set resource limits** in docker-compose.yml:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: "1.0"
         memory: 512M
   ```
3. **Configure logging drivers** for centralized logging
4. **Use secrets** for sensitive configuration
5. **Enable monitoring** with Prometheus/Grafana
6. **Set up health check alerts**

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
- name: Run pipeline with Docker
  run: |
    docker compose up --build --abort-on-container-exit
    test -f out/summary.json
```

## Performance

Expected performance with default configuration:

- **Execution Time:** < 60 seconds
- **Memory Usage:** ~200MB per container
- **Network:** ~5 requests/second per endpoint
- **Output:** 300+ products from 3 endpoints
