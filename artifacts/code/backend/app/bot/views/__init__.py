"""Telegram view renderers."""

from __future__ import annotations

from app.bot.views.base import TelegramView
from app.bot.views.health_report import format_health_report
from app.bot.views.progress_bar import format_run_progress, format_phase_summary
from app.bot.views.project_card import format_project_card, format_project_list_card
from app.bot.views.research_report import format_research_report
from app.bot.views.scan_report import format_scan_report
from app.bot.views.welcome import format_welcome, format_help, format_onboarding_step

__all__ = [
    "TelegramView",
    "format_health_report",
    "format_run_progress",
    "format_phase_summary",
    "format_project_card",
    "format_project_list_card",
    "format_research_report",
    "format_scan_report",
    "format_welcome",
    "format_help",
    "format_onboarding_step",
]
