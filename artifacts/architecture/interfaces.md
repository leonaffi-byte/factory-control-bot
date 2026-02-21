# Factory Control Bot — Interface Contracts v1.0

This document defines the CONTRACT between frontend (Telegram handlers), backend (services), and external systems. Implementers must follow these interfaces exactly.

---

## 1. Bot Handler → Service Layer Contracts

### 1.1 ProjectService

```python
class ProjectService:
    async def create_project(
        self,
        name: str,              # Validated: ^[a-z][a-z0-9-]*[a-z0-9]$, 3-50 chars
        description: str,
        engines: list[str],     # ["claude", "gemini", "opencode", "aider"]
        requirements: str,      # Final approved requirements text
        settings: dict,         # Per-project settings override
        deploy_config: dict,    # Deployment configuration
        created_by: int,        # Telegram user ID
    ) -> Project:
        """Create a new project and return it."""
        ...

    async def get_project(self, project_id: UUID) -> Project | None:
        """Get project by ID, or None if not found."""
        ...

    async def list_projects(
        self,
        offset: int = 0,
        limit: int = 20,
        status_filter: str | None = None,
    ) -> tuple[list[Project], int]:
        """List projects with pagination. Returns (projects, total_count)."""
        ...

    async def delete_project(self, project_id: UUID) -> bool:
        """Delete project and all associated runs/events. Returns success."""
        ...

    async def update_status(self, project_id: UUID, status: str) -> None:
        """Update project status."""
        ...
```

### 1.2 FactoryRunner

```python
class FactoryRunner:
    async def start_run(
        self,
        project: Project,
        engine: str,            # "claude" | "gemini" | "opencode" | "aider"
        created_by: int,
    ) -> FactoryRun:
        """
        Start a factory run:
        1. Create project directory at /home/factory/projects/{name}-{engine}/
        2. Copy engine config template
        3. Write raw-input.md with requirements
        4. Create tmux session
        5. Start factory command in tmux
        6. Record run in database
        7. Start RunMonitor
        Returns the created FactoryRun.
        """
        ...

    async def stop_run(self, run_id: UUID) -> None:
        """
        Stop a factory run:
        1. Touch .factory-stop file in project directory
        2. Wait 30 seconds for graceful shutdown
        3. If still running, kill tmux session
        4. Update DB status to 'failed'
        """
        ...

    async def pause_run(self, run_id: UUID) -> None:
        """Touch .factory-pause file. Factory pauses after current phase."""
        ...

    async def get_active_runs(self) -> list[FactoryRun]:
        """Get all runs with status 'running'."""
        ...

    async def get_run(self, run_id: UUID) -> FactoryRun | None:
        """Get a single run by ID."""
        ...

    async def get_runs_for_project(self, project_id: UUID) -> list[FactoryRun]:
        """Get all runs for a project."""
        ...

    async def answer_clarification(
        self,
        run_id: UUID,
        question_id: int,
        answer: str,
    ) -> None:
        """
        Write answer to clarification-answers.json in project directory.
        Format: [{"question_id": N, "answer": "..."}]
        """
        ...

    async def list_tmux_sessions(self) -> list[str]:
        """List all active tmux session names."""
        ...
```

### 1.3 TranscriptionService

```python
class TranscriptionService:
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,          # e.g., "voice_123.ogg"
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes using Groq (primary) or OpenAI (fallback).
        Returns TranscriptionResult with text, detected language, provider used.
        Raises TranscriptionError if both providers fail.
        """
        ...

class TranscriptionResult:
    text: str                   # Transcribed text
    language: str               # Detected language code (he, en, ru)
    provider: str               # "groq" or "openai"
    duration_ms: int            # Processing time
```

### 1.4 TranslationService

```python
class TranslationService:
    async def translate_to_english(
        self,
        text: str,
        source_lang: str | None = None,  # Auto-detect if None
    ) -> str:
        """Translate text to English using configured AI model."""
        ...

    async def structure_requirements(
        self,
        raw_text: str,
    ) -> str:
        """
        Transform raw text into structured requirements using AI.
        Uses the prompt template from /app/templates/prompts/requirements_structurer.txt
        or the DB override in settings table.
        Returns structured markdown text.
        """
        ...
```

### 1.5 DockerService

