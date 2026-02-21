#!/usr/bin/env bash
# Factory Control Bot v2.0 — One-Command Deployment Script
#
# Usage:
#   ./deploy.sh [docker|manual|install]
#
#   docker   — Start with Docker Compose (bot + worker + PostgreSQL)
#   manual   — Set up venv and run both services directly
#   install  — Full VPS setup: postgres, python, engines, docker, systemd services
#
# Examples:
#   ./deploy.sh              # defaults to docker mode
#   ./deploy.sh docker
#   ./deploy.sh manual
#   ./deploy.sh install

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ARTIFACTS_DIR/code/backend"
VENV_DIR="$BACKEND_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
FACTORY_BIN="$VENV_DIR/bin/factory"
FACTORY_USER="${FACTORY_USER:-factory}"
INSTALL_DIR="${INSTALL_DIR:-/home/factory/factory-control-bot}"
PROJECTS_DIR="${FACTORY_ROOT_DIR:-/home/factory/projects}"
BACKUP_DIR="${BACKUP_DIR:-/home/factory/backups}"
SERVICE_BOT="factory-bot"
SERVICE_WORKER="factory-worker"

# ── Colours ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${BOLD}${BLUE}==> $1${NC}"; }
log_ok()      { echo -e "${GREEN}  OK${NC}  $1"; }
log_missing() { echo -e "${RED}  MISSING${NC}  $1"; }

# ── Prerequisite Checks ───────────────────────────────────────────────────────

check_common_prereqs() {
    log_section "Checking common prerequisites"
    local missing=0

    for cmd in python3 git tmux curl; do
        if command -v "$cmd" &>/dev/null; then
            log_ok "$cmd ($(command -v "$cmd"))"
        else
            log_missing "$cmd"
            missing=1
        fi
    done

    # Python version check (require 3.12+)
    if command -v python3 &>/dev/null; then
        local pyver
        pyver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"; then
            log_ok "Python $pyver >= 3.12"
        else
            log_error "Python $pyver is below required 3.12"
            log_info "Install: sudo apt install python3.12 python3.12-venv"
            missing=1
        fi
    fi

    if [ "$missing" -eq 1 ]; then
        log_error "Install missing prerequisites and retry."
        exit 1
    fi
}

check_docker_prereqs() {
    log_section "Checking Docker prerequisites"
    local missing=0

    if command -v docker &>/dev/null; then
        log_ok "docker ($(docker --version | head -1))"
    else
        log_missing "docker"
        log_info "Install: curl -fsSL https://get.docker.com | sh"
        missing=1
    fi

    if docker compose version &>/dev/null 2>&1; then
        log_ok "docker compose ($(docker compose version --short 2>/dev/null || echo 'installed'))"
    else
        log_missing "docker compose plugin"
        log_info "Upgrade Docker to 24+ which includes compose as a plugin."
        missing=1
    fi

    if [ "$missing" -eq 1 ]; then
        log_error "Install missing Docker prerequisites and retry."
        exit 1
    fi
}

check_manual_prereqs() {
    log_section "Checking manual deployment prerequisites"

    if command -v psql &>/dev/null; then
        log_ok "psql ($(psql --version | head -1))"
    else
        log_warn "psql not found — ensure PostgreSQL is running and DATABASE_URL is configured"
    fi

    if command -v python3.12 &>/dev/null; then
        log_ok "python3.12"
    else
        log_warn "python3.12 not found, using python3 ($(python3 --version))"
    fi
}

# ── Environment Validation ────────────────────────────────────────────────────

check_env() {
    log_section "Validating environment configuration"

    if [ ! -f "$BACKEND_DIR/.env" ]; then
        log_error ".env file not found at $BACKEND_DIR/.env"
        log_info "Create it from the template:"
        log_info "  cat > $BACKEND_DIR/.env << 'EOF'"
        log_info "  TELEGRAM_BOT_TOKEN=your-bot-token"
        log_info "  ADMIN_TELEGRAM_ID=your-telegram-id"
        log_info "  DATABASE_URL=postgresql+asyncpg://factory:password@localhost:5432/factory_bot"
        log_info "  EOF"
        exit 1
    fi

    # shellcheck source=/dev/null
    source "$BACKEND_DIR/.env"

    local missing=0

    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        log_error "TELEGRAM_BOT_TOKEN is not set in .env"
        missing=1
    else
        log_ok "TELEGRAM_BOT_TOKEN is set"
    fi

    if [ -z "${ADMIN_TELEGRAM_ID:-}" ]; then
        log_error "ADMIN_TELEGRAM_ID is not set in .env"
        missing=1
    else
        log_ok "ADMIN_TELEGRAM_ID=$ADMIN_TELEGRAM_ID"
    fi

    if [ -z "${DATABASE_URL:-}" ]; then
        log_warn "DATABASE_URL not set — will use default (postgresql+asyncpg://factory:factory@localhost:5432/factory_bot)"
    else
        log_ok "DATABASE_URL is set"
    fi

    # Check at least one AI provider key is configured
    local provider_keys=(
        GROQ_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY GOOGLE_API_KEY
        NVIDIA_API_KEY TOGETHER_API_KEY CEREBRAS_API_KEY SAMBANOVA_API_KEY
        FIREWORKS_API_KEY MISTRAL_API_KEY
    )
    local has_provider=0
    for key in "${provider_keys[@]}"; do
        if [ -n "${!key:-}" ]; then
            has_provider=1
            break
        fi
    done
    if [ "$has_provider" -eq 0 ]; then
        log_warn "No AI provider API keys configured. Pipeline runs require at least one provider key."
    else
        log_ok "At least one AI provider key is configured"
    fi

    if [ "$missing" -eq 1 ]; then
        log_error "Fix required environment variables and retry."
        exit 1
    fi

    log_info "Environment configuration OK."
}

