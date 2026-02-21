# v2.0 Multi-Model Brainstorm

## Participants
| Model | Provider | Via |
|-------|----------|-----|
| Gemini 3 Pro | Google | zen MCP |
| GPT-5.2 | OpenAI | zen MCP |
| Llama 3.3 70B | Meta | zen MCP |
| Claude Opus 4.6 | Anthropic | Native (synthesis) |

---

## 1. Architecture: Consensus

### All 3 agree: "Shared Core + Thin Adapters" pattern
- Central core services (FactoryOrchestrator, ProviderRegistry, ModelScanner, etc.)
- Telegram adapter: thin controller layer (parse commands → call core → render views)
- CLI adapter: Typer commands → call same core → print/stream output
- Both adapters share DB as single source of truth

### Gemini 3 Pro: Event-Driven State Machine ("Reactor" Pattern)
- `FactoryOrchestrator` as persistent FSM
- `asyncio.Queue` as internal event bus
- Bot/CLI are publishers, Orchestrator is consumer
- Notification service subscribes to state changes

### GPT-5.2: Two-Process Split
- `factory-bot.service` = Telegram polling + event rendering
- `factory-worker.service` = orchestrator executor (pulls pending work from DB)
- Isolates Telegram heartbeat from long-running tasks
- Uses PostgreSQL `LISTEN/NOTIFY` for cross-process events

### Llama: Modular with task queue
- Suggested Celery/Zato for task queue
- (OVERRULED: too heavy for this; asyncio + DB is sufficient per Gemini/GPT consensus)

### SYNTHESIS: Adopted Architecture
- **Two-service split** (GPT-5.2 recommendation): separate bot from worker
- **Event-driven FSM** (Gemini recommendation): FactoryOrchestrator as state machine
- **PostgreSQL NOTIFY** (GPT-5.2): for cross-process communication
- **No external queue** (Celery/Redis unnecessary — asyncio + DB sufficient)

---

## 2. Provider Abstraction: LiteLLM Debate

### Gemini 3 Pro: USE LiteLLM
- "Do not write 13 separate HTTP adapters manually"
- LiteLLM as the heavy lifter for OpenAI-compatible providers
- Custom layer only for: waterfall logic, rate limit tracking, rotation
- Strong opinion: building custom registry from scratch is "waste of engineering time"

### GPT-5.2: CUSTOM with optional LiteLLM backing
- Build own `ProviderAdapter` Protocol as stable core
- Use LiteLLM internally for OpenAI-compatible subset
- Need custom: health checks, rate-limit tracking, waterfall, context validation, auditability
- LiteLLM doesn't cover: "provider starts charging" detection, TTFT measurement, streaming quirks

### Llama: USE LiteLLM
- "Given 13+ providers, building custom adapters would be time-consuming and prone to errors"

### SYNTHESIS: Hybrid Approach (Adopted)
- **LiteLLM as backend** for OpenAI-compatible providers (Groq, NVIDIA, Together, Cerebras, Fireworks, Mistral, OpenRouter, DeepSeek)
- **Custom adapters** for non-compatible: Google AI Studio (Google SDK), SambaNova (custom REST), HuggingFace, Cloudflare
- **Custom ProviderAdapter Protocol** wrapping everything (health checks, rate limits, telemetry, fallback logic)
- **Tenacity** for retry logic (Gemini recommendation)
- **Pydantic Settings** for config management

---

## 3. CLI Framework: Consensus

### All 3 agree: Typer + Rich
- Typer: type-hint-based CLI framework, auto-complete, help text
- Rich: progress bars, tables, formatted output
- Modern Python standard for CLI tools
- Integrates natively with Pydantic

### ADOPTED: Typer + Rich

---

## 4. Model Scanner Design: Consensus

### All agree: Parallel async probing
- `asyncio.TaskGroup` or `asyncio.gather` for concurrent scanning
- Per-provider timeout (10s)
- Probe prompt: lightweight ("Return 'OK'" per Gemini, not code generation)
- Cache results for 1 hour in DB
- Background scan every 10 minutes (Gemini suggestion) for "hot" results
- 3 consecutive failures before blacklisting (rolling window in DB)

### Grading: Split recommendation
- Gemini: 60% benchmark (static) + 40% availability (dynamic)
- Spec: 40% quality + 20% availability + 20% rate limits + 10% context + 10% speed
- **ADOPTED**: Spec formula (more granular, better role matching)

---

## 5. Self-Research Safety: Consensus

### All agree: branch-based, never auto-merge
- Gemini: AST analysis to enforce allowed-file rules
- GPT-5.2: Glob-pattern allowlist + test gate
- Both: run full test suite before PR creation

