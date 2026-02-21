# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

## [1.0.0] - 2026-02-21

### Added
- **Project Creation Wizard**: 13-state ConversationHandler with voice/text input, multi-engine selection, AI-powered requirements structuring, translation, deployment config
- **Factory Run Management**: Start, stop, pause factory runs via tmux session management with 4 engine support (Claude, Gemini, OpenCode, Aider)
- **Real-Time Log Monitoring**: RunMonitor supervisor with per-run asyncio tasks, [FACTORY:...] marker parsing (PHASE, CLARIFY, ERROR, COST, COMPLETE), push notifications
- **Voice Transcription**: Groq Whisper primary with OpenAI fallback, 3-failure cooldown with 5-minute auto-recovery
- **Docker Management**: List, start, stop, restart, remove containers; compose up/down via aiodocker async API
- **System Health Monitoring**: CPU, RAM, disk monitoring via psutil with configurable alert thresholds and periodic health checks
- **Service Management**: Control systemd services (docker, nginx, postgresql, tailscaled, fail2ban) with ALLOWED_SERVICES whitelist
- **Admin Panel**: Add/remove whitelisted users, role management (admin/user)
- **Analytics**: Cost tracking by provider, phase, and engine with database persistence
- **Settings Management**: Global and per-project settings with type validation
- **Deployment Configuration**: Project type, target platform, domain/SSL, access control
- **Notification Service**: Rate-limited Telegram notifications with RetryAfter handling, message deduplication (SHA-256), token bucket rate limiter
- **Database**: 8 SQLAlchemy async ORM models (users, projects, factory_runs, factory_events, deployments, nodes, settings, analytics), Alembic migrations (auto-run on startup), PTB persistence backed by PostgreSQL
- **Authentication**: Telegram user ID whitelist middleware with silent rejection
- **Infrastructure**: Multi-stage Dockerfile, docker-compose.yml (bot + PostgreSQL 16), backup script, structured JSON logging via structlog

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

[Unreleased]: https://github.com/user/factory-control-bot/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/user/factory-control-bot/releases/tag/v1.0.0
