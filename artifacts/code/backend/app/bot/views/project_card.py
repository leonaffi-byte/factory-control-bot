"""Project card view — format project info as a Telegram HTML card."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.bot.views.base import TelegramView

if TYPE_CHECKING:
    from app.models.project import Project


def format_project_card(project: "Project") -> str:
    """
    Format a Project as a Telegram HTML card.

    Returns a message string with HTML parse mode.
    """
    view = TelegramView()
    status = project.status
    badge = view.status_badge(status)
    engines = ", ".join(project.engines) if project.engines else "none"

    cost = float(getattr(project, "total_cost", 0.0) or 0.0)

    lines = [
        view.section_header(f"{badge} {project.name}"),
        "",
        view.key_value("Status", f"{badge} {status}"),
        view.key_value("Engines", engines),
        view.key_value("Total Cost", f"${cost:.2f}"),
    ]

    description = getattr(project, "description", "")
    if description:
        short_desc = description[:200] + ("..." if len(description) > 200 else "")
        lines += ["", "<b>Description:</b>", short_desc]

    github_url = getattr(project, "github_url", None)
    if github_url:
        lines.append(view.key_value("GitHub", f'<a href="{github_url}">{github_url}</a>'))

    runs = getattr(project, "runs", [])
    if runs:
        lines.append("")
        lines.append(f"<b>Runs:</b> {len(runs)} total")
        active = [r for r in runs if getattr(r, "status", "") == "running"]
        if active:
            lines.append(f"  Active: {len(active)} running")

    project_id = getattr(project, "id", "")
    lines += [
        "",
        f"<code>ID: {project_id}</code>",
    ]

    return "\n".join(lines)


def format_project_list_card(projects: list["Project"], page: int, total: int, per_page: int = 10) -> str:
    """
    Format a paginated project list as HTML.

    Args:
        projects: Projects on the current page.
        page: Zero-indexed page number.
        total: Total number of projects.
        per_page: Items per page.

    Returns:
        HTML string for the Telegram message.
    """
    view = TelegramView()
    offset = page * per_page

    lines = [view.section_header("Projects"), ""]
    for proj in projects:
        badge = view.status_badge(proj.status)
        engines = ", ".join(proj.engines) if proj.engines else "none"
        cost = float(getattr(proj, "total_cost", 0.0) or 0.0)
        lines.append(
            f"{badge} <b>{proj.name}</b>\n"
            f"   {view.key_value('Engine', engines)} | ${cost:.2f}"
        )

    lines.append("")
    end = min(offset + per_page, total)
    lines.append(f"Showing {offset + 1}–{end} of {total}")

    return "\n".join(lines)
