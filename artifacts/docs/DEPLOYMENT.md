# Deployment Guide — Factory Control Bot v1.0.0

## Prerequisites

### Required Software

| Software | Version | Install (Ubuntu 22.04+) |
|----------|---------|------------------------|
| Python | 3.12+ | `sudo apt install python3.12 python3.12-venv` |
| PostgreSQL | 16+ | `sudo apt install postgresql-16` |
| Docker | 24+ | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose | 2.20+ | Included with Docker |
| tmux | 3.3+ | `sudo apt install tmux` |
| Git | 2.30+ | `sudo apt install git` |

### Required Accounts

| Service | Purpose | Get Token |
|---------|---------|-----------|
| Telegram Bot | Bot API access | [@BotFather](https://t.me/BotFather) |
| Groq | Voice transcription (primary) | [console.groq.com](https://console.groq.com) |
| OpenAI | Voice transcription (fallback) | [platform.openai.com](https://platform.openai.com) |
| OpenRouter | Translation + AI structuring | [openrouter.ai](https://openrouter.ai) |

---

## Option 1: Docker Deployment (Recommended)

### Step 1: Clone and Navigate

```bash
git clone <your-repo-url> factory-control-bot
cd factory-control-bot/artifacts/code/backend
```

### Step 2: Create Environment File

```bash
cat > .env << 'EOF'
# Required
TELEGRAM_BOT_TOKEN=your-bot-token-here
ADMIN_TELEGRAM_ID=your-telegram-id-here

# Database (docker-compose uses network_mode: host, so localhost is correct)
# Replace 'your-db-password' with the POSTGRES_PASSWORD value below
POSTGRES_PASSWORD=change-this-to-a-strong-password
DATABASE_URL=postgresql+asyncpg://factory:change-this-to-a-strong-password@localhost:5432/factory_bot

# API Keys (optional but recommended)
GROQ_API_KEY=your-groq-key
OPENAI_API_KEY=your-openai-key
OPENROUTER_API_KEY=your-openrouter-key
GOOGLE_API_KEY=your-google-key
GITHUB_TOKEN=your-github-token

# Factory
FACTORY_ROOT_DIR=/home/factory/projects

# Logging
LOG_LEVEL=INFO
EOF
```

> **Note:** Alembic database migrations run automatically on first startup. No manual migration step is needed.

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

### Step 5: Verify

```bash
# Check services are running
docker compose ps

# Check bot logs
docker compose logs -f bot

# Check database health
docker compose exec postgres pg_isready -U factory -d factory_bot
```

### Stopping

```bash
docker compose down          # Stop services
docker compose down -v       # Stop and remove volumes (DESTRUCTIVE)
```

---

## Option 2: Manual Deployment

### Step 1: Install System Dependencies

```bash
# Ubuntu 22.04+
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
    postgresql-16 tmux git curl procps
```

### Step 2: Set Up PostgreSQL

```bash
sudo -u postgres createuser factory
sudo -u postgres createdb factory_bot -O factory
sudo -u postgres psql -c "ALTER USER factory PASSWORD 'your-db-password';"
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
ADMIN_TELEGRAM_ID=your-telegram-id
DATABASE_URL=postgresql+asyncpg://factory:your-db-password@localhost:5432/factory_bot
GROQ_API_KEY=your-groq-key
OPENAI_API_KEY=your-openai-key
FACTORY_ROOT_DIR=/home/factory/projects
LOG_LEVEL=INFO
EOF
```

### Step 5: Run

```bash
source .venv/bin/activate
python -m app.main
```

> **Note:** Alembic database migrations run automatically on first startup. All 8 tables are created without manual intervention.

---

## Option 3: VPS Production Deployment

### Step 1: Create System User and Directory Structure

```bash
# Create the factory user
sudo useradd -m -s /bin/bash factory
sudo usermod -aG docker factory

# Create required directories
sudo mkdir -p /home/factory/projects
sudo mkdir -p /home/factory/backups/db
sudo chown -R factory:factory /home/factory

# Switch to factory user
sudo -u factory -i

# Clone the project
git clone <your-repo-url> /home/factory/factory-control-bot
```

### Step 2: Follow Manual Deployment Steps 1-4

(Install system deps, set up PostgreSQL, create venv, configure .env — all as the `factory` user)

> **Note:** Alembic database migrations run automatically on first startup. No manual migration step is needed.

### Step 3: Create systemd Service

```bash
sudo cat > /etc/systemd/system/factory-bot.service << 'EOF'
[Unit]
Description=Factory Control Bot
After=network.target postgresql.service docker.service
Requires=postgresql.service

[Service]
Type=simple
User=factory
Group=factory
WorkingDirectory=/home/factory/factory-control-bot/artifacts/code/backend
Environment=PATH=/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin:/usr/bin:/bin
EnvironmentFile=/home/factory/factory-control-bot/artifacts/code/backend/.env
ExecStart=/home/factory/factory-control-bot/artifacts/code/backend/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable factory-bot
sudo systemctl start factory-bot
```

### Step 3: Configure sudoers for Service Management

```bash
# Allow the factory user to manage specific services without password
sudo visudo -f /etc/sudoers.d/factory-bot
```

Add (restrict to ALLOWED_SERVICES whitelist only):
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

### Step 4: Set Up nginx Reverse Proxy (Optional, for webhook mode)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

sudo cat > /etc/nginx/sites-available/factory-bot << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/factory-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# SSL certificate
sudo certbot --nginx -d your-domain.com --email your-email@example.com --agree-tos
```

### Step 5: Set Up Database Backups

```bash
# Add cron job for daily backups
(crontab -l 2>/dev/null; echo "0 3 * * * /home/factory/factory-control-bot/artifacts/code/backend/scripts/backup_db.sh") | crontab -
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | Telegram Bot API token from @BotFather |
| `ADMIN_TELEGRAM_ID` | **Yes** | — | Admin's Telegram numeric user ID |
| `DATABASE_URL` | No | `postgresql+asyncpg://factory:factory@localhost:5432/factory_bot` | PostgreSQL async connection string |
| `DB_POOL_SIZE` | No | `10` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | No | `5` | Max overflow connections |
| `DB_POOL_RECYCLE` | No | `3600` | Recycle connections after N seconds |
| `GROQ_API_KEY` | No | — | Groq API key for Whisper transcription |
| `OPENAI_API_KEY` | No | — | OpenAI API key for Whisper fallback + translation |
| `OPENROUTER_API_KEY` | No | — | OpenRouter API key for free AI models |
| `GOOGLE_API_KEY` | No | — | Google API key for Gemini engine |
| `PERPLEXITY_API_KEY` | No | — | Perplexity API key for research |
| `GITHUB_TOKEN` | No | — | GitHub token for repo management |
| `FACTORY_ROOT_DIR` | No | `/home/factory/projects` | Root directory for factory projects |
| `TEMPLATES_DIR` | No | `/app/templates` | Engine config templates directory |
| `LOG_POLL_INTERVAL` | No | `3` | Seconds between log file polls |
| `MAX_CONCURRENT_MONITORS` | No | `10` | Max simultaneous monitored runs |
| `HEALTH_CHECK_INTERVAL` | No | `300` | Seconds between health checks |
| `IDLE_TIMEOUT_MINUTES` | No | `10` | Minutes before a run is considered stuck |
| `DEFAULT_ENGINE` | No | `claude` | Default engine for new projects |
| `QUALITY_GATE_THRESHOLD` | No | `97` | Quality gate pass threshold |
| `MAX_FIX_CYCLES` | No | `5` | Max fix cycles in Phase 6 |
| `COST_ALERT_THRESHOLD` | No | `50.0` | Alert when project cost exceeds this |
| `VOICE_PROVIDER` | No | `auto` | Transcription: groq, openai, or auto |
| `LOG_LEVEL` | No | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |

---

## Troubleshooting

### Bot doesn't respond to messages
1. Check bot token: `echo $TELEGRAM_BOT_TOKEN`
2. Verify your Telegram ID matches `ADMIN_TELEGRAM_ID`
3. Check logs: `docker compose logs bot` or `journalctl -u factory-bot -f`

### Database connection errors
1. Check PostgreSQL is running: `systemctl status postgresql`
2. Verify connection string: `psql $DATABASE_URL -c "SELECT 1"`
3. Check pg_hba.conf allows local connections

### tmux session not found
1. Verify tmux is installed: `which tmux`
2. Check running sessions: `tmux list-sessions`
3. Ensure the factory user has permission to create tmux sessions

### Docker socket permission denied
1. Add user to docker group: `sudo usermod -aG docker factory`
2. If using Docker deployment, verify socket mount in docker-compose.yml

### Voice transcription fails
1. Check Groq API key: `curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models`
2. Check OpenAI fallback key is set
3. Review cooldown status in logs (3 Groq failures = 5-min cooldown)

### High memory usage
1. Check `MAX_CONCURRENT_MONITORS` (default 10)
2. Verify no runaway log files (256KB read cap per poll)
3. Review Docker resource limits in docker-compose.yml

---

## Maintenance

### Database Backup
```bash
# Manual backup
./scripts/backup_db.sh

# Backups are stored in /home/factory/backups/db/
ls -la /home/factory/backups/db/
```

### Log Rotation
Application logs go to stdout (Docker handles rotation). For systemd:
```bash
sudo journalctl --vacuum-size=500M
```

### Updating
```bash
git pull
docker compose down && docker compose up -d --build
# Or for manual deployment:
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart factory-bot
```
