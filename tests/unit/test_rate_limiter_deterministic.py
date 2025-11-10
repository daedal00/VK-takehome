"""Deterministic unit tests for rate limiter with fake clock.

These tests use a fake clock to achieve deterministic, fast, and comprehensive
coverage of the rate limiter's behavior without flaky real-time waits.

Target: ≥90% coverage on src/fetcher/rate_limiter.py
"""

import asyncio

import pytest

from src.fetcher.rate_limiter import RateLimiter


class FakeClock:
    """Fake clock for deterministic time testing."""
    
    def __init__(self, initial_time: float = 0.0):
        """Initialize fake clock.
        
        Args:
            initial_time: Starting time value
        """
        self.t = initial_time
    
    def now(self) -> float:
        """Get current fake time."""
        return self.t
    
    async def sleep(self, dt: float) -> None:
        """Advance fake time by dt seconds."""
        self.t += dt


class TestRateLimiterEmptyBucket:
    """Test rate limiter behavior when bucket is empty."""
    
    @pytest.mark.asyncio
    async def test_waits_when_empty_with_fake_clock(self):
        """Rate limiter should wait and retry when bucket is empty."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Drain all 5 tokens
        for _ in range(5):
            await rl.acquire(ep)
        
        assert rl.tokens_available(ep) == 0
        
        # Next acquire should wait for refill
        t0 = clk.t
        
        # Create task that will wait for token
        task = asyncio.create_task(rl.acquire(ep))
        
        # Advance time in small steps until token appears
        for _ in range(20):
            await clk.sleep(0.05)
            if rl.tokens_available(ep) >= 1:
                break
        
        # Complete the acquire
        await task
        
        # Should have advanced time by at least retry_sleep
        assert clk.t - t0 >= 0.05
        
        # Token should be consumed
        assert rl.tokens_available(ep) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_waits_when_empty(self):
        """Multiple acquires should wait sequentially when bucket is empty."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Drain all tokens
        for _ in range(5):
            await rl.acquire(ep)
        
        # Try to acquire 3 more - should wait for refills
        t0 = clk.t
        
        for _ in range(3):
            # Each acquire will wait for refill
            task = asyncio.create_task(rl.acquire(ep))
            
            # Advance time to allow refill
            for _ in range(10):
                await clk.sleep(0.05)
                if rl.tokens_available(ep) >= 1:
                    break
            
            await task
        
        # Should have taken time to refill
        assert clk.t - t0 >= 0.15


class TestRateLimiterRefillMath:
    """Test token refill calculations and capping."""
    
    def test_refill_fractional_time(self):
        """Tokens should refill based on fractional elapsed time."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Initialize bucket
        rl._get_bucket_state(ep)
        
        # Drain all tokens
        for _ in range(5):
            rl._buckets[ep] = (rl._buckets[ep][0] - 1.0, rl._buckets[ep][1])
        
        assert rl.tokens_available(ep) == 0
        
        # Advance 0.2s -> should add 1 token at 5 tokens/sec
        clk.t += 0.2
        assert rl.tokens_available(ep) == 1
        
        # Advance another 0.4s -> should add 2 more tokens (total 3)
        clk.t += 0.4
        assert rl.tokens_available(ep) == 3
    
    def test_refill_caps_at_max_tokens(self):
        """Token refill should cap at max_tokens."""
        clk = FakeClock()
        rl = RateLimiter(max_tokens=5, now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Initialize and drain
        rl._get_bucket_state(ep)
        for _ in range(5):
            rl._buckets[ep] = (rl._buckets[ep][0] - 1.0, rl._buckets[ep][1])
        
        assert rl.tokens_available(ep) == 0
        
        # Advance 2 seconds -> would be +10 tokens but should cap at 5
        clk.t += 2.0
        assert rl.tokens_available(ep) == 5
        
        # Advance more time -> should still be capped
        clk.t += 10.0
        assert rl.tokens_available(ep) == 5
    
    def test_refill_with_partial_tokens(self):
        """Refill should work correctly with partial tokens remaining."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Initialize
        rl._get_bucket_state(ep)
        
        # Set to 2.5 tokens manually
        rl._buckets[ep] = (2.5, clk.t)
        
        # Advance 0.5s -> should add 2.5 tokens (total 5.0, capped)
        clk.t += 0.5
        assert rl.tokens_available(ep) == 5


