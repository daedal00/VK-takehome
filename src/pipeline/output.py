"""JSON output formatter for pipeline results.

This module provides structured JSON output formatting that matches
the exact schema specified in the requirements. It handles serialization
of pipeline results including summary statistics, per-source breakdowns,
product listings, and error records.
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.models.data_models import PipelineResult


class JSONOutputFormatter:
    """
    Formats pipeline results as JSON with exact schema compliance.
    
    The output format matches the requirements specification:
    - summary: aggregate statistics (total_products, processing_time, success_rate)
    - sources: per-endpoint statistics with avg_price calculations
    - products: unified product schema with ISO-8601 timestamps
    - errors: structured error records for debugging
    
    Example output structure:
    {
        "summary": {
            "total_products": 150,
            "processing_time_seconds": 12.34,
            "success_rate": 0.95,
            "sources": ["api1", "api2", "api3"]
        },
        "sources": [
            {
                "name": "api1",
                "items_fetched": 50,
                "errors": 2,
                "avg_price": 29.99
            }
        ],
        "products": [...],
        "errors": [...]
    }
    """
    
    def format(self, result: PipelineResult) -> Dict[str, Any]:
        """
        Format pipeline result as JSON-serializable dictionary.
        
        Args:
            result: Complete pipeline execution result
            
        Returns:
            Dictionary with summary, sources, products, and errors sections
        """
        return {
            "summary": self._format_summary(result),
            "sources": self._format_sources(result.sources),
            "products": self._format_products(result.products),
            "errors": self._format_errors(result.errors)
        }
    
    def _format_summary(self, result: PipelineResult) -> Dict[str, Any]:
        """Format summary section with aggregate statistics."""
        return {
            "total_products": result.summary.total_products,
            "processing_time_seconds": round(result.summary.processing_time_seconds, 2),
            "success_rate": round(result.summary.success_rate, 4),
            "sources": [source.name for source in result.sources]
        }
    
    def _format_sources(self, sources) -> list:
        """Format per-source statistics."""
        return [
            {
                "name": source.name,
                "items_fetched": source.items_fetched,
                "errors": source.errors,
                "avg_price": round(source.avg_price, 2) if source.avg_price is not None else None
            }
            for source in sources
        ]
    
    def _format_products(self, products) -> list:
        """Format products with unified schema."""
        return [
            {
                "id": product.id,
                "title": product.title,
                "source": product.source,
                "price": product.price,
                "category": product.category,
                "processed_at": product.processed_at
            }
            for product in products
        ]
    
    def _format_errors(self, errors) -> list:
        """Format error records for debugging."""
        return [
            {
                "source": error.source,
                "page": error.page,
                "code": error.code,
                "error": error.error,
                "timestamp": error.timestamp,
                "action": error.action.value
            }
            for error in errors
        ]
    
    def save(self, result: PipelineResult, path: str = "out/summary.json") -> None:
        """
        Save formatted result to JSON file.
        
        Creates parent directories if they don't exist. Uses 2-space
        indentation for readability.
        
        Args:
            result: Pipeline result to save
            path: Output file path (default: out/summary.json)
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        formatted_data = self.format(result)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(formatted_data, f, indent=2, ensure_ascii=False)