```python
class DockerService:
    async def list_containers(
        self,
        all: bool = True,      # Include stopped containers
    ) -> list[ContainerInfo]:
        """List all Docker containers with stats."""
        ...

    async def start_container(self, container_id: str) -> None:
        """Start a stopped container. Raises DockerError on failure."""
        ...

    async def stop_container(self, container_id: str) -> None:
        """Stop a running container. Raises DockerError on failure."""
        ...

    async def restart_container(self, container_id: str) -> None:
        """Restart a container. Raises DockerError on failure."""
        ...

    async def get_logs(
        self,
        container_id: str,
        tail: int = 50,
    ) -> str:
        """Get last N lines of container logs."""
        ...

    async def remove_container(
        self,
        container_id: str,
        force: bool = False,
    ) -> None:
        """Remove a container. Raises DockerError on failure."""
        ...

    async def compose_up(self, project_dir: str) -> None:
        """Run docker-compose up -d in the given directory."""
        ...

    async def compose_down(self, project_dir: str) -> None:
        """Run docker-compose down in the given directory."""
        ...
```

### 1.6 SystemService

```python
class SystemService:
    async def get_health(self) -> SystemHealth:
        """Get current system health metrics (CPU, RAM, disk, uptime)."""
        ...

    async def get_service_status(self, service_name: str) -> ServiceStatus:
        """
        Get systemd service status.
        Valid services: docker, nginx, postgresql, tailscaled, fail2ban
        """
        ...

    async def restart_service(self, service_name: str) -> bool:
        """Restart a systemd service. Admin only. Returns success."""
        ...

    async def get_service_logs(
        self,
        service_name: str,
        lines: int = 50,
    ) -> str:
        """Get last N lines of service journal logs."""
        ...

    async def check_disk_space(self) -> DiskAlert | None:
        """Check disk space, return alert if >80% used."""
        ...
```

### 1.7 AnalyticsService

```python
class AnalyticsService:
    async def get_project_analytics(
        self,
        project_id: UUID,
    ) -> ProjectAnalytics:
        """Get per-project analytics (cost, duration, quality, tests)."""
        ...

    async def get_aggregate_analytics(
        self,
        period: str = "month",  # "week", "month", "year"
    ) -> AggregateAnalytics:
        """Get aggregate analytics for the given period."""
        ...

    async def get_engine_comparison(
        self,
        project_id: UUID,
    ) -> list[EngineComparison] | None:
        """Compare engines for a project with parallel runs. None if single engine."""
        ...

    async def record_cost(
        self,
        run: FactoryRun,
        amount: float,
        provider: str,
    ) -> None:
        """Record a cost entry for a run."""
        ...

    async def record_metric(
        self,
        project_id: UUID,
        run_id: UUID | None,
        metric_name: str,
        metric_value: float,
    ) -> None:
        """Record an analytics metric."""
        ...
```

### 1.8 SettingsService

```python
class SettingsService:
    async def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value. Returns default if not set."""
        ...

    async def set(self, key: str, value: Any, updated_by: int) -> None:
        """Set a setting value."""
        ...

    async def get_all(self) -> dict[str, Any]:
        """Get all settings as a dict."""
        ...

    async def get_openrouter_usage(self) -> tuple[int, int]:
        """Get (current_count, daily_limit) for OpenRouter rate tracking."""
        ...

    async def increment_openrouter_usage(self) -> None:
        """Increment OpenRouter daily usage counter."""
        ...
```

### 1.9 UserService

```python
class UserService:
    async def get_user(self, telegram_id: int) -> User | None:
        """Get user by Telegram ID."""
        ...

    async def is_authorized(self, telegram_id: int) -> bool:
        """Check if user is in whitelist (cached)."""
        ...

    async def is_admin(self, telegram_id: int) -> bool:
        """Check if user is admin."""
        ...

    async def add_user(
        self,
        telegram_id: int,
        display_name: str,
        role: str = "user",
    ) -> User:
        """Add user to whitelist. Raises if already exists."""
        ...

    async def remove_user(self, telegram_id: int) -> bool:
        """Remove user from whitelist. Returns success."""
        ...

    async def list_users(self) -> list[User]:
        """List all whitelisted users."""
        ...

    async def refresh_cache(self) -> None:
        """Refresh the in-memory user whitelist cache."""
        ...
```

---

## 2. Data Model Contracts (Pydantic DTOs)

