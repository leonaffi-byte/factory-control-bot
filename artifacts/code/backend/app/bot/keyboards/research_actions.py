"""Research actions inline keyboard."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_research_actions_keyboard(suggestion_count: int = 0) -> InlineKeyboardMarkup:
    """
    Build the inline keyboard shown after a self-research run.

    Args:
        suggestion_count: Number of suggestions in the report.
                          Used to label the "Apply All" button accurately.

    Returns:
        InlineKeyboardMarkup with research action buttons.
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if suggestion_count > 0:
        apply_label = (
            f"\U0001f7e2 Apply All Low Risk"
            if suggestion_count > 1
            else "\U0001f7e2 Apply Low Risk"
        )
        buttons.append([
            InlineKeyboardButton(apply_label, callback_data="research:apply_all"),
        ])
        buttons.append([
            InlineKeyboardButton(
                f"\U0001f4cb Review Individual ({suggestion_count})",
                callback_data="research:review",
            ),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("\U0001f504 Re-run Research", callback_data="research:rerun"),
        ])

    buttons.append([
        InlineKeyboardButton("\u274c Dismiss All", callback_data="research:dismiss"),
        InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="menu:back"),
    ])

    return InlineKeyboardMarkup(buttons)
