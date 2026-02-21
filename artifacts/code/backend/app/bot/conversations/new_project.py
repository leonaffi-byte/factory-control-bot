"""Project creation ConversationHandler — complete 13-state wizard."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.keyboards.engine_select import get_engine_select_keyboard
from app.services import ServiceContainer
from app.utils.validators import validate_project_name
from app.utils.formatting import truncate_message

logger = structlog.get_logger()

# Conversation states
(
    ENGINE_SELECT,
    NAME_INPUT,
    DESC_INPUT,
    REQ_GATHERING,
    REQ_TRANSLATING,
    REQ_REVIEW,
    SETTINGS_CHOICE,
    SETTINGS_MENU,
    DEPLOY_CHOICE,
    PROJECT_TYPE,
    DEPLOY_TARGET,
    ACCESS_CONFIG,
    CONFIRM_LAUNCH,
) = range(13)

# Engine list
ENGINES = ["claude", "gemini", "opencode", "aider"]


def get_new_project_conversation() -> ConversationHandler:
    """Build and return the project creation ConversationHandler."""
    return ConversationHandler(
        entry_points=[CommandHandler("new", new_command)],
        states={
            ENGINE_SELECT: [
                CallbackQueryHandler(engine_toggle, pattern=r"^engine_toggle:"),
                CallbackQueryHandler(engine_confirm, pattern=r"^engine_confirm$"),
            ],
            NAME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, name_input),
            ],
            DESC_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, desc_text_input),
                MessageHandler(filters.VOICE, desc_voice_input),
            ],
            REQ_GATHERING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, req_text_input),
                MessageHandler(filters.VOICE, req_voice_input),
                CallbackQueryHandler(req_done, pattern=r"^req:done$"),
                CallbackQueryHandler(req_delete_last, pattern=r"^req:delete_last$"),
                CallbackQueryHandler(req_edit, pattern=r"^req:edit$"),
            ],
            REQ_TRANSLATING: [
                # Auto-transition — no user input expected
            ],
            REQ_REVIEW: [
                CallbackQueryHandler(req_approve, pattern=r"^req_review:approve$"),
                CallbackQueryHandler(req_regenerate, pattern=r"^req_review:regenerate$"),
                CallbackQueryHandler(req_edit_review, pattern=r"^req_review:edit$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, req_edit_text),
            ],
            SETTINGS_CHOICE: [
                CallbackQueryHandler(settings_defaults, pattern=r"^settings:defaults$"),
                CallbackQueryHandler(settings_customize, pattern=r"^settings:customize$"),
            ],
            SETTINGS_MENU: [
                CallbackQueryHandler(settings_set, pattern=r"^psetting:"),
                CallbackQueryHandler(settings_done, pattern=r"^psettings:done$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_text_input),
            ],
            DEPLOY_CHOICE: [
                CallbackQueryHandler(deploy_yes, pattern=r"^deploy:yes$"),
                CallbackQueryHandler(deploy_no, pattern=r"^deploy:no$"),
            ],
            PROJECT_TYPE: [
                CallbackQueryHandler(project_type_select, pattern=r"^ptype:"),
            ],
            DEPLOY_TARGET: [
                CallbackQueryHandler(deploy_target_select, pattern=r"^dtarget:"),
            ],
            ACCESS_CONFIG: [
                CallbackQueryHandler(access_config_select, pattern=r"^access:"),
            ],
            CONFIRM_LAUNCH: [
                CallbackQueryHandler(confirm_launch, pattern=r"^launch:confirm$"),
                CallbackQueryHandler(confirm_cancel, pattern=r"^launch:cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        name="new_project",
        persistent=True,
        per_message=False,
    )


def _init_wizard_data(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    """Initialize wizard data in user_data."""
    wizard: dict[str, Any] = {
        "engines": [],
        "name": "",
        "description": "",
        "voice_segments": [],
        "requirements_raw": "",
        "requirements_structured": "",
        "settings": {},
        "deploy_config": {},
        "name_attempts": 0,
    }
    if context.user_data is not None:
        context.user_data["wizard"] = wizard
    return wizard


def _get_wizard(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    """Get wizard data from user_data."""
    if context.user_data is None:
        return {}
    return context.user_data.get("wizard", {})


# ────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /new — start project creation wizard."""
    if not update.effective_message:
        return ConversationHandler.END

    services: ServiceContainer = context.application.bot_data["services"]

    # Check disk space
    disk_critical = await services.settings_service.get("disk_critical", False)
    if disk_critical:
        await update.effective_message.reply_text(
            "Cannot create new projects: disk usage is critically high (>90%). "
            "Free up space and try again."
        )
        return ConversationHandler.END

    _init_wizard_data(context)

    keyboard = get_engine_select_keyboard(selected=[])
    await update.effective_message.reply_text(
        "<b>New Project — Step 1/7</b>\n\n"
        "Select the AI engines to use.\n"
        "You can select multiple engines for parallel runs.\n"
        "Tap an engine to toggle, then press Confirm.",
        reply_markup=keyboard,
    )
    return ENGINE_SELECT


