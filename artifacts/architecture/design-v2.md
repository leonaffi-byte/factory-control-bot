# Factory Control Bot v2.0 — Architecture Design

## 1. System Overview

```
                         ┌──────────────────────┐
                         │   Telegram Cloud      │
                         │   (Bot API Server)    │
                         └──────────┬───────────┘
                                    │ Long Polling
                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                     HOST (Ubuntu VPS)                              │
│                                                                   │
│  ┌──────────────────────┐     ┌──────────────────────────────┐   │
│  │  factory-bot.service  │     │  factory-worker.service       │   │
│  │  (systemd)            │     │  (systemd)                    │   │
│  │                       │     │                               │   │
│  │  ┌────────────────┐  │     │  ┌─────────────────────────┐ │   │
│  │  │ Telegram Layer │  │     │  │ FactoryOrchestrator     │ │   │
│  │  │ (PTB handlers) │  │     │  │ (FSM, phases 0-7)       │ │   │
│  │  └───────┬────────┘  │     │  └──────────┬──────────────┘ │   │
│  │          │            │     │             │                 │   │
│  │  ┌───────▼────────┐  │     │  ┌──────────▼──────────────┐ │   │
│  │  │ CLI Layer      │  │     │  │ Provider Router         │ │   │
│  │  │ (Typer + Rich) │  │     │  │ (LiteLLM + custom)      │ │   │
│  │  └───────┬────────┘  │     │  └──────────┬──────────────┘ │   │
│  │          │            │     │             │                 │   │
│  │  ┌───────▼──────────────────────────▼──────────────────┐  │   │
│  │  │              Core Service Layer                      │  │   │
│  │  │  ProjectService · ProviderRegistry · ModelScanner    │  │   │
│  │  │  HealthMonitor · BackupService · SelfResearcher      │  │   │
│  │  │  NotificationService · SettingsService               │  │   │
│  │  └───────────────────────┬─────────────────────────────┘  │   │
│  │                          │                                 │   │
│  │  ┌───────────────────────▼─────────────────────────────┐  │   │
│  │  │              Data Layer                              │  │   │
│  │  │  SQLAlchemy 2.0 async · Alembic · LISTEN/NOTIFY     │  │   │
│  │  └───────────────────────┬─────────────────────────────┘  │   │
│  └──────────────────────────┼─────────────────────────────────┘   │
│                             │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐   │
│  │  Docker                                                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │   │
│  │  │ PostgreSQL  │  │ Project A   │  │ Project B       │    │   │
│  │  │ (persistent)│  │ (deployed)  │  │ (deployed)      │    │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘    │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  tmux Sessions                                              │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │   │
│  │  │ proj-claude  │  │ proj-gemini  │  │ proj-aider   │     │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  Local CLIs: claude · gemini · opencode · aider                   │
│  MCP Servers: zen · perplexity · context7 · github · memory       │
└───────────────────────────────────────────────────────────────────┘
```

## 2. Architecture Pattern

**Two-Service Modular Architecture with Event-Driven State Machine**

### Services
1. **factory-bot.service** (systemd): Telegram polling + CLI entrypoint + notification rendering
2. **factory-worker.service** (systemd): Factory orchestrator + background tasks (health, backup, scan, self-research)

### Communication
- **PostgreSQL LISTEN/NOTIFY** for real-time cross-service events
- **DB as single source of truth** for all state
- **Advisory locks** for concurrent state transitions

### Layers (both services share)
1. **Interface Layer**: Telegram handlers (`app/bot/`) + CLI commands (`app/cli/`)
2. **Core Service Layer**: Business logic (`app/services/`)
3. **Provider Layer**: LLM provider abstraction (`app/providers/`)
4. **Model Layer**: SQLAlchemy ORM (`app/models/`)
5. **Database Layer**: Engine, sessions, events (`app/database/`)
6. **Utils**: Shared helpers (`app/utils/`)

## 3. Module Structure

