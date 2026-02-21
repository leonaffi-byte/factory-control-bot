# Deployment Guide — Factory Control Bot v2.0.0

This guide covers all deployment options for Factory Control Bot v2.0, including Docker Compose, manual deployment, full VPS production setup with systemd, and the one-line installer.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Option 1: Docker Deployment (Recommended)](#option-1-docker-deployment)
3. [Option 2: Manual Deployment](#option-2-manual-deployment)
4. [Option 3: VPS Production Deployment](#option-3-vps-production-deployment)
5. [One-Line Installer](#one-line-installer)
6. [CLI Setup](#cli-setup)
7. [Environment Variables Reference](#environment-variables-reference)
8. [API Keys Reference](#api-keys-reference)
9. [Health Monitoring](#health-monitoring)
10. [Backup and Maintenance](#backup-and-maintenance)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Min Version | Ubuntu 22.04+ Install | macOS Install | Windows (WSL2) |
|----------|-------------|----------------------|---------------|----------------|
| Python | 3.12 | `sudo apt install python3.12 python3.12-venv` | `brew install python@3.12` | Install via python.org |
| PostgreSQL | 16 | `sudo apt install postgresql-16` | `brew install postgresql@16` | Install via postgresql.org |
| Docker | 24 | `curl -fsSL https://get.docker.com \| sh` | Docker Desktop | Docker Desktop |
| Docker Compose | 2.20 | Included with Docker | Included with Docker Desktop | Included with Docker Desktop |
| tmux | 3.3 | `sudo apt install tmux` | `brew install tmux` | `sudo apt install tmux` (WSL2) |
| Git | 2.30 | `sudo apt install git` | `brew install git` | `sudo apt install git` (WSL2) |

### Required Telegram Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) — send `/newbot` and follow instructions
2. Copy the bot token (format: `123456789:ABCdef...`)
3. Find your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot)

### Required Accounts

| Service | Purpose | Registration |
|---------|---------|-------------|
| Telegram Bot API | Bot access | [@BotFather](https://t.me/BotFather) |
| Groq | Voice transcription (primary, free tier) | [console.groq.com](https://console.groq.com) |
| OpenAI | Voice transcription (fallback) | [platform.openai.com](https://platform.openai.com) |
| OpenRouter | Free model access + translation | [openrouter.ai](https://openrouter.ai) |

### Optional Accounts (v2.0 providers)

| Service | Purpose | Registration |
|---------|---------|-------------|
| NVIDIA NIM | Fast inference (free tier) | [build.nvidia.com](https://build.nvidia.com) |
| Together AI | Open model access | [api.together.xyz](https://api.together.xyz) |
| Cerebras | High-speed inference | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| SambaNova | Enterprise open models | [cloud.sambanova.ai](https://cloud.sambanova.ai) |
| Fireworks AI | Fast open models | [fireworks.ai](https://fireworks.ai) |
| Mistral AI | Mistral models | [console.mistral.ai](https://console.mistral.ai) |
| Google AI Studio | Gemini models | [aistudio.google.com](https://aistudio.google.com) |
| Perplexity | Research queries | [perplexity.ai](https://perplexity.ai) |
| GitHub | Repo management | [github.com](https://github.com) |

---

## Option 1: Docker Deployment

Docker is the recommended deployment method. It starts the bot, worker, and PostgreSQL with a single command.

### Step 1: Navigate to the Backend Directory

```bash
cd factory-control-bot/artifacts/code/backend
```

### Step 2: Create the Environment File

```bash
cat > .env << 'EOF'
# ── Required ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN=your-bot-token-here
ADMIN_TELEGRAM_ID=123456789

# ── Database ───────────────────────────────────────────
# Must match POSTGRES_PASSWORD below
POSTGRES_PASSWORD=change-this-to-a-strong-password
DATABASE_URL=postgresql+asyncpg://factory:change-this-to-a-strong-password@localhost:5432/factory_bot

# ── v1.0 API Keys ──────────────────────────────────────
GROQ_API_KEY=
OPENAI_API_KEY=
OPENROUTER_API_KEY=
GOOGLE_API_KEY=
PERPLEXITY_API_KEY=
GITHUB_TOKEN=

# ── v2.0 API Keys ──────────────────────────────────────
NVIDIA_API_KEY=
TOGETHER_API_KEY=
CEREBRAS_API_KEY=
SAMBANOVA_API_KEY=
FIREWORKS_API_KEY=
MISTRAL_API_KEY=

# ── Factory ────────────────────────────────────────────
FACTORY_ROOT_DIR=/home/factory/projects
DEFAULT_ENGINE=claude
DEFAULT_ROUTING_MODE=api_direct
QUALITY_GATE_THRESHOLD=97

# ── Monitoring ─────────────────────────────────────────
HEALTH_CHECK_INTERVAL=300
DISK_WARNING_PERCENT=80
DISK_CRITICAL_PERCENT=90

# ── Logging ────────────────────────────────────────────
LOG_LEVEL=INFO
EOF
```

### Step 3: Create Required Directories

```bash
sudo mkdir -p /home/factory/projects
sudo mkdir -p /home/factory/backups/db
sudo chown -R $(whoami):$(whoami) /home/factory
```

### Step 4: Start Services

```bash
docker compose up -d
```

This starts three services:
- `postgres` — PostgreSQL 16 database (health-checked)
- `bot` — Telegram bot + API services
- `worker` — Background task processor

Database migrations run automatically on first startup.

### Step 5: Verify

```bash
# Check all services are running
docker compose ps

# Tail bot logs
docker compose logs -f bot

# Tail worker logs
docker compose logs -f worker

# Check database
docker compose exec postgres pg_isready -U factory -d factory_bot
```

### Managing the Stack

```bash
# Stop services (preserves data)
docker compose down

# Stop and remove volumes (DESTRUCTIVE — deletes all data)
docker compose down -v

# Restart a single service
docker compose restart bot

# Rebuild after code changes
docker compose up -d --build

# View resource usage
docker compose stats
```

---

## Option 2: Manual Deployment

Use manual deployment for development, CI environments, or when Docker is not available.

### Step 1: Install System Dependencies

**Ubuntu 22.04+:**
```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
    postgresql-16 tmux git curl procps build-essential
```

**macOS:**
```bash
brew install python@3.12 postgresql@16 tmux git
brew services start postgresql@16
```

### Step 2: Set Up PostgreSQL

```bash
# Ubuntu
sudo -u postgres createuser factory
sudo -u postgres createdb factory_bot -O factory
sudo -u postgres psql -c "ALTER USER factory PASSWORD 'your-db-password';"

# macOS (Homebrew PostgreSQL)
createuser factory
createdb factory_bot -O factory
psql factory_bot -c "ALTER USER factory PASSWORD 'your-db-password';"
```

### Step 3: Set Up Python Environment

```bash
cd factory-control-bot/artifacts/code/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your-bot-token
ADMIN_TELEGRAM_ID=123456789
DATABASE_URL=postgresql+asyncpg://factory:your-db-password@localhost:5432/factory_bot
GROQ_API_KEY=your-groq-key
OPENAI_API_KEY=your-openai-key
OPENROUTER_API_KEY=your-openrouter-key
FACTORY_ROOT_DIR=/home/factory/projects
LOG_LEVEL=INFO
DEFAULT_ROUTING_MODE=api_direct
EOF
```

### Step 5: Create Project Directory

```bash
mkdir -p /home/factory/projects
mkdir -p /home/factory/backups
```

### Step 6: Start Bot and Worker

Migrations run automatically on first boot.

```bash
# Terminal 1: Bot service
source .venv/bin/activate
python -m app.main

# Terminal 2: Worker service
source .venv/bin/activate
python -m app.worker
```

### Step 7: Install CLI (Optional)

```bash
source .venv/bin/activate
pip install -e .
factory --help
```

---

## Option 3: VPS Production Deployment

Full production setup with systemd services, nginx, SSL, and automated backups.

### Step 1: Provision the Server

Minimum recommended specs:
- **OS**: Ubuntu 22.04 LTS
- **RAM**: 2 GB
- **CPU**: 2 vCPUs
- **Disk**: 20 GB SSD
- **Network**: Public IP with port 443 open (for SSL webhook, optional)

### Step 2: Create the Factory User

```bash
# Run as root or a sudo-capable user
sudo useradd -m -s /bin/bash factory
sudo usermod -aG docker factory

# Create required directories
sudo mkdir -p /home/factory/projects
sudo mkdir -p /home/factory/backups/db
sudo chown -R factory:factory /home/factory

# Switch to factory user
sudo -u factory -i
```

### Step 3: Install System Dependencies

```bash
# As factory user (or via sudo)
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
    postgresql-16 tmux git curl procps build-essential
```

Install Docker:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker factory
# Log out and back in for group membership to take effect
```

### Step 4: Clone and Configure

```bash
# As factory user
git clone <your-repo-url> /home/factory/factory-control-bot
cd /home/factory/factory-control-bot/artifacts/code/backend

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Create `.env`:
```bash
cat > /home/factory/factory-control-bot/artifacts/code/backend/.env << 'EOF'
TELEGRAM_BOT_TOKEN=your-bot-token
ADMIN_TELEGRAM_ID=123456789
DATABASE_URL=postgresql+asyncpg://factory:your-db-password@localhost:5432/factory_bot
POSTGRES_PASSWORD=your-db-password
GROQ_API_KEY=your-groq-key
OPENAI_API_KEY=your-openai-key
OPENROUTER_API_KEY=your-openrouter-key
GOOGLE_API_KEY=your-google-key
NVIDIA_API_KEY=your-nvidia-key
FACTORY_ROOT_DIR=/home/factory/projects
BACKUP_DIR=/home/factory/backups
LOG_LEVEL=INFO
DEFAULT_ROUTING_MODE=api_direct
QUALITY_GATE_THRESHOLD=97
DISK_WARNING_PERCENT=80
DISK_CRITICAL_PERCENT=90
EOF
chmod 600 /home/factory/factory-control-bot/artifacts/code/backend/.env
```

### Step 5: Set Up PostgreSQL

```bash
sudo -u postgres createuser factory
sudo -u postgres createdb factory_bot -O factory
sudo -u postgres psql -c "ALTER USER factory PASSWORD 'your-db-password';"
```

### Step 6: Create systemd Service — factory-bot

```bash
sudo tee /etc/systemd/system/factory-bot.service << 'EOF'
[Unit]
Description=Factory Control Bot — Telegram Bot Service
After=network.target postgresql.service docker.service
Requires=postgresql.service

[Service]
Type=simple
User=factory
Group=factory
WorkingDirectory=/home/factory/factory-control-bot/artifacts/code/backend
Environment=PATH=/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/home/factory/factory-control-bot/artifacts/code/backend/.env
ExecStart=/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=factory-bot

[Install]
WantedBy=multi-user.target
EOF
```

### Step 7: Create systemd Service — factory-worker

```bash
sudo tee /etc/systemd/system/factory-worker.service << 'EOF'
[Unit]
Description=Factory Control Bot — Background Worker Service
After=network.target postgresql.service factory-bot.service
Requires=postgresql.service

[Service]
Type=simple
User=factory
Group=factory
WorkingDirectory=/home/factory/factory-control-bot/artifacts/code/backend
Environment=PATH=/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/home/factory/factory-control-bot/artifacts/code/backend/.env
ExecStart=/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin/python -m app.worker
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=factory-worker

[Install]
WantedBy=multi-user.target
EOF
```

### Step 8: Enable and Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable factory-bot factory-worker
sudo systemctl start factory-bot factory-worker

# Verify both are running
sudo systemctl status factory-bot
sudo systemctl status factory-worker
```

### Step 9: Configure sudoers for Service Management

The bot can restart whitelisted services via Telegram `/services`. Grant passwordless sudo for those specific commands only:

```bash
sudo visudo -f /etc/sudoers.d/factory-bot
```

Add these lines (do not modify beyond these specific commands):
```
factory ALL=(root) NOPASSWD: /usr/bin/systemctl restart docker
factory ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx
factory ALL=(root) NOPASSWD: /usr/bin/systemctl restart postgresql
factory ALL=(root) NOPASSWD: /usr/bin/systemctl restart tailscaled
factory ALL=(root) NOPASSWD: /usr/bin/systemctl restart fail2ban
factory ALL=(root) NOPASSWD: /usr/bin/systemctl status docker
factory ALL=(root) NOPASSWD: /usr/bin/systemctl status nginx
factory ALL=(root) NOPASSWD: /usr/bin/systemctl status postgresql
factory ALL=(root) NOPASSWD: /usr/bin/systemctl status tailscaled
factory ALL=(root) NOPASSWD: /usr/bin/systemctl status fail2ban
```

### Step 10: Set Up nginx (Optional — for webhook mode or web dashboard)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

sudo tee /etc/nginx/sites-available/factory-bot << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/factory-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Obtain SSL certificate:
```bash
sudo certbot --nginx -d your-domain.com --email your-email@example.com --agree-tos --non-interactive
```

Set in `.env`:
```
DOMAIN_NAME=your-domain.com
SSL_EMAIL=your-email@example.com
```

### Step 11: Set Up Automated Database Backups

```bash
# Run backups daily at 03:00
(crontab -l 2>/dev/null; echo "0 3 * * * /home/factory/factory-control-bot/artifacts/code/backend/scripts/backup_db.sh >> /home/factory/backups/backup.log 2>&1") | crontab -

# Verify cron entry
crontab -l
```

---

## One-Line Installer

For a fully automated VPS setup, use the built-in installer. It detects your system, installs all dependencies, sets up PostgreSQL, installs engine CLIs, configures Docker, and creates both systemd services.

```bash
# From the backend directory with venv activated
factory install
```

Or use the deploy script in install mode:

```bash
# From artifacts/release/
bash deploy.sh install
```

The installer runs these steps in order:
1. `postgres` — Check or install PostgreSQL and create the database
2. `python` — Create virtualenv and install requirements
3. `engines` — Install engine CLIs (claude, gemini, aider, opencode)
4. `docker` — Install Docker if not present
5. `systemd` — Create and enable factory-bot and factory-worker services

---

## CLI Setup

The `factory` CLI is registered as a console script in `pyproject.toml`.

### Install

```bash
cd factory-control-bot/artifacts/code/backend
source .venv/bin/activate
pip install -e .
```

### Permanent PATH Configuration

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):
```bash
export PATH="/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin:$PATH"
```

### Useful Aliases

```bash
# Add to ~/.bashrc
alias fs='factory status'
alias fl='factory logs'
alias fh='factory health'
alias fr='factory run'
```

### Shell Completion

```bash
# Bash
factory --install-completion bash

# Zsh
factory --install-completion zsh
```

---

## Environment Variables Reference

### Required Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdef...` | Telegram Bot API token from @BotFather |
| `ADMIN_TELEGRAM_ID` | `123456789` | Admin's Telegram numeric user ID |

### Database Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://factory:factory@localhost:5432/factory_bot` | No | PostgreSQL async connection string |
| `DB_POOL_SIZE` | `10` | No | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `5` | No | Max overflow connections above pool size |
| `DB_POOL_RECYCLE` | `3600` | No | Recycle connections after N seconds |

For Docker deployment, also set:

| Variable | Example | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | `change-me` | PostgreSQL password (used by docker-compose postgres service) |

### Factory Pipeline Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `FACTORY_ROOT_DIR` | `/home/factory/projects` | No | Root directory for all factory projects |
| `TEMPLATES_DIR` | `/app/templates` | No | Engine config and prompt templates directory |
| `DEFAULT_ENGINE` | `claude` | No | Default AI engine: claude, gemini, opencode, aider |
| `QUALITY_GATE_THRESHOLD` | `97` | No | Quality gate pass score (0-100) |
| `MAX_QUALITY_RETRIES` | `3` | No | Max retries per quality gate before escalation |
| `MAX_FIX_CYCLES` | `5` | No | Max fix cycles in Phase 6 |
| `COST_ALERT_THRESHOLD` | `50.0` | No | Alert when project API cost exceeds this (USD) |
| `DEFAULT_ROUTING_MODE` | `api_direct` | No | Model routing: `api_direct`, `openrouter`, or `clink` |

### Monitoring Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `LOG_POLL_INTERVAL` | `3` | No | Seconds between log file polls |
| `MAX_CONCURRENT_MONITORS` | `10` | No | Max simultaneous monitored pipeline runs |
| `HEALTH_CHECK_INTERVAL` | `300` | No | Seconds between automatic health checks |
| `IDLE_TIMEOUT_MINUTES` | `10` | No | Minutes before a run is considered stuck |
| `DISK_WARNING_PERCENT` | `80` | No | Disk usage % to trigger warning alert |
| `DISK_CRITICAL_PERCENT` | `90` | No | Disk usage % to trigger critical alert |
| `BACKUP_DIR` | `/home/factory/backups` | No | Directory for automated and manual backups |

### Translation and Transcription Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `VOICE_PROVIDER` | `auto` | No | Transcription provider: `groq`, `openai`, or `auto` |
| `TRANSLATION_MODEL` | `gpt-4o-mini` | No | Model used for requirement translation |
| `REQUIREMENTS_MODEL` | `gpt-4o-mini` | No | Model used for requirements structuring |

### OpenRouter Rate Limiting Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OPENROUTER_DAILY_LIMIT` | `200` | No | Max daily OpenRouter requests |
| `OPENROUTER_WARN_THRESHOLD` | `0.8` | No | Warn at this fraction of the daily limit (0.0-1.0) |
| `OPENROUTER_BLOCK_THRESHOLD` | `0.95` | No | Block new runs at this fraction of the daily limit |

### Deployment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DOMAIN_NAME` | _(none)_ | No | Registered domain for nginx/SSL configuration |
| `SSL_EMAIL` | _(none)_ | No | Email for certbot SSL certificate registration |
| `LOG_LEVEL` | `INFO` | No | Log verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL |

---

## API Keys Reference

### v1.0 Provider Keys

| Variable | Provider | Free Tier | Used For |
|----------|----------|-----------|---------|
| `GROQ_API_KEY` | Groq | Yes (generous) | Voice transcription via Whisper (primary) |
| `OPENAI_API_KEY` | OpenAI | No | Voice transcription fallback; translation |
| `OPENROUTER_API_KEY` | OpenRouter | Yes (limited) | Access to many free models; translation |
| `GOOGLE_API_KEY` | Google AI Studio | Yes | Gemini engine for factory runs |
| `PERPLEXITY_API_KEY` | Perplexity | No | Research queries during Phase 1 |
| `GITHUB_TOKEN` | GitHub | Yes | Repository creation and management |

### v2.0 Provider Keys

| Variable | Provider | Free Tier | Used For |
|----------|----------|-----------|---------|
| `NVIDIA_API_KEY` | NVIDIA NIM | Yes (limited) | High-performance inference via NIM API |
| `TOGETHER_API_KEY` | Together AI | No | Open model access (Llama, Qwen, etc.) |
| `CEREBRAS_API_KEY` | Cerebras Cloud | Yes (limited) | Ultra-fast inference on Cerebras hardware |
| `SAMBANOVA_API_KEY` | SambaNova Cloud | Yes (limited) | Enterprise open model inference |
| `FIREWORKS_API_KEY` | Fireworks AI | No | Fast open model inference |
| `MISTRAL_API_KEY` | Mistral AI | No | Mistral and Codestral models |

> None of the v2.0 provider keys are required. The factory runs with at minimum a Telegram bot token and admin ID. Providers are used only when their key is configured. At least one AI provider key is required for factory pipeline runs.

---

## Health Monitoring

### Via Telegram

Send `/health` to the bot (admin only). The response includes:
- CPU usage percent
- RAM usage (used / total)
- Disk usage per mount point with warning/critical indicators
- Status of both systemd services (factory-bot, factory-worker)
- PostgreSQL connection status
- Docker daemon status

### Via CLI

```bash
factory health
factory health --json   # Machine-readable JSON output
```

### Automatic Alerts

The health monitor runs every `HEALTH_CHECK_INTERVAL` seconds (default 300). Alerts are sent to the admin Telegram ID when:
- CPU usage exceeds 90% for sustained periods
- RAM usage exceeds 90%
- Disk usage exceeds `DISK_WARNING_PERCENT` (warning) or `DISK_CRITICAL_PERCENT` (critical)
- A factory run has been idle for more than `IDLE_TIMEOUT_MINUTES` minutes

### Checking Service Status

```bash
# Both services
sudo systemctl status factory-bot factory-worker

# Live logs
sudo journalctl -u factory-bot -f
sudo journalctl -u factory-worker -f

# Last 100 lines
sudo journalctl -u factory-bot -n 100
```

---

## Backup and Maintenance

### Automated Backups

Backups are managed by the `backup_service` and run on schedule via the worker. Backup files are stored in `BACKUP_DIR` (default `/home/factory/backups`).

**Cron setup (recommended for production):**
```bash
# Daily database backup at 03:00
0 3 * * * /home/factory/factory-control-bot/artifacts/code/backend/scripts/backup_db.sh >> /home/factory/backups/backup.log 2>&1

# Weekly backup prune (keep last 14 days)
0 4 * * 0 factory backup prune >> /home/factory/backups/prune.log 2>&1
```

### Manual Backup Commands

```bash
# Via CLI
factory backup                   # Create manual backup
factory backup list-backups      # List all backups
factory backup restore <id>      # Restore from backup ID
factory backup prune             # Remove old backups

# Via script directly
./scripts/backup_db.sh

# List backup files
ls -lh /home/factory/backups/db/
```

### Via Telegram

Send `/backup` and use the inline menu to create, list, or restore backups.

### Database Maintenance

```bash
# Vacuum (reclaim space)
psql -U factory -d factory_bot -c "VACUUM ANALYZE;"

# Check database size
psql -U factory -d factory_bot -c "SELECT pg_size_pretty(pg_database_size('factory_bot'));"

# List tables with sizes
psql -U factory -d factory_bot -c "
  SELECT table_name, pg_size_pretty(pg_total_relation_size(table_name::regclass))
  FROM information_schema.tables
  WHERE table_schema = 'public'
  ORDER BY pg_total_relation_size(table_name::regclass) DESC;
"
```

### Log Rotation

Application logs go to stdout (Docker handles rotation automatically). For systemd:
```bash
# Limit journal size
sudo journalctl --vacuum-size=500M

# View journal disk usage
sudo journalctl --disk-usage
```

### Updating the Application

**Docker:**
```bash
git pull
docker compose down
docker compose up -d --build
```

**Manual / systemd:**
```bash
git pull
cd factory-control-bot/artifacts/code/backend
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart factory-bot factory-worker
```

**Via CLI:**
```bash
factory update            # Full update
factory update --engines-only  # Update only engine CLIs
```

---

## Troubleshooting

### Bot Does Not Respond to Messages

1. Confirm the bot token is valid:
   ```bash
   curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
   ```
2. Verify `ADMIN_TELEGRAM_ID` matches your actual Telegram user ID (message [@userinfobot](https://t.me/userinfobot))
3. Check bot logs for auth rejections:
   ```bash
   journalctl -u factory-bot -n 50 | grep "unauthorized\|rejected"
   ```
4. Ensure the bot is not in privacy mode for group chats (use BotFather to disable)

### Database Connection Errors

1. Confirm PostgreSQL is running:
   ```bash
   sudo systemctl status postgresql
   pg_isready -U factory -d factory_bot
   ```
2. Test the connection string directly:
   ```bash
   psql "postgresql://factory:password@localhost:5432/factory_bot" -c "SELECT 1"
   ```
3. Check `pg_hba.conf` allows local md5 connections:
   ```bash
   sudo grep -n "factory\|local" /etc/postgresql/16/main/pg_hba.conf
   ```
4. For Docker: ensure `DATABASE_URL` uses `localhost` (not the container name) because `network_mode: host` is used

### Alembic Migration Failures

Migrations run automatically on startup. If they fail:
1. Check logs for the specific Alembic error
2. Run migrations manually:
   ```bash
   source .venv/bin/activate
   alembic upgrade head
   ```
3. If there is a revision conflict:
   ```bash
   alembic history
   alembic current
   alembic stamp head  # Mark current DB as up to date (use with caution)
   ```

### tmux Session Not Found

Factory runs execute in tmux sessions. If sessions are missing:
1. Verify tmux is installed: `which tmux`
2. List active sessions: `tmux list-sessions`
3. Check the factory user can create sessions:
   ```bash
   sudo -u factory tmux new-session -d -s test && tmux kill-session -t test
   ```
4. If running in Docker, tmux is installed in the container by default

### Docker Socket Permission Denied

The bot mounts `/var/run/docker.sock` for container management:
1. Add the factory user to the docker group:
   ```bash
   sudo usermod -aG docker factory
   # Log out and back in
   ```
2. For Docker deployment, verify the socket mount in `docker-compose.yml`:
   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock
   ```

### Voice Transcription Fails

1. Test the Groq API key:
   ```bash
   curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models
   ```
2. Check the fallback status in logs (3 Groq failures triggers a 5-minute cooldown on Groq, switching to OpenAI)
3. Set `VOICE_PROVIDER=openai` to force OpenAI transcription
4. Ensure the audio file is under 25 MB (Whisper limit)

### Model Provider Errors

1. Run the model scanner to identify working providers:
   ```bash
   factory scan-models --verbose
   ```
   Or via Telegram: `/scan`
2. Check provider-specific API key configuration in `.env`
3. For OpenRouter rate limits, check `OPENROUTER_DAILY_LIMIT` and current usage in `/analytics`
4. Switch routing mode to test a different provider path:
   ```bash
   # Try clink mode (uses local CLI tools)
   export DEFAULT_ROUTING_MODE=clink
   # Try OpenRouter
   export DEFAULT_ROUTING_MODE=openrouter
   ```

### High Memory or CPU Usage

1. Reduce concurrent monitors: set `MAX_CONCURRENT_MONITORS=5` in `.env`
2. Check for runaway log files (256 KB read cap per poll prevents most cases):
   ```bash
   du -sh /home/factory/projects/*/factory.log 2>/dev/null | sort -h
   ```
3. Check Docker resource limits in `docker-compose.yml` (default: 512 MB for bot, 256 MB for postgres)
4. View per-process usage:
   ```bash
   ps aux --sort=-%mem | head -15
   ```

### Self-Research Fails

1. Ensure at least one AI provider is configured (the self-researcher uses the model router)
2. Check that `FACTORY_ROOT_DIR` exists and is readable:
   ```bash
   ls -la $FACTORY_ROOT_DIR
   ```
3. Run with `--dry-run` first to preview changes without applying:
   ```bash
   factory self-research --dry-run
   ```

### Backup Restore Fails

1. List available backups and verify the target backup exists:
   ```bash
   factory backup list-backups
   ls -lh $BACKUP_DIR/
   ```
2. Check PostgreSQL user has restore permissions:
   ```bash
   psql -U factory -d factory_bot -c "\l"
   ```
3. For Docker, restore from inside the postgres container:
   ```bash
   docker compose exec postgres pg_restore -U factory -d factory_bot /backups/backup_name.dump
   ```

### Services Do Not Start After Reboot

1. Verify services are enabled (not just started):
   ```bash
   sudo systemctl is-enabled factory-bot factory-worker
   ```
2. Check for startup ordering issues:
   ```bash
   sudo journalctl -u factory-bot --boot
   ```
3. Confirm PostgreSQL starts before the bot:
   ```bash
   sudo systemctl status postgresql
   sudo systemctl enable postgresql
   ```

---

## Quick Reference

### Service Commands

```bash
# Start / stop / restart both services
sudo systemctl start factory-bot factory-worker
sudo systemctl stop factory-bot factory-worker
sudo systemctl restart factory-bot factory-worker

# View status
sudo systemctl status factory-bot factory-worker

# Live logs
sudo journalctl -u factory-bot -f
sudo journalctl -u factory-worker -f
```

### Docker Commands

```bash
docker compose up -d          # Start all services
docker compose down           # Stop all services
docker compose ps             # Show service status
docker compose logs -f bot    # Tail bot logs
docker compose logs -f worker # Tail worker logs
docker compose restart bot    # Restart bot only
docker compose up -d --build  # Rebuild and restart
```

### Database Commands

```bash
# Connect to DB
psql -U factory -d factory_bot

# Run migrations manually
alembic upgrade head

# Check migration status
alembic current
```

### CLI Quick Reference

```bash
factory run my-project --engine claude
factory status my-project
factory logs my-project --follow
factory health
factory scan-models --verbose
factory backup
factory self-research --dry-run
```
