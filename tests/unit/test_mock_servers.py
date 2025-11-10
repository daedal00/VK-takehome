"""Unit tests for mock servers."""

import pytest
from fastapi.testclient import TestClient

from src.mock_servers import create_mock_app, create_server_a


class TestMockServer:
    
    @pytest.fixture
    def app(self):
        return create_mock_app(
            name="test-server",
            schema={"category": "test"},
            random_seed=42,
            error_rate=0.0,  # No errors for basic tests
            pages=3,
            items_per_page=20
        )
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_get_products_first_page(self, client):
        response = client.get("/products?page=1")
        assert response.status_code == 200
        
        data = response.json()
        assert data["page"] == 1
        assert data["total_pages"] == 3
        assert len(data["products"]) == 20
    
    def test_get_products_pagination(self, client):
        response = client.get("/products?page=2")
        assert response.status_code == 200
        
        data = response.json()
        assert data["page"] == 2
        assert len(data["products"]) == 20
    
    def test_get_products_beyond_last_page(self, client):
        response = client.get("/products?page=4")
        assert response.status_code == 204  # No content
    
    def test_get_products_invalid_page(self, client):
        response = client.get("/products?page=0")
        assert response.status_code == 400
    
    def test_products_have_schema_fields(self, client):
        response = client.get("/products?page=1")
        data = response.json()
        
        product = data["products"][0]
        assert "category" in product
        assert "id" in product
        assert "name" in product
        assert "price" in product
    

    def test_server_a_creation(self):
        app = create_server_a()
        client = TestClient(app)
        
        response = client.get("/health")
        assert response.status_code == 200
        assert "server-a" in response.json()["server"]