### ADOPTED:
- Allowlist of modifiable paths (templates, config, prompts, provider settings)
- Blocklist: core orchestrator, auth, DB schema, security middleware
- Test suite MUST pass on branch
- Max 10 files per PR
- Labels: `self-research`, `auto-generated`
- Never auto-merge

---

## 6. Deployment: Consensus

### Gemini 3 Pro: DISSENT on Hybrid — prefers Fat Container
- Argues tmux is "fragile dependency for production orchestrator"
- Suggests replacing tmux with Docker containers + `docker exec` for log streaming
- Concerns about docker socket security

### GPT-5.2: SUPPORTS Hybrid but recommends two-service split
- Bot + Worker on host (systemd)
- DB in Docker
- Projects in Docker containers

### SYNTHESIS: Hybrid (Adopted, with Gemini's concerns noted)
- **Hybrid** stays as spec decision (tmux access is essential for v2.0 — engines require it)
- **Gemini's tmux concern DEFERRED** to v3.0: evaluate replacing tmux with programmatic Docker control
- **Docker socket security**: create `factory` user in docker group, restrict socket access
- **Two-service split adopted** (bot + worker as separate systemd units)

---

## 7. Risks: Synthesized Top 5

| # | Risk | Source | Mitigation |
|---|------|--------|------------|
| 1 | Free tier API bans from aggressive usage | Gemini | Client-side throttling at 80% of provider limits |
| 2 | tmux/Docker state desync | Gemini | DB is source of truth; mark "Crashed" if tmux gone but DB says "Running" |
| 3 | Provider churn (APIs change, free becomes paid) | GPT-5.2 | Adapter contract tests + nightly scan; cost header circuit-breaker |
| 4 | Concurrency bugs (CLI + bot on same DB) | GPT-5.2 | Advisory locks, immutable event log, idempotent phase transitions |
| 5 | Scope creep (v2 becomes platform rewrite) | GPT-5.2 | "No new infra" rule; ship in slices: REQ-1→2→3→4; defer plugin system |

---

## 8. Dissenting Opinions (Documented)

| Opinion | Model | Status |
|---------|-------|--------|
| Replace tmux with Docker containers for engines | Gemini 3 Pro | DEFERRED to v3.0 (engines currently require tmux) |
| Use Celery/Zato for task queue | Llama 3.3 | REJECTED (asyncio + DB sufficient) |
| S3/remote backup MUST not SHOULD | Gemini 3 Pro | ADOPTED (escalate to MUST in implementation) |
| Internal FastAPI gateway for provider routing | Gemini 3 Pro | CONSIDERED (may add if complexity warrants) |
| Build entirely custom provider adapters (no LiteLLM) | GPT-5.2 (partial) | HYBRID adopted (LiteLLM for compatible, custom for rest) |
| Capability tags on models (reasoning/planning/code) | GPT-5.2 | ADOPTED (add to ModelInfo for role-matching) |
| Bash bootstrap → Python installer | GPT-5.2 | ADOPTED (bash only for prereqs, Python for logic) |

---

## 9. Tech Stack (Final)

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ | Balance of speed/async features |
| Telegram | python-telegram-bot (v21+ async) | Already in v1.0, mature |
| CLI | Typer + Rich | Consensus: modern, type-safe, beautiful |
| DB | PostgreSQL + SQLAlchemy 2.0 async | Already in v1.0, advisory locks, LISTEN/NOTIFY |
| Migrations | Alembic | Standard, already in v1.0 |
| LLM calls | LiteLLM (OpenAI-compat) + custom adapters (others) | Hybrid: fast integration + full control |
| Config | Pydantic Settings | Type-safe .env handling |
| Retry logic | Tenacity | Don't reinvent exponential backoff |
| HTTP client | httpx (async) | For custom adapters |
| Logging | structlog | Already in v1.0, structured JSON |
| Process model | 2 systemd services (bot + worker) | Isolate Telegram heartbeat from factory work |
| State sync | PostgreSQL LISTEN/NOTIFY | Cross-process events without extra infra |
| Installer | Bash bootstrap → Python installer | Robust, testable, resumable |

---

## 10. Creative Feature Suggestions

| Feature | Model | Verdict |
|---------|-------|---------|
| Docker label-based container reaper | Gemini 3 Pro | ADOPTED (cleanup zombie containers) |
| Token Budget Manager (summarize before API call) | Gemini 3 Pro | ADOPTED (prevent context overflow on free models) |
| Capability-based model routing (not just provider name) | GPT-5.2 | ADOPTED (tag models with reasoning/code/planning) |
| Read-before-edit enforcement for self-research | GPT-5.2 | ADOPTED (hash file before allowing edit) |
| Performance self-analysis with ML | Llama 3.3 | DEFERRED (too complex for v2.0) |
