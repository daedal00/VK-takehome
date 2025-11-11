"""Unit tests for retry handler with exponential backoff."""

import pytest
from unittest.mock import Mock

from src.fetcher.retry_handler import RetryHandler, calculate_backoff_delay


class TestBackoffCalculation:
    """Test exponential backoff formula: min(4.0, (0.5 * (2 ** attempt)) + jitter)."""
    
    def test_first_attempt_base_delay(self):
        # Attempt 0: 0.5 * (2^0) = 0.5, plus jitter [0, 0.5]
        delay = calculate_backoff_delay(0, max_delay=4.0, jitter_max=0.0)
        assert delay == 0.5
    
    def test_second_attempt_doubles(self):
        # Attempt 1: 0.5 * (2^1) = 1.0
        delay = calculate_backoff_delay(1, max_delay=4.0, jitter_max=0.0)
        assert delay == 1.0
    
    def test_third_attempt_doubles_again(self):
        # Attempt 2: 0.5 * (2^2) = 2.0
        delay = calculate_backoff_delay(2, max_delay=4.0, jitter_max=0.0)
        assert delay == 2.0
    
    def test_caps_at_max_delay(self):
        # Attempt 3: 0.5 * (2^3) = 4.0 (at cap)
        delay = calculate_backoff_delay(3, max_delay=4.0, jitter_max=0.0)
        assert delay == 4.0
        
        # Attempt 4: 0.5 * (2^4) = 8.0, but capped at 4.0
        delay = calculate_backoff_delay(4, max_delay=4.0, jitter_max=0.0)
        assert delay == 4.0
    
    def test_jitter_adds_randomness(self):
        # With jitter, delay should be in range [base, base + jitter_max]
        delays = [calculate_backoff_delay(0, max_delay=4.0, jitter_max=0.5) for _ in range(100)]
        
        assert all(0.5 <= d <= 1.0 for d in delays)
        assert min(delays) >= 0.5
        assert max(delays) <= 1.0
    
    def test_jitter_respects_max_delay(self):
        # Even with jitter, should not exceed max_delay
        delays = [calculate_backoff_delay(3, max_delay=4.0, jitter_max=0.5) for _ in range(100)]
        
        assert all(d <= 4.0 for d in delays)
    
    def test_deterministic_backoff_formula_verification(self):
        """Verify exact backoff formula: min(4.0, (0.5 * (2 ** attempt)) + jitter)."""
        # Test without jitter for deterministic verification
        test_cases = [
            (0, 0.5),   # 0.5 * (2^0) = 0.5
            (1, 1.0),   # 0.5 * (2^1) = 1.0
            (2, 2.0),   # 0.5 * (2^2) = 2.0
            (3, 4.0),   # 0.5 * (2^3) = 4.0 (at cap)
            (4, 4.0),   # 0.5 * (2^4) = 8.0, capped at 4.0
            (5, 4.0),   # 0.5 * (2^5) = 16.0, capped at 4.0
        ]
        
        for attempt, expected_delay in test_cases:
            actual_delay = calculate_backoff_delay(attempt, max_delay=4.0, jitter_max=0.0)
            assert actual_delay == expected_delay, \
                f"Attempt {attempt}: expected {expected_delay}, got {actual_delay}"
    
    def test_backoff_formula_with_jitter_bounds(self):
        """Verify backoff formula with jitter stays within bounds."""
        # With jitter_max=0.5, delay should be in [base, base + 0.5]
        test_cases = [
            (0, 0.5, 1.0),    # base=0.5, range [0.5, 1.0]
            (1, 1.0, 1.5),    # base=1.0, range [1.0, 1.5]
            (2, 2.0, 2.5),    # base=2.0, range [2.0, 2.5]
            (3, 4.0, 4.0),    # base=4.0, capped at max_delay=4.0
        ]
        
        for attempt, min_expected, max_expected in test_cases:
            delays = [calculate_backoff_delay(attempt, max_delay=4.0, jitter_max=0.5) 
                     for _ in range(50)]
            
            assert all(min_expected <= d <= max_expected for d in delays), \
                f"Attempt {attempt}: delays outside [{min_expected}, {max_expected}]"


class TestRetryHandler:
    
    @pytest.fixture
    def retry_handler(self):
        return RetryHandler(max_retries=3, base_delay=0.5, max_delay=4.0, jitter_max=0.5)
    
    def test_initialization(self, retry_handler):
        assert retry_handler.max_retries == 3
        assert retry_handler.base_delay == 0.5
        assert retry_handler.max_delay == 4.0
    
    def test_is_retryable_status_429(self, retry_handler):
        assert retry_handler.is_retryable(status_code=429) is True
    
    def test_is_retryable_status_502(self, retry_handler):
        assert retry_handler.is_retryable(status_code=502) is True
    
    def test_is_retryable_status_503(self, retry_handler):
        assert retry_handler.is_retryable(status_code=503) is True
    
    def test_is_retryable_status_504(self, retry_handler):
        assert retry_handler.is_retryable(status_code=504) is True
    
    def test_is_retryable_timeout(self, retry_handler):
        assert retry_handler.is_retryable(is_timeout=True) is True
    
    def test_not_retryable_status_400(self, retry_handler):
        assert retry_handler.is_retryable(status_code=400) is False
    
    def test_not_retryable_status_404(self, retry_handler):
        assert retry_handler.is_retryable(status_code=404) is False
    
    def test_not_retryable_status_500(self, retry_handler):
        # 500 is not in retryable list (only 502, 503, 504)
        assert retry_handler.is_retryable(status_code=500) is False
    
    @pytest.mark.asyncio
    async def test_execute_success_first_try(self, retry_handler):
        mock_func = Mock(return_value="success")
        
        result = await retry_handler.execute(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_retries_on_retryable_error(self, retry_handler):
        mock_func = Mock(side_effect=[
            Exception("429 error"),
            Exception("502 error"),
            "success"
        ])
        
        # Mock is_retryable to return True for these exceptions
        retry_handler.is_retryable = Mock(return_value=True)
        
        result = await retry_handler.execute(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_fails_after_max_retries(self, retry_handler):
        mock_func = Mock(side_effect=Exception("persistent error"))
        retry_handler.is_retryable = Mock(return_value=True)
        
        with pytest.raises(Exception, match="persistent error"):
            await retry_handler.execute(mock_func)
        
        # Should try: initial + 3 retries = 4 total
        assert mock_func.call_count == 4
    
    @pytest.mark.asyncio
    async def test_execute_no_retry_on_non_retryable(self, retry_handler):
        mock_func = Mock(side_effect=Exception("400 error"))
        retry_handler.is_retryable = Mock(return_value=False)
        
        with pytest.raises(Exception, match="400 error"):
            await retry_handler.execute(mock_func)
        
        # Should only try once
        assert mock_func.call_count == 1
