# Factory Control Bot v2.0 — Requirements Specification

## Document Info
- **Version**: 2.0
- **Base**: v1.0.0 (complete, 50/50 tests, all quality gates passed)
- **Date**: 2026-02-21
- **Tier**: 3 (Complex)
- **Analyst**: Gemini 3 Pro (via zen MCP) + Claude Opus 4.6 (Orchestrator)
- **Research**: Perplexity Sonar Deep Research (free provider landscape)

---

## Executive Summary

v2.0 transforms the Factory Control Bot from a Telegram remote control into a **unified AI software factory platform**. The factory pipeline logic moves from prompt-only configs into Python services. The platform gains a CLI interface, comprehensive free model provider support, real-time model scanning, local CLI routing via clink, one-line installation, self-research capabilities, and a polished modern UI.

---

## REQ-1: Unified Project Architecture

### Overview
Merge the Black Box Software Factory pipeline logic into the bot codebase. One project, two interfaces (Telegram + CLI).

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Implement `FactoryOrchestrator` Python class managing full build lifecycle (phases 0-7) | MUST |
| FR-1.2 | Orchestrator implements quality gates, information barriers, cross-provider verification as Python logic | MUST |
| FR-1.3 | Orchestrator manages model routing based on tier selection and user settings | MUST |
| FR-1.4 | Dual interface: all factory operations accessible via Telegram AND CLI (`factory <command>`) | MUST |
| FR-1.5 | CLI commands: `factory run`, `factory status`, `factory stop`, `factory list`, `factory logs`, `factory deploy` | MUST |
| FR-1.6 | CLI uses same database and services as Telegram bot (shared state) | MUST |
| FR-1.7 | Engine configs (CLAUDE.md, GEMINI.md, OPENCODE.md, AIDER.conf) remain as template files copied per-project | MUST |
| FR-1.8 | Orchestrator uses `libtmux` or `asyncio.subprocess` to manage engine tmux sessions | MUST |
| FR-1.9 | On bot restart, re-attach to existing tmux sessions and reconcile with DB state | MUST |
| FR-1.10 | Detect zombie tmux sessions (no matching DB record) and offer cleanup | SHOULD |
| FR-1.11 | CLI built with `click` or `typer` for modern CLI UX with help text, auto-complete | SHOULD |
| FR-1.12 | CLI shares authentication via config file (~/.factory/config.yaml) | MUST |

### Non-Functional Requirements
- CLI response time < 200ms for status queries
- Support 5+ concurrent factory runs without blocking Telegram heartbeat
- Shared SQLAlchemy async session pool between bot and CLI (when bot is running)
- CLI can operate standalone (direct DB connection) when bot is down

### Data Model Changes
- `factory_orchestration_state` table: tracks orchestrator state per run (current phase, retry count, quality scores per phase, model assignments)
- Add `interface_source` column to `factory_runs`: 'telegram' | 'cli' | 'api'
- Add `orchestrator_config_json` to `factory_runs`: serialized orchestrator settings for reproducibility

### CLI Interface
```
factory run <project-name> [--engine claude|gemini|opencode|aider] [--tier 1|2|3|auto]
factory status [project-name]
factory stop <project-name|run-id>
factory list [--status running|completed|failed]
factory logs <project-name> [--follow] [--lines 50]
factory deploy <project-name> [--docker|--manual]
factory scan-models [--verbose]
factory self-research [--apply]
factory update
factory install-engines
```

### Edge Cases
- Bot crash during active orchestration: on restart, check `factory_orchestration_state` and resume from last completed phase
- Concurrent CLI and Telegram commands on same project: use DB-level locking on run state transitions
- tmux session dies unexpectedly: detect via periodic health check, notify user, offer retry from last phase

### Dependencies
- None (foundation for all other requirements)

### Acceptance Criteria
- [ ] User starts a factory run via CLI, sees status updates in Telegram
- [ ] User stops a run via Telegram, CLI confirms stopped state
- [ ] Factory run completes all 7 phases with quality gates via the Python orchestrator
- [ ] Bot restart during Phase 4 resumes from Phase 4 (not Phase 0)

---

## REQ-2: Free Model Provider Integration

### Overview
Abstract model provider layer to support 10+ free-tier providers, eliminating surprise charges from OpenRouter.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | Implement `ProviderRegistry` with pluggable provider adapters | MUST |
| FR-2.2 | Each adapter implements: `list_models()`, `chat_completion()`, `check_health()`, `get_rate_limits()` | MUST |
| FR-2.3 | Unified OpenAI-compatible interface across all providers | MUST |
| FR-2.4 | Provider adapters for: NVIDIA NIM, Groq, Google AI Studio, Together AI, Cerebras, SambaNova, Fireworks AI, Mistral, HuggingFace, Cloudflare Workers AI, OpenRouter, DeepSeek, Alibaba/Qwen | MUST |
| FR-2.5 | Waterfall fallback: free provider A -> free B -> free C -> ask user before paid | MUST |
| FR-2.6 | Track usage per provider: requests today, tokens today, estimated cost | MUST |
| FR-2.7 | Alert at 80% of daily rate limit; pause at 100% and switch to next provider | MUST |
| FR-2.8 | Clearly label each provider as FREE or PAID in all UIs | MUST |
| FR-2.9 | OpenRouter marked as PAID by default; user can opt-in for free models only | MUST |
| FR-2.10 | Context window validation: skip provider if model context < required context | MUST |
| FR-2.11 | Automatic retry on HTTP 429 with exponential backoff, then failover | MUST |
| FR-2.12 | Provider health dashboard accessible via `/providers` or `factory providers` | SHOULD |
| FR-2.13 | Cost tracking: log each API call with provider, model, tokens, cost (0 for free) | MUST |

### Free Provider Details (from Perplexity Research)

| Provider | Free Models | Rate Limits (Free) | Context | API Compatible |
|----------|-------------|-------------------|---------|---------------|
| NVIDIA NIM | Kimi K2.5, Qwen, Nemotron | Generous | 256K | OpenAI |
| Groq | Llama 3.1 8B, Llama 3.3 70B, Mistral | 1440 RPM (8B), 240 RPM (70B) | 128K | OpenAI |
| Google AI Studio | Gemini 3 Pro, 2.5 Pro, 2.5 Flash | 300 RPM / 1000 RPD (standard) | 1M | Google SDK |
| Together AI | DeepSeek-R1, Kimi K2, Qwen3 | Some $0.00/token models | 256K | OpenAI |
| Cerebras | Qwen3-Coder, open-source models | Free tier available | 131K | OpenAI |
| SambaNova | DeepSeek-R1, Llama 3.1 | $5 free credit (~30M tokens) | 128K | REST |
| Fireworks AI | Various open-source | Limited without payment | 128K | OpenAI |
| Mistral AI | Mistral Small/Large, Codestral | Experiment plan (free) | 128K | OpenAI |
| OpenRouter | 30+ free models | 20 RPM / 200 RPD | Varies | OpenAI |
| DeepSeek | V3.2, R1 (via OpenRouter free) | Via aggregator | 128K | OpenAI |

