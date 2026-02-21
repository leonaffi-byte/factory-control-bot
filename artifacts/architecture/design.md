# Factory Control Bot — Architecture Design v1.0

## 1. System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Telegram Cloud                        │
│                   (Bot API Server)                        │
└──────────────────────┬──────────────────────────────────┘
                       │ Long Polling (v1.0)
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Factory Control Bot (Docker)                 │
│                                                          │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────┐    │
│  │ Telegram  │  │  Service  │  │  Run Supervisor   │    │
│  │  Layer    │──│  Layer    │──│  (asyncio tasks)  │    │
│  │ handlers  │  │  logic    │  │  LogWatchers      │    │
│  └──────────┘  └───────────┘  └───────────────────┘    │
│       │              │               │                   │
│       ▼              ▼               ▼                   │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────┐    │
│  │ Database  │  │  Docker   │  │  tmux Sessions    │    │
│  │  Layer    │  │  Client   │  │  (factory runs)   │    │
│  └────┬─────┘  └─────┬─────┘  └─────────┬─────────┘    │
└───────┼──────────────┼───────────────────┼──────────────┘
        │              │                   │
        ▼              ▼                   ▼
   PostgreSQL     Docker Socket      /home/factory/projects/
   (Container)    (/var/run/         (Host filesystem)
                  docker.sock)
```

## 2. Architecture Pattern

**Modular Monolith with Async Event-Driven Supervision**

### Layers
1. **Bot Layer** (`app/bot/`): Telegram handlers, conversation flows, keyboards. Thin — delegates to services.
2. **Service Layer** (`app/services/`): Business logic. Stateless where possible. Each service owns one domain.
3. **Model Layer** (`app/models/`): SQLAlchemy ORM models. Data representation only.
4. **Database Layer** (`app/database/`): Engine, session factory, persistence adapter.
5. **Utils** (`app/utils/`): Shared helpers (log parsing, formatting, validation).

### Concurrency Model
- **PTB Application**: Runs the Telegram update loop with `concurrent_updates=True`
- **Run Supervisor**: Background asyncio task that manages `RunMonitor` instances
- **RunMonitor**: Per-factory-run asyncio task that tails log files and emits events
- **Notification Service**: Receives events from RunMonitors and sends Telegram messages with throttling

## 3. Component Architecture

### 3.1 Application Startup

```python
async def main():
    # 1. Load config from environment
    config = Settings()

    # 2. Initialize database
    engine = create_async_engine(config.database_url)
    async_session = async_sessionmaker(engine)

    # 3. Run Alembic migrations
    await run_migrations(engine)

    # 4. Initialize services
    services = ServiceContainer(config, async_session)

    # 5. Build PTB Application
    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .persistence(PostgresPersistence(async_session))
        .post_init(post_init)
        .build()
    )

    # 6. Register handlers
    register_handlers(app, services)

    # 7. Start run supervisor (reconciles active runs)
    app.job_queue.run_once(startup_reconciliation, when=0)

    # 8. Start periodic health checks
    app.job_queue.run_repeating(health_check_job, interval=300)

    # 9. Run polling
    await app.run_polling(allowed_updates=Update.ALL_TYPES)
```

### 3.2 Authentication Middleware

```python
async def auth_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False  # No user in update

    # Check whitelist (cached in memory, refreshed every 60s)
    if user.id not in context.bot_data.get('allowed_users', set()):
        return False  # Silent ignore — no response

    return True
```

Applied as a `TypeHandler` at group -1 (runs before all other handlers).

### 3.3 Run Supervisor

```python
class RunSupervisor:
    """Manages all active factory run monitors."""

    def __init__(self, services: ServiceContainer):
        self.services = services
        self.monitors: dict[str, RunMonitor] = {}  # run_id -> monitor

    async def start_run(self, run: FactoryRun) -> None:
        """Start monitoring a factory run."""
        monitor = RunMonitor(run, self.services)
        self.monitors[str(run.id)] = monitor
        asyncio.create_task(monitor.start())

    async def stop_run(self, run_id: str) -> None:
        """Stop monitoring and signal factory to stop."""
        monitor = self.monitors.get(run_id)
        if monitor:
            await monitor.stop()
            del self.monitors[run_id]

    async def reconcile(self) -> None:
        """On startup: find active runs in DB, check tmux, re-attach."""
        active_runs = await self.services.factory.get_active_runs()
        tmux_sessions = await self.services.factory.list_tmux_sessions()

        for run in active_runs:
            if run.tmux_session in tmux_sessions:
                await self.start_run(run)
            else:
                await self.services.factory.mark_failed(run)
                await self.services.notification.send_run_failed(run)
