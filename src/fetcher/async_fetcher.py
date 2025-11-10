"""Async fetcher with rate limiting, circuit breaker, and retry logic."""

import asyncio
from typing import Dict, List

import httpx

from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.models.data_models import EndpointStats, HalfOpenToken


class AsyncFetcher:
    """
    Async fetcher with resilience patterns.
    
    Integrates:
    - Rate limiter (5 req/sec per endpoint)
    - Circuit breaker (3 failures, 15s cooldown)
    - Pagination (terminates on 204 or empty list)
    """
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
        http_client: AsyncHTTPClient
    ):
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.http_client = http_client
    
    async def fetch_endpoint_pages(
        self,
        endpoint: str,
        queue: asyncio.Queue
    ) -> EndpointStats:
        """
        Fetch all pages from endpoint, streaming to queue.
        
        Args:
            endpoint: URL to fetch from
            queue: Bounded queue for streaming pages
            
        Returns:
            Statistics for this endpoint
        """
        stats = EndpointStats(
            name=endpoint,
            pages_fetched=0,
            items_fetched=0,
            errors=0,
            total_duration=0.0
        )
        
        page = 1
        while True:
            # Check circuit breaker
            cb_result = self.circuit_breaker.should_allow(endpoint)
            if cb_result is False:
                stats.errors += 1
                break
            
            # Rate limit
            await self.rate_limiter.acquire(endpoint)
            
            # Fetch page
            try:
                start = asyncio.get_event_loop().time()
                response = await self.http_client.get(
                    f"{endpoint}/products",
                    params={"page": page}
                )
                duration = asyncio.get_event_loop().time() - start
                stats.total_duration += duration
                
                # Handle 204 (no more pages)
                if response.status_code == 204:
                    break
                
                response.raise_for_status()
                data = response.json()
                
                # Check for empty products list
                products = data.get("products", [])
                if not products:
                    break
                
                # Stream to queue
                await queue.put({"endpoint": endpoint, "page": page, "data": data})
                
                stats.pages_fetched += 1
                stats.items_fetched += len(products)
                page += 1
                
                # Record success for circuit breaker
                if isinstance(cb_result, HalfOpenToken):
                    self.circuit_breaker.record_success(endpoint, token=cb_result)
                else:
                    self.circuit_breaker.record_success(endpoint)
                
            except (httpx.HTTPError, Exception) as e:
                stats.errors += 1
                
                # Determine if retryable
                is_retryable = False
                if isinstance(e, httpx.HTTPStatusError):
                    is_retryable = e.response.status_code in {429, 502, 503, 504}
                elif isinstance(e, httpx.TimeoutException):
                    is_retryable = True
                
                self.circuit_breaker.record_failure(endpoint, retryable=is_retryable)
                
                # Break on non-retryable or circuit open
                if not is_retryable or self.circuit_breaker.state(endpoint).value == "open":
                    break
        
        return stats
    
    async def fetch_all_endpoints(
        self,
        endpoints: List[str],
        queue: asyncio.Queue
    ) -> Dict[str, EndpointStats]:
        """
        Fetch from all endpoints concurrently.
        
        Args:
            endpoints: List of endpoint URLs
            queue: Bounded queue for streaming
            
        Returns:
            Statistics per endpoint
        """
        tasks = [
            self.fetch_endpoint_pages(endpoint, queue)
            for endpoint in endpoints
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        stats_dict = {}
        for endpoint, result in zip(endpoints, results):
            if isinstance(result, Exception):
                stats_dict[endpoint] = EndpointStats(
                    name=endpoint,
                    pages_fetched=0,
                    items_fetched=0,
                    errors=1,
                    total_duration=0.0
                )
            else:
                stats_dict[endpoint] = result
        
        return stats_dict
