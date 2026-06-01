import os
import sys
os.environ["PYTHONIOENCODING"] = "utf-8"

# Force UTF-8 on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

"""
run_outreach.py
===============
CLI entry point for the Automated Outreach Bot.

Usage:
    python run_outreach.py
    python run_outreach.py --config ./config/outreach_config.yaml
    python run_outreach.py --headed --dry-run
"""

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core import Config
from src.outreach.bot import OutreachBot
from src.outreach.message_handler import MessageHandler
from src.utils.logger import setup_logger

console = Console(force_terminal=True)


@click.command()
@click.option(
    "--config", "-c",
    default="./config/outreach_config.yaml",
    help="Path to the outreach config file.",
    type=click.Path(exists=True),
)
@click.option(
    "--headed",
    is_flag=True,
    default=False,
    help="Run browser in headed (visible) mode for debugging.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview messages without actually sending them.",
)
def main(config: str, headed: bool, dry_run: bool):
    """Send automated outreach messages to scraped users."""

    # ── Banner ──
    console.print(Panel.fit(
        "[bold magenta]Automation-Flow[/bold magenta] - [dim]Outreach Bot[/dim]",
        border_style="magenta",
    ))

    # ── Load config ──
    try:
        cfg = Config(config, root_key="outreach" if str(config).endswith(".json") else None)
    except Exception as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    # Override headless mode
    if headed and cfg.data.get("browser"):
        cfg.data["browser"]["headless"] = False

    # Setup logging
    log_level = cfg.get("logging", "level", default="INFO")
    logger = setup_logger("outreach", log_dir="./logs", level=log_level)

    # ── Dry run: preview messages ──
    if dry_run:
        console.print("[yellow]>> DRY RUN -- no messages will be sent[/yellow]\n")
        template_path = cfg.get(
            "message", "template_file", default="./config/message_template.txt"
        )
        try:
            handler = MessageHandler(template_path)
            preview = handler.preview("sample_user")
            console.print(Panel(
                preview,
                title="Message Preview",
                border_style="yellow",
            ))
        except Exception as e:
            console.print(f"[red]Template error:[/red] {e}")

        # Show rate limit settings
        rl = cfg.get("rate_limit") or {}
        table = Table(title="Rate Limit Settings", border_style="yellow")
        table.add_column("Setting", style="bold")
        table.add_column("Value", style="cyan")
        table.add_row("Messages/hour", str(rl.get("messages_per_hour", "-")))
        table.add_row("Daily limit", str(rl.get("daily_limit", "-")))
        table.add_row("Delay range", f"{rl.get('min_delay_seconds', '?')}-{rl.get('max_delay_seconds', '?')}s")
        table.add_row("Batch size", str(rl.get("batch_size", "-")))
        table.add_row("Batch pause", f"{rl.get('batch_pause_minutes', '?')} min")
        console.print(table)
        return

    # ── Confirmation ──
    rl = cfg.get("rate_limit") or {}
    console.print(
        f"\n[bold]Rate limits:[/bold] "
        f"{rl.get('messages_per_hour', '?')}/hr, "
        f"{rl.get('daily_limit', '?')}/day, "
        f"{rl.get('min_delay_seconds', '?')}-{rl.get('max_delay_seconds', '?')}s delay"
    )

    if not click.confirm("\nProceed with outreach?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return

    # ── Run bot ──
    bot = OutreachBot(cfg)

    try:
        summary = asyncio.run(bot.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]>> Interrupted by user -- saving progress...[/yellow]")
        asyncio.run(bot.shutdown())
        sys.exit(0)

    # ── Summary ──
    table = Table(title="Outreach Results", border_style="magenta")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="green")
    table.add_row("Messages sent", f"[green]{summary['sent']}[/green]")
    table.add_row("Failed", f"[red]{summary['failed']}[/red]")
    table.add_row("Skipped", f"[yellow]{summary['skipped']}[/yellow]")
    table.add_row("Duration", f"{summary['duration_seconds']}s")
    console.print(table)

    log_path = cfg.get("logging", "message_log", default="./logs/outreach_log.csv")
    console.print(f"\n[dim]Full audit log: {log_path}[/dim]")


if __name__ == "__main__":
    main()
