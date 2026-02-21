"""Factory run control handlers — /run, /stop, /status."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.views.progress_bar import format_run_progress
from app.services import ServiceContainer

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

PHASES = [
    "Complexity Assessment",
    "Requirements Analysis",
    "Brainstorm",
    "Architecture",
    "Implementation + Testing",
    "Cross-Provider Review",
    "Fix Cycle",
    "Docs & Release",
]
TOTAL_PHASES = len(PHASES)


async def run_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /run command — start factory run with project selection."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text(
            "Only admins can start factory runs."
        )
        return

    projects, total = await services.project_service.list_projects(offset=0, limit=20)

    if not projects:
        await update.effective_message.reply_text(
            "<b>No projects found.</b>\n\nCreate one first with /new.",
            parse_mode="HTML",
        )
        return

    runnable = [p for p in projects if p.status in ("draft", "completed", "failed", "paused")]

    if not runnable:
        await update.effective_message.reply_text(
            "<b>No runnable projects.</b>\n\n"
            "All projects are currently running or queued.\n"
            "Use /status to check on them.",
            parse_mode="HTML",
        )
        return

    buttons = []
    for proj in runnable:
        engines_str = ", ".join(proj.engines) if proj.engines else "none"
        buttons.append([
            InlineKeyboardButton(
                f"{proj.name} [{engines_str}]",
                callback_data=f"factory:select:{proj.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("Cancel", callback_data="factory:cancel")])

    await update.effective_message.reply_text(
        "<b>Start Factory Run</b>\n\nSelect a project to run:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command — stop a running factory."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text(
            "Only admins can stop factory runs."
        )
        return

    active_runs = await services.factory_runner.get_active_runs()

    if not active_runs:
        await update.effective_message.reply_text(
            "<b>No active runs.</b>\n\nUse /status to see all runs.",
            parse_mode="HTML",
        )
        return

    buttons = []
    for run in active_runs:
        phase_name = PHASES[run.current_phase] if 0 <= run.current_phase < TOTAL_PHASES else "Unknown"
        buttons.append([
            InlineKeyboardButton(
                f"Stop: {run.engine} — Phase {run.current_phase} ({phase_name})",
                callback_data=f"factory:stop:{run.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("Cancel", callback_data="factory:cancel")])

    await update.effective_message.reply_text(
        "<b>Stop Factory Run</b>\n\nSelect a run to stop:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command — show current run status with progress bar."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    active_runs = await services.factory_runner.get_active_runs()

    if not active_runs:
        await update.effective_message.reply_text(
            "<b>Factory Status</b>\n\nNo active runs.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Start a Run", callback_data="factory:start_menu")],
            ]),
        )
        return

    lines = ["<b>Factory Status</b>\n"]
    for run in active_runs:
        text = format_run_progress(run, PHASES)
        lines.append(text)

    text = "\n\n".join(lines)
    if len(text) > 4096:
        text = text[:4093] + "..."

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Refresh", callback_data="factory:refresh_status"),
                InlineKeyboardButton("Stop a Run", callback_data="factory:stop_menu"),
            ],
        ]),
    )


async def factory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button callbacks prefixed with factory:*."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("factory:")

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return

    if data == "refresh_status":
        active_runs = await services.factory_runner.get_active_runs()
        if not active_runs:
            await query.edit_message_text(
                "<b>Factory Status</b>\n\nNo active runs.",
                parse_mode="HTML",
            )
            return

        lines = ["<b>Factory Status</b>\n"]
        for run in active_runs:
            lines.append(format_run_progress(run, PHASES))

        text = "\n\n".join(lines)
        if len(text) > 4096:
            text = text[:4093] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Refresh", callback_data="factory:refresh_status"),
                    InlineKeyboardButton("Stop a Run", callback_data="factory:stop_menu"),
                ],
            ]),
        )
        return

    if data == "start_menu":
        # Re-use the run handler logic
        await query.message.reply_text("Use /run to start a factory run.")
        return

    if data == "stop_menu":
        active_runs = await services.factory_runner.get_active_runs()
        if not active_runs:
            await query.edit_message_text(
                "<b>No active runs to stop.</b>",
                parse_mode="HTML",
            )
            return

        buttons = []
        for run in active_runs:
            phase_name = PHASES[run.current_phase] if 0 <= run.current_phase < TOTAL_PHASES else "Unknown"
            buttons.append([
                InlineKeyboardButton(
                    f"Stop: {run.engine} — Phase {run.current_phase} ({phase_name})",
                    callback_data=f"factory:stop:{run.id}",
                )
            ])
        buttons.append([InlineKeyboardButton("Cancel", callback_data="factory:cancel")])
        await query.edit_message_text(
            "<b>Stop Factory Run</b>\n\nSelect a run to stop:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("select:"):
        # Project selected for run — show engine confirmation
        project_id_str = data.removeprefix("select:")
        try:
            project_id = UUID(project_id_str)
        except ValueError:
            await query.edit_message_text("Invalid project ID.")
            return

        project = await services.project_service.get_project(project_id)
        if not project:
            await query.edit_message_text("Project not found.")
            return

        engines = project.engines or [services._settings.default_engine]
        engines_display = ", ".join(engines)

        await query.edit_message_text(
            f"<b>Confirm Factory Run</b>\n\n"
            f"Project: <b>{project.name}</b>\n"
            f"Engines: <code>{engines_display}</code>\n\n"
            f"This will start the full 7-phase pipeline.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Confirm Run", callback_data=f"factory:confirm:{project_id}"),
                    InlineKeyboardButton("Cancel", callback_data="factory:cancel"),
                ]
            ]),
        )
        return

    if data.startswith("confirm:"):
        project_id_str = data.removeprefix("confirm:")
        try:
            project_id = UUID(project_id_str)
        except ValueError:
            await query.edit_message_text("Invalid project ID.")
            return

        if not await services.user_service.is_admin(user_id):
            await query.edit_message_text("Only admins can start factory runs.")
            return

        project = await services.project_service.get_project(project_id)
        if not project:
            await query.edit_message_text("Project not found.")
            return

        runs_started = []
        errors = []
        for engine in (project.engines or [services._settings.default_engine]):
            try:
                run = await services.factory_runner.start_run(
                    project=project,
                    engine=engine,
                    created_by=user_id,
                )
                await services.run_monitor.attach(run)
                runs_started.append(f"{engine}: run #{run.id}")
                logger.info(
                    "factory_run_started_via_bot",
                    run_id=str(run.id),
                    engine=engine,
                    project=project.name,
                    user_id=user_id,
                )
            except Exception as e:
                logger.error("factory_run_start_failed", engine=engine, error=str(e))
                errors.append(f"{engine}: {e}")

        if runs_started:
            await services.project_service.update_status(project_id, "running")

        lines = [f"<b>Factory Run Started — {project.name}</b>\n"]
        for r in runs_started:
            lines.append(f"  Started: {r}")
        for err in errors:
            lines.append(f"  Failed: {err}")
        lines.append("\nUse /status to monitor progress.")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
        )
        return

    if data.startswith("stop:"):
        run_id_str = data.removeprefix("stop:")
        try:
            run_id = UUID(run_id_str)
        except ValueError:
            await query.edit_message_text("Invalid run ID.")
            return

        if not await services.user_service.is_admin(user_id):
            await query.edit_message_text("Only admins can stop runs.")
            return

        try:
            await services.factory_runner.stop_run(run_id)
            await query.edit_message_text(
                f"<b>Run stopped.</b>\n\nRun ID: <code>{run_id}</code>",
                parse_mode="HTML",
            )
            logger.info("factory_run_stopped_via_bot", run_id=str(run_id), user_id=user_id)
        except Exception as e:
            logger.error("factory_run_stop_failed", run_id=str(run_id), error=str(e))
            await query.edit_message_text(f"Failed to stop run: {e}")
        return

    logger.warning("factory_callback_unknown_action", data=data)
    await query.edit_message_text("Unknown action.")
