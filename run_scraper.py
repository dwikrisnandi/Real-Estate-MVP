import os
import sys
os.environ["PYTHONIOENCODING"] = "utf-8"

# Force UTF-8 on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

"""
run_scraper.py
==============
CLI entry point for the Username Scraper.

Usage:
    python run_scraper.py
    python run_scraper.py --config ./config/scraper_config.yaml
    python run_scraper.py --headed    (visible browser for debugging)
"""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core import Config
from src.scraper.platform_scraper import PlatformScraper
from src.utils.csv_handler import CSVHandler
from src.utils.logger import setup_logger

console = Console(force_terminal=True)


@click.command()
@click.option(
    "--config", "-c",
    default="./config/scraper_config.yaml",
    help="Path to the scraper config file.",
    type=click.Path(exists=True),
)
@click.option(
    "--headed",
    is_flag=True,
    default=False,
    help="Run browser in headed (visible) mode for debugging.",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Override output CSV path.",
)
def main(config: str, headed: bool, output: str):
    """Scrape usernames from a membership platform."""

    # ── Banner ──
    console.print(Panel.fit(
        "[bold cyan]Automation-Flow[/bold cyan] - [dim]Username Scraper[/dim]",
        border_style="cyan",
    ))

    # ── Load config ──
    try:
        cfg = Config(config, root_key="scraper" if str(config).endswith(".json") else None)
    except Exception as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    # Override headless mode if --headed flag is used
    if headed and cfg.data.get("browser"):
        cfg.data["browser"]["headless"] = False

    # Setup logging
    log_level = cfg.get("logging", "level", default="INFO")
    logger = setup_logger("scraper", log_dir="./logs", level=log_level)

    # ── Run scraper ──
    scraper = PlatformScraper(cfg)

    try:
        result = asyncio.run(scraper.scrape())
    except KeyboardInterrupt:
        console.print("\n[yellow]>> Interrupted by user[/yellow]")
        asyncio.run(scraper.shutdown())
        sys.exit(0)

    # ── Save results ──
    if result.users:
        output_cfg = cfg.get("output") or {}
        output_dir = output_cfg.get("directory", "./output")
        output_file = output or output_cfg.get(
            "filename", "scraped_users_{timestamp}.csv"
        )
        filepath = Path(output_dir) / output_file
        columns = output_cfg.get("columns", ["username", "display_name", "profile_url", "scraped_at"])

        user_dicts = [u.to_dict() for u in result.users]
        user_dicts = CSVHandler.deduplicate(user_dicts, key="username")

        saved_path = CSVHandler.write_users(user_dicts, filepath, columns)

        # ── Summary table ──
        table = Table(title="Scrape Results", border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="green")
        table.add_row("Users found", str(len(user_dicts)))
        table.add_row("Pages scraped", str(result.pages_scraped))
        table.add_row("Duration", f"{result.duration_seconds}s")
        table.add_row("Errors", str(len(result.errors)) if result.errors else "0")
        table.add_row("Output", str(saved_path))
        console.print(table)

    else:
        console.print("[yellow]>> No users found. Check your selectors and URL.[/yellow]")
        if result.errors:
            for err in result.errors:
                console.print(f"  [red]• {err}[/red]")

    # ── Errors ──
    if result.errors:
        console.print(f"\n[yellow]>> {len(result.errors)} error(s) occurred:[/yellow]")
        for err in result.errors:
            console.print(f"  [dim red]• {err}[/dim red]")


if __name__ == "__main__":
    main()
