"""Test fixtures with deterministic data for CI stability."""

import random
from typing import List, Dict, Any


def get_sample_products(source: str, count: int = 20, seed: int = 42) -> List[Dict[str, Any]]:
    """
    Generate deterministic sample product data for testing.
    
    Args:
        source: Source name for the products
        count: Number of products to generate
        seed: Random seed for deterministic results
        
    Returns:
        List of product dictionaries
    """
    rng = random.Random(seed)
    
    categories = ["Electronics", "Clothing", "Books", "Home", "Sports"]
    
    products = []
    for i in range(count):
        product = {
            "id": f"{source}_{i+1}",
            "name": f"Product {i+1} from {source}",
            "price": round(rng.uniform(10.0, 500.0), 2),
            "category": rng.choice(categories),
        }
        products.append(product)
    
    return products


def get_sample_products_variant_schema(
    source: str, count: int = 20, seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Generate sample products with variant schema (different field names).
    
    Args:
        source: Source name for the products
        count: Number of products to generate
        seed: Random seed for deterministic results
        
    Returns:
        List of product dictionaries with variant schema
    """
    rng = random.Random(seed)
    
    categories = ["Tech", "Fashion", "Literature", "Household", "Fitness"]
    
    products = []
    for i in range(count):
        product = {
            "product_id": f"{source}_{i+1}",
            "title": f"Item {i+1} from {source}",
            "cost": round(rng.uniform(10.0, 500.0), 2),
            "type": rng.choice(categories),
        }
        products.append(product)
    
    return products


def get_paginated_response(
    products: List[Dict[str, Any]], page: int, page_size: int = 20
) -> Dict[str, Any]:
    """
    Create a paginated response structure.
    
    Args:
        products: Full list of products
        page: Page number (1-indexed)
        page_size: Number of items per page
        
    Returns:
        Paginated response dictionary
    """
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    page_products = products[start_idx:end_idx]
    
    return {
        "page": page,
        "page_size": page_size,
        "total": len(products),
        "products": page_products,
    }


def get_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """
    Create an error response structure.
    
    Args:
        status_code: HTTP status code
        message: Error message
        
    Returns:
        Error response dictionary
    """
    return {
        "error": {
            "code": status_code,
            "message": message,
        }
    }


# Pre-generated deterministic datasets for common test scenarios
SEED_42_PRODUCTS_SOURCE1 = get_sample_products("source1", 100, seed=42)
SEED_42_PRODUCTS_SOURCE2 = get_sample_products("source2", 100, seed=43)
SEED_42_PRODUCTS_SOURCE3 = get_sample_products("source3", 100, seed=44)

# Variant schema products
SEED_42_VARIANT_SOURCE1 = get_sample_products_variant_schema("source1", 100, seed=42)
SEED_42_VARIANT_SOURCE2 = get_sample_products_variant_schema("source2", 100, seed=43)
SEED_42_VARIANT_SOURCE3 = get_sample_products_variant_schema("source3", 100, seed=44)
