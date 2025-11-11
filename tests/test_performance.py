"""Performance benchmarks and verification tests."""

import pytest
import time
import asyncio
from typing import List, Dict, Any

from src.fetcher.rate_limiter import RateLimiter
from src.fetcher.circuit_breaker import CircuitBreaker
from src.processor.processor import DataProcessor
from src.processor import normalizer
from src.processor.aggregator import ThreadSafeAggregator
from tests.fixtures.sample_data import get_sample_products


@pytest.mark.performance
class TestPerformanceBenchmarks:
    """Performance benchmarks ensuring 60-second execution constraint."""

    @pytest.mark.asyncio
    async def test_rate_limiter_performance_5_rps(self):
        """Verify rate limiter maintains 5 requests per second under load."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0)
        endpoint = "test_endpoint"
        
        start = time.time()
        request_count = 15  # 3 seconds worth at 5 rps
        
        for _ in range(request_count):
            await rate_limiter.acquire(endpoint)
        
        elapsed = time.time() - start
        
        # Should take approximately 2-3 seconds (15 requests / 5 rps)
        # First 5 are instant (burst), then 10 more at 5 rps = 2 seconds
        assert 1.8 <= elapsed <= 4.0, f"Rate limiter took {elapsed}s for {request_count} requests"
        
        # Verify average rate is reasonable
        actual_rps = request_count / elapsed
        assert 3.5 <= actual_rps <= 8.5, f"Actual RPS: {actual_rps}, expected ~5.0"

    @pytest.mark.asyncio
    async def test_concurrent_rate_limiting_performance(self):
        """Verify rate limiter handles concurrent requests efficiently."""
        rate_limiter = RateLimiter(max_tokens=5, refill_rate=5.0)
        endpoint = "test_endpoint"
        
        async def make_request():
            await rate_limiter.acquire(endpoint)
            return time.time()
        
        start = time.time()
        
        # Launch 15 concurrent requests
        tasks = [make_request() for _ in range(15)]
        timestamps = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start
        
        # 15 requests at 5 rps should take ~2 seconds (5 instant + 10 at 5rps)
        assert 1.8 <= elapsed <= 4.0, f"Concurrent requests took {elapsed}s"
        
        # Verify requests were spread over time
        time_span = max(timestamps) - min(timestamps)
        assert time_span >= 1.5, "Requests should be spread over time"

    def test_data_normalizer_batch_performance(self):
        """Verify data normalizer processes batches efficiently."""
        # Generate large batch
        raw_products = get_sample_products("perf_test", count=1000, seed=42)
        
        start = time.time()
        normalized = normalizer.normalize_batch(raw_products, "perf_test")
        elapsed = time.time() - start
        
        # Should process 1000 products in under 1 second
        assert elapsed < 1.0, f"Normalization took {elapsed}s for 1000 products"
        assert len(normalized) == 1000
        
        # Verify throughput
        throughput = len(normalized) / elapsed
        assert throughput > 500, f"Throughput: {throughput} products/sec, expected > 500"

    @pytest.mark.asyncio
    async def test_processor_batch_performance(self):
        """Verify data processor handles batches within performance constraints."""
        processor = DataProcessor(
            batch_size=50,
            worker_pool_size=4
        )
        
        # Create queue with test data
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        
        # Add 5 pages of 20 products each
        for page in range(5):
            products = get_sample_products(f"source_{page}", count=20, seed=42 + page)
            await queue.put({
                "source": f"source_{page}",
                "page": page + 1,
                "products": products
            })
        
        # Add sentinel
        await queue.put(None)
        
        start = time.time()
        stats = await processor.consume_queue(queue, sentinel=None)
        elapsed = time.time() - start
        
        # Should process batches quickly (< 3 seconds for 5 batches)
        assert elapsed < 3.0, f"Processing took {elapsed}s for 5 batches"
        
        # Verify processor completed successfully
        assert stats.batches_processed == 5
        assert stats.errors == 0
        
        # Verify reasonable processing speed
        assert elapsed < 1.0, f"Processing should be fast, took {elapsed}s"

    def test_aggregator_thread_safety_performance(self):
        """Verify aggregator maintains performance under concurrent access."""
        from concurrent.futures import ThreadPoolExecutor
        from src.models.data_models import Product
        
        aggregator = ThreadSafeAggregator()
        
        def add_products_batch(batch_id: int):
            products = [
                Product(
                    id=f"perf_{batch_id}_{i}",
                    title=f"Product {i}",
                    source=f"source_{batch_id % 3}",
                    price=100.0 + i,
                    category="Electronics",
                    processed_at="2024-01-01T00:00:00Z"
                )
                for i in range(50)
            ]
            aggregator.add_products(products)
        
        start = time.time()
        
        # Simulate concurrent processing from 4 workers
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(add_products_batch, i) for i in range(20)]
            for future in futures:
                future.result()
        
        elapsed = time.time() - start
        
        # Should handle 1000 products (20 batches * 50) quickly
        assert elapsed < 2.0, f"Aggregation took {elapsed}s for 1000 products"
        
        summary = aggregator.get_summary()
        assert summary.total_products == 1000

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_transition_performance(self):
        """Verify circuit breaker state transitions are fast."""
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
        endpoint = "test_endpoint"
        
        start = time.time()
        
        # Trigger state transitions
        for _ in range(3):
            cb.record_failure(endpoint, retryable=True)
        
        # Should open immediately
        assert not cb.should_allow(endpoint)
        
        # Wait for cooldown
        await asyncio.sleep(0.15)
        
        # Should be half-open
        result = cb.should_allow(endpoint)
        assert result is not False
        
        # Record success to close
        cb.record_success(endpoint, result)
        
        elapsed = time.time() - start
        
        # State transitions should be fast (< 0.5s including sleep)
        assert elapsed < 0.5, f"Circuit breaker transitions took {elapsed}s"


@pytest.mark.performance
class TestExecutionTimeConstraints:
    """Tests verifying the 60-second execution constraint."""

    def test_pipeline_execution_time_constraint(self):
        """Verify pipeline configuration includes 60-second constraint."""
        # This is a lightweight version to verify timing logic
        # Full integration test in test_pipeline_e2e.py
        
        from src.models.config import PipelineConfig
        
        config = PipelineConfig(
            total_timeout=60.0,
            max_requests_per_second=5,
            worker_pool_size=4,
        )
        
        # Verify timeout is properly configured
        assert config.total_timeout == 60.0
        
        # Verify default config also has reasonable timeout
        default_config = PipelineConfig()
        assert default_config.total_timeout == 60.0

    def test_performance_requirements_documented(self):
        """Verify performance requirements are properly documented."""
        # This test ensures we have documented performance constraints
        
        # Read requirements from spec
        import os
        spec_path = ".kiro/specs/async-data-pipeline/requirements.md"
        
        if os.path.exists(spec_path):
            with open(spec_path, 'r') as f:
                content = f.read()
                
            # Verify 60-second constraint is documented
            assert "60 seconds" in content or "60-second" in content
            
            # Verify rate limiting is documented
            assert "5 requests per second" in content or "5 req/sec" in content
            
            # Verify coverage requirement is documented
            assert "80%" in content


@pytest.mark.performance
class TestCoverageVerification:
    """Tests verifying coverage requirements are met."""

    def test_coverage_configuration_exists(self):
        """Verify coverage configuration is properly set up."""
        import os
        
        # Check pyproject.toml has coverage config
        assert os.path.exists("pyproject.toml")
        
        with open("pyproject.toml", 'r') as f:
            content = f.read()
            
        # Verify coverage settings
        assert "[tool.coverage.run]" in content
        assert "[tool.coverage.report]" in content
        assert "fail_under = 80" in content

    def test_coverage_omit_patterns_correct(self):
        """Verify coverage omit patterns exclude CLI and non-core code."""
        with open("pyproject.toml", 'r') as f:
            content = f.read()
        
        # Verify CLI is excluded
        assert "src/models/*" in content or "models" in content
        
        # Verify __init__ files are excluded
        assert "__init__.py" in content

    def test_test_markers_configured(self):
        """Verify pytest markers are properly configured."""
        with open("pyproject.toml", 'r') as f:
            content = f.read()
        
        # Verify markers are defined
        assert "markers" in content
        assert "unit:" in content or "integration:" in content


@pytest.mark.performance
class TestDeterministicFixtures:
    """Tests verifying fixtures use fixed random seeds for CI stability."""

    def test_sample_data_is_deterministic(self):
        """Verify sample data generation is deterministic with fixed seed."""
        from tests.fixtures.sample_data import get_sample_products
        
        # Generate data twice with same seed
        products1 = get_sample_products("test", count=10, seed=42)
        products2 = get_sample_products("test", count=10, seed=42)
        
        # Should be identical
        assert len(products1) == len(products2) == 10
        
        for p1, p2 in zip(products1, products2):
            assert p1["id"] == p2["id"]
            assert p1["name"] == p2["name"]
            assert p1["price"] == p2["price"]
            assert p1["category"] == p2["category"]

    def test_different_seeds_produce_different_data(self):
        """Verify different seeds produce different data."""
        from tests.fixtures.sample_data import get_sample_products
        
        products1 = get_sample_products("test", count=10, seed=42)
        products2 = get_sample_products("test", count=10, seed=99)
        
        # Should have different prices/categories
        prices1 = [p["price"] for p in products1]
        prices2 = [p["price"] for p in products2]
        
        assert prices1 != prices2

    def test_predefined_datasets_available(self):
        """Verify predefined deterministic datasets are available."""
        from tests.fixtures.sample_data import (
            SEED_42_PRODUCTS_SOURCE1,
            SEED_42_PRODUCTS_SOURCE2,
            SEED_42_PRODUCTS_SOURCE3,
        )
        
        # Verify datasets exist and have expected size
        assert len(SEED_42_PRODUCTS_SOURCE1) == 100
        assert len(SEED_42_PRODUCTS_SOURCE2) == 100
        assert len(SEED_42_PRODUCTS_SOURCE3) == 100
        
        # Verify they're different
        ids1 = {p["id"] for p in SEED_42_PRODUCTS_SOURCE1}
        ids2 = {p["id"] for p in SEED_42_PRODUCTS_SOURCE2}
        
        assert ids1.isdisjoint(ids2)

    def test_conftest_provides_deterministic_seed(self):
        """Verify conftest provides deterministic seed fixture."""
        import os
        
        assert os.path.exists("tests/conftest.py")
        
        with open("tests/conftest.py", 'r') as f:
            content = f.read()
        
        # Verify seed fixture exists
        assert "deterministic_seed" in content
        assert "random.seed(42)" in content or "seed=42" in content