# ────────────────────────────────────────────
# ENGINE_SELECT state
# ────────────────────────────────────────────

async def engine_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle engine selection."""
    query = update.callback_query
    if not query or not query.data:
        return ENGINE_SELECT

    await query.answer()
    engine = query.data.removeprefix("engine_toggle:")
    wizard = _get_wizard(context)

    if engine in wizard.get("engines", []):
        wizard["engines"].remove(engine)
    else:
        wizard.setdefault("engines", []).append(engine)

    keyboard = get_engine_select_keyboard(selected=wizard.get("engines", []))
    await query.edit_message_text(
        "<b>New Project — Step 1/7</b>\n\n"
        "Select the AI engines to use.\n"
        f"Selected: {', '.join(wizard.get('engines', [])) or 'none'}\n\n"
        "Tap an engine to toggle, then press Confirm.",
        reply_markup=keyboard,
    )
    return ENGINE_SELECT


async def engine_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm engine selection and move to name input."""
    query = update.callback_query
    if not query:
        return ENGINE_SELECT

    wizard = _get_wizard(context)
    engines = wizard.get("engines", [])

    if not engines:
        await query.answer("Select at least one engine!", show_alert=True)
        return ENGINE_SELECT

    await query.answer()
    await query.edit_message_text(
        "<b>New Project — Step 2/7</b>\n\n"
        f"Engines: {', '.join(engines)}\n\n"
        "Enter the project name.\n"
        "Rules: lowercase letters, numbers, hyphens.\n"
        "Must start with a letter, 3-50 characters.\n"
        "Example: <code>my-awesome-app</code>",
    )
    return NAME_INPUT


# ────────────────────────────────────────────
# NAME_INPUT state
# ────────────────────────────────────────────

async def name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and accept project name."""
    if not update.effective_message or not update.effective_message.text:
        return NAME_INPUT

    wizard = _get_wizard(context)
    name = update.effective_message.text.strip()

    # Validate
    is_valid, error = validate_project_name(name)
    if not is_valid:
        wizard["name_attempts"] = wizard.get("name_attempts", 0) + 1
        if wizard["name_attempts"] >= 3:
            await update.effective_message.reply_text(
                f"Invalid name: {error}\n\n"
                "Too many invalid attempts. Use /cancel to abort and start over."
            )
            return NAME_INPUT

        await update.effective_message.reply_text(
            f"Invalid name: {error}\n\nTry again:"
        )
        return NAME_INPUT

    # Check uniqueness
    services: ServiceContainer = context.application.bot_data["services"]
    existing = await services.project_service.get_project_by_name(name)
    if existing:
        await update.effective_message.reply_text(
            f"Project '{name}' already exists. Choose a different name:"
        )
        return NAME_INPUT

    wizard["name"] = name

    await update.effective_message.reply_text(
        "<b>New Project — Step 3/7</b>\n\n"
        f"Project: <b>{name}</b>\n\n"
        "Enter a brief project description.\n"
        "You can type text or send a voice message.",
    )
    return DESC_INPUT


# ────────────────────────────────────────────
# DESC_INPUT state
# ────────────────────────────────────────────

async def desc_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept text description."""
    if not update.effective_message or not update.effective_message.text:
        return DESC_INPUT

    wizard = _get_wizard(context)
    wizard["description"] = update.effective_message.text.strip()

    return await _transition_to_req_gathering(update, context)


