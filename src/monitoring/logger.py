"""Structured logging for pipeline monitoring."""

import json
import logging
from typing import Any, Dict, Optional


class StructuredLogger:
    """Structured logger with uniform schema."""
    
    def __init__(self, name: str = "pipeline", level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
    
    def log(self, event: str, **kwargs) -> None:
        """
        Log structured event.
        
        Standard keys: event, source, page, status, attempt, elapsed_ms, 
                      cb_state, queue_size, batch_size
        """
        log_data = {"event": event, **kwargs}
        self.logger.info(json.dumps(log_data))
    
    def fetch_start(self, source: str, page: int) -> None:
        self.log("fetch_start", source=source, page=page)
    
    def fetch_success(self, source: str, page: int, elapsed_ms: float) -> None:
        self.log("fetch_success", source=source, page=page, elapsed_ms=elapsed_ms)
    
    def fetch_error(self, source: str, page: int, status: Optional[int], error: str, attempt: int) -> None:
        self.log("fetch_error", source=source, page=page, status=status, error=error, attempt=attempt)
    
    def circuit_breaker_state(self, source: str, state: str) -> None:
        self.log("circuit_breaker", source=source, cb_state=state)
    
    def queue_depth(self, size: int) -> None:
        self.log("queue_depth", queue_size=size)
    
    def batch_processed(self, batch_size: int, elapsed_ms: float) -> None:
        self.log("batch_processed", batch_size=batch_size, elapsed_ms=elapsed_ms)