### Data Model Changes
```sql
CREATE TABLE model_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,  -- 'nvidia', 'groq', 'google_ai', etc.
    display_name VARCHAR(100) NOT NULL,
    api_base_url VARCHAR(255),
    is_free BOOLEAN DEFAULT FALSE,
    is_enabled BOOLEAN DEFAULT FALSE,
    api_key_env_var VARCHAR(100),  -- env var name for the API key
    priority_score INT DEFAULT 0,  -- higher = preferred
    openai_compatible BOOLEAN DEFAULT TRUE,
    config_json JSONB  -- provider-specific config
);

CREATE TABLE api_usage_log (
    id SERIAL PRIMARY KEY,
    provider_id INT REFERENCES model_providers(id),
    model_name VARCHAR(100),
    tokens_input INT,
    tokens_output INT,
    cost_estimated DECIMAL(10, 6) DEFAULT 0,
    is_free BOOLEAN DEFAULT TRUE,
    factory_run_id UUID REFERENCES factory_runs(id),
    role VARCHAR(50),  -- 'implementer', 'tester', 'reviewer', etc.
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE provider_rate_limits (
    provider_id INT REFERENCES model_providers(id),
    model_name VARCHAR(100),
    rpm_limit INT,
    rpd_limit INT,
    tpm_limit INT,
    tpd_limit INT,
    requests_today INT DEFAULT 0,
    tokens_today INT DEFAULT 0,
    last_reset DATE DEFAULT CURRENT_DATE,
    PRIMARY KEY (provider_id, model_name)
);
```

### Edge Cases
- Provider returns 429: exponential backoff (1s, 2s, 4s), then failover to next provider in chain
- Provider returns 5xx: mark unhealthy, retry after 60s, notify user if persistent
- Free provider starts charging: detect non-zero cost in response headers, alert user immediately
- API key missing/invalid: skip provider silently in fallback chain, log warning
- Context exceeds model limit: automatically try next model with larger context

### Acceptance Criteria
- [ ] Factory run completes using only free providers (no OpenRouter charges)
- [ ] When Groq hits rate limit, system automatically fails over to NVIDIA NIM
- [ ] Cost report shows $0.00 for a full free-tier run
- [ ] `/providers` shows real-time health and usage for all configured providers

---

## REQ-3: Free Model Scanner Command

### Overview
Real-time scanning and grading of all available free models to suggest optimal free configuration.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | `/scan-models` Telegram command and `factory scan-models` CLI command | MUST |
| FR-3.2 | Scan all configured providers with API keys present | MUST |
| FR-3.3 | For each provider/model: test connectivity with a standard probe prompt | MUST |
| FR-3.4 | Measure: latency (TTFT + total), success/failure, reported rate limits | MUST |
| FR-3.5 | Grade each model 0-100 based on: quality (40%), availability (20%), rate limits (20%), context window (10%), speed (10%) | MUST |
| FR-3.6 | Model quality score derived from known benchmark data (stored/cached) | MUST |
| FR-3.7 | Suggest best free model for each factory role based on role requirements | MUST |
| FR-3.8 | Show overall "free factory viability" score (0-100) with description | MUST |
| FR-3.9 | One-click "Accept Suggestion" button in Telegram to apply config | MUST |
| FR-3.10 | Cache scan results for 1 hour; show cached age in output | SHOULD |
| FR-3.11 | `--verbose` flag shows detailed per-model breakdown | SHOULD |
| FR-3.12 | Require 3 consecutive failures before blacklisting a provider (prevent flaky blacklisting) | MUST |

### Probe Prompt
Standard test: "Write a Python function that checks if a number is prime. Return only the code."
- Tests: code generation ability, response format, latency

### Grading Formula
```
score = (quality_weight * quality_score) + (availability_weight * availability_score) +
        (rate_limit_weight * rate_limit_score) + (context_weight * context_score) +
        (speed_weight * speed_score)

quality_score: based on model benchmark data (MMLU, HumanEval, etc.) normalized 0-100
availability_score: 100 if responding, 0 if down, 50 if slow (>5s)
rate_limit_score: normalized based on RPM/RPD (higher = better)
context_score: normalized based on context window (larger = better, log scale)
speed_score: normalized based on TTFT (faster = better)
```

### Role-to-Model Mapping Criteria
| Role | Key Requirements | Preferred Qualities |
|------|-----------------|-------------------|
| Orchestrator | Planning, reasoning, long context | High benchmark, large context |
| Implementer | Code generation, accuracy | HumanEval score, speed |
| Tester | Test writing, spec comprehension | Reasoning ability, accuracy |
| Reviewer | Code analysis, security awareness | Large context, reasoning |
| Security Auditor | Vulnerability detection | Security benchmarks, reasoning |
| Docs Writer | Technical writing | Clarity, instruction following |

### Telegram Output Format
```
📊 Free Model Scanner Results
━━━━━━━━━━━━━━━━━━━━━━━━━

🏆 Overall Free Viability: 78/100 (Good)
"A free-only factory run is viable for Tier 1-2 projects"

📋 Suggested Configuration:
┌─────────────┬──────────────────┬───────┐
│ Role        │ Model            │ Score │
├─────────────┼──────────────────┼───────┤
│ Orchestrator│ Gemini 3 Pro     │ 92/100│
│ Implementer │ Llama 3.3 70B    │ 85/100│
│ Tester      │ Qwen3 Coder      │ 81/100│
│ Reviewer    │ DeepSeek R1      │ 88/100│
│ Security    │ Gemini 2.5 Pro   │ 86/100│
│ Docs        │ Llama 3.3 70B    │ 82/100│
└─────────────┴──────────────────┴───────┘

⚡ 3 providers scanned in 4.2s
📦 Results cached for 1 hour

[✅ Apply Suggestion] [🔄 Rescan] [📋 Details]
```

### Data Model Changes
```sql
CREATE TABLE model_benchmarks (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100),
    provider_name VARCHAR(50),
    benchmark_mmlu DECIMAL(5,2),
    benchmark_humaneval DECIMAL(5,2),
    benchmark_reasoning DECIMAL(5,2),
    context_window INT,
    scan_latency_ms INT,
    scan_success BOOLEAN,
    overall_score DECIMAL(5,2),
    last_scanned TIMESTAMP,
    UNIQUE(model_name, provider_name)
);
```