async def desc_voice_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Transcribe voice description."""
    if not update.effective_message or not update.effective_message.voice:
        return DESC_INPUT

    services: ServiceContainer = context.application.bot_data["services"]
    wizard = _get_wizard(context)

    await update.effective_message.reply_text("Transcribing voice message...")

    try:
        voice = update.effective_message.voice
        voice_file = await voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        result = await services.transcription.transcribe(
            bytes(audio_bytes), f"voice_{update.update_id}.ogg"
        )
        wizard["description"] = result.text

        await update.effective_message.reply_text(
            f"Transcription ({result.provider}, {result.language}):\n\n"
            f"<i>{result.text}</i>"
        )
    except Exception as e:
        logger.error("desc_voice_transcription_failed", error=str(e))
        await update.effective_message.reply_text(
            f"Transcription failed: {e}\n\nPlease type your description instead."
        )
        return DESC_INPUT

    return await _transition_to_req_gathering(update, context)


async def _transition_to_req_gathering(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Transition to requirements gathering state."""
    wizard = _get_wizard(context)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Done", callback_data="req:done"),
            InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req:edit"),
        ],
        [InlineKeyboardButton("\U0001f5d1 Delete Last", callback_data="req:delete_last")],
    ])

    await update.effective_message.reply_text(
        "<b>New Project — Step 4/7</b>\n\n"
        f"Project: <b>{wizard['name']}</b>\n"
        f"Description: {wizard['description'][:100]}\n\n"
        "Now provide detailed requirements.\n"
        "Send voice messages or text — you can send multiple.\n"
        "Press Done when finished.",
        reply_markup=keyboard,
    )
    return REQ_GATHERING


# ────────────────────────────────────────────
# REQ_GATHERING state
# ────────────────────────────────────────────

