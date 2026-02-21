# Factory Control Bot — Software Requirements Specification v1.0

## 1. Overview

The **Factory Control Bot** is a Telegram bot serving as the complete command-and-control interface for the Black Box Software Factory v2. It replaces SSH-based workflows with a mobile-first experience, enabling users to:
- Create software projects via voice or text input
- Select and run multiple AI engines in parallel
- Monitor factory progress in real-time
- Manage deployments on the VPS
- Control Docker containers and system services
- View analytics and cost breakdowns

**Target Platform**: Telegram (mobile + desktop)
**Runtime**: VPS (Ubuntu 22.04+), Docker-based deployment

---

## 2. User Roles & Permissions

### 2.1 Role Definitions

| Role | Description | Capabilities |
|------|-------------|--------------|
| **Admin** | Primary owner (1 user) | All capabilities + manage whitelist (add/remove users) |
| **User** | Whitelisted trusted users (1-2) | Create projects, monitor, manage own projects, view analytics, VPS read-only |
| **Unauthorized** | Any Telegram ID not in whitelist | Silently ignored — no response, no error message |

### 2.2 Authentication Mechanism

- **Method**: Telegram user ID whitelist stored in the `users` database table
- **Initial Setup**: Admin's Telegram ID configured via `ADMIN_TELEGRAM_ID` env var on first boot
- **Runtime**: Admin can add/remove users via `/admin` command
- **Middleware**: Every incoming update is checked against the whitelist before handler dispatch
- **Silent Rejection**: Non-whitelisted users receive NO response (security by obscurity — doesn't confirm bot exists)

### 2.3 User Tracking

- All actions (project creation, factory start, deployment, etc.) log the initiating `telegram_user_id`
- Audit trail in `factory_events` table

---

## 3. Data Entities (Database Schema)

### 3.1 users
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| telegram_id | BIGINT | PK | Telegram user ID |
| username | VARCHAR(255) | NULLABLE | Telegram username |
| display_name | VARCHAR(255) | NOT NULL | User's display name |
| role | ENUM('admin', 'user') | NOT NULL, DEFAULT 'user' | User role |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | Whether user is active |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Account creation time |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update time |

### 3.2 projects
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, DEFAULT gen_random_uuid() | Project ID |
| name | VARCHAR(100) | UNIQUE, NOT NULL | Lowercase, hyphens only |
| description | TEXT | NULLABLE | Project description |
| status | ENUM | NOT NULL, DEFAULT 'draft' | draft, queued, running, paused, completed, failed, deployed |
| engines | VARCHAR[] | NOT NULL | Array of engine names |
| tier | SMALLINT | NULLABLE | Complexity tier (1, 2, or 3) |
| requirements_text | TEXT | NOT NULL | Final approved requirements |
| settings_json | JSONB | DEFAULT '{}' | Per-project settings override |
| deploy_config | JSONB | DEFAULT '{}' | Deployment configuration |
| created_by | BIGINT | FK -> users.telegram_id | Creating user |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation time |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update time |

**Validation**: `name` must match `^[a-z][a-z0-9-]*[a-z0-9]$`, 3-50 chars, unique across all projects.

### 3.3 factory_runs
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Run ID |
| project_id | UUID | FK -> projects.id, NOT NULL | Parent project |
| engine | VARCHAR(50) | NOT NULL | claude, gemini, opencode, aider |
| branch_prefix | VARCHAR(50) | NOT NULL | Git branch prefix (e.g., 'claude') |
| status | ENUM | NOT NULL, DEFAULT 'queued' | queued, running, paused, completed, failed |
| current_phase | SMALLINT | DEFAULT 0 | Current factory phase (0-7) |
| tmux_session | VARCHAR(100) | NULLABLE | tmux session name |
| pid | INTEGER | NULLABLE | Factory process PID |
| started_at | TIMESTAMPTZ | NULLABLE | Run start time |
| finished_at | TIMESTAMPTZ | NULLABLE | Run end time |
| cost_total | DECIMAL(10,4) | DEFAULT 0 | Total estimated cost |
| audit_log_path | VARCHAR(500) | NOT NULL | Path to audit log |
| quality_scores | JSONB | DEFAULT '{}' | Quality gate scores by phase |
| test_results | JSONB | DEFAULT '{}' | Test pass/fail/skip counts |
| created_by | BIGINT | FK -> users.telegram_id | Initiating user |

### 3.4 factory_events
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PK | Event ID |
| run_id | UUID | FK -> factory_runs.id, NOT NULL | Parent run |
| event_type | VARCHAR(50) | NOT NULL | phase_start, phase_end, clarify, error, cost, complete, user_input |
| phase | SMALLINT | NULLABLE | Phase number |
| data_json | JSONB | DEFAULT '{}' | Event-specific data |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Event timestamp |

**Index**: `(run_id, created_at)` for efficient event streaming.

### 3.5 deployments
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Deployment ID |
| project_id | UUID | FK -> projects.id, NOT NULL | Parent project |
| run_id | UUID | FK -> factory_runs.id, NULLABLE | Source factory run |
| deploy_type | ENUM | NOT NULL | telegram_bot, web_app, api_service, other |
| target | ENUM | NOT NULL | local_docker, remote_ssh |
| status | ENUM | NOT NULL, DEFAULT 'pending' | pending, building, running, healthy, unhealthy, stopped, failed |
| container_id | VARCHAR(100) | NULLABLE | Docker container ID |
| container_name | VARCHAR(100) | NULLABLE | Docker container name |
| port | INTEGER | NULLABLE | Exposed port |
| domain | VARCHAR(255) | NULLABLE | Domain/subdomain if configured |
| ssl_enabled | BOOLEAN | DEFAULT false | Whether SSL is configured |
| health_check_url | VARCHAR(500) | NULLABLE | Health check endpoint |
| env_vars | JSONB | DEFAULT '{}' | Non-sensitive env vars (sensitive stored separately) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Deployment time |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update time |

### 3.6 nodes
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Node ID |
| name | VARCHAR(100) | UNIQUE, NOT NULL | Human-readable node name |
| tailscale_ip | VARCHAR(45) | NULLABLE | Tailscale IP address |
| public_ip | VARCHAR(45) | NULLABLE | Public IP |
| status | ENUM | NOT NULL, DEFAULT 'active' | active, inactive, maintenance |
| capabilities_json | JSONB | DEFAULT '{}' | CPU cores, RAM, disk, GPU, etc. |
| is_current | BOOLEAN | DEFAULT false | Whether this is the current VPS |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Registration time |

**Note**: Single node for v1.0. Schema supports multi-node for future expansion.

### 3.7 settings
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| key | VARCHAR(100) | PK | Setting key |
| value | JSONB | NOT NULL | Setting value |
| updated_by | BIGINT | FK -> users.telegram_id | Last editor |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update time |

### 3.8 analytics
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PK | Record ID |
| project_id | UUID | FK -> projects.id, NOT NULL | Parent project |
| run_id | UUID | FK -> factory_runs.id, NULLABLE | Parent run |
| metric_name | VARCHAR(100) | NOT NULL | e.g., cost_anthropic, duration_phase_3, test_pass_rate |
| metric_value | DECIMAL(12,4) | NOT NULL | Numeric value |
| metadata_json | JSONB | DEFAULT '{}' | Additional context |
| recorded_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Recording time |

**Index**: `(project_id, metric_name, recorded_at)` for efficient analytics queries.

---

## 4. Bot Commands & Handlers

### 4.1 Command Handlers

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | `start_handler` | Show main menu with inline keyboard |
| `/menu` | `menu_handler` | Same as /start — show main menu |
| `/new` | `new_project_handler` | Start project creation wizard (ConversationHandler) |
| `/projects` | `projects_handler` | List all projects with status |
| `/analytics` | `analytics_handler` | Show analytics dashboard |
| `/docker` | `docker_handler` | Show Docker container management |
| `/system` | `system_handler` | Show system health and services |
| `/settings` | `settings_handler` | Show global settings menu |
| `/admin` | `admin_handler` | Manage whitelist (admin only) |
| `/help` | `help_handler` | Show help text |
| `/cancel` | `cancel_handler` | Cancel current conversation flow |
| `/update_engines` | `update_engines_handler` | Update all engine installations (admin only) |
| `/engine_status` | `engine_status_handler` | Show installed engine versions |

### 4.2 Callback Query Patterns

| Pattern | Description |
|---------|-------------|
| `menu:{action}` | Main menu navigation |
| `engine_toggle:{engine}` | Toggle engine selection in project wizard |
| `engine_confirm` | Confirm engine selection |
| `voice:{action}` | Voice input: done, edit, delete_last |
| `req:{action}` | Requirements review: approve, edit, regenerate |
| `settings_mode:{choice}` | Default vs customize |
| `deploy:{choice}` | Deployment configuration choices |
| `project_type:{type}` | Project type selection |
| `deploy_target:{target}` | Deploy target selection |
| `access:{choice}` | Domain/access configuration |
| `proj:{project_id}:{action}` | Project actions: view, logs, resume, stop, deploy, feature, delete |
| `proj_confirm_delete:{id}` | Confirm project deletion |
| `run:{run_id}:{action}` | Factory run actions: watch, pause_updates |
| `docker:{container_id}:{action}` | Docker container actions: start, stop, restart, logs, remove |
| `docker_confirm_remove:{id}` | Confirm container removal |
| `svc:{service}:{action}` | Service actions: restart, logs |
| `setting:{key}` | Open setting for editing |
| `setting_val:{key}:{value}` | Set a setting value |
| `clarify:{run_id}:{answer_idx}` | Answer clarification question |
| `analytics:{view}` | Analytics view: per_project, aggregate, trends, compare |
| `admin:{action}` | Admin: add_user, remove_user, list_users |
| `page:{context}:{offset}` | Pagination for lists |

**Callback data limit**: 64 bytes max. Use short prefixes, UUIDs trimmed to first 8 chars where needed.

### 4.3 Message Handlers

| Filter | Handler | Description |
|--------|---------|-------------|
| `filters.VOICE` | `voice_message_handler` | Process voice messages during input flows |
| `filters.TEXT` (in conversation) | `text_input_handler` | Process text input during conversation flows |
| `filters.REPLY` (to clarification) | `clarify_reply_handler` | Handle open-ended clarification answers |

---

## 5. Conversation Flows (State Machines)

### 5.1 Project Creation Wizard

```
States:
  ENGINE_SELECT    -> User selects engines via inline keyboard
  NAME_INPUT       -> User types project name
  DESCRIPTION_INPUT -> User types/voices project description
  REQUIREMENTS_GATHERING -> Voice/text input cycle
  REQUIREMENTS_REVIEW -> AI-structured requirements shown for approval
  SETTINGS_CHOICE  -> Default or customize
  SETTINGS_CUSTOM  -> Per-project settings (if customize chosen)
  DEPLOY_CHOICE    -> Auto-deploy yes/no
  PROJECT_TYPE     -> Select project type (if deploying)
  DEPLOY_TARGET    -> Select deploy target
  ACCESS_CONFIG    -> Domain/SSL configuration (if web app)
  CONFIRM_LAUNCH   -> Final confirmation
```

**Flow**:
1. `/new` -> Show engine multi-select keyboard -> `ENGINE_SELECT`
2. User toggles engines, presses Confirm -> `NAME_INPUT`
3. User types name -> validate -> `DESCRIPTION_INPUT`
4. User types/voices description -> `REQUIREMENTS_GATHERING`
5. Voice/text input cycle with Done/Edit/Delete -> (on Done) -> AI structuring -> `REQUIREMENTS_REVIEW`
6. User approves requirements -> `SETTINGS_CHOICE`
7. "Start with defaults" -> `DEPLOY_CHOICE` | "Customize" -> `SETTINGS_CUSTOM` -> `DEPLOY_CHOICE`
8. "Yes auto-deploy" -> `PROJECT_TYPE` -> `DEPLOY_TARGET` -> `ACCESS_CONFIG` -> `CONFIRM_LAUNCH`
9. "No auto-deploy" -> `CONFIRM_LAUNCH`
10. User confirms -> Create project in DB, start factory run(s), redirect to monitoring

**Cancel**: `/cancel` at any state -> abort wizard, clean up partial data

### 5.2 Voice Input Sub-Flow

Used in: project description, requirements gathering, feature requests

```
State: VOICE_TEXT_INPUT
  - User sends voice -> transcribe -> display text + [Done|Edit|Delete Last]
  - User sends text -> display text + [Done|Edit|Delete Last]
  - User presses Edit -> bot sends transcript -> user replies with correction -> replace
  - User presses Delete Last -> remove last segment -> show updated
  - User presses Done -> concatenate all segments -> exit sub-flow
```

**Data stored in** `context.user_data['voice_segments']` (list of strings)

### 5.3 Requirements Review Sub-Flow

```
After voice Done:
  1. If segments not in English -> translate via AI (configurable model)
  2. Send concatenated text to AI for structuring into formal requirements
  3. Display structured requirements to user
  4. Buttons: [Approve | Edit | Regenerate]
  - Approve -> continue to next state
  - Edit -> bot sends as message, user replies with correction
  - Regenerate -> re-run AI structuring with different prompt variation
```

### 5.4 Factory Monitoring Flow

```
When factory run starts:
  1. Create async monitoring task for each run
  2. Monitoring task: poll log file every 3 seconds
  3. Parse structured markers from log
  4. On PHASE_START/PHASE_END -> send notification
  5. On CLARIFY -> send question as Telegram message with buttons
  6. On ERROR -> send error notification with action buttons
  7. On COMPLETE -> send full summary

Real-time mode (user watching):
  1. Bot maintains one "live" message that is edited every 3-5 seconds
  2. Content: phase, last 5 log lines, progress indicator
  3. Pause Updates button to stop editing
```

### 5.5 Admin User Management

```
/admin -> Show admin menu
  - List users -> show all whitelisted users
  - Add user -> ask for Telegram user ID -> validate -> add to DB
  - Remove user -> show user list -> confirm -> remove from DB
```

---

## 6. External Integrations

### 6.1 Transcription Services

| Service | Priority | API | Rate Limit | Cost |
|---------|----------|-----|------------|------|
| Groq Whisper | Primary | `api.groq.com/openai/v1/audio/transcriptions` | 20 req/min | Free tier |
| OpenAI Whisper | Fallback | `api.openai.com/v1/audio/transcriptions` | Standard | $0.006/min |

**Fallback Logic**: Try Groq first. If HTTP 429/500/timeout -> switch to OpenAI for this request. Track Groq failures; if 3 consecutive failures, use OpenAI as primary for 5 minutes.

### 6.2 AI Models (Translation + Requirements Structuring)

- **Translation**: Configurable model (default: OpenAI GPT-4o-mini via OpenRouter for cost efficiency)
- **Requirements Structuring**: Configurable model (default: same as translation)
- Both configurable in global settings

### 6.3 Factory Engines

| Engine | Install Command | Start Method | Config File |
|--------|----------------|--------------|-------------|
| Claude Code | `npm install -g @anthropic-ai/claude-code` | tmux + `claude` | CLAUDE.md |
| Gemini CLI | `npm install -g @anthropic-ai/gemini-cli` | tmux + `gemini` | GEMINI.md |
| OpenCode | `curl -fsSL https://opencode.ai/install \| bash` | tmux + `opencode` | OPENCODE.md |
| Aider | `pip install aider-chat` | tmux + `aider` | .aider.conf.yml |

**Per engine, the bot**:
1. Creates project directory at `/home/factory/projects/{project-name}-{engine}/`
2. Copies CLAUDE.md/GEMINI.md/OPENCODE.md to project dir
3. Writes `raw-input.md` with approved requirements
4. Creates tmux session: `tmux new-session -d -s {project}-{engine}`
5. Sends factory start command to tmux session
6. Begins log monitoring

### 6.4 Docker Socket

- Bot accesses Docker via mounted `/var/run/docker.sock`
- Uses `docker` Python SDK (aiodocker for async)
- Operations: list containers, start, stop, restart, logs, remove, compose up/down

### 6.5 System Monitoring

- Uses `psutil` for CPU, RAM, disk metrics
- Uses `subprocess` for service status (`systemctl is-active`)
- Services monitored: docker, nginx, postgresql, tailscaled, fail2ban

### 6.6 GitHub

- Uses `GITHUB_TOKEN` for repo operations
- Creates repos, pushes branches, manages PRs
- Each parallel engine run uses branch prefix: `{engine}/dev`, `{engine}/main`

---

## 7. Communication Protocol (Bot <-> Factory)

### 7.1 Factory -> Bot (Structured Log Markers)

The factory writes these markers to `artifacts/reports/factory-run.log`:

```
[FACTORY:PHASE:N:START]          - Phase N started
[FACTORY:PHASE:N:END:score]      - Phase N completed with quality gate score
[FACTORY:CLARIFY:question_json]  - Clarification question for user
[FACTORY:ERROR:message]          - Error needing user attention
[FACTORY:COST:amount:provider]   - Cost update
[FACTORY:COMPLETE:summary_json]  - Factory run finished
```

**question_json format**:
```json
{
  "question": "What authentication method should we use?",
  "type": "multiple_choice",
  "options": ["JWT tokens", "Session-based", "OAuth2"],
  "context": "The app needs user authentication..."
}
```

**summary_json format**:
```json
{
  "project": "my-app",
  "engine": "claude",
  "duration_minutes": 45,
  "phases": {"1": 98, "2": null, "3": 97, "4": null, "5": 97, "6": 98, "7": 97},
  "total_cost": 12.50,
  "cost_by_provider": {"anthropic": 0, "google": 3.20, "openai": 5.30, "openrouter": 4.00},
  "test_results": {"passed": 42, "failed": 0, "skipped": 2},
  "github_url": "https://github.com/user/my-app",
  "deploy_status": "healthy"
}
```

### 7.2 Bot -> Factory (Input Files)

| File | Purpose | Format |
|------|---------|--------|
| `artifacts/reports/clarification-answers.json` | Answers to clarification questions | `[{"question_id": 1, "answer": "JWT tokens"}]` |
| `.factory-stop` | Signal to stop factory | Touch file (empty) |
| `.factory-pause` | Signal to pause after current phase | Touch file (empty) |

Factory checks for these files between phases.

---

## 8. Error Handling

### 8.1 Factory Errors

| Error | Detection | Action |
|-------|-----------|--------|
| Factory crash | tmux session dies, process exits non-zero | Notify user with last 20 log lines, offer Retry/View Full Log/Cancel |
| Stuck factory | No log update for >10 minutes | Send warning, offer Stop/Continue Waiting |
| Quality gate fail | `[FACTORY:PHASE:N:END:score]` with score < 97 | Log, factory auto-retries per CLAUDE.md rules. Notify user if escalated |
| Fix cycle fail (3x) | Factory writes `[FACTORY:ERROR:...]` | Pause factory, ask user for guidance |

### 8.2 API/Service Errors

| Error | Detection | Action |
|-------|-----------|--------|
| Groq Whisper timeout/error | HTTP 429/500/timeout | Auto-fallback to OpenAI Whisper |
| OpenAI API error | HTTP error response | Retry 2x with exponential backoff, then notify user |
| Telegram API rate limit | HTTP 429 | Respect retry_after header, queue messages |
| Docker socket unavailable | Connection error | Notify admin, suggest checking Docker service |
| PostgreSQL connection lost | Connection error | Auto-reconnect with pool, notify if persistent |

### 8.3 Resource Errors

| Error | Detection | Action |
|-------|-----------|--------|
| Disk usage > 80% | Periodic check (every 5 min) | Alert admin |
| Disk usage > 90% | Periodic check | Refuse new projects, alert admin urgently |
| OpenRouter rate limit approaching | Track daily request count | Warn at 80% of 200/day limit |
| OpenRouter rate limit hit | HTTP 429 | Pause OpenCode factory, offer switch to paid model or wait |
| Memory pressure | psutil check | Log warning, alert if >90% |

### 8.4 Bot Self-Recovery

- Docker restart policy: `restart: unless-stopped`
- On startup: scan DB for runs with status='running', check if tmux sessions still exist
  - If session alive: re-attach monitoring
  - If session dead: mark run as 'failed', notify user

---

## 9. Performance Requirements

| Metric | Target |
|--------|--------|
| Bot command response time | < 1 second |
| Voice transcription (Groq) | < 3 seconds for 1-minute audio |
| Voice transcription (OpenAI fallback) | < 8 seconds for 1-minute audio |
| Log polling interval | 3 seconds (configurable 2-5s) |
| Live message edit rate | Every 3-5 seconds (respect Telegram limits) |
| Concurrent factory run monitoring | Up to 10 simultaneous runs |
| Database query response | < 50ms for indexed queries |
| Analytics aggregation | < 2 seconds for monthly rollups |
| Concurrent Telegram users | Up to 5 simultaneous users |

---

## 10. Settings System

### 10.1 Global Settings (stored in `settings` table)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_engine` | string | "claude" | Default engine for new projects |
| `voice_provider` | string | "auto" | "groq", "openai", or "auto" |
| `translation_model` | string | "gpt-4o-mini" | Model for translating voice to English |
| `requirements_model` | string | "gpt-4o-mini" | Model for structuring requirements |
| `notification_events` | string[] | ["phase_end", "error", "complete"] | Events that trigger notifications |
| `quality_gate_threshold` | integer | 97 | Default quality gate threshold |
| `max_quality_retries` | integer | 3 | Max retries per quality gate |
| `max_fix_cycles` | integer | 5 | Max fix cycles in Phase 6 |
| `cost_alert_threshold` | decimal | 50.00 | Alert if project cost exceeds this |
| `domain_name` | string | null | Registered domain for web deployments |
| `ssl_email` | string | null | Email for certbot SSL |
| `log_poll_interval` | integer | 3 | Seconds between log polls |

### 10.2 Per-Project Settings Override (stored in `projects.settings_json`)

| Key | Type | Description |
|-----|------|-------------|
| `tier_override` | integer | Force complexity tier (1, 2, or 3) |
| `model_overrides` | object | Model override per role (e.g., `{"code_reviewer": "gpt-5.2"}`) |
| `quality_gate_threshold` | integer | Override quality gate threshold |
| `max_quality_retries` | integer | Override max retries |
| `cost_limit` | decimal | Hard stop if cost exceeds this |
| `auto_deploy` | boolean | Whether to auto-deploy |
| `deploy_type` | string | Project type for deployment |
| `deploy_target` | string | Deployment target |

---

## 11. Security Requirements

### 11.1 Access Control
- Whitelist-only access via Telegram user IDs
- Silent ignore for non-whitelisted users (no error message — doesn't confirm bot exists)
- Admin-only commands: `/admin`, `/update_engines`, user management

### 11.2 Data Protection
- API keys NEVER displayed in full in Telegram messages (show first 4 + last 4 chars only, e.g., `sk-ab...xy9z`)
- API keys stored in `.factory-env` file with 600 permissions
- Database credentials via environment variables only
- No sensitive data in callback_data (use IDs, not values)

### 11.3 Sandboxing
- All factory runs sandboxed to `/home/factory/projects/`
- Docker socket access restricted to the factory system user
- Bot runs as non-root user in its Docker container
- Each factory run gets its own isolated project directory

### 11.4 Input Validation
- Project names: strict regex validation
- Voice files: size limit (20MB Telegram limit)
- Text input: sanitize for log injection (strip `[FACTORY:` prefixes from user text)
- Callback data: validate format before processing

---

## 12. Deployment Requirements

### 12.1 Docker Deployment

The bot runs as a Docker container:
- **Base image**: python:3.12-slim
- **Volumes**: `/home/factory/projects` (R/W), `/var/run/docker.sock` (R/W), `/home/factory/.factory-env` (R)
- **Restart policy**: `unless-stopped`
- **Network**: host network (needs access to tmux, Docker socket, and local services)
- **Resource limits**: 512MB RAM, 1 CPU

### 12.2 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `ADMIN_TELEGRAM_ID` | Yes | Admin's Telegram user ID (initial setup) |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GROQ_API_KEY` | Yes | Groq API for Whisper transcription |
| `OPENAI_API_KEY` | Yes | OpenAI API for Whisper fallback + translation |
| `OPENROUTER_API_KEY` | Yes | OpenRouter for free models |
| `GOOGLE_API_KEY` | Yes (Gemini) | Google API for Gemini engine |
| `PERPLEXITY_API_KEY` | Yes | Perplexity for research |
| `GITHUB_TOKEN` | Yes | GitHub for repo management |
| `FACTORY_ROOT_DIR` | No | Default: `/home/factory/projects` |
| `LOG_LEVEL` | No | Default: `INFO` |

### 12.3 Systemd Backup

A systemd service file as backup in case Docker itself goes down:
- `factory-control-bot.service`
- Watches the Docker container, restarts if needed
- Alerts admin if Docker daemon is down

---

## 13. Main Menu Navigation

```
/start or /menu:

  Black Box Factory v2

  [New Project]     [Projects]
  [Analytics]       [Docker]
  [System]          [Settings]
  [Help]

Reply keyboard (persistent):
  [ New Project ] [ Projects ]
  [ Analytics  ]  [ Settings ]
```

---

## 14. Analytics

### 14.1 Per-Project Analytics
- Cost breakdown by AI provider (Anthropic, Google, OpenAI, OpenRouter, Perplexity)
- Cost breakdown by phase (1-7)
- Duration per phase
- Quality gate scores per phase
- Test pass/fail/skip counts

### 14.2 Aggregate Analytics
- Total spend this month
- Projects completed this month
- Average cost per complexity tier
- Success rate (completed / total runs)
- Average duration per tier

### 14.3 Engine Comparison
- For parallel runs (same project, multiple engines): side-by-side comparison
- Metrics: cost, duration, quality scores, test coverage

### 14.4 Trends
- Cost over time (daily/weekly/monthly)
- Projects per week/month
- Format: formatted text messages with data tables
- Complex charts: generate as images (matplotlib/plotly) and send as photos

---

## 15. Third-Party Engine Management

### 15.1 Engine Installation/Update
- `/update_engines` command triggers update of all engines
- Per-engine update commands (run in background, notify on completion)
- Version tracking in settings table

### 15.2 Engine Health Check
- `/engine_status` shows: engine name, installed version, last used, status (ok/error)
- Checks: binary exists, can execute `--version`, API keys configured

### 15.3 OpenRouter Rate Limit Tracking
- Track requests per minute and per day
- **Persistence**: Store counters in PostgreSQL `settings` table (keys: `openrouter_daily_count`, `openrouter_daily_reset_at`) to survive container restarts
- On startup: read current count from DB; if `daily_reset_at` < today, reset to 0
- Increment counter on each OpenRouter API call; flush to DB every 10 requests or every 60 seconds (whichever comes first)
- Warn at 80% of daily limit (160/200)
- Block new OpenCode runs at 95% (190/200)

---

## 16. System Prompts & Templates

### 16.1 Template Storage
All engine configuration templates and system prompts are stored in the bot's Docker image at `/app/templates/`:

```
/app/templates/
  engine_configs/
    CLAUDE.md          # Claude Code orchestrator instructions
    GEMINI.md          # Gemini CLI orchestrator instructions
    OPENCODE.md        # OpenCode orchestrator instructions
    .aider.conf.yml    # Aider configuration
  prompts/
    requirements_structurer.txt   # System prompt for structuring raw text into requirements
    translator.txt                # System prompt for translating voice input to English
    summary_generator.txt         # System prompt for generating factory run summaries
```

### 16.2 Template Versioning
- Templates are versioned with the bot's Docker image
- Admin can override prompts via `/settings` -> "System Prompts" (stored in `settings` table as JSON)
- Runtime resolution: check `settings` table override first, fall back to file-based template

### 16.3 Engine Config Deployment
When starting a factory run, the bot:
1. Copies the relevant engine config template from `/app/templates/engine_configs/` to the project directory
2. Injects project-specific variables (project name, tier, model assignments) into the template
3. Writes `artifacts/requirements/raw-input.md` with the approved requirements

---

## 17. Database Backup & Maintenance

### 17.1 Automated Backups
- Daily `pg_dump` via cron job inside the PostgreSQL container (or a sidecar container)
- Backup stored at `/home/factory/backups/db/` with format `factory_bot_YYYY-MM-DD.sql.gz`
- Retain last 7 daily backups, last 4 weekly backups (Sunday)
- Backup script: `/app/scripts/backup_db.sh`

### 17.2 Log Rotation
- Factory run logs: rotate when > 10MB, keep last 5 rotations per project
- Bot application logs: daily rotation, keep last 30 days
- Use Python's `logging.handlers.RotatingFileHandler` for bot logs
- Factory logs managed by the factory process itself

### 17.3 Database Maintenance
- Weekly `VACUUM ANALYZE` on `factory_events` and `analytics` tables (high-write tables)
- Configurable via cron in docker-compose

---

## 18. Edge Cases

| Scenario | Handling |
|----------|----------|
| Container restart during rate tracking | Rate counters persisted in PostgreSQL; on startup read from DB |
| User sends voice during non-voice state | Ignore or prompt "Use /new to start a project" |
| Two users create project with same name simultaneously | DB unique constraint prevents collision; second user gets error |
| Factory run hangs indefinitely | 10-minute idle detection -> warn -> user can stop |
| Bot restart during active factory run | On startup, re-scan DB, re-attach to existing tmux sessions |
| Disk full during factory run | Factory will fail; bot detects via periodic check, notifies user |
| Telegram message too long (>4096 chars) | Split into multiple messages or truncate with "... (truncated)" |
| User presses Done with zero voice segments | Show error "No input received. Send voice or text first." |
| Invalid project name on retry | Show specific validation error, let user try again (max 3 attempts) |
| Concurrent factory monitoring overload | Cap at 10 simultaneous monitors; queue additional |
| Engine not installed when selected | Check before launch, offer to install |
