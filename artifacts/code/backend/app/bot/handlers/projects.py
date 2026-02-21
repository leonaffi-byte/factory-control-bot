"""Project management handlers — list, detail, and actions."""

from __future__ import annotations

from uuid import UUID

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.keyboards.project_actions import get_project_actions_keyboard
from app.services import ServiceContainer
from app.utils.formatting import (
    format_project_list_item,
    format_project_detail,
    format_run_status,
    truncate_message,
    relative_time,
)

logger = structlog.get_logger()

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


async def projects_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /projects command — show project list."""
    await _show_project_list(update, context)


async def _show_project_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display paginated project list."""
    services: ServiceContainer = context.application.bot_data["services"]

    page = context.user_data.get("projects_page", 0) if context.user_data else 0
    limit = 10
    offset = page * limit

    projects, total = await services.project_service.list_projects(offset=offset, limit=limit)

    if not projects:
        text = "<b>Projects</b>\n\nNo projects found. Use /new to create one."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("New Project", callback_data="menu:new_project")],
            [InlineKeyboardButton("\u00ab Back", callback_data="menu:back")],
        ])
    else:
        lines = ["<b>Projects</b>\n"]
        for proj in projects:
            emoji = STATUS_EMOJI.get(proj.status, "\u2753")
            engines_str = ", ".join(proj.engines) if proj.engines else "none"
            last_time = relative_time(proj.updated_at) if proj.updated_at else "never"
            lines.append(
                f"{emoji} <b>{proj.name}</b>\n"
                f"   Engine: {engines_str} | Status: {proj.status}\n"
                f"   Cost: ${proj.total_cost:.2f} | Last: {last_time}"
            )

        text = "\n".join(lines)
        text += f"\n\nShowing {offset + 1}-{min(offset + limit, total)} of {total}"

        buttons = []
        row = []
        for proj in projects:
            row.append(
                InlineKeyboardButton(
                    f"{STATUS_EMOJI.get(proj.status, '')} {proj.name}",
                    callback_data=f"project:{proj.id}",
                )
            )
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("\u25c0 Prev", callback_data="project:page:prev"))
        if offset + limit < total:
            nav_row.append(InlineKeyboardButton("Next \u25b6", callback_data="project:page:next"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="menu:back")])
        keyboard = InlineKeyboardMarkup(buttons)

    # Send or edit
    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def project_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle project detail and pagination callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("project:")

    if data.startswith("page:"):
        direction = data.removeprefix("page:")
        if context.user_data is None:
            return
        page = context.user_data.get("projects_page", 0)
        if direction == "next":
            context.user_data["projects_page"] = page + 1
        elif direction == "prev":
            context.user_data["projects_page"] = max(0, page - 1)
        await _show_project_list(update, context)
        return

    # project:<uuid>
    try:
        project_id = UUID(data)
    except ValueError:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    project = await services.project_service.get_project(project_id)

    if not project:
        await query.edit_message_text("Project not found.")
        return

    text = format_project_detail(project)
    keyboard = get_project_actions_keyboard(project)
    await query.edit_message_text(text, reply_markup=keyboard)


async def project_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle project action callbacks (start, stop, pause, delete, logs)."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("proj_action:")
    parts = data.split(":")
    if len(parts) < 2:
        return

    action = parts[0]
    project_id_str = parts[1]

    try:
        project_id = UUID(project_id_str)
    except ValueError:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    project = await services.project_service.get_project(project_id)
    if not project:
        await query.edit_message_text("Project not found.")
        return

    user_id = update.effective_user.id if update.effective_user else 0

    if action == "start":
        # Start factory runs for all selected engines
        runs_started = []
        for engine in project.engines:
            try:
                run = await services.factory_runner.start_run(
                    project=project, engine=engine, created_by=user_id,
                )
                runs_started.append(f"{engine}: {run.id}")
                # Attach monitor
                await services.run_monitor.attach(run)
            except Exception as e:
                logger.error("start_run_failed", engine=engine, error=str(e))
                await query.message.reply_text(f"Failed to start {engine}: {e}")

        if runs_started:
            await services.project_service.update_status(project_id, "running")
            await query.edit_message_text(
                f"<b>Factory started for {project.name}</b>\n\n"
                + "\n".join(f"  {r}" for r in runs_started)
                + "\n\nMonitoring active. You'll receive notifications on progress."
            )

    elif action == "stop":
        runs = await services.factory_runner.get_runs_for_project(project_id)
        for run in runs:
            if run.status == "running":
                await services.factory_runner.stop_run(run.id)
        await services.project_service.update_status(project_id, "failed")
        await query.edit_message_text(f"Factory stopped for <b>{project.name}</b>.")

    elif action == "pause":
        runs = await services.factory_runner.get_runs_for_project(project_id)
        for run in runs:
            if run.status == "running":
                await services.factory_runner.pause_run(run.id)
        await services.project_service.update_status(project_id, "paused")
        await query.edit_message_text(f"Factory paused for <b>{project.name}</b>.")

    elif action == "delete":
        success = await services.project_service.delete_project(project_id)
        if success:
            await query.edit_message_text(f"Project <b>{project.name}</b> deleted.")
        else:
            await query.edit_message_text("Failed to delete project.")

    elif action == "logs":
        runs = await services.factory_runner.get_runs_for_project(project_id)
        if not runs:
            await query.edit_message_text("No runs found for this project.")
            return

        text_parts = [f"<b>Runs for {project.name}</b>\n"]
        for run in runs[-5:]:  # Last 5 runs
            text_parts.append(format_run_status(run))

        await query.edit_message_text(
            truncate_message("\n".join(text_parts)),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u00ab Back", callback_data=f"project:{project_id}")],
            ]),
        )

    elif action == "runs":
        runs = await services.factory_runner.get_runs_for_project(project_id)
        if not runs:
            await query.edit_message_text("No runs found.")
            return

        buttons = []
        for run in runs:
            emoji = STATUS_EMOJI.get(run.status, "")
            buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {run.engine} - {run.status}",
                    callback_data=f"proj_action:run_detail:{run.id}",
                )
            ])
        buttons.append([InlineKeyboardButton("\u00ab Back", callback_data=f"project:{project_id}")])

        await query.edit_message_text(
            f"<b>Runs for {project.name}</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
