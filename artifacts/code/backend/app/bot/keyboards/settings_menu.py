"""Settings menu inline keyboard."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Build the settings menu inline keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f504 Routing Mode", callback_data="settings:routing"),
            InlineKeyboardButton("\U0001f511 API Keys", callback_data="settings:keys"),
        ],
        [
            InlineKeyboardButton("\u2699\ufe0f Quality Gate", callback_data="settings:gate"),
            InlineKeyboardButton("\U0001f4be Backup", callback_data="settings:backup"),
        ],
        [
            InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="menu:back"),
        ],
    ])


def get_routing_mode_keyboard(current_mode: str = "api_direct") -> InlineKeyboardMarkup:
    """
    Build the routing mode selection keyboard.

    Args:
        current_mode: Currently active routing mode string.

    Returns:
        Inline keyboard with routing options.
    """
    MODES = [
        ("api_direct", "Direct API"),
        ("openrouter", "OpenRouter"),
        ("clink", "Clink Proxy"),
    ]

    buttons = []
    for mode_key, mode_label in MODES:
        tick = "\u2713 " if mode_key == current_mode else ""
        buttons.append([
            InlineKeyboardButton(
                f"{tick}{mode_label}",
                callback_data=f"settings:set:default_routing_mode:{mode_key}",
            )
        ])
    buttons.append([InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(buttons)


def get_quality_gate_keyboard() -> InlineKeyboardMarkup:
    """Build the quality gate configuration keyboard with preset thresholds."""
    presets = [
        ("90", "Relaxed (90)"),
        ("95", "Standard (95)"),
        ("97", "Strict (97)"),
        ("99", "Very Strict (99)"),
        ("100", "Perfect (100)"),
    ]

    buttons = []
    row: list[InlineKeyboardButton] = []
    for value, label in presets:
        row.append(
            InlineKeyboardButton(
                label,
                callback_data=f"settings:set:quality_gate_threshold:{value}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(buttons)
