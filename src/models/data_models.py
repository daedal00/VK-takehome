"""Core data models for the async data pipeline."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ErrorAction(Enum):
    """Actions to take when errors occur."""
    RETRY = "retry"
    SKIP = "skip"
    CB_OPEN = "circuit_break"


@dataclass
class Product:
    """Unified product data model."""
    id: str  # Format: "sourceName:sourceId"
    title: str
    source: str
    price: Optional[float]
    category: str
    processed_at: str  # ISO-8601 UTC timestamp


@dataclass
class ErrorRecord:
    """Error information for tracking and reporting."""
    source: str
    page: int
    code: Optional[int]
    error: str
    timestamp: str  # ISO-8601 UTC
    action: ErrorAction


@dataclass
class HalfOpenToken:
    """Token for tracking half-open circuit breaker requests."""
    endpoint: str
    timestamp: float


@dataclass
class EndpointStats:
    """Statistics for a single endpoint."""
    name: str
    pages_fetched: int
    items_fetched: int
    errors: int
    total_duration: float


@dataclass
class Summary:
    """Pipeline execution summary."""
    total_products: int
    processing_time_seconds: float
    success_rate: float  # Range 0.0-1.0


@dataclass
class SourceSummary:
    """Per-source statistics summary."""
    name: str
    items_fetched: int
    errors: int
    avg_price: Optional[float]


@dataclass
class PipelineResult:
    """Complete pipeline execution result."""
    summary: Summary
    sources: List[SourceSummary]
    products: List[Product]
    errors: List[ErrorRecord]


@dataclass
class FetchResult:
    """Result of fetching from a single endpoint."""
    endpoint: str
    products: List[Dict]
    success: bool
    error: Optional[str]
    duration: float


@dataclass
class ProcessorStats:
    """Statistics from the data processor."""
    products_processed: int
    batches_processed: int
    processing_time: float
    errors: int