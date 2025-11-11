"""Unit tests for JSON output formatter."""

import json
import tempfile
from pathlib import Path

import pytest

from src.models.data_models import (
    ErrorAction,
    ErrorRecord,
    PipelineResult,
    Product,
    SourceSummary,
    Summary,
)
from src.pipeline.output import JSONOutputFormatter


@pytest.fixture
def sample_products():
    """Sample products for testing."""
    return [
        Product(
            id="api1:prod1",
            title="Product 1",
            source="api1",
            price=29.99,
            category="electronics",
            processed_at="2024-01-01T12:00:00Z"
        ),
        Product(
            id="api2:prod2",
            title="Product 2",
            source="api2",
            price=49.99,
            category="books",
            processed_at="2024-01-01T12:00:01Z"
        ),
        Product(
            id="api1:prod3",
            title="Product 3",
            source="api1",
            price=None,  # Missing price
            category="clothing",
            processed_at="2024-01-01T12:00:02Z"
        )
    ]


@pytest.fixture
def sample_errors():
    """Sample errors for testing."""
    return [
        ErrorRecord(
            source="api3",
            page=1,
            code=503,
            error="Service unavailable",
            timestamp="2024-01-01T12:00:00Z",
            action=ErrorAction.RETRY
        ),
        ErrorRecord(
            source="api3",
            page=2,
            code=None,
            error="Connection timeout",
            timestamp="2024-01-01T12:00:05Z",
            action=ErrorAction.CB_OPEN
        )
    ]


@pytest.fixture
def sample_result(sample_products, sample_errors):
    """Complete pipeline result for testing."""
    return PipelineResult(
        summary=Summary(
            total_products=3,
            processing_time_seconds=12.3456,
            success_rate=0.6
        ),
        sources=[
            SourceSummary(
                name="api1",
                items_fetched=2,
                errors=0,
                avg_price=29.99
            ),
            SourceSummary(
                name="api2",
                items_fetched=1,
                errors=0,
                avg_price=49.99
            ),
            SourceSummary(
                name="api3",
                items_fetched=0,
                errors=2,
                avg_price=None
            )
        ],
        products=sample_products,
        errors=sample_errors
    )


def test_format_creates_correct_structure(sample_result):
    """Test that format() creates the correct JSON structure."""
    formatter = JSONOutputFormatter()
    output = formatter.format(sample_result)
    
    # Verify top-level keys
    assert set(output.keys()) == {"summary", "sources", "products", "errors"}
    
    # Verify summary structure
    assert "total_products" in output["summary"]
    assert "processing_time_seconds" in output["summary"]
    assert "success_rate" in output["summary"]
    assert "sources" in output["summary"]
    
    # Verify sources is a list
    assert isinstance(output["sources"], list)
    assert len(output["sources"]) == 3
    
    # Verify products is a list
    assert isinstance(output["products"], list)
    assert len(output["products"]) == 3
    
    # Verify errors is a list
    assert isinstance(output["errors"], list)
    assert len(output["errors"]) == 2


def test_format_summary_section(sample_result):
    """Test summary section formatting."""
    formatter = JSONOutputFormatter()
    output = formatter.format(sample_result)
    
    summary = output["summary"]
    assert summary["total_products"] == 3
    assert summary["processing_time_seconds"] == 12.35  # Rounded to 2 decimals
    assert summary["success_rate"] == 0.6
    assert summary["sources"] == ["api1", "api2", "api3"]


def test_format_sources_section(sample_result):
    """Test per-source statistics formatting."""
    formatter = JSONOutputFormatter()
    output = formatter.format(sample_result)
    
    sources = output["sources"]
    
    # Check api1
    api1 = sources[0]
    assert api1["name"] == "api1"
    assert api1["items_fetched"] == 2
    assert api1["errors"] == 0
    assert api1["avg_price"] == 29.99
    
    # Check api3 with null avg_price
    api3 = sources[2]
    assert api3["name"] == "api3"
    assert api3["items_fetched"] == 0
    assert api3["errors"] == 2
    assert api3["avg_price"] is None


