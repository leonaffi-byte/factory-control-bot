# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

## [2.0.0] - 2026-02-21

### Added

#### LLM Provider Integration
- **15+ provider support** — NVIDIA NIM, Groq, Google AI, Together AI, Cerebras, SambaNova, Fireworks AI, Mistral AI, OpenAI, OpenRouter, Perplexity, and GitHub Models
- **LiteLLM adapter** (`providers/litellm_adapter.py`) — OpenAI-compatible interface covering the majority of providers via a single unified client
- **Custom adapters** — Dedicated adapters for Google AI Studio (`google_ai_adapter.py`), SambaNova Cloud (`sambanova_adapter.py`), and clink-based local CLI routing (`clink_adapter.py`)
- **Fallback chain** (`providers/fallback_chain.py`) — Automatic multi-provider failover when a provider is unavailable or rate-limited
- **Provider registry** (`providers/registry.py`) — Central registration and discovery of all configured providers
- **Per-provider rate limiting** (`providers/rate_limiter.py`) — Token bucket rate limiter per provider with configurable limits

#### Model Scanner
- **Model scanner service** (`services/model_scanner.py`) — Scan all configured providers, grade model quality, and produce role-specific suggestions
- **Telegram /scan command** — Trigger model scan and receive graded provider report via Telegram
- **CLI factory scan-models** — Terminal-based model scan with verbose output and optional JSON export

#### clink Routing
- **clink router service** (`services/clink_router.py`) — Route AI inference through local CLI tools (claude, gemini, aider, opencode) instead of remote API keys
- **DEFAULT_ROUTING_MODE setting** — Switch between `api_direct`, `openrouter`, and `clink` at runtime

#### CLI Interface (Typer + Rich)
- **factory run** — Start a factory pipeline run with engine and tier selection
- **factory status** — Show project or specific run status with Rich formatting
- **factory stop** — Terminate a running pipeline by project name or run ID
- **factory list** — List all projects and runs with optional status filter and JSON output
- **factory logs** — View or tail factory logs with configurable line count
- **factory deploy** — Deploy a completed project in Docker or manual mode
- **factory scan-models** — Full provider scan with verbose flag and JSON export
- **factory self-research** — Run autonomous codebase improvement with apply or dry-run flag
- **factory health** — Display system health (CPU, RAM, disk, services) with JSON option
- **factory backup** — Create, list, restore, and prune database backups
- **factory update** — Update the factory application and engine CLIs
- **factory config** — Show or sync environment configuration
- **factory version** — Print version string

#### Multi-Model Orchestrator
- **8 phase executor modules** — Phase 0 (assessment) through Phase 7 (release), each as an independent module
- **Quality gate controller** (`orchestrator/quality_gate.py`) — Configurable pass threshold with automatic retry and escalation logic
- **Run state machine** (`orchestrator/state_machine.py`) — Typed state transitions for pipeline runs
- **Audit logger** (`orchestrator/audit_logger.py`) — Per-run append-only audit trail with model, cost, and decision records
- **Information barrier** (`orchestrator/information_barrier.py`) — Enforced separation between implementer and tester context

#### Self-Research
- **Self-researcher service** (`services/self_researcher.py`) — Autonomous codebase analysis, pattern detection, and improvement proposal generation
- **Telegram /research command** — Trigger self-research and receive findings via Telegram
- **CLI factory self-research** — Terminal-based self-research with --apply flag to write improvements

#### Health Monitoring
- **Health monitor service** (`services/health_monitor.py`) — Continuous CPU, RAM, and disk monitoring with configurable warning and critical thresholds
- **DISK_WARNING_PERCENT / DISK_CRITICAL_PERCENT** settings — Configurable disk usage alert levels
- **Telegram /health command** — On-demand detailed health report
- **CLI factory health** — Terminal health status with optional JSON output

#### Automated Backups
- **Backup service** (`services/backup_service.py`) — Scheduled and manual database backups with retention policy
- **Telegram /backup command** — Backup management via inline keyboard (create, list, restore, prune)
- **CLI factory backup** — Full backup lifecycle from the terminal
- **BACKUP_DIR setting** — Configurable backup storage directory

#### Two-Service Architecture
- **factory-worker.service** — Separate systemd service for background task processing
- **worker.py** — Dedicated entry point for the worker process
- **PostgreSQL LISTEN/NOTIFY** — Event-driven inter-service communication without external message broker
- **Scheduled tasks** — Cron-style task scheduler integrated into the worker service

#### One-Line VPS Installer
- **Installer module** (`installer/`) — Automated VPS setup orchestrating postgres, python, engines, docker, and systemd steps
- **System detector** (`installer/detector.py`) — Pre-flight system capability detection
- **factory install** — Single command to bootstrap a full production environment
- **Installation steps** — Individual step modules for postgres, python, engines, docker, and systemd

#### New Database Tables (v2.0, 9 tables)
- `model_providers` — Registered LLM providers and their configuration
- `model_benchmarks` — Graded model performance records from scanner runs
- `backup_records` — Backup metadata and restoration history
- `scheduled_tasks` — Cron-style task definitions for the worker service
- `self_research_runs` — Self-research session records and findings
- `rate_limit_records` — Per-provider rate limit tracking
- `orchestration_states` — Per-run pipeline state snapshots
- `cost_records` — Fine-grained cost tracking per provider and phase
- `provider_health` — Provider availability and latency history

