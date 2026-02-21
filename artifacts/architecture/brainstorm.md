# Phase 2: Multi-Model Brainstorm

## Models Consulted
| Model | Provider | Response Quality |
|-------|----------|-----------------|
| Gemini 3 Pro | Google | Excellent — detailed library recommendations, event-driven observer pattern |
| GPT-5.2 | OpenAI | Excellent — hexagonal architecture, ProjectSupervisor pattern, webhook recommendation |
| DeepSeek R1 | DeepSeek | Good — modular monolith, practical code examples, codebase structure |
| Qwen3 Coder | Alibaba | Non-responsive (asked for files instead of answering) |

---

## Consensus Points (All 3 Models Agree)

### 1. Architecture: Modular Monolith with Async Event-Driven Patterns
All 3 models recommend a **modular monolith** over microservices:
- Tight integration between features (log monitoring, conversation flows, Docker management)
- Single-node deployment makes microservices unnecessary overhead
- Clear module boundaries to allow future extraction if needed

### 2. Database: SQLAlchemy 2.0 Async + asyncpg
Unanimous recommendation:
- **SQLAlchemy 2.0** with async session management for typed queries
- **asyncpg** driver for pure async PostgreSQL access (~20% faster than alternatives)
- **Alembic** for schema migrations
- Connection pool: 5-10 connections with `pool_recycle`

### 3. Docker Management: aiodocker
All models that addressed Docker recommend **aiodocker** (async) over the synchronous `docker` SDK to avoid blocking the event loop.

### 4. Key Risk: Telegram FloodWait / Rate Limits
All 3 models flag this as a critical risk:
- Editing messages every 3 seconds across multiple factory runs WILL hit Telegram limits
- **Mitigation**: Message diffing (skip edits if content unchanged), throttling (max 1 edit per 3-5s per message), debouncing

### 5. Key Risk: Docker Socket Security
All 3 models flag mounting `/var/run/docker.sock` as a security concern:
- Gives bot root-equivalent access to host
- **Mitigation**: Admin-only access, container name allowlist, command allowlist, consider Docker API proxy for v2

---

## Divergent Opinions

### Polling vs Webhook (GPT-5.2 dissents)
- **GPT-5.2**: Strongly recommends **webhook** for production — avoids update conflicts (409 errors), simplifies horizontal scaling
- **Gemini/DeepSeek**: Don't address this directly, implicitly assume polling
- **Decision**: **Use polling for v1.0**. Single instance, single node, no scaling needed. Simpler to develop and debug. Can switch to webhook in v2 if scaling becomes necessary.

### Log Monitoring Pattern
- **Gemini**: Dedicated `LogWatcher` observer with inode tracking + `aiofiles`
- **GPT-5.2**: `ProjectSupervisor` actor pattern with asyncio.Queue + `watchfiles`
- **DeepSeek**: Simple asyncio.sleep(3) polling loop
- **Decision**: **Use Gemini's LogWatcher pattern with GPT-5.2's supervisor concept**. Each factory run gets a `RunMonitor` class that owns a log watcher task. Store `last_read_offset` per run. Use `asyncio.to_thread()` for file reads to avoid blocking.

