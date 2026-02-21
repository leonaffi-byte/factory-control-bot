"""Admin handlers — user management (whitelist add/remove)."""

from __future__ import annotations

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer

logger = structlog.get_logger()


async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command — show admin menu. Admin only."""
    if not update.effective_message or not update.effective_user:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text("This command is for admins only.")
        return

    await _show_admin_menu(update, context)


async def _show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display admin menu."""
    services: ServiceContainer = context.application.bot_data["services"]
    users = await services.user_service.list_users()

    text = "<b>Admin Panel</b>\n\n<b>Whitelisted Users:</b>\n"
    for u in users:
        role_badge = "\U0001f451" if u.role == "admin" else "\U0001f464"
        name = u.display_name or str(u.telegram_id)
        text += f"  {role_badge} <code>{u.telegram_id}</code> — {name} ({u.role})\n"

    text += f"\nTotal: {len(users)} users"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2795 Add User", callback_data="admin:add")],
        [InlineKeyboardButton("\u2796 Remove User", callback_data="admin:remove_select")],
        [InlineKeyboardButton("\U0001f504 Refresh", callback_data="admin:refresh")],
        [InlineKeyboardButton("\u00ab Back", callback_data="menu:back")],
    ])

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin callback queries."""
    query = update.callback_query
    if not query or not query.data:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await query.answer("Admin only.", show_alert=True)
        return

    await query.answer()
    data = query.data.removeprefix("admin:")

    if data == "add":
        # Prompt user to send a Telegram ID
        if context.user_data is not None:
            context.user_data["awaiting_admin_action"] = "add_user"
        await query.edit_message_text(
            "<b>Add User</b>\n\n"
            "Send the Telegram user ID to add to the whitelist.\n"
            "Format: <code>telegram_id display_name</code>\n"
            "Example: <code>123456789 John</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="admin:refresh")],
            ]),
        )

    elif data == "remove_select":
        users = await services.user_service.list_users()
        # Filter out admin users (can't remove admin via this flow)
        removable = [u for u in users if u.role != "admin"]

        if not removable:
            await query.edit_message_text(
                "No non-admin users to remove.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u00ab Back", callback_data="admin:refresh")],
                ]),
            )
            return

        buttons = []
        for u in removable:
            name = u.display_name or str(u.telegram_id)
            buttons.append([
                InlineKeyboardButton(
                    f"\u274c {name} ({u.telegram_id})",
                    callback_data=f"admin:remove:{u.telegram_id}",
                )
            ])
        buttons.append([InlineKeyboardButton("Cancel", callback_data="admin:refresh")])

        await query.edit_message_text(
            "<b>Remove User</b>\n\nSelect user to remove:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("remove:"):
        telegram_id_str = data.removeprefix("remove:")
        try:
            target_id = int(telegram_id_str)
        except ValueError:
            return

        # Confirm removal
        if context.user_data is not None:
            confirmed = context.user_data.pop("confirm_remove", None)
            if confirmed == target_id:
                success = await services.user_service.remove_user(target_id)
                if success:
                    logger.info("user_removed", removed_id=target_id, by=user_id)
                    await query.edit_message_text(
                        f"User <code>{target_id}</code> removed from whitelist.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("\u00ab Back", callback_data="admin:refresh")],
                        ]),
                    )
                else:
                    await query.edit_message_text("Failed to remove user.")
                return

            context.user_data["confirm_remove"] = target_id

        await query.edit_message_text(
            f"Are you sure you want to remove user <code>{target_id}</code>?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "\u2705 Yes, Remove",
                        callback_data=f"admin:remove:{target_id}",
                    ),
                    InlineKeyboardButton("Cancel", callback_data="admin:refresh"),
                ],
            ]),
        )

    elif data == "refresh":
        await _show_admin_menu(update, context)