### Edge Cases
- All providers down: show "No free models currently available" with suggestion to retry
- Single provider flapping: 3 consecutive failures to blacklist, auto-re-check every 30 min
- Scan takes too long (>30s): timeout per provider at 10s, return partial results
- No API keys configured: show which providers need keys and how to add them

### Acceptance Criteria
- [ ] `/scan-models` returns sorted results within 30 seconds
- [ ] Clicking "Apply Suggestion" updates runtime config immediately
- [ ] Suggestions are sensible (don't assign 8B model to orchestrator role)
- [ ] Re-scan after 1 hour shows fresh data

---

## REQ-4: clink Toggle (Routing Strategy)

### Overview
Allow users to route model calls through OpenRouter API, direct provider APIs, or local CLIs via zen MCP's `clink` tool.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Global setting `routing_mode`: 'api_direct' | 'openrouter' | 'clink' | MUST |
| FR-4.2 | Per-role override: each factory role can have its own routing mode | SHOULD |
| FR-4.3 | clink mode uses `mcp__zen__clink` tool with cli_name parameter | MUST |
| FR-4.4 | Supported clink CLIs: claude, gemini, codex | MUST |
| FR-4.5 | Auto-detect installed CLIs: `which claude`, `which gemini`, `which codex` | MUST |
| FR-4.6 | Gray out / disable clink options for CLIs not installed on host | MUST |
| FR-4.7 | Settings UI shows routing mode with clear descriptions | MUST |
| FR-4.8 | When clink selected, capture CLI stderr for auth errors and forward to user | MUST |
| FR-4.9 | clink supports roles: 'default', 'codereviewer', 'planner' per CLI | SHOULD |
| FR-4.10 | Mixed mode: clink for Claude/Gemini, direct API for others | SHOULD |

### Settings UI (Telegram)
```
⚙️ Model Routing
━━━━━━━━━━━━━━━

Current: Direct API

Choose routing method:
[🌐 OpenRouter] [🔌 Direct API] [💻 Local CLI (clink)]

Local CLIs detected:
✅ claude (installed)
✅ gemini (installed)
❌ codex (not found)

[Apply] [Cancel]
```

### Data Model Changes
- Add `routing_mode` to `settings` table (global)
- Add `routing_mode` column to per-project settings JSON
- Add `routing_overrides_json` for per-role routing config

### Edge Cases
- CLI not logged in: capture auth error, send to user via Telegram, suggest `claude login` or `gemini auth`
- CLI crashes mid-request: timeout after 120s, failover to API if configured
- clink unavailable (zen MCP down): fall back to direct API with warning

### Acceptance Criteria
- [ ] User switches to clink in settings, factory uses local Gemini CLI for Gemini roles
- [ ] When Claude CLI is not installed, clink option shows it as unavailable
- [ ] Mixed mode works: clink for Claude, direct API for Groq

---

## REQ-5: One-Line Install Script

### Overview
Single command deploys the entire factory platform on a fresh Ubuntu VPS.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | `curl -fsSL <url>/install.sh \| bash` works on fresh Ubuntu 22.04/24.04 | MUST |
| FR-5.2 | Detect OS version, architecture; fail gracefully on unsupported systems | MUST |
| FR-5.3 | Install system deps: Python 3.11+, Node.js 20+, Docker, docker-compose, tmux, git, nginx, certbot, jq, curl | MUST |
| FR-5.4 | Install AI engines: Claude Code CLI, Gemini CLI, OpenCode, Aider | MUST |
| FR-5.5 | Install MCP servers: zen, perplexity, context7, github, memory | MUST |
| FR-5.6 | Set up PostgreSQL in Docker with persistent volume | MUST |
| FR-5.7 | Clone project repo, create Python venv, install requirements | MUST |
| FR-5.8 | Interactive API key setup: one-by-one with description, required/optional flag, skip option | MUST |
| FR-5.9 | Test each API key after entry (validate with a ping call) | MUST |
| FR-5.10 | Generate .env file from entered keys | MUST |
| FR-5.11 | Create systemd service file for auto-restart | MUST |
| FR-5.12 | Create `factory` CLI alias in /usr/local/bin | MUST |
| FR-5.13 | Idempotent: running twice doesn't break installation | MUST |
| FR-5.14 | `factory update` command: git pull + pip install + restart service | MUST |
| FR-5.15 | `factory deploy <project>`: one-line project deployment | MUST |
| FR-5.16 | Show progress with clear section headers and success/fail indicators | SHOULD |
| FR-5.17 | Support `--unattended` flag for automated setup (uses env vars for keys) | SHOULD |

### API Key Setup Flow
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 API Key Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1/12 TELEGRAM_BOT_TOKEN [REQUIRED]
  Purpose: Telegram bot communication
  Get it: https://t.me/BotFather
  Enter key (or press Enter to skip): ********
  ✅ Valid! Bot name: @MyFactoryBot

2/12 GROQ_API_KEY [REQUIRED]
  Purpose: Fast transcription (Whisper) + free inference
  Get it: https://console.groq.com
  Enter key (or press Enter to skip): ********
  ✅ Valid! Account: free tier

3/12 NVIDIA_API_KEY [OPTIONAL]
  Purpose: Free model inference via NVIDIA NIM
  Get it: https://build.nvidia.com
  Enter key (or press Enter to skip): [skipped]

...
```

### Keys to Configure
| # | Key | Purpose | Required |
|---|-----|---------|----------|
| 1 | TELEGRAM_BOT_TOKEN | Bot communication | Yes |
| 2 | GROQ_API_KEY | Whisper + free inference | Yes |
| 3 | OPENAI_API_KEY | Whisper fallback + GPT models | Recommended |
| 4 | GOOGLE_API_KEY | Gemini CLI + Google AI Studio | Recommended |
| 5 | GITHUB_TOKEN | Repo management | Recommended |
| 6 | PERPLEXITY_API_KEY | Research MCP | Recommended |
| 7 | NVIDIA_API_KEY | Free NVIDIA NIM inference | Optional |
| 8 | TOGETHER_API_KEY | Together AI free models | Optional |
| 9 | CEREBRAS_API_KEY | Cerebras fast inference | Optional |
| 10 | SAMBANOVA_API_KEY | SambaNova inference | Optional |
| 11 | FIREWORKS_API_KEY | Fireworks AI | Optional |
| 12 | MISTRAL_API_KEY | Mistral AI | Optional |
| 13 | OPENROUTER_API_KEY | OpenRouter (PAID) | Optional |

### Edge Cases
- Python version too old: install from deadsnakes PPA
- Docker not starting: check systemd, retry, provide manual fix instructions
- API key invalid: show error, allow re-entry or skip
- Disk space < 5GB: warn and ask to continue
- Non-root user: use sudo where needed, create factory user

### Acceptance Criteria
- [ ] Fresh Ubuntu 22.04 VM → single command → working Telegram bot within 15 minutes
- [ ] All engines installed and functional
- [ ] `factory status` works after install
- [ ] Running install.sh again doesn't duplicate anything

---

## REQ-6: Slick Modern Telegram UI

### Overview
Professional, polished Telegram bot experience with consistent design language.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | Use `editMessageText` for all status updates (no message spam) | MUST |
| FR-6.2 | Visual progress bars: `▓▓▓▓░░░░ 4/7 Architecture` | MUST |
| FR-6.3 | Card-style project layouts with emoji status badges | MUST |
| FR-6.4 | Consistent header/footer template for all bot messages | MUST |
| FR-6.5 | Color-coded status: 🟢 running, 🔴 failed, 🟡 paused, ⚪ pending, ✅ completed | MUST |
| FR-6.6 | Inline keyboards with logical grouping and icon prefixes | MUST |
| FR-6.7 | Welcome screen for first-time users with setup wizard | MUST |
| FR-6.8 | Dark-mode friendly formatting (avoid light-gray text) | MUST |
| FR-6.9 | Loading animations using message editing (⣾⣷⣯⣟⡿⢿⣻⣽ spinner in text) | SHOULD |
| FR-6.10 | Compact notification format for push notifications (one-line with expandable) | SHOULD |
| FR-6.11 | Dashboard-style pinned message with auto-refresh | SHOULD |
| FR-6.12 | Consistent emoji vocabulary across all messages | MUST |

### Design Language
```
Header:  ━━━━━━━━━━━━━━━━━━━━━━
Content: Clean, minimal, scannable
Divider: ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
Footer:  ━━━━━━━━━━━━━━━━━━━━━━

Status badges: 🟢🔴🟡⚪✅
Actions: Inline keyboard buttons with emoji prefix
Numbers: Monospace where possible
```

### Welcome Screen
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🏭 Black Box Software Factory
        v 2 . 0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Welcome! I build software using AI.

Tell me what to build — in text or voice,
in any language — and I'll handle the rest.

▸ Multi-engine: Claude, Gemini, OpenCode, Aider
▸ Free model support: 10+ providers
▸ Full lifecycle: code → test → review → deploy

[➕ New Project] [📁 Projects]
[📊 Analytics ] [⚙️ Settings]
```

### Project Card
```
🏭 my-awesome-app
━━━━━━━━━━━━━━━━━━━━

🟢 Running · Phase 4/7 · Claude
▓▓▓▓▓░░ 71%

⏱ 12m elapsed · 💰 $0.00 (free)
📊 QG: 98 → 97 → — → —

[📋 Logs] [⏸ Pause] [⏹ Stop]
```

### Acceptance Criteria
- [ ] Every bot message follows the design language
- [ ] Progress bars update in-place (no new messages)
- [ ] First-time user sees welcome wizard
- [ ] All screens readable in dark mode

---

## REQ-7: Docker Evaluation

### Overview
Determine if Docker is the right deployment strategy given the need for tmux, local CLIs, and Docker socket access.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | Evaluate: Docker container accessing host tmux sessions | MUST |
| FR-7.2 | Evaluate: Docker socket mounting (sibling containers) | MUST |
| FR-7.3 | Evaluate: clink/local CLI access from inside container | MUST |
| FR-7.4 | Evaluate: "Fat Container" (all tools inside) vs "Thin Container" (host access) | MUST |
| FR-7.5 | Produce DOCKER_STRATEGY.md with recommendation and trade-offs | MUST |
| FR-7.6 | Implement the recommended strategy | MUST |

### Expected Findings [ASSUMPTION]
Based on v1.0 analysis:
- **tmux from Docker**: Possible via host PID namespace or socket mounting, but fragile
- **Docker socket**: Possible via volume mount `/var/run/docker.sock`, security concern
- **Local CLIs in Docker**: Requires "fat container" with all CLIs installed, large image
- **Likely recommendation**: Hybrid — bot runs on host (systemd), DB in Docker, project containers in Docker
- This allows native tmux access, native CLI access, and clean Docker for projects

### Acceptance Criteria
- [ ] DOCKER_STRATEGY.md documents all trade-offs
- [ ] Chosen strategy implemented and tested
- [ ] All functionality works under the chosen strategy

---

## REQ-8: Self-Research Function

### Overview
Autonomous self-improvement capability that researches and applies optimizations.

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.1 | `/self-research` Telegram command and `factory self-research` CLI | MUST |
| FR-8.2 | Scheduled execution via cron-like settings (e.g., "every Sunday 2 AM") | MUST |
| FR-8.3 | Research areas: prompt optimization, model assignments, new MCP servers, new free providers, pipeline improvements, engine updates | MUST |
| FR-8.4 | Uses Perplexity MCP for web-grounded research | MUST |
| FR-8.5 | Short report sent via Telegram (summary + key findings) | MUST |
| FR-8.6 | Detailed report saved to `artifacts/reports/self-research-<date>.md` | MUST |
| FR-8.7 | Each suggestion includes: what, why, expected impact, risk level (low/medium/high) | MUST |
| FR-8.8 | One-click accept per suggestion: ✅ Accept / ❌ Reject / 📋 Details | MUST |
| FR-8.9 | Accept creates git branch `chore/self-research-<date>`, applies changes, creates PR | MUST |
| FR-8.10 | Never auto-merge to main; user must approve PR | MUST |
| FR-8.11 | Check for engine updates: Claude Code, Gemini CLI, OpenCode, Aider versions | MUST |
| FR-8.12 | Compare current model benchmarks vs newer models | SHOULD |

### Research Checklist
1. **Prompts**: Search for latest prompting techniques (chain-of-thought variants, system prompt best practices)
2. **Models**: Check if new models outperform current assignments (e.g., new Llama release, new Gemini version)
3. **Free Providers**: Scan for new free tiers or changed limits
4. **MCP Servers**: Search for new MCP servers that could enhance the factory
5. **Pipeline**: Research AI software engineering best practices, new quality gate approaches
6. **Engines**: Check latest versions of Claude Code, Gemini CLI, OpenCode, Aider
7. **Security**: Check for CVEs in dependencies

### Telegram Output Format
```
🔬 Self-Research Report
━━━━━━━━━━━━━━━━━━━━━━

📅 2026-02-21 02:00 (scheduled)
⏱ Completed in 3m 42s

Found 4 suggestions:

1. 🟢 LOW RISK — Update Groq model
   Llama 3.4 70B now available (was 3.3)
   Impact: ~5% better code generation
   [✅ Accept] [❌ Reject] [📋 Details]

2. 🟡 MED RISK — New free provider: Nebius
   Offers free DeepSeek-V4 inference
   Impact: More fallback options
   [✅ Accept] [❌ Reject] [📋 Details]

3. 🟢 LOW RISK — Engine update
   Claude Code 2.1.0 available (current: 2.0.3)
   Impact: Bug fixes, new features
   [✅ Accept] [❌ Reject] [📋 Details]

4. 🔴 HIGH RISK — Pipeline change
   Research suggests adding "pre-review" phase
   Impact: Better code quality, +10min per run
   [✅ Accept] [❌ Reject] [📋 Details]

📄 Full report: artifacts/reports/self-research-2026-02-21.md
```

### Data Model Changes
```sql
CREATE TABLE self_research_reports (
    id SERIAL PRIMARY KEY,
    triggered_by VARCHAR(20),  -- 'manual' | 'scheduled'
    triggered_by_user INT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    suggestions_count INT,
    accepted_count INT DEFAULT 0,
    rejected_count INT DEFAULT 0,
    report_path TEXT,
    branch_name VARCHAR(100),
    pr_url TEXT
);

CREATE TABLE self_research_suggestions (
    id SERIAL PRIMARY KEY,
    report_id INT REFERENCES self_research_reports(id),
    category VARCHAR(50),  -- 'model', 'provider', 'prompt', 'engine', 'pipeline', 'security'
    title VARCHAR(200),
    description TEXT,
    risk_level VARCHAR(10),  -- 'low', 'medium', 'high'
    expected_impact TEXT,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'accepted', 'rejected'
    changes_json JSONB  -- what files/configs to change
);

CREATE TABLE scheduled_tasks (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(50),  -- 'self_research', 'model_scan', etc.
    cron_expression VARCHAR(50),  -- '0 2 * * 0' for Sunday 2 AM
    is_enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    created_by INT
);
```

### Edge Cases
- Self-research suggests removing a provider that's currently in use: show dependency warning
- Accept fails (can't apply changes): revert branch, notify user
- Scheduled research runs during active factory run: defer until run completes
- No internet during research: skip web research, still check local engine versions

### Acceptance Criteria
- [ ] `/self-research` completes and sends Telegram report
- [ ] Accepting a suggestion creates a branch and PR
- [ ] Scheduled research runs at configured time
- [ ] Never auto-merges to main

---

## REQ-9: Additional Improvements (Brainstorm)

### Overview
Creative additions to make this the ultimate AI software factory platform.

### Selected Features for v2.0
| ID | Feature | Priority | Rationale |
|----|---------|----------|-----------|
| FR-9.1 | **Template Library**: Pre-built templates for common project types (React+FastAPI, Telegram Bot, CLI tool, etc.) | SHOULD | Reduces project setup time by 80% |
| FR-9.2 | **GitHub Webhook Deploys**: Listen for pushes to main, auto-trigger redeploy | SHOULD | CI/CD replacement, automates deployment |
| FR-9.3 | **Cost Optimization Advisor**: Weekly cost report with savings suggestions | SHOULD | Helps users minimize spend |
| FR-9.4 | **A/B Engine Testing**: Run same project on 2 engines, compare quality scores and cost | SHOULD | Already partially exists (parallel mode), enhance with comparison UI |
| FR-9.5 | **Backup/Restore**: Automated DB backup, project backup to GitHub, disaster recovery | MUST | Data safety |
| FR-9.6 | **Health Monitor**: Periodic self-health check (disk, CPU, DB, engines) with alerts | MUST | Prevents silent failures |

### Deferred to v3.0
- Plugin/extension system
- Voice command shortcuts
- Grafana/Prometheus integration
- Multi-user collaboration (beyond current whitelist)

### Template Library Structure
```
templates/
├── react-fastapi/
│   ├── template.yaml       # metadata, variables, description
│   ├── raw-input.md        # pre-filled requirements
│   └── overrides.yaml      # engine/tier/setting overrides
├── telegram-bot/
├── cli-tool/
├── rest-api/
├── landing-page/
└── discord-bot/
```

### Acceptance Criteria
- [ ] `factory new --template telegram-bot` creates project with pre-filled requirements
- [ ] GitHub webhook triggers redeploy on push to main
- [ ] Weekly cost report sent via Telegram
- [ ] Backup runs daily, user can restore from Telegram

---

## Factory Pipeline State Machine (Phases 0-7)

### Overview
The `FactoryOrchestrator` implements the following phases as a deterministic state machine. Each phase has defined inputs, outputs, gate criteria, and failure policies.

### Phase Definitions

| Phase | Name | Inputs | Outputs | Gate Threshold | On Fail |
|-------|------|--------|---------|---------------|---------|
| 0 | Complexity Assessment | raw-input.md | tier selection, model assignments | N/A (auto) | N/A |
| 1 | Requirements Analysis | raw-input.md, tier | spec.md | >= 97/100 | Iterate (max 3x), then escalate to user |
| 2 | Multi-Model Brainstorm | spec.md | brainstorm.md | N/A (advisory) | N/A |
| 3 | Architecture Design | spec.md, brainstorm.md | design.md, interfaces.md | >= 97/100 | Iterate (max 3x), then escalate |
| 4 | Implementation + Testing | spec.md, design.md, interfaces.md | code/backend/, tests/ | N/A (tested in Phase 6) | N/A |
| 5 | Cross-Provider Review | all code | reviews/*.md | N/A (issues logged) | N/A |
| 6 | Test Execution + Fix | code + tests + reviews | passing tests, fixed code | 100% tests pass | Fix cycle (max 5x), escalate after 3 same-issue failures |
| 7 | Docs + Release | all artifacts | README, CHANGELOG, DEPLOYMENT, deploy.sh | >= 97/100 | Iterate (max 3x), then escalate |

### Quality Gate Scoring Rubric
Each quality gate scores 0-100 across 4 dimensions (25 points each):
- **Completeness** (0-25): All required sections present, all entities covered
- **Clarity** (0-25): Unambiguous, implementable by a developer without further questions
- **Consistency** (0-25): No contradictions, terminology uniform, dependencies valid
- **Robustness** (0-25): Edge cases covered, error handling defined, failure modes addressed

### Gate Failure State Machine
```
PENDING -> SCORING -> PASS (score >= 97) -> NEXT_PHASE
                   -> FAIL_SOFT (90-96) -> ITERATE_ONCE -> RESCORING -> PASS/FAIL_HARD
                   -> FAIL_HARD (<90) -> ITERATE (max 3) -> RESCORING -> PASS/ESCALATE
                                                         -> ESCALATE -> USER_DECISION
```

### Information Barrier Rules
- **Barrier 1 (Implementation ↔ Testing)**: The test-writing model receives ONLY spec.md + interfaces.md. It NEVER receives implementation code. The implementation model NEVER receives test code.
- **Barrier 2 (Write ↔ Review)**: Code reviewer models are from a DIFFERENT AI provider than the implementation model.
- **Enforcement**: The orchestrator passes only permitted file paths to each agent. File access is controlled at the Python service level, not by trust.

### Cross-Provider Verification
- Phase 4: Implementation by Provider A, Testing by Provider B
- Phase 5: Review by Provider C (and optionally Provider D)
- Minimum 3 distinct AI providers used across phases 4-5
- Provider assignments logged to audit trail for reproducibility

### State Persistence
```sql
CREATE TABLE factory_orchestration_state (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES factory_runs(id) UNIQUE,
    current_phase INT DEFAULT 0,
    phase_status VARCHAR(20) DEFAULT 'pending',  -- pending, running, scoring, passed, failed, escalated
    retry_count INT DEFAULT 0,
    quality_scores JSONB DEFAULT '{}',  -- {"phase_1": {"score": 98, "breakdown": {...}}, ...}
    model_assignments JSONB,  -- {"orchestrator": "claude-opus-4.6", "implementer": "claude-sonnet-4.6", ...}
    barrier_manifest JSONB,  -- {"tester_allowed_files": [...], "implementer_blocked_files": [...]}
    last_gate_feedback TEXT,
    escalation_reason TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## Provider Adapter Interface Specification

### Abstract Interface
Every provider adapter MUST implement this interface:

```python
class ProviderAdapter(Protocol):
    name: str  # e.g., "groq"
    display_name: str  # e.g., "Groq"
    is_free: bool

    async def list_models(self) -> list[ModelInfo]:
        """Return available models with metadata."""

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],  # OpenAI-compatible format: [{"role": "user", "content": "..."}]
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,  # OpenAI function-calling format
        timeout: float = 120.0,
    ) -> CompletionResponse:
        """Send chat completion request. Returns unified response."""

    async def check_health(self) -> HealthStatus:
        """Ping provider. Returns status + latency."""

    async def get_rate_limits(self) -> RateLimitInfo:
        """Return current rate limit status."""
```

### Response Schema
```python
@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    tokens_input: int
    tokens_output: int
    cost: float  # 0.0 for free
    latency_ms: int
    finish_reason: str  # "stop", "length", "tool_calls"
    tool_calls: list[dict] | None = None
    raw_response: dict | None = None  # provider-specific, for debugging

@dataclass
class ModelInfo:
    name: str
    display_name: str
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    is_free: bool
    cost_per_1k_input: float
    cost_per_1k_output: float

@dataclass
class HealthStatus:
    is_healthy: bool
    latency_ms: int
    error: str | None = None
    last_checked: datetime

@dataclass
class RateLimitInfo:
    rpm_limit: int
    rpd_limit: int
    rpm_remaining: int
    rpd_remaining: int
    reset_at: datetime | None = None
```

### Error Taxonomy
| Error Type | HTTP Code | Action |
|-----------|-----------|--------|
| RateLimited | 429 | Exponential backoff (1s, 2s, 4s, 8s), then failover |
| AuthError | 401/403 | Mark provider disabled, log warning, skip |
| ServerError | 500-503 | Retry 3x with 2s delay, then mark unhealthy for 60s |
| Timeout | - | After 120s, cancel, failover |
| ContextTooLong | 400 (context) | Skip model, try next with larger context |
| ContentFilter | 400 (filter) | Log, retry with different phrasing, then failover |
| NetworkError | - | Retry 3x with 1s delay, then mark unhealthy |

### Non-OpenAI Provider Mapping
| Provider | API Style | Mapping Approach |
|----------|-----------|-----------------|
| Google AI Studio | Google SDK / REST | Adapter translates OpenAI messages format ↔ Google GenerateContent format. Handles `systemInstruction` field. Streaming via SSE. |
| SambaNova | REST (custom) | Adapter maps to OpenAI-like request body. Response parsed to CompletionResponse. |
| HuggingFace | Inference API | Adapter uses `text-generation` task format. Maps messages to prompt string. |
| Cloudflare Workers AI | Workers API | Adapter uses `@cf/` model prefix. Maps to Workers AI request format. |
| All others (Groq, NVIDIA, Together, Cerebras, Fireworks, Mistral, OpenRouter, DeepSeek) | OpenAI-compatible | Direct mapping. Only `base_url` and `api_key` differ. |

### Timeout Defaults
- Health check: 5s
- Chat completion (non-streaming): 120s
- Chat completion (streaming, first token): 30s
- Model listing: 10s
- Rate limit query: 5s

### Required Telemetry Fields (logged per call)
- provider, model, role, run_id, phase
- tokens_input, tokens_output, cost, is_free
- latency_ms, success (bool), error_type (if failed)
- timestamp

---

## REQ-5 Security, Rollback, and Provenance

### Install Script Security Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.18 | Script verifies SHA256 checksum of downloaded components against pinned hashes | MUST |
| FR-5.19 | API keys entered interactively are NEVER written to shell history (use `read -s`) | MUST |
| FR-5.20 | Script output NEVER contains API key values (masked in logs) | MUST |
| FR-5.21 | .env file created with 600 permissions (owner read/write only) | MUST |
| FR-5.22 | All installed packages use pinned versions (no `latest` tags) | MUST |
| FR-5.23 | On partial failure: script logs what was installed, what failed, and provides manual fix commands | MUST |
| FR-5.24 | `factory uninstall` removes all components cleanly | SHOULD |
| FR-5.25 | `--unattended` mode reads keys from env vars: `FACTORY_TELEGRAM_BOT_TOKEN`, `FACTORY_GROQ_API_KEY`, etc. | MUST |
| FR-5.26 | Precedence: CLI flags > env vars > interactive input > skip | MUST |

### Rollback Behavior
- Each install step is wrapped in a checkpoint
- On failure at step N: steps 1..N-1 remain (idempotent, already installed)
- User gets a clear message: "Installation failed at step N: <reason>. Steps 1-{N-1} completed. Run `install.sh --resume` to retry from step N."
- No automatic rollback of completed steps (destructive rollbacks are risky on production servers)

---

## REQ-7 Revised: Docker Strategy Decision

### Overview
Concrete decision on containerization strategy based on evaluated constraints.

### Decision Criteria Matrix
| Criterion | Weight | Docker (Fat Container) | Hybrid (Host + Docker DB) | Full Host (systemd) |
|-----------|--------|----------------------|--------------------------|-------------------|
| tmux access | 25% | Fragile (host PID ns) | Native | Native |
| clink/CLI access | 20% | Requires all CLIs in image | Native | Native |
| Docker socket | 15% | Mount required (security risk) | Native | Native |
| Deploy simplicity | 15% | Single `docker-compose up` | 2 steps (compose + systemd) | Complex manual setup |
| Image size | 10% | ~5GB+ (all CLIs) | ~500MB (DB only) | N/A |
| Update story | 10% | Rebuild image | git pull + pip install | git pull + pip install |
| Debugging | 5% | Harder (exec into container) | Native | Native |

### Required Experiments (during Phase 4)
| Experiment | Pass Criteria |
|-----------|---------------|
| tmux create/attach from Docker | Session persists across container restart |
| clink call from Docker | p95 latency < 5s, no auth failures |
| Docker socket mount | Can list/start/stop sibling containers |
| Fat container build | Image builds < 10 min, size < 8GB |

### Decision: Hybrid Architecture [MUST IMPLEMENT]
Based on the constraints analysis, the implementation MUST use the **Hybrid** approach:
- **Bot + Factory Orchestrator**: Runs on host via systemd (native tmux, native CLIs, native filesystem)
- **PostgreSQL**: Runs in Docker with persistent volume
- **Project deployments**: Run in Docker (each project gets its own container via docker-compose)
- **Rationale**: Native host access for tmux and CLIs is essential; Docker for DB and projects provides isolation

### Functional Requirements (Revised)
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | Bot runs as systemd service on host with auto-restart | MUST |
| FR-7.2 | PostgreSQL runs in Docker with named volume for data persistence | MUST |
| FR-7.3 | Project deployments use Docker (per-project docker-compose.yml) | MUST |
| FR-7.4 | Bot accesses Docker socket natively for container management | MUST |
| FR-7.5 | All CLIs (claude, gemini, opencode, aider) installed on host | MUST |
| FR-7.6 | `DOCKER_STRATEGY.md` documents architecture and trade-offs | MUST |
| FR-7.7 | Install script implements hybrid setup (systemd + Docker compose for DB) | MUST |

### Acceptance Criteria
- [ ] Bot starts via `systemctl start factory-bot` and survives reboot
- [ ] PostgreSQL runs in Docker and persists data across restart
- [ ] tmux sessions work natively (no Docker abstraction layer)
- [ ] clink calls work without latency penalty
- [ ] Project containers can be managed from the bot

---

## REQ-9.5 Expanded: Backup and Restore

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-9.5.1 | Automated daily backup of PostgreSQL database (pg_dump) | MUST |
| FR-9.5.2 | Backup project artifacts directories (tar.gz per project) | MUST |
| FR-9.5.3 | Backup .env and config files (encrypted with backup passphrase) | MUST |
| FR-9.5.4 | Store backups locally at /home/factory/backups/ with date-stamped names | MUST |
| FR-9.5.5 | Retention policy: keep last 7 daily, 4 weekly, 3 monthly backups | MUST |
| FR-9.5.6 | Optional push to remote storage (GitHub repo, S3-compatible, rsync to remote) | SHOULD |
| FR-9.5.7 | `/backup` Telegram command for on-demand backup | MUST |
| FR-9.5.8 | `/restore` Telegram command to list available backups and restore selected | MUST |
| FR-9.5.9 | Restore verifies integrity (SHA256 checksum) before applying | MUST |
| FR-9.5.10 | Restore creates a pre-restore snapshot (safety backup before overwriting) | MUST |
| FR-9.5.11 | `factory backup` and `factory restore` CLI equivalents | MUST |
| FR-9.5.12 | Backup status in health dashboard (last backup time, size, success) | MUST |

### Data Model Changes
```sql
CREATE TABLE backups (
    id SERIAL PRIMARY KEY,
    backup_type VARCHAR(20),  -- 'daily', 'weekly', 'monthly', 'manual'
    file_path TEXT,
    file_size_bytes BIGINT,
    sha256_checksum VARCHAR(64),
    includes_db BOOLEAN DEFAULT TRUE,
    includes_projects BOOLEAN DEFAULT TRUE,
    includes_config BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    retention_until DATE,
    status VARCHAR(20) DEFAULT 'completed'  -- 'running', 'completed', 'failed'
);
```

### Edge Cases
- Backup fails (disk full): alert user, suggest cleanup, show disk usage
- Restore from corrupted backup: checksum mismatch detected, refuse to apply, show available alternatives
- Restore during active factory run: refuse with message "Stop all running jobs first"
- Config file contains sensitive keys: encrypt with AES-256 using user-provided passphrase (set during install)

### Acceptance Criteria
- [ ] Daily backup runs automatically and appears in /home/factory/backups/
- [ ] Restore from 3-day-old backup recovers DB + projects + config
- [ ] Backup integrity verified via SHA256
- [ ] Old backups auto-cleaned per retention policy

---

## REQ-9.6 Expanded: Health Monitor

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-9.6.1 | Periodic health check every 5 minutes (configurable) | MUST |
| FR-9.6.2 | Check: CPU usage (alert > 85%), RAM usage (alert > 85%), Disk usage (alert > 80%, critical > 90%) | MUST |
| FR-9.6.3 | Check: PostgreSQL connectivity and query latency | MUST |
| FR-9.6.4 | Check: Docker daemon status | MUST |
| FR-9.6.5 | Check: tmux availability | MUST |
| FR-9.6.6 | Check: Bot process health (memory usage, uptime, event loop lag) | MUST |
| FR-9.6.7 | Check: All configured provider API health (cached from last scan) | SHOULD |
| FR-9.6.8 | Check: Last backup age (alert if > 48 hours) | MUST |
| FR-9.6.9 | Alert via Telegram when any check fails | MUST |
| FR-9.6.10 | `/health` Telegram command for on-demand health report | MUST |
| FR-9.6.11 | `factory health` CLI equivalent | MUST |
| FR-9.6.12 | Mute/acknowledge alerts: user can mute an alert for N hours | SHOULD |
| FR-9.6.13 | Remediation suggestions per alert type (e.g., "Disk full: run `docker system prune`") | SHOULD |

### Health Report Format (Telegram)
```
🏥 System Health
━━━━━━━━━━━━━━━━

💻 CPU: 23% ✅
🧠 RAM: 61% ✅  (4.9/8.0 GB)
💾 Disk: 45% ✅  (18/40 GB)
⏱ Uptime: 12d 4h

🐘 PostgreSQL: ✅ (2ms latency)
🐳 Docker: ✅ (3 containers running)
📺 tmux: ✅ (2 sessions active)
🤖 Bot: ✅ (uptime: 12d, mem: 142MB)

📦 Last backup: 6h ago ✅
🔑 Providers: 5/7 healthy ⚠️
  ❌ SambaNova: timeout
  ❌ Fireworks: 401 auth error

[🔄 Refresh] [🔇 Mute Alerts 1h]
```

### Alert Thresholds
| Metric | Warning | Critical | Action on Critical |
|--------|---------|----------|-------------------|
| CPU | > 85% for 5 min | > 95% for 2 min | Kill lowest-priority factory run |
| RAM | > 85% | > 95% | Alert user + suggest restart |
| Disk | > 80% | > 90% | Refuse new projects, alert user |
| DB latency | > 100ms | > 1000ms | Alert user |
| Backup age | > 48h | > 7d | Force backup on next quiet period |
| Provider down | 3 consecutive failures | N/A | Remove from active rotation, alert |

### Acceptance Criteria
- [ ] Health checks run every 5 minutes
- [ ] Telegram alert sent when disk exceeds 80%
- [ ] `/health` shows comprehensive status report
- [ ] Muting an alert suppresses notifications for specified duration

---

## REQ-8 Supplement: Self-Research Guardrails

### Citation Verification
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.13 | Every suggestion from web research MUST include source URL | MUST |
| FR-8.14 | Before including in report: verify source URL is accessible (HTTP 200) | MUST |
| FR-8.15 | Discard suggestions where source URL returns 404 or content doesn't match claim | MUST |
| FR-8.16 | Pin source URLs with archive.org snapshot link where possible | SHOULD |

### Safe Change Scope
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.17 | Self-research may ONLY modify: config files, model assignments, provider settings, engine version pins, prompt templates | MUST |
| FR-8.18 | Self-research may NOT modify: authentication logic, database schema, core orchestrator logic, security middleware | MUST |
| FR-8.19 | All changes MUST pass existing test suite before PR creation | MUST |
| FR-8.20 | PR description MUST list all changed files with explanation | MUST |
| FR-8.21 | PR is labeled `self-research` and `auto-generated` for easy filtering | MUST |
| FR-8.22 | Maximum 10 file changes per self-research PR (split into multiple PRs if more) | MUST |

---

## Concurrency and Locking Specification

### Locking Strategy
- Use **PostgreSQL advisory locks** keyed by `run_id` for factory run state transitions
- Lock acquisition: `SELECT pg_try_advisory_lock(hashtext(run_id::text))` — non-blocking
- If lock not acquired: return "Run is being modified by another process" to CLI/Telegram

### Transaction Boundaries
- Phase transitions: single transaction (update orchestration_state + factory_run status + create factory_events)
- Provider fallback: no transaction (each API call is independent)
- Backup operations: exclusive advisory lock on backup table

### CLI ↔ Bot Coordination
- CLI connects directly to DB when bot is running (shared connection pool via unix socket)
- CLI detects bot status via PID file (/var/run/factory-bot.pid)
- If bot is down: CLI operates standalone with own DB connection
- State changes by CLI emit PostgreSQL NOTIFY on `factory_events` channel; bot listens via LISTEN

### Deadlock Prevention
- Advisory locks have 10s timeout (not indefinite)
- Lock acquisition order: always lock by run_id in sorted order when multiple runs involved
- No nested advisory locks

---

## Telegram UI Measurable Constraints

### Message Editing Limits
| Constraint | Limit | Handling |
|-----------|-------|---------|
| Edit frequency | Max 1 edit per 3 seconds per message (Telegram API limit) | Buffer updates, batch into single edit |
| Message age for editing | 48 hours | After 48h, send new message instead of editing |
| Message size | 4096 characters (Telegram limit) | Truncate with "..." and [View Full] button |
| Inline keyboard buttons | Max 8 per row, 100 total | Paginate if needed |
| Rate limit (global) | 30 messages/sec to same chat | Queue with backpressure |

### Fallback Behavior
- Edit fails (message too old): send new message, delete old if possible
- Edit fails (message deleted by user): send new message
- Rate limited by Telegram: exponential backoff (1s, 2s, 4s), queue pending updates

### Acceptance Criteria (Measurable)
- [ ] No message floods: active factory run produces at most 1 message per phase + 1 updating status message
- [ ] Status message updates no more frequently than every 3 seconds
- [ ] All messages fit within 4096 character limit
- [ ] Buttons are logically grouped, max 4 per row in normal views

---

## Cross-Cutting Concerns

### Security
- All API keys stored in .env, never in DB or git
- API keys masked in all Telegram messages (show first/last 4 chars)
- CLI authenticates via ~/.factory/config.yaml (600 permissions)
- Self-research changes on branch only, never direct to main
- Rate limit tracking prevents accidental paid API usage

### Performance
- Async everywhere (asyncio, SQLAlchemy async, aiohttp)
- Connection pooling for DB and HTTP clients
- Provider health cache (1 min TTL) to avoid redundant health checks
- Model scan results cached (1 hour TTL)

### Observability
- Structured logging (structlog) for all components
- Audit log maintained per factory run
- API usage logged per call (provider, model, tokens, cost, latency)
- Health monitor sends alerts for anomalies

### Testing Strategy
- Unit tests: provider adapters, scanner, grading, CLI parsing
- Integration tests: full factory run lifecycle, provider fallback chains
- E2E tests: Telegram command flow (mocked bot), CLI flow
- Black-box tests: against spec interfaces (information barrier)
- Target: 80%+ coverage on new code

---

## Dependency Graph

```
REQ-1 (Unified Architecture)
  ├── REQ-2 (Free Providers) — needs provider abstraction
  │     └── REQ-3 (Scanner) — needs provider list
  ├── REQ-4 (clink) — needs routing abstraction
  ├── REQ-5 (Install Script) — needs full project defined
  ├── REQ-6 (UI) — needs message templates
  ├── REQ-8 (Self-Research) — needs orchestrator + providers
  └── REQ-9 (Extras) — needs all above

REQ-7 (Docker Eval) — independent, informs REQ-5
```

## Implementation Notes (from Quality Gate Review)

### 1. Config Consistency (.env + config.yaml)
The install script MUST generate BOTH `.env` (for systemd bot) and `~/.factory/config.yaml` (for CLI) from the same API key input. If either file is updated, a `factory config sync` command MUST synchronize them. The CLI MUST fall back to reading `.env` if `config.yaml` is missing.

### 2. Backup Schema Versioning
Add `schema_version VARCHAR(20)` column to `backups` table. On backup: record current Alembic migration head. On restore: compare backup schema version to current. If mismatch: warn user and offer "restore + migrate" or "cancel". Never silently restore an incompatible schema.

### 3. GitHub Webhook Security
REQ-9.2 webhook endpoint MUST verify `X-Hub-Signature-256` header using a per-project `webhook_secret` stored in `projects.config_json`. Unsigned requests MUST be rejected with 403. The install script MUST generate webhook secrets during project setup.

---

## Summary Statistics
- **Total functional requirements**: 87
- **MUST requirements**: 68
- **SHOULD requirements**: 19
- **New DB tables**: 6
- **New services**: ~8 (ProviderRegistry, ModelScanner, ClinkRouter, SelfResearcher, TemplateManager, HealthMonitor, CostAdvisor, Installer)
- **New CLI commands**: 10
- **New Telegram commands**: 5
