# Factory Control Bot — Requirements Specification

## Overview

A Telegram bot that serves as the complete control interface for the Black Box Software Factory v2. It replaces SSH-based workflows with a mobile-first experience: create projects via voice or text, choose AI engines, monitor factory progress in real-time, manage deployments, and control the entire VPS infrastructure — all from Telegram.

## 1. Users and Access

- **Access model**: Whitelist of Telegram user IDs (stored in config/DB)
- **Users**: 1-3 trusted users (the owner + 1-2 others)
- **Shared resources**: All users share the same API keys, VPS, and project list
- **User tracking**: Log which user started each project/action for audit purposes
- **Admin role**: The primary user (owner) can add/remove whitelisted users via the bot

## 2. Voice Input System

### 2.1 Transcription

- **Auto-select provider**: Try Groq (Whisper) first for speed. If transcription confidence is low or Groq is unavailable, fall back to OpenAI Whisper.
- **Supported languages**: Hebrew (primary), English, Russian — auto-detect language
- **Flow for each voice message**:
  1. User sends voice message
  2. Bot transcribes it (show "Transcribing..." status)
  3. Bot displays the transcription text
  4. Bot shows 3 inline buttons: **✅ Done** | **✏️ Edit** | **🗑️ Delete Last**
- **Delete Last**: Removes the last transcription segment. Bot confirms deletion.
- **Edit**: Bot sends the transcript as a message. User replies with the corrected text. Bot replaces the segment and re-displays with the 3 buttons.
- **Done**: Signals end of voice input for the current stage. Bot concatenates all accepted segments.
- **Multiple messages**: User can send as many voice messages as needed before pressing Done. Each goes through the same transcribe → review → accept cycle.
- **Text input**: User can also type messages instead of voice. Same flow applies (show text, 3 buttons).

### 2.2 Translation and Requirements Generation

- After "Done" is pressed:
  1. Translate all accepted segments to English (if not already English)
  2. Use an AI model (configurable in settings) to transform the raw text into structured requirements
  3. Display the generated requirements to the user for review
  4. Buttons: **✅ Approve** | **✏️ Edit** | **🔄 Regenerate**

## 3. Project Creation Flow

### 3.1 Engine Selection

When user initiates a new project (/new or "New Project" button):

1. **Select engines** (multi-select inline keyboard):
   - ☐ Claude (Opus 4.6 orchestrator)
   - ☐ Gemini (Gemini 3 Pro orchestrator)
   - ☐ OpenCode (free models via OpenRouter)
   - ☐ Aider (open-source, bring your own key)
   - Button: **✅ Confirm Selection**

2. **Parallel mode**: If 2+ engines selected, each engine creates its own independent factory run of the same project. This allows side-by-side comparison of results.
   - Each engine gets its own tmux session, git branch prefix, and audit log
   - Project folders: `project-name-claude/`, `project-name-gemini/`, `project-name-opencode/`, etc.
   - All are pushed to the same GitHub repo on separate branches: `claude/dev`, `gemini/dev`, `opencode/dev`, etc.

3. **Project name**: Bot asks for name. User types or voice-inputs it. Bot validates (lowercase, hyphens, no spaces, no duplicates).

4. **Project description**: Bot asks for description. User can type or voice. Voice goes through the transcription flow (Section 2).

### 3.2 Requirements Input

After name + description:

1. Bot says: "Now describe your requirements in detail. Send voice or text messages. Press Done when finished."
2. Voice/text input cycle (Section 2.1)
3. Translation + AI structuring (Section 2.2)
4. User approves final requirements

### 3.3 Settings Override

After requirements are approved:

1. Bot asks: **"Start with default settings or customize?"**
   - **🚀 Start with defaults** → proceed to deployment config
   - **⚙️ Customize** → show settings menu (Section 5)
   - Changes made here apply ONLY to this project

### 3.4 Deployment Configuration

1. Bot asks: **"Auto-deploy when finished?"**
   - **Yes** → Bot asks: "What type of project?"
     - 🤖 Telegram Bot
     - 🌐 Web App / Website
     - 🔌 API Service
     - 📦 Other (no auto-deploy template, manual)
   - **No** → Skip, factory just produces code + docs