class TestRateLimiterPerEndpointIsolation:
    """Test that endpoints are independently rate limited."""
    
    @pytest.mark.asyncio
    async def test_two_endpoints_parallel_limits(self):
        """Two endpoints should each honor 5 rps independently."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        
        async def take_n(ep: str, n: int):
            """Acquire n tokens from endpoint."""
            for _ in range(n):
                await rl.acquire(ep)
        
        # 10 acquires per endpoint (5 immediate + 5 that need refills)
        # At 5 tokens/sec, 5 additional tokens take 1 second
        t0 = clk.t
        
        # Run both endpoints in parallel
        await asyncio.gather(
            take_n("endpoint_A", 10),
            take_n("endpoint_B", 10)
        )
        
        elapsed = clk.t - t0
        
        # Each endpoint independently limited to 5 rps
        # With parallel execution and shared clock, both will advance time
        # 10 tokens per endpoint = 5 immediate + 5 over 1 second minimum
        assert 1.0 <= elapsed <= 2.5
    
    @pytest.mark.asyncio
    async def test_endpoint_a_blocking_does_not_throttle_endpoint_b(self):
        """Blocking on endpoint A should not affect endpoint B."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        
        # Drain endpoint A
        for _ in range(5):
            await rl.acquire("endpoint_A")
        
        assert rl.tokens_available("endpoint_A") == 0
        
        # Endpoint B should still have full tokens
        assert rl.tokens_available("endpoint_B") == 5
        
        # Should be able to acquire from B immediately
        t0 = clk.t
        await rl.acquire("endpoint_B")
        assert clk.t == t0  # No time should have passed
    
    @pytest.mark.asyncio
    async def test_high_contention_isolation(self):
        """High contention on one endpoint should not affect others."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        
        async def spam(ep: str, n: int):
            """Spam acquires on endpoint."""
            for _ in range(n):
                await rl.acquire(ep)
        
        # 50 acquires on endpoint A (high contention)
        await asyncio.gather(*(spam("endpoint_A", 10) for _ in range(5)))
        
        # Endpoint B should still be full
        assert rl.tokens_available("endpoint_B") == 5


class TestRateLimiterThroughputCeiling:
    """Test that rate limiter enforces throughput ceiling."""
    
    @pytest.mark.asyncio
    async def test_twenty_acquires_take_approximately_three_seconds(self):
        """20 acquires should take ~3 seconds (5 immediate + 15 over 3s)."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        t0 = clk.t
        
        for _ in range(20):
            await rl.acquire(ep)
        
        elapsed = clk.t - t0
        
        # 5 immediate + 15 at 5/sec = 3 seconds
        assert 2.8 <= elapsed <= 3.2
    
    @pytest.mark.asyncio
    async def test_enforces_five_requests_per_second_ceiling(self):
        """Rate limiter should enforce ≤5 requests per second."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Acquire 10 tokens
        for _ in range(10):
            await rl.acquire(ep)
        
        # Should take at least 1 second (5 immediate + 5 over 1s)
        assert clk.t >= 1.0


class TestRateLimiterTokensAvailable:
    """Test tokens_available monitoring method."""
    
    def test_tokens_available_floors_to_int(self):
        """tokens_available should floor fractional tokens to int."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Set fractional tokens manually
        rl._buckets[ep] = (4.999, clk.t)
        assert rl.tokens_available(ep) == 4
        
        rl._buckets[ep] = (0.999, clk.t)
        assert rl.tokens_available(ep) == 0
        
        rl._buckets[ep] = (2.001, clk.t)
        assert rl.tokens_available(ep) == 2
    
    def test_tokens_available_with_large_fractional(self):
        """tokens_available should handle large fractional values."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Set to just under max
        rl._buckets[ep] = (4.9, clk.t)
        assert rl.tokens_available(ep) == 4
        
        # Advance to refill past max
        clk.t += 1.0
        assert rl.tokens_available(ep) == 5  # Capped at max
    
    def test_tokens_available_near_zero(self):
        """tokens_available should handle near-zero values."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        rl._buckets[ep] = (0.001, clk.t)
        assert rl.tokens_available(ep) == 0
        
        rl._buckets[ep] = (0.0, clk.t)
        assert rl.tokens_available(ep) == 0


