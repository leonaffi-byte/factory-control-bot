# Factory Control Bot v2.0

A unified AI software factory platform with a Telegram bot and CLI interface. Factory Control Bot v2.0 orchestrates multi-model AI pipelines across 15+ free and paid LLM providers to build production-quality software with cross-provider verification and information barriers.

## Features

### Core Pipeline
- **7-phase orchestration** — Complexity assessment, requirements, brainstorm, architecture, implementation, review, test/fix, and release phases
- **Quality gates** — Configurable pass threshold (default 97/100) with automatic retry and escalation
- **Information barriers** — Testers never see implementation code; implementers never see tests
- **Cross-provider verification** — Code written by one AI provider is reviewed by a different provider
- **8 orchestrator phase executors** — Each phase is a standalone module (phase0 through phase7)

### LLM Provider Integration
- **15+ provider support** — NVIDIA NIM, Groq, Google AI, Together AI, Cerebras, SambaNova, Fireworks, Mistral, OpenAI, OpenRouter, and more
- **LiteLLM adapter** — OpenAI-compatible interface for most providers
- **Custom adapters** — Dedicated adapters for Google AI, SambaNova, and clink-based routing
- **Model scanner** — Scan all configured providers, grade models, and get role-specific suggestions
- **Fallback chains** — Automatic failover between providers when one is unavailable
- **OpenRouter rate limiting** — Daily request cap with configurable warn/block thresholds

### Interfaces
- **Telegram bot** — 18 commands for mobile-first pipeline control
- **CLI (Typer + Rich)** — 13 commands with subcommands for terminal-based workflow
- **Project creation wizard** — 13-state conversation handler with voice and text input

### Infrastructure
- **Two-service architecture** — `factory-bot.service` (Telegram + API) and `factory-worker.service` (background tasks)
- **PostgreSQL LISTEN/NOTIFY** — Event-driven cross-service communication
- **One-line VPS installation** — `factory install` bootstraps the full environment
- **clink routing** — Route AI calls through local CLIs (claude, gemini, aider) instead of API keys
- **Docker Compose deployment** — `docker compose up -d` for full stack

### Monitoring and Maintenance
- **Health monitoring** — CPU, RAM, disk metrics with configurable alert thresholds
- **Automated backups** — Scheduled database backups with CLI and Telegram management
- **Cost tracking** — Per-project, per-provider, per-phase cost analytics
- **Self-research** — Autonomous codebase analysis and improvement suggestions
- **Real-time log tailing** — Live `[FACTORY:...]` marker parsing with push notifications
- **Voice input** — Groq Whisper primary with OpenAI fallback and automatic cooldown

### Security
- Telegram user ID whitelist with silent rejection of unauthorized users
- Factory marker sanitization to prevent log injection via user input
- Engine validation to prevent command injection in tmux sessions
- Symlink protection on log file reads
- Path traversal protection on project directory construction
- Atomic file writes for clarification answers (temp file + os.replace)
- ALLOWED_SERVICES whitelist for systemd operations
- API key masking in all display contexts
- No `shell=True` in any subprocess call
- Parameterized SQL queries via SQLAlchemy ORM

---

## Architecture

```
Factory Control Bot v2.0 — Two-Service Architecture

  ┌─────────────────────────────────────────────────────┐
  │                   factory-bot.service                │
  │                                                      │
  │  Telegram Bot          CLI (factory <cmd>)           │
  │  (python-telegram-bot) (Typer + Rich)                │
  │         │                      │                     │
  │         └──────────┬───────────┘                     │
  │                    │                                  │
  │              App Services                            │
  │  factory_orchestrator  model_router  model_scanner   │
  │  factory_runner        clink_router  self_researcher  │
  │  run_monitor           health_monitor backup_service │
  │  notification          transcription  translation    │
  │  user_service          project_service analytics     │
  │                    │                                  │
  │              PostgreSQL (asyncpg)                    │
  │              LISTEN/NOTIFY pub/sub                   │
  └────────────────────┬────────────────────────────────┘
                       │ pg_notify
  ┌────────────────────▼────────────────────────────────┐
  │                factory-worker.service                │
  │                                                      │
  │  Background task processor                          │
  │  Scheduled tasks (cron-style)                       │
  │  Async job queue consumer                           │
  └─────────────────────────────────────────────────────┘

  External Providers (via LiteLLM + custom adapters)
  ┌──────────────────────────────────────────────────────┐
  │ NVIDIA  Groq  Google  Together  Cerebras  SambaNova  │
  │ Fireworks  Mistral  OpenAI  OpenRouter  Perplexity   │
  │ clink (local CLI routing: claude, gemini, aider)     │
  └──────────────────────────────────────────────────────┘
```