```
app/
├── __init__.py
├── config.py                    # Pydantic Settings (loads .env)
├── main.py                      # Bot service entrypoint
├── worker.py                    # Worker service entrypoint
│
├── bot/                         # Telegram interface layer
│   ├── __init__.py
│   ├── application.py           # PTB Application builder
│   ├── middleware.py             # Auth whitelist, rate limiting
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py             # /start, welcome screen
│   │   ├── projects.py          # /projects, project CRUD
│   │   ├── factory.py           # /run, /stop, /status (factory control)
│   │   ├── scan.py              # /scan-models
│   │   ├── research.py          # /self-research
│   │   ├── health.py            # /health
│   │   ├── backup.py            # /backup, /restore
│   │   ├── docker.py            # /docker container management
│   │   ├── system.py            # /system VPS management
│   │   ├── settings.py          # /settings
│   │   ├── analytics.py         # /analytics
│   │   ├── admin.py             # /admin user management
│   │   └── help.py              # /help
│   ├── conversations/
│   │   ├── __init__.py
│   │   ├── new_project.py       # Multi-step project creation
│   │   └── voice_input.py       # Voice transcription flow
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── main_menu.py
│   │   ├── engine_select.py
│   │   ├── project_actions.py
│   │   ├── settings_menu.py
│   │   ├── scan_results.py
│   │   └── research_actions.py
│   └── views/                   # NEW: Telegram message formatters
│       ├── __init__.py
│       ├── base.py              # Base view with design language
│       ├── project_card.py      # Project card renderer
│       ├── progress_bar.py      # Phase progress bar
│       ├── health_report.py     # Health status formatter
│       ├── scan_report.py       # Model scan results
│       ├── research_report.py   # Self-research results
│       └── welcome.py           # Welcome/onboarding screen
│
├── cli/                         # NEW: CLI interface layer
│   ├── __init__.py
│   ├── main.py                  # Typer app definition
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── run.py               # factory run
│   │   ├── status.py            # factory status
│   │   ├── stop.py              # factory stop
│   │   ├── list_cmd.py          # factory list
│   │   ├── logs.py              # factory logs
│   │   ├── deploy.py            # factory deploy
│   │   ├── scan.py              # factory scan-models
│   │   ├── research.py          # factory self-research
│   │   ├── health.py            # factory health
│   │   ├── backup.py            # factory backup/restore
│   │   ├── update.py            # factory update
│   │   └── config_cmd.py        # factory config sync
│   └── output/                  # Rich formatters
│       ├── __init__.py
│       ├── tables.py
│       ├── progress.py
│       └── panels.py
│
├── services/                    # Core business logic
│   ├── __init__.py
│   ├── project_service.py       # Project CRUD + lifecycle
│   ├── factory_runner.py        # tmux session management (v1.0 upgraded)
│   ├── factory_orchestrator.py  # NEW: Phase state machine
│   ├── provider_registry.py     # NEW: Provider management
│   ├── model_router.py          # NEW: LiteLLM + fallback routing
│   ├── model_scanner.py         # NEW: Free model scanner + grading
│   ├── clink_router.py          # NEW: Local CLI routing via zen MCP
│   ├── self_researcher.py       # NEW: Auto-improvement research
│   ├── health_monitor.py        # NEW: System health checks
│   ├── backup_service.py        # NEW: Backup/restore
│   ├── cost_tracker.py          # NEW: Per-provider cost tracking
│   ├── template_service.py      # NEW: Project templates
│   ├── notification.py          # Telegram notification with rate limiting (v1.0 upgraded)
│   ├── settings_service.py      # Settings management (v1.0 upgraded)
│   ├── run_monitor.py           # Log tail + event emission (v1.0 upgraded)
│   ├── docker_service.py        # Docker management (v1.0 upgraded)
│   ├── system_service.py        # VPS management (v1.0 upgraded)
│   ├── analytics_service.py     # Analytics (v1.0 upgraded)
│   ├── transcription.py         # Voice transcription (v1.0)
│   ├── translation.py           # Translation service (v1.0)
│   └── user_service.py          # User management (v1.0)
│
├── providers/                   # NEW: LLM Provider abstraction
│   ├── __init__.py
│   ├── base.py                  # ProviderAdapter Protocol + response schemas
│   ├── registry.py              # Provider registry + health tracking
│   ├── litellm_adapter.py       # LiteLLM-based adapter (Groq, NVIDIA, Together, etc.)
│   ├── google_ai_adapter.py     # Google AI Studio custom adapter
│   ├── sambanova_adapter.py     # SambaNova custom adapter
│   ├── clink_adapter.py         # clink (local CLI) adapter
│   ├── rate_limiter.py          # Per-provider rate limit tracker
│   └── fallback_chain.py        # Waterfall fallback logic
│
├── orchestrator/                # NEW: Factory pipeline logic
│   ├── __init__.py
│   ├── state_machine.py         # Phase FSM (pending→running→scoring→passed/failed)
│   ├── phases/
│   │   ├── __init__.py
│   │   ├── phase0_assessment.py # Complexity assessment
│   │   ├── phase1_requirements.py
│   │   ├── phase2_brainstorm.py
│   │   ├── phase3_architecture.py
│   │   ├── phase4_implementation.py
│   │   ├── phase5_review.py
│   │   ├── phase6_testing.py
│   │   └── phase7_release.py
│   ├── quality_gate.py          # Scoring rubric + pass/fail logic
│   ├── information_barrier.py   # File access control per role
│   └── audit_logger.py          # Structured audit logging
│
├── models/                      # SQLAlchemy ORM models
│   ├── __init__.py
│   ├── base.py                  # Base model with ID, timestamps
│   ├── user.py                  # (v1.0)
│   ├── project.py               # (v1.0, extended)
│   ├── factory_run.py           # (v1.0, extended)
│   ├── factory_event.py         # (v1.0)
│   ├── orchestration_state.py   # NEW: Per-run orchestration state
│   ├── model_provider.py        # NEW: Provider config + status
│   ├── api_usage.py             # NEW: Per-call usage log
│   ├── rate_limit.py            # NEW: Provider rate limit tracking
│   ├── model_benchmark.py       # NEW: Scan results + scores
│   ├── self_research.py         # NEW: Research reports + suggestions
│   ├── scheduled_task.py        # NEW: Cron-like scheduled tasks
│   ├── backup.py                # NEW: Backup records
│   ├── setting.py               # (v1.0, extended)
│   ├── node.py                  # (v1.0, future multi-node)
│   ├── deployment.py            # (v1.0)
│   └── analytics.py             # (v1.0)
│
├── database/
│   ├── __init__.py
│   ├── engine.py                # (v1.0)
│   ├── session.py               # (v1.0)
│   ├── persistence.py           # PTB BasePersistence (v1.0)
│   └── events.py                # NEW: LISTEN/NOTIFY helper
│
├── utils/
│   ├── __init__.py
│   ├── log_parser.py            # (v1.0)
│   ├── formatting.py            # (v1.0, extended with new views)
│   ├── validators.py            # (v1.0, extended)
│   └── token_counter.py         # NEW: Token estimation for context budgeting
│
├── installer/                   # NEW: Python installer module
│   ├── __init__.py
│   ├── main.py                  # Installer state machine
│   ├── steps/
│   │   ├── __init__.py
│   │   ├── system_deps.py       # OS packages
│   │   ├── python_setup.py      # Python venv + deps
│   │   ├── docker_setup.py      # Docker + PostgreSQL
│   │   ├── engine_install.py    # Claude, Gemini, OpenCode, Aider
│   │   ├── mcp_setup.py         # MCP servers
│   │   ├── api_keys.py          # Interactive key setup + validation
│   │   └── systemd_setup.py     # Service file creation
│   └── utils.py                 # Installer helpers (checksums, progress)
│
└── templates/
    ├── engine_configs/
    │   ├── CLAUDE.md
    │   ├── GEMINI.md
    │   ├── OPENCODE.md
    │   └── .aider.conf.yml
    ├── project_templates/       # NEW: Project scaffolds
    │   ├── telegram-bot/
    │   ├── rest-api/
    │   ├── react-fastapi/
    │   └── cli-tool/
    └── prompts/
        ├── requirements_structurer.txt
        ├── summary_generator.txt
        └── translator.txt
```

