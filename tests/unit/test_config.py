"""Unit tests for configuration management."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.models.config import ConfigManager, EndpointConfig, PipelineConfig


def test_pipeline_config_defaults():
    """Test that PipelineConfig has correct default values."""
    config = PipelineConfig()
    
    # Rate limiting
    assert config.max_requests_per_second == 5
    assert config.rate_limit_tokens == 5
    assert config.rate_limit_refill_interval == 1.0
    
    # Retry policy
    assert config.max_retries == 3
    assert config.retry_base_delay == 0.5
    assert config.retry_max_delay == 4.0
    assert config.retryable_status_codes == [429, 502, 503, 504]
    
    # Timeouts
    assert config.connect_timeout == 3.0
    assert config.read_timeout == 8.0
    
    # Circuit breaker
    assert config.circuit_breaker_failure_threshold == 3
    assert config.circuit_breaker_cooldown == 15.0
    
    # Processing
    assert config.worker_pool_size == 4
    assert config.processing_batch_size == 50
    assert config.bounded_queue_size == 100
    
    # Pipeline
    assert config.total_timeout == 60.0
    
    # Output
    assert config.output_directory == "out"
    assert config.output_filename == "summary.json"


def test_endpoint_config_validation():
    """Test endpoint configuration validation."""
    # Valid endpoint
    endpoint = EndpointConfig(name="api1", url="http://localhost:8001/products")
    assert endpoint.name == "api1"
    assert endpoint.url == "http://localhost:8001/products"
    
    # HTTPS is also valid
    endpoint_https = EndpointConfig(name="api2", url="https://example.com/api")
    assert endpoint_https.url == "https://example.com/api"
    
    # Invalid URL should raise error
    with pytest.raises(ValueError, match="must start with http"):
        EndpointConfig(name="bad", url="ftp://invalid.com")


def test_pipeline_config_validators():
    """Test PipelineConfig field validators."""
    # Invalid rate limit
    with pytest.raises(ValueError, match="max_requests_per_second must be positive"):
        PipelineConfig(max_requests_per_second=0)
    
    with pytest.raises(ValueError, match="max_requests_per_second must be positive"):
        PipelineConfig(max_requests_per_second=-1)
    
    # Invalid worker pool size
    with pytest.raises(ValueError, match="worker_pool_size must be positive"):
        PipelineConfig(worker_pool_size=0)
    
    # Invalid timeout
    with pytest.raises(ValueError, match="total_timeout must be positive"):
        PipelineConfig(total_timeout=0.0)
    
    with pytest.raises(ValueError, match="total_timeout must be positive"):
        PipelineConfig(total_timeout=-10.0)


def test_output_path_property():
    """Test output_path property combines directory and filename."""
    config = PipelineConfig(
        output_directory="custom_out",
        output_filename="results.json"
    )
    
    assert config.output_path == Path("custom_out/results.json")


def test_config_from_env():
    """Test loading configuration from environment variables."""
    # Set environment variables
    env_vars = {
        "PIPELINE_TIMEOUT": "120.0",
        "PIPELINE_RATE_LIMIT_RPS": "10",
        "PIPELINE_WORKER_POOL_SIZE": "8",
        "PIPELINE_LOG_LEVEL": "DEBUG",
        "PIPELINE_CONNECT_TIMEOUT": "5.0",
        "PIPELINE_READ_TIMEOUT": "15.0",
        "PIPELINE_BATCH_SIZE": "100",
        "PIPELINE_QUEUE_SIZE": "200",
    }
    
    # Apply environment variables
    for key, value in env_vars.items():
        os.environ[key] = value
    
    try:
        config = PipelineConfig.from_env()
        
        assert config.total_timeout == 120.0
        assert config.max_requests_per_second == 10
        assert config.worker_pool_size == 8
        assert config.log_level == "DEBUG"
        assert config.connect_timeout == 5.0
        assert config.read_timeout == 15.0
        assert config.processing_batch_size == 100
        assert config.bounded_queue_size == 200
    finally:
        # Clean up environment variables
        for key in env_vars:
            os.environ.pop(key, None)


def test_config_manager_loads_yaml():
    """Test ConfigManager loads configuration from YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"
        
        # Create test YAML config
        test_config = {
            "max_requests_per_second": 10,
            "worker_pool_size": 8,
            "total_timeout": 120.0,
            "log_level": "DEBUG",
            "endpoints": [
                {"name": "test1", "url": "http://test1.com/api"},
                {"name": "test2", "url": "http://test2.com/api"},
            ]
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(test_config, f)
        
        # Load config
        manager = ConfigManager(config_file)
        config = manager.load_config()
        
        assert config.max_requests_per_second == 10
        assert config.worker_pool_size == 8
        assert config.total_timeout == 120.0
        assert config.log_level == "DEBUG"
        assert len(config.endpoints) == 2
        assert config.endpoints[0].name == "test1"
        assert config.endpoints[0].url == "http://test1.com/api"


def test_config_manager_env_overrides_yaml():
    """Test that environment variables override YAML configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"
        
        # Create YAML config
        yaml_config = {
            "max_requests_per_second": 5,
            "worker_pool_size": 4,
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(yaml_config, f)
        
        # Set environment variable
        os.environ["PIPELINE_RATE_LIMIT_RPS"] = "15"
        
        try:
            manager = ConfigManager(config_file)
            config = manager.load_config()
            
            # ENV should override YAML
            assert config.max_requests_per_second == 15
            # YAML value should be preserved
            assert config.worker_pool_size == 4
        finally:
            os.environ.pop("PIPELINE_RATE_LIMIT_RPS", None)


def test_config_manager_cli_overrides_all():
    """Test that CLI overrides have highest precedence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"
        
        # Create YAML config
        yaml_config = {
            "max_requests_per_second": 5,
            "worker_pool_size": 4,
            "total_timeout": 60.0,
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(yaml_config, f)
        
        # Set environment variable
        os.environ["PIPELINE_RATE_LIMIT_RPS"] = "10"
        os.environ["PIPELINE_WORKER_POOL_SIZE"] = "8"
        
        try:
            # CLI overrides
            cli_overrides = {
                "max_requests_per_second": 20,
                "total_timeout": 120.0,
            }
            
            manager = ConfigManager(config_file)
            config = manager.load_config(cli_overrides)
            
            # CLI should override everything
            assert config.max_requests_per_second == 20
            assert config.total_timeout == 120.0
            # ENV should override YAML
            assert config.worker_pool_size == 8
        finally:
            os.environ.pop("PIPELINE_RATE_LIMIT_RPS", None)
            os.environ.pop("PIPELINE_WORKER_POOL_SIZE", None)


def test_config_manager_missing_yaml_uses_defaults():
    """Test that missing YAML file uses default configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "nonexistent.yaml"
        
        manager = ConfigManager(config_file)
        config = manager.load_config()
        
        # Should use defaults
        assert config.max_requests_per_second == 5
        assert config.worker_pool_size == 4
        assert config.total_timeout == 60.0


def test_config_manager_property_caches_config():
    """Test that config property caches the loaded configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"
        
        yaml_config = {"max_requests_per_second": 10}
        with open(config_file, 'w') as f:
            yaml.dump(yaml_config, f)
        
        manager = ConfigManager(config_file)
        
        # First access loads config
        config1 = manager.config
        # Second access returns cached config
        config2 = manager.config
        
        assert config1 is config2
        assert config1.max_requests_per_second == 10


def test_cli_overrides_filters_none_values():
    """Test that None values in CLI overrides are filtered out."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"
        
        yaml_config = {"max_requests_per_second": 10}
        with open(config_file, 'w') as f:
            yaml.dump(yaml_config, f)
        
        # CLI overrides with None values
        cli_overrides = {
            "max_requests_per_second": None,  # Should be ignored
            "worker_pool_size": 8,  # Should be applied
        }
        
        manager = ConfigManager(config_file)
        config = manager.load_config(cli_overrides)
        
        # YAML value should be preserved (None was filtered)
        assert config.max_requests_per_second == 10
        # CLI value should be applied
        assert config.worker_pool_size == 8


def test_default_endpoints_configuration():
    """Test that default endpoints are configured correctly."""
    config = PipelineConfig()
    
    assert len(config.endpoints) == 3
    assert config.endpoints[0].name == "api1"
    assert config.endpoints[0].url == "http://localhost:8001/products"
    assert config.endpoints[1].name == "api2"
    assert config.endpoints[1].url == "http://localhost:8002/products"
    assert config.endpoints[2].name == "api3"
    assert config.endpoints[2].url == "http://localhost:8003/products"


def test_custom_endpoints_from_yaml():
    """Test loading custom endpoints from YAML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"
        
        yaml_config = {
            "endpoints": [
                {"name": "custom1", "url": "https://api1.example.com/v1/products"},
                {"name": "custom2", "url": "https://api2.example.com/v1/products"},
            ]
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(yaml_config, f)
        
        manager = ConfigManager(config_file)
        config = manager.load_config()
        
        assert len(config.endpoints) == 2
        assert config.endpoints[0].name == "custom1"
        assert config.endpoints[0].url == "https://api1.example.com/v1/products"
