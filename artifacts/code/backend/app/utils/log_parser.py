"""Parse [FACTORY:...] markers from factory run log files."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

# Regex patterns for factory markers
_MARKER_PATTERN = re.compile(r'^\[FACTORY:(\w+):(.*)\]$')
_PHASE_START_PATTERN = re.compile(r'^(\d+):START$')
_PHASE_END_PATTERN = re.compile(r'^(\d+):END:(\d+)$')
_COST_PATTERN = re.compile(r'^([\d.]+):(\w+)$')


class FactoryMarker(BaseModel):
    """Parsed factory log marker."""
    marker_type: str  # phase_start, phase_end, clarify, error, cost, complete
    phase: int | None = None
    data: dict[str, Any] = {}


def parse_factory_marker(line: str) -> FactoryMarker | None:
    """
    Parse a line for [FACTORY:...] markers.

    Returns FactoryMarker if found, None otherwise.

    Marker grammar:
        [FACTORY:PHASE:N:START]          - Phase N started
        [FACTORY:PHASE:N:END:score]      - Phase N completed with quality gate score
        [FACTORY:CLARIFY:question_json]  - Clarification question for user
        [FACTORY:ERROR:message]          - Error needing user attention
        [FACTORY:COST:amount:provider]   - Cost update
        [FACTORY:COMPLETE:summary_json]  - Factory run finished

    Examples:
        "[FACTORY:PHASE:3:START]" -> FactoryMarker(type="phase_start", phase=3)
        "[FACTORY:PHASE:3:END:98]" -> FactoryMarker(type="phase_end", phase=3, data={"score": 98})
        "[FACTORY:COST:1.50:openai]" -> FactoryMarker(type="cost", data={"amount": 1.50, "provider": "openai"})
    """
    line = line.strip()
    if not line.startswith("[FACTORY:"):
        return None

    # Try to match the full marker
    match = _MARKER_PATTERN.match(line)
    if not match:
        return None

    marker_type = match.group(1).upper()
    payload = match.group(2)

    if marker_type == "PHASE":
        return _parse_phase(payload)
    elif marker_type == "CLARIFY":
        return _parse_clarify(payload)
    elif marker_type == "ERROR":
        return _parse_error(payload)
    elif marker_type == "COST":
        return _parse_cost(payload)
    elif marker_type == "COMPLETE":
        return _parse_complete(payload)

    return None


def _parse_phase(payload: str) -> FactoryMarker | None:
    """Parse PHASE marker payload."""
    # Try phase start: N:START
    start_match = _PHASE_START_PATTERN.match(payload)
    if start_match:
        phase = int(start_match.group(1))
        return FactoryMarker(
            marker_type="phase_start",
            phase=phase,
            data={"phase": phase},
        )

    # Try phase end: N:END:score
    end_match = _PHASE_END_PATTERN.match(payload)
    if end_match:
        phase = int(end_match.group(1))
        score = int(end_match.group(2))
        return FactoryMarker(
            marker_type="phase_end",
            phase=phase,
            data={"phase": phase, "score": score},
        )

    return None


def _parse_clarify(payload: str) -> FactoryMarker | None:
    """Parse CLARIFY marker payload (JSON)."""
    try:
        data = json.loads(payload)
        return FactoryMarker(
            marker_type="clarify",
            data=data,
        )
    except json.JSONDecodeError:
        # Treat as plain text question
        return FactoryMarker(
            marker_type="clarify",
            data={"question": payload, "type": "open", "options": []},
        )


def _parse_error(payload: str) -> FactoryMarker | None:
    """Parse ERROR marker payload (plain text)."""
    return FactoryMarker(
        marker_type="error",
        data={"message": payload},
    )


def _parse_cost(payload: str) -> FactoryMarker | None:
    """Parse COST marker payload (amount:provider)."""
    match = _COST_PATTERN.match(payload)
    if match:
        amount = float(match.group(1))
        provider = match.group(2)
        return FactoryMarker(
            marker_type="cost",
            data={"amount": amount, "provider": provider},
        )
    return None


def _parse_complete(payload: str) -> FactoryMarker | None:
    """Parse COMPLETE marker payload (JSON)."""
    try:
        data = json.loads(payload)
        return FactoryMarker(
            marker_type="complete",
            data=data,
        )
    except json.JSONDecodeError:
        return FactoryMarker(
            marker_type="complete",
            data={"summary": payload},
        )
