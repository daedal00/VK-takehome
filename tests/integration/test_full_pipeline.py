"""Full pipeline integration test: fetcher → queue → processor."""

import asyncio
import pytest
import httpx

from src.fetcher.async_fetcher import AsyncFetcher
from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.processor import DataProcessor


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_fetcher_to_processor():
    """Test complete pipeline: fetch → queue → process → metrics."""
    
    # Mock 2 endpoints with different data
    def handler(request):
        page = int(request.url.params.get("page", 1))
        
        if page > 2:
            return httpx.Response(204)
        
        # Different data per endpoint
        if "server1" in str(request.url):
            products = [
                {"id": i, "name": f"Electronics {i}", "price": 100.0 + i, "category": "electronics"}
                for i in range(10)
            ]
        else:
            products = [
                {"id": i, "name": f"Book {i}", "price": 20.0 + i, "category": "books"}
                for i in range(10)
            ]
        
        return httpx.Response(200, json={"products": products, "page": page})
    
    transport = httpx.MockTransport(handler)
    
    # Create components
    rate_limiter = RateLimiter()
    circuit_breaker = CircuitBreaker()
    processor = DataProcessor(worker_pool_size=2)
    
    async with AsyncHTTPClient() as http_client:
        http_client._client = httpx.AsyncClient(transport=transport)
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        
        # Create bounded queue
        queue = asyncio.Queue(maxsize=100)
        
        # Start processor task
        processor_task = asyncio.create_task(
            processor.consume_queue(queue, sentinel=None)
        )
        
        # Fetch from 2 endpoints
        endpoints = ["http://server1.com", "http://server2.com"]
        stats_dict = await fetcher.fetch_all_endpoints(endpoints, queue)
        
        # Send sentinel to stop processor
        await queue.put(None)
        
        # Wait for processor to finish
        processor_stats = await processor_task
        
        # Verify fetcher stats
        assert len(stats_dict) == 2
        assert all(s.pages_fetched == 2 for s in stats_dict.values())
        assert all(s.items_fetched == 20 for s in stats_dict.values())
        
        # Verify processor stats
        assert processor_stats.products_processed == 40  # 2 endpoints * 2 pages * 10 items
        assert processor_stats.batches_processed == 4  # 2 endpoints * 2 pages
        
        # Verify normalized products
        products = processor.get_products()
        assert len(products) == 40
        
        # Check product schema
        product = products[0]
        assert ":" in product.id  # Format: source:id
        assert product.title is not None
        assert product.source in ["http://server1.com", "http://server2.com"]
        assert product.processed_at is not None
        
        # Verify metrics
        metrics = processor.calculate_metrics()
        assert len(metrics["sources"]) == 2
        assert len(metrics["categories"]) == 2
        
        # Check avg prices (server1: ~105, server2: ~25)
        assert metrics["sources"]["http://server1.com"] > 100
        assert metrics["sources"]["http://server2.com"] < 30
        
        # Check category counts
        assert metrics["categories"]["electronics"] == 20
        assert metrics["categories"]["books"] == 20


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_handles_empty_queue():
    """Test processor handles empty queue gracefully."""
    
    processor = DataProcessor()
    queue = asyncio.Queue()
    
    # Immediately send sentinel
    await queue.put(None)
    
    stats = await processor.consume_queue(queue, sentinel=None)
    
    assert stats.products_processed == 0
    assert stats.batches_processed == 0
    assert len(processor.get_products()) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_memory_bounded():
    """Test that bounded queue prevents memory overflow."""
    
    # Small queue to test backpressure
    queue = asyncio.Queue(maxsize=2)
    
    # Producer (fast)
    async def producer():
        for i in range(10):
            await queue.put({"data": {"products": [{"id": i}]}, "endpoint": "test"})
        await queue.put(None)
    
    # Consumer (slow)
    processor = DataProcessor()
    
    async def consumer():
        return await processor.consume_queue(queue, sentinel=None)
    
    # Run concurrently
    producer_task = asyncio.create_task(producer())
    consumer_task = asyncio.create_task(consumer())
    
    await asyncio.gather(producer_task, consumer_task)
    
    # Verify all items processed
    assert len(processor.get_products()) == 10
