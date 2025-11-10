"""Unit tests for the RateLimiter token bucket implementation."""

import asyncio
import pytest
import time
from unittest.mock import patch

from src.fetcher.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for RateLimiter token bucket algorithm."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a RateLimiter instance for testing."""
        return RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
    
    def test_initialization(self, rate_limiter):
        """Test RateLimiter initialization with correct parameters."""
        assert rate_limiter.max_tokens == 5
        assert rate_limiter.refill_rate == 5.0
        assert rate_limiter.retry_sleep == 0.05
        assert rate_limiter._buckets == {}
    
    def test_tokens_available_new_endpoint(self, rate_limiter):
        """Test tokens_available returns max tokens for new endpoint."""
        tokens = rate_limiter.tokens_available("test-endpoint")
        assert tokens == 5
    
    def test_tokens_available_after_consumption(self, rate_limiter):
        """Test tokens_available decreases after token consumption."""
        # Consume one token by getting bucket state
        rate_limiter._get_bucket_state("test-endpoint")
        rate_limiter._buckets["test-endpoint"] = (3.0, time.monotonic())
        
        tokens = rate_limiter.tokens_available("test-endpoint")
        assert tokens == 3
    
    @pytest.mark.asyncio
    async def test_acquire_single_token(self, rate_limiter):
        """Test acquiring a single token succeeds immediately."""
        start_time = time.monotonic()
        await rate_limiter.acquire("test-endpoint")
        end_time = time.monotonic()
        
        # Should complete quickly (no blocking)
        assert end_time - start_time < 0.1
        
        # Should have 4 tokens remaining
        tokens = rate_limiter.tokens_available("test-endpoint")
        assert tokens == 4
    
    @pytest.mark.asyncio
    async def test_acquire_multiple_tokens_same_endpoint(self, rate_limiter):
        """Test acquiring multiple tokens from same endpoint."""
        endpoint = "test-endpoint"
        
        # Acquire 3 tokens
        for i in range(3):
            await rate_limiter.acquire(endpoint)
        
        # Should have 2 tokens remaining
        tokens = rate_limiter.tokens_available(endpoint)
        assert tokens == 2
    
    @pytest.mark.asyncio
    async def test_acquire_different_endpoints(self, rate_limiter):
        """Test that different endpoints have separate token buckets."""
        await rate_limiter.acquire("endpoint-1")
        await rate_limiter.acquire("endpoint-2")
        
        # Each endpoint should have 4 tokens remaining
        assert rate_limiter.tokens_available("endpoint-1") == 4
        assert rate_limiter.tokens_available("endpoint-2") == 4
    
    @pytest.mark.asyncio
    async def test_acquire_blocks_when_tokens_exhausted(self, rate_limiter):
        """Test that acquire blocks when no tokens are available."""
        endpoint = "test-endpoint"
        
        # Exhaust all tokens
        for i in range(5):
            await rate_limiter.acquire(endpoint)
        
        # Verify no tokens remaining
        assert rate_limiter.tokens_available(endpoint) == 0
        
        # Next acquire should block for at least retry_sleep duration
        start_time = time.monotonic()
        
        # Use asyncio.wait_for to prevent test from hanging
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(rate_limiter.acquire(endpoint), timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_token_refill_over_time(self, rate_limiter):
        """Test that tokens are refilled over time at correct rate."""
        endpoint = "test-endpoint"
        
        # Consume all tokens
        for i in range(5):
            await rate_limiter.acquire(endpoint)
        
        assert rate_limiter.tokens_available(endpoint) == 0
        
        # Wait for partial refill (0.2 seconds = 1 token at 5 tokens/sec)
        await asyncio.sleep(0.2)
        
        # Should have approximately 1 token available
        tokens = rate_limiter.tokens_available(endpoint)
        assert tokens >= 1
    
    @pytest.mark.asyncio
    async def test_token_refill_caps_at_maximum(self, rate_limiter):
        """Test that token refill doesn't exceed maximum bucket size."""
        endpoint = "test-endpoint"
        
        # Initialize bucket and wait longer than needed for full refill
        rate_limiter._get_bucket_state(endpoint)
        await asyncio.sleep(2.0)  # Wait 2 seconds (should refill 10 tokens, but cap at 5)
        
        tokens = rate_limiter.tokens_available(endpoint)
        assert tokens == 5  # Should not exceed max_tokens
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforcement(self, rate_limiter):
        """Test that rate limiter enforces 5 requests per second limit."""
        endpoint = "test-endpoint"
        
        # Record start time
        start_time = time.monotonic()
        
        # Try to acquire 10 tokens (should take at least 1 second due to rate limiting)
        for i in range(10):
            await rate_limiter.acquire(endpoint)
        
        end_time = time.monotonic()
        elapsed = end_time - start_time
        
        # Should take at least 1 second to get 10 tokens at 5 tokens/sec
        # (5 immediate + 5 more after 1 second refill)
        assert elapsed >= 0.9  # Allow some tolerance for timing
    
    @pytest.mark.asyncio
    async def test_concurrent_access_thread_safety(self, rate_limiter):
        """Test that concurrent access to rate limiter is thread-safe."""
        endpoint = "test-endpoint"
        
        async def acquire_token():
            await rate_limiter.acquire(endpoint)
            return 1
        
        # Launch 20 concurrent acquire attempts
        tasks = [acquire_token() for _ in range(20)]
        results = await asyncio.gather(*tasks)
        
        # All tasks should complete successfully
        assert len(results) == 20
        assert all(result == 1 for result in results)
        
        # Final token count should be consistent
        # (Started with 5, acquired 20, so should have refilled some during execution)
        final_tokens = rate_limiter.tokens_available(endpoint)
        assert final_tokens >= 0  # Should not be negative
    
    def test_get_bucket_state_new_endpoint(self, rate_limiter):
        """Test _get_bucket_state initializes new endpoint correctly."""
        tokens, last_refill = rate_limiter._get_bucket_state("new-endpoint")
        
        assert tokens == 5.0
        assert isinstance(last_refill, float)
        assert "new-endpoint" in rate_limiter._buckets
    
    def test_get_bucket_state_existing_endpoint(self, rate_limiter):
        """Test _get_bucket_state updates existing endpoint correctly."""
        endpoint = "test-endpoint"
        
        # Initialize bucket
        initial_tokens, initial_time = rate_limiter._get_bucket_state(endpoint)
        
        # Manually set bucket to 2 tokens and earlier time
        earlier_time = initial_time - 0.4  # 0.4 seconds ago
        rate_limiter._buckets[endpoint] = (2.0, earlier_time)
        
        # Get updated state (should refill ~2 tokens in 0.4 seconds at 5 tokens/sec)
        tokens, last_refill = rate_limiter._get_bucket_state(endpoint)
        
        assert tokens > 2.0  # Should have refilled
        assert tokens <= 5.0  # Should not exceed maximum
        assert last_refill > earlier_time  # Time should be updated