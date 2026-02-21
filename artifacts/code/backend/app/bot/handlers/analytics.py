"""Analytics handlers — per-project and aggregate views."""

from __future__ import annotations

from uuid import UUID

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer
from app.utils.formatting import truncate_message

logger = structlog.get_logger()


async def analytics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics command — show analytics menu."""
    await _show_analytics_menu(update, context)


async def _show_analytics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display analytics menu with period selection and project analytics access."""
    text = (
        "<b>Analytics</b>\n\n"
        "View cost breakdowns, quality metrics, and engine comparisons.\n"
        "Select a time period for aggregate data or view per-project analytics."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("This Week", callback_data="analytics:aggregate:week"),
            InlineKeyboardButton("This Month", callback_data="analytics:aggregate:month"),
        ],
        [
            InlineKeyboardButton("This Year", callback_data="analytics:aggregate:year"),
        ],
        [
            InlineKeyboardButton("Per-Project", callback_data="analytics:project_select"),
        ],
        [InlineKeyboardButton("\u00ab Back", callback_data="menu:back")],
    ])

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle analytics callback queries."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("analytics:")

    services: ServiceContainer = context.application.bot_data["services"]

    if data.startswith("aggregate:"):
        period = data.removeprefix("aggregate:")
        await _show_aggregate(query, services, period)

    elif data == "project_select":
        await _show_project_select(query, services)

    elif data.startswith("project:"):
        project_id_str = data.removeprefix("project:")
        try:
            project_id = UUID(project_id_str)
        except ValueError:
            return
        await _show_project_analytics(query, services, project_id)

    elif data.startswith("comparison:"):
        project_id_str = data.removeprefix("comparison:")
        try:
            project_id = UUID(project_id_str)
        except ValueError:
            return
        await _show_engine_comparison(query, services, project_id)


async def _show_aggregate(query, services: ServiceContainer, period: str) -> None:
    """Display aggregate analytics for a given period."""
    try:
        agg = await services.analytics_service.get_aggregate_analytics(period=period)
    except Exception as e:
        await query.edit_message_text(f"Failed to load analytics: {e}")
        return

    period_label = {"week": "This Week", "month": "This Month", "year": "This Year"}.get(
        period, period
    )

    text = (
        f"<b>Analytics: {period_label}</b>\n\n"
        f"<b>Total Spend:</b> ${agg.total_spend:.2f}\n"
        f"<b>Projects Completed:</b> {agg.projects_completed}\n"
        f"<b>Projects Failed:</b> {agg.projects_failed}\n"
        f"<b>Success Rate:</b> {agg.success_rate:.0%}\n"
        f"<b>Projects This Period:</b> {agg.projects_this_period}\n\n"
    )

    if agg.avg_cost_by_tier:
        text += "<b>Avg Cost by Tier:</b>\n"
        for tier, cost in sorted(agg.avg_cost_by_tier.items()):
            text += f"  Tier {tier}: ${cost:.2f}\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u00ab Back", callback_data="analytics:menu")],
    ])

    # analytics:menu goes back to analytics menu
    await query.edit_message_text(text, reply_markup=keyboard)


async def _show_project_select(query, services: ServiceContainer) -> None:
    """Show project list for per-project analytics."""
    projects, total = await services.project_service.list_projects(limit=20)

    if not projects:
        await query.edit_message_text(
            "No projects found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u00ab Back", callback_data="analytics:menu")],
            ]),
        )
        return

    buttons = []
    for proj in projects:
        buttons.append([
            InlineKeyboardButton(
                f"{proj.name} ({proj.status})",
                callback_data=f"analytics:project:{proj.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="analytics:menu")])

    await query.edit_message_text(
        "<b>Select project for analytics:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _show_project_analytics(query, services: ServiceContainer, project_id: UUID) -> None:
    """Display per-project analytics."""
    try:
        analytics = await services.analytics_service.get_project_analytics(project_id)
    except Exception as e:
        await query.edit_message_text(f"Failed to load project analytics: {e}")
        return

    project = await services.project_service.get_project(project_id)
    name = project.name if project else str(project_id)[:8]

    text = (
        f"<b>Analytics: {name}</b>\n\n"
        f"<b>Total Cost:</b> ${analytics.total_cost:.2f}\n\n"
    )

    if analytics.cost_by_provider:
        text += "<b>Cost by Provider:</b>\n"
        for provider, cost in sorted(analytics.cost_by_provider.items(), key=lambda x: -x[1]):
            text += f"  {provider}: ${cost:.2f}\n"
        text += "\n"

    if analytics.cost_by_phase:
        text += "<b>Cost by Phase:</b>\n"
        for phase, cost in sorted(analytics.cost_by_phase.items()):
            text += f"  Phase {phase}: ${cost:.2f}\n"
        text += "\n"

    if analytics.quality_scores:
        text += "<b>Quality Scores:</b>\n"
        for phase, score in sorted(analytics.quality_scores.items()):
            text += f"  Phase {phase}: {score:.0f}/100\n"
        text += "\n"

    if analytics.duration_minutes is not None:
        text += f"<b>Duration:</b> {analytics.duration_minutes:.0f} min\n"

    text += (
        f"\n<b>Tests:</b> {analytics.test_passed} passed, "
        f"{analytics.test_failed} failed, {analytics.test_skipped} skipped"
    )

    buttons = [
        [InlineKeyboardButton("Engine Comparison", callback_data=f"analytics:comparison:{project_id}")],
        [InlineKeyboardButton("\u00ab Back", callback_data="analytics:project_select")],
    ]

    await query.edit_message_text(
        truncate_message(text),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _show_engine_comparison(query, services: ServiceContainer, project_id: UUID) -> None:
    """Show engine comparison for a project with parallel runs."""
    comparisons = await services.analytics_service.get_engine_comparison(project_id)

    if not comparisons:
        await query.edit_message_text(
            "No engine comparison available (single engine or no completed runs).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u00ab Back", callback_data=f"analytics:project:{project_id}")],
            ]),
        )
        return

    project = await services.project_service.get_project(project_id)
    name = project.name if project else str(project_id)[:8]

    text = f"<b>Engine Comparison: {name}</b>\n\n"

    # Table header
    text += "<pre>"
    text += f"{'Engine':<12} {'Cost':>8} {'Time':>8} {'Quality':>8} {'Tests':>8}\n"
    text += "-" * 48 + "\n"

    for comp in comparisons:
        text += (
            f"{comp.engine:<12} "
            f"${comp.total_cost:>7.2f} "
            f"{comp.duration_minutes:>6.0f}m "
            f"{comp.quality_avg:>7.1f} "
            f"{comp.test_pass_rate:>6.0%}\n"
        )

    text += "</pre>"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u00ab Back", callback_data=f"analytics:project:{project_id}")],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)