### Conversation State Persistence
- **Gemini**: Custom `BasePersistence` implementation using SQLAlchemy (replaces PTB's PicklePersistence)
- **DeepSeek**: Separate `conversation_state` table with JSONB
- **Decision**: **Use PTB's built-in persistence with a PostgreSQL backend**. Implement PTB's `BasePersistence` interface backed by a `conversation_states` table. This integrates cleanly with ConversationHandler and survives container restarts.

### Codebase Structure
- **GPT-5.2**: Hexagonal (ports & adapters) with application/domain/infrastructure layers
- **DeepSeek**: Simpler layered: `bot/handlers/`, `services/`, `models/`, `utils/`
- **Gemini**: PTB Application + JobQueue + Observer
- **Decision**: **Use DeepSeek's practical layered structure with GPT-5.2's interface separation**. Keep it simple but use interfaces for Docker client, transcription service, etc.

---

## Unified Tech Stack Recommendation

### Core Framework
| Component | Library | Version | Rationale |
|-----------|---------|---------|-----------|
| Bot framework | python-telegram-bot | v21+ | Mature async, ConversationHandler, JobQueue |
| ORM/DB | SQLAlchemy | 2.0+ | Async sessions, typed queries, migration support |
| DB driver | asyncpg | latest | Fastest async PostgreSQL driver |
| Migrations | Alembic | latest | Standard SQLAlchemy migration tool |
| Validation | Pydantic | v2 | Settings, log marker parsing, API responses |
| Config | pydantic-settings | latest | Typed env var configuration |

### Infrastructure
| Component | Library | Rationale |
|-----------|---------|-----------|
| Docker management | aiodocker | Async Docker API, non-blocking |
| tmux management | libtmux | Object-oriented tmux Python API |
| System monitoring | psutil | Standard system metrics |
| HTTP client | httpx | Async HTTP for AI API calls |
| File I/O | asyncio.to_thread() | Wrap blocking reads in thread executor |

### AI/Voice
| Component | Library | Rationale |
|-----------|---------|-----------|
| Groq Whisper | httpx (direct API) | Simple REST call, no SDK needed |
| OpenAI Whisper | openai SDK | Well-maintained, async support |
| AI structuring | httpx (OpenRouter) | Unified API for model selection |

### Observability
| Component | Library | Rationale |
|-----------|---------|-----------|
| Logging | structlog | Structured async logging |
| Retries | tenacity | Flexible retry patterns with backoff |

---

## Recommended Codebase Structure

```
factory_control_bot/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Application entry point
│   ├── config.py                  # Pydantic settings
│   ├── bot/                       # Telegram layer
│   │   ├── __init__.py
│   │   ├── application.py         # PTB Application builder
│   │   ├── middleware.py          # Auth whitelist check
│   │   ├── handlers/              # Command handlers
│   │   │   ├── __init__.py
│   │   │   ├── start.py
│   │   │   ├── projects.py
│   │   │   ├── docker.py
│   │   │   ├── system.py
│   │   │   ├── analytics.py
│   │   │   ├── settings.py
│   │   │   ├── admin.py
│   │   │   └── help.py
│   │   ├── conversations/         # ConversationHandler flows
│   │   │   ├── __init__.py
│   │   │   ├── new_project.py
│   │   │   ├── voice_input.py
│   │   │   └── requirements_review.py
│   │   └── keyboards/             # Inline keyboard builders
│   │       ├── __init__.py
│   │       ├── main_menu.py
│   │       ├── project_actions.py
│   │       └── engine_select.py
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── project_service.py
│   │   ├── factory_runner.py      # Start/stop factory runs
│   │   ├── run_monitor.py         # Log watching + event emission
│   │   ├── transcription.py       # Groq/OpenAI Whisper
│   │   ├── translation.py         # Text translation
│   │   ├── docker_service.py      # Container management
│   │   ├── system_service.py      # System health
│   │   ├── analytics_service.py   # Cost/metrics
│   │   └── notification.py        # Push notification routing
│   ├── models/                    # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── project.py
│   │   ├── factory_run.py
│   │   ├── factory_event.py
│   │   ├── deployment.py
│   │   ├── node.py
│   │   ├── setting.py
│   │   └── analytics.py
│   ├── database/                  # Database layer
│   │   ├── __init__.py
│   │   ├── engine.py              # AsyncEngine setup
│   │   ├── session.py             # AsyncSession factory
│   │   └── persistence.py         # PTB BasePersistence impl
│   └── utils/                     # Shared utilities
│       ├── __init__.py
│       ├── log_parser.py          # Parse [FACTORY:...] markers
│       ├── validators.py          # Project name, etc.
│       └── formatting.py          # Telegram message formatting
├── alembic/                       # Database migrations
│   ├── alembic.ini
│   └── versions/
├── templates/                     # Engine configs + prompts
│   ├── engine_configs/
│   └── prompts/
├── scripts/                       # Maintenance scripts
│   └── backup_db.sh
├── tests/                         # Test suite
│   ├── conftest.py
│   ├── test_handlers/
│   ├── test_services/
│   └── test_models/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## Risk Matrix (Prioritized)

| # | Risk | Severity | Probability | Mitigation |
|---|------|----------|-------------|------------|
| 1 | Telegram FloodWait on message edits | High | High | Diffing + throttling (max 1 edit/3s/message) |
| 2 | Docker socket security (root access) | High | Low | Admin-only, command allowlist, container label filter |
| 3 | Async task leaks (orphaned monitors) | Medium | Medium | TaskGroup, explicit lifecycle, startup reconciliation |
| 4 | Log rotation race condition | Medium | Low | Inode tracking, offset persistence, handle truncation |
| 5 | Vendor API cost overrun | Medium | Medium | Per-project budgets, cost estimation, hard caps |
| 6 | Bot restart during active runs | Medium | Medium | Startup reconciliation: scan tmux + DB sync |
| 7 | Voice transcription latency | Low | Low | Async processing, "typing..." indicator, background task |