```

### 3.4 RunMonitor (Log Watcher)

```python
class RunMonitor:
    """Monitors a single factory run by tailing its log file."""

    def __init__(self, run: FactoryRun, services: ServiceContainer):
        self.run = run
        self.services = services
        self.last_offset = 0
        self.running = True
        self.last_activity = datetime.utcnow()

    async def start(self) -> None:
        log_path = Path(self.run.audit_log_path).parent / "factory-run.log"
        while self.running:
            try:
                new_lines = await self._read_new_lines(log_path)
                if new_lines:
                    self.last_activity = datetime.utcnow()
                    await self._process_lines(new_lines)
                else:
                    # Check for idle timeout (10 minutes)
                    idle = (datetime.utcnow() - self.last_activity).seconds
                    if idle > 600:
                        await self.services.notification.send_idle_warning(self.run)
            except Exception as e:
                logger.error("Monitor error", run_id=self.run.id, error=str(e))
            await asyncio.sleep(3)  # Poll interval

    async def _read_new_lines(self, log_path: Path) -> list[str]:
        """Read new lines from log file starting at last offset."""
        def _read():
            try:
                with open(log_path, 'r') as f:
                    f.seek(self.last_offset)
                    lines = f.readlines()
                    self.last_offset = f.tell()
                    return lines
            except FileNotFoundError:
                return []
        return await asyncio.to_thread(_read)

    async def _process_lines(self, lines: list[str]) -> None:
        """Parse structured markers and emit events."""
        for line in lines:
            event = parse_factory_marker(line)
            if event:
                await self._handle_event(event)

    async def _handle_event(self, event: FactoryEvent) -> None:
        match event.event_type:
            case "phase_start":
                await self.services.factory.update_phase(self.run, event.phase)
                await self.services.notification.send_phase_start(self.run, event)
            case "phase_end":
                score = event.data_json.get("score")
                await self.services.factory.record_quality_score(self.run, event.phase, score)
                await self.services.notification.send_phase_end(self.run, event)
            case "clarify":
                await self.services.notification.send_clarification(self.run, event)
            case "error":
                await self.services.notification.send_error(self.run, event)
            case "cost":
                await self.services.analytics.record_cost(self.run, event)
            case "complete":
                await self.services.factory.mark_completed(self.run, event)
                await self.services.notification.send_complete(self.run, event)
                self.running = False
```

### 3.5 Notification Service (Throttled)

```python
class NotificationService:
    """Sends Telegram notifications with rate limiting."""

    def __init__(self, bot: Bot, session_factory):
        self.bot = bot
        self.session_factory = session_factory
        self._message_cache: dict[str, MessageSession] = {}

    async def send_or_edit(self, chat_id: int, run_id: str, text: str) -> None:
        """Send or edit a monitoring message with throttling."""
        key = f"{chat_id}:{run_id}"
        session = self._message_cache.get(key)

        if session and session.should_throttle():
            return  # Skip — too soon since last edit

        if session and session.last_text_hash == hash(text):
            return  # Skip — content unchanged

        try:
            if session and session.message_id:
                await self.bot.edit_message_text(
                    text=text, chat_id=chat_id,
                    message_id=session.message_id,
                    parse_mode="HTML"
                )
            else:
                msg = await self.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="HTML"
                )
                session = MessageSession(message_id=msg.message_id)
                self._message_cache[key] = session

            session.update(text)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except BadRequest:
            pass  # Message may have been deleted
