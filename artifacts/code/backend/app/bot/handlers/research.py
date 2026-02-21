"""Self-research handler — /research."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.keyboards.research_actions import get_research_actions_keyboard
from app.bot.views.research_report import format_research_report
from app.services import ServiceContainer

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


async def research_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /research command — trigger self-research."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text(
            "Only admins can trigger self-research."
        )
        return

    msg = await update.effective_message.reply_text(
        "<b>Self-Research</b>\n\nAnalysing factory configuration and performance...",
        parse_mode="HTML",
    )

    try:
        report = await services.self_researcher.run_research()
        text = format_research_report(report)
        suggestion_count = len(getattr(report, "suggestions", []))
        keyboard = get_research_actions_keyboard(suggestion_count=suggestion_count)

        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        logger.info(
            "self_research_completed",
            user_id=user_id,
            suggestions=suggestion_count,
        )
    except Exception as e:
        logger.error("self_research_failed", error=str(e), user_id=user_id)
        await msg.edit_text(
            f"<b>Research Failed</b>\n\n<code>{e}</code>",
            parse_mode="HTML",
        )


async def research_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle research:* inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("research:")

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await query.edit_message_text("Only admins can apply research changes.")
        return

    if data == "apply_all":
        try:
            report = await services.self_researcher.get_last_report()
            if not report:
                await query.edit_message_text(
                    "No research report available. Run /research first."
                )
                return

            low_risk = [
                s for s in getattr(report, "suggestions", [])
                if getattr(s, "risk", "high") == "low"
            ]
            if not low_risk:
                await query.edit_message_text(
                    "<b>No low-risk suggestions to apply.</b>\n\n"
                    "All suggestions require manual review.",
                    parse_mode="HTML",
                )
                return

            applied = await services.self_researcher.apply_suggestions(low_risk)
            await query.edit_message_text(
                f"<b>Applied {len(applied)} low-risk suggestion(s).</b>\n\n"
                + "\n".join(
                    f"  • {getattr(s, 'title', str(s))}" for s in applied
                ),
                parse_mode="HTML",
            )
            logger.info(
                "research_suggestions_applied",
                user_id=user_id,
                count=len(applied),
            )
        except Exception as e:
            logger.error("research_apply_all_failed", error=str(e))
            await query.edit_message_text(f"Failed to apply suggestions: {e}")
        return

    if data == "review":
        try:
            report = await services.self_researcher.get_last_report()
            if not report:
                await query.edit_message_text(
                    "No research report available. Run /research first."
                )
                return

            suggestions = getattr(report, "suggestions", [])
            if not suggestions:
                await query.edit_message_text(
                    "<b>No suggestions to review.</b>",
                    parse_mode="HTML",
                )
                return

            buttons = []
            for i, s in enumerate(suggestions):
                risk = getattr(s, "risk", "unknown")
                title = getattr(s, "title", f"Suggestion {i + 1}")
                risk_tag = {"low": "LOW", "medium": "MED", "high": "HIGH"}.get(risk, risk.upper())
                buttons.append([
                    InlineKeyboardButton(
                        f"[{risk_tag}] {title[:40]}",
                        callback_data=f"research:detail:{i}",
                    )
                ])
            buttons.append([InlineKeyboardButton("Back", callback_data="research:back")])

            await query.edit_message_text(
                "<b>Research Suggestions</b>\n\nSelect a suggestion to review:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception as e:
            logger.error("research_review_failed", error=str(e))
            await query.edit_message_text(f"Failed to load suggestions: {e}")
        return

    if data.startswith("detail:"):
        idx_str = data.removeprefix("detail:")
        try:
            idx = int(idx_str)
        except ValueError:
            await query.edit_message_text("Invalid suggestion index.")
            return

        try:
            report = await services.self_researcher.get_last_report()
            if not report:
                await query.edit_message_text("No research report available.")
                return

            suggestions = getattr(report, "suggestions", [])
            if idx >= len(suggestions):
                await query.edit_message_text("Suggestion not found.")
                return

            s = suggestions[idx]
            title = getattr(s, "title", f"Suggestion {idx + 1}")
            description = getattr(s, "description", "No description available.")
            risk = getattr(s, "risk", "unknown")
            impact = getattr(s, "impact", "unknown")

            text = (
                f"<b>{title}</b>\n\n"
                f"<b>Risk:</b> {risk.upper()}\n"
                f"<b>Impact:</b> {impact}\n\n"
                f"{description}"
            )
            if len(text) > 4096:
                text = text[:4093] + "..."

            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "Apply", callback_data=f"research:apply_one:{idx}"
                        ),
                        InlineKeyboardButton(
                            "Dismiss", callback_data=f"research:dismiss_one:{idx}"
                        ),
                    ],
                    [InlineKeyboardButton("Back", callback_data="research:review")],
                ]),
            )
        except Exception as e:
            logger.error("research_detail_failed", error=str(e), idx=idx_str)
            await query.edit_message_text(f"Failed to load detail: {e}")
        return

    if data.startswith("apply_one:"):
        idx_str = data.removeprefix("apply_one:")
        try:
            idx = int(idx_str)
        except ValueError:
            await query.edit_message_text("Invalid suggestion index.")
            return

        try:
            report = await services.self_researcher.get_last_report()
            suggestions = getattr(report, "suggestions", []) if report else []
            if idx >= len(suggestions):
                await query.edit_message_text("Suggestion not found.")
                return

            applied = await services.self_researcher.apply_suggestions([suggestions[idx]])
            title = getattr(suggestions[idx], "title", f"Suggestion {idx + 1}")
            await query.edit_message_text(
                f"<b>Applied:</b> {title}",
                parse_mode="HTML",
            )
            logger.info("research_single_applied", user_id=user_id, idx=idx, title=title)
        except Exception as e:
            logger.error("research_apply_one_failed", error=str(e))
            await query.edit_message_text(f"Failed to apply: {e}")
        return

    if data.startswith("dismiss_one:"):
        await query.edit_message_text(
            "<b>Suggestion dismissed.</b>",
            parse_mode="HTML",
        )
        return

    if data == "dismiss":
        await query.edit_message_text(
            "<b>All research suggestions dismissed.</b>",
            parse_mode="HTML",
        )
        return

    if data == "back":
        try:
            report = await services.self_researcher.get_last_report()
            if report:
                text = format_research_report(report)
                suggestion_count = len(getattr(report, "suggestions", []))
                keyboard = get_research_actions_keyboard(suggestion_count=suggestion_count)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text("No research report available. Use /research.")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
        return

    logger.warning("research_callback_unknown_action", data=data)
    await query.edit_message_text("Unknown action.")
