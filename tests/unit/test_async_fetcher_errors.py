"""Unit tests for AsyncFetcher error handling scenarios.

Tests cover:
- Malformed JSON handling (200 OK with invalid JSON → SKIP)
- 429 behavior (retry + circuit breaker failure increment)
- Other error scenarios
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.fetcher.async_fetcher import AsyncFetcher
from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.models.data_models import CircuitState


class TestMalformedJSONHandling:
    """Test handling of malformed JSON responses."""
    
    @pytest.fixture
    def fetcher_components(self):
        """Create fetcher components for testing."""
        rate_limiter = RateLimiter()
        circuit_breaker = CircuitBreaker()
        http_client = AsyncHTTPClient()
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        return fetcher, rate_limiter, circuit_breaker, http_client
    
    @pytest.mark.asyncio
    async def test_malformed_json_returns_skip_error(self, fetcher_components):
        """Test that 200 OK with invalid JSON returns SKIP error."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock response with 200 status but invalid JSON
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        
        # Mock HTTP client to return malformed response
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            # Fetch page
            result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should return error with retryable=False (SKIP)
        assert result is not None
        assert "error" in result
        assert result["retryable"] is False
        assert "Invalid JSON" in result["error"]
    
    @pytest.mark.asyncio
    async def test_malformed_json_increments_circuit_breaker_non_retryable(self, fetcher_components):
        """Test that malformed JSON increments circuit breaker as non-retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        endpoint = "http://api.test/products"
        
        # Mock response with invalid JSON
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            # Fetch page
            await fetcher._fetch_page_with_retries(endpoint, 1)
        
        # Circuit breaker should remain CLOSED (non-retryable failures don't count)
        assert circuit_breaker.state(endpoint) == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_malformed_json_does_not_retry(self, fetcher_components):
        """Test that malformed JSON does not trigger retries."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock response with invalid JSON
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            # Fetch page
            await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should only call once (no retries)
        assert mock_get.call_count == 1


class Test429Behavior:
    """Test 429 (Too Many Requests) handling."""
    
    @pytest.fixture
    def fetcher_components(self):
        """Create fetcher components for testing."""
        rate_limiter = RateLimiter()
        circuit_breaker = CircuitBreaker(failure_threshold=3)
        http_client = AsyncHTTPClient()
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        return fetcher, rate_limiter, circuit_breaker, http_client
    
    @pytest.mark.asyncio
    async def test_429_triggers_retry(self, fetcher_components):
        """Test that 429 status triggers retry with backoff."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 429 response
        mock_response_429 = Mock(spec=httpx.Response)
        mock_response_429.status_code = 429
        mock_response_429.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=Mock(),
                response=mock_response_429
            )
        )
        
        # Mock successful response after retry
        mock_response_success = Mock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = Mock()
        mock_response_success.json = Mock(return_value={"products": [{"id": 1}]})
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_response_429, mock_response_success]
            
            # Mock sleep to avoid waiting
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should succeed after retry
        assert result is not None
        assert "error" not in result
        assert result["item_count"] == 1
        
        # Should have called get twice (initial + 1 retry)
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_429_increments_circuit_breaker_failure_count(self, fetcher_components):
        """Test that 429 increments circuit breaker failure counter."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        endpoint = "http://api.test/products"
        
        # Mock 429 response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=Mock(),
                response=mock_response
            )
        )
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            # Mock sleep to avoid waiting
            with patch('asyncio.sleep', new_callable=AsyncMock):
                # Fetch page (will fail after retries)
                await fetcher._fetch_page_with_retries(endpoint, 1)
        
        # Circuit breaker should have recorded failures
        # 3 attempts = 3 failures (initial + 2 retries, since MAX_RETRIES=3 means 3 total attempts)
        assert circuit_breaker.state(endpoint) == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_429_opens_circuit_after_threshold(self, fetcher_components):
        """Test that repeated 429 errors open the circuit breaker."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        endpoint = "http://api.test/products"
        
        # Mock 429 response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=Mock(),
                response=mock_response
            )
        )
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            # Mock sleep to avoid waiting
            with patch('asyncio.sleep', new_callable=AsyncMock):
                # First fetch attempt (3 retries = 3 failures)
                await fetcher._fetch_page_with_retries(endpoint, 1)
        
        # Circuit should be open after 3 failures
        assert circuit_breaker.state(endpoint) == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_429_with_backoff_delay(self, fetcher_components):
        """Test that 429 applies exponential backoff between retries."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 429 response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=Mock(),
                response=mock_response
            )
        )
        
        sleep_calls = []
        
        async def mock_sleep(delay):
            sleep_calls.append(delay)
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            with patch('asyncio.sleep', side_effect=mock_sleep):
                await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should have applied backoff delays
        # Attempt 0: 0.5 * (2^0) = 0.5s
        # Attempt 1: 0.5 * (2^1) = 1.0s
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == 0.5
        assert sleep_calls[1] == 1.0