```

### 3.6 Transcription Service

```python
class TranscriptionService:
    """Voice transcription with Groq primary, OpenAI fallback."""

    def __init__(self, config: Settings):
        self.groq_client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": f"Bearer {config.groq_api_key}"}
        )
        self.openai_client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {config.openai_api_key}"}
        )
        self.groq_failures = 0
        self.groq_cooldown_until: datetime | None = None

    async def transcribe(self, audio_bytes: bytes, filename: str) -> TranscriptionResult:
        """Transcribe audio, trying Groq first then OpenAI."""
        if self._should_use_groq():
            try:
                result = await self._transcribe_groq(audio_bytes, filename)
                self.groq_failures = 0
                return result
            except (httpx.HTTPStatusError, httpx.TimeoutException):
                self.groq_failures += 1
                if self.groq_failures >= 3:
                    self.groq_cooldown_until = datetime.utcnow() + timedelta(minutes=5)

        return await self._transcribe_openai(audio_bytes, filename)
```

## 4. Database Design

### 4.1 SQLAlchemy Model Base

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import func
from datetime import datetime
import uuid

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### 4.2 Entity Relationship Diagram

```
users (telegram_id PK)
  │
  ├──< projects (created_by FK)
  │      │
  │      ├──< factory_runs (project_id FK)
  │      │      │
  │      │      ├──< factory_events (run_id FK)
  │      │      │
  │      │      └──< analytics (run_id FK)
  │      │
  │      ├──< deployments (project_id FK)
  │      │
  │      └──< analytics (project_id FK)
  │
  └── settings (updated_by FK)

nodes (standalone, future multi-node)
```

### 4.3 Migration Strategy

- **Tool**: Alembic with async support
- **Auto-migration on startup**: `alembic upgrade head` runs in `post_init` callback
- **Naming convention**: `{date}_{description}.py` (e.g., `20260221_initial_schema.py`)
- **Down migrations**: Supported but not required for production

### 4.4 Connection Pool Configuration

```python
engine = create_async_engine(
    config.database_url,
    pool_size=10,         # Base connections
    max_overflow=5,       # Extra connections under load
    pool_recycle=3600,    # Recycle connections every hour
    pool_pre_ping=True,   # Verify connections before use
    echo=False,           # No SQL logging in production
)
```

## 5. API Interfaces (Contract)

### 5.1 Service Layer Interfaces

```python
# These are the contracts between bot handlers and services

class ProjectServiceProtocol(Protocol):
    async def create_project(self, name: str, description: str, engines: list[str],
                            requirements: str, settings: dict, deploy_config: dict,
                            created_by: int) -> Project: ...
    async def get_project(self, project_id: UUID) -> Project | None: ...
    async def list_projects(self, offset: int = 0, limit: int = 20) -> list[Project]: ...
    async def delete_project(self, project_id: UUID) -> bool: ...
    async def update_project_status(self, project_id: UUID, status: str) -> None: ...

class FactoryRunnerProtocol(Protocol):
    async def start_run(self, project: Project, engine: str) -> FactoryRun: ...
    async def stop_run(self, run_id: UUID) -> None: ...
    async def pause_run(self, run_id: UUID) -> None: ...
    async def get_active_runs(self) -> list[FactoryRun]: ...
    async def get_run_status(self, run_id: UUID) -> FactoryRun | None: ...
    async def list_tmux_sessions(self) -> list[str]: ...
    async def answer_clarification(self, run_id: UUID, answer: str) -> None: ...

class TranscriptionProtocol(Protocol):
    async def transcribe(self, audio_bytes: bytes, filename: str) -> TranscriptionResult: ...

class TranslationProtocol(Protocol):
    async def translate_to_english(self, text: str, source_lang: str | None = None) -> str: ...

class DockerServiceProtocol(Protocol):
    async def list_containers(self, all: bool = True) -> list[ContainerInfo]: ...
    async def start_container(self, container_id: str) -> None: ...
    async def stop_container(self, container_id: str) -> None: ...
    async def restart_container(self, container_id: str) -> None: ...
    async def get_container_logs(self, container_id: str, tail: int = 50) -> str: ...
    async def remove_container(self, container_id: str) -> None: ...

class SystemServiceProtocol(Protocol):
    async def get_health(self) -> SystemHealth: ...
    async def get_service_status(self, service_name: str) -> ServiceStatus: ...
    async def restart_service(self, service_name: str) -> bool: ...
    async def get_service_logs(self, service_name: str, lines: int = 50) -> str: ...

class AnalyticsServiceProtocol(Protocol):
    async def get_project_analytics(self, project_id: UUID) -> ProjectAnalytics: ...
    async def get_aggregate_analytics(self, period: str = "month") -> AggregateAnalytics: ...
    async def record_cost(self, run: FactoryRun, event: FactoryEvent) -> None: ...

