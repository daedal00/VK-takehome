"""Unit tests for circuit breaker."""

import pytest

from src.fetcher.circuit_breaker import CircuitBreaker, MonotonicClock
from src.models.data_models import CircuitState, HalfOpenToken


class FakeClock:
    """Fake clock for testing."""
    
    def __init__(self, initial_time: float = 0.0):
        self._current_time = initial_time
    
    def now(self) -> float:
        return self._current_time
    
    def advance(self, seconds: float) -> None:
        self._current_time += seconds


class TestCircuitBreakerBasics:
    
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state("endpoint1") == CircuitState.CLOSED
    
    def test_closed_circuit_allows_requests(self):
        cb = CircuitBreaker()
        assert cb.should_allow("endpoint1") is True
    
    def test_uses_monotonic_clock_by_default(self):
        cb = CircuitBreaker()
        assert isinstance(cb.clock, MonotonicClock)
    
    def test_accepts_custom_clock(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(clock=fake_clock)
        assert cb.clock is fake_clock


class TestCircuitBreakerStateTransitions:
    
    def test_opens_after_threshold_failures(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        
        assert cb.state("endpoint1") == CircuitState.OPEN
    
    def test_open_circuit_rejects_requests(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        
        assert cb.should_allow("endpoint1") is False
    
    def test_transitions_to_half_open_after_cooldown(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        
        fake_clock.advance(15.0)
        result = cb.should_allow("endpoint1")
        
        assert isinstance(result, HalfOpenToken)
        assert cb.state("endpoint1") == CircuitState.HALF_OPEN
    
    def test_half_open_allows_single_probe(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        fake_clock.advance(15.0)
        
        token = cb.should_allow("endpoint1")
        assert isinstance(token, HalfOpenToken)
        
        # Second request rejected
        assert cb.should_allow("endpoint1") is False
    
    def test_closes_on_successful_probe(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        fake_clock.advance(15.0)
        token = cb.should_allow("endpoint1")
        
        cb.record_success("endpoint1", token=token)
        
        assert cb.state("endpoint1") == CircuitState.CLOSED
    
    def test_reopens_on_failed_probe(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        fake_clock.advance(15.0)
        cb.should_allow("endpoint1")
        
        cb.record_failure("endpoint1", retryable=True)
        
        assert cb.state("endpoint1") == CircuitState.OPEN


class TestCircuitBreakerFailureHandling:
    
    def test_non_retryable_failures_ignored(self):
        cb = CircuitBreaker(failure_threshold=3)
        
        for _ in range(5):
            cb.record_failure("endpoint1", retryable=False)
        
        assert cb.state("endpoint1") == CircuitState.CLOSED
    
    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure("endpoint1", retryable=True)
        cb.record_failure("endpoint1", retryable=True)
        cb.record_success("endpoint1")
        cb.record_failure("endpoint1", retryable=True)
        cb.record_failure("endpoint1", retryable=True)
        
        assert cb.state("endpoint1") == CircuitState.CLOSED
    
    def test_only_retryable_failures_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure("endpoint1", retryable=True)
        cb.record_failure("endpoint1", retryable=False)
        cb.record_failure("endpoint1", retryable=True)
        cb.record_failure("endpoint1", retryable=False)
        cb.record_failure("endpoint1", retryable=True)
        
        assert cb.state("endpoint1") == CircuitState.OPEN


class TestCircuitBreakerPerEndpoint:
    
    def test_independent_circuits(self):
        cb = CircuitBreaker(failure_threshold=3)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        
        assert cb.state("endpoint1") == CircuitState.OPEN
        assert cb.state("endpoint2") == CircuitState.CLOSED
    
    def test_multiple_endpoints_different_states(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=15.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        cb.record_failure("endpoint2", retryable=True)
        
        fake_clock.advance(15.0)
        cb.should_allow("endpoint1")
        
        assert cb.state("endpoint1") == CircuitState.HALF_OPEN
        assert cb.state("endpoint2") == CircuitState.CLOSED


class TestCircuitBreakerConfiguration:
    
    def test_custom_failure_threshold(self):
        cb = CircuitBreaker(failure_threshold=5)
        
        for _ in range(4):
            cb.record_failure("endpoint1", retryable=True)
        assert cb.state("endpoint1") == CircuitState.CLOSED
        
        cb.record_failure("endpoint1", retryable=True)
        assert cb.state("endpoint1") == CircuitState.OPEN
    
    def test_custom_cooldown_period(self):
        fake_clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0, clock=fake_clock)
        
        for _ in range(3):
            cb.record_failure("endpoint1", retryable=True)
        
        fake_clock.advance(29.0)
        assert cb.should_allow("endpoint1") is False
        
        fake_clock.advance(1.0)
        assert isinstance(cb.should_allow("endpoint1"), HalfOpenToken)
