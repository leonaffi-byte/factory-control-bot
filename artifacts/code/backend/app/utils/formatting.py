"""Telegram message formatting helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.factory_run import FactoryRun

# Max Telegram message length
MAX_MESSAGE_LEN = 4096

# Status emoji mapping
STATUS_EMOJI = {
    "draft": "\u270f\ufe0f",
    "queued": "\u23f3",
    "running": "\u2699\ufe0f",
    "paused": "\u23f8",
    "completed": "\u2705",
    "failed": "\u274c",
    "deployed": "\U0001f680",
}

# Phase names
PHASE_NAMES = {
    0: "Setup",
    1: "Requirements",
    2: "Brainstorm",
    3: "Architecture",
    4: "Implementation",
    5: "Review",
    6: "Fix Cycle",
    7: "Documentation",
}


def truncate_message(text: str, max_len: int = MAX_MESSAGE_LEN) -> str:
    """
    Truncate a message to fit Telegram's character limit.

    If truncated, adds "... (truncated)" at the end.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n\n... (truncated)"


def relative_time(dt: datetime | None) -> str:
    """
    Format a datetime as a human-readable relative time string.

    Examples: "2 min ago", "3 hours ago", "5 days ago"
    """
    if dt is None:
        return "never"

    now = datetime.utcnow()
    delta = now - dt

    if delta < timedelta(seconds=60):
        return "just now"
    elif delta < timedelta(minutes=60):
        mins = int(delta.total_seconds() / 60)
        return f"{mins} min ago"
    elif delta < timedelta(hours=24):
        hours = int(delta.total_seconds() / 3600)
        return f"{hours} hours ago"
    elif delta < timedelta(days=30):
        days = int(delta.total_seconds() / 86400)
        return f"{days} days ago"
    else:
        return dt.strftime("%Y-%m-%d")


def format_project_list_item(project: "Project") -> str:
    """Format a project for display in a list."""
    emoji = STATUS_EMOJI.get(project.status, "\u2753")
    engines_str = ", ".join(project.engines) if project.engines else "none"
    cost = float(project.total_cost or 0)
    last_time = relative_time(project.updated_at) if project.updated_at else "never"

    return (
        f"{emoji} <b>{project.name}</b>\n"
        f"   Engine: {engines_str} | Status: {project.status}\n"
        f"   Cost: ${cost:.2f} | Last: {last_time}"
    )


def format_project_detail(project: "Project") -> str:
    """Format a project for the detail view."""
    emoji = STATUS_EMOJI.get(project.status, "\u2753")
    engines_str = ", ".join(project.engines) if project.engines else "none"
    cost = float(project.total_cost or 0)
    created = project.created_at.strftime("%Y-%m-%d %H:%M") if project.created_at else "unknown"
    updated = relative_time(project.updated_at) if project.updated_at else "never"

    text = (
        f"{emoji} <b>{project.name}</b>\n\n"
        f"<b>Status:</b> {project.status}\n"
        f"<b>Engines:</b> {engines_str}\n"
        f"<b>Cost:</b> ${cost:.2f}\n"
        f"<b>Created:</b> {created}\n"
        f"<b>Updated:</b> {updated}\n"
    )

    if project.description:
        desc = project.description[:200]
        if len(project.description) > 200:
            desc += "..."
        text += f"\n<b>Description:</b> {desc}\n"

    if project.github_url:
        text += f"\n<b>GitHub:</b> {project.github_url}\n"

    return text


def format_run_status(run: "FactoryRun") -> str:
    """Format a factory run status for display."""
    emoji = STATUS_EMOJI.get(run.status, "\u2753")
    phase_name = PHASE_NAMES.get(run.current_phase, f"Phase {run.current_phase}")
    cost = float(run.total_cost or 0)
    started = run.started_at.strftime("%H:%M") if run.started_at else "?"

    text = (
        f"{emoji} <b>{run.engine}</b> — {run.status}\n"
        f"   Phase: {run.current_phase}/7 ({phase_name})\n"
        f"   Cost: ${cost:.2f} | Started: {started}"
    )

    if run.error_message:
        text += f"\n   Error: {run.error_message[:100]}"

    return text


def format_duration(minutes: float | None) -> str:
    """Format duration in minutes to a human-readable string."""
    if minutes is None:
        return "N/A"

    if minutes < 1:
        return f"{int(minutes * 60)}s"
    elif minutes < 60:
        return f"{int(minutes)}m"
    else:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}m"


def format_cost(amount: float | None) -> str:
    """Format a cost amount."""
    if amount is None:
        return "$0.00"
    return f"${amount:.2f}"


def mask_api_key(key: str) -> str:
    """Show first 4 and last 4 characters only."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def progress_bar(percent: float, length: int = 10) -> str:
    """Create a text-based progress bar."""
    filled = int(percent / (100 / length))
    filled = min(filled, length)
    return "\u2588" * filled + "\u2591" * (length - filled)