class SettingsServiceProtocol(Protocol):
    async def get_setting(self, key: str) -> Any: ...
    async def set_setting(self, key: str, value: Any, updated_by: int) -> None: ...
    async def get_all_settings(self) -> dict[str, Any]: ...
```

### 5.2 Data Transfer Objects

```python
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

class TranscriptionResult(BaseModel):
    text: str
    language: str  # detected language code
    provider: str  # "groq" or "openai"
    duration_ms: int

class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    status: str  # running, exited, paused
    state: str
    ports: dict[str, str]
    created: datetime
    cpu_percent: float | None = None
    memory_mb: float | None = None

class SystemHealth(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: int

class ServiceStatus(BaseModel):
    name: str
    active: bool
    status: str  # active, inactive, failed
    uptime: str | None = None

class ProjectAnalytics(BaseModel):
    project_id: UUID
    total_cost: float
    cost_by_provider: dict[str, float]
    cost_by_phase: dict[int, float]
    duration_minutes: float | None
    quality_scores: dict[int, float]
    test_passed: int
    test_failed: int
    test_skipped: int

class AggregateAnalytics(BaseModel):
    total_spend: float
    projects_completed: int
    projects_failed: int
    avg_cost_by_tier: dict[int, float]
    success_rate: float
```

### 5.3 Factory Communication DTOs

```python
class FactoryMarker(BaseModel):
    """Parsed from [FACTORY:TYPE:data] log markers."""
    marker_type: str  # phase_start, phase_end, clarify, error, cost, complete
    phase: int | None = None
    data: dict = {}

class ClarificationQuestion(BaseModel):
    question: str
    type: str = "open"  # "multiple_choice" or "open"
    options: list[str] = []
    context: str = ""

class FactorySummary(BaseModel):
    project: str
    engine: str
    duration_minutes: float
    phases: dict[str, float]  # phase number -> quality score
    total_cost: float
    cost_by_provider: dict[str, float]
    test_results: dict[str, int]
    github_url: str | None = None
    deploy_status: str | None = None
```

## 6. Conversation Flow State Machines

### 6.1 Project Creation Flow

```
┌─────────┐
│  /new    │
└────┬─────┘
     ▼
┌─────────────────┐
│ ENGINE_SELECT    │ ← Multi-select inline keyboard
│ Toggle engines   │ ← callback: engine_toggle:{name}
│ Press Confirm    │ ← callback: engine_confirm
└────┬────────────┘
     ▼
┌─────────────────┐
│ NAME_INPUT       │ ← Text input
│ Validate regex   │ ← ^[a-z][a-z0-9-]*[a-z0-9]$
│ Check uniqueness │ ← DB query
└────┬────────────┘
     ▼
┌─────────────────┐
│ DESC_INPUT       │ ← Text or voice
│ If voice → sub   │ ← voice_input sub-flow
└────┬────────────┘
     ▼
┌─────────────────┐
│ REQ_GATHERING    │ ← Voice/text input loop
│ Done/Edit/Delete │ ← Inline buttons
└────┬────────────┘
     ▼ (on Done)
┌─────────────────┐
│ REQ_TRANSLATING  │ ← Translate if not English
│ AI structuring   │ ← Generate formal requirements
└────┬────────────┘
     ▼
┌─────────────────┐
│ REQ_REVIEW       │ ← Display structured requirements
│ Approve/Edit/    │ ← Inline buttons
│ Regenerate       │
└────┬────────────┘
     ▼ (on Approve)
┌─────────────────┐
│ SETTINGS_CHOICE  │ ← Default or Customize
└────┬────┬───────┘
     │    │ (Customize)
     │    ▼
     │ ┌──────────────┐
     │ │ SETTINGS_MENU│ ← Per-project overrides
     │ └──────┬───────┘
     │        │
     ▼ ◄──────┘
┌─────────────────┐
│ DEPLOY_CHOICE    │ ← Auto-deploy yes/no
└────┬────┬───────┘
     │    │ (Yes)
     │    ▼
     │ ┌──────────────┐
     │ │ PROJECT_TYPE │ ← Bot/Web/API/Other
     │ └──────┬───────┘
     │        ▼
     │ ┌──────────────┐
     │ │ DEPLOY_TARGET│ ← This VPS / Other
     │ └──────┬───────┘
     │        ▼
     │ ┌──────────────┐
     │ │ ACCESS_CONFIG│ ← Localhost / Public+domain
     │ └──────┬───────┘
     │        │
     ▼ ◄──────┘
┌─────────────────┐
│ CONFIRM_LAUNCH   │ ← Summary + Launch button
└────┬────────────┘
     ▼
  Create project → Start factory run(s) → Monitoring
```

### 6.2 State Constants

```python
(
    ENGINE_SELECT,
    NAME_INPUT,
    DESC_INPUT,
    REQ_GATHERING,
    REQ_TRANSLATING,
    REQ_REVIEW,
    SETTINGS_CHOICE,
    SETTINGS_MENU,
    DEPLOY_CHOICE,
    PROJECT_TYPE,
    DEPLOY_TARGET,
    ACCESS_CONFIG,
    CONFIRM_LAUNCH,
) = range(13)
```

## 7. Error Handling Strategy

### 7.1 Error Hierarchy

```python
class FactoryBotError(Exception):
    """Base exception for all bot errors."""
    pass

class AuthorizationError(FactoryBotError):
    """User not authorized."""
    pass

class ProjectNotFoundError(FactoryBotError):
    """Project does not exist."""
    pass

class FactoryRunError(FactoryBotError):
    """Factory run encountered an error."""
    pass

class TranscriptionError(FactoryBotError):
    """Voice transcription failed."""
    pass

class DockerError(FactoryBotError):
    """Docker operation failed."""
    pass

class ResourceError(FactoryBotError):
    """System resource issue (disk, memory)."""
    pass
```

### 7.2 Global Error Handler

```python
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for all unhandled exceptions."""
    logger.error("Unhandled exception", exc_info=context.error)

    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An unexpected error occurred. Please try again."
        )
```

## 8. Security Architecture

### 8.1 Authentication Flow

```
User sends message
    │
    ▼
Auth Middleware (group -1)
    │
    ├── user_id in whitelist? ── No ──> Silent drop (no response)
    │
    └── Yes ──> Continue to handler
                    │
                    ├── Admin-only command? ── user.role != 'admin' ──> "Admin only"
                    │
                    └── Process request
```

### 8.2 API Key Masking

```python
def mask_api_key(key: str) -> str:
    """Show first 4 and last 4 characters only."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"
```

### 8.3 Input Sanitization

```python
def sanitize_user_input(text: str) -> str:
    """Strip factory marker patterns from user input to prevent injection."""
    import re
    return re.sub(r'\[FACTORY:[^\]]*\]', '', text)
```

## 9. Deployment Architecture

### 9.1 Docker Compose

```yaml
version: '3.8'

services:
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    volumes:
      - /home/factory/projects:/home/factory/projects
      - /var/run/docker.sock:/var/run/docker.sock
      - /home/factory/.factory-env:/home/factory/.factory-env:ro
    network_mode: host
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 512M

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: factory_bot
      POSTGRES_USER: factory
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/backup_db.sh:/usr/local/bin/backup_db.sh:ro
    ports:
      - "127.0.0.1:5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U factory -d factory_bot"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### 9.2 Dockerfile

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

# Install system deps for psutil and tmux interaction
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux libtmux0 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

CMD ["python", "-m", "app.main"]
```

### 9.3 Startup Sequence

```
1. Load environment variables (pydantic-settings)
2. Connect to PostgreSQL
3. Run Alembic migrations
4. Initialize service container
5. Build PTB Application with persistence
6. Register all handlers
7. Run startup reconciliation (check for orphaned factory runs)
8. Start periodic jobs (health check every 5 min, disk check every 5 min)
9. Start polling
```

## 10. Monitoring and Observability

### 10.1 Structured Logging

```python
import structlog

logger = structlog.get_logger()

# Every log line includes:
# - timestamp (ISO 8601)
# - level
# - event (what happened)
# - context (run_id, project_id, user_id, etc.)
```

### 10.2 Health Check Job

```python
async def health_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Periodic health check — runs every 5 minutes."""
    health = await services.system.get_health()

    if health.disk_percent > 90:
        await notify_admins("CRITICAL: Disk usage at {health.disk_percent}%")
    elif health.disk_percent > 80:
        await notify_admins("WARNING: Disk usage at {health.disk_percent}%")

    if health.memory_percent > 90:
        await notify_admins("WARNING: Memory usage at {health.memory_percent}%")
```

## 11. State Transition Rules

### 11.1 Project Status Transitions

```
draft ──> queued ──> running ──> completed ──> deployed
                       │             │
                       ├──> paused ──┤
                       │             │
                       └──> failed   └──> failed
```

**Legal transitions**:
| From | To | Trigger |
|------|----|---------|
| draft | queued | User confirms launch |
| queued | running | Factory run starts (tmux session created) |
| running | paused | User pauses or .factory-pause signal |
| running | completed | All runs complete successfully |
| running | failed | All runs fail or user stops |
| paused | running | User resumes |
| completed | deployed | Auto-deploy succeeds |
| completed | failed | Auto-deploy fails |

**Invariant**: A project's status reflects the aggregate of its runs. If ANY run is 'running', project is 'running'. If ALL runs are 'completed', project is 'completed'.

### 11.2 Factory Run Status Transitions

```
queued ──> running ──> completed
              │
              ├──> paused ──> running
              │
              └──> failed
```

**Invariant**: Run status changes MUST be persisted to DB before sending notifications. Use a single async transaction.

### 11.3 Idempotency Guarantees

| Operation | Guarantee | Implementation |
|-----------|-----------|----------------|
| Run status update | At-most-once | UPDATE WHERE status = expected_status (optimistic lock) |
| Notification send | At-least-once | Track last_notified_event_id per run; skip duplicates |
| Log marker processing | Exactly-once | Offset-based — each byte read exactly once; offset persisted periodically |
| Clarification answer write | Idempotent | Overwrite file each time (last write wins) |
| Cost recording | At-most-once | Unique constraint on (run_id, event_type, phase, provider) |

## 12. Log Protocol Specification

### 12.1 Marker Grammar

```
marker     := '[FACTORY:' type ':' payload ']'
type       := 'PHASE' | 'CLARIFY' | 'ERROR' | 'COST' | 'COMPLETE'
payload    := phase_start | phase_end | clarify | error | cost | complete

phase_start := NUMBER ':START'
phase_end   := NUMBER ':END:' NUMBER
clarify     := JSON_STRING          (single line, no newlines in JSON)
error       := TEXT_STRING          (no ']' characters)
cost        := DECIMAL ':' PROVIDER
complete    := JSON_STRING          (single line, no newlines in JSON)

NUMBER      := [0-9]+
DECIMAL     := [0-9]+('.'[0-9]+)?
PROVIDER    := [a-z_]+
TEXT_STRING := [^\]]+
JSON_STRING := '{' ... '}'          (valid JSON, newlines escaped as \n)
```

### 12.2 Parsing Rules
1. Markers always appear at the START of a line
2. One marker per line maximum
3. Lines without markers are regular log output (used for live display)
4. JSON payloads are single-line (no literal newlines — use `\n` escape)
5. Partial lines: if a line doesn't end with `\n`, wait for next read cycle
6. UTF-8 encoding only

### 12.3 File Rotation Handling
1. On each read cycle, check file size against last known size
2. If file size < last offset → file was truncated/rotated → reset offset to 0
3. Re-read from beginning after rotation (some duplicates are acceptable; dedup via event_id)

### 12.4 Offset Persistence
- Store `last_read_offset` in memory (per RunMonitor instance)
- Flush to `factory_runs.last_log_offset` DB column every 30 seconds
- On bot restart: restore offset from DB; if file size < stored offset, reset to 0

## 13. Rate Limiting Strategy

### 13.1 Telegram API Limits
- **Global**: ~30 messages/second across all chats
- **Per chat**: ~1 message/second, ~20 messages/minute
- **Message edits**: Same limits as sending

### 13.2 Rate Limiter Implementation

```python
class TelegramRateLimiter:
    """Token bucket rate limiter for Telegram API calls."""

    def __init__(self):
        self._per_chat: dict[int, TokenBucket] = {}
        self._global = TokenBucket(rate=25, capacity=30)  # 25/sec, burst 30

    async def acquire(self, chat_id: int) -> None:
        """Wait until a message can be sent to chat_id."""
        per_chat = self._per_chat.setdefault(
            chat_id, TokenBucket(rate=0.8, capacity=3)  # ~1/sec, burst 3
        )
        await self._global.acquire()
        await per_chat.acquire()
```

### 13.3 Message Edit Strategy
1. Each monitored run has a `MessageSession` with:
   - `message_id`: The live monitoring message
   - `last_edit_time`: Timestamp of last successful edit
   - `last_text_hash`: Hash of last sent content
   - `min_edit_interval`: 3 seconds (configurable)
2. Before editing: check `time.time() - last_edit_time >= min_edit_interval`
3. Before editing: check `hash(new_text) != last_text_hash` (skip if unchanged)
4. On `RetryAfter` exception: sleep for `retry_after` seconds, then resume
5. On `BadRequest` (message deleted): clear session, send new message on next update

## 14. Testing Strategy

### 14.1 Test Layers

| Layer | Framework | What to Test |
|-------|-----------|-------------|
| Unit | pytest + pytest-asyncio | Services, log parser, validators, formatters |
| Integration | pytest + testcontainers | Database operations with real PostgreSQL |
| Bot handlers | pytest + python-telegram-bot test utils | Handler logic with mocked services |
| End-to-end | pytest + Docker | Full bot startup, DB migrations, health checks |

### 14.2 Test Structure

```
tests/
├── conftest.py                  # Shared fixtures (db session, mock services)
├── unit/
│   ├── test_log_parser.py       # Factory marker parsing
│   ├── test_validators.py       # Project name validation
│   ├── test_transcription.py    # Fallback logic
│   └── test_rate_limiter.py     # Token bucket
├── integration/
│   ├── test_project_service.py  # CRUD with real DB
│   ├── test_settings_service.py # Settings persistence
│   └── test_analytics.py        # Analytics queries
├── handlers/
│   ├── test_start_handler.py    # Main menu
│   ├── test_new_project.py      # Project creation flow
│   └── test_docker_handler.py   # Docker management
└── e2e/
    └── test_startup.py          # Full application startup + shutdown
```

### 14.3 Mocking Strategy
- **Telegram API**: Use `python-telegram-bot`'s test utilities with `MockBot`
- **Docker**: Mock `aiodocker` client
- **tmux**: Mock `libtmux` server
- **External APIs** (Groq/OpenAI): Use `httpx` transport mocking
- **Database**: Use testcontainers for PostgreSQL (real DB in tests)

## 15. Backpressure and Queueing

### 15.1 Update Processing
- PTB's `concurrent_updates=True` processes updates concurrently
- Max concurrent handlers: limited by asyncio task count (no explicit limit needed for 1-5 users)

### 15.2 Log Monitoring Backpressure
- If NotificationService can't keep up with log events (Telegram rate limits):
  1. Buffer events in memory (max 100 per run)
  2. If buffer full: drop oldest non-critical events (keep phase_start, phase_end, error, complete)
  3. When rate limit clears: flush buffered events with latest state only (don't replay history)

### 15.3 Concurrent Run Limits
- Maximum 10 concurrent monitored runs (enforced in RunSupervisor)
- If limit reached: new runs are queued and start when a slot opens
- Notification to user: "Factory run queued. 10 runs already active."

## 16. Secrets Management

### 16.1 Secret Storage
- **Development**: `.env` file (git-ignored)
- **Production**: Docker secrets or environment variables passed via `env_file` in compose
- **Rotation**: API keys can be updated by restarting the container with new env vars
- **In-memory**: Loaded once at startup into `Settings` object; not stored in DB

### 16.2 Secret Access
- Services receive secrets via dependency injection from `Settings`
- No secret is ever logged (structlog configured with secret-filtering processor)
- No secret displayed in Telegram (masked via `mask_api_key()`)

## 17. Deployment Topology

### 17.1 Production: Single Instance
- **Instances**: Exactly 1 bot instance (no horizontal scaling in v1.0)
- **Mode**: Long polling (not webhook)
- **Rationale**: 1-3 users, single VPS, no need for HA
- **Recovery**: Docker `restart: unless-stopped` + optional systemd watcher

### 17.2 Future: Multi-Instance (v2.0)
- Switch to webhook mode
- Use PostgreSQL advisory locks for leader election
- Use PgBouncer for connection pooling
- Run supervisor only on leader instance
- Stateless handlers on all instances
