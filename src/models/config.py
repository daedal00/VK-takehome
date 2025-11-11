"""Configuration management for the async data pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class EndpointConfig(BaseModel):
    """Configuration for a single API endpoint."""
    name: str = Field(description="Endpoint identifier")
    url: str = Field(description="Full URL to the endpoint")
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError(f"URL must start with http:// or https://, got: {v}")
        return v


class PipelineConfig(BaseModel):
    """Main pipeline configuration with precise parameters from requirements."""
    
    # Rate limiting configuration (Requirement 1.3, 2.1)
    max_requests_per_second: int = Field(default=5, description="Requests per second per endpoint")
    rate_limit_tokens: int = Field(default=5, description="Token bucket size")
    rate_limit_refill_interval: float = Field(default=1.0, description="Token refill interval in seconds")
    rate_limit_retry_sleep: float = Field(default=0.05, description="Sleep duration when tokens unavailable")
    
    # Retry configuration (Requirement 2.1, 2.3)
    max_retries: int = Field(default=3, description="Maximum retry attempts per request")
    retry_base_delay: float = Field(default=0.5, description="Base delay for exponential backoff")
    retry_max_delay: float = Field(default=4.0, description="Maximum retry delay")
    retry_jitter_max: float = Field(default=0.5, description="Maximum jitter for retry delay")
    retryable_status_codes: List[int] = Field(
        default=[429, 502, 503, 504], 
        description="HTTP status codes that trigger retries"
    )
    
    # Timeout configuration (Requirement 13.1)
    connect_timeout: float = Field(default=3.0, description="HTTP connect timeout in seconds")
    read_timeout: float = Field(default=8.0, description="HTTP read timeout in seconds")
    
    # Circuit breaker configuration (Requirement 2.2, 13.4)
    circuit_breaker_failure_threshold: int = Field(default=3, description="Failures before opening circuit")
    circuit_breaker_cooldown: float = Field(default=15.0, description="Cooldown period in seconds")
    
    # Processing configuration (Requirement 3.2, 3.5)
    worker_pool_size: int = Field(default=4, description="ThreadPoolExecutor worker count")
    processing_batch_size: int = Field(default=50, description="Maximum items per processing batch")
    bounded_queue_size: int = Field(default=100, description="Maximum queue size for memory management")
    
    # Pipeline constraints (Requirement 1.4, 4.1)
    total_timeout: float = Field(default=60.0, description="Maximum pipeline execution time")
    
    # Mock server configuration (Requirement 9.1, 9.2, 9.5)
    mock_server_ports: List[int] = Field(default=[8001, 8002, 8003], description="Mock server ports")
    mock_server_items_per_page: int = Field(default=20, description="Items per page in mock responses")
    mock_server_min_pages: int = Field(default=5, description="Minimum pages per endpoint")
    mock_server_error_rate: float = Field(default=0.1, description="Random error rate for mock servers")
    
    # Logging configuration (Requirement 4.2, 13.4)
    log_level: str = Field(default="INFO", description="Logging level")
    structured_logging: bool = Field(default=True, description="Enable structured logging")
    
    # Output configuration (Requirement 8.1, 8.4)
    output_directory: str = Field(default="out", description="Output directory for results")
    output_filename: str = Field(default="summary.json", description="Output JSON filename")
    
    # Endpoint configuration
    endpoints: List[EndpointConfig] = Field(
        default=[
            EndpointConfig(name="api1", url="http://localhost:8001/products"),
            EndpointConfig(name="api2", url="http://localhost:8002/products"),
            EndpointConfig(name="api3", url="http://localhost:8003/products"),
        ],
        description="API endpoints to fetch from"
    )
    
    @field_validator('max_requests_per_second')
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        """Validate rate limit is positive."""
        if v <= 0:
            raise ValueError(f"max_requests_per_second must be positive, got: {v}")
        return v
    
    @field_validator('worker_pool_size')
    @classmethod
    def validate_worker_pool(cls, v: int) -> int:
        """Validate worker pool size is positive."""
        if v <= 0:
            raise ValueError(f"worker_pool_size must be positive, got: {v}")
        return v
    
    @field_validator('total_timeout')
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Validate timeout is positive."""
        if v <= 0:
            raise ValueError(f"total_timeout must be positive, got: {v}")
        return v
    
    @property
    def output_path(self) -> Path:
        """Get full output file path."""
        return Path(self.output_directory) / self.output_filename
    
    # Environment variable overrides
    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Create configuration with environment variable overrides."""
        config = cls()
        
        # Map environment variables to config fields
        env_mappings = {
            "PIPELINE_TIMEOUT": "total_timeout",
            "PIPELINE_RATE_LIMIT_RPS": "max_requests_per_second",
            "PIPELINE_WORKER_POOL_SIZE": "worker_pool_size",
            "PIPELINE_LOG_LEVEL": "log_level",
            "PIPELINE_CONNECT_TIMEOUT": "connect_timeout",
            "PIPELINE_READ_TIMEOUT": "read_timeout",
            "PIPELINE_BATCH_SIZE": "processing_batch_size",
            "PIPELINE_QUEUE_SIZE": "bounded_queue_size",
        }
        
        for env_var, field_name in env_mappings.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                # Convert to appropriate type based on field type
                field_info = config.model_fields[field_name]
                if field_info.annotation == int:
                    setattr(config, field_name, int(value))
                elif field_info.annotation == float:
                    setattr(config, field_name, float(value))
                else:
                    setattr(config, field_name, value)
        
        return config


@dataclass
class MockServerConfig:
    """Configuration for individual mock servers."""
    port: int
    name: str
    product_schema: Dict
    error_rate: float = 0.1
    extra_latency_ms: int = 0
    pages: int = 5
    items_per_page: int = 20
    random_seed: Optional[int] = None


class ConfigManager:
    """Manages configuration loading with override precedence."""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or Path("config/config.yaml")
        self._config: Optional[PipelineConfig] = None
    
    def load_config(self, cli_overrides: Optional[Dict] = None) -> PipelineConfig:
        """
        Load configuration with override precedence: CLI > ENV > YAML.
        
        This implements the three-tier configuration system specified in
        requirements 4.3 and 7.4. Each tier can override values from lower
        tiers, with CLI flags having the highest precedence.
        
        Args:
            cli_overrides: Optional dictionary of CLI flag overrides
            
        Returns:
            Fully merged PipelineConfig instance
            
        Raises:
            ValueError: If configuration validation fails
        """
        # Start with defaults
        config_dict = {}
        
        # Load from YAML file if it exists
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    # Handle endpoints specially to convert dicts to EndpointConfig
                    if 'endpoints' in yaml_config:
                        yaml_config['endpoints'] = [
                            EndpointConfig(**ep) if isinstance(ep, dict) else ep
                            for ep in yaml_config['endpoints']
                        ]
                    config_dict.update(yaml_config)
        
        # Create base config from YAML + defaults
        base_config = PipelineConfig(**config_dict)
        
        # Apply environment variable overrides
        env_config = PipelineConfig.from_env()
        
        # Merge configurations (ENV overrides YAML)
        merged_dict = base_config.model_dump()
        env_dict = env_config.model_dump()
        
        # Only override with env values that differ from defaults
        default_dict = PipelineConfig().model_dump()
        for key, value in env_dict.items():
            if value != default_dict[key]:
                merged_dict[key] = value
        
        # Apply CLI overrides (highest precedence)
        if cli_overrides:
            # Filter out None values from CLI
            cli_overrides = {k: v for k, v in cli_overrides.items() if v is not None}
            merged_dict.update(cli_overrides)
        
        self._config = PipelineConfig(**merged_dict)
        return self._config
    
    @property
    def config(self) -> PipelineConfig:
        """Get the loaded configuration."""
        if self._config is None:
            self._config = self.load_config()
        return self._config