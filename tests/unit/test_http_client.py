"""Unit tests for HTTP client wrapper."""

import pytest
import httpx

from src.fetcher.http_client import AsyncHTTPClient


class TestAsyncHTTPClient:
    
    @pytest.mark.asyncio
    async def test_initialization_with_defaults(self):
        async with AsyncHTTPClient() as client:
            assert client.connect_timeout == 3.0
            assert client.read_timeout == 8.0
    
    @pytest.mark.asyncio
    async def test_initialization_with_custom_timeouts(self):
        async with AsyncHTTPClient(connect_timeout=5.0, read_timeout=10.0) as client:
            assert client.connect_timeout == 5.0
            assert client.read_timeout == 10.0
    
    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(self):
        client = AsyncHTTPClient()
        
        async with client:
            assert client._client is not None
        
        # Client should be closed after context exit
        assert client._client is None
    
    @pytest.mark.asyncio
    async def test_get_request_with_mock_transport(self):
        # Mock transport for testing without network
        def handler(request):
            return httpx.Response(200, json={"status": "ok"})
        
        transport = httpx.MockTransport(handler)
        
        async with AsyncHTTPClient() as client:
            client._client = httpx.AsyncClient(transport=transport)
            response = await client.get("http://test.com/api")
            
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
    
    @pytest.mark.asyncio
    async def test_get_request_with_params(self):
        def handler(request):
            # Verify params are passed
            assert "page=1" in str(request.url)
            return httpx.Response(200, json={"page": 1})
        
        transport = httpx.MockTransport(handler)
        
        async with AsyncHTTPClient() as client:
            client._client = httpx.AsyncClient(transport=transport)
            response = await client.get("http://test.com/api", params={"page": 1})
            
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_timeout_configuration_applied(self):
        async with AsyncHTTPClient(connect_timeout=5.0, read_timeout=10.0) as client:
            # Verify timeout is configured in the underlying client
            timeout = client._client.timeout
            assert timeout.connect == 5.0
            assert timeout.read == 10.0
