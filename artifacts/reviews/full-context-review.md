# Full Context Review — Factory Control Bot
## Reviewer: Gemini 2.5 Pro (Google, 1M context) via zen MCP
## Date: 2026-02-21
## Scope: Entire codebase holistic review (~7,155 lines Python, 64 backend files, 10 test files)

---

## Executive Summary

The application follows a modular monolith architecture with a clean service layer, which is a strong foundation. Configuration, logging, and basic application lifecycle management are well-handled. The most significant issues are **blocking I/O calls within async functions** (particularly in RunMonitor and FactoryRunner), and some **inconsistencies in the log marker grammar**. The auth and notification layers are robust. Core functionality is well-implemented.

---

## 1. Architecture Assessment

### Strengths
- **Modular Monolith**: Well-organized into `bot`, `services`, `database`, and `utils` layers
- **ServiceContainer**: Central dependency injection pattern works well within PTB framework
- **Handler Registration**: Clean separation with auth middleware at group -1, conversation handlers, command handlers, and callback query handlers in proper order
- **No Circular Dependencies**: Import structure is clean with proper TYPE_CHECKING guards

### Weaknesses
- **tmux Dependency**: Factory execution relies on tmux for process management. While practical, it lacks automatic restarts, resource management, and scalability compared to container-based solutions
- **No Health Endpoint**: The bot has periodic health checks but no external health endpoint for monitoring systems to probe

### Recommendation
Consider adding a lightweight HTTP health endpoint (e.g., via aiohttp) for external monitoring tools to verify bot liveness.

---

## 2. Consistency Check

### Strengths
- **Logging**: Excellent consistency with `structlog` throughout all modules. Structured log messages follow `snake_case` event naming convention
- **Error Handling**: Consistent pattern of try/except with structured logging at service level, user-friendly messages at handler level
- **Naming**: Clear, predictable naming across services, handlers, and models

### Weaknesses
- **Log Marker Grammar**: Inconsistent format — some markers use colon-separated values (`PHASE`, `COST`), others expect JSON payloads (`CLARIFY`, `COMPLETE`). This complicates parsing logic.
  - **Current**: `[FACTORY:PHASE:3:END:98]` and `[FACTORY:COST:1.50:openai]`
  - **Proposed**: Uniform JSON: `[FACTORY:PHASE_END:{"phase":3,"score":98}]`
- **Input Sanitization Applied Inconsistently**: `sanitize_user_input()` is called in `req_text_input` but not in `desc_text_input` or `req_edit_text`. Factory markers could be injected via description or edited requirements.

---

## 3. Async Correctness

### CRITICAL: Blocking File I/O in async functions

| Location | Issue |
|----------|-------|
| `run_monitor.py:143-163` | `os.path.exists`, `os.path.getsize`, `open()` — all blocking |
| `factory_runner.py:130` | `stop_file.touch()` — blocking |
| `factory_runner.py:161` | `pause_file.touch()` — blocking |
| `factory_runner.py:284-297` | `answers_file.exists()`, `read_text()`, `write_text()` — blocking |

These blocking calls will freeze the event loop, making the bot unresponsive.

**Fix**: Wrap in `asyncio.to_thread()` (Python 3.9+) or `loop.run_in_executor(None, ...)`. Note that `_create_project_dir` already does this correctly (line 322), providing a template.

### Deprecated API Usage
- `asyncio.get_event_loop()` used in `main.py:66`, `factory_runner.py:322,348` — should be `asyncio.get_running_loop()`
- `datetime.utcnow()` used in 4 locations — deprecated in Python 3.12+

### Race Condition
- `factory_runner.py:133` uses `await asyncio.sleep(5)` to wait for graceful shutdown. This is unreliable — should poll tmux session status with timeout.

---

## 4. Completeness Check

