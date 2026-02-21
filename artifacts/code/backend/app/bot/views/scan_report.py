"""Scan report view — format ScanResult with grades table."""

from __future__ import annotations

from typing import Any

from app.bot.views.base import TelegramView


def format_scan_report(result: Any) -> str:
    """
    Format a ScanResult object as an HTML Telegram message.

    The result object is expected to have:
        - providers: list of provider objects with:
            - name: str
            - status: str
            - models: list of model objects with:
                - id: str
                - grade: str ("A+", "A", "B", "C", "F")
                - latency_ms: int (optional)
                - context_window: int (optional)
            - latency_ms: int (optional)
        - routing_suggestion: optional suggestion object with:
            - mode: str
            - reason: str
        - scanned_at: datetime or str (optional)

    Args:
        result: ScanResult instance (duck-typed).

    Returns:
        HTML string for Telegram.
    """
    view = TelegramView()

    providers = getattr(result, "providers", [])
    suggestion = getattr(result, "routing_suggestion", None)
    scanned_at = getattr(result, "scanned_at", None)

    lines = [
        view.section_header("Model Scan Results"),
        "",
    ]

    if scanned_at:
        ts_str = str(scanned_at)[:19]
        lines.append(f"<i>Scanned: {ts_str}</i>")
        lines.append("")

    total_models = sum(len(getattr(p, "models", [])) for p in providers)
    lines.append(
        f"Found <b>{len(providers)}</b> providers, <b>{total_models}</b> models total\n"
    )

    # Provider/model table
    if providers:
        lines.append("<b>Providers & Models:</b>")
        lines.append("<code>")
        lines.append(f"{'Provider':<18} {'St':<4} {'Models':<7} {'Best'}")
        lines.append("-" * 40)

        for p in providers:
            name = getattr(p, "name", "unknown")[:18]
            status = getattr(p, "status", "?")
            models = getattr(p, "models", [])
            model_count = len(models)

            # Find best grade
            grades = [getattr(m, "grade", "?") for m in models]
            GRADE_ORDER = ["A+", "A", "B+", "B", "C+", "C", "D", "F", "?"]
            best_grade = next(
                (g for g in GRADE_ORDER if g in grades), grades[0] if grades else "?"
            )

            status_tag = {"ok": "OK", "error": "ERR", "unknown": "?", "degraded": "DEG"}.get(
                status, status[:4]
            )
            lines.append(f"{name:<18} {status_tag:<4} {model_count:<7} {best_grade}")

        lines.append("</code>")
    else:
        lines.append("<i>No providers found.</i>")

    # Top models by grade
    all_models_with_provider: list[tuple[str, Any]] = []
    for p in providers:
        p_name = getattr(p, "name", "?")
        for m in getattr(p, "models", []):
            all_models_with_provider.append((p_name, m))

    GRADE_RANK = {"A+": 0, "A": 1, "B+": 2, "B": 3, "C+": 4, "C": 5, "D": 6, "F": 7, "?": 99}
    top_models = sorted(
        all_models_with_provider,
        key=lambda pm: GRADE_RANK.get(getattr(pm[1], "grade", "?"), 99),
    )[:5]

    if top_models:
        lines += ["", "<b>Top Models:</b>"]
        for p_name, m in top_models:
            m_id = getattr(m, "id", "unknown")
            grade = getattr(m, "grade", "?")
            latency = getattr(m, "latency_ms", None)
            latency_str = f" {latency}ms" if latency is not None else ""
            ctx = getattr(m, "context_window", None)
            ctx_str = f" {ctx // 1000}K ctx" if ctx else ""
            lines.append(f"  [{grade}] <code>{m_id}</code>{latency_str}{ctx_str} ({p_name})")

    # Routing suggestion
    if suggestion:
        mode = getattr(suggestion, "mode", "unknown")
        reason = getattr(suggestion, "reason", "")
        lines += [
            "",
            "<b>Routing Suggestion:</b>",
            f"  Mode: <code>{mode}</code>",
        ]
        if reason:
            lines.append(f"  <i>{reason[:200]}</i>")

    text = "\n".join(lines)
    return view.truncate(text)
