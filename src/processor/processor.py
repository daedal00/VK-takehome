"""Data processor with ThreadPoolExecutor for CPU-bound normalization."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from src.models.data_models import Product, ProcessorStats
from src.processor.normalizer import normalize_batch


class DataProcessor:
    """
    Processes fetched data using ThreadPoolExecutor.
    
    Consumes pages from queue, normalizes in worker threads,
    and aggregates results.
    """
    
    def __init__(self, worker_pool_size: int = 4, batch_size: int = 50, logger=None):
        """
        Initialize processor.
        
        Args:
            worker_pool_size: Number of worker threads
            batch_size: Maximum items per batch
            logger: Optional structured logger
        """
        self.worker_pool_size = worker_pool_size
        self.batch_size = batch_size
        self.products: List[Product] = []
        self.batches_processed = 0
        self.seen_ids: set = set()  # For deduplication
        self.logger = logger
    
    async def consume_queue(
        self,
        queue: asyncio.Queue,
        sentinel: object = None
    ) -> ProcessorStats:
        """
        Consume pages from queue and process them.
        
        Args:
            queue: Queue with page data
            sentinel: Sentinel value to signal completion
            
        Returns:
            Processing statistics
        """
        start_time = asyncio.get_event_loop().time()
        
        with ThreadPoolExecutor(max_workers=self.worker_pool_size) as executor:
            loop = asyncio.get_event_loop()
            
            while True:
                page_data = await queue.get()
                
                # Log queue depth periodically
                if self.logger and self.batches_processed % 10 == 0:
                    self.logger.queue_depth(size=queue.qsize())
                
                # Check for sentinel
                if page_data is sentinel:
                    break
                
                # Extract products
                products = page_data.get("data", {}).get("products", [])
                source = page_data.get("endpoint", "unknown")
                
                # Process in thread pool (CPU-bound) with deduplication
                batch_start = asyncio.get_event_loop().time()
                normalized = await loop.run_in_executor(
                    executor,
                    normalize_batch,
                    products,
                    source,
                    self.seen_ids
                )
                batch_elapsed = (asyncio.get_event_loop().time() - batch_start) * 1000
                
                self.products.extend(normalized)
                self.batches_processed += 1
                
                if self.logger:
                    self.logger.batch_processed(
                        batch_size=len(normalized),
                        elapsed_ms=batch_elapsed
                    )
        
        processing_time = asyncio.get_event_loop().time() - start_time
        
        return ProcessorStats(
            products_processed=len(self.products),
            batches_processed=self.batches_processed,
            processing_time=processing_time,
            errors=0
        )
    
    def get_products(self) -> List[Product]:
        """Get all processed products."""
        return self.products
    
    def calculate_metrics(self) -> Dict:
        """
        Calculate aggregated metrics.
        
        Returns:
            Dictionary with metrics (avg_price per source, category counts)
        """
        if not self.products:
            return {"sources": {}, "categories": {}}
        
        # Calculate per-source metrics
        source_prices: Dict[str, List[float]] = {}
        for product in self.products:
            if product.price is not None:
                source_prices.setdefault(product.source, []).append(product.price)
        
        source_metrics = {
            source: sum(prices) / len(prices)
            for source, prices in source_prices.items()
        }
        
        # Calculate category distribution
        category_counts: Dict[str, int] = {}
        for product in self.products:
            category_counts[product.category] = category_counts.get(product.category, 0) + 1
        
        return {
            "sources": source_metrics,
            "categories": category_counts
        }
