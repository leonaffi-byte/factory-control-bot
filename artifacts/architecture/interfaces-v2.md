# Factory Control Bot v2.0 — Interface Contracts

This document defines the CONTRACTS between all system components. Implementers MUST follow these interfaces exactly.

---

## 1. Provider Adapter Protocol

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Protocol


@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    tokens_input: int
    tokens_output: int
    cost: float  # 0.0 for free
    latency_ms: int
    finish_reason: str  # "stop" | "length" | "tool_calls"
    tool_calls: list[dict] | None = None
    raw_response: dict | None = None


@dataclass
class ModelInfo:
    name: str
    display_name: str
    provider: str
    context_window: int
    supports_tools: bool = False
    supports_streaming: bool = False
    supports_vision: bool = False
    is_free: bool = True
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    capability_tags: list[str] = field(default_factory=list)
        # "reasoning", "code", "planning", "security", "writing", "multilingual"


@dataclass
class HealthStatus:
    is_healthy: bool
    latency_ms: int
    error: str | None = None
    last_checked: datetime | None = None


@dataclass
class RateLimitInfo:
    rpm_limit: int  # requests per minute
    rpd_limit: int  # requests per day
    rpm_remaining: int
    rpd_remaining: int
    tpm_limit: int = 0  # tokens per minute (0 = unknown)
    reset_at: datetime | None = None


class ProviderAdapter(Protocol):
    """All provider adapters MUST implement this interface."""

    name: str
    display_name: str
    is_free: bool

    async def list_models(self) -> list[ModelInfo]: ...

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,
        timeout: float = 120.0,
    ) -> CompletionResponse: ...

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> AsyncIterator[str]: ...

    async def check_health(self) -> HealthStatus: ...

    async def get_rate_limits(self) -> RateLimitInfo: ...
```

---

## 2. Quality Gate Interface

```python
@dataclass
class QualityGateResult:
    phase: int
    total_score: int  # 0-100
    completeness: int  # 0-25
    clarity: int  # 0-25
    consistency: int  # 0-25
    robustness: int  # 0-25
    passed: bool  # total_score >= threshold
    threshold: int  # default 97
    feedback: str  # explanation of scores
    gaps: list[str]  # specific issues to fix
    scored_by_model: str
    scored_by_provider: str
    iteration: int  # which attempt (1, 2, 3)


class QualityGateScorer(Protocol):
    async def score(
        self,
        phase: int,
        artifacts: dict[str, str],  # filename -> content
        iteration: int = 1,
    ) -> QualityGateResult: ...
```

---

## 3. Orchestrator State Machine

```python
from enum import Enum

class PhaseStatus(str, Enum):
    """Must match DB column allowed values exactly."""
    PENDING = "pending"
    RUNNING = "running"
    SCORING = "scoring"      # quality gate being scored
    PASSED = "passed"        # quality gate passed (gated phases) or execution complete (ungated)
    FAILED = "failed"        # quality gate failed
    ITERATING = "iterating"  # retrying after gate failure
    ESCALATED = "escalated"  # needs user input (terminal state)
    SKIPPED = "skipped"      # phase skipped by user override

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


# Phase transition rules
PHASE_TRANSITIONS = {
    PhaseStatus.PENDING: [PhaseStatus.RUNNING],
    PhaseStatus.RUNNING: [PhaseStatus.SCORING, PhaseStatus.SKIPPED],
    PhaseStatus.SCORING: [PhaseStatus.PASSED, PhaseStatus.FAILED],
    PhaseStatus.PASSED: [PhaseStatus.PENDING],  # next phase starts as pending
    PhaseStatus.FAILED: [PhaseStatus.ITERATING, PhaseStatus.ESCALATED],
    PhaseStatus.ITERATING: [PhaseStatus.RUNNING],  # retry the phase
    PhaseStatus.ESCALATED: [],  # terminal — needs user input
    PhaseStatus.SKIPPED: [PhaseStatus.PENDING],  # next phase
}

# Phases with quality gates (scored by external model, threshold >= 97)
GATED_PHASES = {1, 3, 7}
# Phases without quality gates (auto-pass on completion)
# Phase 0: auto (complexity assessment)
# Phase 2: advisory only (brainstorm, no gate)
# Phase 4: implementation (tested in phase 6)
# Phase 5: review (issues logged, no pass/fail gate)
# Phase 6: test execution (pass = 100% tests pass, own criteria not quality gate)
UNGATED_PHASES = {0, 2, 4, 5, 6}
# For ungated phases: status goes PENDING -> RUNNING -> PASSED (skip SCORING)
# For phase 6: status goes PENDING -> RUNNING -> PASSED (if all tests pass) or FAILED (if tests fail)
```

---

## 4. Event System DTOs

```python
@dataclass
class PhaseStartedEvent:
    run_id: UUID
    phase: int
    phase_name: str
    model_assignments: dict[str, str]