# ── Directory Setup ───────────────────────────────────────────────────────────

setup_directories() {
    log_section "Setting up required directories"

    local dirs=("$PROJECTS_DIR" "$BACKUP_DIR/db")
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            if sudo mkdir -p "$dir" 2>/dev/null; then
                sudo chown -R "$(whoami):$(whoami)" "$(echo "$dir" | cut -d'/' -f1-3)" 2>/dev/null || true
                log_ok "Created $dir"
            else
                mkdir -p "$dir" 2>/dev/null && log_ok "Created $dir" || log_warn "Could not create $dir (may need sudo)"
            fi
        else
            log_ok "Exists: $dir"
        fi
    done
}

# ── Virtual Environment ───────────────────────────────────────────────────────

setup_venv() {
    log_section "Setting up Python virtual environment"

    local python_cmd
    if command -v python3.12 &>/dev/null; then
        python_cmd="python3.12"
    else
        python_cmd="python3"
    fi

    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating virtualenv with $python_cmd..."
        "$python_cmd" -m venv "$VENV_DIR"
        log_ok "Virtualenv created at $VENV_DIR"
    else
        log_ok "Virtualenv already exists at $VENV_DIR"
    fi

    log_info "Installing dependencies..."
    "$PIP_BIN" install -q --upgrade pip
    "$PIP_BIN" install -q -r "$BACKEND_DIR/requirements.txt"
    log_ok "Dependencies installed"

    if [ ! -f "$FACTORY_BIN" ]; then
        log_info "Installing factory CLI..."
        "$PIP_BIN" install -q -e "$BACKEND_DIR"
        log_ok "factory CLI installed"
    fi
}

# ── Docker Mode ───────────────────────────────────────────────────────────────

deploy_docker() {
    log_section "Docker Compose Deployment"

    check_docker_prereqs
    setup_directories

    cd "$BACKEND_DIR"

    log_info "Building and starting services (bot + worker + postgres)..."
    docker compose up -d --build

    log_info "Waiting for services to initialise (15s)..."
    sleep 15

    local failed=0
    for svc in postgres bot worker; do
        if docker compose ps "$svc" 2>/dev/null | grep -q "running\|Up"; then
            log_ok "$svc is running"
        else
            log_error "$svc failed to start"
            docker compose logs "$svc" --tail=20
            failed=1
        fi
    done

    if [ "$failed" -eq 1 ]; then
        log_error "One or more services failed to start. Check logs above."
        exit 1
    fi

    echo ""
    log_info "Deployment successful!"
    log_info "Tail bot logs:    docker compose logs -f bot"
    log_info "Tail worker logs: docker compose logs -f worker"
    log_info "Stop services:    docker compose down"
}

# ── Manual Mode ───────────────────────────────────────────────────────────────

