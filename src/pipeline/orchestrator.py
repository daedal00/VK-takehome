"""Pipeline orchestrator coordinating fetch and process phases."""

import asyncio
from typing import List

from src.fetcher.async_fetcher import AsyncFetcher
from src.fetcher.circuit_breaker import CircuitBreaker
from src.fetcher.http_client import AsyncHTTPClient
from src.fetcher.rate_limiter import RateLimiter
from src.models.config import PipelineConfig
from src.models.data_models import PipelineResult
from src.monitoring.logger import StructuredLogger
from src.processor import DataProcessor, ThreadSafeAggregator


class PipelineOrchestrator:
    """Orchestrates the complete data pipeline."""
    
    def __init__(self, config: PipelineConfig):
        """
        Initialize orchestrator with pipeline configuration.
        
        Args:
            config: Pipeline configuration object
        """
        self.config = config
        self.endpoints = [ep.url for ep in config.endpoints]
        self.queue_size = config.bounded_queue_size
        self.worker_pool_size = config.worker_pool_size
        self.logger = StructuredLogger(level=config.log_level)
    
    async def run(self) -> PipelineResult:
        """
        Run the complete pipeline: fetch → process → aggregate.
        
        Enforces total_timeout constraint from configuration.
        
        Returns:
            PipelineResult with summary, sources, products, errors
            
        Raises:
            asyncio.TimeoutError: If pipeline exceeds total_timeout
        """
        try:
            return await asyncio.wait_for(
                self._run_pipeline(),
                timeout=self.config.total_timeout
            )
        except asyncio.TimeoutError:
            self.logger.log("pipeline_timeout", timeout=self.config.total_timeout)
            raise
    
    async def _run_pipeline(self) -> PipelineResult:
        """Internal pipeline execution without timeout wrapper."""
        # Initialize components with configuration
        rate_limiter = RateLimiter(
            max_tokens=self.config.rate_limit_tokens,
            refill_rate=self.config.max_requests_per_second
        )
        circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            cooldown_seconds=self.config.circuit_breaker_cooldown,
            logger=self.logger
        )
        processor = DataProcessor(
            worker_pool_size=self.worker_pool_size,
            batch_size=self.config.processing_batch_size,
            logger=self.logger
        )
        aggregator = ThreadSafeAggregator()
        
        # Create bounded queue
        queue = asyncio.Queue(maxsize=self.queue_size)
        
        self.logger.log("pipeline_start", endpoints=len(self.endpoints))
        aggregator.start_timer()
        
        async with AsyncHTTPClient(
            connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout
        ) as http_client:
            fetcher = AsyncFetcher(
                rate_limiter,
                circuit_breaker,
                http_client,
                max_retries=self.config.max_retries,
                retry_base_delay=self.config.retry_base_delay,
                retryable_status_codes=self.config.retryable_status_codes,
                logger=self.logger
            )
            
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
        
        # Collect detailed errors from fetch stats and add to aggregator
        for endpoint, stats in stats_dict.items():
            for error_record in stats.error_details:
                aggregator.add_error(error_record)
        
        # Generate result
        summary = aggregator.get_summary()
        sources = aggregator.get_source_summaries()
        errors = aggregator.get_errors()
        
        return PipelineResult(
            summary=summary,
            sources=sources,
            products=products,
            errors=errors
        )
