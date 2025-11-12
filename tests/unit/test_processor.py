"""Unit tests for data processor and normalizer."""

import asyncio
import pytest

from src.processor import DataProcessor, normalize_product
from src.processor.normalizer import (
    normalize_batch,
    _extract_id,
    _extract_title,
    _extract_price,
    _extract_category,
)


class TestNormalizerExtraction:
    """Test individual extraction functions for defensive parsing."""
    
    def test_extract_id_standard(self):
        """Test ID extraction with standard field name."""
        assert _extract_id({"id": 123}) == "123"
        assert _extract_id({"id": "ABC123"}) == "ABC123"
    
    def test_extract_id_variants(self):
        """Test ID extraction with variant field names."""
        assert _extract_id({"product_id": 456}) == "456"
        assert _extract_id({"item_id": "XYZ"}) == "XYZ"
        assert _extract_id({"userId": 789}) == "789"
        assert _extract_id({"sku": "SKU-001"}) == "SKU-001"
    
    def test_extract_id_missing(self):
        """Test ID extraction with missing field."""
        assert _extract_id({}) == "unknown"
        assert _extract_id({"name": "Product"}) == "unknown"
    
    def test_extract_title_standard(self):
        """Test title extraction with standard field names."""
        assert _extract_title({"title": "Product Title"}) == "Product Title"
        assert _extract_title({"name": "Product Name"}) == "Product Name"
    
    def test_extract_title_variants(self):
        """Test title extraction with variant field names."""
        assert _extract_title({"product_name": "Variant"}) == "Variant"
        assert _extract_title({"productName": "CamelCase"}) == "CamelCase"
    
    def test_extract_title_from_description(self):
        """Test title fallback to description."""
        long_desc = "A" * 150
        result = _extract_title({"description": long_desc})
        assert len(result) == 103  # 100 chars + "..."
        assert result.endswith("...")
    
    def test_extract_title_missing(self):
        """Test title extraction with missing field."""
        assert _extract_title({}) == "Unknown Product"
        assert _extract_title({"id": 123}) == "Unknown Product"
    
    def test_extract_price_numeric(self):
        """Test price extraction with numeric values."""
        assert _extract_price({"price": 19.99}) == 19.99
        assert _extract_price({"price": 20}) == 20.0
        assert _extract_price({"cost": 15.50}) == 15.50
    
    def test_extract_price_string(self):
        """Test price extraction with string values."""
        assert _extract_price({"price": "19.99"}) == 19.99
        assert _extract_price({"price": "$29.99"}) == 29.99
        assert _extract_price({"price": "€15.50"}) == 15.50
        assert _extract_price({"price": "£10.00"}) == 10.0
    
    def test_extract_price_european_format(self):
        """Test price extraction with European decimal format."""
        assert _extract_price({"price": "19,99"}) == 19.99
        # Note: Complex thousand separators (1.234,56) not supported - edge case
    
    def test_extract_price_invalid(self):
        """Test price extraction with invalid values."""
        assert _extract_price({"price": "invalid"}) is None
        assert _extract_price({"price": ""}) is None
        assert _extract_price({"price": -10}) is None  # Negative price
    
    def test_extract_price_missing(self):
        """Test price extraction with missing field."""
        assert _extract_price({}) is None
        assert _extract_price({"id": 123}) is None
    
    def test_extract_category_string(self):
        """Test category extraction with string value."""
        assert _extract_category({"category": "Electronics"}) == "electronics"
        assert _extract_category({"type": "Clothing"}) == "clothing"
    
    def test_extract_category_nested_object(self):
        """Test category extraction with nested object."""
        nested = {"category": {"name": "Electronics", "id": 1}}
        assert _extract_category(nested) == "electronics"
        
        nested_slug = {"category": {"slug": "home-goods", "id": 2}}
        assert _extract_category(nested_slug) == "home-goods"
    
    def test_extract_category_array(self):
        """Test category extraction with array."""
        assert _extract_category({"categories": ["electronics", "gadgets"]}) == "electronics"
        
        nested_array = {"categories": [{"name": "Books"}, {"name": "Fiction"}]}
        assert _extract_category(nested_array) == "books"
    
    def test_extract_category_missing(self):
        """Test category extraction with missing field."""
        assert _extract_category({}) == "uncategorized"
        assert _extract_category({"id": 123}) == "uncategorized"


