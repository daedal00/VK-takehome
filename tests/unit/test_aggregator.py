"""Unit tests for ThreadSafeAggregator."""

import threading
import pytest

from src.models.data_models import ErrorRecord, Product
from src.processor import ThreadSafeAggregator


class TestThreadSafeAggregator:
    
    def test_initialization(self):
        agg = ThreadSafeAggregator()
        assert len(agg.get_products()) == 0
        assert len(agg.get_errors()) == 0
    
    def test_add_products(self):
        agg = ThreadSafeAggregator()
        products = [
            Product(id="s1:1", title="P1", source="s1", price=10.0, category="a", processed_at="2024-01-01"),
            Product(id="s1:2", title="P2", source="s1", price=20.0, category="a", processed_at="2024-01-01"),
        ]
        
        agg.add_products(products)
        
        assert len(agg.get_products()) == 2
    
    def test_add_products_deduplication(self):
        agg = ThreadSafeAggregator()
        products = [
            Product(id="s1:1", title="P1", source="s1", price=10.0, category="a", processed_at="2024-01-01"),
            Product(id="s1:1", title="P1 Dup", source="s1", price=10.0, category="a", processed_at="2024-01-01"),
        ]
        
        agg.add_products(products)
        
        # Should only have 1 product (duplicate removed)
        assert len(agg.get_products()) == 1
    
    def test_add_error(self):
        agg = ThreadSafeAggregator()
        error = ErrorRecord(source="s1", page=1, code=500, error="Server error", timestamp="2024-01-01", action="retry")
        
        agg.add_error(error)
        
        assert len(agg.get_errors()) == 1
    
    def test_get_summary(self):
        agg = ThreadSafeAggregator()
        agg.start_timer()
        
        products = [
            Product(id="s1:1", title="P1", source="s1", price=10.0, category="a", processed_at="2024-01-01"),
        ]
        agg.add_products(products)
        
        agg.stop_timer()
        summary = agg.get_summary()
        
        assert summary.total_products == 1
        assert summary.processing_time_seconds > 0
        assert summary.success_rate == 1.0  # 1 product, 0 errors
    
    def test_get_summary_with_errors(self):
        agg = ThreadSafeAggregator()
        
        products = [Product(id="s1:1", title="P1", source="s1", price=10.0, category="a", processed_at="2024-01-01")]
        agg.add_products(products)
        
        error = ErrorRecord(source="s1", page=1, code=500, error="Error", timestamp="2024-01-01", action="retry")
        agg.add_error(error)
        
        summary = agg.get_summary()
        
        assert summary.total_products == 1
        assert summary.success_rate == 0.5  # 1 success, 1 error
    
    def test_get_source_summaries(self):
        agg = ThreadSafeAggregator()
        
        products = [
            Product(id="s1:1", title="P1", source="server1", price=10.0, category="a", processed_at="2024-01-01"),
            Product(id="s1:2", title="P2", source="server1", price=20.0, category="a", processed_at="2024-01-01"),
            Product(id="s2:1", title="P3", source="server2", price=30.0, category="b", processed_at="2024-01-01"),
        ]
        agg.add_products(products)
        
        error = ErrorRecord(source="server1", page=1, code=500, error="Error", timestamp="2024-01-01", action="retry")
        agg.add_error(error)
        
        summaries = agg.get_source_summaries()
        
        assert len(summaries) == 2
        
        # Find server1 summary
        s1 = next(s for s in summaries if s.name == "server1")
        assert s1.items_fetched == 2
        assert s1.errors == 1
        assert s1.avg_price == 15.0  # (10 + 20) / 2
        
        # Find server2 summary
        s2 = next(s for s in summaries if s.name == "server2")
        assert s2.items_fetched == 1
        assert s2.errors == 0
        assert s2.avg_price == 30.0
    
    def test_thread_safety(self):
        """Test concurrent access from multiple threads."""
        agg = ThreadSafeAggregator()
        
        def add_products_thread(start_id):
            products = [
                Product(id=f"s1:{i}", title=f"P{i}", source="s1", price=10.0, category="a", processed_at="2024-01-01")
                for i in range(start_id, start_id + 10)
            ]
            agg.add_products(products)
        
        # Create 10 threads, each adding 10 products
        threads = [threading.Thread(target=add_products_thread, args=(i * 10,)) for i in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have 100 products total
        assert len(agg.get_products()) == 100
