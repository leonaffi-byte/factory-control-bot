"""Help handler — command reference and usage guide."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


HELP_TEXT = """<b>Factory Control Bot — Help</b>

<b>Commands:</b>

<b>Project Management:</b>
/new — Start the project creation wizard
/projects — List all projects with status
/cancel — Cancel current wizard

<b>Monitoring:</b>
/docker — View and manage Docker containers
/system — System health (CPU, RAM, disk, services)

<b>Analytics:</b>
/analytics — Cost breakdowns, quality metrics, engine comparisons

<b>Configuration:</b>
/settings — View and edit global settings
/admin — User whitelist management (admin only)

<b>General:</b>
/menu — Show main menu
/help — This help message

<b>Project Creation Flow:</b>
1. Select AI engines (Claude, Gemini, OpenCode, Aider)
2. Enter project name
3. Describe the project (text or voice)
4. Provide detailed requirements (voice or text, multiple segments)
5. Review AI-structured requirements
6. Configure settings (or use defaults)
7. Set up deployment options
8. Confirm and launch

<b>Voice Input:</b>
Send voice messages during requirements gathering.
The bot transcribes (via Groq/OpenAI Whisper), translates if needed,
and structures your input into formal requirements.

<b>Factory Monitoring:</b>
Once a factory run starts, you'll receive notifications for:
- Phase transitions (start/end with quality scores)
- Clarification questions (answer inline)
- Errors (with retry/stop options)
- Completion summary (cost, quality, test results)

<b>Docker Management:</b>
View all containers, start/stop/restart, view logs.
Admin-only: stop, restart, remove containers.

<b>System Monitoring:</b>
CPU, RAM, disk usage with visual bars.
Service status for: docker, nginx, postgresql, tailscaled, fail2ban.
Admin-only: restart services.
"""


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await _show_help(update, context)


async def _show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help text."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u00ab Back to Menu", callback_data="menu:back")],
    ])

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(HELP_TEXT, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(HELP_TEXT, reply_markup=keyboard)
