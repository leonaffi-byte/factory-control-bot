# Security Audit — Factory Control Bot
## Primary Auditor: Gemini 3 Pro (Google) via zen MCP
## Secondary Auditor: GPT-5.2 (OpenAI) via zen MCP
## Date: 2026-02-21
## Scope: Full codebase — VPS management Telegram bot with Docker socket, shell commands, filesystem, PostgreSQL

---

## Summary

| Severity | Primary | Secondary | Total Unique |
|----------|---------|-----------|-------------|
| CRITICAL | 1       | 0         | 1           |
| HIGH     | 3       | 4         | 6           |
| MEDIUM   | 4       | 5         | 8           |
| LOW      | 4       | 1         | 4           |
| **Total**| **12**  | **9**     | **19**      |

The application has a solid authentication foundation (Telegram whitelist with silent rejection) and good input sanitization (factory marker stripping). Primary risks are in the tmux/shell interaction layer, file system operations (symlinks/TOCTOU), and system service management (sudo escalation).

---

## CRITICAL Issues

### SEC-CRIT-1: Command injection defense-in-depth gap in tmux send-keys
- **File:** `factory_runner.py:362-386`
- **Description:** `_start_tmux_session()` looks up engine commands from `ENGINE_COMMANDS` dict, but the fallback at line 366 uses `f"echo 'Unknown engine: {engine}'"` which is sent directly to the shell via `tmux send-keys`. While engine names are currently validated from a fixed list in `new_project.py`, this is a defense-in-depth gap. If the engine name is ever user-controlled from DB, this becomes shell injection.
- **Remediation:** Remove the echo fallback. Add explicit validation: `if engine not in ENGINE_COMMANDS: raise ValueError(...)`. Never construct shell commands from variables.

---

## HIGH Issues

### SEC-HIGH-1: Auth bypass for channel posts / system updates
- **File:** `middleware.py:55-59`
- **Description:** When `update.effective_user is None` (channel posts, some group updates), the auth middleware allows the update through. If any downstream handler reacts to these updates, this bypasses authorization entirely.
- **Remediation:** Default-deny when `effective_user is None`. Raise `ApplicationHandlerStop` unless the update is from an explicitly allowlisted chat/channel.

### SEC-HIGH-2: Symlink attack on log file reads
- **File:** `run_monitor.py:160`
- **Description:** Log files are opened with plain `open()` without following-symlink protection. If an attacker controls the project directory, they can symlink the log file to sensitive system files (e.g., `/etc/shadow`, `/proc/self/environ`). Content would be parsed and potentially forwarded via Telegram notifications.
- **Remediation:** Use `os.path.realpath()` and verify resolved path stays within `factory_root_dir`. Consider using `O_NOFOLLOW` flag.

### SEC-HIGH-3: Path traversal via unsanitized engine in directory naming
- **File:** `factory_runner.py:71-73`
- **Description:** `project_dir = self._factory_root / f"{project.name}-{engine}"`. While `project.name` is validated, `engine` is not validated at the runner level. Values like `../../etc` would traverse the directory. The tmux session name has the same issue.
- **Remediation:** Enforce `engine in ENGINE_COMMANDS` before any path construction. Verify `project_dir.resolve().is_relative_to(self._factory_root.resolve())`.

### SEC-HIGH-4: TOCTOU + symlink hazards in file writes
- **File:** `factory_runner.py:279-298, 354-361`
- **Description:** Multiple file write operations (clarification answers, raw-input.md, engine configs) follow symlinks and have TOCTOU windows. Two answers arriving simultaneously can cause lost updates (read-modify-write race).
- **Remediation:** Use atomic file replacement (write to temp + `os.replace()`). Use `O_NOFOLLOW|O_CREAT|O_TRUNC` flags. Move clarification answers to database instead.

### SEC-HIGH-5: Docker socket access without service-level authorization
- **File:** `docker_service.py`
- **Description:** Full Docker API access (start/stop/restart/remove/compose up/down) with no authorization layer at the service level. Handler-level admin checks exist, but if any code path bypasses handlers, containers can be manipulated.
- **Remediation:** Add service-level authorization checks or a decorator pattern.

### SEC-HIGH-6: Privilege escalation via sudo systemctl
- **File:** `system_service.py:120-137`
- **Description:** `sudo systemctl restart` is called for ALLOWED_SERVICES. Requires passwordless sudo for the factory user. If sudoers is misconfigured for broader access, this enables privilege escalation.
- **Remediation:** Document exact sudoers rules needed. Use polkit instead of sudo. Consider running service management via a restricted helper script.

---

## MEDIUM Issues