async def req_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept text requirement segment."""
    if not update.effective_message or not update.effective_message.text:
        return REQ_GATHERING

    wizard = _get_wizard(context)
    text = update.effective_message.text.strip()

    # Sanitize factory markers
    from app.utils.validators import sanitize_user_input
    text = sanitize_user_input(text)

    wizard.setdefault("voice_segments", []).append(text)

    segment_count = len(wizard["voice_segments"])
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Done", callback_data="req:done"),
            InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req:edit"),
        ],
        [InlineKeyboardButton("\U0001f5d1 Delete Last", callback_data="req:delete_last")],
    ])

    await update.effective_message.reply_text(
        f"Segment {segment_count} added.\n"
        "Send more, or press Done.",
        reply_markup=keyboard,
    )
    return REQ_GATHERING


async def req_voice_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Transcribe voice requirement segment."""
    if not update.effective_message or not update.effective_message.voice:
        return REQ_GATHERING

    services: ServiceContainer = context.application.bot_data["services"]
    wizard = _get_wizard(context)

    await update.effective_message.reply_text("Transcribing...")

    try:
        voice = update.effective_message.voice
        voice_file = await voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        result = await services.transcription.transcribe(
            bytes(audio_bytes), f"voice_{update.update_id}.ogg"
        )

        wizard.setdefault("voice_segments", []).append(result.text)
        segment_count = len(wizard["voice_segments"])

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Done", callback_data="req:done"),
                InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req:edit"),
            ],
            [InlineKeyboardButton("\U0001f5d1 Delete Last", callback_data="req:delete_last")],
        ])

        await update.effective_message.reply_text(
            f"Segment {segment_count} ({result.provider}):\n"
            f"<i>{result.text}</i>\n\n"
            "Send more, or press Done.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error("req_voice_transcription_failed", error=str(e))
        await update.effective_message.reply_text(
            f"Transcription failed: {e}\nTry again or type your requirements."
        )

    return REQ_GATHERING


async def req_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Done button — process and structure requirements."""
    query = update.callback_query
    if not query:
        return REQ_GATHERING

    await query.answer()
    wizard = _get_wizard(context)
    segments = wizard.get("voice_segments", [])

    if not segments:
        await query.answer("No input received. Send voice or text first.", show_alert=True)
        return REQ_GATHERING

    # Concatenate all segments
    raw_text = "\n\n".join(segments)
    wizard["requirements_raw"] = raw_text

    await query.edit_message_text("Processing requirements...")

    # Translate and structure
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        # Step 1: Translate if needed
        translated = await services.translation.translate_to_english(raw_text)

        # Step 2: Structure into formal requirements
        structured = await services.translation.structure_requirements(translated)

        wizard["requirements_structured"] = structured

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Approve", callback_data="req_review:approve")],
            [InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req_review:edit")],
            [InlineKeyboardButton("\U0001f504 Regenerate", callback_data="req_review:regenerate")],
        ])

        await query.message.reply_text(
            "<b>New Project — Step 5/7: Review Requirements</b>\n\n"
            + truncate_message(structured, max_len=3500)
            + "\n\nApprove, edit, or regenerate.",
            reply_markup=keyboard,
        )
        return REQ_REVIEW

    except Exception as e:
        logger.error("requirements_processing_failed", error=str(e))
        await query.message.reply_text(
            f"Failed to process requirements: {e}\n\n"
            "Your raw input has been saved. Press Done to retry, "
            "or add more segments."
        )
        return REQ_GATHERING


async def req_delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete the last voice/text segment."""
    query = update.callback_query
    if not query:
        return REQ_GATHERING

    wizard = _get_wizard(context)
    segments = wizard.get("voice_segments", [])

    if segments:
        removed = segments.pop()
        await query.answer(f"Removed: {removed[:30]}...")
    else:
        await query.answer("No segments to delete.", show_alert=True)
        return REQ_GATHERING

    remaining = len(segments)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Done", callback_data="req:done"),
            InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req:edit"),
        ],
        [InlineKeyboardButton("\U0001f5d1 Delete Last", callback_data="req:delete_last")],
    ])

    await query.edit_message_text(
        f"Segment removed. {remaining} segments remaining.\n"
        "Send more, or press Done.",
        reply_markup=keyboard,
    )
    return REQ_GATHERING


async def req_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send current segments for editing."""
    query = update.callback_query
    if not query:
        return REQ_GATHERING

    await query.answer()
    wizard = _get_wizard(context)
    segments = wizard.get("voice_segments", [])

    if not segments:
        await query.answer("No segments to edit.", show_alert=True)
        return REQ_GATHERING

    text = "<b>Current segments:</b>\n\n"
    for i, seg in enumerate(segments, 1):
        text += f"<b>Segment {i}:</b>\n{seg}\n\n"

    text += "Reply with corrected text to replace all segments."

    await query.edit_message_text(truncate_message(text))
    # Next text message replaces all segments
    if context.user_data is not None:
        context.user_data["editing_segments"] = True
    return REQ_GATHERING


# ────────────────────────────────────────────
# REQ_REVIEW state
# ────────────────────────────────────────────

async def req_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Approve structured requirements."""
    query = update.callback_query
    if not query:
        return REQ_REVIEW

    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Start with Defaults", callback_data="settings:defaults")],
        [InlineKeyboardButton("Customize Settings", callback_data="settings:customize")],
    ])

    await query.edit_message_text(
        "<b>New Project — Step 6/7: Settings</b>\n\n"
        "Use default factory settings or customize for this project?",
        reply_markup=keyboard,
    )
    return SETTINGS_CHOICE