## 4. Service Contracts

### 4.1 FactoryOrchestrator (NEW)

```python
class FactoryOrchestrator:
    """Phase state machine. Runs in factory-worker.service."""

    async def start_pipeline(
        self,
        project: Project,
        engine: str,
        tier: int | None = None,  # None = auto-detect
        model_overrides: dict[str, str] | None = None,
        created_by: int = 0,
        interface_source: str = "telegram",  # "telegram" | "cli"
    ) -> FactoryRun:
        """Create run, assess complexity, start phase 0."""

    async def resume_pipeline(self, run_id: UUID) -> None:
        """Resume a paused/failed pipeline from last completed phase."""

    async def advance_phase(self, run_id: UUID) -> None:
        """Called by worker loop. Executes current phase, scores gate, transitions."""

    async def score_quality_gate(
        self, run_id: UUID, phase: int, artifacts: dict
    ) -> QualityGateResult:
        """Score artifacts against rubric. Returns pass/fail + breakdown."""

    async def handle_gate_failure(
        self, run_id: UUID, result: QualityGateResult
    ) -> str:
        """Iterate, escalate, or proceed based on failure policy. Returns action taken."""

    async def get_orchestration_state(self, run_id: UUID) -> OrchestrationState | None:
        """Get current orchestrator state for a run."""

    async def run_work_loop(self) -> None:
        """Main worker loop: poll DB for runs in 'running' state, advance phases."""

    async def resume_interrupted_runs(self) -> None:
        """On startup: find runs with status 'running' in DB, verify tmux, resume or mark failed."""

    async def handle_clarification(self, event: dict) -> None:
        """Handle clarification answer from bot via NOTIFY. Unblocks waiting phase."""

    async def request_paid_permission(
        self, run_id: UUID, provider: str, model: str, estimated_cost: float
    ) -> bool:
        """
        Store permission request in DB. Emit NOTIFY to bot.
        Worker blocks (polls DB every 5s, timeout 5min) until user responds.
        Returns True if approved, False if denied or timed out.
        """
```

### 4.2 ProviderRegistry (NEW)

```python
class ProviderRegistry:
    """Manages all configured LLM providers."""

    async def register_provider(self, config: ProviderConfig) -> None:
        """Add a provider adapter. Called at startup from config."""

    async def get_provider(self, name: str) -> ProviderAdapter | None:
        """Get a specific provider adapter."""

    async def list_providers(
        self, free_only: bool = False, healthy_only: bool = False
    ) -> list[ProviderInfo]:
        """List all registered providers with status."""

    async def get_best_model_for_role(
        self, role: str, free_only: bool = True
    ) -> ModelRecommendation | None:
        """Suggest best model for a factory role based on benchmarks + availability."""

    async def health_check_all(self) -> dict[str, HealthStatus]:
        """Run health check on all providers. Returns provider_name -> status."""
```

