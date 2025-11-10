"""Circuit breaker implementation with explicit state management."""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Union

from src.models.data_models import CircuitState, HalfOpenToken


class Clock(Protocol):
    """Clock interface for testable time management."""
    
    def now(self) -> float:
        """Return current time in seconds."""
        ...


class MonotonicClock:
    """Default clock implementation using time.monotonic."""
    
    def now(self) -> float:
        """Return current monotonic time in seconds."""
        return time.monotonic()


@dataclass
class CircuitBreakerState:
    """Internal state for a single circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_token: Optional[HalfOpenToken] = None


class CircuitBreaker:
    """
    Circuit breaker with CLOSED/OPEN/HALF_OPEN states.
    
    Prevents calls to failing services with configurable thresholds:
    - Opens after 3 consecutive retryable failures
    - Stays open for 15 seconds cooldown
    - Transitions to half-open for single probe request
    - Closes on successful probe or opens again on failure
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 15.0,
        clock: Optional[Clock] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            cooldown_seconds: Time to wait before attempting half-open probe
            clock: Clock interface for time management (defaults to MonotonicClock)
        """
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock or MonotonicClock()
        self._circuits: Dict[str, CircuitBreakerState] = {}
    
    def _get_circuit(self, endpoint: str) -> CircuitBreakerState:
        """Get or create circuit state for endpoint."""
        if endpoint not in self._circuits:
            self._circuits[endpoint] = CircuitBreakerState()
        return self._circuits[endpoint]

    def should_allow(self, endpoint: str) -> Union[bool, HalfOpenToken]:
        """
        Check if request should be allowed for endpoint.
        
        Args:
            endpoint: Endpoint identifier
            
        Returns:
            - True if circuit is CLOSED (allow request)
            - False if circuit is OPEN (reject request)
            - HalfOpenToken if circuit is HALF_OPEN (allow probe request)
        """
        circuit = self._get_circuit(endpoint)
        current_time = self.clock.now()
        
        if circuit.state == CircuitState.CLOSED:
            return True
        
        elif circuit.state == CircuitState.OPEN:
            # Check if cooldown period has elapsed
            time_since_failure = current_time - circuit.last_failure_time
            if time_since_failure >= self.cooldown_seconds:
                # Transition to HALF_OPEN and issue probe token
                circuit.state = CircuitState.HALF_OPEN
                token = HalfOpenToken(endpoint=endpoint, timestamp=current_time)
                circuit.half_open_token = token
                return token
            else:
                # Still in cooldown, reject request
                return False
        
        elif circuit.state == CircuitState.HALF_OPEN:
            # Only allow one probe request at a time
            if circuit.half_open_token is not None:
                # Probe already in progress, reject additional requests
                return False
            else:
                # Issue new probe token (shouldn't normally happen)
                token = HalfOpenToken(endpoint=endpoint, timestamp=current_time)
                circuit.half_open_token = token
                return token
        
        return False
    
    def record_success(self, endpoint: str, token: Optional[HalfOpenToken] = None) -> None:
        """
        Record successful request for endpoint.
        
        Args:
            endpoint: Endpoint identifier
            token: HalfOpenToken if this was a half-open probe request
        
        Note:
            In HALF_OPEN state, closes the circuit even without token to avoid
            sticky half-open state. This is pragmatic for integration safety.
        """
        circuit = self._get_circuit(endpoint)
        
        if circuit.state == CircuitState.HALF_OPEN:
            # Successful probe - close the circuit
            # Close even without token to avoid sticky half-open state
            circuit.state = CircuitState.CLOSED
            circuit.failure_count = 0
            circuit.half_open_token = None
            return
        
        if circuit.state == CircuitState.CLOSED:
            # Reset failure count on success
            circuit.failure_count = 0

    def record_failure(self, endpoint: str, retryable: bool) -> None:
        """
        Record failed request for endpoint.
        
        Args:
            endpoint: Endpoint identifier
            retryable: Whether the failure is retryable (affects circuit breaker)
        """
        circuit = self._get_circuit(endpoint)
        current_time = self.clock.now()
        
        # Only count retryable failures toward circuit breaker threshold
        if not retryable:
            return
        
        if circuit.state == CircuitState.CLOSED:
            circuit.failure_count += 1
            circuit.last_failure_time = current_time
            
            # Check if threshold reached
            if circuit.failure_count >= self.failure_threshold:
                circuit.state = CircuitState.OPEN
        
        elif circuit.state == CircuitState.HALF_OPEN:
            # Failed probe - reopen circuit
            circuit.state = CircuitState.OPEN
            circuit.failure_count = self.failure_threshold
            circuit.last_failure_time = current_time
            circuit.half_open_token = None
    
    def state(self, endpoint: str) -> CircuitState:
        """
        Get current circuit state for endpoint.
        
        Args:
            endpoint: Endpoint identifier
            
        Returns:
            Current CircuitState (CLOSED, OPEN, or HALF_OPEN)
        """
        circuit = self._get_circuit(endpoint)
        return circuit.state
    
    def reset(self, endpoint: str) -> None:
        """Reset circuit breaker for endpoint (useful for testing)."""
        if endpoint in self._circuits:
            self._circuits[endpoint] = CircuitBreakerState()