@dataclass
class PhaseCompletedEvent:
    run_id: UUID
    phase: int
    phase_name: str
    quality_score: int | None  # None for ungated phases
    duration_seconds: int

@dataclass
class GateResultEvent:
    run_id: UUID
    phase: int
    score: int
    passed: bool
    iteration: int
    feedback: str

@dataclass
class ClarificationNeededEvent:
    run_id: UUID
    question_id: int
    question_text: str
    options: list[str] | None  # None = open-ended

@dataclass
class AlertEvent:
    alert_type: str  # "health" | "rate_limit" | "cost" | "disk"
    severity: str  # "warning" | "critical"
    message: str
    data: dict

@dataclass
class RunStartedEvent:
    run_id: UUID
    project_name: str
    engine: str
    tier: int
    interface_source: str  # "telegram" | "cli"

@dataclass
class RunStoppedEvent:
    run_id: UUID
    project_name: str
    reason: str  # "user_stopped" | "escalated" | "crashed"

@dataclass
class RunCompletedEvent:
    run_id: UUID
    project_name: str
    engine: str
    duration_seconds: int
    total_cost: float
    quality_scores: dict[int, int]  # phase -> score
    test_results: str  # "50/50 passed"

@dataclass
class RunFailedEvent:
    run_id: UUID
    project_name: str
    phase: int
    error: str

@dataclass
class PaidPermissionNeededEvent:
    run_id: UUID
    provider: str
    model: str
    estimated_cost: float
    reason: str  # "All free providers exhausted"

@dataclass
class PaidPermissionResponseEvent:
    run_id: UUID
    approved: bool
    responded_by: int  # user ID

@dataclass
class ScanCompletedEvent:
    total_providers: int
    healthy_providers: int
    best_free_viability: int  # 0-100
    duration_seconds: float

@dataclass
class ResearchCompletedEvent:
    report_id: int
    suggestions_count: int
    summary: str
```

---

## 5. Model Scanner DTOs

```python
@dataclass
class ProbeResult:
    provider: str
    model: str
    success: bool
    latency_ms: int
    error: str | None = None

@dataclass
class ModelGrade:
    provider: str
    model: str
    overall_score: float  # 0-100
    quality_score: float  # from benchmarks
    availability_score: float  # from probe
    rate_limit_score: float
    context_score: float
    speed_score: float
    is_available: bool
    context_window: int
    capability_tags: list[str]

@dataclass
class RoleRecommendation:
    role: str
    provider: str
    model: str
    score: float
    reason: str

@dataclass
class SuggestedConfig:
    recommendations: list[RoleRecommendation]
    overall_viability: int  # 0-100
    viability_description: str  # "Good for Tier 1-2" etc.
    scan_duration_seconds: float
    providers_scanned: int
    providers_healthy: int
    cached: bool
    cache_age_minutes: float

@dataclass
class ScanResult:
    grades: list[ModelGrade]
    suggestion: SuggestedConfig
    timestamp: datetime
    cached: bool
```

---

## 6. Self-Research DTOs

```python
@dataclass
class ResearchSuggestion:
    category: str  # "model" | "provider" | "prompt" | "engine" | "pipeline" | "security"
    title: str
    description: str
    risk_level: str  # "low" | "medium" | "high"
    expected_impact: str
    source_url: str | None = None
    changes: list[FileChange] = field(default_factory=list)

@dataclass
class FileChange:
    file_path: str
    change_type: str  # "modify" | "create" | "delete"
    description: str

@dataclass
class SelfResearchReport:
    id: int
    triggered_by: str
    started_at: datetime
    completed_at: datetime
    suggestions: list[ResearchSuggestion]
    overall_summary: str

@dataclass
class ApplyResult:
    success: bool
    branch_name: str | None = None
    pr_url: str | None = None
    error: str | None = None
    test_results: str | None = None
```

---

## 7. Health Monitor DTOs

```python
@dataclass
class HealthMetric:
    name: str
    status: str  # "ok" | "warning" | "critical"
    value: str  # human-readable
    details: str | None = None

@dataclass
class HealthReport:
    timestamp: datetime
    overall_status: str  # "healthy" | "degraded" | "critical"
    metrics: list[HealthMetric]
    alerts: list[Alert]

@dataclass
class Alert:
    alert_type: str
    severity: str  # "warning" | "critical"
    message: str
    metric_name: str
    metric_value: str
    threshold: str
    remediation: str | None = None
    muted_until: datetime | None = None