deploy_manual() {
    log_section "Manual Deployment"

    check_manual_prereqs
    setup_directories
    setup_venv

    echo ""
    log_info "Starting services in background via tmux..."

    # Create a tmux session for each service if tmux is available
    if command -v tmux &>/dev/null; then
        # Kill existing sessions if present
        tmux kill-session -t factory-bot 2>/dev/null || true
        tmux kill-session -t factory-worker 2>/dev/null || true

        tmux new-session -d -s factory-bot \
            "cd $BACKEND_DIR && source .venv/bin/activate && python -m app.main; echo 'Bot exited. Press enter.'; read"
        log_ok "factory-bot started in tmux session 'factory-bot'"

        tmux new-session -d -s factory-worker \
            "cd $BACKEND_DIR && source .venv/bin/activate && python -m app.worker; echo 'Worker exited. Press enter.'; read"
        log_ok "factory-worker started in tmux session 'factory-worker'"

        echo ""
        log_info "Attach to bot:    tmux attach -t factory-bot"
        log_info "Attach to worker: tmux attach -t factory-worker"
        log_info "List sessions:    tmux list-sessions"
        log_info "Kill services:    tmux kill-session -t factory-bot; tmux kill-session -t factory-worker"
        log_info ""
        log_warn "Database migrations run automatically on first bot startup."
        log_warn "For production, use the 'install' mode to set up systemd services."
    else
        log_warn "tmux not found — starting bot in foreground."
        log_warn "Run factory-worker in a separate terminal:"
        log_warn "  source $VENV_DIR/bin/activate && python -m app.worker"
        echo ""
        cd "$BACKEND_DIR"
        source "$VENV_DIR/bin/activate"
        python -m app.main
    fi
}

# ── Install Mode (Full VPS Setup) ─────────────────────────────────────────────

