"""Data normalizer for converting heterogeneous product data to unified schema.

This module provides flexible, defensive parsing for product data from various APIs
with different schemas, data types, and structures.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union


from src.models.data_models import Product


def _extract_id(raw_product: Dict) -> str:
    """
    Extract product ID from various field names and types.
    
    Tries common field names: id, product_id, item_id, userId, sku
    Handles both string and numeric IDs.
    
    Args:
        raw_product: Raw product data
        
    Returns:
        String representation of product ID, or "unknown" if not found
    """
    id_fields = ["id", "product_id", "item_id", "userId", "sku"]
    
    for field in id_fields:
        value = raw_product.get(field)
        if value is not None:
            return str(value)
    
    return "unknown"


def _extract_title(raw_product: Dict) -> str:
    """
    Extract product title from various field names.
    
    Tries common field names: title, name, product_name, description
    Falls back to "Unknown Product" if not found.
    
    Args:
        raw_product: Raw product data
        
    Returns:
        Product title string
    """
    title_fields = ["title", "name", "product_name", "productName"]
    
    for field in title_fields:
        value = raw_product.get(field)
        if value and isinstance(value, str) and value.strip():
            return value.strip()
    
    # Fallback to truncated description if available
    description = raw_product.get("description") or raw_product.get("body")
    if description and isinstance(description, str):
        return description[:100].strip() + ("..." if len(description) > 100 else "")
    
    return "Unknown Product"


def _extract_price(raw_product: Dict) -> Optional[float]:
    """
    Extract and normalize price from various field names and types.
    
    Tries common field names: price, cost, amount, value
    Handles string prices (e.g., "$10.99", "10,99")
    Validates price is positive.
    
    Args:
        raw_product: Raw product data
        
    Returns:
        Float price or None if not found/invalid
    """
    price_fields = ["price", "cost", "amount", "value"]
    
    for field in price_fields:
        value = raw_product.get(field)
        if value is None:
            continue
        
        # Handle numeric types
        if isinstance(value, (int, float)):
            price = float(value)
            # Validate positive price
            if price >= 0:
                return round(price, 2)
            continue
        
        # Handle string prices
        if isinstance(value, str):
            try:
                # Remove common currency symbols and whitespace
                cleaned = value.strip().replace("$", "").replace("€", "").replace("£", "")
                # Handle comma as decimal separator (European format)
                if "," in cleaned and "." not in cleaned:
                    cleaned = cleaned.replace(",", ".")
                # Remove thousand separators
                cleaned = cleaned.replace(",", "")
                
                price = float(cleaned)
                if price >= 0:
                    return round(price, 2)
            except (ValueError, AttributeError):
                continue
    
    return None


def _extract_category(raw_product: Dict) -> str:
    """
    Extract category from various field names and structures.
    
    Handles:
    - Simple string categories: "electronics"
    - Nested category objects: {"name": "Electronics", "id": 1}
    - Category arrays: ["electronics", "gadgets"]
    - Type fields: "type": "clothing"
    
    Args:
        raw_product: Raw product data
        
    Returns:
        Category string, or "uncategorized" if not found
    """
    category_fields = ["category", "type", "categories", "genre", "department"]
    
    for field in category_fields:
        value = raw_product.get(field)
        if value is None:
            continue
        
        # Handle string category
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
        
        # Handle nested category object (e.g., {"name": "Electronics", "id": 1})
        if isinstance(value, dict):
            # Try common nested field names
            for nested_field in ["name", "title", "label", "slug"]:
                nested_value = value.get(nested_field)
                if nested_value and isinstance(nested_value, str) and nested_value.strip():
                    return nested_value.strip().lower()
        
        # Handle category array (take first element)
        if isinstance(value, list) and len(value) > 0:
            first = value[0]
            if isinstance(first, str) and first.strip():
                return first.strip().lower()
            if isinstance(first, dict):
                # Nested object in array
                for nested_field in ["name", "title", "label"]:
                    nested_value = first.get(nested_field)
                    if nested_value and isinstance(nested_value, str) and nested_value.strip():
                        return nested_value.strip().lower()
    
    return "uncategorized"


def normalize_product(raw_product: Dict, source: str) -> Product:
    """
    Normalize single product to unified schema with flexible, defensive parsing.
    
    This normalizer handles real-world API complexity:
    - Different field names (id vs product_id vs item_id)
    - Different data types (string prices, numeric prices)
    - Nested structures (category objects, arrays)
    - Missing fields (graceful defaults)
    - Invalid data (type coercion, validation)
    
    Field Extraction Strategy:
    - ID: Tries id, product_id, item_id, userId, sku
    - Title: Tries title, name, product_name, falls back to description
    - Price: Tries price, cost, amount; handles strings and validation
    - Category: Tries category, type; handles nested objects and arrays
    
    Args:
        raw_product: Raw product data from API (any structure)
        source: Source endpoint name for tracking
        
    Returns:
        Normalized Product with unified schema
        
    Examples:
        >>> # Simple flat structure
        >>> normalize_product({"id": 1, "name": "Widget", "price": 9.99}, "api1")
        Product(id="api1:1", title="Widget", price=9.99, ...)
        
        >>> # Nested category
        >>> normalize_product({
        ...     "product_id": "ABC123",
        ...     "title": "Gadget",
        ...     "cost": "19.99",
        ...     "category": {"name": "Electronics", "id": 5}
        ... }, "api2")
        Product(id="api2:ABC123", title="Gadget", price=19.99, category="electronics", ...)
        
        >>> # Missing fields
        >>> normalize_product({"id": 1}, "api3")
        Product(id="api3:1", title="Unknown Product", price=None, category="uncategorized", ...)
    """
    product_id = _extract_id(raw_product)
    title = _extract_title(raw_product)
    price = _extract_price(raw_product)
    category = _extract_category(raw_product)
    
    return Product(
        id=f"{source}:{product_id}",
        title=title,
        source=source,
        price=price,
        category=category,
        processed_at=datetime.now(timezone.utc).isoformat()
    )


def normalize_batch(
    raw_products: List[Dict],
    source: str,
    seen_ids: Set[str] = None
) -> List[Product]:
    """
    Normalize batch of products with deduplication.
    
    Args:
        raw_products: List of raw product data
        source: Source endpoint name
        seen_ids: Set of already seen product IDs for deduplication
        
    Returns:
        List of normalized Products (deduplicated if seen_ids provided)
    """
    products = []
    
    for raw in raw_products:
        product = normalize_product(raw, source)
        
        # Deduplicate if seen_ids provided
        if seen_ids is not None:
            if product.id in seen_ids:
                continue  # Skip duplicate
            seen_ids.add(product.id)
        
        products.append(product)
    
    return products
