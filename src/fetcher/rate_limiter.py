"""Rate limiter implementation using token bucket algorithm."""

import asyncio
import time
from typing import Callable, Dict


class RateLimiter:
    """Token bucket rate limiter for controlling request frequency per endpoint.
    
    Implements precise rate limiting with 5 tokens per endpoint, refilled once per second.
    When tokens are unavailable, uses sleep(0.05) retry to maintain ≤5 rps/endpoint.
    """
    
    def __init__(
        self,
        max_tokens: int = 5,
        refill_rate: float = 5.0,
        retry_sleep: float = 0.05,
        now: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], any] = asyncio.sleep,
    ):
        """Initialize rate limiter with token bucket parameters.
        
        Args:
            max_tokens: Maximum tokens in bucket (default: 5)
            refill_rate: Tokens added per second (default: 5.0 for 5 tokens/sec)
            retry_sleep: Sleep duration when tokens unavailable (default: 0.05s)
            now: Clock function for time operations (default: time.monotonic)
            sleeper: Async sleep function (default: asyncio.sleep)
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.retry_sleep = retry_sleep
        self._now = now
        self._sleep = sleeper
        
        # Per-endpoint token buckets: {endpoint: (tokens, last_refill_time)}
        self._buckets: Dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()
    
    async def acquire(self, endpoint: str) -> None:
        """Acquire a token for the specified endpoint.
        
        Blocks until a token is available, using sleep(0.05) retry when empty.
        Maintains precise rate limiting of ≤5 requests per second per endpoint.
        
        Args:
            endpoint: The endpoint identifier for rate limiting
        """
        while True:
            async with self._lock:
                tokens, last_refill = self._get_bucket_state(endpoint)
                
                if tokens >= 1.0:
                    # Token available, consume it
                    new_tokens = tokens - 1.0
                    self._buckets[endpoint] = (new_tokens, last_refill)
                    return
            
            # No tokens available, sleep and retry
            await self._sleep(self.retry_sleep)
    
    def tokens_available(self, endpoint: str) -> int:
        """Get the number of tokens currently available for an endpoint.
        
        Used for monitoring and testing purposes.
        
        Args:
            endpoint: The endpoint identifier
            
        Returns:
            Number of tokens available (floored to integer)
        """
        tokens, _ = self._get_bucket_state(endpoint)
        return int(tokens)
    
    def _get_bucket_state(self, endpoint: str) -> tuple[float, float]:
        """Get current bucket state with token refill calculation.
        
        Args:
            endpoint: The endpoint identifier
            
        Returns:
            Tuple of (current_tokens, last_refill_time)
        """
        current_time = self._now()
        
        if endpoint not in self._buckets:
            # Initialize new bucket with full tokens
            self._buckets[endpoint] = (float(self.max_tokens), current_time)
            return (float(self.max_tokens), current_time)
        
        tokens, last_refill = self._buckets[endpoint]
        
        # Calculate tokens to add based on elapsed time
        time_elapsed = current_time - last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        
        # Refill tokens up to maximum
        new_tokens = min(self.max_tokens, tokens + tokens_to_add)
        
        # Update bucket state
        self._buckets[endpoint] = (new_tokens, current_time)
        
        return (new_tokens, current_time)