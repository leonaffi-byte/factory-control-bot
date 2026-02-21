"""Input validation utilities."""

from __future__ import annotations

import re
from typing import Any

# Project name regex: lowercase letters, numbers, hyphens
# Must start with a letter, end with letter or number, 3-50 chars
_PROJECT_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9-]*[a-z0-9]$')

# Factory marker pattern for sanitization
_FACTORY_MARKER_PATTERN = re.compile(r'\[FACTORY:[^\]]*\]')


def validate_project_name(name: str) -> tuple[bool, str]:
    """
    Validate a project name.

    Returns:
        (is_valid, error_message) — error_message is empty if valid.

    Rules:
        - 3-50 characters
        - Must start with a lowercase letter
        - Only lowercase letters, numbers, and hyphens
        - Must end with a letter or number (not a hyphen)
        - No consecutive hyphens
    """
    if not name:
        return False, "Project name cannot be empty."

    if len(name) < 3:
        return False, "Project name must be at least 3 characters."

    if len(name) > 50:
        return False, "Project name must be at most 50 characters."

    if not name[0].isalpha() or not name[0].islower():
        return False, "Project name must start with a lowercase letter."

    if name[-1] == "-":
        return False, "Project name must end with a letter or number."

    if "--" in name:
        return False, "Project name cannot contain consecutive hyphens."

    if not _PROJECT_NAME_PATTERN.match(name):
        return False, (
            "Project name must contain only lowercase letters, numbers, "
            "and hyphens."
        )

    return True, ""


def is_valid_project_name(name: str) -> bool:
    """Check if a project name is valid. Returns True/False."""
    valid, _ = validate_project_name(name)
    return valid


def sanitize_user_input(text: str) -> str:
    """
    Strip factory marker patterns from user input to prevent injection.

    Removes any [FACTORY:...] patterns from the text.
    """
    return _FACTORY_MARKER_PATTERN.sub('', text)


def validate_telegram_id(value: str) -> tuple[bool, int | None, str]:
    """
    Validate a Telegram user ID string.

    Returns:
        (is_valid, parsed_id, error_message)
    """
    try:
        telegram_id = int(value.strip())
        if telegram_id <= 0:
            return False, None, "Telegram ID must be a positive integer."
        if telegram_id > 9999999999:
            return False, None, "Telegram ID is too large."
        return True, telegram_id, ""
    except ValueError:
        return False, None, "Invalid Telegram ID. Must be a number."


def mask_api_key(key: str) -> str:
    """Mask an API key for safe display — show first 4 + last 4 chars."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def validate_setting_value(
    key: str, value: str, setting_type: str, **constraints
) -> tuple[bool, Any, str]:
    """
    Validate a setting value.

    Returns:
        (is_valid, parsed_value, error_message)
    """
    try:
        if setting_type == "int":
            parsed = int(value)
            min_val = constraints.get("min")
            max_val = constraints.get("max")
            if min_val is not None and parsed < min_val:
                return False, None, f"Value must be >= {min_val}"
            if max_val is not None and parsed > max_val:
                return False, None, f"Value must be <= {max_val}"
            return True, parsed, ""

        elif setting_type == "float":
            parsed = float(value)
            min_val = constraints.get("min")
            max_val = constraints.get("max")
            if min_val is not None and parsed < min_val:
                return False, None, f"Value must be >= {min_val}"
            if max_val is not None and parsed > max_val:
                return False, None, f"Value must be <= {max_val}"
            return True, parsed, ""

        elif setting_type == "choice":
            choices = constraints.get("choices", [])
            if value not in choices:
                return False, None, f"Value must be one of: {', '.join(choices)}"
            return True, value, ""

        elif setting_type == "text":
            if not value.strip():
                return False, None, "Value cannot be empty."
            return True, value.strip(), ""

        else:
            return True, value, ""

    except (ValueError, TypeError) as e:
        return False, None, f"Invalid value: {e}"
