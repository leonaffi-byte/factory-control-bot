# Factory Control Bot

A Telegram bot that serves as the command-and-control interface for the Black Box Software Factory v2. It replaces SSH-based workflows with a mobile-first experience for managing AI-powered software generation.

## Features

- **Project Creation Wizard** — 13-state conversation handler for creating projects via text or voice input
- **Multi-Engine Support** — Run projects with Claude, Gemini, OpenCode, or Aider in parallel
- **Real-Time Monitoring** — Live log watching with `[FACTORY:...]` marker parsing and push notifications
- **Docker Management** — List, start, stop, restart, remove containers and manage compose stacks
- **System Health** — CPU, RAM, disk monitoring with automatic alerts at configurable thresholds
- **Service Management** — Control systemd services (docker, nginx, postgresql, tailscaled, fail2ban)
- **Voice Input** — Groq Whisper primary with OpenAI fallback (3-failure cooldown, auto-switch)
- **Translation** — Auto-detect and translate non-English requirements via OpenRouter
- **Analytics** — Cost tracking by provider, phase, and engine with per-project breakdowns
- **Admin Panel** — Whitelist management, user roles, global settings
- **Deployment Config** — Project type, target platform, domain/SSL, access control per project

## Tech Stack

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.12+ |
| Bot Framework | python-telegram-bot 21.5+ (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async ORM) + asyncpg |
| Migrations | Alembic |
| Docker | aiodocker (async Docker API) |
| HTTP Client | httpx (async, for Groq/OpenAI/OpenRouter APIs) |
| Monitoring | psutil |
| Logging | structlog (JSON) |
| Config | pydantic-settings (.env) |
| Deployment | Docker Compose |

## Architecture

```
app/
├── bot/                    # Telegram bot layer
│   ├── application.py      # PTB Application builder
│   ├── middleware.py        # Auth whitelist middleware
│   ├── conversations/      # ConversationHandlers (new_project, voice_input)
│   ├── handlers/           # Command & callback handlers
│   └── keyboards/          # Inline keyboard builders
├── services/               # Business logic (12 service classes)
│   ├── factory_runner.py   # tmux-based factory lifecycle
│   ├── run_monitor.py      # Log file watcher + event dispatcher
│   ├── notification.py     # Rate-limited Telegram notifications
│   ├── transcription.py    # Groq/OpenAI Whisper with fallback
│   ├── docker_service.py   # Container management via aiodocker
│   ├── system_service.py   # Health checks + systemd control
│   └── ...                 # project, user, analytics, settings, translation
├── models/                 # SQLAlchemy ORM models (8 tables)
├── database/               # Engine, session factory, PTB persistence
├── utils/                  # Log parser, validators, formatting
├── config.py               # Pydantic settings
└── main.py                 # Entry point
```

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Docker & Docker Compose
- tmux
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Docker Deployment (Recommended)

```bash
# 1. Clone and navigate
cd factory-control-bot/artifacts/code/backend

# 2. Create .env file
cp .env.example .env
# Edit .env with your tokens and settings

# 3. Start services
docker compose up -d

# 4. Check logs
docker compose logs -f bot
```

### Manual Deployment

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up PostgreSQL
createdb factory_bot

# 4. Configure environment
export TELEGRAM_BOT_TOKEN="your-token"
export ADMIN_TELEGRAM_ID="your-telegram-id"
export DATABASE_URL="postgresql+asyncpg://factory:password@localhost:5432/factory_bot"

# 5. Run
python -m app.main
```

## Database Migrations

Alembic migrations run automatically on startup (`post_init` hook). No manual migration step is required. On first boot, all 8 tables are created automatically.

## Environment Variables

See [DEPLOYMENT.md](../../docs/DEPLOYMENT.md) for the complete reference. Key variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram Bot API token |
| `ADMIN_TELEGRAM_ID` | Yes | — | Admin's Telegram user ID |
| `DATABASE_URL` | No | `postgresql+asyncpg://factory:factory@localhost:5432/factory_bot` | PostgreSQL connection string |
| `DB_POOL_SIZE` | No | `10` | SQLAlchemy connection pool size |
| `GROQ_API_KEY` | No | — | Groq API key for Whisper transcription |
| `OPENAI_API_KEY` | No | — | OpenAI API key for Whisper fallback |
| `OPENROUTER_API_KEY` | No | — | OpenRouter API key for translation |
| `GOOGLE_API_KEY` | No | — | Google API key for Gemini engine |
| `PERPLEXITY_API_KEY` | No | — | Perplexity API key for research |
| `GITHUB_TOKEN` | No | — | GitHub token for repo management |
| `FACTORY_ROOT_DIR` | No | `/home/factory/projects` | Root directory for factory projects |
| `TEMPLATES_DIR` | No | `/app/templates` | Engine config templates directory |
| `DEFAULT_ENGINE` | No | `claude` | Default engine for new projects |
| `VOICE_PROVIDER` | No | `auto` | Transcription: groq, openai, or auto |
| `COST_ALERT_THRESHOLD` | No | `50.0` | Alert when project cost exceeds this |
| `MAX_CONCURRENT_MONITORS` | No | `10` | Max simultaneous monitored runs |
| `LOG_LEVEL` | No | `INFO` | Application log level |

## Bot Commands

| Command | Description | Access |
|---------|-------------|--------|
| `/start` | Main menu with inline keyboard | All users |
| `/new` | Start project creation wizard | All users |
| `/projects` | List all projects | All users |
| `/status` | System health overview | All users |
| `/docker` | Docker container management | Admin |
| `/services` | Systemd service management | Admin |
| `/analytics` | Cost and usage analytics | All users |
| `/settings` | Global and per-project settings | Admin |
| `/admin` | User whitelist management | Admin |
| `/help` | Command reference | All users |

## Testing

```bash
# Run all tests
PYTHONPATH=. python -m pytest tests/ -v

# Run specific test file
PYTHONPATH=. python -m pytest tests/unit/test_log_parser.py -v
```

## Security

- Telegram user ID whitelist with silent rejection (no response to unauthorized users)
- Factory marker sanitization prevents log injection via user input
- Engine validation prevents command injection in tmux sessions
- Symlink protection on log file reads
- Path traversal protection on project directories
- Atomic file writes for clarification answers
- ALLOWED_SERVICES whitelist for systemd operations
- API key masking in all display contexts
- No `shell=True` in any subprocess call
- Parameterized SQL queries via SQLAlchemy ORM

## License

Private — internal use only.
