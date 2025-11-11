"""Thread-safe aggregator for collecting pipeline results."""

import threading
from typing import Dict, List

from src.models.data_models import ErrorRecord, Product, SourceSummary, Summary


class ThreadSafeAggregator:
    """
    Thread-safe aggregator for collecting products and errors.
    
    Uses locks to prevent race conditions when multiple threads
    add data concurrently.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._products: List[Product] = []
        self._errors: List[ErrorRecord] = []
        self._seen_ids: set = set()
        self._start_time: float = 0.0
        self._end_time: float = 0.0
    
    def start_timer(self) -> None:
        """Start timing the pipeline execution."""
        import time
        self._start_time = time.time()
    
    def stop_timer(self) -> None:
        """Stop timing the pipeline execution."""
        import time
        self._end_time = time.time()
    
    def add_products(self, products: List[Product]) -> None:
        """
        Add products with deduplication.
        
        Args:
            products: List of products to add
        """
        with self._lock:
            for product in products:
                if product.id not in self._seen_ids:
                    self._products.append(product)
                    self._seen_ids.add(product.id)
    
    def add_error(self, error: ErrorRecord) -> None:
        """
        Add error record.
        
        Args:
            error: Error record to add
        """
        with self._lock:
            self._errors.append(error)
    
    def get_summary(self) -> Summary:
        """
        Generate summary statistics.
        
        Returns:
            Summary with total products, processing time, success rate
        """
        with self._lock:
            processing_time = self._end_time - self._start_time if self._end_time > 0 else 0.0
            
            # Calculate success rate
            total_attempts = len(self._products) + len(self._errors)
            success_rate = len(self._products) / total_attempts if total_attempts > 0 else 0.0
            
            return Summary(
                total_products=len(self._products),
                processing_time_seconds=processing_time,
                success_rate=success_rate
            )
    
    def get_source_summaries(self) -> List[SourceSummary]:
        """
        Generate per-source statistics.
        
        Returns:
            List of SourceSummary with items_fetched, errors, avg_price per source
        """
        with self._lock:
            # Group products by source
            source_products: Dict[str, List[Product]] = {}
            for product in self._products:
                source_products.setdefault(product.source, []).append(product)
            
            # Group errors by source
            source_errors: Dict[str, int] = {}
            for error in self._errors:
                source_errors[error.source] = source_errors.get(error.source, 0) + 1
            
            # Generate summaries
            summaries = []
            for source, products in source_products.items():
                # Calculate avg price
                prices = [p.price for p in products if p.price is not None]
                avg_price = sum(prices) / len(prices) if prices else None
                
                summaries.append(SourceSummary(
                    name=source,
                    items_fetched=len(products),
                    errors=source_errors.get(source, 0),
                    avg_price=avg_price
                ))
            
            return summaries
    
    def get_products(self) -> List[Product]:
        """Get all products."""
        with self._lock:
            return self._products.copy()
    
    def get_errors(self) -> List[ErrorRecord]:
        """Get all errors."""
        with self._lock:
            return self._errors.copy()
