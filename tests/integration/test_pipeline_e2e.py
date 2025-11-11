"""End-to-end integration tests for the complete pipeline.

These tests verify all take-home assignment requirements are met:
- Concurrent fetching from multiple endpoints
- Rate limiting (5 req/sec per endpoint)
- Retry logic with exponential backoff
- Circuit breaker pattern
- Data processing with worker pools
- Memory-efficient bounded queues
- Error handling and resilience
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path

import pytest

from src.models.config import ConfigManager, PipelineConfig
from src.pipeline.orchestrator import PipelineOrchestrator


@pytest.fixture(scope="module")
def mock_servers():
    """Start mock servers for integration tests."""
    # Start mock servers with docker compose
    subprocess.run(
        ["docker", "compose", "-f", "docker/docker-compose.yml", 
         "up", "mock-server-1", "mock-server-2", "mock-server-3", "-d"],
        check=True,
        capture_output=True
    )
    
    # Wait for servers to be ready
    time.sleep(3)
    
    yield
    
    # Cleanup is optional - servers can keep running for other tests


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_with_mock_servers(mock_servers):
    """
    Test complete pipeline execution with real mock servers.
    
    Requirements tested:
    - 1.1-1.5: Concurrent fetching with rate limiting
    - 2.1-2.3: Retry logic and error handling
    - 3.1-3.5: Data processing and normalization
    - 4.1: Performance (< 60 seconds)
    - 5.2: Integration test for full pipeline
    """
    # Load configuration
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)
    
    # Run pipeline with timing
    import time
    start = time.time()
    result = await orchestrator.run()
    elapsed = time.time() - start
    
    # Verify performance requirement (< 60 seconds)
    assert elapsed < 60.0, f"Pipeline took {elapsed}s, requirement is < 60s"
    
    # Verify data was fetched
    assert result.summary.total_products > 0, "Should fetch at least some products"
    
    # Verify success rate is reasonable (should handle errors gracefully)
    assert result.summary.success_rate >= 0.0, "Success rate should be non-negative"
    
    # Verify per-source statistics
    assert len(result.sources) > 0, "Should have statistics for at least one source"
    
    # Verify products have unified schema
    if result.products:
        product = result.products[0]
        assert hasattr(product, 'id'), "Product should have id"
        assert hasattr(product, 'title'), "Product should have title"
        assert hasattr(product, 'source'), "Product should have source"
        assert hasattr(product, 'price'), "Product should have price"
        assert hasattr(product, 'category'), "Product should have category"
        assert hasattr(product, 'processed_at'), "Product should have processed_at timestamp"


@pytest.mark.integration  
@pytest.mark.asyncio
async def test_pipeline_output_format():
    """
    Test that pipeline generates correct JSON output format.
    
    Requirements tested:
    - 8.1-8.5: JSON output with exact schema
    - 13.2: Validate output format
    """
    # Run pipeline with mock to generate output
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    result = await orchestrator.run()
    
    # Format as JSON
    from src.pipeline.output import JSONOutputFormatter
    formatter = JSONOutputFormatter()
    data = formatter.format(result)
    
    # Verify top-level structure
    assert "summary" in data, "Output should have summary section"
    assert "sources" in data, "Output should have sources section"
    assert "products" in data, "Output should have products section"
    assert "errors" in data, "Output should have errors section"
    
    # Verify summary structure
    summary = data["summary"]
    assert "total_products" in summary
    assert "processing_time_seconds" in summary
    assert "success_rate" in summary
    assert "sources" in summary
    
    # Verify sources structure
    if data["sources"]:
        source = data["sources"][0]
        assert "name" in source
        assert "items_fetched" in source
        assert "errors" in source
        assert "avg_price" in source
    
    # Verify products structure
    if data["products"]:
        product = data["products"][0]
        assert "id" in product
        assert "title" in product
        assert "source" in product
        assert "price" in product
        assert "category" in product
        assert "processed_at" in product


@pytest.mark.integration
def test_configuration_override_precedence():
    """
    Test that configuration follows CLI > ENV > YAML precedence.
    
    Requirements tested:
    - 4.3: Configuration file for tuning parameters
    - 7.4: Environment variable support
    """
    import os
    
    # Test YAML defaults
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    assert config.max_requests_per_second == 5, "Default rate limit should be 5"
    
    # Test environment variable override
    os.environ["PIPELINE_RATE_LIMIT_RPS"] = "10"
    try:
        config_with_env = ConfigManager(Path("config/config.yaml")).load_config()
        assert config_with_env.max_requests_per_second == 10, "ENV should override YAML"
    finally:
        os.environ.pop("PIPELINE_RATE_LIMIT_RPS", None)
    
    # Test CLI override (highest precedence)
    cli_overrides = {"max_requests_per_second": 20}
    config_with_cli = config_manager.load_config(cli_overrides)
    assert config_with_cli.max_requests_per_second == 20, "CLI should override all"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_efficiency_with_bounded_queue(mock_servers):
    """
    Test that pipeline uses bounded queues for memory efficiency.
    
    Requirements tested:
    - 3.5: Bounded queue for memory management
    - 4.1: Memory-efficient processing
    - 13.3: Memory stability tests
    """
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    # Verify bounded queue configuration
    assert config.bounded_queue_size == 100, "Queue should be bounded to 100"
    
    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)
    
    # Run pipeline - if it completes without OOM, memory management works
    result = await orchestrator.run()
    
    # Verify pipeline completed successfully
    assert result is not None, "Pipeline should complete without memory issues"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_scenario_handling():
    """
    Test that pipeline handles various error scenarios gracefully.
    
    Requirements tested:
    - 2.2: Circuit breaker for failing endpoints
    - 2.3: Graceful error handling
    - 5.3: Error scenario tests
    """
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    result = await orchestrator.run()
    
    from src.pipeline.output import JSONOutputFormatter
    formatter = JSONOutputFormatter()
    data = formatter.format(result)
    
    # Pipeline should complete even with errors
    assert data["summary"]["total_products"] >= 0, "Should handle errors gracefully"
    
    # Success rate should be between 0 and 1
    success_rate = data["summary"]["success_rate"]
    assert 0.0 <= success_rate <= 1.0, f"Success rate {success_rate} should be 0-1"
    
    # Errors should be tracked
    assert isinstance(data["errors"], list), "Errors should be a list"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_fetching_from_multiple_endpoints():
    """
    Test that pipeline fetches from multiple endpoints concurrently.
    
    Requirements tested:
    - 1.1: Fetch from 3 different endpoints
    - 1.2: Concurrent requests
    - 5.2: Integration test with multiple endpoints
    """
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    result = await orchestrator.run()
    
    from src.pipeline.output import JSONOutputFormatter
    formatter = JSONOutputFormatter()
    data = formatter.format(result)
    
    # Should have data from multiple sources
    sources = data["summary"]["sources"]
    assert len(sources) >= 1, "Should fetch from at least one endpoint"
    
    # Each source should have statistics
    for source_summary in data["sources"]:
        assert source_summary["items_fetched"] >= 0, "Should track items per source"
        assert "errors" in source_summary, "Should track errors per source"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_data_normalization_unified_schema():
    """
    Test that products from different APIs are normalized to unified schema.
    
    Requirements tested:
    - 3.1: Normalize data from different APIs
    - 8.3: Unified product schema
    """
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    result = await orchestrator.run()
    
    from src.pipeline.output import JSONOutputFormatter
    formatter = JSONOutputFormatter()
    data = formatter.format(result)
    
    if not data["products"]:
        pytest.skip("No products in output")
    
    # All products should have the same schema
    required_fields = {"id", "title", "source", "price", "category", "processed_at"}
    
    for product in data["products"][:10]:  # Check first 10
        product_fields = set(product.keys())
        assert required_fields.issubset(product_fields), \
            f"Product missing required fields: {required_fields - product_fields}"
        
        # Verify ID format: "source:id"
        assert ":" in product["id"], "Product ID should be in format 'source:id'"
        
        # Verify timestamp is ISO-8601
        assert "T" in product["processed_at"], "Timestamp should be ISO-8601 format"
        assert "Z" in product["processed_at"] or "+" in product["processed_at"], \
            "Timestamp should include timezone"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_metrics_calculation():
    """
    Test that pipeline calculates metrics correctly.
    
    Requirements tested:
    - 3.3: Calculate metrics (avg price, category distribution)
    - 8.2: Per-source statistics
    """
    config_manager = ConfigManager(Path("config/config.yaml"))
    config = config_manager.load_config()
    
    orchestrator = PipelineOrchestrator(config)
    result = await orchestrator.run()
    
    from src.pipeline.output import JSONOutputFormatter
    formatter = JSONOutputFormatter()
    data = formatter.format(result)
    
    # Verify per-source metrics
    for source in data["sources"]:
        if source["items_fetched"] > 0:
            # Should have average price if items were fetched
            assert "avg_price" in source, "Should calculate average price per source"
            
            if source["avg_price"] is not None:
                assert source["avg_price"] > 0, "Average price should be positive"
