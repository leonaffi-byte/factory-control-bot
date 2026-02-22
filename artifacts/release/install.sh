#!/usr/bin/env bash
# Factory Control Bot v2.0 — One-Line VPS Installer
#
# Usage (from a fresh Ubuntu 22.04+ VPS):
#   curl -fsSL https://raw.githubusercontent.com/leonaffi-byte/factory-control-bot/main/artifacts/release/install.sh | bash
#
# What this does:
#   1. Installs system dependencies (Python 3.12, PostgreSQL 16, Docker, tmux, git)
#   2. Creates the 'factory' system user
#   3. Clones the repository
#   4. Sets up Python virtualenv and installs dependencies
#   5. Creates the PostgreSQL database
#   6. Prompts for required config (Telegram token, admin ID)
#   7. Installs both systemd services (factory-bot + factory-worker)
#   8. Starts everything
#
# Requirements:
#   - Ubuntu 22.04+ or Debian 12+ (amd64)
#   - Root or sudo access
#   - Internet connection

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}${BOLD}==> $1${NC}"; }

# ── Config ───────────────────────────────────────────────────────────────────

FACTORY_USER="factory"
FACTORY_HOME="/home/${FACTORY_USER}"
REPO_URL="https://github.com/leonaffi-byte/factory-control-bot.git"
INSTALL_DIR="${FACTORY_HOME}/factory-control-bot"
BACKEND_DIR="${INSTALL_DIR}/artifacts/code/backend"
VENV_DIR="${BACKEND_DIR}/.venv"
DB_NAME="factory_bot"
DB_USER="factory"
DB_PASS="$(openssl rand -hex 16)"

# ── Pre-flight checks ───────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (or with sudo)."
    log_info  "Usage: curl -fsSL <url> | sudo bash"
    exit 1
fi

if ! grep -qiE 'ubuntu|debian' /etc/os-release 2>/dev/null; then
    log_warn "This script is tested on Ubuntu 22.04+ / Debian 12+."
    log_warn "Proceeding anyway — some steps may need manual adjustment."
fi

echo ""
echo -e "${BOLD}Factory Control Bot v2.0 — One-Line Installer${NC}"
echo "================================================"
echo ""

# ── Step 1: System dependencies ─────────────────────────────────────────────

log_step "Step 1/8: Installing system dependencies"

apt-get update -qq
apt-get install -y -qq \
    python3.12 python3.12-venv python3.12-dev \
    postgresql-16 postgresql-client-16 \
    tmux git curl wget gnupg lsb-release \
    build-essential libffi-dev libssl-dev \
    ca-certificates software-properties-common \
    2>/dev/null

# If python3.12 not in default repos, try deadsnakes PPA
if ! command -v python3.12 &>/dev/null; then
    log_info "Adding deadsnakes PPA for Python 3.12..."
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
fi

log_info "System dependencies installed."

# ── Step 2: Install Docker ──────────────────────────────────────────────────

log_step "Step 2/8: Installing Docker"

if command -v docker &>/dev/null; then
    log_info "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
    log_info "Docker installed."
fi

# ── Step 3: Create factory user ─────────────────────────────────────────────

log_step "Step 3/8: Creating factory user"

if id "${FACTORY_USER}" &>/dev/null; then
    log_info "User '${FACTORY_USER}' already exists."
else
    useradd -m -s /bin/bash "${FACTORY_USER}"
    log_info "User '${FACTORY_USER}' created."
fi

usermod -aG docker "${FACTORY_USER}" 2>/dev/null || true

mkdir -p "${FACTORY_HOME}/projects"
mkdir -p "${FACTORY_HOME}/backups/db"
chown -R "${FACTORY_USER}:${FACTORY_USER}" "${FACTORY_HOME}"

# ── Step 4: Clone repository ────────────────────────────────────────────────

log_step "Step 4/8: Cloning repository"

if [[ -d "${INSTALL_DIR}" ]]; then
    log_info "Repository already exists at ${INSTALL_DIR}, pulling latest..."
    sudo -u "${FACTORY_USER}" git -C "${INSTALL_DIR}" pull --ff-only
else
    sudo -u "${FACTORY_USER}" git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

log_info "Repository ready at ${INSTALL_DIR}"

# ── Step 5: Python virtualenv + dependencies ────────────────────────────────

log_step "Step 5/8: Setting up Python environment"

sudo -u "${FACTORY_USER}" python3.12 -m venv "${VENV_DIR}"
sudo -u "${FACTORY_USER}" "${VENV_DIR}/bin/pip" install -q --upgrade pip
sudo -u "${FACTORY_USER}" "${VENV_DIR}/bin/pip" install -q -r "${BACKEND_DIR}/requirements.txt"

# Install the factory CLI
sudo -u "${FACTORY_USER}" "${VENV_DIR}/bin/pip" install -q -e "${BACKEND_DIR}"

log_info "Python environment ready. CLI installed at ${VENV_DIR}/bin/factory"

# ── Step 6: PostgreSQL setup ────────────────────────────────────────────────

log_step "Step 6/8: Setting up PostgreSQL"

systemctl enable postgresql
systemctl start postgresql

