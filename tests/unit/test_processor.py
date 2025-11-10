"""Unit tests for data processor."""

import asyncio
import pytest

from src.processor import DataProcessor, normalize_product


class TestNormalizer:
    
    def test_normalize_product_basic(self):
        raw = {"id": 123, "name": "Test Product", "price": 29.99, "category": "electronics"}
        product = normalize_product(raw, "server-a")
        
        assert product.id == "server-a:123"
        assert product.title == "Test Product"
        assert product.source == "server-a"
        assert product.price == 29.99
        assert product.category == "electronics"
        assert product.processed_at is not None
    
    def test_normalize_product_missing_fields(self):
        raw = {"id": 456}
        product = normalize_product(raw, "server-b")
        
        assert product.id == "server-b:456"
        assert product.title == "Unknown"
        assert product.price is None
        assert product.category == "uncategorized"
    
    def test_normalize_product_alternate_field_names(self):
        raw = {"product_id": 789, "title": "Alt Product", "price": 49.99}
        product = normalize_product(raw, "server-c")
        
        assert product.id == "server-c:789"
        assert product.title == "Alt Product"


class TestDataProcessor:
    
    @pytest.mark.asyncio
    async def test_consume_queue_processes_pages(self):
        processor = DataProcessor(worker_pool_size=2)
        queue = asyncio.Queue()
        
        # Add test data
        await queue.put({
            "endpoint": "server-a",
            "data": {
                "products": [
                    {"id": 1, "name": "Product 1", "price": 10.0, "category": "test"},
                    {"id": 2, "name": "Product 2", "price": 20.0, "category": "test"}
                ]
            }
        })
        await queue.put(None)  # Sentinel
        
        stats = await processor.consume_queue(queue, sentinel=None)
        
        assert stats.products_processed == 2
        assert stats.batches_processed == 1
        assert len(processor.get_products()) == 2
    
    @pytest.mark.asyncio
    async def test_consume_queue_multiple_batches(self):
        processor = DataProcessor()
        queue = asyncio.Queue()
        
        # Add multiple pages
        for i in range(3):
            await queue.put({
                "endpoint": f"server-{i}",
                "data": {"products": [{"id": j, "name": f"P{j}", "price": 10.0} for j in range(10)]}
            })
        await queue.put(None)
        
        stats = await processor.consume_queue(queue, sentinel=None)
        
        assert stats.products_processed == 30
        assert stats.batches_processed == 3
    
    def test_calculate_metrics_avg_price(self):
        processor = DataProcessor()
        processor.products = [
            normalize_product({"id": 1, "name": "P1", "price": 10.0, "category": "a"}, "server-a"),
            normalize_product({"id": 2, "name": "P2", "price": 20.0, "category": "a"}, "server-a"),
            normalize_product({"id": 3, "name": "P3", "price": 30.0, "category": "b"}, "server-b"),
        ]
        
        metrics = processor.calculate_metrics()
        
        assert metrics["sources"]["server-a"] == 15.0  # (10 + 20) / 2
        assert metrics["sources"]["server-b"] == 30.0
    
    def test_calculate_metrics_category_counts(self):
        processor = DataProcessor()
        processor.products = [
            normalize_product({"id": 1, "category": "electronics"}, "s1"),
            normalize_product({"id": 2, "category": "electronics"}, "s1"),
            normalize_product({"id": 3, "category": "books"}, "s2"),
        ]
        
        metrics = processor.calculate_metrics()
        
        assert metrics["categories"]["electronics"] == 2
        assert metrics["categories"]["books"] == 1
    
    def test_calculate_metrics_empty(self):
        processor = DataProcessor()
        metrics = processor.calculate_metrics()
        
        assert metrics["sources"] == {}
        assert metrics["categories"] == {}