### Implemented (per spec)
- Project creation wizard (13-state ConversationHandler)
- Multi-engine selection (claude, gemini, opencode, aider)
- Voice transcription with Groq primary / OpenAI fallback
- Translation + AI requirements structuring
- Factory run management (start/stop/pause via tmux)
- Real-time log monitoring with event parsing
- Push notifications with rate limiting
- Clarification question forwarding
- Docker container management (list/start/stop/restart/remove/logs)
- System health monitoring (CPU/RAM/disk/uptime)
- Service status and management (docker, nginx, postgresql, tailscaled, fail2ban)
- Admin panel (add/remove whitelisted users)
- Settings management (global + per-project)
- Analytics recording (cost by provider/phase)
- Deployment configuration (project type, target, access)

### Partial / Stub
- **Analytics Dashboard**: Cost recording exists but no chart generation or aggregate views
- **Engine Update**: `/update-engines` and `/engine-status` commands not implemented
- **Multi-Node**: Schema supports it (Node model) but commands not implemented (future-ready as spec intended)
- **Voice Input conversation module**: `voice_input.py` exists but is separate from the ConversationHandler flow

### Missing
- **Domain/SSL auto-configuration**: Not yet implemented
- **Live message editing** for real-time monitoring (MessageSession exists in NotificationService but not wired up)
- **Rate limit tracking** for OpenRouter (config exists but no tracking service)

---

## 5. Database Design

### Strengths
- 8 SQLAlchemy models covering all spec entities (users, projects, factory_runs, factory_events, deployments, nodes, settings, analytics)
- Proper use of UUID primary keys
- JSON columns for flexible data (settings_json, cost_by_provider, capabilities_json)

### Concerns
- **Missing indexes**: `factory_runs.status` and `factory_events.run_id` likely need indexes for common query patterns
- **Missing `log_file_path` property**: RunMonitor references `run.log_file_path` which doesn't exist on the model — needs a `@property` that constructs from `project_dir`
- **No cascade deletes**: Relationships between models don't specify cascade behavior

---

## 6. Edge Cases

| Scenario | Handling |
|----------|----------|
| Groq API down | Falls back to OpenAI. After 3 failures, 5-min cooldown. Good. |
| OpenAI also down | Raises `TranscriptionError`, user sees error message. Good. |
| Docker daemon unavailable | `DockerError` raised, shown to user. Good. |
| tmux not installed | `FileNotFoundError` caught, logged as warning. Run returns empty list. Good. |
| Disk >90% | Health check sends CRITICAL alert, disk_critical setting blocks new projects. Good. |
| Telegram rate limit | RetryAfter exception caught, sleeps and retries once. Good. |
| Factory log file missing | Monitor increments consecutive_empty counter, continues polling. Good. |
| Factory tmux session dies | Detected via periodic tmux session check, marked as failed, user notified. Good. |
| Bot crash during factory run | On restart, `reconcile_orphaned_runs` re-attaches monitors or marks runs failed. Excellent. |

---

## 7. Production Readiness

### Ready
- Structured logging with JSON output
- Graceful lifecycle (post_init/post_shutdown hooks)
- Orphaned run reconciliation on startup
- Periodic health checks (disk, memory)
- Docker + docker-compose deployment
- Alembic migrations
- Database backup script
- Environment-based configuration via pydantic-settings

### Needs Improvement
- **Blocking I/O** in async context (top priority)
- **Missing database indexes** for query performance
- **No external health endpoint** for monitoring systems
- **Polling mode** instead of webhooks (acceptable for internal tool)
- **No rate limit tracking service** for OpenRouter
- **No structured error codes** for API-like error responses

---

## Conclusion

The codebase is well-architected with solid foundations. The primary issues to address before production deployment are:

1. **Fix blocking I/O in async functions** (run_monitor.py, factory_runner.py)
2. **Add missing `log_file_path` property** to FactoryRun model
3. **Apply input sanitization consistently** across all text input handlers
4. **Add database indexes** for common query patterns
5. **Validate engine names** at the runner level (defense-in-depth)

Overall quality: **Good** — with the above fixes, the codebase is production-ready.
