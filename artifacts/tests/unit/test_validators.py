"""
Black-box tests for input validation functions.

Tests against spec:
  - Project name: ^[a-z][a-z0-9-]*[a-z0-9]$, 3-50 chars
  - Input sanitizer: strip [FACTORY:...] patterns
  - API key masker: show first 4 + last 4 chars
"""
import pytest

from app.utils.validators import is_valid_project_name, sanitize_user_input, mask_api_key


class TestProjectNameValidation:
    """Project names must be lowercase, hyphens only, 3-50 chars."""

    @pytest.mark.parametrize("name", [
        "abc",              # minimum length
        "my-project",       # typical name
        "a1b",              # with numbers
        "test-app-123",     # hyphens and numbers
        "a" * 49 + "z",    # 50 chars (max)
    ])
    def test_valid_names(self, name):
        assert is_valid_project_name(name) is True

    @pytest.mark.parametrize("name", [
        "ab",               # too short (2 chars)
        "a",                # single char
        "Abc",              # uppercase
        "ABC",              # all uppercase
        "-abc",             # starts with hyphen
        "abc-",             # ends with hyphen
        "a_b",              # underscore not allowed
        "a.b",              # dot not allowed
        "a b",              # space not allowed
        "a" * 51,           # too long (51 chars)
        "",                 # empty
        "1abc",             # starts with number
    ])
    def test_invalid_names(self, name):
        assert is_valid_project_name(name) is False


class TestInputSanitization:
    """User input must have [FACTORY:...] markers stripped to prevent injection."""

    def test_strips_factory_markers(self):
        text = "Hello [FACTORY:ERROR:boom] world"
        result = sanitize_user_input(text)
        assert "[FACTORY:" not in result
        assert "Hello" in result
        assert "world" in result

    def test_strips_multiple_markers(self):
        text = "[FACTORY:PHASE:3:START] text [FACTORY:COST:1.50:openai]"
        result = sanitize_user_input(text)
        assert "[FACTORY:" not in result
        assert "text" in result

    def test_preserves_clean_text(self):
        text = "This is normal text without markers"
        result = sanitize_user_input(text)
        assert result.strip() == text

    def test_handles_multiline(self):
        text = "line1\n[FACTORY:ERROR:bad]\nline2"
        result = sanitize_user_input(text)
        assert "[FACTORY:" not in result
        assert "line1" in result
        assert "line2" in result


class TestApiKeyMasking:
    """API keys must show only first 4 and last 4 characters."""

    def test_normal_key(self):
        key = "sk-abcdEFGHijklMNOPxy9z"
        masked = mask_api_key(key)
        assert masked.startswith("sk-a")
        assert masked.endswith("xy9z")
        assert key not in masked  # full key must not be visible
        assert "..." in masked

    def test_short_key(self):
        key = "short"
        masked = mask_api_key(key)
        assert key not in masked or len(key) <= 8
        assert "****" in masked or "..." in masked

    def test_exactly_8_chars(self):
        key = "12345678"
        masked = mask_api_key(key)
        # 8 chars or less should be heavily masked
        assert masked == "****" or "..." in masked
