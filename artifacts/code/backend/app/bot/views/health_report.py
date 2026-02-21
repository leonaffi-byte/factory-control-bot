"""Health report view — format HealthReport as a Telegram message."""

from __future__ import annotations

from typing import Any

from app.bot.views.base import TelegramView


def format_health_report(report: Any) -> str:
    """
    Format a HealthReport object as an HTML Telegram message.

    The report object is expected to have:
        - overall_status: str ("ok", "warning", "critical")
        - checks: list of check objects with:
            - name: str
            - status: str
            - message: str (optional)
            - value: Any (optional, e.g. "78%" or 1024)
        - uptime_seconds: int (optional)
        - timestamp: datetime or str (optional)

    Args:
        report: HealthReport instance (duck-typed).

    Returns:
        HTML string for Telegram.
    """
    view = TelegramView()

    overall_status = getattr(report, "overall_status", "unknown")
    badge = view.status_badge(overall_status)

    STATUS_LABEL = {
        "ok": "All Systems Operational",
        "warning": "Degraded Performance",
        "critical": "Critical — Action Required",
        "unknown": "Status Unknown",
    }
    label = STATUS_LABEL.get(overall_status, overall_status.title())

    lines = [
        view.section_header(f"{badge} Health Report"),
        "",
        f"<b>Overall:</b> {badge} {label}",
    ]

    # Uptime
    uptime = getattr(report, "uptime_seconds", None)
    if uptime is not None:
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            uptime_str = f"{hours}h {minutes}m"
        else:
            uptime_str = f"{minutes}m {seconds}s"
        lines.append(view.key_value("Uptime", uptime_str))

    # Timestamp
    ts = getattr(report, "timestamp", None)
    if ts:
        ts_str = str(ts)[:19] if len(str(ts)) > 19 else str(ts)
        lines.append(view.key_value("Checked", ts_str))

    lines.append("")

    # Individual checks
    checks = getattr(report, "checks", [])
    if checks:
        lines.append("<b>Checks:</b>")
        for check in checks:
            name = getattr(check, "name", "unknown")
            status = getattr(check, "status", "unknown")
            message = getattr(check, "message", "")
            value = getattr(check, "value", None)

            check_badge = view.status_badge(status)
            line = f"  {check_badge} <b>{name}</b>"
            if value is not None:
                line += f": <code>{value}</code>"
            if message:
                line += f"\n     <i>{message[:100]}</i>"
            lines.append(line)
    else:
        lines.append("<i>No individual checks available.</i>")

    # Summary counts
    if checks:
        ok_count = sum(1 for c in checks if getattr(c, "status", "") == "ok")
        warn_count = sum(1 for c in checks if getattr(c, "status", "") == "warning")
        crit_count = sum(1 for c in checks if getattr(c, "status", "") == "critical")
        lines += [
            "",
            f"OK: {ok_count}  |  Warning: {warn_count}  |  Critical: {crit_count}",
        ]

    text = "\n".join(lines)
    return view.truncate(text)
