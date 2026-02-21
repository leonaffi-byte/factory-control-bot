"""Docker container management handlers."""

from __future__ import annotations

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer
from app.utils.formatting import truncate_message

logger = structlog.get_logger()

# Container state emoji
STATE_EMOJI = {
    "running": "\U0001f7e2",
    "exited": "\U0001f534",
    "paused": "\U0001f7e1",
    "restarting": "\U0001f7e0",
    "created": "\u26aa",
    "dead": "\u2b1b",
}


async def docker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /docker command — show container list."""
    await _show_container_list(update, context)


async def _show_container_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display list of Docker containers."""
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        containers = await services.docker_service.list_containers(all=True)
    except Exception as e:
        text = f"<b>Docker</b>\n\nFailed to connect to Docker: {e}"
        if update.callback_query and update.callback_query.message:
            await update.callback_query.edit_message_text(text)
        elif update.effective_message:
            await update.effective_message.reply_text(text)
        return

    if not containers:
        text = "<b>Docker Containers</b>\n\nNo containers found."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u00ab Back", callback_data="menu:back")],
        ])
    else:
        lines = ["<b>Docker Containers</b>\n"]
        buttons = []

        for c in containers:
            emoji = STATE_EMOJI.get(c.state, "\u2753")
            name = c.name.lstrip("/")
            cpu_str = f" | CPU: {c.cpu_percent:.1f}%" if c.cpu_percent is not None else ""
            mem_str = f" | RAM: {c.memory_mb:.0f}MB" if c.memory_mb is not None else ""
            lines.append(
                f"{emoji} <b>{name}</b>\n"
                f"   Image: <code>{c.image}</code>\n"
                f"   Status: {c.status}{cpu_str}{mem_str}"
            )
            buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {name}",
                    callback_data=f"docker:{c.id[:12]}",
                )
            ])

        buttons.append([InlineKeyboardButton("\U0001f504 Refresh", callback_data="docker:refresh")])
        buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="menu:back")])

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(buttons)

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(truncate_message(text), reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(truncate_message(text), reply_markup=keyboard)


async def docker_container_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle container selection and refresh callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("docker:")

    if data == "refresh":
        await _show_container_list(update, context)
        return

    # Container detail
    container_id = data
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        containers = await services.docker_service.list_containers(all=True)
        container = next(
            (c for c in containers if c.id.startswith(container_id)),
            None,
        )
    except Exception as e:
        await query.edit_message_text(f"Docker error: {e}")
        return

    if not container:
        await query.edit_message_text("Container not found.")
        return

    name = container.name.lstrip("/")
    emoji = STATE_EMOJI.get(container.state, "\u2753")
    ports_str = ", ".join(f"{k}->{v}" for k, v in container.ports.items()) if container.ports else "none"

    text = (
        f"{emoji} <b>Container: {name}</b>\n\n"
        f"ID: <code>{container.id[:12]}</code>\n"
        f"Image: <code>{container.image}</code>\n"
        f"State: {container.state}\n"
        f"Status: {container.status}\n"
        f"Ports: {ports_str}\n"
        f"Created: {container.created.strftime('%Y-%m-%d %H:%M')}\n"
    )

    if container.cpu_percent is not None:
        text += f"CPU: {container.cpu_percent:.1f}%\n"
    if container.memory_mb is not None:
        text += f"Memory: {container.memory_mb:.0f}MB\n"

    # Action buttons based on state
    buttons = []
    if container.state == "running":
        buttons.append([
            InlineKeyboardButton("\u23f9 Stop", callback_data=f"dock_action:stop:{container_id}"),
            InlineKeyboardButton("\U0001f504 Restart", callback_data=f"dock_action:restart:{container_id}"),
        ])
    elif container.state in ("exited", "created"):
        buttons.append([
            InlineKeyboardButton("\u25b6 Start", callback_data=f"dock_action:start:{container_id}"),
            InlineKeyboardButton("\U0001f5d1 Remove", callback_data=f"dock_action:remove:{container_id}"),
        ])

    buttons.append([
        InlineKeyboardButton("\U0001f4dc Logs", callback_data=f"dock_action:logs:{container_id}"),
    ])
    buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="docker:refresh")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def docker_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle container action callbacks (start, stop, restart, remove, logs)."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data.removeprefix("dock_action:")
    parts = data.split(":", 1)
    if len(parts) < 2:
        await query.answer("Invalid action.")
        return

    action, container_id = parts
    services: ServiceContainer = context.application.bot_data["services"]

    # Check admin for destructive actions
    user_id = update.effective_user.id if update.effective_user else 0
    is_admin = await services.user_service.is_admin(user_id)

    if action in ("stop", "restart", "remove") and not is_admin:
        await query.answer("Admin only action.", show_alert=True)
        return

    await query.answer(f"Performing {action}...")

    try:
        if action == "start":
            await services.docker_service.start_container(container_id)
            await query.edit_message_text(f"Container <code>{container_id}</code> started.")

        elif action == "stop":
            await services.docker_service.stop_container(container_id)
            await query.edit_message_text(f"Container <code>{container_id}</code> stopped.")

        elif action == "restart":
            await services.docker_service.restart_container(container_id)
            await query.edit_message_text(f"Container <code>{container_id}</code> restarted.")

        elif action == "remove":
            await services.docker_service.remove_container(container_id, force=True)
            await query.edit_message_text(f"Container <code>{container_id}</code> removed.")

        elif action == "logs":
            logs = await services.docker_service.get_logs(container_id, tail=50)
            text = (
                f"<b>Container Logs</b> (<code>{container_id}</code>)\n\n"
                f"<pre>{truncate_message(logs, max_len=3500)}</pre>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Refresh Logs", callback_data=f"dock_action:logs:{container_id}")],
                [InlineKeyboardButton("\u00ab Back", callback_data=f"docker:{container_id}")],
            ])
            await query.edit_message_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error("docker_action_failed", action=action, container=container_id, error=str(e))
        await query.edit_message_text(
            f"Failed to {action} container: {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u00ab Back", callback_data="docker:refresh")],
            ]),
        )