### Codebase Structure

```
app/
├── bot/                        # Telegram bot layer
│   ├── application.py          # PTB Application builder
│   ├── middleware.py            # Auth whitelist middleware
│   ├── conversations/          # ConversationHandlers
│   ├── handlers/               # Command and callback handlers
│   └── keyboards/              # Inline keyboard builders
├── cli/                        # Typer CLI layer
│   ├── main.py                 # Root CLI app + command registration
│   ├── commands/               # 12 command modules
│   └── output/                 # Rich formatting helpers
├── services/                   # Business logic (22 service classes)
│   ├── factory_orchestrator.py # Phase 0-7 pipeline controller
│   ├── factory_runner.py       # tmux-based factory lifecycle
│   ├── run_monitor.py          # Log file watcher + event dispatcher
│   ├── model_router.py         # Provider routing and fallback
│   ├── model_scanner.py        # Provider scan, grade, suggest
│   ├── clink_router.py         # Local CLI routing adapter
│   ├── self_researcher.py      # Autonomous codebase improvement
│   ├── health_monitor.py       # CPU/RAM/disk monitoring
│   ├── backup_service.py       # Automated database backups
│   ├── cost_tracker.py         # Per-project cost tracking
│   ├── notification.py         # Rate-limited Telegram push
│   ├── transcription.py        # Groq/OpenAI Whisper with fallback
│   ├── translation.py          # Auto-detect + translate
│   ├── docker_service.py       # Container management via aiodocker
│   ├── system_service.py       # Health checks + systemd control
│   └── ...                     # project, user, analytics, settings
├── orchestrator/               # Pipeline phase executors
│   ├── phases/                 # phase0 through phase7 modules
│   ├── quality_gate.py         # Scoring and retry logic
│   ├── state_machine.py        # Run state transitions
│   ├── audit_logger.py         # Per-run audit trail
│   └── information_barrier.py  # Cross-agent isolation
├── providers/                  # LLM provider adapters
│   ├── litellm_adapter.py      # OpenAI-compatible providers
│   ├── google_ai_adapter.py    # Google AI Studio adapter
│   ├── sambanova_adapter.py    # SambaNova Cloud adapter
│   ├── clink_adapter.py        # Local CLI routing adapter
│   ├── fallback_chain.py       # Multi-provider fallback
│   ├── rate_limiter.py         # Per-provider rate limiting
│   └── registry.py             # Provider registration
├── installer/                  # VPS one-line installer
│   ├── runner.py               # Installation step orchestrator
│   ├── detector.py             # System capability detection
│   └── steps/                  # postgres, python, engines, docker, systemd
├── models/                     # SQLAlchemy ORM models (18 tables)
├── database/                   # Engine, session factory, PTB persistence
├── utils/                      # Log parser, validators, formatting
├── config.py                   # Pydantic settings (all env vars)
├── main.py                     # Bot entry point
└── worker.py                   # Worker service entry point
```

---

## Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Runtime | Python | 3.12+ |
| Bot framework | python-telegram-bot | 21.5+ |
| CLI framework | Typer + Rich | latest |
| Database ORM | SQLAlchemy async | 2.0+ |
| DB driver | asyncpg | 0.29+ |
| Migrations | Alembic | 1.13+ |
| LLM routing | LiteLLM | latest |
| Config | pydantic-settings | 2.3+ |
| HTTP client | httpx | 0.27+ |
| Docker API | aiodocker | 0.22+ |
| System metrics | psutil | 5.9+ |
| Logging | structlog (JSON) | 24.1+ |
| Database | PostgreSQL | 16+ |
| Container runtime | Docker + Compose | 24+ / 2.20+ |
| Production service | systemd | — |

---

## Quick Start

### Docker Deployment (Recommended)

```bash
# 1. Navigate to the backend directory
cd factory-control-bot/artifacts/code/backend

# 2. Create environment file
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_ID at minimum

# 3. Create required directories
sudo mkdir -p /home/factory/projects /home/factory/backups/db
sudo chown -R $(whoami):$(whoami) /home/factory

# 4. Start all services (bot + PostgreSQL)
docker compose up -d

# 5. Verify
docker compose ps
docker compose logs -f bot
```