#### Supporting DTOs (ProviderRegistry)
```python
@dataclass
class ProviderConfig:
    name: str                   # "groq", "nvidia", etc.
    display_name: str
    api_base_url: str | None
    api_key_env_var: str        # env var name
    is_free: bool
    priority_score: int         # higher = preferred
    openai_compatible: bool
    adapter_type: str           # "litellm" | "google_ai" | "sambanova" | "clink"
    config: dict = field(default_factory=dict)

@dataclass
class ProviderInfo:
    name: str
    display_name: str
    is_free: bool
    is_enabled: bool            # API key present and valid
    is_healthy: bool
    model_count: int
    adapter_type: str
    last_health_check: datetime | None

@dataclass
class ModelRecommendation:
    role: str                   # "orchestrator", "implementer", etc.
    provider: str
    model: str
    score: float                # 0-100
    reason: str                 # "Best HumanEval score among free models"
    context_window: int
    capability_tags: list[str]
```

### 4.3 ModelRouter (NEW)

```python
class ModelRouter:
    """Routes model calls through appropriate provider with fallback."""

    async def completion(
        self,
        role: str,                  # Factory role: "implementer", "tester", etc.
        messages: list[dict],
        *,
        run_id: UUID | None = None,
        preferred_model: str | None = None,
        free_only: bool = True,
        routing_mode: str = "auto", # "auto" | "api_direct" | "openrouter" | "clink"
        max_tokens: int | None = None,
        temperature: float = 0.7,
        tools: list[dict] | None = None,
        timeout: float = 120.0,
    ) -> CompletionResponse:
        """
        Route a completion request:
        1. Determine provider chain based on role + routing_mode + settings
        2. Try primary provider
        3. On failure: waterfall through fallback chain
        4. Before paid: ask user permission
        5. Log usage to api_usage_log
        """

    async def get_fallback_chain(
        self, role: str, free_only: bool = True
    ) -> list[tuple[str, str]]:
        """Get ordered (provider, model) fallback chain for a role."""
```

### 4.4 ModelScanner (NEW)

```python
class ModelScanner:
    """Scans and grades free models across providers."""

    async def scan_all(
        self, force: bool = False
    ) -> ScanResult:
        """
        Scan all configured providers in parallel.
        Returns cached results if < 1 hour old unless force=True.
        """

    async def grade_model(
        self, provider: str, model: str, probe_result: ProbeResult
    ) -> ModelGrade:
        """Grade a model based on quality + availability + rate limits + context + speed."""

    async def suggest_configuration(
        self, scan_result: ScanResult
    ) -> SuggestedConfig:
        """Suggest best free model per role. Includes overall viability score."""

    async def apply_suggestion(
        self, suggestion: SuggestedConfig
    ) -> None:
        """Apply suggested model configuration to settings."""
```

### 4.5 SelfResearcher (NEW)

```python
class SelfResearcher:
    """Autonomous self-improvement research capability."""

    async def run_research(
        self,
        triggered_by: str = "manual",  # "manual" | "scheduled"
        user_id: int | None = None,
    ) -> SelfResearchReport:
        """
        Research improvements:
        1. Check for new/better models (via Perplexity + provider APIs)
        2. Check for new free providers
        3. Check for engine updates
        4. Check for MCP server updates
        5. Analyze current prompt effectiveness
        6. Check dependency CVEs
        Returns report with suggestions.
        """

    async def apply_suggestion(
        self, suggestion_id: int
    ) -> ApplyResult:
        """
        Apply a suggestion:
        1. Create branch chore/self-research-<date>
        2. Apply changes (within allowed scope)
        3. Run test suite
        4. If tests pass: create PR
        5. If tests fail: revert, report failure
        """

    async def schedule_research(
        self, cron_expression: str
    ) -> ScheduledTask:
        """Set up recurring self-research."""
```

### 4.6 HealthMonitor (NEW)

```python
class HealthMonitor:
    """System health monitoring with alerts."""

    async def run_health_check(self) -> HealthReport:
        """
        Check all health metrics:
        - CPU, RAM, Disk usage
        - PostgreSQL connectivity + latency
        - Docker daemon
        - tmux availability
        - Bot process health
        - Provider API health
        - Last backup age
        Returns structured report.
        """

    async def start_periodic_checks(self, interval_seconds: int = 300) -> None:
        """Start background health check loop (default every 5 min)."""

    async def evaluate_alerts(self, report: HealthReport) -> list[Alert]:
        """Compare report against thresholds. Return triggered alerts."""
```

### 4.7 BackupService (NEW)

