"""Async fetcher with rate limiting, circuit breaker, and retry logic."""

import asyncio
from typing import Dict, List, Optional

import httpx

from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.models.data_models import EndpointStats, HalfOpenToken


class AsyncFetcher:
    """
    Async fetcher with resilience patterns.
    
    Responsibilities:
    - Fetch paginated data from multiple endpoints concurrently
    - Apply rate limiting (5 req/sec per endpoint)
    - Use circuit breaker to handle failing endpoints
    - Retry transient failures with exponential backoff
    - Stream results to bounded queue for memory efficiency
    """
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
        http_client: AsyncHTTPClient,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        retryable_status_codes: Optional[List[int]] = None,
        logger: Optional['StructuredLogger'] = None
    ):
        """
        Initialize fetcher with resilience components.
        
        Args:
            rate_limiter: Controls request rate per endpoint
            circuit_breaker: Prevents requests to failing endpoints
            http_client: Makes HTTP requests with timeouts
            max_retries: Maximum retry attempts per request
            retry_base_delay: Base delay for exponential backoff
            retryable_status_codes: HTTP status codes that trigger retries
            logger: Optional structured logger for telemetry
        """
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.http_client = http_client
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retryable_status_codes = frozenset(
            retryable_status_codes or [429, 502, 503, 504]
        )
        self.logger = logger
    
    async def fetch_endpoint_pages(
        self,
        endpoint: str,
        queue: asyncio.Queue
    ) -> EndpointStats:
        """
        Fetch all pages from an endpoint until pagination ends.
        
        Pagination terminates when:
        - Server returns 204 No Content
        - Response contains empty products list
        - Circuit breaker opens
        - Non-retryable error occurs
        
        Args:
            endpoint: Full URL to fetch from (e.g., http://api.com/products)
            queue: Bounded queue for streaming page data
            
        Returns:
            Statistics for this endpoint (pages, items, errors, duration)
        """
        from datetime import datetime, timezone
        from src.models.data_models import ErrorAction, ErrorRecord
        
        stats = EndpointStats(
            name=endpoint,
            pages_fetched=0,
            items_fetched=0,
            errors=0,
            total_duration=0.0,
            error_details=[]
        )
        
        page = 1
        
        while True:
            # Check circuit breaker state before attempting request
            if not self._should_attempt_request(endpoint):
                stats.errors += 1
                break
            
            # Apply rate limiting
            await self.rate_limiter.acquire(endpoint)
            
            # Attempt to fetch page with retries
            page_result = await self._fetch_page_with_retries(endpoint, page)
            
            if page_result is None:
                # Pagination ended (204 or empty products)
                break
            
            if "error" in page_result:
                # Failed after all retries
                stats.errors += 1
                
                # Create detailed error record
                error_record = ErrorRecord(
                    source=endpoint,
                    page=page,
                    code=page_result.get("status_code"),
                    error=page_result["error"],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    action=ErrorAction.RETRY if page_result.get("retryable", False) else ErrorAction.SKIP
                )
                stats.error_details.append(error_record)
                
                if not page_result.get("retryable", False):
                    # Non-retryable error, stop fetching
                    break
                # Retryable error but retries exhausted, stop fetching
                break
            
            # Success - stream to queue and update stats
            await queue.put(page_result["data"])
            stats.pages_fetched += 1
            stats.items_fetched += page_result["item_count"]
            stats.total_duration += page_result["duration"]
            page += 1
        
        return stats
    
    def _should_attempt_request(self, endpoint: str) -> bool:
        """
        Check if request should be attempted based on circuit breaker state.
        
        Args:
            endpoint: Endpoint URL
            
        Returns:
            True if request should be attempted, False if circuit is open
        """
        cb_result = self.circuit_breaker.should_allow(endpoint)
        return cb_result is not False
    
    async def _fetch_page_with_retries(
        self,
        endpoint: str,
        page: int
    ) -> Optional[Dict]:
        """
        Fetch a single page with retry logic.
        
        Implements exponential backoff: delay = base_delay * (2 ** attempt)
        - Attempt 0: 0.5s
        - Attempt 1: 1.0s  
        - Attempt 2: 2.0s
        
        Args:
            endpoint: Endpoint URL
            page: Page number to fetch
            
        Returns:
            Dict with data, item_count, duration on success
            Dict with error, retryable on failure
            None if pagination ended (204 or empty products)
        """
        cb_result = self.circuit_breaker.should_allow(endpoint)
        last_error = None
        
        if self.logger:
            self.logger.fetch_start(source=endpoint, page=page)
        
        for attempt in range(self.max_retries):
            try:
                result = await self._fetch_single_page(endpoint, page)
                
                # Success - record with circuit breaker
                if isinstance(cb_result, HalfOpenToken):
                    self.circuit_breaker.record_success(endpoint, token=cb_result)
                else:
                    self.circuit_breaker.record_success(endpoint)
                
                if self.logger and result:
                    self.logger.fetch_success(
                        source=endpoint,
                        page=page,
                        elapsed_ms=result.get('duration', 0) * 1000
                    )
                
                return result
                
            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                is_retryable = status_code in self.retryable_status_codes
                self.circuit_breaker.record_failure(endpoint, retryable=is_retryable)
                
                if self.logger:
                    self.logger.fetch_error(
                        source=endpoint,
                        page=page,
                        status=status_code,
                        error=str(e),
                        attempt=attempt
                    )
                
                if not is_retryable:
                    # Non-retryable HTTP error (e.g., 404, 400)
                    return {"error": str(e), "retryable": False, "status_code": status_code}
                
                # Retryable error - apply backoff if retries remain
                if attempt < self.max_retries - 1:
                    await self._apply_backoff(attempt)
                    
            except httpx.TimeoutException as e:
                last_error = e
                self.circuit_breaker.record_failure(endpoint, retryable=True)
                
                if self.logger:
                    self.logger.fetch_error(
                        source=endpoint,
                        page=page,
                        status=None,
                        error="timeout",
                        attempt=attempt
                    )
                
                # Timeout is retryable - apply backoff if retries remain
                if attempt < self.max_retries - 1:
                    await self._apply_backoff(attempt)
                    
            except Exception as e:
                # Unexpected error (e.g., JSON decode error)
                last_error = e
                self.circuit_breaker.record_failure(endpoint, retryable=False)
                
                if self.logger:
                    self.logger.fetch_error(
                        source=endpoint,
                        page=page,
                        status=None,
                        error=str(e),
                        attempt=attempt
                    )
                
                return {"error": str(e), "retryable": False, "status_code": None}
        
        # All retries exhausted
        status_code = getattr(last_error, 'response', None)
        if status_code:
            status_code = status_code.status_code
        return {"error": str(last_error), "retryable": True, "status_code": status_code}
    
    async def _fetch_single_page(self, endpoint: str, page: int) -> Optional[Dict]:
        """
        Fetch a single page without retry logic.
        
        Args:
            endpoint: Endpoint URL
            page: Page number
            
        Returns:
            Dict with data, item_count, duration
            None if pagination ended
            
        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.TimeoutException: On timeout
            Exception: On other errors (e.g., JSON decode)
        """
        start = asyncio.get_event_loop().time()
        
        response = await self.http_client.get(
            endpoint,
            params={"page": page}
        )
        
        duration = asyncio.get_event_loop().time() - start
        
        # Check for pagination end
        if response.status_code == 204:
            return None
        
        # Raise on HTTP errors
        response.raise_for_status()
        
        # Parse response
        data = response.json()
        products = data.get("products", [])
        
        # Check for empty products (pagination end)
        if not products:
            return None
        
        return {
            "data": {
                "endpoint": endpoint,
                "page": page,
                "data": data
            },
            "item_count": len(products),
            "duration": duration
        }
    
    async def _apply_backoff(self, attempt: int) -> None:
        """
        Apply exponential backoff delay.
        
        Formula: base_delay * (2 ** attempt)
        
        Args:
            attempt: Current attempt number (0-indexed)
        """
        delay = self.retry_base_delay * (2 ** attempt)
        await asyncio.sleep(delay)
    
    async def fetch_all_endpoints(
        self,
        endpoints: List[str],
        queue: asyncio.Queue
    ) -> Dict[str, EndpointStats]:
        """
        Fetch from all endpoints concurrently.
        
        Uses asyncio.gather to fetch from multiple endpoints in parallel,
        respecting per-endpoint rate limits and circuit breakers.
        
        Args:
            endpoints: List of endpoint URLs
            queue: Bounded queue for streaming results
            
        Returns:
            Dictionary mapping endpoint URL to its statistics
        """
        tasks = [
            self.fetch_endpoint_pages(endpoint, queue)
            for endpoint in endpoints
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        stats_dict = {}
        for endpoint, result in zip(endpoints, results):
            if isinstance(result, Exception):
                # Task raised unhandled exception
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