### Manual Deployment

```bash
# 1. Install system dependencies (Ubuntu 22.04+)
sudo apt install -y python3.12 python3.12-venv postgresql-16 tmux git

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Set up PostgreSQL
sudo -u postgres createuser factory
sudo -u postgres createdb factory_bot -O factory
sudo -u postgres psql -c "ALTER USER factory PASSWORD 'your-password';"

# 4. Configure environment
export TELEGRAM_BOT_TOKEN="your-bot-token"
export ADMIN_TELEGRAM_ID="your-telegram-id"
export DATABASE_URL="postgresql+asyncpg://factory:your-password@localhost:5432/factory_bot"

# 5. Start bot (migrations run automatically on first boot)
python -m app.main

# 6. In a separate terminal, start the worker
python -m app.worker
```

### CLI Setup

```bash
# Install CLI into active venv
pip install -e .

# The factory command is now available
factory --help
factory version

# Add to PATH permanently (if not using venv activation)
echo 'export PATH="/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## CLI Commands Reference

| Command | Arguments / Options | Description |
|---------|---------------------|-------------|
| `factory run <project>` | `--engine X`, `--tier N` | Start a factory pipeline run |
| `factory status [project]` | — | Show project or run status |
| `factory stop <project\|run-id>` | — | Stop a running pipeline |
| `factory list` | `--status X`, `--json` | List all projects and runs |
| `factory logs <project>` | `--follow`, `--lines N` | View or tail project logs |
| `factory deploy <project>` | `--docker`, `--manual` | Deploy a completed project |
| `factory scan-models` | `--verbose`, `--force`, `--json` | Scan and grade all AI model providers |
| `factory self-research` | `--apply`, `--dry-run` | Run autonomous codebase improvement |
| `factory health` | `--json` | Show system health status |
| `factory backup` | `--type manual` | Create a database backup |
| `factory backup restore <id>` | — | Restore a backup by ID |
| `factory backup list-backups` | — | List available backups |
| `factory backup prune` | — | Remove old backups |
| `factory update` | `--engines-only` | Update the factory and engine CLIs |
| `factory config show` | — | Display current configuration |
| `factory config sync` | — | Sync config to environment |
| `factory version` | — | Print version |

---

## Telegram Commands Reference

| Command | Description | Access |
|---------|-------------|--------|
| `/start` | Main menu with inline keyboard | All users |
| `/new` | Start project creation wizard | All users |
| `/projects` | List all projects | All users |
| `/status` | System status overview | All users |
| `/factory <action>` | Factory pipeline control | Admin |
| `/scan` | Scan and grade model providers | Admin |
| `/research` | Run self-research and improvement | Admin |
| `/health` | Detailed health report | Admin |
| `/backup` | Backup management menu | Admin |
| `/docker` | Docker container management | Admin |
| `/services` | Systemd service management | Admin |
| `/analytics` | Cost and usage analytics | All users |
| `/settings` | Global and per-project settings | Admin |
| `/admin` | User whitelist management | Admin |
| `/help` | Command reference | All users |

---

## Environment Variables

See [DEPLOYMENT.md](../../docs/DEPLOYMENT.md) for the complete reference with example values.

### Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token (from @BotFather) |
| `ADMIN_TELEGRAM_ID` | Admin's Telegram numeric user ID |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://factory:factory@localhost:5432/factory_bot` | PostgreSQL async connection string |
| `DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `5` | Max overflow connections above pool size |
| `DB_POOL_RECYCLE` | `3600` | Recycle connections after N seconds |

### API Keys (v1.0 providers)

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq — voice transcription (primary) |
| `OPENAI_API_KEY` | OpenAI — Whisper fallback + translation |
| `OPENROUTER_API_KEY` | OpenRouter — free model access |
| `GOOGLE_API_KEY` | Google AI Studio — Gemini models |
| `PERPLEXITY_API_KEY` | Perplexity — research queries |
| `GITHUB_TOKEN` | GitHub — repo management |

### API Keys (v2.0 providers)

| Variable | Description |
|----------|-------------|
| `NVIDIA_API_KEY` | NVIDIA NIM API |
| `TOGETHER_API_KEY` | Together AI |
| `CEREBRAS_API_KEY` | Cerebras Cloud |
| `SAMBANOVA_API_KEY` | SambaNova Cloud |
| `FIREWORKS_API_KEY` | Fireworks AI |
| `MISTRAL_API_KEY` | Mistral AI |

### Factory Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `FACTORY_ROOT_DIR` | `/home/factory/projects` | Root directory for all factory projects |
| `TEMPLATES_DIR` | `/app/templates` | Engine config and prompt templates |
| `DEFAULT_ENGINE` | `claude` | Default engine for new projects |
| `QUALITY_GATE_THRESHOLD` | `97` | Quality gate pass threshold (0-100) |
| `MAX_QUALITY_RETRIES` | `3` | Max retries per quality gate |
| `MAX_FIX_CYCLES` | `5` | Max fix cycles in Phase 6 |
| `COST_ALERT_THRESHOLD` | `50.0` | Alert when project cost exceeds this (USD) |
| `DEFAULT_ROUTING_MODE` | `api_direct` | Model routing: `api_direct`, `openrouter`, or `clink` |

### Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_POLL_INTERVAL` | `3` | Seconds between log file polls |
| `MAX_CONCURRENT_MONITORS` | `10` | Max simultaneous monitored runs |
| `HEALTH_CHECK_INTERVAL` | `300` | Seconds between health checks |
| `IDLE_TIMEOUT_MINUTES` | `10` | Minutes before a run is considered stuck |
| `DISK_WARNING_PERCENT` | `80` | Disk usage percent to trigger warning |
| `DISK_CRITICAL_PERCENT` | `90` | Disk usage percent to trigger critical alert |
| `BACKUP_DIR` | `/home/factory/backups` | Directory for automated backups |