class TestNormalizer:
    """Test product normalization with various schemas."""
    
    def test_normalize_product_basic(self):
        """Test basic product normalization."""
        raw = {"id": 123, "name": "Test Product", "price": 29.99, "category": "electronics"}
        product = normalize_product(raw, "server-a")
        
        assert product.id == "server-a:123"
        assert product.title == "Test Product"
        assert product.source == "server-a"
        assert product.price == 29.99
        assert product.category == "electronics"
        assert product.processed_at is not None
    
    def test_normalize_product_missing_fields(self):
        """Test normalization with missing fields."""
        raw = {"id": 456}
        product = normalize_product(raw, "server-b")
        
        assert product.id == "server-b:456"
        assert product.title == "Unknown Product"
        assert product.price is None
        assert product.category == "uncategorized"
    
    def test_normalize_product_alternate_field_names(self):
        """Test normalization with alternate field names."""
        raw = {"product_id": 789, "title": "Alt Product", "price": 49.99}
        product = normalize_product(raw, "server-c")
        
        assert product.id == "server-c:789"
        assert product.title == "Alt Product"
    
    def test_normalize_product_nested_category(self):
        """Test normalization with nested category object."""
        raw = {
            "id": 789,
            "title": "Nested Category Product",
            "price": 49.99,
            "category": {
                "id": 5,
                "name": "Home & Garden",
                "slug": "home-garden"
            }
        }
        
        product = normalize_product(raw, "test-source")
        
        assert product.id == "test-source:789"
        assert product.category == "home & garden"
    
    def test_normalize_product_string_price(self):
        """Test normalization with string price."""
        raw = {
            "id": 101,
            "name": "String Price Product",
            "price": "$39.99",
            "category": "books"
        }
        
        product = normalize_product(raw, "test-source")
        
        assert product.price == 39.99
    
    def test_normalize_product_real_world_dummyjson(self):
        """Test normalization with DummyJSON-like structure."""
        raw = {
            "id": 1,
            "title": "Essence Mascara",
            "price": 9.99,
            "category": "beauty",
            "brand": "Essence",
            "stock": 99,
            "rating": 2.56
        }
        
        product = normalize_product(raw, "dummyjson")
        
        assert product.id == "dummyjson:1"
        assert product.title == "Essence Mascara"
        assert product.price == 9.99
        assert product.category == "beauty"
    
    def test_normalize_product_real_world_escuelajs(self):
        """Test normalization with Escuelajs-like structure."""
        raw = {
            "id": 1,
            "title": "Majestic Mountain T-Shirt",
            "price": 44,
            "slug": "majestic-mountain-tshirt",
            "category": {
                "id": 1,
                "name": "Clothes",
                "slug": "clothes"
            }
        }
        
        product = normalize_product(raw, "escuelajs")
        
        assert product.id == "escuelajs:1"
        assert product.title == "Majestic Mountain T-Shirt"
        assert product.price == 44.0
        assert product.category == "clothes"
    
    def test_normalize_product_real_world_jsonplaceholder(self):
        """Test normalization with JSONPlaceholder-like structure (posts as products)."""
        raw = {
            "userId": 1,
            "id": 1,
            "title": "sunt aut facere repellat",
            "body": "quia et suscipit suscipit recusandae"
        }
        
        product = normalize_product(raw, "jsonplaceholder")
        
        assert product.id == "jsonplaceholder:1"
        assert product.title == "sunt aut facere repellat"
        assert product.price is None  # No price field
        assert product.category == "uncategorized"
    
    def test_normalize_batch_with_deduplication(self):
        raw_products = [
            {"id": 1, "name": "Product 1"},
            {"id": 2, "name": "Product 2"},
            {"id": 1, "name": "Product 1 Duplicate"},  # Duplicate
        ]
        
        seen_ids = set()
        products = normalize_batch(raw_products, "server-a", seen_ids)
        
        # Should only have 2 products (duplicate removed)
        assert len(products) == 2
        assert products[0].id == "server-a:1"
        assert products[1].id == "server-a:2"
        assert len(seen_ids) == 2
    
    def test_normalize_batch_without_deduplication(self):
        raw_products = [
            {"id": 1, "name": "Product 1"},
            {"id": 1, "name": "Product 1 Duplicate"},
        ]
        
        # Without seen_ids, should keep duplicates
        products = normalize_batch(raw_products, "server-a")
        
        assert len(products) == 2


class TestDataProcessor:
    """Test data processor with worker pools."""
    
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