async def req_regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Regenerate structured requirements with AI."""
    query = update.callback_query
    if not query:
        return REQ_REVIEW

    await query.answer("Regenerating...")
    wizard = _get_wizard(context)
    raw_text = wizard.get("requirements_raw", "")

    services: ServiceContainer = context.application.bot_data["services"]

    try:
        translated = await services.translation.translate_to_english(raw_text)
        structured = await services.translation.structure_requirements(translated)
        wizard["requirements_structured"] = structured

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Approve", callback_data="req_review:approve")],
            [InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req_review:edit")],
            [InlineKeyboardButton("\U0001f504 Regenerate", callback_data="req_review:regenerate")],
        ])

        await query.edit_message_text(
            "<b>Regenerated Requirements</b>\n\n"
            + truncate_message(structured, max_len=3500)
            + "\n\nApprove, edit, or regenerate again.",
            reply_markup=keyboard,
        )
    except Exception as e:
        await query.edit_message_text(f"Regeneration failed: {e}")

    return REQ_REVIEW


async def req_edit_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enter edit mode for structured requirements."""
    query = update.callback_query
    if not query:
        return REQ_REVIEW

    await query.answer()
    wizard = _get_wizard(context)

    await query.message.reply_text(
        "Send your corrected requirements text.\n"
        "The full text you send will replace the current requirements."
    )

    if context.user_data is not None:
        context.user_data["editing_requirements"] = True

    return REQ_REVIEW


async def req_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept edited requirements text."""
    if not update.effective_message or not update.effective_message.text:
        return REQ_REVIEW

    wizard = _get_wizard(context)

    if context.user_data and context.user_data.pop("editing_requirements", False):
        wizard["requirements_structured"] = update.effective_message.text.strip()

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Approve", callback_data="req_review:approve")],
            [InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req_review:edit")],
            [InlineKeyboardButton("\U0001f504 Regenerate", callback_data="req_review:regenerate")],
        ])

        await update.effective_message.reply_text(
            "<b>Updated Requirements</b>\n\n"
            + truncate_message(wizard["requirements_structured"], max_len=3500),
            reply_markup=keyboard,
        )

    return REQ_REVIEW


# ────────────────────────────────────────────
# SETTINGS_CHOICE / SETTINGS_MENU states
# ────────────────────────────────────────────

async def settings_defaults(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Use default settings."""
    query = update.callback_query
    if not query:
        return SETTINGS_CHOICE

    await query.answer()
    wizard = _get_wizard(context)
    wizard["settings"] = {}  # Use global defaults

    return await _transition_to_deploy(update, context)


async def settings_customize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show per-project settings menu."""
    query = update.callback_query
    if not query:
        return SETTINGS_CHOICE

    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Tier Override (1/2/3)", callback_data="psetting:tier")],
        [InlineKeyboardButton("Quality Threshold", callback_data="psetting:quality")],
        [InlineKeyboardButton("Cost Limit", callback_data="psetting:cost_limit")],
        [InlineKeyboardButton("\u2705 Done with Settings", callback_data="psettings:done")],
    ])

    await query.edit_message_text(
        "<b>Per-Project Settings</b>\n\n"
        "Configure overrides for this project, then press Done.",
        reply_markup=keyboard,
    )
    return SETTINGS_MENU


async def settings_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle per-project setting selection."""
    query = update.callback_query
    if not query or not query.data:
        return SETTINGS_MENU

    await query.answer()
    setting = query.data.removeprefix("psetting:")

    prompts = {
        "tier": "Enter complexity tier (1, 2, or 3):",
        "quality": "Enter quality gate threshold (80-100):",
        "cost_limit": "Enter cost limit in dollars (e.g., 25.00):",
    }

    if context.user_data is not None:
        context.user_data["awaiting_psetting"] = setting

    await query.edit_message_text(prompts.get(setting, f"Enter value for {setting}:"))
    return SETTINGS_MENU


