"""Quality gate result dataclass for pipeline phase scoring."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QualityGateResult:
    phase: int
    total_score: int  # 0-100
    completeness: int  # 0-25
    clarity: int  # 0-25
    consistency: int  # 0-25
    robustness: int  # 0-25
    passed: bool  # total_score >= threshold
    threshold: int  # default 97
    feedback: str
    gaps: list[str] = field(default_factory=list)
    scored_by_model: str = ""
    scored_by_provider: str = ""
    iteration: int = 1