class TestRateLimiterLockGranularity:
    """Test lock behavior and contention handling."""
    
    @pytest.mark.asyncio
    async def test_concurrent_acquires_no_deadlock(self):
        """Concurrent acquires should not deadlock."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        
        async def acquire_many(ep: str, count: int):
            """Acquire multiple tokens."""
            for _ in range(count):
                await rl.acquire(ep)
        
        # Run many concurrent acquires
        await asyncio.gather(
            acquire_many("ep1", 10),
            acquire_many("ep2", 10),
            acquire_many("ep3", 10),
        )
        
        # All should complete without deadlock
        assert True
    
    @pytest.mark.asyncio
    async def test_tokens_remain_non_negative_under_contention(self):
        """Token counts should never go negative under high contention."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        async def acquire_and_check():
            """Acquire token and verify non-negative."""
            await rl.acquire(ep)
            # After acquire, tokens should be non-negative
            assert rl.tokens_available(ep) >= 0
        
        # Run many concurrent acquires
        await asyncio.gather(*(acquire_and_check() for _ in range(20)))
        
        # Final token count should be non-negative
        assert rl.tokens_available(ep) >= 0


class TestRateLimiterInitialization:
    """Test rate limiter initialization and configuration."""
    
    def test_new_endpoint_starts_with_full_tokens(self):
        """New endpoint should start with max_tokens available."""
        clk = FakeClock()
        rl = RateLimiter(max_tokens=5, now=clk.now, sleeper=clk.sleep)
        
        assert rl.tokens_available("new_endpoint") == 5
    
    def test_custom_max_tokens(self):
        """Rate limiter should respect custom max_tokens."""
        clk = FakeClock()
        rl = RateLimiter(max_tokens=10, now=clk.now, sleeper=clk.sleep)
        
        assert rl.tokens_available("endpoint1") == 10
    
    def test_custom_refill_rate(self):
        """Rate limiter should respect custom refill_rate."""
        clk = FakeClock()
        rl = RateLimiter(max_tokens=5, refill_rate=10.0, now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Drain tokens
        rl._get_bucket_state(ep)
        for _ in range(5):
            rl._buckets[ep] = (rl._buckets[ep][0] - 1.0, rl._buckets[ep][1])
        
        # Advance 0.5s -> should add 5 tokens at 10 tokens/sec
        clk.t += 0.5
        assert rl.tokens_available(ep) == 5


class TestRateLimiterEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_acquire_exactly_one_token(self):
        """Each acquire should consume exactly 1.0 token."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        initial = rl.tokens_available(ep)
        await rl.acquire(ep)
        after = rl.tokens_available(ep)
        
        assert initial - after == 1
    
    def test_zero_elapsed_time_no_refill(self):
        """Zero elapsed time should not refill tokens."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Initialize and drain
        rl._get_bucket_state(ep)
        rl._buckets[ep] = (0.0, clk.t)
        
        # Check immediately (no time elapsed)
        assert rl.tokens_available(ep) == 0
    
    @pytest.mark.asyncio
    async def test_rapid_acquire_release_pattern(self):
        """Rapid acquire patterns should maintain rate limit."""
        clk = FakeClock()
        rl = RateLimiter(now=clk.now, sleeper=clk.sleep)
        ep = "endpoint1"
        
        # Burst of 5, wait, burst of 5
        for _ in range(5):
            await rl.acquire(ep)
        
        t0 = clk.t
        
        for _ in range(5):
            await rl.acquire(ep)
        
        # Second burst should take ~1 second
        assert clk.t - t0 >= 0.9