```python
class BackupService:
    """Database and project backup/restore."""

    async def create_backup(
        self,
        backup_type: str = "manual",  # "manual" | "daily" | "weekly" | "monthly"
        include_db: bool = True,
        include_projects: bool = True,
        include_config: bool = True,
    ) -> Backup:
        """Create a backup. Returns backup record."""

    async def restore_backup(
        self, backup_id: int, passphrase: str
    ) -> RestoreResult:
        """
        Restore from backup:
        1. Verify checksum
        2. Check schema version compatibility
        3. Create safety snapshot
        4. Apply restoration
        """

    async def list_backups(self) -> list[Backup]:
        """List all available backups."""

    async def cleanup_old_backups(self) -> int:
        """Remove backups beyond retention policy. Returns count removed."""
```

### 4.8 TaskScheduler (NEW)

```python
class TaskScheduler:
    """Cron-like scheduler for recurring tasks."""

    async def run_scheduler(self) -> None:
        """
        Main scheduler loop:
        1. Every 60s, check scheduled_tasks table for tasks where next_run <= now
        2. For each due task: acquire advisory lock, execute, update last_run/next_run
        3. Overlap policy: skip if previous execution still running (lock held)
        4. Timezone: UTC always. DST not applicable.
        """

    async def schedule_task(
        self,
        task_type: str,       # "self_research" | "model_scan" | "backup"
        cron_expression: str, # "0 2 * * 0" (Sunday 2 AM UTC)
        created_by: int | None = None,
    ) -> ScheduledTask:
        """Create or update a scheduled task."""

    async def unschedule_task(self, task_id: int) -> None:
        """Disable a scheduled task."""

    async def list_scheduled(self) -> list[ScheduledTask]:
        """List all scheduled tasks with next_run times."""

    def _calculate_next_run(self, cron_expression: str, from_time: datetime) -> datetime:
        """Parse cron expression and calculate next run time. Uses croniter library."""
```

#### Scheduler Semantics
- **Misfire handling**: If bot was down during scheduled time, run task on next scheduler tick (catch-up, max 1 missed run)
- **Locking**: Advisory lock per task_type prevents duplicate execution across bot restarts
- **Timezone**: All cron expressions are UTC. Display converts to user's timezone in Telegram.

## 5. Data Models (New + Extended)

### 5.1 OrchestrationState

```python
class OrchestrationState(Base):
    __tablename__ = "factory_orchestration_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("factory_runs.id"), unique=True)
    current_phase: Mapped[int] = mapped_column(default=0)
    phase_status: Mapped[str] = mapped_column(default="pending")
        # pending | running | scoring | passed | failed | iterating | escalated | skipped
        # Must match PhaseStatus enum in interfaces-v2.md exactly
    retry_count: Mapped[int] = mapped_column(default=0)
    quality_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_assignments: Mapped[dict] = mapped_column(JSONB)
    tier: Mapped[int] = mapped_column(default=0)
    barrier_manifest: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_gate_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(nullable=True)
    interface_source: Mapped[str] = mapped_column(default="telegram")
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    run: Mapped["FactoryRun"] = relationship(back_populates="orchestration_state")
```

### 5.2 ModelProvider

```python
class ModelProvider(Base):
    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)  # "groq", "nvidia", etc.
    display_name: Mapped[str] = mapped_column(String(100))
    api_base_url: Mapped[str | None] = mapped_column(String(255))
    is_free: Mapped[bool] = mapped_column(default=False)
    is_enabled: Mapped[bool] = mapped_column(default=False)
    api_key_env_var: Mapped[str | None] = mapped_column(String(100))
    priority_score: Mapped[int] = mapped_column(default=0)
    openai_compatible: Mapped[bool] = mapped_column(default=True)
    adapter_type: Mapped[str] = mapped_column(default="litellm")
        # "litellm" | "google_ai" | "sambanova" | "clink" | "custom"
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_healthy: Mapped[bool] = mapped_column(default=True)
    last_health_check: Mapped[datetime | None] = mapped_column(nullable=True)
```

### 5.3 ApiUsageLog

```python
class ApiUsageLog(Base):
    __tablename__ = "api_usage_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50))
    tokens_input: Mapped[int] = mapped_column(default=0)
    tokens_output: Mapped[int] = mapped_column(default=0)
    cost_estimated: Mapped[float] = mapped_column(default=0.0)
    is_free: Mapped[bool] = mapped_column(default=True)
    latency_ms: Mapped[int] = mapped_column(default=0)
    success: Mapped[bool] = mapped_column(default=True)
    error_type: Mapped[str | None] = mapped_column(nullable=True)
    factory_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("factory_runs.id"), nullable=True)
    phase: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### 5.4 ModelBenchmark

```python
class ModelBenchmark(Base):
    __tablename__ = "model_benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(100))
    provider_name: Mapped[str] = mapped_column(String(50))
    context_window: Mapped[int] = mapped_column(default=0)
    supports_tools: Mapped[bool] = mapped_column(default=False)
    supports_streaming: Mapped[bool] = mapped_column(default=False)
    supports_vision: Mapped[bool] = mapped_column(default=False)
    is_free: Mapped[bool] = mapped_column(default=True)
    benchmark_quality: Mapped[float] = mapped_column(default=0.0)  # 0-100 composite
    capability_tags: Mapped[list] = mapped_column(JSONB, default=list)
        # ["reasoning", "code", "planning", "security", "writing"]
    scan_latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    scan_success: Mapped[bool | None] = mapped_column(nullable=True)
    overall_score: Mapped[float | None] = mapped_column(nullable=True)
    last_scanned: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (UniqueConstraint("model_name", "provider_name"),)
