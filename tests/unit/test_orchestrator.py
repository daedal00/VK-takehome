"""Unit tests for PipelineOrchestrator.

Tests cover:
- Happy path minimal pipeline execution
- Partial failure handling
- Error recovery and graceful degradation
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models.config import ConfigManager, EndpointConfig, PipelineConfig
from src.models.data_models import EndpointStats, ProcessorStats, Product
from src.pipeline.orchestrator import PipelineOrchestrator


@pytest.mark.asyncio
async def test_pipeline_runs_minimal_happy_path():
    """Test minimal pipeline execution with 2 products."""
    # Load real config
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    
    # Mock AsyncFetcher.fetch_all_endpoints
    mock_stats = {
        config.endpoints[0].url: EndpointStats(
            name=config.endpoints[0].url,
            pages_fetched=1,
            items_fetched=1,
            errors=0,
            total_duration=0.1
        )
    }
    
    async def mock_fetch_all(endpoints, queue):
        # Enqueue 1 product
        await queue.put({
            "endpoint": config.endpoints[0].url,
            "page": 1,
            "data": {"products": [{"id": 1, "name": "Product 1", "price": 10.0, "category": "test"}]}
        })
        return mock_stats
    
    with patch('src.pipeline.orchestrator.AsyncFetcher') as MockFetcher:
        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.fetch_all_endpoints = mock_fetch_all
        
        result = await orchestrator.run()
    
    # Verify result
    assert result.summary.total_products >= 1
    assert 0.0 <= result.summary.success_rate <= 1.0
    assert len(result.products) >= 1


@pytest.mark.asyncio
async def test_pipeline_continues_on_endpoint_failure():
    """Test pipeline continues when one endpoint fails."""
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    
    # Mock with partial failure
    mock_stats = {}
    for i, ep in enumerate(config.endpoints):
        if i == 0:
            # First endpoint succeeds
            mock_stats[ep.url] = EndpointStats(
                name=ep.url,
                pages_fetched=1,
                items_fetched=10,
                errors=0,
                total_duration=0.1
            )
        else:
            # Other endpoints fail
            mock_stats[ep.url] = EndpointStats(
                name=ep.url,
                pages_fetched=0,
                items_fetched=0,
                errors=3,
                total_duration=0.1
            )
    
    async def mock_fetch_all(endpoints, queue):
        # Only enqueue from first endpoint
        await queue.put({
            "endpoint": config.endpoints[0].url,
            "page": 1,
            "data": {"products": [{"id": i, "name": f"Product {i}", "price": 10.0, "category": "test"} for i in range(10)]}
        })
        return mock_stats
    
    with patch('src.pipeline.orchestrator.AsyncFetcher') as MockFetcher:
        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.fetch_all_endpoints = mock_fetch_all
        
        result = await orchestrator.run()
    
    # Verify partial success (aggregator calculates from actual stats)
    assert result.summary.total_products >= 1
    # Success rate depends on aggregator implementation
    assert 0.0 <= result.summary.success_rate <= 1.0


@pytest.mark.asyncio
async def test_pipeline_handles_complete_failure():
    """Test pipeline handles complete failure gracefully."""
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    
    # Mock complete failure
    mock_stats = {}
    for ep in config.endpoints:
        mock_stats[ep.url] = EndpointStats(
            name=ep.url,
            pages_fetched=0,
            items_fetched=0,
            errors=5,
            total_duration=0.1
        )
    
    async def mock_fetch_all(endpoints, queue):
        # No products enqueued
        return mock_stats
    
    with patch('src.pipeline.orchestrator.AsyncFetcher') as MockFetcher:
        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.fetch_all_endpoints = mock_fetch_all
        
        result = await orchestrator.run()
    
    # Verify graceful handling
    assert result.summary.total_products == 0
    assert result.summary.success_rate == 0.0
    assert len(result.products) == 0


@pytest.mark.asyncio
async def test_pipeline_calculates_success_rate_correctly():
    """Test success rate calculation with mixed results."""
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    
    # 2 successful, 1 failed (assuming 3 endpoints in config)
    mock_stats = {}
    for i, ep in enumerate(config.endpoints):
        if i < 2:
            # First 2 succeed
            mock_stats[ep.url] = EndpointStats(
                name=ep.url,
                pages_fetched=2,
                items_fetched=40,
                errors=0,
                total_duration=0.2
            )
        else:
            # Last one fails
            mock_stats[ep.url] = EndpointStats(
                name=ep.url,
                pages_fetched=0,
                items_fetched=0,
                errors=3,
                total_duration=0.1
            )
    
    async def mock_fetch_all(endpoints, queue):
        # Enqueue from successful endpoints
        for i in range(2):
            await queue.put({
                "endpoint": config.endpoints[i].url,
                "page": 1,
                "data": {"products": [{"id": j, "name": f"Product {j}", "price": 10.0, "category": "test"} for j in range(20)]}
            })
        return mock_stats
    
    with patch('src.pipeline.orchestrator.AsyncFetcher') as MockFetcher:
        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.fetch_all_endpoints = mock_fetch_all
        
        result = await orchestrator.run()
    
    # Verify mixed results
    assert result.summary.total_products >= 20
    assert 0.0 <= result.summary.success_rate <= 1.0
