.PHONY: help install test test-unit test-integration lint format clean docker-build docker-up docker-down docker-dev-up docker-dev-down manual-test up demo

help: ## Show this help message
	@echo '🚀 Async Data Pipeline - Quick Commands'
	@echo ''
	@echo '⚡ Quick Start (30 seconds):'
	@echo '  make up          # Build and run complete system'
	@echo '  make test        # Run all tests'
	@echo '  make demo        # Show failure scenarios'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Quick start commands
up: docker-up ## Quick start: Build and run complete system

demo: ## Run failure scenario demonstrations
	./demo_failure_scenarios.sh

install: ## Install dependencies with uv
	uv sync

test: ## Run all tests
	uv run pytest

test-unit: ## Run unit tests only
	uv run pytest tests/unit/ -v

test-integration: ## Run integration tests only
	uv run pytest tests/integration/ -v -m integration

test-coverage: ## Run tests with coverage report
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

clean: ## Clean up generated files
	rm -rf __pycache__ .pytest_cache .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf out/*.json

# Docker commands
docker-build: ## Build Docker images
	cd docker && docker compose build

docker-up: ## Run full pipeline with Docker (mock servers + pipeline)
	cd docker && docker compose up --build

docker-down: ## Stop and remove Docker containers
	cd docker && docker compose down

docker-dev-up: ## Start mock servers only (for development)
	cd docker && docker compose -f docker-compose.dev.yml up --build -d

docker-dev-down: ## Stop mock servers
	cd docker && docker compose -f docker-compose.dev.yml down

docker-logs: ## View Docker logs
	cd docker && docker compose logs -f

# Manual testing
manual-test: ## Run manual test script (requires mock servers running)
	@echo "Starting mock servers..."
	@make docker-dev-up
	@echo "Waiting for servers to be ready..."
	@sleep 5
	@echo "Running manual test..."
	uv run python manual_test.py
	@echo "Stopping mock servers..."
	@make docker-dev-down

# Development workflow
dev: docker-dev-up ## Start development environment (mock servers)
	@echo "Mock servers running on ports 8001, 8002, 8003"
	@echo "Run 'make docker-dev-down' to stop"

run: ## Run pipeline locally (requires mock servers)
	uv run python -m src.pipeline.main

run-no-progress: ## Run pipeline without progress bars
	uv run python -m src.pipeline.main --no-progress
