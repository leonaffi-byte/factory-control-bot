"""Backup and restore handlers — /backup, /restore."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


async def backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /backup command — create a backup."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text(
            "Only admins can create backups."
        )
        return

    await update.effective_message.reply_text(
        "<b>Backup</b>\n\nWhat would you like to back up?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Database", callback_data="backup:db"),
                InlineKeyboardButton("Projects", callback_data="backup:projects"),
            ],
            [InlineKeyboardButton("Full Backup", callback_data="backup:full")],
            [InlineKeyboardButton("Cancel", callback_data="backup:cancel")],
        ]),
    )


async def restore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restore command — restore from backup."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text(
            "Only admins can restore backups."
        )
        return

    try:
        backups = await services.backup_service.list_backups()
    except Exception as e:
        logger.error("backup_list_failed", error=str(e), user_id=user_id)
        await update.effective_message.reply_text(
            f"<b>Failed to list backups:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
        return

    if not backups:
        await update.effective_message.reply_text(
            "<b>No backups found.</b>\n\nCreate one with /backup.",
            parse_mode="HTML",
        )
        return

    buttons = []
    for bk in backups[:10]:
        bk_id = getattr(bk, "id", str(bk))
        bk_name = getattr(bk, "name", bk_id)
        bk_size = getattr(bk, "size_human", "")
        bk_date = getattr(bk, "created_at_human", "")
        label = f"{bk_name}"
        if bk_date:
            label += f" ({bk_date})"
        if bk_size:
            label += f" [{bk_size}]"
        buttons.append([
            InlineKeyboardButton(
                label[:60],
                callback_data=f"backup:restore_confirm:{bk_id}",
            )
        ])
    buttons.append([InlineKeyboardButton("Cancel", callback_data="backup:cancel")])

    await update.effective_message.reply_text(
        "<b>Restore from Backup</b>\n\nSelect a backup to restore:\n\n"
        "<i>Warning: This will overwrite current data.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle backup:* inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("backup:")

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await query.edit_message_text("Only admins can manage backups.")
        return

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return

    if data == "db":
        await query.edit_message_text(
            "<b>Backup</b>\n\nBacking up database...",
            parse_mode="HTML",
        )
        try:
            result = await services.backup_service.backup_database()
            path = getattr(result, "path", str(result))
            size = getattr(result, "size_human", "")
            await query.edit_message_text(
                f"<b>Database backup complete.</b>\n\n"
                f"Path: <code>{path}</code>\n"
                f"Size: {size}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("List Backups", callback_data="backup:list")],
                ]),
            )
            logger.info("database_backup_created", user_id=user_id, path=path)
        except Exception as e:
            logger.error("database_backup_failed", error=str(e), user_id=user_id)
            await query.edit_message_text(f"Backup failed: {e}")
        return

    if data == "projects":
        await query.edit_message_text(
            "<b>Backup</b>\n\nBacking up projects...",
            parse_mode="HTML",
        )
        try:
            result = await services.backup_service.backup_projects()
            path = getattr(result, "path", str(result))
            size = getattr(result, "size_human", "")
            await query.edit_message_text(
                f"<b>Projects backup complete.</b>\n\n"
                f"Path: <code>{path}</code>\n"
                f"Size: {size}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("List Backups", callback_data="backup:list")],
                ]),
            )
            logger.info("projects_backup_created", user_id=user_id, path=path)
        except Exception as e:
            logger.error("projects_backup_failed", error=str(e), user_id=user_id)
            await query.edit_message_text(f"Backup failed: {e}")
        return

    if data == "full":
        await query.edit_message_text(
            "<b>Backup</b>\n\nCreating full backup (database + projects)...",
            parse_mode="HTML",
        )
        try:
            result = await services.backup_service.backup_full()
            path = getattr(result, "path", str(result))
            size = getattr(result, "size_human", "")
            await query.edit_message_text(
                f"<b>Full backup complete.</b>\n\n"
                f"Path: <code>{path}</code>\n"
                f"Size: {size}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("List Backups", callback_data="backup:list")],
                ]),
            )
            logger.info("full_backup_created", user_id=user_id, path=path)
        except Exception as e:
            logger.error("full_backup_failed", error=str(e), user_id=user_id)
            await query.edit_message_text(f"Backup failed: {e}")
        return

    if data == "list":
        try:
            backups = await services.backup_service.list_backups()
            if not backups:
                await query.edit_message_text(
                    "<b>No backups found.</b>",
                    parse_mode="HTML",
                )
                return

            lines = ["<b>Available Backups</b>\n"]
            for bk in backups[:10]:
                bk_name = getattr(bk, "name", str(bk))
                bk_date = getattr(bk, "created_at_human", "")
                bk_size = getattr(bk, "size_human", "")
                bk_type = getattr(bk, "type", "unknown")
                lines.append(
                    f"• <b>{bk_name}</b> [{bk_type}]\n"
                    f"  {bk_date} — {bk_size}"
                )

            await query.edit_message_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("New Backup", callback_data="backup:new"),
                        InlineKeyboardButton("Restore", callback_data="backup:restore_menu"),
                    ],
                ]),
            )
        except Exception as e:
            logger.error("backup_list_display_failed", error=str(e))
            await query.edit_message_text(f"Failed to list backups: {e}")
        return

    if data == "new":
        await query.edit_message_text(
            "<b>Backup</b>\n\nWhat would you like to back up?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Database", callback_data="backup:db"),
                    InlineKeyboardButton("Projects", callback_data="backup:projects"),
                ],
                [InlineKeyboardButton("Full Backup", callback_data="backup:full")],
                [InlineKeyboardButton("Cancel", callback_data="backup:cancel")],
            ]),
        )
        return

    if data == "restore_menu":
        try:
            backups = await services.backup_service.list_backups()
            if not backups:
                await query.edit_message_text(
                    "<b>No backups to restore from.</b>",
                    parse_mode="HTML",
                )
                return

            buttons = []
            for bk in backups[:10]:
                bk_id = getattr(bk, "id", str(bk))
                bk_name = getattr(bk, "name", bk_id)
                bk_date = getattr(bk, "created_at_human", "")
                label = f"{bk_name}"
                if bk_date:
                    label += f" ({bk_date})"
                buttons.append([
                    InlineKeyboardButton(
                        label[:60],
                        callback_data=f"backup:restore_confirm:{bk_id}",
                    )
                ])
            buttons.append([InlineKeyboardButton("Cancel", callback_data="backup:cancel")])

            await query.edit_message_text(
                "<b>Restore from Backup</b>\n\nSelect a backup:\n\n"
                "<i>Warning: This will overwrite current data.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception as e:
            logger.error("restore_menu_failed", error=str(e))
            await query.edit_message_text(f"Failed to load backups: {e}")
        return

    if data.startswith("restore_confirm:"):
        bk_id = data.removeprefix("restore_confirm:")
        await query.edit_message_text(
            f"<b>Confirm Restore</b>\n\n"
            f"Backup ID: <code>{bk_id}</code>\n\n"
            f"<i>This will overwrite current data. Are you sure?</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "Yes, Restore",
                        callback_data=f"backup:restore_exec:{bk_id}",
                    ),
                    InlineKeyboardButton("Cancel", callback_data="backup:cancel"),
                ]
            ]),
        )
        return

    if data.startswith("restore_exec:"):
        bk_id = data.removeprefix("restore_exec:")
        await query.edit_message_text(
            "<b>Restoring...</b>\n\nThis may take a moment.",
            parse_mode="HTML",
        )
        try:
            await services.backup_service.restore(bk_id)
            await query.edit_message_text(
                f"<b>Restore complete.</b>\n\nBackup <code>{bk_id}</code> has been restored.",
                parse_mode="HTML",
            )
            logger.info("backup_restored", user_id=user_id, backup_id=bk_id)
        except Exception as e:
            logger.error("backup_restore_failed", error=str(e), backup_id=bk_id)
            await query.edit_message_text(f"Restore failed: {e}")
        return

    logger.warning("backup_callback_unknown_action", data=data)
    await query.edit_message_text("Unknown action.")
