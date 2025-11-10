"""End-to-end integration test for async fetcher."""

import asyncio
import pytest
import httpx

from src.fetcher.async_fetcher import AsyncFetcher
from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_single_endpoint_e2e():
    """Test fetching from a single mock endpoint end-to-end."""
    
    # Mock transport simulating 3 pages of data
    def handler(request):
        page = int(request.url.params.get("page", 1))
        
        if page > 3:
            return httpx.Response(204)  # No more pages
        
        products = [{"id": i, "name": f"Product {i}", "price": 10.0} for i in range(20)]
        return httpx.Response(200, json={"products": products, "page": page, "total_pages": 3})
    
    transport = httpx.MockTransport(handler)
    
    rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0)
    circuit_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0)
    
    async with AsyncHTTPClient() as http_client:
        http_client._client = httpx.AsyncClient(transport=transport)
        
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        queue = asyncio.Queue(maxsize=100)
        
        stats = await fetcher.fetch_endpoint_pages("http://test.com", queue)
        
        assert stats.pages_fetched == 3
        assert stats.items_fetched == 60
        assert stats.errors == 0
        assert queue.qsize() == 3


@pytest.mark.integration  
@pytest.mark.asyncio
async def test_fetch_handles_pagination_termination():
    """Test that fetcher stops at last page (204 response)."""
    
    def handler(request):
        page = int(request.url.params.get("page", 1))
        
        if page > 2:
            return httpx.Response(204)
        
        products = [{"id": i, "name": f"Product {i}"} for i in range(20)]
        return httpx.Response(200, json={"products": products, "page": page})
    
    transport = httpx.MockTransport(handler)
    
    rate_limiter = RateLimiter()
    circuit_breaker = CircuitBreaker()
    
    async with AsyncHTTPClient() as http_client:
        http_client._client = httpx.AsyncClient(transport=transport)
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        
        queue = asyncio.Queue(maxsize=100)
        stats = await fetcher.fetch_endpoint_pages("http://test.com", queue)
        
        assert stats.pages_fetched == 2
        assert stats.items_fetched == 40


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_multiple_endpoints_concurrently():
    """Test fetching from multiple endpoints concurrently."""
    
    def handler(request):
        page = int(request.url.params.get("page", 1))
        
        if page > 2:
            return httpx.Response(204)
        
        products = [{"id": i, "name": f"Product {i}"} for i in range(20)]
        return httpx.Response(200, json={"products": products, "page": page})
    
    transport = httpx.MockTransport(handler)
    
    rate_limiter = RateLimiter()
    circuit_breaker = CircuitBreaker()
    
    async with AsyncHTTPClient() as http_client:
        http_client._client = httpx.AsyncClient(transport=transport)
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        
        queue = asyncio.Queue(maxsize=100)
        
        # Fetch from multiple endpoints
        stats_dict = await fetcher.fetch_all_endpoints(
            ["http://server1.com", "http://server2.com"],
            queue
        )
        
        assert len(stats_dict) == 2
        assert all(s.pages_fetched == 2 for s in stats_dict.values())
        assert all(s.items_fetched == 40 for s in stats_dict.values())
