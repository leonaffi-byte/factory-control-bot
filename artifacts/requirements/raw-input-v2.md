# Factory Control Bot v2.0 — Requirements Update

## Context

v1.0.0 is complete — a Telegram bot that controls the Black Box Software Factory. The following 9 requirements define v2.0.

## Requirement 1: Unified Project (Factory + Bot as One)

Merge the factory-control-bot and the Black Box Software Factory into a single unified project. Currently they are separate — the bot is a remote control and the factory pipeline lives in CLAUDE.md config files. In v2.0:

- **One codebase**: The factory pipeline logic (phases, quality gates, model routing, information barriers, audit logging) should be implemented as Python services within the bot codebase, not just as prompt instructions in CLAUDE.md
- **Dual interface**: The same factory can be operated via:
  - **Telegram**: The existing bot interface (mobile-first)
  - **SSH/CLI**: A command-line interface for direct terminal use (e.g., `factory run`, `factory status`, `factory scan-models`)
- The factory still launches engines (claude, gemini, opencode, aider) in tmux, but the orchestration, monitoring, and control logic is unified
- CLAUDE.md/GEMINI.md/OPENCODE.md still exist as engine-specific instruction files, but the bot manages the full lifecycle

## Requirement 2: Free Model Provider Research & Integration

Replace reliance on OpenRouter (which has caused unexpected charges) with a comprehensive free model strategy:

- **Research and integrate all available free model API providers**:
  - NVIDIA NIM API (free tier)
  - Groq (free tier for inference)
  - Together AI (free tier)
  - Google AI Studio (free Gemini API)
  - Cerebras (free tier)
  - SambaNova (free tier)
  - Fireworks AI (free tier)
  - Any other providers with free tiers
- **OpenCode free models**: Inspect how OpenCode provides free models, integrate that mechanism directly
- **Provider abstraction layer**: Unified interface to call any provider. User configures which API keys they have
- **Cost tracking**: Clearly distinguish free vs paid calls. Alert if a "free" provider starts charging
- **Fallback chain**: If a free provider is down or rate-limited, try next free provider before falling back to paid
- **OpenRouter remains as option** but clearly marked as PAID, never used by default for "free" runs

## Requirement 3: Free Model Scanner Command

A bot command (and CLI equivalent) that:

1. **Scans all configured free providers** for currently available models
2. **Tests connectivity and rate limits** for each provider in real-time
3. **Grades each free option** on:
   - Model quality (benchmark scores, known capabilities)
   - Current availability (is it up right now?)
   - Rate limits (requests/min, tokens/day)
   - Context window size
   - Speed (inference latency)
4. **Suggests the best free model for each factory role** (orchestrator, implementer, tester, reviewer, etc.)
5. **Shows a perspective summary**: "How good can a fully-free factory run be right now?" with overall grade
6. **One-click accept**: User taps a button and the suggested free configuration is applied to settings
7. Should be runnable on-demand: `/scan-models` or `factory scan-models`

## Requirement 4: clink Toggle in Settings

Add a settings option to choose the routing method for external model calls:

- **OpenRouter API** (current default) — routes through OpenRouter
- **Direct API** — calls provider APIs directly (Google AI for Gemini, OpenAI for GPT, etc.)
- **clink (Local CLI)** — uses zen MCP's `clink` tool to route to locally installed CLIs:
  - Claude CLI (local)
  - Gemini CLI (local)
  - Codex CLI (local)
- User can set this globally or per-role
- When clink is selected, the factory uses `mcp__zen__clink` instead of `mcp__zen__chat` for those roles
- Show which CLIs are installed and available

## Requirement 5: One-Line Install Script

Create a comprehensive installer that works on a fresh Ubuntu VPS:

- **Single command**: `curl -fsSL https://raw.githubusercontent.com/<repo>/install.sh | bash`
- **Installs everything**:
  - System dependencies (Python 3.11+, Node.js, Docker, docker-compose, tmux, git, nginx, certbot)
  - The bot/factory project itself
  - Claude Code CLI
  - Gemini CLI
  - OpenCode
  - Aider
  - PostgreSQL (in Docker)
  - All Python dependencies in venv
  - MCP servers (zen, perplexity, context7, github, memory)
  - Systemd service files
- **Interactive API key setup**: After install, walks through each API key one by one:
  - Shows which key, what it's for, whether it's required or optional
  - Option to skip (press Enter)
  - Saves to .env file
  - Tests each key after entry (verify it works)
- **One-line deploy for projects**: After a factory run completes, `factory deploy <project-name>` handles everything
- **Update script**: `factory update` pulls latest, updates all engines, migrates DB

## Requirement 6: Slick Modern Telegram UI

Make the bot look professional and modern:

- **Rich formatting**: Use Telegram's HTML/Markdown formatting extensively
- **Status indicators**: Animated/updating progress for factory runs
- **Card-style layouts**: Project cards with emoji icons, status badges, key metrics
- **Inline keyboards**: Well-organized, logical button layouts with clear icons
- **Progress bars**: Visual progress for factory phases (e.g., ▓▓▓▓░░░░ 4/7)
- **Color coding**: Use emoji for status colors (🟢 running, 🔴 failed, 🟡 paused, ⚪ pending)
- **Minimal clutter**: Don't spam messages. Use edit-in-place for updates
- **Welcome screen**: Polished onboarding for first-time users
- **Dark-mode friendly**: Ensure formatting looks good in both light and dark Telegram themes
- **Consistent design language**: Every screen should feel like it belongs to the same app

## Requirement 7: Docker Evaluation

Evaluate whether running the bot in Docker preserves all required functionality:

- Can Docker containers access tmux sessions on the host?
- Can Docker containers use Docker socket (Docker-in-Docker or socket mounting)?
- Can clink access local CLIs from inside Docker?
- Can the bot monitor factory runs in tmux from inside a container?
- **Recommendation**: If Docker limits functionality, recommend hybrid approach (bot on host, DB in Docker) or full host deployment with systemd
- Document the trade-offs clearly

## Requirement 8: Self-Research Function

An autonomous self-improvement capability:

- **On-demand**: `/self-research` or `factory self-research`
- **Scheduled**: Set via settings (e.g., every Sunday at 2 AM)
- **What it researches**:
  - Are current prompts/system instructions optimal? Check for better prompting techniques
  - Are the model assignments per role still the best choices? (new models released, benchmarks changed)
  - Are there new MCP servers or tools that could improve the factory?
  - Are there new free model providers or tier changes?
  - Are there improvements to the factory pipeline itself? (new phases, better quality gates, etc.)
  - Check for updates to all installed engines (Claude, Gemini, OpenCode, Aider)
- **Output**:
  - Short report sent via Telegram
  - Detailed report saved to artifacts/reports/self-research-<date>.md
  - Each suggestion has: what to change, why, expected impact, risk level
- **One-click accept**: For each suggestion, user can:
  - ✅ Accept → bot automatically updates code/config, commits, pushes to GitHub
  - ❌ Reject → skip
  - 📋 Details → show full analysis
- **Safety**: Changes are made on a branch, PR is created, user can review before merging to main

## Requirement 9: Brainstorm Additional Improvements

Think creatively about what else could make this the ultimate AI software factory:

- Template library for common project types
- Webhook support for GitHub (auto-trigger deploys on push)
- Multi-user collaboration features
- Cost optimization advisor
- A/B testing between engines
- Plugin/extension system
- Voice command shortcuts ("Hey Factory, start a new project")
- Integration with monitoring tools (Grafana, Prometheus)
- Backup and disaster recovery automation
- Any other innovations that would make this exceptional