2. If Yes, bot asks: **"Deploy where?"**
   - 🖥️ This VPS (Docker)
   - ☁️ Other (provide SSH details later)

3. If "This VPS":
   - After factory completes and pushes to GitHub, bot automatically:
     - Generates Dockerfile + docker-compose.yml (if factory didn't already)
     - Builds and starts the container
     - Sets up `restart: unless-stopped`
     - If API keys are needed, asks for them one by one via Telegram
     - Reports deployment status + health check

4. Domain/SSL handling (for web apps):
   - Bot asks: **"How should this be accessible?"**
     - 🏠 Localhost only (port forwarded)
     - 🌍 Public with domain — Bot asks for subdomain. Checks if user has a domain configured. If not, offers:
       - "You don't have a domain set up. Options:"
       - Buy a domain (bot can guide through Namecheap/Cloudflare API if configured)
       - Use a free subdomain service (e.g., nip.io, sslip.io for testing)
       - Set up later manually
     - If domain exists: auto-configure nginx reverse proxy + SSL via certbot

## 4. Factory Monitoring

### 4.1 Real-Time Mode

When user is actively watching (viewing the project status):

- Bot streams factory output in near-real-time, similar to watching an SSH terminal
- Implementation: Poll tmux capture-pane or tail the factory-run.log every 2-5 seconds
- Send updates as edited messages (to avoid spam) or as a "live feed" message that updates in place
- Show: current phase, what the agent is doing, which model is being called
- Include a **⏸️ Pause Updates** button to stop the stream

### 4.2 Push Notifications

When user is NOT actively watching, send notifications for:

- ✅ Phase N completed (brief summary, quality gate score)
- ❌ Error that needs attention (with error details + quick-action buttons)
- 🏁 Factory finished — full summary:
  - Project name, engine used
  - Duration
  - Quality gate scores per phase
  - Total estimated cost
  - Test results (passed/failed/skipped)
  - GitHub link
  - If auto-deploy was on: deployment status

### 4.3 Clarification Questions (Phase 1)

During requirements analysis, the factory may ask clarifying questions:

- Bot receives the question from the factory (via log parsing or a dedicated communication channel)
- Formats it as a Telegram message with **multiple choice inline buttons** where possible
- Ensure buttons have enough room for text (use short labels + descriptions below)
- For open-ended questions: let user type or voice-reply
- Forward the answer back to the factory process
- Maximum 6 clarification rounds (as defined in CLAUDE.md/GEMINI.md)

## 5. Settings

### 5.1 Global Settings (affect all new projects by default)

Accessible via /settings or ⚙️ Settings button:

- **Default engine**: Claude / Gemini / OpenCode / Aider
- **Voice provider**: Groq (default) / OpenAI / Auto-select
- **Translation model**: Model used to translate voice to English
- **Requirements model**: Model used to structure requirements from raw text
- **Notification preferences**: Which events trigger push notifications
- **Default quality gate threshold**: 97% (adjustable)
- **Default max retries**: 3 per quality gate, 5 per fix cycle
- **Cost alert threshold**: Alert if project exceeds $X
- **Domain configuration**: Registered domain, SSL email, etc.

### 5.2 Per-Project Settings Override

When customizing before a factory run:

- **Complexity tier**: Auto-detect / Force Tier 1 / Tier 2 / Tier 3
- **Model assignments per role**: For each of the 12 agent roles, choose which model to use
  - Show current defaults based on tier
  - Allow overriding any role's model
  - List available models (from zen MCP + native)
- **Quality gate threshold**: Override global default
- **Max retries**: Override global default
- **Cost limit**: Hard stop if cost exceeds this amount
- **Auto-deploy**: Yes/No + deploy target

## 6. Project Management

### 6.1 Project List

/projects or 📁 Projects button:

- Show all projects with:
  - Name
  - Engine(s) used
  - Status (running / completed / failed / deployed)
  - Last activity date
  - Cost so far
- Tap a project for detail view

### 6.2 Project Detail View

- Full status: current phase, git branch, latest commit
- Audit log summary
- Cost breakdown by provider
- Quick actions:
  - 📋 View logs (last 50 lines)
  - 🔄 Resume (if paused/failed)
  - ⏹️ Stop factory
  - 🚀 Deploy / Redeploy
  - ➕ Add feature (new requirements round → factory runs feature pipeline)
  - 🗑️ Delete project (with confirmation)

### 6.3 Update Existing Projects

Select a completed project → "Add Feature / Update":

1. Voice/text input cycle for new requirements
2. Bot appends to existing requirements or creates a feature spec
3. Lets user choose engine
4. Factory runs the /feature pipeline (not full /factory) on the existing codebase
5. Commits, reviews, tests, deploys update

## 7. VPS Management

### 7.1 Docker Control

/docker or 🐳 Docker button:

- **List containers**: Show all running/stopped containers with status, uptime, ports, CPU/memory
- **Per container actions**:
  - ▶️ Start
  - ⏹️ Stop
  - 🔄 Restart
  - 📋 Logs (last 50 lines)
  - 🗑️ Remove (with confirmation)
- **Docker compose operations**: Up / Down / Rebuild for project directories

### 7.2 System Services

/system or 🖥️ System button:

- **System health**: CPU, RAM, disk usage, uptime
- **Service status**: Tailscale, fail2ban, nginx, PostgreSQL, the bot itself
- **Quick actions**:
  - Restart a service
  - View service logs
  - Check for system updates

### 7.3 Multi-Node (Future-Ready)

- Architecture should support adding more VPS nodes later
- Node concept: each VPS has a name, Tailscale IP, and capabilities
- For now: single node, but DB schema and bot commands should accommodate multiple
- Future: /nodes command to list, add, remove VPS nodes
- Future: project creation can target a specific node

## 8. Analytics Dashboard

/analytics or 📊 Analytics button:

- **Per project**: Cost breakdown (by provider, by phase), duration, quality scores, test pass rate
- **Aggregate**: Total spend this month, projects completed, average cost per tier, success rate
- **Trends**: Cost over time, projects per week/month
- **Engine comparison**: When same project was built by multiple engines, show side-by-side: cost, duration, quality scores, test coverage
- Format: Send as formatted messages with inline data. For complex charts, generate an image and send it.

## 9. Third-Party Engines

### 9.1 OpenCode Integration

- Install: `npm install -g opencode-ai` or `curl -fsSL https://opencode.ai/install | bash`
- Configuration: Uses free models from OpenRouter by default
- Free model routing: Use OpenRouter free models (Qwen3 Coder 480B, DeepSeek R1, Llama 3.3 70B, etc.)
- Rate limits: ~20 req/min, ~200 req/day on free tier (bot should track and warn when approaching limits)
- Create OPENCODE.md orchestrator instructions (similar to CLAUDE.md and GEMINI.md)
- MCP support: OpenCode supports MCP — configure same servers (zen, perplexity, context7, github, memory)
- Factory start: Run in tmux like the other engines
- Cost: $0 (completely free)

### 9.2 Aider Integration

- Install: `pip install aider-chat`
- Configuration: Can use any model via API key (OpenRouter, OpenAI, Anthropic, etc.)
- Can also use free OpenRouter models
- Create AIDER instructions file equivalent
- Factory start: `aider --model <model> --api-key openrouter=<key>` in tmux
- Lower automation capability than Claude/Gemini/OpenCode — may need more structured prompting

### 9.3 Engine Management

- Bot should be able to install/update engines via Telegram:
  - /update-engines → updates Claude Code, Gemini CLI, OpenCode, Aider to latest versions
  - /engine-status → shows installed versions and health

## 10. Communication Between Bot and Factory

### 10.1 Factory → Bot (output)

- **Log tailing**: Bot continuously reads factory-run.log for status updates
- **Structured markers**: Factory writes special markers to the log that the bot parses:
  - `[FACTORY:PHASE:N:START]` — phase N started
  - `[FACTORY:PHASE:N:END:score]` — phase N completed with quality gate score
  - `[FACTORY:CLARIFY:question_json]` — clarification question for user
  - `[FACTORY:ERROR:message]` — error that needs user attention
  - `[FACTORY:COST:amount:provider]` — cost update
  - `[FACTORY:COMPLETE:summary_json]` — factory finished
- These markers should be added to CLAUDE.md, GEMINI.md, OPENCODE.md so all engines emit them

### 10.2 Bot → Factory (input)

- **Clarification answers**: Bot writes answers to a file the factory watches:
  - `artifacts/reports/clarification-answers.json`
  - Factory polls this file during Phase 1
- **Stop/pause signals**: Touch files like `.factory-stop` or `.factory-pause` that the factory checks between phases

## 11. Technical Architecture

### 11.1 Stack

- Let the factory decide the optimal stack, but suggest:
  - Python 3.11+ with python-telegram-bot (async)
  - PostgreSQL in Docker for persistence
  - asyncio for concurrent factory monitoring
  - Docker for the bot itself (self-contained)

### 11.2 Database Schema (conceptual)

- **users**: telegram_id, name, role (admin/user), created_at
- **projects**: id, name, description, status, engine(s), tier, created_by, created_at, settings_json
- **factory_runs**: id, project_id, engine, status, phase, started_at, finished_at, cost_total, audit_log_path
- **factory_events**: id, run_id, event_type, phase, data_json, timestamp
- **deployments**: id, project_id, type, status, container_id, port, domain, created_at
- **nodes**: id, name, tailscale_ip, status, capabilities_json (future multi-node)
- **analytics**: id, project_id, run_id, metric_name, metric_value, timestamp

### 11.3 Deployment

- The bot itself runs in Docker on the VPS with `restart: unless-stopped`
- Bot needs access to: Docker socket, tmux sessions, filesystem (/home/factory/), system commands
- Environment variables: TELEGRAM_BOT_TOKEN, DATABASE_URL, all factory API keys (from .factory-env)
- Systemd service as backup to Docker (if Docker itself goes down)

## 12. Main Menu / Navigation

When user sends /start or /menu:

```
🏭 Black Box Factory v2

➕ New Project
📁 Projects
📊 Analytics
🐳 Docker
🖥️ System
⚙️ Settings
❓ Help
```

Reply keyboard (persistent at bottom):
```
[ ➕ New Project ] [ 📁 Projects ]
[ 📊 Analytics  ] [ ⚙️ Settings ]
```

## 13. Error Handling

- **Factory crash**: Detect when tmux session dies unexpectedly. Notify user with last 20 lines of log. Offer: Retry / View Full Log / Cancel.
- **API key expiration**: If a model call fails with auth error, notify user and pause factory.
- **Disk space**: Alert if disk usage exceeds 80%. At 90%, refuse new projects until space is freed.
- **Rate limits**: Track OpenRouter free tier usage. Warn at 80% of daily limit. Pause OpenCode factory if limit reached, offer to switch to paid models or wait.
- **Bot self-recovery**: If the bot crashes, Docker restart policy brings it back. On startup, check for any factory runs that were active and report their status.

## 14. Security

- Only whitelisted Telegram IDs can interact with the bot
- All commands from non-whitelisted users are silently ignored (no error message to avoid confirming bot exists)
- API keys are never displayed in full in Telegram messages (show first/last 4 chars only)
- Docker socket access is restricted to the factory user
- All factory runs are sandboxed to /home/factory/projects/

## 15. API Keys Required

| Key | Purpose | Required? |
|-----|---------|-----------|
| TELEGRAM_BOT_TOKEN | Bot communication | Yes |
| GOOGLE_API_KEY | Gemini CLI + zen MCP | Yes (for Gemini engine) |
| OPENROUTER_API_KEY | OpenCode/Aider free models + zen MCP | Yes |
| PERPLEXITY_API_KEY | Research MCP | Yes |
| GITHUB_TOKEN | Repo management | Yes |
| OPENAI_API_KEY | Whisper fallback + voice translation | Yes |
| GROQ_API_KEY | Whisper primary (fast transcription) | Yes |
| DATABASE_URL | PostgreSQL connection | Auto-configured |
