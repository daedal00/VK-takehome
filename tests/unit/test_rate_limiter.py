"""Unit tests for RateLimiter token bucket implementation."""

import asyncio
import pytest
import time

from src.fetcher.rate_limiter import RateLimiter


class TestRateLimiter:
    
    @pytest.fixture
    def rate_limiter(self):
        return RateLimiter(max_tokens=5, refill_rate=5.0, retry_sleep=0.05)
    
    def test_initialization(self, rate_limiter):
        assert rate_limiter.max_tokens == 5
        assert rate_limiter.refill_rate == 5.0
        assert rate_limiter._buckets == {}
    
    def test_tokens_available_new_endpoint(self, rate_limiter):
        assert rate_limiter.tokens_available("endpoint1") == 5
    
    @pytest.mark.asyncio
    async def test_acquire_consumes_token(self, rate_limiter):
        await rate_limiter.acquire("endpoint1")
        assert rate_limiter.tokens_available("endpoint1") == 4
    
    @pytest.mark.asyncio
    async def test_independent_endpoints(self, rate_limiter):
        await rate_limiter.acquire("endpoint1")
        await rate_limiter.acquire("endpoint2")
        
        assert rate_limiter.tokens_available("endpoint1") == 4
        assert rate_limiter.tokens_available("endpoint2") == 4
    
    @pytest.mark.asyncio
    async def test_blocks_when_exhausted(self, rate_limiter):
        # Exhaust all tokens
        for _ in range(5):
            await rate_limiter.acquire("endpoint1")
        
        assert rate_limiter.tokens_available("endpoint1") == 0
        
        # Should block
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(rate_limiter.acquire("endpoint1"), timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_refills_over_time(self, rate_limiter):
        # Exhaust tokens
        for _ in range(5):
            await rate_limiter.acquire("endpoint1")
        
        # Wait for refill
        await asyncio.sleep(0.3)
        
        # Should have ~1-2 tokens
        assert rate_limiter.tokens_available("endpoint1") >= 1
    
    @pytest.mark.asyncio
    async def test_caps_at_max_tokens(self, rate_limiter):
        rate_limiter._get_bucket_state("endpoint1")
        await asyncio.sleep(2.0)
        
        assert rate_limiter.tokens_available("endpoint1") == 5
    
    @pytest.mark.asyncio
    async def test_enforces_rate_limit(self, rate_limiter):
        start = time.monotonic()
        
        # 10 tokens at 5/sec should take ~1 second
        for _ in range(10):
            await rate_limiter.acquire("endpoint1")
        
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, rate_limiter):
        async def acquire():
            await rate_limiter.acquire("endpoint1")
            return 1
        
        results = await asyncio.gather(*[acquire() for _ in range(20)])
        
        assert len(results) == 20
        assert rate_limiter.tokens_available("endpoint1") >= 0
    
    @pytest.mark.asyncio
    async def test_twenty_concurrent_coroutines_ceiling(self, rate_limiter):
        """Test that 20 concurrent coroutines respect ≤5 acquires/sec ceiling.
        
        With 5 tokens initially available and 5 tokens/sec refill rate:
        - First 5 acquires: immediate (0s)
        - Next 15 acquires: require refills at 5/sec = 3 seconds
        - Total minimum time: 3 seconds
        """
        start = time.monotonic()
        
        async def acquire():
            await rate_limiter.acquire("endpoint1")
            return time.monotonic()
        
        # Launch 20 concurrent coroutines
        timestamps = await asyncio.gather(*[acquire() for _ in range(20)])
        
        elapsed = time.monotonic() - start
        
        # 20 acquires at 5/sec = minimum 3 seconds (5 immediate + 15 over 3s)
        # Allow some tolerance for timing and scheduling overhead
        assert elapsed >= 2.8, f"Expected ≥2.8s for 20 acquires at 5/sec, got {elapsed:.2f}s"
        
        # Verify all 20 acquires completed
        assert len(timestamps) == 20
