"""Scan results inline keyboard."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_scan_results_keyboard(has_suggestion: bool = True) -> InlineKeyboardMarkup:
    """
    Build the inline keyboard shown after a model scan.

    Args:
        has_suggestion: Whether a routing suggestion is present.
                        If True, an "Accept Suggestion" button is shown.

    Returns:
        InlineKeyboardMarkup with scan result action buttons.
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if has_suggestion:
        buttons.append([
            InlineKeyboardButton(
                "\u2705 Accept Suggestion",
                callback_data="scan:accept",
            ),
        ])

    buttons.append([
        InlineKeyboardButton("\U0001f504 Refresh", callback_data="scan:refresh"),
        InlineKeyboardButton("\U0001f4cb Details", callback_data="scan:details"),
    ])

    buttons.append([
        InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="menu:back"),
    ])

    return InlineKeyboardMarkup(buttons)
