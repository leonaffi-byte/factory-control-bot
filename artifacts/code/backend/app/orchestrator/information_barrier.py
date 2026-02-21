"""Enforces file access rules per role during factory pipeline."""
from __future__ import annotations

import fnmatch

IMPLEMENTER_ALLOWED: list[str] = [
    "artifacts/requirements/spec*.md",
    "artifacts/architecture/design*.md",
    "artifacts/architecture/interfaces*.md",
]
IMPLEMENTER_WRITES: str = "artifacts/code/"
IMPLEMENTER_BLOCKED: list[str] = ["artifacts/tests/"]

TESTER_ALLOWED: list[str] = [
    "artifacts/requirements/spec*.md",
    "artifacts/architecture/interfaces*.md",
]
TESTER_WRITES: str = "artifacts/tests/"
TESTER_BLOCKED: list[str] = ["artifacts/code/"]

_ROLE_RULES: dict[str, dict] = {
    "implementer": {
        "allowed": IMPLEMENTER_ALLOWED,
        "writes": IMPLEMENTER_WRITES,
        "blocked": IMPLEMENTER_BLOCKED,
    },
    "tester": {
        "allowed": TESTER_ALLOWED,
        "writes": TESTER_WRITES,
        "blocked": TESTER_BLOCKED,
    },
}


class InformationBarrier:
    def validate_access(self, role: str, file_path: str, access_type: str) -> bool:
        rules = _ROLE_RULES.get(role)
        if not rules:
            return True  # unknown roles get full access
        if access_type == "write":
            return file_path.startswith(rules["writes"])
        # read access
        for blocked in rules["blocked"]:
            if file_path.startswith(blocked):
                return False
        for pattern in rules["allowed"]:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        # Also allow reading from own write directory
        if file_path.startswith(rules["writes"]):
            return True
        return False

    def get_allowed_files(self, role: str) -> list[str]:
        rules = _ROLE_RULES.get(role, {})
        return rules.get("allowed", [])

    def filter_artifacts(
        self, role: str, artifacts: dict[str, str]
    ) -> dict[str, str]:
        return {
            path: content
            for path, content in artifacts.items()
            if self.validate_access(role, path, "read")
        }