```

---

## 8. Backup DTOs

```python
@dataclass
class BackupInfo:
    id: int
    backup_type: str
    file_path: str
    file_size_bytes: int
    sha256_checksum: str
    schema_version: str
    includes_db: bool
    includes_projects: bool
    includes_config: bool
    created_at: datetime
    retention_until: date | None

@dataclass
class RestoreResult:
    success: bool
    backup_id: int
    schema_compatible: bool
    safety_snapshot_path: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
```

---

## 9. CLI Command Interface

```
factory run <project> [--engine ENGINE] [--tier TIER] [--free-only]
factory status [PROJECT]
factory stop <PROJECT|RUN_ID>
factory list [--status STATUS] [--json]
factory logs <PROJECT> [--follow] [--lines N]
factory deploy <PROJECT> [--docker|--manual]
factory scan-models [--verbose] [--force] [--json]
factory self-research [--apply] [--dry-run]
factory health [--json]
factory backup [--type TYPE]
factory restore <BACKUP_ID> --passphrase PASS
factory update [--engines-only]
factory config sync
factory providers [--free-only] [--json]
factory install-engines [--claude] [--gemini] [--opencode] [--aider]
```

---

## 10. Telegram Command Interface

| Command | Description | Handler |
|---------|-------------|---------|
| /start | Welcome screen + onboarding | start.py |
| /menu | Main menu | start.py |
| /new | New project wizard | new_project.py |
| /projects | Project list | projects.py |
| /run | Start factory run | factory.py |
| /stop | Stop factory run | factory.py |
| /status | Run status | factory.py |
| /scan | Scan free models | scan.py |
| /research | Self-research | research.py |
| /health | Health report | health.py |
| /backup | Create backup | backup.py |
| /restore | Restore from backup | backup.py |
| /docker | Docker management | docker.py |
| /system | System management | system.py |
| /settings | Settings | settings.py |
| /analytics | Analytics dashboard | analytics.py |
| /providers | Provider status | scan.py |
| /help | Help | help.py |

---

## 11. Information Barrier Contracts

### Phase 4 Barriers

```python
# Note: paths are relative to project directory. The orchestrator resolves
# the actual filenames (which may be spec.md, spec-v2.md, etc.) based on
# what exists in the project artifacts directory. These are GLOB patterns.
IMPLEMENTER_ALLOWED = [
    "artifacts/requirements/spec*.md",
    "artifacts/architecture/design*.md",
    "artifacts/architecture/interfaces*.md",
]
IMPLEMENTER_WRITES = "artifacts/code/"
IMPLEMENTER_BLOCKED = [
    "artifacts/tests/",
]

TESTER_ALLOWED = [
    "artifacts/requirements/spec*.md",
    "artifacts/architecture/interfaces*.md",
]
TESTER_WRITES = "artifacts/tests/"
TESTER_BLOCKED = [
    "artifacts/code/",
]
```

### Enforcement
```python
class InformationBarrier:
    """Enforces file access rules per role."""

    def validate_access(
        self, role: str, file_path: str, access_type: str
    ) -> bool:
        """Check if role can read/write the file path."""

    def get_allowed_files(self, role: str) -> list[str]:
        """Get list of files a role is allowed to access."""

    def filter_artifacts(
        self, role: str, artifacts: dict[str, str]
    ) -> dict[str, str]:
        """Filter artifact dict to only allowed files for role."""
```

---

## 12. Notification Message Templates

### Phase Completed
```
✅ Phase {N} Complete: {phase_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Quality Gate: {score}/100 {pass_emoji}
⏱ Duration: {duration}
💰 Cost: ${cost} ({provider_breakdown})

{progress_bar}

[📋 Details] [⏭ Next Phase]
```

### Factory Complete
```
🏁 Factory Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━

🏭 {project_name} · {engine}
⏱ Total: {duration}
💰 Total: ${cost}

📊 Quality Gates:
  P1: {s1}/100 · P3: {s3}/100 · P7: {s7}/100

🧪 Tests: {passed}/{total} passed
📦 Files: {file_count} · {line_count} lines

🔗 GitHub: {repo_url}
{deploy_status}

[🚀 Deploy] [📋 Full Report] [➕ Add Feature]
```

### Alert
```
⚠️ Alert: {alert_type}
━━━━━━━━━━━━━━━━━━━━━━━━━━

{severity_emoji} {message}
📊 {metric}: {value} (threshold: {threshold})

💡 {remediation}

[🔇 Mute 1h] [🔇 Mute 24h]
```