### SEC-MED-1: Unbounded memory consumption in log reading
- **File:** `run_monitor.py:160-163`
- **Description:** `f.read()` reads the entire file delta into memory. If the log grows rapidly (or offset resets to 0 on rotation), this can spike RAM. A compromised factory process can write massive output for DoS.
- **Remediation:** Cap bytes per poll (e.g., 256KB max). Loop until caught up with bounded reads.

### SEC-MED-2: Event/notification amplification via marker spam
- **File:** `run_monitor.py:172-182, 233-269`
- **Description:** Unlimited `[FACTORY:...]` markers can be emitted to the log, causing unbounded DB growth (FactoryEvent rows), Telegram notification spam, and analytics cost ingestion.
- **Remediation:** Rate-limit markers by type per run (token bucket). Enforce max payload sizes.

### SEC-MED-3: Secret leakage via structured logging of marker payloads
- **File:** `run_monitor.py:210-216`
- **Description:** Marker payloads (which may contain URLs, tokens, stack traces) are logged verbatim via `data=marker.data`. This can leak secrets into application logs.
- **Remediation:** Redact/allowlist marker fields before logging. Log only event ID + type + phase.

### SEC-MED-4: Lost update / JSON corruption in clarification answers
- **File:** `factory_runner.py:282-298`
- **Description:** Read-modify-write cycle on `clarification-answers.json` without locking. Concurrent writes cause lost updates. Partial writes leave invalid JSON (silently dropped on decode error).
- **Remediation:** Use atomic file replace (temp + `os.replace()`) with `fcntl.flock`. Or move to database.

### SEC-MED-5: Auth timing side channel
- **File:** `middleware.py:56-68`
- **Description:** `is_authorized` makes a DB query. Authorized users complete faster than unauthorized ones. Timing difference could confirm whitelist membership.
- **Remediation:** Use a cached whitelist with periodic refresh. LOW practical risk since Telegram IDs aren't secrets.

### SEC-MED-6: Default database credentials in code
- **File:** `config.py:27-29`
- **Description:** Default `database_url` contains `factory:factory@localhost` credentials.
- **Remediation:** Require `DATABASE_URL` as mandatory environment variable with no default.

### SEC-MED-7: Callback data injection from untrusted factory logs
- **File:** `notification.py:130-132`
- **Description:** Clarification options from factory log markers are used directly in `callback_data`. Compromised logs could craft malicious callback data (limited by 64-byte Telegram limit).
- **Remediation:** Sanitize and validate callback data before use. Use an ID-based lookup instead.

### SEC-MED-8: Missing `Any` import may crash on annotation evaluation
- **File:** `validators.py:83-86`
- **Description:** `validate_setting_value` uses `Any` in return type but doesn't import it. Protected by `from __future__ import annotations` but may crash if annotations are evaluated at runtime (pydantic, typing introspection).
- **Remediation:** Add `from typing import Any` import.

---

## LOW Issues

### SEC-LOW-1: Dockerfile runs as root
- **File:** `Dockerfile`
- **Description:** Container runs as root user.
- **Remediation:** Add `USER` directive for non-root execution.

### SEC-LOW-2: Docker socket mounted read-write
- **File:** `docker-compose.yml`
- **Description:** Docker socket mounted with full read-write access.
- **Remediation:** Use read-only where container management isn't needed.

### SEC-LOW-3: API keys in long-lived httpx clients
- **File:** `transcription.py:45-53`
- **Description:** API keys stored as headers in long-lived httpx client instances. Memory dump could expose them.
- **Remediation:** Acceptable risk for this deployment model. Consider short-lived clients if paranoid.

### SEC-LOW-4: Backup script exposes DATABASE_URL in process environment
- **File:** `scripts/backup_db.sh`
- **Description:** Uses env var for DATABASE_URL, visible in `/proc/<pid>/environ`.
- **Remediation:** Use `.pgpass` file instead.

---

## Positive Security Observations

- **Telegram whitelist auth** with silent rejection — no information leakage to unauthorized users
- **Factory marker sanitization** (`validators.py:56-62`) — prevents log injection via user input
- **ALLOWED_SERVICES whitelist** (`system_service.py:42`) — limits systemd operations to known services
- **Admin-only checks** on destructive actions (Docker operations, service restart, user management)
- **API key masking** (`config.py:104-118`) — keys never shown in full in Telegram messages
- **Rate limiting** on Telegram notifications with RetryAfter handling
- **No SQL injection vectors** — all queries use SQLAlchemy ORM with parameterized queries
- **No `shell=True`** in any subprocess call — all use `create_subprocess_exec`
