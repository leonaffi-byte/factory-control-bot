"""Project action inline keyboards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from app.models.project import Project


def get_project_actions_keyboard(project: "Project") -> InlineKeyboardMarkup:
    """Build action keyboard based on project status."""
    buttons = []

    status = project.status

    if status in ("draft", "completed", "failed"):
        buttons.append([
            InlineKeyboardButton(
                "\u25b6 Start Factory",
                callback_data=f"proj_action:start:{project.id}",
            ),
        ])

    if status == "running":
        buttons.append([
            InlineKeyboardButton(
                "\u23f8 Pause",
                callback_data=f"proj_action:pause:{project.id}",
            ),
            InlineKeyboardButton(
                "\u23f9 Stop",
                callback_data=f"proj_action:stop:{project.id}",
            ),
        ])

    if status == "paused":
        buttons.append([
            InlineKeyboardButton(
                "\u25b6 Resume",
                callback_data=f"proj_action:start:{project.id}",
            ),
            InlineKeyboardButton(
                "\u23f9 Stop",
                callback_data=f"proj_action:stop:{project.id}",
            ),
        ])

    # Always available actions
    buttons.append([
        InlineKeyboardButton(
            "\U0001f4dc Runs",
            callback_data=f"proj_action:runs:{project.id}",
        ),
        InlineKeyboardButton(
            "\U0001f4ca Analytics",
            callback_data=f"analytics:project:{project.id}",
        ),
    ])

    if status in ("draft", "completed", "failed"):
        buttons.append([
            InlineKeyboardButton(
                "\U0001f5d1 Delete",
                callback_data=f"proj_action:delete:{project.id}",
            ),
        ])

    buttons.append([
        InlineKeyboardButton("\u00ab Back to Projects", callback_data="menu:projects"),
    ])

    return InlineKeyboardMarkup(buttons)
