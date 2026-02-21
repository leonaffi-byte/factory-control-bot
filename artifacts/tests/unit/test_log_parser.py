"""
Black-box tests for the Factory log marker parser.

Tests against the specification:
  [FACTORY:PHASE:N:START]          -> phase_start
  [FACTORY:PHASE:N:END:score]      -> phase_end
  [FACTORY:CLARIFY:json]           -> clarify
  [FACTORY:ERROR:message]          -> error
  [FACTORY:COST:amount:provider]   -> cost
  [FACTORY:COMPLETE:json]          -> complete
  Regular lines                    -> None
"""
import json
import pytest

from app.utils.log_parser import parse_factory_marker


class TestRegularLines:
    """Lines without factory markers should return None."""

    def test_plain_text(self):
        assert parse_factory_marker("hello world") is None

    def test_empty_line(self):
        assert parse_factory_marker("") is None

    def test_similar_but_not_marker(self):
        assert parse_factory_marker("INFO something [NOTFACTORY:x]") is None

    def test_partial_marker(self):
        assert parse_factory_marker("[FACTORY:") is None


class TestPhaseMarkers:
    """Test PHASE:N:START and PHASE:N:END:score markers."""

    def test_phase_start(self):
        result = parse_factory_marker("[FACTORY:PHASE:3:START]")
        assert result is not None
        assert result.marker_type == "phase_start"
        assert result.phase == 3

    def test_phase_end_with_score(self):
        result = parse_factory_marker("[FACTORY:PHASE:5:END:98]")
        assert result is not None
        assert result.marker_type == "phase_end"
        assert result.phase == 5
        assert result.data.get("score") == 98

    def test_phase_zero(self):
        result = parse_factory_marker("[FACTORY:PHASE:0:START]")
        assert result is not None
        assert result.marker_type == "phase_start"
        assert result.phase == 0

    def test_phase_end_perfect_score(self):
        result = parse_factory_marker("[FACTORY:PHASE:7:END:100]")
        assert result is not None
        assert result.data.get("score") == 100

    def test_phase_end_zero_score(self):
        result = parse_factory_marker("[FACTORY:PHASE:1:END:0]")
        assert result is not None
        assert result.data.get("score") == 0


class TestClarifyMarker:
    """Test CLARIFY markers with JSON payloads."""

    def test_clarify_with_question(self):
        payload = {"question": "What auth method?", "type": "multiple_choice", "options": ["JWT", "Session"]}
        line = f'[FACTORY:CLARIFY:{json.dumps(payload)}]'
        result = parse_factory_marker(line)
        assert result is not None
        assert result.marker_type == "clarify"
        assert result.data["question"] == "What auth method?"

    def test_clarify_minimal_json(self):
        line = '[FACTORY:CLARIFY:{"question":"Simple?"}]'
        result = parse_factory_marker(line)
        assert result is not None
        assert result.marker_type == "clarify"


class TestErrorMarker:
    """Test ERROR markers with text messages."""

    def test_error_simple(self):
        result = parse_factory_marker("[FACTORY:ERROR:something went wrong]")
        assert result is not None
        assert result.marker_type == "error"
        assert "something went wrong" in str(result.data.get("message", ""))

    def test_error_empty_message(self):
        result = parse_factory_marker("[FACTORY:ERROR:]")
        assert result is not None
        assert result.marker_type == "error"


class TestCostMarker:
    """Test COST markers with amount and provider."""

    def test_cost_decimal(self):
        result = parse_factory_marker("[FACTORY:COST:1.50:openai]")
        assert result is not None
        assert result.marker_type == "cost"
        assert result.data.get("amount") == pytest.approx(1.50)
        assert result.data.get("provider") == "openai"

    def test_cost_zero(self):
        result = parse_factory_marker("[FACTORY:COST:0.00:anthropic]")
        assert result is not None
        assert result.marker_type == "cost"
        assert result.data.get("amount") == pytest.approx(0.00)

    def test_cost_large(self):
        result = parse_factory_marker("[FACTORY:COST:99.99:google]")
        assert result is not None
        assert result.data.get("amount") == pytest.approx(99.99)


class TestCompleteMarker:
    """Test COMPLETE markers with JSON summary."""

    def test_complete_full_summary(self):
        payload = {
            "project": "my-app",
            "engine": "claude",
            "duration_minutes": 45,
            "total_cost": 12.50,
        }
        line = f'[FACTORY:COMPLETE:{json.dumps(payload)}]'
        result = parse_factory_marker(line)
        assert result is not None
        assert result.marker_type == "complete"
        assert result.data["project"] == "my-app"
        assert result.data["total_cost"] == 12.50