async def settings_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept text input for per-project setting."""
    if not update.effective_message or not update.effective_message.text:
        return SETTINGS_MENU

    wizard = _get_wizard(context)
    setting = context.user_data.pop("awaiting_psetting", None) if context.user_data else None

    if not setting:
        return SETTINGS_MENU

    value = update.effective_message.text.strip()

    try:
        if setting == "tier":
            tier = int(value)
            if tier not in (1, 2, 3):
                raise ValueError("Must be 1, 2, or 3")
            wizard.setdefault("settings", {})["tier_override"] = tier

        elif setting == "quality":
            threshold = int(value)
            if not 80 <= threshold <= 100:
                raise ValueError("Must be between 80 and 100")
            wizard.setdefault("settings", {})["quality_gate_threshold"] = threshold

        elif setting == "cost_limit":
            limit = float(value)
            if limit <= 0:
                raise ValueError("Must be positive")
            wizard.setdefault("settings", {})["cost_limit"] = limit

    except ValueError as e:
        await update.effective_message.reply_text(f"Invalid value: {e}")
        return SETTINGS_MENU

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Tier Override (1/2/3)", callback_data="psetting:tier")],
        [InlineKeyboardButton("Quality Threshold", callback_data="psetting:quality")],
        [InlineKeyboardButton("Cost Limit", callback_data="psetting:cost_limit")],
        [InlineKeyboardButton("\u2705 Done with Settings", callback_data="psettings:done")],
    ])

    settings_str = "\n".join(f"  {k}: {v}" for k, v in wizard.get("settings", {}).items())
    await update.effective_message.reply_text(
        f"<b>Settings updated:</b>\n{settings_str}\n\n"
        "Configure more or press Done.",
        reply_markup=keyboard,
    )
    return SETTINGS_MENU


async def settings_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Done configuring per-project settings."""
    query = update.callback_query
    if not query:
        return SETTINGS_MENU

    await query.answer()
    return await _transition_to_deploy(update, context)


# ────────────────────────────────────────────
# DEPLOY_CHOICE / PROJECT_TYPE / DEPLOY_TARGET / ACCESS_CONFIG
# ────────────────────────────────────────────

async def _transition_to_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Transition to deployment configuration."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Yes, auto-deploy", callback_data="deploy:yes"),
            InlineKeyboardButton("\u274c No", callback_data="deploy:no"),
        ],
    ])

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(
            "<b>New Project — Step 7/7: Deployment</b>\n\n"
            "Auto-deploy when factory completes?",
            reply_markup=keyboard,
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            "<b>New Project — Step 7/7: Deployment</b>\n\n"
            "Auto-deploy when factory completes?",
            reply_markup=keyboard,
        )

    return DEPLOY_CHOICE


async def deploy_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User wants auto-deploy — ask project type."""
    query = update.callback_query
    if not query:
        return DEPLOY_CHOICE

    await query.answer()
    wizard = _get_wizard(context)
    wizard.setdefault("deploy_config", {})["auto_deploy"] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Telegram Bot", callback_data="ptype:telegram_bot")],
        [InlineKeyboardButton("Web App", callback_data="ptype:web_app")],
        [InlineKeyboardButton("API Service", callback_data="ptype:api_service")],
        [InlineKeyboardButton("Other", callback_data="ptype:other")],
    ])

    await query.edit_message_text(
        "<b>Project Type</b>\n\nWhat type of project is this?",
        reply_markup=keyboard,
    )
    return PROJECT_TYPE


async def deploy_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip deploy config."""
    query = update.callback_query
    if not query:
        return DEPLOY_CHOICE

    await query.answer()
    wizard = _get_wizard(context)
    wizard.setdefault("deploy_config", {})["auto_deploy"] = False

    return await _show_confirmation(update, context)


async def project_type_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select project type."""
    query = update.callback_query
    if not query or not query.data:
        return PROJECT_TYPE

    await query.answer()
    wizard = _get_wizard(context)
    ptype = query.data.removeprefix("ptype:")
    wizard.setdefault("deploy_config", {})["deploy_type"] = ptype

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("This VPS (Docker)", callback_data="dtarget:local_docker")],
        [InlineKeyboardButton("Remote Server (SSH)", callback_data="dtarget:remote_ssh")],
    ])

    await query.edit_message_text(
        "<b>Deploy Target</b>\n\nWhere should this be deployed?",
        reply_markup=keyboard,
    )
    return DEPLOY_TARGET


async def deploy_target_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select deploy target."""
    query = update.callback_query
    if not query or not query.data:
        return DEPLOY_TARGET

    await query.answer()
    wizard = _get_wizard(context)
    target = query.data.removeprefix("dtarget:")
    wizard.setdefault("deploy_config", {})["deploy_target"] = target

    deploy_type = wizard["deploy_config"].get("deploy_type", "")

    # If web app, ask about domain/access
    if deploy_type == "web_app":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Localhost only", callback_data="access:localhost")],
            [InlineKeyboardButton("Public + Domain + SSL", callback_data="access:public")],
        ])
        await query.edit_message_text(
            "<b>Access Configuration</b>\n\nHow should the web app be accessed?",
            reply_markup=keyboard,
        )
        return ACCESS_CONFIG

    return await _show_confirmation(update, context)


