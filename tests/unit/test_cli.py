"""Unit tests for CLI interface."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.models.data_models import PipelineResult, SourceSummary, Summary
from src.pipeline.main import main


@pytest.fixture
def mock_result():
    """Create a mock pipeline result."""
    return PipelineResult(
        summary=Summary(
            total_products=150,
            processing_time_seconds=12.34,
            success_rate=0.95,
        ),
        sources=[
            SourceSummary(
                name="api1",
                items_fetched=50,
                errors=1,
                avg_price=29.99,
            ),
            SourceSummary(
                name="api2",
                items_fetched=50,
                errors=2,
                avg_price=39.99,
            ),
            SourceSummary(
                name="api3",
                items_fetched=50,
                errors=0,
                avg_price=19.99,
            ),
        ],
        products=[],
        errors=[],
    )


def test_cli_help():
    """Test that CLI help message works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    
    assert result.exit_code == 0
    assert "Async Data Pipeline" in result.output
    assert "--config" in result.output
    assert "--timeout" in result.output
    assert "--rate-limit" in result.output


def test_cli_version():
    """Test that version flag works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    
    assert result.exit_code == 0
    assert "1.0.0" in result.output


@patch("src.pipeline.main.PipelineOrchestrator")
@patch("src.pipeline.main.ConfigManager")
@patch("src.pipeline.main.JSONOutputFormatter")
def test_cli_runs_with_defaults(
    mock_formatter_class,
    mock_config_manager_class,
    mock_orchestrator_class,
    mock_result,
    tmp_path,
):
    """Test CLI runs with default configuration."""
    # Setup mocks
    mock_config = MagicMock()
    mock_config.output_path = tmp_path / "summary.json"
    mock_config.endpoints = []
    mock_config.total_timeout = 60.0
    mock_config.max_requests_per_second = 5
    mock_config.worker_pool_size = 4
    mock_config.bounded_queue_size = 100
    
    mock_config_manager = MagicMock()
    mock_config_manager.load_config.return_value = mock_config
    mock_config_manager_class.return_value = mock_config_manager
    
    # Mock orchestrator to return result
    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(return_value=mock_result)
    mock_orchestrator_class.return_value = mock_orchestrator
    
    mock_formatter = MagicMock()
    mock_formatter_class.return_value = mock_formatter
    
    # Run CLI with explicit config path
    runner = CliRunner()
    config_file = tmp_path / "config.yaml"
    config_file.write_text("# Empty config")
    
    result = runner.invoke(main, ["--config", str(config_file), "--no-progress"])
    
    # Verify
    assert result.exit_code == 0
    mock_config_manager.load_config.assert_called_once()
    mock_orchestrator_class.assert_called_once()
    mock_formatter.save.assert_called_once()


@patch("src.pipeline.main.PipelineOrchestrator")
@patch("src.pipeline.main.ConfigManager")
@patch("src.pipeline.main.JSONOutputFormatter")
def test_cli_applies_overrides(
    mock_formatter_class,
    mock_config_manager_class,
    mock_orchestrator_class,
    mock_result,
    tmp_path,
):
    """Test that CLI overrides are applied correctly."""
    # Setup mocks
    mock_config = MagicMock()
    mock_config.output_path = tmp_path / "summary.json"
    mock_config.endpoints = []
    mock_config.total_timeout = 120.0
    mock_config.max_requests_per_second = 10
    mock_config.worker_pool_size = 8
    mock_config.bounded_queue_size = 100
    
    mock_config_manager = MagicMock()
    mock_config_manager.load_config.return_value = mock_config
    mock_config_manager_class.return_value = mock_config_manager
    
    # Mock orchestrator to return result
    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(return_value=mock_result)
    mock_orchestrator_class.return_value = mock_orchestrator
    
    mock_formatter = MagicMock()
    mock_formatter_class.return_value = mock_formatter
    
    # Run CLI with overrides
    runner = CliRunner()
    config_file = tmp_path / "config.yaml"
    config_file.write_text("# Empty config")
    
    result = runner.invoke(
        main,
        [
            "--config", str(config_file),
            "--timeout", "120",
            "--rate-limit", "10",
            "--workers", "8",
            "--log-level", "DEBUG",
            "--no-progress",
        ],
    )
    
    # Verify overrides were passed
    assert result.exit_code == 0
    call_args = mock_config_manager.load_config.call_args
    cli_overrides = call_args[0][0] if call_args[0] else {}
    
    assert cli_overrides.get("total_timeout") == 120.0
    assert cli_overrides.get("max_requests_per_second") == 10
    assert cli_overrides.get("worker_pool_size") == 8
    assert cli_overrides.get("log_level") == "DEBUG"


@patch("src.pipeline.main.PipelineOrchestrator")
@patch("src.pipeline.main.ConfigManager")
@patch("src.pipeline.main.JSONOutputFormatter")
def test_cli_custom_output_path(
    mock_formatter_class,
    mock_config_manager_class,
    mock_orchestrator_class,
    mock_result,
    tmp_path,
):
    """Test CLI with custom output path."""
    # Setup mocks
    mock_config = MagicMock()
    mock_config.output_path = tmp_path / "summary.json"
    mock_config.endpoints = []
    mock_config.total_timeout = 60.0
    mock_config.max_requests_per_second = 5
    mock_config.worker_pool_size = 4
    mock_config.bounded_queue_size = 100
    
    mock_config_manager = MagicMock()
    mock_config_manager.load_config.return_value = mock_config
    mock_config_manager_class.return_value = mock_config_manager
    
    # Mock orchestrator to return result
    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(return_value=mock_result)
    mock_orchestrator_class.return_value = mock_orchestrator
    
    mock_formatter = MagicMock()
    mock_formatter_class.return_value = mock_formatter
    
    # Run CLI with custom output
    config_file = tmp_path / "config.yaml"
    config_file.write_text("# Empty config")
    custom_output = tmp_path / "custom_output.json"
    
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(config_file), "--output", str(custom_output), "--no-progress"],
    )
    
    # Verify custom output path was used
    assert result.exit_code == 0
    mock_formatter.save.assert_called_once()
    save_call_args = mock_formatter.save.call_args
    assert str(custom_output) in str(save_call_args)


@patch("src.pipeline.main.ConfigManager")
def test_cli_handles_config_error(mock_config_manager_class):
    """Test CLI handles configuration errors gracefully."""
    # Setup mock to raise error
    mock_config_manager = MagicMock()
    mock_config_manager.load_config.side_effect = ValueError("Invalid configuration")
    mock_config_manager_class.return_value = mock_config_manager
    
    # Run CLI
    runner = CliRunner()
    result = runner.invoke(main, ["--no-progress"])
    
    # Should exit with error code
    assert result.exit_code == 1
    assert "Error" in result.output or "Invalid configuration" in result.output


def test_cli_no_progress_flag():
    """Test that --no-progress flag is recognized."""
    runner = CliRunner()
    # Just test that the flag is accepted (will fail on actual run without mocks)
    result = runner.invoke(main, ["--help"])
    
    assert "--no-progress" in result.output
    assert "Disable progress bars" in result.output
