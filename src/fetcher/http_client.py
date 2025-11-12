"""Async HTTP client wrapper with timeout configuration."""

from typing import Any, Dict, Optional

import httpx


class AsyncHTTPClient:
    """
    Async HTTP client wrapper around httpx.AsyncClient.
    
    Provides:
    - Configurable connect and read timeouts
    - Connection pooling via httpx
    - Context manager for proper lifecycle management
    """
    
    def __init__(
        self,
        connect_timeout: float = 3.0,
        read_timeout: float = 8.0,
        write_timeout: float = 5.0,
        pool_timeout: float = 5.0
    ):
        """
        Initialize HTTP client.
        
        Args:
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds
            write_timeout: Write timeout in seconds
            pool_timeout: Pool timeout in seconds
        """
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.pool_timeout = pool_timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Enter async context manager."""
        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
            pool=self.pool_timeout
        )
        self._client = httpx.AsyncClient(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Perform GET request.
        
        Args:
            url: URL to request
            params: Query parameters
            **kwargs: Additional arguments for httpx
            
        Returns:
            HTTP response
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        
        return await self._client.get(url, params=params, **kwargs)
