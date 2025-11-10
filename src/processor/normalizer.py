"""Data normalizer for converting heterogeneous product data to unified schema."""

from datetime import datetime, timezone
from typing import Dict, List

from src.models.data_models import Product


def normalize_product(raw_product: Dict, source: str) -> Product:
    """
    Normalize single product to unified schema.
    
    Args:
        raw_product: Raw product data from API
        source: Source endpoint name
        
    Returns:
        Normalized Product
    """
    product_id = raw_product.get("id", raw_product.get("product_id", "unknown"))
    
    return Product(
        id=f"{source}:{product_id}",
        title=raw_product.get("name", raw_product.get("title", "Unknown")),
        source=source,
        price=raw_product.get("price"),
        category=raw_product.get("category", "uncategorized"),
        processed_at=datetime.now(timezone.utc).isoformat()
    )


def normalize_batch(raw_products: List[Dict], source: str) -> List[Product]:
    """
    Normalize batch of products.
    
    Args:
        raw_products: List of raw product data
        source: Source endpoint name
        
    Returns:
        List of normalized Products
    """
    return [normalize_product(p, source) for p in raw_products]
