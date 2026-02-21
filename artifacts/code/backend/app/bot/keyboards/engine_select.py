"""Engine multi-select inline keyboard for project creation."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

ENGINES = {
    "claude": {"label": "Claude Code", "icon": "\U0001f916"},
    "gemini": {"label": "Gemini CLI", "icon": "\u2728"},
    "opencode": {"label": "OpenCode", "icon": "\U0001f4bb"},
    "aider": {"label": "Aider", "icon": "\U0001f527"},
}


def get_engine_select_keyboard(
    selected: list[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    Build engine multi-select keyboard.

    Selected engines show a checkmark. Unselected show an empty box.
    """
    if selected is None:
        selected = []

    buttons = []
    for engine_id, meta in ENGINES.items():
        check = "\u2705" if engine_id in selected else "\u2b1c"
        buttons.append([
            InlineKeyboardButton(
                f"{check} {meta['icon']} {meta['label']}",
                callback_data=f"engine_toggle:{engine_id}",
            )
        ])

    # Confirm button (only if at least one selected)
    buttons.append([
        InlineKeyboardButton(
            "\u2714\ufe0f Confirm Selection",
            callback_data="engine_confirm",
        )
    ])

    return InlineKeyboardMarkup(buttons)
