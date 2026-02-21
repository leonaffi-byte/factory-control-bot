# Code Review — Factory Control Bot
## Reviewer: O3 (OpenAI) via zen MCP
## Date: 2026-02-21
## Scope: Full codebase (~7,155 lines Python, 64 backend files)

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH     | 1     |
| MEDIUM   | 6     |
| LOW      | 3     |
| **Total**| **10**|

The codebase is a well-structured modular monolith with clean separation of concerns, consistent structured logging via structlog, and good use of async patterns. The architecture is sound for a Tier 3 project. Key issues involve deprecated API usage, a potential null-reference bug, and performance concerns with sequential Docker stats fetching.

---

## Architecture Assessment

**Strengths:**
- Clean modular monolith: `config` -> `bot` layer (handlers/conversations/keyboards) -> `services` (12 classes) -> `models` (8 SQLAlchemy) -> `database` (engine/session/persistence) -> `utils`
- ServiceContainer pattern for dependency injection via `bot_data`
- Auth middleware at handler group -1 with silent rejection (per security spec)
- ConversationHandler with 13 states for project creation wizard
- RunMonitor supervisor with per-run asyncio tasks for log file watching
- Proper PTB persistence backed by PostgreSQL

**No circular dependencies detected.**

---

## Issues

### HIGH-1: Missing `log_file_path` property on FactoryRun model
- **File:** `run_monitor.py:94`
- **Description:** `run.log_file_path` is used but not defined as a model column or property on the FactoryRun SQLAlchemy model. If `project_dir` is None, this will fail silently and the monitor loop will exit without notification.
- **Fix:** Add a `@property` method to FactoryRun that constructs the log file path from `project_dir`, e.g., `return f"{self.project_dir}/artifacts/reports/factory-run.log"` with None-safety.

### MEDIUM-1: Command injection defense gap in engine fallback
- **File:** `factory_runner.py:366`
- **Description:** `ENGINE_COMMANDS` fallback uses `echo 'Unknown engine: {engine}'` sent via `tmux send-keys`. While engines are validated from a fixed list in `new_project.py`, no validation exists at the runner level.
- **Fix:** Add `if engine not in ENGINE_COMMANDS: raise ValueError(f"Unknown engine: {engine}")` before the tmux call. Remove the echo fallback.

### MEDIUM-2: Deprecated `datetime.utcnow()` usage
- **File:** `factory_runner.py:95, 206, 220, 294`
- **Description:** `datetime.utcnow()` is deprecated in Python 3.12+.
- **Fix:** Replace with `datetime.now(timezone.utc)`.

### MEDIUM-3: Deprecated `asyncio.get_event_loop()` usage
- **File:** `main.py:66`, `factory_runner.py:322,348`
- **Description:** `asyncio.get_event_loop()` is deprecated in Python 3.10+ in favor of `asyncio.get_running_loop()`.
- **Fix:** Replace with `asyncio.get_running_loop()`.

### MEDIUM-4: Sequential Docker stats fetching
- **File:** `docker_service.py:52-66`
- **Description:** `list_containers` fetches stats for every container sequentially, creating a waterfall of API calls. With many containers, this creates significant latency.
- **Fix:** Use `asyncio.gather()` to fetch stats in parallel.

### MEDIUM-5: Symlink vulnerability in log file reads
- **File:** `run_monitor.py:160`
- **Description:** Log files are opened with plain `open()` without checking for symlinks. Path could be manipulated if project directory is compromised.
- **Fix:** Use `os.path.realpath()` and verify the resolved path stays within `factory_root_dir`.

### MEDIUM-6: Potential NoneType error on `query.message`
- **File:** `new_project.py:469`
- **Description:** `query.message.reply_text` is called after `query.edit_message_text`. If `query.message` is None (edge case with expired callback queries), this will raise AttributeError.
- **Fix:** Add null check: `if query and query.message:`.

### LOW-1: Private API access in aiodocker
- **File:** `docker_service.py:148`
- **Description:** Accesses `container._container` private attribute. Fragile across aiodocker version upgrades.
- **Fix:** Use `await container.show()` to get container info dict.

### LOW-2: MD5 for message deduplication
- **File:** `notification.py:47`
- **Description:** Uses MD5 for message change detection hashing. Not a security concern (just dedup), but MD5 is deprecated.
- **Fix:** Replace with `hashlib.sha256()`.

### LOW-3: `get_settings()` not cached
- **File:** `config.py:124`
- **Description:** Creates a new `Settings()` instance on every call, re-reading environment variables.
- **Fix:** Use `@functools.lru_cache(maxsize=1)` or a module-level singleton.

---

## Positive Observations

- Structured logging with structlog throughout — excellent observability
- Proper use of pydantic for data validation and DTOs
- Rate limiting in NotificationService with RetryAfter handling
- Factory marker sanitization in user input (`validators.py:56-62`)
- Admin-only checks on destructive actions (Docker stop/restart/remove, service restart)
- ALLOWED_SERVICES whitelist for systemd operations (`system_service.py:42`)
- Proper error propagation with custom exception types (DockerError, TranscriptionError)
- Good ConversationHandler design with proper state management and fallbacks
