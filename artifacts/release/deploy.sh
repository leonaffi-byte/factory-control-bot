#!/usr/bin/env bash
set -euo pipefail

# Factory Control Bot — One-Command Deployment Script
# Usage: ./deploy.sh [docker|manual]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/code/backend"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prereqs() {
    log_info "Checking prerequisites..."
    local missing=0

    # Common prerequisites
    for cmd in python3 tmux git; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "Missing: $cmd"
            missing=1
        fi
    done

    # Mode-specific prerequisites
    if [ "${MODE:-docker}" = "docker" ]; then
        if ! command -v docker &>/dev/null; then
            log_error "Missing: docker (run: curl -fsSL https://get.docker.com | sh)"
            missing=1
        fi
        if ! docker compose version &>/dev/null 2>&1; then
            log_error "Missing: docker compose plugin"
            missing=1
        fi
    else
        if ! command -v psql &>/dev/null; then
            log_warn "psql not found — ensure PostgreSQL is running and accessible"
        fi
    fi

    if [ "$missing" -eq 1 ]; then
        log_error "Install missing prerequisites and retry."
        exit 1
    fi

    log_info "All prerequisites found."
}

check_env() {
    if [ ! -f "$BACKEND_DIR/.env" ]; then
        log_error "No .env file found at $BACKEND_DIR/.env"
        log_info "Copy .env.example and fill in your values:"
        log_info "  cp $BACKEND_DIR/.env.example $BACKEND_DIR/.env"
        exit 1
    fi

    # Source and check required vars
    source "$BACKEND_DIR/.env"
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        log_error "TELEGRAM_BOT_TOKEN not set in .env"
        exit 1
    fi
    if [ -z "${ADMIN_TELEGRAM_ID:-}" ]; then
        log_error "ADMIN_TELEGRAM_ID not set in .env"
        exit 1
    fi

    log_info "Environment configuration OK."
}

deploy_docker() {
    log_info "Deploying with Docker Compose..."

    if ! command -v docker &>/dev/null; then
        log_error "Docker not installed. Run: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi

    # Create required directories
    sudo mkdir -p /home/factory/projects
    sudo mkdir -p /home/factory/backups/db
    sudo chown -R "$(whoami):$(whoami)" /home/factory

    cd "$BACKEND_DIR"
    docker compose up -d --build

    log_info "Waiting for services to start..."
    sleep 10

    if docker compose ps | grep -q "running"; then
        log_info "Deployment successful!"
        log_info "Check logs: docker compose logs -f bot"
    else
        log_error "Some services failed to start."
        docker compose logs
        exit 1
    fi
}

deploy_manual() {
    log_info "Deploying manually..."

    cd "$BACKEND_DIR"

    # Create venv if needed
    if [ ! -d ".venv" ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv .venv
    fi

    source .venv/bin/activate

    log_info "Installing dependencies..."
    pip install -q -r requirements.txt

    # Create required directories
    mkdir -p /home/factory/projects

    log_info "Starting bot (foreground — press Ctrl+C to stop)..."
    log_info "For production, use systemd: see DEPLOYMENT.md Option 3"
    log_info "Database migrations will run automatically on first startup."
    python -m app.main
}

# Main
MODE="${1:-docker}"

log_info "Factory Control Bot — Deployment"
log_info "Mode: $MODE"
echo ""

check_prereqs
check_env

case "$MODE" in
    docker)
        deploy_docker
        ;;
    manual)
        deploy_manual
        ;;
    *)
        log_error "Unknown mode: $MODE"
        log_info "Usage: $0 [docker|manual]"
        exit 1
        ;;
esac

echo ""
log_info "Done! Send /start to your bot on Telegram."
