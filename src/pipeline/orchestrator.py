"""Pipeline orchestrator coordinating fetch and process phases."""

import asyncio
from typing import List

from src.fetcher.async_fetcher import AsyncFetcher
from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.models.data_models import PipelineResult
from src.processor import DataProcessor, ThreadSafeAggregator


class PipelineOrchestrator:
    """Orchestrates the complete data pipeline."""
    
    def __init__(
        self,
        endpoints: List[str],
        queue_size: int = 100,
        worker_pool_size: int = 4
    ):
        self.endpoints = endpoints
        self.queue_size = queue_size
        self.worker_pool_size = worker_pool_size
    
    async def run(self) -> PipelineResult:
        """
        Run the complete pipeline: fetch → process → aggregate.
        
        Returns:
            PipelineResult with summary, sources, products, errors
        """
        # Initialize components
        rate_limiter = RateLimiter()
        circuit_breaker = CircuitBreaker()
        processor = DataProcessor(worker_pool_size=self.worker_pool_size)
        aggregator = ThreadSafeAggregator()
        
        # Create bounded queue
        queue = asyncio.Queue(maxsize=self.queue_size)
        
        aggregator.start_timer()
        
        async with AsyncHTTPClient() as http_client:
            fetcher = AsyncFetcher(rate_limiter, circuit_breaker, http_client)
            
            # Start processor task
            processor_task = asyncio.create_task(
                processor.consume_queue(queue, sentinel=None)
            )
            
            # Fetch from all endpoints
            stats_dict = await fetcher.fetch_all_endpoints(self.endpoints, queue)
            
            # Send sentinel to stop processor
            await queue.put(None)
            
            # Wait for processor to finish
            processor_stats = await processor_task
        
        aggregator.stop_timer()
        
        # Aggregate results
        products = processor.get_products()
        aggregator.add_products(products)
        
        # Generate result
        summary = aggregator.get_summary()
        sources = aggregator.get_source_summaries()
        
        return PipelineResult(
            summary=summary,
            sources=sources,
            products=products,
            errors=[]  # TODO: collect errors from fetcher
        )