async def access_config_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select access configuration."""
    query = update.callback_query
    if not query or not query.data:
        return ACCESS_CONFIG

    await query.answer()
    wizard = _get_wizard(context)
    access = query.data.removeprefix("access:")
    wizard.setdefault("deploy_config", {})["access"] = access

    return await _show_confirmation(update, context)


# ────────────────────────────────────────────
# CONFIRM_LAUNCH state
# ────────────────────────────────────────────

async def _show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show project summary for confirmation."""
    wizard = _get_wizard(context)

    engines_str = ", ".join(wizard.get("engines", []))
    settings_str = "\n".join(
        f"  {k}: {v}" for k, v in wizard.get("settings", {}).items()
    ) or "  Defaults"

    deploy_cfg = wizard.get("deploy_config", {})
    if deploy_cfg.get("auto_deploy"):
        deploy_str = (
            f"  Type: {deploy_cfg.get('deploy_type', 'N/A')}\n"
            f"  Target: {deploy_cfg.get('deploy_target', 'N/A')}\n"
            f"  Access: {deploy_cfg.get('access', 'N/A')}"
        )
    else:
        deploy_str = "  No auto-deploy"

    text = (
        "<b>Project Summary</b>\n\n"
        f"<b>Name:</b> {wizard.get('name', '?')}\n"
        f"<b>Engines:</b> {engines_str}\n"
        f"<b>Description:</b> {wizard.get('description', '')[:200]}\n\n"
        f"<b>Settings:</b>\n{settings_str}\n\n"
        f"<b>Deployment:</b>\n{deploy_str}\n\n"
        "Ready to launch?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f680 Launch!", callback_data="launch:confirm"),
            InlineKeyboardButton("\u274c Cancel", callback_data="launch:cancel"),
        ],
    ])

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(truncate_message(text), reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(truncate_message(text), reply_markup=keyboard)

    return CONFIRM_LAUNCH


async def confirm_launch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create project and start factory runs."""
    query = update.callback_query
    if not query:
        return CONFIRM_LAUNCH

    await query.answer("Launching...")
    wizard = _get_wizard(context)
    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    try:
        project = await services.project_service.create_project(
            name=wizard["name"],
            description=wizard.get("description", ""),
            engines=wizard.get("engines", []),
            requirements=wizard.get("requirements_structured", wizard.get("requirements_raw", "")),
            settings=wizard.get("settings", {}),
            deploy_config=wizard.get("deploy_config", {}),
            created_by=user_id,
        )

        # Start factory runs for each engine
        runs_started = []
        for engine in project.engines:
            try:
                run = await services.factory_runner.start_run(
                    project=project, engine=engine, created_by=user_id,
                )
                await services.run_monitor.attach(run)
                runs_started.append(f"\u2705 {engine}")
            except Exception as e:
                logger.error("launch_run_failed", engine=engine, error=str(e))
                runs_started.append(f"\u274c {engine}: {e}")

        await services.project_service.update_status(project.id, "running")

        await query.edit_message_text(
            f"<b>Project Launched!</b>\n\n"
            f"<b>{project.name}</b>\n\n"
            f"Runs:\n" + "\n".join(f"  {r}" for r in runs_started) + "\n\n"
            "You'll receive real-time notifications on progress."
        )

    except Exception as e:
        logger.error("project_creation_failed", error=str(e))
        await query.edit_message_text(f"Failed to create project: {e}")

    # Clear wizard data
    if context.user_data is not None:
        context.user_data.pop("wizard", None)

    return ConversationHandler.END


async def confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel project creation."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Project creation cancelled.")

    if context.user_data is not None:
        context.user_data.pop("wizard", None)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command during wizard."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "Project creation cancelled. Use /new to start again."
        )

    if context.user_data is not None:
        context.user_data.pop("wizard", None)

    return ConversationHandler.END