# Create user and database (ignore errors if they already exist)
sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || log_info "DB user already exists."
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || log_info "Database already exists."
sudo -u postgres psql -c "ALTER USER ${DB_USER} PASSWORD '${DB_PASS}';" 2>/dev/null || true

log_info "PostgreSQL ready. Database: ${DB_NAME}, User: ${DB_USER}"

# ── Step 7: Configuration ───────────────────────────────────────────────────

log_step "Step 7/8: Configuration"

ENV_FILE="${BACKEND_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
    log_info "Existing .env found — preserving it."
else
    echo ""
    echo -e "${BOLD}Required configuration:${NC}"
    echo ""

    read -rp "  Telegram Bot Token (from @BotFather): " TELEGRAM_TOKEN
    read -rp "  Your Telegram User ID (numeric):      " ADMIN_ID

    if [[ -z "${TELEGRAM_TOKEN}" || -z "${ADMIN_ID}" ]]; then
        log_error "Both TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_ID are required."
        log_info  "You can set them later in ${ENV_FILE}"
        TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-CHANGE_ME}"
        ADMIN_ID="${ADMIN_ID:-0}"
    fi

    cat > "${ENV_FILE}" << ENVEOF
# Factory Control Bot v2.0 — Generated by installer
# $(date -Iseconds)

# Required
TELEGRAM_BOT_TOKEN=${TELEGRAM_TOKEN}
ADMIN_TELEGRAM_ID=${ADMIN_ID}

# Database (auto-generated password)
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}

# Directories
FACTORY_ROOT_DIR=${FACTORY_HOME}/projects
BACKUP_DIR=${FACTORY_HOME}/backups

# API Keys (add as needed — all optional)
# GROQ_API_KEY=
# OPENAI_API_KEY=
# OPENROUTER_API_KEY=
# GOOGLE_API_KEY=
# NVIDIA_API_KEY=
# TOGETHER_API_KEY=
# CEREBRAS_API_KEY=
# SAMBANOVA_API_KEY=
# FIREWORKS_API_KEY=
# MISTRAL_API_KEY=
# PERPLEXITY_API_KEY=
# GITHUB_TOKEN=

# Defaults
LOG_LEVEL=INFO
DEFAULT_ENGINE=claude
DEFAULT_ROUTING_MODE=api_direct
ENVEOF

    chown "${FACTORY_USER}:${FACTORY_USER}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    log_info ".env created at ${ENV_FILE}"
fi

# ── Step 8: systemd services ────────────────────────────────────────────────

log_step "Step 8/8: Installing systemd services"

# factory-bot.service
cat > /etc/systemd/system/factory-bot.service << SVCEOF
[Unit]
Description=Factory Control Bot (Telegram + CLI)
After=network.target postgresql.service docker.service
Requires=postgresql.service

[Service]
Type=simple
User=${FACTORY_USER}
Group=${FACTORY_USER}
WorkingDirectory=${BACKEND_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python -m app.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

# factory-worker.service
cat > /etc/systemd/system/factory-worker.service << SVCEOF
[Unit]
Description=Factory Worker (Background Tasks)
After=network.target postgresql.service factory-bot.service
Requires=postgresql.service

[Service]
Type=simple
User=${FACTORY_USER}
Group=${FACTORY_USER}
WorkingDirectory=${BACKEND_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python -m app.worker
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

# Sudoers for service management
cat > /etc/sudoers.d/factory-bot << SUDOEOF
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart factory-bot
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart factory-worker
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart docker
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart postgresql
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl status factory-bot
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl status factory-worker
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl status docker
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl status nginx
${FACTORY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl status postgresql
SUDOEOF
chmod 440 /etc/sudoers.d/factory-bot

# Daily backup cron
(sudo -u "${FACTORY_USER}" crontab -l 2>/dev/null; echo "0 3 * * * ${VENV_DIR}/bin/factory backup --type scheduled 2>&1 | logger -t factory-backup") | sudo -u "${FACTORY_USER}" crontab -

systemctl daemon-reload
systemctl enable factory-bot factory-worker
systemctl start factory-bot factory-worker

log_info "Services installed and started."

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "================================================"
echo -e "${GREEN}${BOLD}Installation complete!${NC}"
echo "================================================"
echo ""
echo "  Services:"
echo "    systemctl status factory-bot"
echo "    systemctl status factory-worker"
echo ""
echo "  Logs:"
echo "    journalctl -u factory-bot -f"
echo "    journalctl -u factory-worker -f"
echo ""
echo "  CLI (as factory user):"
echo "    sudo -u ${FACTORY_USER} -i"
echo "    factory --help"
echo ""
echo "  Config:"
echo "    ${ENV_FILE}"
echo ""
echo "  Next steps:"
echo "    1. Harden your VPS: sudo bash ${INSTALL_DIR}/artifacts/release/secure.sh"
echo "    2. Send /start to your bot on Telegram"
echo "    3. Add API keys to .env for more providers"
echo "    4. Run: factory scan-models"
echo ""
echo -e "  DB password (save this): ${YELLOW}${DB_PASS}${NC}"
echo ""
