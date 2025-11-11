"""True end-to-end test with real FastAPI servers."""

import asyncio
import pytest
import httpx
from multiprocessing import Process
import time
import uvicorn

from src.fetcher.async_fetcher import AsyncFetcher
from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.mock_servers import create_server_a


def run_server(port: int):
    """Run FastAPI server in separate process."""
    app = create_server_a()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_end_to_end_with_running_server():
    """Test with actual FastAPI server running."""
    
    # Start server in background process
    port = 8001
    server_process = Process(target=run_server, args=(port,))
    server_process.start()
    
    # Wait for server to start
    await asyncio.sleep(1)
    
    try:
        # Create components
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0)
        circuit_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0)
        
        async with AsyncHTTPClient() as http_client:
            fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
            
            # Create bounded queue
            queue = asyncio.Queue(maxsize=100)
            
            # Fetch from real server
            endpoint = f"http://127.0.0.1:{port}"
            stats = await fetcher.fetch_endpoint_pages(endpoint, queue)
            
            # Verify we got data
            assert stats.pages_fetched > 0
            assert stats.items_fetched > 0
            assert stats.errors == 0
            
            # Verify queue has pages
            assert queue.qsize() > 0
            
            # Check first page structure
            page_data = await queue.get()
            assert "endpoint" in page_data
            assert "page" in page_data
            assert "data" in page_data
            assert "products" in page_data["data"]
            
            print(f"\n✅ Real E2E Test Results:")
            print(f"   Pages fetched: {stats.pages_fetched}")
            print(f"   Items fetched: {stats.items_fetched}")
            print(f"   Duration: {stats.total_duration:.2f}s")
            print(f"   Errors: {stats.errors}")
            
    finally:
        # Cleanup
        server_process.terminate()
        server_process.join(timeout=2)
        if server_process.is_alive():
            server_process.kill()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_before_fetch():
    """Verify server health before running full test."""
    
    port = 8002
    server_process = Process(target=run_server, args=(port,))
    server_process.start()
    
    await asyncio.sleep(1)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{port}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            print(f"\n✅ Health check passed: {data}")
            
    finally:
        server_process.terminate()
        server_process.join(timeout=2)
        if server_process.is_alive():
            server_process.kill()
