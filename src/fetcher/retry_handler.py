"""Retry handler with exponential backoff and jitter."""

import asyncio
import random
from typing import Any, Callable, Optional, Set


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    jitter_max: float = 0.5
) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Formula: min(max_delay, (base_delay * (2 ** attempt)) + random_jitter)
    
    Args:
        attempt: Retry attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter_max: Maximum jitter to add in seconds
        
    Returns:
        Delay in seconds
    """
    exponential_delay = base_delay * (2 ** attempt)
    jitter = random.uniform(0, jitter_max)
    return min(max_delay, exponential_delay + jitter)


class RetryHandler:
    """
    Handles retry logic with exponential backoff for HTTP requests.
    
    Retries on: 429, 502, 503, 504 status codes and timeouts
    Max retries: 3 (configurable)
    Backoff: Exponential with jitter, capped at 4 seconds
    """
    
    RETRYABLE_STATUS_CODES: Set[int] = {429, 502, 503, 504}
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 4.0,
        jitter_max: float = 0.5
    ):
        """
        Initialize retry handler.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff
            max_delay: Maximum delay cap
            jitter_max: Maximum jitter to add
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_max = jitter_max
    
    def is_retryable(
        self,
        status_code: Optional[int] = None,
        is_timeout: bool = False
    ) -> bool:
        """
        Check if error is retryable.
        
        Args:
            status_code: HTTP status code
            is_timeout: Whether the error was a timeout
            
        Returns:
            True if error should be retried
        """
        if is_timeout:
            return True
        if status_code in self.RETRYABLE_STATUS_CODES:
            return True
        return False
    
    async def execute(
        self,
        func: Callable[[], Any],
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from successful function execution
            
        Raises:
            Exception: If all retries exhausted
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if attempt >= self.max_retries:
                    # No more retries left
                    raise
                
                # Check if error is retryable
                if not self.is_retryable():
                    # Non-retryable error, fail immediately
                    raise
                
                # Calculate backoff delay
                delay = calculate_backoff_delay(
                    attempt,
                    self.base_delay,
                    self.max_delay,
                    self.jitter_max
                )
                
                # Wait before retry
                await asyncio.sleep(delay)
        
        # Should not reach here, but raise last exception if we do
        if last_exception:
            raise last_exception
