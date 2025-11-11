"""CLI entry point for the async data pipeline.

This module provides the command-line interface for running the pipeline
with professional argument parsing, progress indicators, and error handling.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from src.models.config import ConfigManager, PipelineConfig
from src.models.data_models import PipelineResult
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.output import JSONOutputFormatter


console = Console()


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default="config/config.yaml",
    help="Path to configuration YAML file",
)
@click.option(
    "--timeout",
    "-t",
    type=float,
    help="Total pipeline execution timeout in seconds (overrides config)",
)
@click.option(
    "--rate-limit",
    "-r",
    type=int,
    help="Requests per second per endpoint (overrides config)",
)
@click.option(
    "--workers",
    "-w",
    type=int,
    help="Number of worker threads for processing (overrides config)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output JSON file path (overrides config)",
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging level (overrides config)",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable progress bars (useful for CI/CD)",
)
@click.version_option(version="1.0.0", prog_name="async-data-pipeline")
def main(
    config: Path,
    timeout: Optional[float],
    rate_limit: Optional[int],
    workers: Optional[int],
    output: Optional[Path],
    log_level: Optional[str],
    no_progress: bool,
) -> None:
    """
    Async Data Pipeline - Concurrent product data fetching and processing.
    
    Fetches product data from multiple API endpoints concurrently, processes
    and normalizes the data, and outputs structured JSON results with
    comprehensive error handling and monitoring.
    
    Examples:
    
        # Run with default configuration
        $ uv run python -m src.pipeline.main
        
        # Override timeout and rate limit
        $ uv run python -m src.pipeline.main --timeout 120 --rate-limit 10
        
        # Use custom config file
        $ uv run python -m src.pipeline.main --config custom_config.yaml
        
        # Disable progress bars for CI/CD
        $ uv run python -m src.pipeline.main --no-progress
    """
    try:
        # Build CLI overrides dictionary
        cli_overrides = {}
        if timeout is not None:
            cli_overrides["total_timeout"] = timeout
        if rate_limit is not None:
            cli_overrides["max_requests_per_second"] = rate_limit
        if workers is not None:
            cli_overrides["worker_pool_size"] = workers
        if log_level is not None:
            cli_overrides["log_level"] = log_level.upper()
        
        # Load configuration with CLI overrides
        config_manager = ConfigManager(config)
        pipeline_config = config_manager.load_config(cli_overrides)
        
        # Determine output path
        output_path = output if output else pipeline_config.output_path
        
        # Display configuration summary
        _display_config_summary(pipeline_config, no_progress)
        
        # Run pipeline with progress tracking
        result = asyncio.run(
            _run_pipeline_with_progress(pipeline_config, no_progress)
        )
        
        # Save results
        formatter = JSONOutputFormatter()
        formatter.save(result, str(output_path))
        
        # Display final results
        _display_results(result, output_path, no_progress)
        
        # Exit with success
        sys.exit(0)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user[/yellow]")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}", style="bold red")
        if "--debug" in sys.argv:
            console.print_exception()
        sys.exit(1)


async def _run_pipeline_with_progress(
    config: PipelineConfig,
    no_progress: bool,
) -> PipelineResult:
    """
    Run the pipeline with progress tracking.
    
    Args:
        config: Pipeline configuration
        no_progress: Whether to disable progress bars
        
    Returns:
        Pipeline execution result
    """
    if no_progress:
        # Run without progress bars (for CI/CD)
        console.print("[cyan]Running pipeline...[/cyan]")
        orchestrator = PipelineOrchestrator(config)
        return await orchestrator.run()
    
    # Run with rich progress bars
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        # Create progress tasks for each endpoint
        endpoint_tasks = {}
        for endpoint in config.endpoints:
            task_id = progress.add_task(
                f"[cyan]Fetching {endpoint.name}...",
                total=None,  # Unknown total pages
            )
            endpoint_tasks[endpoint.name] = task_id
        
        # Add overall progress task
        overall_task = progress.add_task(
            "[green]Overall progress...",
            total=100,
        )
        
        # Run orchestrator
        orchestrator = PipelineOrchestrator(config)
        result = await orchestrator.run()
        
        # Complete all tasks
        for task_id in endpoint_tasks.values():
            progress.update(task_id, completed=True)
        progress.update(overall_task, completed=100)
        
        return result


def _display_config_summary(config: PipelineConfig, no_progress: bool) -> None:
    """Display configuration summary before running."""
    if no_progress:
        return
    
    console.print("\n[bold cyan]Pipeline Configuration[/bold cyan]")
    console.print(f"  Endpoints: {len(config.endpoints)}")
    console.print(f"  Rate Limit: {config.max_requests_per_second} req/s per endpoint")
    console.print(f"  Workers: {config.worker_pool_size}")
    console.print(f"  Timeout: {config.total_timeout}s")
    console.print(f"  Queue Size: {config.bounded_queue_size}")
    console.print()


def _display_results(
    result: PipelineResult,
    output_path: Path,
    no_progress: bool,
) -> None:
    """Display final results summary."""
    if no_progress:
        # Simple output for CI/CD
        console.print(f"✓ Pipeline complete: {result.summary.total_products} products")
        console.print(f"✓ Output saved to: {output_path}")
        return
    
    # Rich formatted output
    console.print("\n[bold green]Pipeline Complete![/bold green]\n")
    
    # Summary table
    summary_table = Table(title="Execution Summary", show_header=False)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    
    summary_table.add_row(
        "Total Products",
        str(result.summary.total_products),
    )
    summary_table.add_row(
        "Processing Time",
        f"{result.summary.processing_time_seconds:.2f}s",
    )
    summary_table.add_row(
        "Success Rate",
        f"{result.summary.success_rate * 100:.1f}%",
    )
    summary_table.add_row(
        "Errors",
        str(len(result.errors)),
    )
    
    console.print(summary_table)
    console.print()
    
    # Per-source statistics
    if result.sources:
        source_table = Table(title="Per-Source Statistics")
        source_table.add_column("Source", style="cyan")
        source_table.add_column("Items", justify="right", style="green")
        source_table.add_column("Errors", justify="right", style="yellow")
        source_table.add_column("Avg Price", justify="right", style="magenta")
        
        for source in result.sources:
            avg_price_str = (
                f"${source.avg_price:.2f}" if source.avg_price is not None else "N/A"
            )
            source_table.add_row(
                source.name,
                str(source.items_fetched),
                str(source.errors),
                avg_price_str,
            )
        
        console.print(source_table)
        console.print()
    
    # Output file location
    console.print(f"[bold]Output saved to:[/bold] {output_path}")
    console.print()


if __name__ == "__main__":
    main()