```

### 5.5 SelfResearchReport + Suggestion

```python
class SelfResearchReport(Base):
    __tablename__ = "self_research_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    triggered_by: Mapped[str] = mapped_column(String(20))  # "manual" | "scheduled"
    triggered_by_user: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    suggestions_count: Mapped[int] = mapped_column(default=0)
    accepted_count: Mapped[int] = mapped_column(default=0)
    rejected_count: Mapped[int] = mapped_column(default=0)
    report_path: Mapped[str | None] = mapped_column(nullable=True)
    branch_name: Mapped[str | None] = mapped_column(nullable=True)
    pr_url: Mapped[str | None] = mapped_column(nullable=True)

    suggestions: Mapped[list["SelfResearchSuggestion"]] = relationship(back_populates="report")


class SelfResearchSuggestion(Base):
    __tablename__ = "self_research_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("self_research_reports.id"))
    category: Mapped[str] = mapped_column(String(50))
        # "model" | "provider" | "prompt" | "engine" | "pipeline" | "security"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(10))  # "low" | "medium" | "high"
    expected_impact: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="pending")
        # "pending" | "accepted" | "rejected"
    changes_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    report: Mapped["SelfResearchReport"] = relationship(back_populates="suggestions")
```

### 5.6 ScheduledTask

```python
class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(50))
        # "self_research" | "model_scan" | "backup" | "health_check"
    cron_expression: Mapped[str] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(default=True)
    last_run: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(nullable=True)
```

### 5.7 Backup

```python
class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(primary_key=True)
    backup_type: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(default=0)
    sha256_checksum: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(20))
    includes_db: Mapped[bool] = mapped_column(default=True)
    includes_projects: Mapped[bool] = mapped_column(default=True)
    includes_config: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    retention_until: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="completed")
```

## 6. Event System (DB-backed Outbox + NOTIFY Wake-up)

### Architecture
- **Source of truth**: `factory_events` table (already in v1.0, extended)
- **NOTIFY**: Used as a **wake-up signal only**, NOT for payload delivery
- **Delivery guarantee**: Bot polls `factory_events` by watermark (last_processed_event_id). NOTIFY triggers immediate poll. If NOTIFY is missed, periodic poll (every 5s) catches up.
- **Payload format**: JSON-encoded typed DTOs

### NOTIFY Channels (wake-up only)
| Channel | Wake-up Signal | Subscriber |
|---------|---------------|------------|
| `factory_events` | `{"event_id": 123}` | Bot (triggers poll) |
| `factory_clarify` | `{"run_id": "...", "question_id": 1}` | Worker (unblocks clarification wait) |

### Event Outbox Table (extended from v1.0)
```python
class FactoryEvent(Base):
    __tablename__ = "factory_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50))
        # "phase_started" | "phase_completed" | "phase_failed"
        # "gate_scoring" | "gate_passed" | "gate_failed"
        # "run_started" | "run_stopped" | "run_completed" | "run_failed"
        # "clarification_needed" | "clarification_answered"
        # "health_alert" | "rate_limit_alert" | "cost_alert"
        # "scan_completed" | "research_completed"
        # "paid_permission_needed" | "paid_permission_response"
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("factory_runs.id"), nullable=True)
    phase: Mapped[int | None] = mapped_column(nullable=True)
    data_json: Mapped[dict] = mapped_column(JSONB, default=dict)
        # Contains the typed DTO fields (see interfaces-v2.md section 4)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    processed: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

### Bot Event Consumer
```python
class EventConsumer:
    """Consumes events from factory_events table."""

    async def start(self) -> None:
        """
        1. Start LISTEN on 'factory_events' channel
        2. On NOTIFY: immediately poll for new events
        3. Also poll every 5s as fallback (handles missed NOTIFY)
        4. For each unprocessed event: dispatch to appropriate handler, mark processed
        """

    async def _poll_events(self) -> list[FactoryEvent]:
        """SELECT * FROM factory_events WHERE processed = FALSE ORDER BY id LIMIT 100"""

    async def _dispatch(self, event: FactoryEvent) -> None:
        """Route event to Telegram notification handler based on event_type."""
```

### Event JSON Envelope
All `data_json` fields follow this structure:
```json
{
    "version": 1,
    "event_type": "phase_completed",
    "run_id": "uuid",
    "project_name": "my-project",
    "payload": { /* typed DTO fields */ }
}
```

## 6.5 Routing Failure Policy

