"""FastAPI mock server for testing async data pipeline."""

import os
import random
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel


class ProductResponse(BaseModel):
    """Product response model."""
    products: List[Dict]
    page: int
    total_pages: int
    
    class Config:
        # Allow arbitrary types for flexible product schemas
        arbitrary_types_allowed = True


def create_mock_app(
    name: str,
    schema: Dict,
    random_seed: Optional[int] = None,
    error_rate: float = 0.1,
    extra_latency_ms: int = 0,
    pages: int = 5,
    items_per_page: int = 20,
    use_variant_schema: bool = False,
    use_alt_schema: bool = False
) -> FastAPI:
    """
    Create a FastAPI mock server with configurable behavior.
    
    Args:
        name: Server name (e.g., "server-a")
        schema: Product schema template
        random_seed: Seed for deterministic behavior
        error_rate: Probability of returning 5xx errors (0.0-1.0)
        extra_latency_ms: Additional latency in milliseconds
        pages: Total number of pages to serve
        items_per_page: Items per page
        use_variant_schema: Use variant field names (product_id, title, cost, type)
        use_alt_schema: Use alternative field names (item_id, product_name)
        
    Returns:
        FastAPI application
    """
    app = FastAPI(title=f"Mock API - {name}")
    
    # Set random seed for deterministic behavior
    if random_seed is not None:
        random.seed(random_seed)
    
    @app.get("/products")
    async def get_products(page: int = 1):
        """Get paginated products."""
        
        # Add extra latency if configured
        if extra_latency_ms > 0:
            time.sleep(extra_latency_ms / 1000.0)
        
        # Simulate random errors
        if random.random() < error_rate:
            error_code = random.choice([500, 502, 503])
            raise HTTPException(status_code=error_code, detail="Simulated error")
        
        # Check if page is out of range
        if page > pages:
            return Response(status_code=204)  # No content
        
        if page < 1:
            raise HTTPException(status_code=400, detail="Invalid page number")
        
        # Generate products for this page
        products = []
        for i in range(items_per_page):
            product_id = (page - 1) * items_per_page + i + 1
            
            # Use different field names based on schema variant
            if use_variant_schema:
                # Server B: product_id, title, cost (string), nested category
                price_value = round(random.uniform(10.0, 500.0), 2)
                product = {
                    **schema,
                    "product_id": product_id,
                    "title": f"Product {product_id}",
                    "cost": f"${price_value}"  # String price to test parsing
                }
            elif use_alt_schema:
                # Server C: item_id, product_name, price, category
                product = {
                    **schema,
                    "item_id": product_id,
                    "product_name": f"{schema.get('category', 'Product')} {product_id}",
                    "price": round(random.uniform(10.0, 500.0), 2)
                }
            else:
                # Server A: id, name, price, category (standard)
                product = {
                    **schema,
                    "id": product_id,
                    "name": f"{schema.get('category', 'Product')} {product_id}",
                    "price": round(random.uniform(10.0, 500.0), 2)
                }
            
            products.append(product)
        
        return {
            "products": products,
            "page": page,
            "total_pages": pages
        }
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "server": name}
    
    return app


# Create 3 different mock servers with different schemas
def create_server_a() -> FastAPI:
    """
    Server A: Electronics with standard schema.
    
    Schema: id, name, price, category, brand
    """
    return create_mock_app(
        name="server-a",
        schema={"category": "electronics", "brand": "TechCorp"},
        random_seed=int(os.getenv("RANDOM_SEED", 42)),
        error_rate=float(os.getenv("ERROR_RATE", 0.1)),
        extra_latency_ms=int(os.getenv("EXTRA_LATENCY_MS", 0)),
        pages=int(os.getenv("PAGES", 7)),
        items_per_page=20
    )


def create_server_b() -> FastAPI:
    """
    Server B: Clothing with variant schema (nested category).
    
    Schema: product_id, title, cost (string), category (nested object), material
    Simulates APIs like Escuelajs with nested category structures.
    """
    return create_mock_app(
        name="server-b",
        schema={"category": {"name": "Clothing", "id": 2, "slug": "clothing"}, "material": "cotton"},
        random_seed=int(os.getenv("RANDOM_SEED", 43)),
        error_rate=float(os.getenv("ERROR_RATE", 0.1)),
        extra_latency_ms=int(os.getenv("EXTRA_LATENCY_MS", 0)),
        pages=int(os.getenv("PAGES", 7)),
        items_per_page=20,
        use_variant_schema=True
    )


def create_server_c() -> FastAPI:
    """
    Server C: Books with another variant schema.
    
    Schema: item_id (instead of id), product_name (instead of name), price, category, author
    """
    return create_mock_app(
        name="server-c",
        schema={"category": "books", "author": "Unknown"},
        random_seed=int(os.getenv("RANDOM_SEED", 44)),
        error_rate=float(os.getenv("ERROR_RATE", 0.1)),
        extra_latency_ms=int(os.getenv("EXTRA_LATENCY_MS", 0)),
        pages=int(os.getenv("PAGES", 7)),
        items_per_page=20,
        use_alt_schema=True
    )


def create_app() -> FastAPI:
    """
    Factory function for uvicorn --factory.
    
    Reads SERVER_NAME from environment to determine which server to create.
    Defaults to server-a if not specified.
    """
    server_name = os.getenv("SERVER_NAME", "api1")
    
    server_map = {
        "api1": create_server_a,
        "api2": create_server_b,
        "api3": create_server_c,
        "server-a": create_server_a,
        "server-b": create_server_b,
        "server-c": create_server_c,
    }
    
    factory = server_map.get(server_name, create_server_a)
    return factory()


# Default app for running directly
app = create_app()
