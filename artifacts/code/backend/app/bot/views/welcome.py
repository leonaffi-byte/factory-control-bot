"""Welcome view — onboarding and welcome screen content."""

from __future__ import annotations

from app.bot.views.base import TelegramView

WELCOME_TEXT = (
    "<b>Black Box Software Factory v2</b>\n\n"
    "Welcome to the Factory Control Bot.\n\n"
    "This bot manages your multi-model software factory pipeline:\n"
    "  \u2022 Launch factory runs across Claude, Gemini, GPT and more\n"
    "  \u2022 Monitor real-time progress through all 7 phases\n"
    "  \u2022 Scan and route to the best available AI models\n"
    "  \u2022 Backup and restore your factory projects\n"
    "  \u2022 View health reports and cost tracking\n\n"
    "Use the menu below or type a command to get started."
)

HELP_TEXT = (
    "<b>Available Commands</b>\n\n"
    "<b>Factory</b>\n"
    "  /run \u2014 Start a factory run\n"
    "  /stop \u2014 Stop a running factory\n"
    "  /status \u2014 Show current run status\n\n"
    "<b>Models</b>\n"
    "  /scan \u2014 Scan and grade available models\n"
    "  /providers \u2014 Show provider status table\n"
    "  /research \u2014 Run self-research for optimisations\n\n"
    "<b>Infrastructure</b>\n"
    "  /health \u2014 System health report\n"
    "  /backup \u2014 Create a backup\n"
    "  /restore \u2014 Restore from backup\n\n"
    "<b>Projects</b>\n"
    "  /new \u2014 Create a new project\n"
    "  /projects \u2014 List all projects\n"
    "  /settings \u2014 Manage settings\n\n"
    "<b>Other</b>\n"
    "  /start \u2014 Show main menu\n"
    "  /help \u2014 Show this message\n"
)

ONBOARDING_STEPS = [
    (
        "<b>Step 1: Configure API Keys</b>\n\n"
        "Go to /settings to add your AI provider API keys.\n"
        "At minimum you need:\n"
        "  \u2022 TELEGRAM_BOT_TOKEN (already set)\n"
        "  \u2022 At least one engine API key (Claude, Gemini, etc.)"
    ),
    (
        "<b>Step 2: Scan Available Models</b>\n\n"
        "Run /scan to discover which providers and models are available.\n"
        "The bot will suggest the optimal routing mode."
    ),
    (
        "<b>Step 3: Create Your First Project</b>\n\n"
        "Use /new to start the project creation wizard.\n"
        "Provide your requirements and select engines to use."
    ),
    (
        "<b>Step 4: Start the Factory</b>\n\n"
        "Use /run to kick off the 7-phase pipeline.\n"
        "You\u2019ll receive notifications as each phase completes."
    ),
]


def format_welcome(is_new_user: bool = False) -> str:
    """Return the appropriate welcome message."""
    if is_new_user:
        return (
            WELCOME_TEXT
            + "\n\n<i>First time here? Use /help to see all commands, "
            "or tap the buttons below to get started.</i>"
        )
    return WELCOME_TEXT


def format_onboarding_step(step: int) -> str:
    """
    Return the message for the given onboarding step (0-indexed).

    Returns empty string if step is out of range.
    """
    if 0 <= step < len(ONBOARDING_STEPS):
        view = TelegramView()
        progress = view.progress_bar(step + 1, len(ONBOARDING_STEPS))
        return (
            ONBOARDING_STEPS[step]
            + f"\n\n<code>{progress}</code>"
        )
    return ""


def format_help() -> str:
    """Return the help message."""
    return HELP_TEXT