deploy_install() {
    log_section "Full VPS Installation — Factory Control Bot v2.0"

    log_info "This will:"
    log_info "  1. Set up PostgreSQL and create the factory database"
    log_info "  2. Create a Python virtualenv and install requirements"
    log_info "  3. Install engine CLIs (claude, gemini, aider, opencode)"
    log_info "  4. Install Docker if not present"
    log_info "  5. Create and enable systemd services (factory-bot + factory-worker)"
    echo ""

    # Step 1: PostgreSQL
    log_section "Step 1: PostgreSQL"
    if command -v pg_isready &>/dev/null && pg_isready -q 2>/dev/null; then
        log_ok "PostgreSQL is running"
    elif command -v apt-get &>/dev/null; then
        log_info "Installing PostgreSQL 16..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq postgresql-16 postgresql-client-16
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
        log_ok "PostgreSQL installed and started"
    else
        log_warn "Cannot auto-install PostgreSQL on this OS. Install manually."
    fi

    # Create DB user and database
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='factory'" 2>/dev/null | grep -q 1; then
        log_ok "PostgreSQL user 'factory' already exists"
    else
        # shellcheck source=/dev/null
        source "$BACKEND_DIR/.env" 2>/dev/null || true
        local db_pass="${POSTGRES_PASSWORD:-factory_secret}"
        sudo -u postgres psql -c "CREATE USER factory WITH PASSWORD '$db_pass';" 2>/dev/null && \
            log_ok "Created PostgreSQL user 'factory'" || log_warn "Could not create user (may already exist)"
        sudo -u postgres psql -c "CREATE DATABASE factory_bot OWNER factory;" 2>/dev/null && \
            log_ok "Created database 'factory_bot'" || log_warn "Could not create DB (may already exist)"
    fi

    # Step 2: Python + venv
    if ! command -v python3.12 &>/dev/null; then
        log_section "Step 2: Python 3.12"
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip
            log_ok "Python 3.12 installed"
        else
            log_warn "Cannot auto-install Python 3.12 on this OS. Install manually."
        fi
    else
        log_ok "Python 3.12 already installed"
    fi

    setup_directories
    setup_venv

    # Step 3: Engine CLIs
    log_section "Step 3: Engine CLIs"

    if command -v npm &>/dev/null; then
        if ! command -v claude &>/dev/null; then
            log_info "Installing Claude CLI..."
            npm install -g @anthropic-ai/claude-code 2>/dev/null && log_ok "claude installed" || log_warn "claude install failed (may require auth)"
        else
            log_ok "claude already installed"
        fi
    else
        log_warn "npm not found — skipping Claude CLI install. Install Node.js first: https://nodejs.org"
    fi

    if command -v pip3 &>/dev/null || command -v pip &>/dev/null; then
        if ! command -v aider &>/dev/null; then
            log_info "Installing Aider..."
            "$PIP_BIN" install -q aider-chat && log_ok "aider installed" || log_warn "aider install failed"
        else
            log_ok "aider already installed"
        fi
    fi

    if command -v gem &>/dev/null; then
        if ! command -v opencode &>/dev/null; then
            log_info "Checking for opencode..."
            log_warn "opencode install not automated. See: https://opencode.ai"
        fi
    fi

    log_info "At least one engine must be available. Install missing engines manually if needed."

    # Step 4: Docker
    log_section "Step 4: Docker"
    if command -v docker &>/dev/null; then
        log_ok "Docker already installed ($(docker --version | head -1))"
    elif command -v apt-get &>/dev/null; then
        log_info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$FACTORY_USER"
        sudo systemctl enable docker
        sudo systemctl start docker
        log_ok "Docker installed"
        log_warn "Log out and back in for docker group membership to take effect"
    else
        log_warn "Cannot auto-install Docker on this OS. See: https://docs.docker.com/get-docker/"
    fi

    # Step 5: systemd services
    log_section "Step 5: systemd Services"

    local working_dir="$BACKEND_DIR"
    local venv_python="$PYTHON_BIN"

    # factory-bot.service
    sudo tee /etc/systemd/system/factory-bot.service > /dev/null << UNIT
[Unit]
Description=Factory Control Bot -- Telegram Bot Service
After=network.target postgresql.service docker.service
Requires=postgresql.service

[Service]
Type=simple
User=$FACTORY_USER
Group=$FACTORY_USER
WorkingDirectory=$working_dir
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$working_dir/.env
ExecStart=$venv_python -m app.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=factory-bot

[Install]
WantedBy=multi-user.target
UNIT
    log_ok "Created /etc/systemd/system/factory-bot.service"

    # factory-worker.service
    sudo tee /etc/systemd/system/factory-worker.service > /dev/null << UNIT
[Unit]
Description=Factory Control Bot -- Background Worker Service
After=network.target postgresql.service factory-bot.service
Requires=postgresql.service

[Service]
Type=simple
User=$FACTORY_USER
Group=$FACTORY_USER
WorkingDirectory=$working_dir
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$working_dir/.env
ExecStart=$venv_python -m app.worker
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=factory-worker

[Install]
WantedBy=multi-user.target
UNIT
    log_ok "Created /etc/systemd/system/factory-worker.service"

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_BOT" "$SERVICE_WORKER"
    log_ok "Services enabled (will start on boot)"

    # Start if .env is present and valid
    if [ -f "$BACKEND_DIR/.env" ]; then
        sudo systemctl start "$SERVICE_BOT" "$SERVICE_WORKER" && \
            log_ok "Services started" || log_warn "Services failed to start — check: journalctl -u factory-bot"
    else
        log_warn ".env not found — configure $BACKEND_DIR/.env before starting services:"
        log_warn "  sudo systemctl start factory-bot factory-worker"
    fi

    # Sudoers for service management via Telegram /services
    log_section "Configuring sudoers for service management"
    local sudoers_file="/etc/sudoers.d/factory-bot"
    sudo tee "$sudoers_file" > /dev/null << SUDOERS
# Factory Control Bot — allow factory user to manage whitelisted services
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart docker
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart postgresql
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart tailscaled
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart fail2ban
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status docker
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status nginx
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status postgresql
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status tailscaled
$FACTORY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status fail2ban
SUDOERS
    sudo chmod 0440 "$sudoers_file"
    log_ok "Sudoers configured at $sudoers_file"

    # Automated backup cron
    log_section "Setting up automated backups"
    (crontab -l 2>/dev/null | grep -v backup_db.sh; echo "0 3 * * * $BACKEND_DIR/scripts/backup_db.sh >> $BACKUP_DIR/backup.log 2>&1") | crontab -
    log_ok "Daily backup cron job added (03:00 every day)"

    echo ""
    log_section "Installation Complete"
    log_info "Services:     sudo systemctl status factory-bot factory-worker"
    log_info "Bot logs:     sudo journalctl -u factory-bot -f"
    log_info "Worker logs:  sudo journalctl -u factory-worker -f"
    log_info "CLI:          $FACTORY_BIN --help"
    log_info ""
    log_warn "If .env was not present during install, create it then start services:"
    log_warn "  sudo systemctl start factory-bot factory-worker"
}

# ── Version Info ──────────────────────────────────────────────────────────────

print_header() {
    echo -e "${BOLD}Factory Control Bot v2.0.0 — Deployment Script${NC}"
    echo -e "Mode: ${BOLD}$MODE${NC}"
    echo -e "Backend: $BACKEND_DIR"
    echo ""
}

# ── Entry Point ───────────────────────────────────────────────────────────────

MODE="${1:-docker}"

print_header

case "$MODE" in
    docker)
        check_common_prereqs
        check_env
        deploy_docker
        ;;
    manual)
        check_common_prereqs
        check_env
        deploy_manual
        ;;
    install)
        check_common_prereqs
        deploy_install
        ;;
    *)
        log_error "Unknown mode: '$MODE'"
        echo ""
        echo "Usage: $0 [docker|manual|install]"
        echo ""
        echo "  docker   Start with Docker Compose (bot + worker + PostgreSQL)"
        echo "  manual   Set up venv and run both services via tmux"
        echo "  install  Full VPS setup: postgres, venv, engines, docker, systemd"
        exit 1
        ;;
esac

echo ""
log_info "Done. Send /start to your bot on Telegram."
