"""Rich progress bar and live display helpers for CLI output."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

console = Console()

# ── Progress bar factories ───────────────────────────────────────────────────


def make_pipeline_progress() -> Progress:
    """
    Create a Rich Progress instance styled for factory pipeline phases.

    Displays: spinner | phase label | bar | N/M | elapsed | remaining
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}", justify="right"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    )


def make_scan_progress() -> Progress:
    """
    Create a Rich Progress instance for model scanning.

    Displays: spinner | provider/model label | bar | elapsed
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def make_download_progress() -> Progress:
    """
    Create a Rich Progress instance for file download / backup operations.

    Displays: spinner | description | bar | N/M | elapsed
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[green]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


# ── Live display helpers ──────────────────────────────────────────────────────


@contextmanager
def pipeline_live(
    phases: list[str],
) -> Generator[tuple[Progress, list[int]], None, None]:
    """
    Context manager that shows a live pipeline progress display.

    Usage::

        phases = ["Phase 0", "Phase 1", ..., "Phase 7"]
        with pipeline_live(phases) as (progress, task_ids):
            for i, task_id in enumerate(task_ids):
                # ... run phase i ...
                progress.advance(task_id)

    Yields:
        (progress, task_ids) — the Progress instance and a list of task IDs,
        one per phase.
    """
    progress = make_pipeline_progress()
    task_ids: list[int] = []

    with Live(progress, refresh_per_second=4, console=console):
        for phase_name in phases:
            task_id = progress.add_task(phase_name, total=1)
            task_ids.append(task_id)
        yield progress, task_ids


@contextmanager
def scanning_live(provider_names: list[str]) -> Generator[tuple[Progress, list[int]], None, None]:
    """
    Context manager for a live model-scanning display.

    Yields:
        (progress, task_ids) — one task per provider.
    """
    progress = make_scan_progress()
    task_ids: list[int] = []

    with Live(progress, refresh_per_second=4, console=console):
        for name in provider_names:
            task_id = progress.add_task(f"Scanning {name}", total=1)
            task_ids.append(task_id)
        yield progress, task_ids


# ── Status-line helpers ───────────────────────────────────────────────────────


def print_phase_header(phase: int, name: str) -> None:
    """Print a bold phase header line to the console."""
    console.rule(
        f"[bold blue]Phase {phase}: {name}[/]",
        style="blue",
    )


def print_gate_result(phase: int, score: int, passed: bool, threshold: int) -> None:
    """Print a formatted quality gate result to the console."""
    color = "bold green" if passed else "bold red"
    verdict = "PASSED" if passed else "FAILED"
    console.print(
        f"  Quality Gate Phase {phase}: "
        f"[{color}]{verdict}[/] "
        f"({score}/{threshold})"
    )


def live_log_table(entries: list[dict]) -> Table:
    """
    Build a live-refreshable Rich Table for recent log entries.

    Each entry dict should have keys: timestamp, level, message.
    """
    table = Table(show_header=True, header_style="bold dim", expand=True)
    table.add_column("Time", style="dim", width=8, no_wrap=True)
    table.add_column("Level", width=7, no_wrap=True)
    table.add_column("Message")

    _LEVEL_COLORS = {
        "INFO": "blue",
        "WARNING": "yellow",
        "ERROR": "red",
        "DEBUG": "dim",
        "CRITICAL": "bold red",
    }

    for entry in entries[-30:]:  # show last 30 lines
        ts = entry.get("timestamp", "")
        if len(ts) >= 19:
            ts = ts[11:19]  # extract HH:MM:SS from ISO timestamp
        level = entry.get("level", "INFO").upper()
        color = _LEVEL_COLORS.get(level, "white")
        table.add_row(ts, f"[{color}]{level}[/]", entry.get("message", ""))

    return table