### Error Types and Actions
| Error | Detection | Retry | Backoff | Failover |
|-------|-----------|-------|---------|----------|
| RateLimited (429) | HTTP status | 3x | 1s, 2s, 4s (Tenacity) | Yes, to next in chain |
| AuthError (401/403) | HTTP status | 0 | N/A | Yes, mark provider disabled |
| ServerError (500-503) | HTTP status | 3x | 2s fixed | Yes after 3 retries |
| Timeout (>120s) | asyncio.timeout | 0 | N/A | Yes, immediately |
| ContextTooLong (400) | Error message parse | 0 | N/A | Yes, to model with larger context |
| ContentFilter (400) | Error message parse | 1x (rephrase) | N/A | Yes after 1 retry |
| NetworkError | ConnectionError | 3x | 1s | Yes after 3 retries |
| CostDetected | Non-zero cost header | 0 | N/A | Stop, request paid permission |

### Paid Permission Protocol
When the waterfall exhausts all free providers:
1. Worker stores `paid_permission_needed` event in `factory_events` with `{provider, model, estimated_cost}`
2. Worker enters poll-wait loop: check `factory_events` for `paid_permission_response` every 5s
3. Bot receives event, sends Telegram message: "Free providers exhausted. Use {model} on {provider} for ~${cost}? [Allow] [Deny]"
4. User responds → bot writes `paid_permission_response` event with `{approved: true/false}`
5. Worker reads response: if approved, proceed with paid call; if denied or timeout (5 min), escalate
6. Same protocol for CLI: print prompt, read stdin

### Circuit Breaker
- Per-provider circuit breaker: 5 failures in 60s → OPEN state (skip provider for 5 min)
- After 5 min: HALF-OPEN (allow 1 request). If succeeds → CLOSE. If fails → OPEN again.
- Circuit state stored in memory (not DB — ephemeral, reset on restart)

### Advisory Lock Strategy
- Lock key: `pg_advisory_lock(hashtext('run:' || run_id::text))`
- Acquisition: `pg_try_advisory_lock()` (non-blocking) with 10s retry loop
- Timeout: 10s. If not acquired, return "Run is being modified by another process"
- Scope: held for duration of phase transition (advance_phase), released after commit
- Deadlock prevention: never hold two advisory locks simultaneously

---

## 7. Provider Routing Architecture

```
                    ┌──────────────────┐
                    │   ModelRouter     │
                    │   (completion)    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Routing Mode?   │
                    └────────┬─────────┘
                 ┌───────────┼───────────┐
                 ▼           ▼           ▼
         ┌───────────┐ ┌─────────┐ ┌─────────┐
         │ api_direct │ │openrouter│ │  clink  │
         └─────┬─────┘ └────┬────┘ └────┬────┘
               │             │           │
     ┌─────────▼─────────┐  │    ┌──────▼──────┐
     │ ProviderRegistry   │  │    │ zen MCP     │
     │ (fallback chain)   │  │    │ clink tool  │
     └────────┬──────────┘  │    └──────┬──────┘
              │              │           │
    ┌─────────┼──────┐      │     ┌─────┼─────┐
    ▼         ▼      ▼      ▼     ▼     ▼     ▼
  Groq     NVIDIA  Google  OR   claude gemini codex
  (litellm)(litellm)(custom)(litellm) (CLI)  (CLI) (CLI)
```

## 8. Factory Worker Loop

```python
async def worker_main():
    """Main worker loop in factory-worker.service."""

    # 1. Connect to DB
    engine, session_factory = await init_database()

    # 2. Initialize services
    registry = ProviderRegistry(session_factory)
    router = ModelRouter(registry)
    orchestrator = FactoryOrchestrator(session_factory, router)
    health = HealthMonitor(session_factory)
    scanner = ModelScanner(registry)
    researcher = SelfResearcher(session_factory, router)
    backup = BackupService(session_factory)
    scheduler = TaskScheduler(session_factory)

    # 3. Start LISTEN on factory_clarify channel
    await start_event_listener(engine, "factory_clarify", orchestrator.handle_clarification)

    # 4. Resume any interrupted runs
    await orchestrator.resume_interrupted_runs()

    # 5. Start background tasks
    async with asyncio.TaskGroup() as tg:
        tg.create_task(orchestrator.run_work_loop())       # Process pending phase transitions
        tg.create_task(health.start_periodic_checks())      # Health checks every 5 min
        tg.create_task(scanner.start_background_scan())     # Model scan every 10 min
        tg.create_task(scheduler.run_scheduler())           # Cron-like scheduled tasks
        tg.create_task(backup.start_auto_backup())          # Daily backup
```

## 9. Installer Architecture

