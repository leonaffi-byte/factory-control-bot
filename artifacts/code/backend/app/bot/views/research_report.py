"""Research report view — format SelfResearchReport with suggestions."""

from __future__ import annotations

from typing import Any

from app.bot.views.base import TelegramView


def format_research_report(report: Any) -> str:
    """
    Format a SelfResearchReport as an HTML Telegram message.

    The report object is expected to have:
        - summary: str
        - suggestions: list of suggestion objects with:
            - title: str
            - description: str
            - risk: str ("low", "medium", "high")
            - impact: str
            - category: str (optional)
        - metrics: dict (optional, key=str, value=str|float)
        - created_at: datetime or str (optional)

    Args:
        report: SelfResearchReport instance (duck-typed).

    Returns:
        HTML string for Telegram.
    """
    view = TelegramView()

    summary = getattr(report, "summary", "No summary available.")
    suggestions = getattr(report, "suggestions", [])
    metrics = getattr(report, "metrics", {})
    created_at = getattr(report, "created_at", None)

    lines = [
        view.section_header("Self-Research Report"),
        "",
    ]

    if created_at:
        ts_str = str(created_at)[:19]
        lines.append(f"<i>{ts_str}</i>")
        lines.append("")

    # Summary
    lines.append("<b>Summary</b>")
    short_summary = summary[:400] + ("..." if len(summary) > 400 else "")
    lines.append(short_summary)

    # Key metrics
    if metrics:
        lines += ["", "<b>Key Metrics:</b>"]
        for key, val in list(metrics.items())[:8]:
            lines.append(f"  • {key}: <code>{val}</code>")

    # Suggestions overview
    if suggestions:
        low = [s for s in suggestions if getattr(s, "risk", "") == "low"]
        med = [s for s in suggestions if getattr(s, "risk", "") == "medium"]
        high = [s for s in suggestions if getattr(s, "risk", "") == "high"]

        lines += [
            "",
            f"<b>Suggestions ({len(suggestions)} total):</b>",
            f"  Low risk: {len(low)}  |  Medium: {len(med)}  |  High: {len(high)}",
            "",
        ]

        RISK_EMOJI = {"low": "\U0001f7e2", "medium": "\U0001f7e1", "high": "\U0001f534"}

        for i, s in enumerate(suggestions[:6]):
            title = getattr(s, "title", f"Suggestion {i + 1}")
            risk = getattr(s, "risk", "unknown")
            impact = getattr(s, "impact", "")
            category = getattr(s, "category", "")
            r_emoji = RISK_EMOJI.get(risk, "\u2b24")

            line = f"  {r_emoji} <b>{title}</b>"
            if category:
                line += f" [{category}]"
            lines.append(line)
            if impact:
                lines.append(f"     Impact: {impact}")

        if len(suggestions) > 6:
            lines.append(f"  ... and {len(suggestions) - 6} more.")
    else:
        lines += ["", "<i>No suggestions generated.</i>"]

    text = "\n".join(lines)
    return view.truncate(text)