#### Telegram Commands (new in v2.0)
- `/factory <action>` — Full pipeline control (start, stop, status) via inline menu
- `/scan` — Model provider scan with graded results
- `/research` — Self-research trigger
- `/health` — Detailed health report
- `/backup` — Backup management

#### Settings
- `QUALITY_GATE_THRESHOLD` — Default quality gate pass score (default 97)
- `MAX_QUALITY_RETRIES` — Maximum retries per quality gate (default 3)
- `MAX_FIX_CYCLES` — Maximum fix cycles in Phase 6 (default 5)
- `DEFAULT_ROUTING_MODE` — Model routing mode: api_direct, openrouter, or clink
- `NVIDIA_API_KEY`, `TOGETHER_API_KEY`, `CEREBRAS_API_KEY`, `SAMBANOVA_API_KEY`, `FIREWORKS_API_KEY`, `MISTRAL_API_KEY` — New provider API keys
- `OPENROUTER_DAILY_LIMIT`, `OPENROUTER_WARN_THRESHOLD`, `OPENROUTER_BLOCK_THRESHOLD` — OpenRouter rate management
- `DISK_WARNING_PERCENT`, `DISK_CRITICAL_PERCENT` — Configurable disk alert levels
- `BACKUP_DIR` — Configurable backup storage path
- `TRANSLATION_MODEL`, `REQUIREMENTS_MODEL` — Configurable models for translation and requirements structuring

### Changed

- **Database** — Expanded from 8 tables (v1.0) to 18 tables (v2.0) with 9 new tables for model management, backups, scheduling, and self-research
- **Services layer** — Expanded from 12 services to 22 services with new model routing, scanning, self-research, health monitoring, and backup capabilities
- **README** — Updated to v2.0 with two-service architecture diagram, full CLI command reference, complete environment variable table, and v2.0 provider list
- **pyproject.toml** — Version bumped to 2.0.0
- **docker-compose.yml** — Updated with worker service and v2.0 environment variables
- **deploy.sh** — Enhanced to support docker, manual, and install modes with both service deployments

### Security

- **clink routing isolation** — Local CLI routing mode avoids sending code to remote APIs, improving data sovereignty
- **Provider registry validation** — Provider configurations are validated at startup before accepting any requests
- **Backup file permissions** — Backup files are written with 0o600 permissions (owner-read only)
- **Rate limit enforcement** — Per-provider rate limits prevent runaway API spend
- **OpenRouter block threshold** — Requests are blocked at 95% of daily limit to prevent overage

---

## [1.0.0] - 2026-02-21

### Added

- **Project Creation Wizard** — 13-state ConversationHandler with voice/text input, multi-engine selection, AI-powered requirements structuring, translation, and deployment configuration
- **Factory Run Management** — Start, stop, and pause factory runs via tmux session management with 4 engine support (Claude, Gemini, OpenCode, Aider)
- **Real-Time Log Monitoring** — RunMonitor supervisor with per-run asyncio tasks, `[FACTORY:...]` marker parsing (PHASE, CLARIFY, ERROR, COST, COMPLETE), and push notifications
- **Voice Transcription** — Groq Whisper primary with OpenAI fallback, 3-failure cooldown with 5-minute auto-recovery
- **Docker Management** — List, start, stop, restart, remove containers; compose up/down via aiodocker async API
- **System Health Monitoring** — CPU, RAM, disk monitoring via psutil with configurable alert thresholds and periodic health checks
- **Service Management** — Control systemd services (docker, nginx, postgresql, tailscaled, fail2ban) with ALLOWED_SERVICES whitelist
- **Admin Panel** — Add/remove whitelisted users, role management (admin/user)
- **Analytics** — Cost tracking by provider, phase, and engine with database persistence
- **Settings Management** — Global and per-project settings with type validation
- **Deployment Configuration** — Project type, target platform, domain/SSL, access control
- **Notification Service** — Rate-limited Telegram notifications with RetryAfter handling, message deduplication (SHA-256), token bucket rate limiter
- **Database** — 8 SQLAlchemy async ORM models (users, projects, factory_runs, factory_events, deployments, nodes, settings, analytics), Alembic migrations with auto-run on startup, PTB persistence backed by PostgreSQL
- **Authentication** — Telegram user ID whitelist middleware with silent rejection of unauthorized users
- **Infrastructure** — Multi-stage Dockerfile, docker-compose.yml (bot + PostgreSQL 16), backup script, structured JSON logging via structlog

### Security

- Engine validation prevents command injection in tmux send-keys
- Default-deny for channel posts (effective_user is None)
- Symlink protection on log file reads (realpath verification)
- Path traversal protection on project directory construction
- Atomic file writes for clarification answers (temp + os.replace)
- Factory marker sanitization strips [FACTORY:...] from user input
- 256KB read cap per log poll prevents memory exhaustion
- ALLOWED_SERVICES whitelist for systemd operations
- API key masking in all display contexts
- No shell=True in any subprocess call

[Unreleased]: https://github.com/user/factory-control-bot/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/user/factory-control-bot/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/user/factory-control-bot/releases/tag/v1.0.0