```
install.sh (bash bootstrap)
  │
  ├── Check OS (Ubuntu 22.04/24.04)
  ├── Install: curl, python3, ca-certificates
  ├── Download factory-installer.tar.gz
  ├── Verify SHA256 checksum
  └── Run: python3 -m factory_installer

factory_installer/ (Python state machine)
  │
  ├── Step 1: System dependencies
  │   └── apt install: docker, tmux, git, nginx, certbot, jq, Node.js
  ├── Step 2: Python setup
  │   └── Python 3.11+ (deadsnakes if needed), venv, pip install
  ├── Step 3: Docker setup
  │   └── Start Docker, pull PostgreSQL image, create volume, start DB
  ├── Step 4: Engine install
  │   └── Claude Code CLI, Gemini CLI, OpenCode, Aider
  ├── Step 5: MCP setup
  │   └── zen, perplexity, context7, github, memory
  ├── Step 6: API key configuration
  │   └── Interactive one-by-one, test each, save to .env
  ├── Step 7: Service setup
  │   └── Create systemd units, enable, start
  └── Checkpoint: each step saves progress to /opt/factory/install.state
      └── --resume flag skips completed steps
```

## 10. Telegram View Design Language

### Formatting Rules
- **Parse mode**: HTML (not MarkdownV2 — simpler escaping, consistent across all messages)
- **Escaping**: All user-provided text passed through `html.escape()` before embedding
- **Max message length**: 4096 chars. If exceeded: truncate body, add "[Full report in logs]" link
- **Edit frequency**: Max 1 edit per 3 seconds per message. Buffer updates in memory.
- **Edit fallback**: If message too old (>48h) or deleted, send new message instead.

### Base Template
```python
class TelegramView:
    """Base class for all bot messages. All render methods return (text, reply_markup)."""

    HEADER = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    DIVIDER = "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    FOOTER = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    MAX_LENGTH = 4096

    STATUS_EMOJI = {
        "running": "🟢",
        "completed": "✅",
        "failed": "🔴",
        "paused": "🟡",
        "pending": "⚪",
    }

    @staticmethod
    def progress_bar(current: int, total: int, width: int = 7) -> str:
        filled = int(width * current / total)
        return "▓" * filled + "░" * (width - filled) + f" {current}/{total}"

    def render(self, context: dict) -> tuple[str, InlineKeyboardMarkup | None]:
        """Render view. Returns (html_text, keyboard). Must be < 4096 chars."""
        raise NotImplementedError

    @staticmethod
    def truncate(text: str, max_len: int = 4096) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 30] + "\n\n[... truncated, see full logs]"
```

## 11. Configuration Schema

```python
class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    admin_user_ids: list[int]

    # Database
    database_url: str = "postgresql+asyncpg://factory:factory@localhost:5432/factory"

    # AI Providers
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    nvidia_api_key: str | None = None
    together_api_key: str | None = None
    cerebras_api_key: str | None = None
    sambanova_api_key: str | None = None
    fireworks_api_key: str | None = None
    mistral_api_key: str | None = None
    openrouter_api_key: str | None = None
    perplexity_api_key: str | None = None

    # GitHub
    github_token: str | None = None

    # Factory
    factory_root_dir: Path = Path("/home/factory/projects")
    templates_dir: Path = Path("templates")
    backup_dir: Path = Path("/home/factory/backups")

    # Routing
    default_routing_mode: str = "api_direct"  # "api_direct" | "openrouter" | "clink"
    default_quality_gate_threshold: int = 97
    default_max_retries: int = 3

    # Health
    health_check_interval: int = 300  # seconds
    disk_warning_percent: int = 80
    disk_critical_percent: int = 90

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

## 12. Deployment Architecture

### systemd Service Files

**factory-bot.service:**
```ini
[Unit]
Description=Factory Control Bot (Telegram)
After=network.target docker.service
Wants=factory-worker.service

[Service]
Type=simple
User=factory
Group=factory
WorkingDirectory=/opt/factory
EnvironmentFile=/opt/factory/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/factory/.venv/bin/python -m app.main
Restart=always
RestartSec=5
# .env file must have 600 permissions, owned by factory:factory
# Contains all API keys and DATABASE_URL

[Install]
WantedBy=multi-user.target
```

**factory-worker.service:**
```ini
[Unit]
Description=Factory Worker (Orchestrator)
After=network.target docker.service

[Service]
Type=simple
User=factory
Group=factory
WorkingDirectory=/opt/factory
EnvironmentFile=/opt/factory/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/factory/.venv/bin/python -m app.worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Secrets/Config Wiring
- `.env` file at `/opt/factory/.env` with `chmod 600` owned by `factory:factory`
- `EnvironmentFile=` directive loads all keys into service environment
- CLI reads from same `.env` via `pydantic-settings` `env_file` parameter
- `~/.factory/config.yaml` stores CLI-specific preferences (no secrets): default project, output format, etc.
- `factory config sync` regenerates `config.yaml` from current `.env` + DB settings

### Docker Compose (DB only)
```yaml
version: "3.8"
services:
  postgres:
    image: postgres:16-alpine
    container_name: factory-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: factory
      POSTGRES_PASSWORD: "${DB_PASSWORD}"
      POSTGRES_DB: factory
    volumes:
      - factory-pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"

volumes:
  factory-pgdata:
```
