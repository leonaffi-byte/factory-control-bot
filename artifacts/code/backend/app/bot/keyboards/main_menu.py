"""Main menu inline keyboard."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the main menu inline keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f195 New Project", callback_data="menu:new_project"),
            InlineKeyboardButton("\U0001f4c1 Projects", callback_data="menu:projects"),
        ],
        [
            InlineKeyboardButton("\U0001f4ca Analytics", callback_data="menu:analytics"),
            InlineKeyboardButton("\U0001f433 Docker", callback_data="menu:docker"),
        ],
        [
            InlineKeyboardButton("\U0001f5a5 System", callback_data="menu:system"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton("\u2753 Help", callback_data="menu:help"),
        ],
    ])
