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


def create_mock_app(
    name: str,
    schema: Dict,
    random_seed: Optional[int] = None,
    error_rate: float = 0.1,
    extra_latency_ms: int = 0,
    pages: int = 5,
    items_per_page: int = 20
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
        
    Returns:
        FastAPI application
    """
    app = FastAPI(title=f"Mock API - {name}")
    
    # Set random seed for deterministic behavior
    if random_seed is not None:
        random.seed(random_seed)
    
    @app.get("/products", response_model=ProductResponse)
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
            product = {
                **schema,
                "id": product_id,
                "name": f"{schema.get('category', 'Product')} {product_id}",
                "price": round(random.uniform(10.0, 500.0), 2)
            }
            products.append(product)
        
        return ProductResponse(
            products=products,
            page=page,
            total_pages=pages
        )
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "server": name}
    
    return app


# Create 3 different mock servers with different schemas
def create_server_a() -> FastAPI:
    """Server A: Electronics."""
    return create_mock_app(
        name="server-a",
        schema={"category": "electronics", "brand": "TechCorp"},
        random_seed=int(os.getenv("RANDOM_SEED", 42)),
        error_rate=float(os.getenv("ERROR_RATE", 0.1)),
        extra_latency_ms=int(os.getenv("EXTRA_LATENCY_MS", 0)),
        pages=int(os.getenv("PAGES", 5)),
        items_per_page=20
    )


def create_server_b() -> FastAPI:
    """Server B: Clothing."""
    return create_mock_app(
        name="server-b",
        schema={"category": "clothing", "material": "cotton"},
        random_seed=int(os.getenv("RANDOM_SEED", 43)),
        error_rate=float(os.getenv("ERROR_RATE", 0.1)),
        extra_latency_ms=int(os.getenv("EXTRA_LATENCY_MS", 0)),
        pages=int(os.getenv("PAGES", 5)),
        items_per_page=20
    )


def create_server_c() -> FastAPI:
    """Server C: Books."""
    return create_mock_app(
        name="server-c",
        schema={"category": "books", "author": "Unknown"},
        random_seed=int(os.getenv("RANDOM_SEED", 44)),
        error_rate=float(os.getenv("ERROR_RATE", 0.1)),
        extra_latency_ms=int(os.getenv("EXTRA_LATENCY_MS", 0)),
        pages=int(os.getenv("PAGES", 5)),
        items_per_page=20
    )


# Default app for running directly
app = create_server_a()
