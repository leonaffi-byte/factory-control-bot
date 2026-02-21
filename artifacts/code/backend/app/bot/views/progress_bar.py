"""Progress bar view — phase-by-phase progress visualization for factory runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.bot.views.base import TelegramView

if TYPE_CHECKING:
    from app.models.factory_run import FactoryRun

DEFAULT_PHASES = [
    "Complexity Assessment",
    "Requirements Analysis",
    "Brainstorm",
    "Architecture",
    "Implementation + Testing",
    "Cross-Provider Review",
    "Fix Cycle",
    "Docs & Release",
]


def format_run_progress(
    run: "FactoryRun",
    phases: list[str] | None = None,
) -> str:
    """
    Format a factory run as an HTML progress card with a phase-by-phase breakdown.

    Args:
        run: The FactoryRun model instance.
        phases: List of phase names. Defaults to DEFAULT_PHASES.

    Returns:
        HTML string suitable for Telegram.
    """
    view = TelegramView()
    phases = phases or DEFAULT_PHASES
    total = len(phases)
    current = max(0, min(getattr(run, "current_phase", 0), total))

    engine = getattr(run, "engine", "unknown")
    status = getattr(run, "status", "unknown")
    run_id = getattr(run, "id", "")
    cost = float(getattr(run, "total_cost", 0.0) or 0.0)
    phase_name = phases[current] if current < total else "Complete"

    badge = view.status_badge(status)
    bar = view.progress_bar(current, total)

    lines = [
        f"{badge} <b>{engine}</b> — {status.upper()}",
        f"Phase: <b>{phase_name}</b> ({current}/{total})",
        f"<code>{bar}</code>",
        "",
    ]

    # Phase checklist
    for i, name in enumerate(phases):
        if i < current:
            marker = "\u2705"  # done
        elif i == current:
            marker = "\U0001f504" if status == "running" else "\u23f8"  # running or paused
        else:
            marker = "\u25cb"  # upcoming
        lines.append(f"  {marker} {i}. {name}")

    lines += [
        "",
        view.key_value("Cost", f"${cost:.2f}"),
        f"<code>Run: {run_id}</code>",
    ]

    error = getattr(run, "error_message", None)
    if error and status == "failed":
        short_err = error[:150] + ("..." if len(error) > 150 else "")
        lines += ["", f"<b>Error:</b> <code>{short_err}</code>"]

    return "\n".join(lines)


def format_phase_summary(phases: list[str], current_phase: int) -> str:
    """
    Format a compact phase summary showing completed/current/upcoming phases.

    Args:
        phases: List of phase names.
        current_phase: Zero-indexed current phase index.

    Returns:
        Multi-line HTML string.
    """
    view = TelegramView()
    total = len(phases)
    bar = view.progress_bar(current_phase, total)

    lines = [f"<code>{bar}</code>", ""]
    for i, name in enumerate(phases):
        if i < current_phase:
            icon = "\u2713"  # check
        elif i == current_phase:
            icon = "\u25b6"  # arrow (current)
        else:
            icon = "\u00b7"  # dot
        bold_open = "<b>" if i == current_phase else ""
        bold_close = "</b>" if i == current_phase else ""
        lines.append(f"  {icon} {bold_open}{name}{bold_close}")

    return "\n".join(lines)
