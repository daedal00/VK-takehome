# Async Data Pipeline - Production Dockerfile
# Python 3.13 with uv for fast dependency management

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create output directory
RUN mkdir -p /app/out

# Set default command (use docker config)
CMD ["python", "-m", "src.pipeline.main", "--config", "config/config.docker.yaml", "--no-progress"]
