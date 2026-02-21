"""Translation and requirements structuring service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger()

DEFAULT_TRANSLATOR_PROMPT = """You are a professional translator. Translate the following text to English.
Preserve the original meaning, technical terms, and formatting.
If the text is already in English, return it unchanged.
Only output the translated text, no explanations."""

DEFAULT_REQUIREMENTS_PROMPT = """You are a software requirements analyst. Transform the following raw project description
into structured, clear software requirements in Markdown format.

Structure the output as:
## Overview
Brief project summary.

## Functional Requirements
- FR-1: ...
- FR-2: ...

## Non-Functional Requirements
- NFR-1: ...

## User Interface
- UI-1: ...

## Technical Constraints
- TC-1: ...

## Edge Cases
- EC-1: ...

Be thorough. Infer reasonable requirements from the description.
If something is ambiguous, make a reasonable assumption and mark it with [ASSUMPTION].

Raw input:
"""


class TranslationService:
    """Handles translation and AI-powered requirements structuring."""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://factory-control-bot.local",
                "X-Title": "Factory Control Bot",
            },
            timeout=60.0,
        )
        self._templates_dir = settings.templates_dir

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    async def translate_to_english(
        self,
        text: str,
        source_lang: str | None = None,
    ) -> str:
        """
        Translate text to English using the configured AI model.

        If the text appears to already be in English, it is returned unchanged.
        """
        # Simple heuristic: if mostly ASCII, probably English
        ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(len(text), 1)
        if ascii_ratio > 0.9:
            logger.debug("text_appears_english", ascii_ratio=ascii_ratio)
            return text

        prompt = self._load_template("translator.txt", DEFAULT_TRANSLATOR_PROMPT)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]

        model = self._settings.translation_model
        result = await self._call_model(model, messages)

        logger.info("translation_complete", source_lang=source_lang, model=model)
        return result

    async def structure_requirements(
        self,
        raw_text: str,
    ) -> str:
        """
        Transform raw text into structured requirements using AI.

        Uses the requirements structurer prompt template.
        """
        prompt = self._load_template("requirements_structurer.txt", DEFAULT_REQUIREMENTS_PROMPT)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": raw_text},
        ]

        model = self._settings.requirements_model
        result = await self._call_model(model, messages, max_tokens=4096)

        logger.info("requirements_structured", model=model, output_len=len(result))
        return result

    async def _call_model(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 2048,
    ) -> str:
        """Call an AI model via OpenRouter."""
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No response from model")

        content = choices[0].get("message", {}).get("content", "")
        return content.strip()

    def _load_template(self, filename: str, default: str) -> str:
        """Load a prompt template from file, falling back to default."""
        template_path = self._templates_dir / "prompts" / filename
        if template_path.exists():
            try:
                return template_path.read_text(encoding="utf-8").strip()
            except Exception:
                logger.warning("template_load_failed", path=str(template_path))

        return default
