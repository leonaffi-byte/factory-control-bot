"""Token estimation for context budgeting."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Approximate: ~4 chars per token for English text
    return max(1, len(text) // 4)


def fits_in_context(
    text: str,
    model_context_window: int,
    margin: float = 0.9,
) -> bool:
    tokens = estimate_tokens(text)
    effective_window = int(model_context_window * margin)
    return tokens <= effective_window
