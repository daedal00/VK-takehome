"""Specific requirement validation tests for RateLimiter."""

import asyncio
import pytest
import time

from src.fetcher.rate_limiter import RateLimiter


class TestRateLimiterRequirements:
    """Test RateLimiter against specific requirements from the spec."""
    
    @pytest.mark.asyncio
    async def test_requirement_1_3_five_requests_per_second_per_endpoint(self):
        """Requirement 1.3: Rate_Limiter SHALL enforce exactly 5 requests per second per endpoint."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
        endpoint = "test-endpoint"
        
        # Measure time to acquire 20 tokens (should take ~3 seconds at 5 rps)
        start_time = time.monotonic()
        
        # Acquire 20 tokens
        for i in range(20):
            await rate_limiter.acquire(endpoint)
        
        end_time = time.monotonic()
        elapsed = end_time - start_time
        
        # Should take approximately 3 seconds (5 immediate + 15 more over 3 seconds)
        # Allow some tolerance for timing variations
        assert elapsed >= 2.8, f"Expected ~3 seconds, got {elapsed:.2f}s"
        assert elapsed <= 4.0, f"Too slow: {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def test_requirement_2_1_token_bucket_with_five_tokens(self):
        """Requirement 2.1: Token bucket implementation with 5 tokens refilled once per second."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
        endpoint = "test-endpoint"
        
        # Initially should have 5 tokens available
        assert rate_limiter.tokens_available(endpoint) == 5
        
        # Consume all 5 tokens
        for i in range(5):
            await rate_limiter.acquire(endpoint)
        
        # Should have 0 tokens
        assert rate_limiter.tokens_available(endpoint) == 0
        
        # Wait 1 second for refill
        await asyncio.sleep(1.0)
        
        # Should have approximately 5 tokens again (refilled once per second)
        tokens = rate_limiter.tokens_available(endpoint)
        assert tokens >= 4, f"Expected ~5 tokens after 1s, got {tokens}"
        assert tokens <= 5, f"Should not exceed 5 tokens, got {tokens}"
    
    @pytest.mark.asyncio
    async def test_requirement_sleep_0_05_retry_when_tokens_unavailable(self):
        """Test sleep(0.05) retry when tokens unavailable."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
        endpoint = "test-endpoint"
        
        # Exhaust all tokens
        for i in range(5):
            await rate_limiter.acquire(endpoint)
        
        # Verify no tokens remaining
        assert rate_limiter.tokens_available(endpoint) == 0
        
        # Measure time for next acquire (should involve multiple 0.05s sleeps)
        start_time = time.monotonic()
        
        # This should block and retry with 0.05s sleeps until tokens refill
        await rate_limiter.acquire(endpoint)
        
        end_time = time.monotonic()
        elapsed = end_time - start_time
        
        # Should take at least 0.05s (one retry cycle) but less than 0.5s
        assert elapsed >= 0.05, f"Should take at least 0.05s, got {elapsed:.3f}s"
        assert elapsed <= 0.5, f"Should not take too long, got {elapsed:.3f}s"
    
    @pytest.mark.asyncio
    async def test_per_endpoint_isolation(self):
        """Test that rate limiting is per-endpoint (different endpoints don't interfere)."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
        
        # Exhaust tokens for endpoint-1
        for i in range(5):
            await rate_limiter.acquire("endpoint-1")
        
        assert rate_limiter.tokens_available("endpoint-1") == 0
        
        # endpoint-2 should still have full tokens
        assert rate_limiter.tokens_available("endpoint-2") == 5
        
        # Should be able to acquire from endpoint-2 immediately
        start_time = time.monotonic()
        await rate_limiter.acquire("endpoint-2")
        end_time = time.monotonic()
        
        # Should complete quickly (no blocking)
        assert end_time - start_time < 0.1
        assert rate_limiter.tokens_available("endpoint-2") == 4
    
    def test_tokens_available_method_for_monitoring(self):
        """Test tokens_available() method for monitoring and testing."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
        
        # New endpoint should report 5 tokens
        assert rate_limiter.tokens_available("new-endpoint") == 5
        
        # After manual bucket manipulation, should report correct count
        rate_limiter._buckets["test-endpoint"] = (3.7, time.monotonic())
        assert rate_limiter.tokens_available("test-endpoint") == 3  # Floored to int
        
        rate_limiter._buckets["test-endpoint"] = (0.9, time.monotonic())
        assert rate_limiter.tokens_available("test-endpoint") == 0  # Floored to int