```python
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from enum import Enum

# --- Enums ---

class ProjectStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    DEPLOYED = "deployed"

class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class Engine(str, Enum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENCODE = "opencode"
    AIDER = "aider"

class DeployType(str, Enum):
    TELEGRAM_BOT = "telegram_bot"
    WEB_APP = "web_app"
    API_SERVICE = "api_service"
    OTHER = "other"

class DeployTarget(str, Enum):
    LOCAL_DOCKER = "local_docker"
    REMOTE_SSH = "remote_ssh"

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"

# --- DTOs ---

class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    status: str
    state: str
    ports: dict[str, str | None] = {}
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
    status: str
    uptime: str | None = None

class DiskAlert(BaseModel):
    percent_used: float
    level: str  # "warning" (>80%) or "critical" (>90%)

class ProjectAnalytics(BaseModel):
    project_id: UUID
    total_cost: float
    cost_by_provider: dict[str, float]
    cost_by_phase: dict[int, float]
    duration_minutes: float | None
    quality_scores: dict[int, float]
    test_passed: int = 0
    test_failed: int = 0
    test_skipped: int = 0

class AggregateAnalytics(BaseModel):
    period: str
    total_spend: float
    projects_completed: int
    projects_failed: int
    avg_cost_by_tier: dict[int, float]
    success_rate: float
    projects_this_period: int

class EngineComparison(BaseModel):
    engine: str
    total_cost: float
    duration_minutes: float
    quality_avg: float
    test_pass_rate: float

class TranscriptionResult(BaseModel):
    text: str
    language: str
    provider: str
    duration_ms: int
```

---

## 3. Factory Communication Protocol

### 3.1 Log Marker Format (Factory → Bot)

```
[FACTORY:PHASE:{N}:START]
[FACTORY:PHASE:{N}:END:{score}]
[FACTORY:CLARIFY:{json}]
[FACTORY:ERROR:{message}]
[FACTORY:COST:{amount}:{provider}]
[FACTORY:COMPLETE:{json}]
```

### 3.2 Log Parser Contract

```python
def parse_factory_marker(line: str) -> FactoryMarker | None:
    """
    Parse a line for [FACTORY:...] markers.
    Returns FactoryMarker if found, None otherwise.

    Examples:
        "[FACTORY:PHASE:3:START]" -> FactoryMarker(type="phase_start", phase=3)
        "[FACTORY:PHASE:3:END:98]" -> FactoryMarker(type="phase_end", phase=3, data={"score": 98})
        "[FACTORY:COST:1.50:openai]" -> FactoryMarker(type="cost", data={"amount": 1.50, "provider": "openai"})
    """
    ...
```

### 3.3 Signal Files (Bot → Factory)

| File | Location | Purpose |
|------|----------|---------|
| `.factory-stop` | Project root | Stop factory after current operation |
| `.factory-pause` | Project root | Pause after current phase |
| `artifacts/reports/clarification-answers.json` | Project dir | Answers to clarification questions |

### 3.4 Clarification Answer Format

```json
[
    {
        "question_id": 1,
        "answer": "JWT tokens",
        "answered_by": 123456789,
        "answered_at": "2026-02-21T14:30:00Z"
    }
]
```

---

## 4. Telegram Message Format Contracts

### 4.1 Main Menu

```
Factory Control Bot v2

[New Project]     [Projects]
[Analytics]       [Docker]
[System]          [Settings]
[Help]
```

### 4.2 Project List Item

```
{emoji} {name}
Engine: {engines} | Status: {status}
Cost: ${cost:.2f} | Last: {relative_time}
[View Details]
```

### 4.3 Factory Run Live Monitor

```
<b>Factory: {project_name} ({engine})</b>
Phase: {phase}/7 — {phase_name}
Status: {status_emoji} {status_text}

<code>{last_5_log_lines}</code>

Updated: {relative_time}
[Pause Updates] [Stop Factory]
```

### 4.4 Completion Summary

```
Factory Complete!

Project: {name}
Engine: {engine}
Duration: {duration}
Cost: ${total_cost:.2f}

Quality Scores:
  Phase 1: {score}/100
  Phase 3: {score}/100
  Phase 5: {score}/100
  Phase 7: {score}/100

Tests: {passed} passed, {failed} failed, {skipped} skipped
GitHub: {url}
Deploy: {status}

[Deploy] [View Logs] [Add Feature]
```

### 4.5 Error Notification

```
Factory Error

Project: {name} ({engine})
Phase: {phase}
Error: {error_message}

Last 5 log lines:
<code>{lines}</code>

[Retry] [View Full Log] [Stop Factory]
```