### Translation and Transcription

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_PROVIDER` | `auto` | Transcription provider: `groq`, `openai`, or `auto` |
| `TRANSLATION_MODEL` | `gpt-4o-mini` | Model for requirement translation |
| `REQUIREMENTS_MODEL` | `gpt-4o-mini` | Model for requirements structuring |

### OpenRouter Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_DAILY_LIMIT` | `200` | Max daily OpenRouter requests |
| `OPENROUTER_WARN_THRESHOLD` | `0.8` | Warn at this fraction of daily limit |
| `OPENROUTER_BLOCK_THRESHOLD` | `0.95` | Block new runs at this fraction |

### Deployment

| Variable | Default | Description |
|----------|---------|-------------|
| `DOMAIN_NAME` | `null` | Registered domain for web deployments |
| `SSL_EMAIL` | `null` | Email for certbot SSL certificate |
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |

---

## Database

Alembic migrations run automatically on every startup via a `post_init` hook. No manual migration step is required.

The v2.0 schema includes 18 tables:

**v1.0 tables (9):** `users`, `projects`, `factory_runs`, `factory_events`, `deployments`, `nodes`, `settings`, `analytics`, `api_usage`

**v2.0 tables (9):** `model_providers`, `model_benchmarks`, `backup_records`, `scheduled_tasks`, `self_research_runs`, `rate_limit_records`, `orchestration_states`, `cost_records`, `provider_health`

---

## Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all 264 tests
PYTHONPATH=. python -m pytest tests/ -v

# Run only unit tests (no DB required)
PYTHONPATH=. python -m pytest tests/ -m unit -v

# Run integration tests (requires PostgreSQL)
PYTHONPATH=. python -m pytest tests/ -m integration -v

# Run with coverage report
PYTHONPATH=. python -m pytest tests/ -v --cov=app --cov-report=term-missing

# Run a specific test file
PYTHONPATH=. python -m pytest tests/unit/test_log_parser.py -v
```

---

## Security

- **Whitelist auth**: Only Telegram user IDs in the whitelist receive responses. All others are silently ignored.
- **Input sanitization**: `[FACTORY:...]` markers are stripped from user input to prevent log injection.
- **Engine validation**: Engine names are validated against an allowlist before use in tmux send-keys.
- **No shell injection**: All subprocess calls use argument lists; `shell=True` is never used.
- **Symlink protection**: Log file reads verify the resolved path matches the expected project directory.
- **Path traversal prevention**: Project directory construction sanitizes user-supplied names.
- **Atomic writes**: Clarification answer files are written via temp file + `os.replace` for crash safety.
- **Service allowlist**: Systemd operations are restricted to `ALLOWED_SERVICES` (docker, nginx, postgresql, tailscaled, fail2ban).
- **Key masking**: API keys are masked (`abcd...wxyz`) in all Telegram and log output.
- **Parameterized queries**: All database access uses SQLAlchemy ORM; no raw SQL interpolation.

---

## License

Private — internal use only.