def test_format_products_section(sample_result):
    """Test products array formatting."""
    formatter = JSONOutputFormatter()
    output = formatter.format(sample_result)
    
    products = output["products"]
    
    # Check first product
    prod1 = products[0]
    assert prod1["id"] == "api1:prod1"
    assert prod1["title"] == "Product 1"
    assert prod1["source"] == "api1"
    assert prod1["price"] == 29.99
    assert prod1["category"] == "electronics"
    assert prod1["processed_at"] == "2024-01-01T12:00:00Z"
    
    # Check product with null price
    prod3 = products[2]
    assert prod3["price"] is None


def test_format_errors_section(sample_result):
    """Test errors array formatting."""
    formatter = JSONOutputFormatter()
    output = formatter.format(sample_result)
    
    errors = output["errors"]
    
    # Check first error
    err1 = errors[0]
    assert err1["source"] == "api3"
    assert err1["page"] == 1
    assert err1["code"] == 503
    assert err1["error"] == "Service unavailable"
    assert err1["timestamp"] == "2024-01-01T12:00:00Z"
    assert err1["action"] == "retry"
    
    # Check error with null code
    err2 = errors[1]
    assert err2["code"] is None
    assert err2["action"] == "circuit_break"


def test_save_creates_file(sample_result):
    """Test that save() creates a JSON file."""
    formatter = JSONOutputFormatter()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.json"
        formatter.save(sample_result, str(output_path))
        
        # Verify file exists
        assert output_path.exists()
        
        # Verify content is valid JSON
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert "summary" in data
        assert "sources" in data
        assert "products" in data
        assert "errors" in data


def test_save_creates_parent_directories(sample_result):
    """Test that save() creates parent directories if needed."""
    formatter = JSONOutputFormatter()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "nested" / "dir" / "output.json"
        formatter.save(sample_result, str(output_path))
        
        # Verify file exists
        assert output_path.exists()


def test_save_uses_default_path(sample_result):
    """Test that save() uses default path when not specified."""
    formatter = JSONOutputFormatter()
    
    # Clean up any existing file
    default_path = Path("out/summary.json")
    if default_path.exists():
        default_path.unlink()
    
    try:
        formatter.save(sample_result)
        
        # Verify file exists at default location
        assert default_path.exists()
        
        # Verify content
        with open(default_path, 'r') as f:
            data = json.load(f)
        
        assert data["summary"]["total_products"] == 3
    finally:
        # Clean up
        if default_path.exists():
            default_path.unlink()


def test_output_is_json_serializable(sample_result):
    """Test that formatted output can be serialized to JSON."""
    formatter = JSONOutputFormatter()
    output = formatter.format(sample_result)
    
    # Should not raise exception
    json_str = json.dumps(output)
    
    # Should be able to parse back
    parsed = json.loads(json_str)
    assert parsed["summary"]["total_products"] == 3


def test_empty_result():
    """Test formatting of empty pipeline result."""
    empty_result = PipelineResult(
        summary=Summary(
            total_products=0,
            processing_time_seconds=0.0,
            success_rate=0.0
        ),
        sources=[],
        products=[],
        errors=[]
    )
    
    formatter = JSONOutputFormatter()
    output = formatter.format(empty_result)
    
    assert output["summary"]["total_products"] == 0
    assert output["sources"] == []
    assert output["products"] == []
    assert output["errors"] == []


def test_rounding_precision():
    """Test that numeric values are rounded appropriately."""
    result = PipelineResult(
        summary=Summary(
            total_products=1,
            processing_time_seconds=12.3456789,
            success_rate=0.123456789
        ),
        sources=[
            SourceSummary(
                name="api1",
                items_fetched=1,
                errors=0,
                avg_price=29.999999
            )
        ],
        products=[],
        errors=[]
    )
    
    formatter = JSONOutputFormatter()
    output = formatter.format(result)
    
    # Processing time rounded to 2 decimals
    assert output["summary"]["processing_time_seconds"] == 12.35
    
    # Success rate rounded to 4 decimals
    assert output["summary"]["success_rate"] == 0.1235
    
    # Avg price rounded to 2 decimals
    assert output["sources"][0]["avg_price"] == 30.0
