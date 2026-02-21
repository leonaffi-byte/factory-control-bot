# Security Audit — Factory Control Bot v2.0

**Primary Auditor**: Gemini 3 Pro (Google) via zen MCP
**Secondary Auditor**: GPT-5.2 (OpenAI) via zen MCP
**Date**: 2026-02-21
**Scope**: Config, backup, installer, worker, provider adapters, self-researcher, middleware
**Files Reviewed**: 16 files across security-sensitive modules

---

## Issue #1 [CRITICAL] — Fragile DB Password Parsing in Backup Service

**File**: `app/services/backup_service.py`
**Lines**: 308-345 (`_run_pg_dump`)

The regex pattern for extracting DB credentials from the SQLAlchemy URL does not handle special characters in passwords (e.g., `@`, `:`, `/`, `%`). URL-encoded passwords will be passed literally, causing authentication failures or worse.

Additionally, `subprocess.run()` is called with `env={"PGPASSWORD": ..., "PATH": ...}` which **replaces the entire environment**, potentially losing important variables.

**Fix**: Use `urllib.parse.urlparse()` with `urllib.parse.unquote()` for URL parsing. Inherit `os.environ` and only override PGPASSWORD:
```python
import os
env = {**os.environ, "PGPASSWORD": password}
```

---

## Issue #2 [HIGH] — No Subprocess Timeout in Backup Restore

**File**: `app/services/backup_service.py`
**Lines**: 348-383 (`_run_pg_restore`)

`subprocess.run()` for both `gunzip` and `psql` has no `timeout` parameter. A hung psql session would block the asyncio thread pool worker indefinitely.

**Fix**: Add `timeout=300` (5 min) to all subprocess calls.

---

## Issue #3 [HIGH] — Git Commit Message Injection in Self-Researcher

**File**: `app/services/self_researcher.py`
**Lines**: 350-355 (`_create_git_branch`)

The git commit message includes `suggestion.title[:60]` which is derived from model output. While subprocess.run with a list argument prevents shell injection, the commit message itself could contain git-interpreted sequences or misleading content.

**Fix**: Sanitize the title by removing non-printable characters and limiting to alphanumeric + basic punctuation.

---

## Issue #4 [HIGH] — Systemd Unit Path Injection

**File**: `app/installer/steps/systemd.py`

Systemd service files are generated with `WorkingDirectory` and `ExecStart` values from parameters. If these values contain newlines or special systemd directives, they could inject arbitrary configuration.

**Fix**: Validate that paths contain no newlines, special characters, or systemd escape sequences. Use `shlex.quote()` for ExecStart arguments.

---

## Issue #5 [HIGH] — API Keys Sent to External Providers via Self-Research

**File**: `app/services/self_researcher.py`
**Lines**: 258-266 (`_build_codebase_context`)

The self-researcher reads `config.py` content and includes it in the research prompt sent to external LLM providers. If `config.py` contains hardcoded default values or the actual source includes field descriptions with example keys, this could leak sensitive information.

**Fix**: Exclude `config.py` from the key files list, or filter out any lines containing "api_key", "token", or "password" before including.

---

## Issue #6 [HIGH] — API Key Leakage via Adapter Serialization

**File**: `app/providers/litellm_adapter.py`

API keys are stored as `self._api_key` instance attributes. If the adapter object is ever serialized (e.g., by pickle, logged by structlog's repr, or included in error tracebacks), the key could leak.

**Fix**: Use a property that reads from a secure store, or implement `__repr__` to mask the key.

---

## Issue #7 [MEDIUM] — SQL Injection in NOTIFY Payload

**File**: `app/database/events.py`
**Method**: `notify()`

If the NOTIFY payload contains single quotes, it could break the NOTIFY SQL command. Depending on the implementation, this could be a SQL injection vector.

**Fix**: Use parameterized queries or escape single quotes in the payload.

---

## Issue #8 [MEDIUM] — Shell Metacharacters in Postgres Installer

**File**: `app/installer/steps/postgres.py`

The `CREATE ROLE` and `CREATE DATABASE` commands may be constructed with user-provided `db_pass` values. If shell metacharacters are present, they could inject into the SQL command.

**Fix**: Use parameterized psql commands or escape the password properly.

---

## Issue #9 [MEDIUM] — API Keys Could Leak via Structlog

**File**: `app/config.py`

Structlog's default configuration serializes all keyword arguments. If a Settings instance or individual API key fields are passed as log context, they will appear in log output.

**Fix**: Add a structlog processor that redacts fields matching `*_key`, `*_token`, `*_password` patterns.

---

## Issue #10 [MEDIUM] — Raw NOTIFY Payload Processed Without Validation

**File**: `app/worker.py`
**Method**: `_on_event()`

The event callback receives raw NOTIFY payloads and logs them directly. Depending on downstream processing, unvalidated payloads could be an injection vector.

**Fix**: Parse and validate the payload structure before processing.

---

## Issue #11 [MEDIUM] — SambaNova Adapter Response Validation

**File**: `app/providers/sambanova_adapter.py`

HTTP responses from the SambaNova API are parsed without validating the response structure. Missing or unexpected fields could cause KeyError or AttributeError.

**Fix**: Add defensive response parsing with `.get()` and type checks.

---

## Issue #12 [MEDIUM] — Health Monitor System Info Exposure

**File**: `app/services/health_monitor.py`

Health reports may include file paths, process names, and memory details. If surfaced to Telegram, this could reveal sensitive system information.

**Fix**: Sanitize health report output before sending to Telegram.

---

## Issue #13 [MEDIUM] — Self-Researcher Enum Values Not Validated

**File**: `app/services/self_researcher.py`

The `category` and `risk_level` fields from model output are accepted without validation against an allowlist. Arbitrary strings are stored in the database.

**Fix**: Validate against allowed values: category in {performance, quality, cost, reliability, dx}, risk_level in {low, medium, high}.

---

## Issue #14 [LOW] — No Package Integrity Verification

**File**: `app/installer/steps/engines.py`

ENGINE_INSTALL_COMMANDS runs `npm install -g` and `pip install` without checksum verification.

**Fix**: Add `--hash` for pip installs where possible. Low priority since packages are from official registries.

---

## Issue #15 [LOW] — Callback Query Auth Bypass

**File**: `app/bot/middleware.py`

The auth whitelist check may only apply to command handlers, not callback query handlers. This could allow unauthorized users to interact with inline buttons if they know the callback data format.

**Fix**: Verify auth check applies to all handler types including callback queries.

---

## Summary

| Severity | Count | Source |
|----------|-------|--------|
| CRITICAL | 1 | Gemini 3 Pro |
| HIGH | 5 | Gemini 3 Pro (3) + GPT-5.2 (2) |
| MEDIUM | 7 | Gemini 3 Pro (4) + GPT-5.2 (3) |
| LOW | 2 | Gemini 3 Pro (1) + GPT-5.2 (1) |
| **Total** | **15** | **2 providers** |