class TestOtherRetryableErrors:
    """Test other retryable error scenarios."""
    
    @pytest.fixture
    def fetcher_components(self):
        """Create fetcher components for testing."""
        rate_limiter = RateLimiter()
        circuit_breaker = CircuitBreaker(failure_threshold=3)
        http_client = AsyncHTTPClient()
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        return fetcher, rate_limiter, circuit_breaker, http_client
    
    @pytest.mark.asyncio
    async def test_502_is_retryable(self, fetcher_components):
        """Test that 502 Bad Gateway is retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 502 then success
        mock_response_502 = Mock(spec=httpx.Response)
        mock_response_502.status_code = 502
        mock_response_502.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "502 Bad Gateway",
                request=Mock(),
                response=mock_response_502
            )
        )
        
        mock_response_success = Mock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = Mock()
        mock_response_success.json = Mock(return_value={"products": [{"id": 1}]})
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_response_502, mock_response_success]
            
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should succeed after retry
        assert "error" not in result
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_503_is_retryable(self, fetcher_components):
        """Test that 503 Service Unavailable is retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 503 then success
        mock_response_503 = Mock(spec=httpx.Response)
        mock_response_503.status_code = 503
        mock_response_503.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "503 Service Unavailable",
                request=Mock(),
                response=mock_response_503
            )
        )
        
        mock_response_success = Mock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = Mock()
        mock_response_success.json = Mock(return_value={"products": [{"id": 1}]})
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_response_503, mock_response_success]
            
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should succeed after retry
        assert "error" not in result
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_504_is_retryable(self, fetcher_components):
        """Test that 504 Gateway Timeout is retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 504 then success
        mock_response_504 = Mock(spec=httpx.Response)
        mock_response_504.status_code = 504
        mock_response_504.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "504 Gateway Timeout",
                request=Mock(),
                response=mock_response_504
            )
        )
        
        mock_response_success = Mock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = Mock()
        mock_response_success.json = Mock(return_value={"products": [{"id": 1}]})
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_response_504, mock_response_success]
            
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should succeed after retry
        assert "error" not in result
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_timeout_is_retryable(self, fetcher_components):
        """Test that timeout exceptions are retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock timeout then success
        mock_response_success = Mock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = Mock()
        mock_response_success.json = Mock(return_value={"products": [{"id": 1}]})
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                httpx.TimeoutException("Request timeout"),
                mock_response_success
            ]
            
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should succeed after retry
        assert "error" not in result
        assert mock_get.call_count == 2


class TestNonRetryableErrors:
    """Test non-retryable error scenarios."""
    
    @pytest.fixture
    def fetcher_components(self):
        """Create fetcher components for testing."""
        rate_limiter = RateLimiter()
        circuit_breaker = CircuitBreaker()
        http_client = AsyncHTTPClient()
        fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
        return fetcher, rate_limiter, circuit_breaker, http_client
    
    @pytest.mark.asyncio
    async def test_404_not_retryable(self, fetcher_components):
        """Test that 404 Not Found is not retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 404 response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=Mock(),
                response=mock_response
            )
        )
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should return error without retry
        assert "error" in result
        assert result["retryable"] is False
        assert mock_get.call_count == 1
    
    @pytest.mark.asyncio
    async def test_400_not_retryable(self, fetcher_components):
        """Test that 400 Bad Request is not retryable."""
        fetcher, rate_limiter, circuit_breaker, http_client = fetcher_components
        
        # Mock 400 response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "400 Bad Request",
                request=Mock(),
                response=mock_response
            )
        )
        
        with patch.object(http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            result = await fetcher._fetch_page_with_retries("http://api.test/products", 1)
        
        # Should return error without retry
        assert "error" in result
        assert result["retryable"] is False
        assert mock_get.call_count == 1
