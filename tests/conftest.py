"""Pytest configuration and shared fixtures."""

import pytest
import random
import asyncio
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def deterministic_seed():
    """Set a fixed random seed for deterministic test results."""
    random.seed(42)
    return 42


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_config():
    """Provide a sample configuration for testing."""
    from src.models.config import PipelineConfig
    
    return PipelineConfig(
        max_requests_per_second=5,
        rate_limit_tokens=5,
        max_retries=3,
        retry_base_delay=0.5,
        retry_max_delay=4.0,
        connect_timeout=3.0,
        read_timeout=8.0,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_cooldown=15.0,
        worker_pool_size=4,
        processing_batch_size=50,
        bounded_queue_size=100,
        total_timeout=60.0,
    )
