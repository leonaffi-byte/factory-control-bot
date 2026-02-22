#!/usr/bin/env bash
# Factory Control Bot v2.0 — VPS Security Hardening
#
# Usage (after install.sh):
#   sudo bash artifacts/release/secure.sh
#
# Or standalone:
#   curl -fsSL https://raw.githubusercontent.com/leonaffi-byte/factory-control-bot/main/artifacts/release/secure.sh | sudo bash
#
# Skip specific steps:
#   sudo bash secure.sh --skip-tailscale --skip-ssh-port --skip-docker-harden
#
# What this does:
#   1. System updates + unattended-upgrades
#   2. SSH hardening (key-only, MaxAuthTries 3, optional port change)
#   3. UFW firewall (default deny, allow SSH + HTTP/HTTPS + Tailscale)
#   4. fail2ban (SSH jail, maxretry=5, bantime=1h)
#   5. Tailscale (install, authenticate, optional SSH-only via Tailscale)
#   6. Kernel hardening (sysctl: SYN cookies, no redirects, reverse path filter)
#   7. Shared memory hardening (/run/shm nosuid,noexec,nodev)
#   8. Automatic security updates (unattended-upgrades config)
#   9. Docker hardening (log driver, container caps)
#  10. Summary report
#
# Non-destructive: backs up all config files before modifying.

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

# ── Skip Flags ───────────────────────────────────────────────────────────────

SKIP_UPDATES=false
SKIP_SSH=false
SKIP_SSH_PORT=false
SKIP_UFW=false
SKIP_FAIL2BAN=false
SKIP_TAILSCALE=false
SKIP_KERNEL=false
SKIP_SHM=false
SKIP_UNATTENDED=false
SKIP_DOCKER_HARDEN=false

for arg in "$@"; do
    case "$arg" in
        --skip-updates)        SKIP_UPDATES=true ;;
        --skip-ssh)            SKIP_SSH=true ;;
        --skip-ssh-port)       SKIP_SSH_PORT=true ;;
        --skip-ufw)            SKIP_UFW=true ;;
        --skip-fail2ban)       SKIP_FAIL2BAN=true ;;
        --skip-tailscale)      SKIP_TAILSCALE=true ;;
        --skip-kernel)         SKIP_KERNEL=true ;;
        --skip-shm)            SKIP_SHM=true ;;
        --skip-unattended)     SKIP_UNATTENDED=true ;;
        --skip-docker-harden)  SKIP_DOCKER_HARDEN=true ;;
        --help|-h)
            echo "Usage: sudo bash secure.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-updates        Skip system updates"
            echo "  --skip-ssh            Skip all SSH hardening"
            echo "  --skip-ssh-port       Skip SSH port change (keep 22)"
            echo "  --skip-ufw            Skip UFW firewall setup"
            echo "  --skip-fail2ban       Skip fail2ban installation"
            echo "  --skip-tailscale      Skip Tailscale installation"
            echo "  --skip-kernel         Skip kernel sysctl hardening"
            echo "  --skip-shm            Skip shared memory hardening"
            echo "  --skip-unattended     Skip unattended-upgrades config"
            echo "  --skip-docker-harden  Skip Docker daemon hardening"
            echo "  -h, --help            Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $arg"
            log_info  "Run with --help to see available options."
            exit 1
            ;;
    esac
done

# ── Pre-flight checks ───────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (or with sudo)."
    exit 1
fi

if ! grep -qiE 'ubuntu|debian' /etc/os-release 2>/dev/null; then
    log_warn "This script is tested on Ubuntu 22.04+ / Debian 12+."
    log_warn "Proceeding anyway — some steps may need manual adjustment."
fi

FACTORY_USER="factory"
SSH_PORT=22
CHANGES_MADE=()

echo ""
echo -e "${BOLD}Factory Control Bot v2.0 — Security Hardening${NC}"
echo "================================================"
echo ""

# ── Helper: backup a file before modifying ───────────────────────────────────

backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        local backup="${file}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$file" "$backup"
        log_info "Backed up $file -> $backup"
    fi
}

# ── Step 1: System Updates ───────────────────────────────────────────────────

step_updates() {
    log_step "Step 1/10: System updates"

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
    apt-get install -y -qq apt-transport-https ca-certificates curl software-properties-common 2>/dev/null

    CHANGES_MADE+=("System packages updated")
    log_info "System updated."
}

# ── Step 2: SSH Hardening ────────────────────────────────────────────────────

step_ssh() {
    log_step "Step 2/10: SSH hardening"

    local sshd_config="/etc/ssh/sshd_config"
    backup_file "$sshd_config"

    # Safety check: if no authorized_keys exist for any user, do NOT disable password auth
    local has_keys=false
    for home_dir in /root /home/*; do
        if [[ -f "${home_dir}/.ssh/authorized_keys" ]] && [[ -s "${home_dir}/.ssh/authorized_keys" ]]; then
            has_keys=true
            break
        fi
    done

    if [[ "$has_keys" == false ]]; then
        log_warn "No SSH authorized_keys found for any user!"
        log_warn "Skipping password auth disable to prevent lockout."
        log_warn "Add your SSH public key first, then re-run this script."
    fi

    # Build hardened sshd_config drop-in to avoid breaking the main config
    local dropin_dir="/etc/ssh/sshd_config.d"
    mkdir -p "$dropin_dir"

    local dropin_file="${dropin_dir}/99-factory-hardening.conf"
    backup_file "$dropin_file"

    cat > "$dropin_file" << 'SSHEOF'
# Factory Control Bot — SSH Hardening
# Generated by secure.sh

# Disable root login
PermitRootLogin no

# Limit auth attempts
MaxAuthTries 3
LoginGraceTime 30

# Disable unused auth methods
KbdInteractiveAuthentication no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no

# Only allow the factory user and root (for initial setup)
# Uncomment and adjust if you have other users:
# AllowUsers factory youruser
SSHEOF

    # Disable password auth only if keys exist
    if [[ "$has_keys" == true ]]; then
        cat >> "$dropin_file" << 'SSHEOF'

# Key-only authentication (password auth disabled)
PasswordAuthentication no
PubkeyAuthentication yes
SSHEOF
        CHANGES_MADE+=("SSH: password auth disabled (key-only)")
    else
        cat >> "$dropin_file" << 'SSHEOF'

# Password auth kept ENABLED (no authorized_keys found)
# Re-run secure.sh after adding SSH keys to disable password auth
PasswordAuthentication yes
PubkeyAuthentication yes
SSHEOF
        CHANGES_MADE+=("SSH: password auth kept (no keys found)")
    fi

    # Optional SSH port change
    if [[ "$SKIP_SSH_PORT" == false ]]; then
        echo ""
        read -rp "  Change SSH port from 22? Enter new port (or press Enter to keep 22): " new_port
        if [[ -n "$new_port" ]] && [[ "$new_port" =~ ^[0-9]+$ ]] && [[ "$new_port" -ge 1024 ]] && [[ "$new_port" -le 65535 ]]; then
            echo "" >> "$dropin_file"
            echo "# Custom SSH port" >> "$dropin_file"
            echo "Port ${new_port}" >> "$dropin_file"
            SSH_PORT="$new_port"
            CHANGES_MADE+=("SSH: port changed to ${new_port}")
            log_info "SSH port will be ${new_port}."
        elif [[ -n "$new_port" ]]; then
            log_warn "Invalid port '${new_port}' (must be 1024-65535). Keeping port 22."
        else
            log_info "Keeping SSH on port 22."
        fi
    fi

    # Validate config before restarting
    if sshd -t 2>/dev/null; then
        systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || true
        CHANGES_MADE+=("SSH: root login disabled, MaxAuthTries=3, LoginGraceTime=30")
        log_info "SSH hardened and reloaded."
    else
        log_error "sshd config validation failed! Reverting..."
        rm -f "$dropin_file"
        log_warn "SSH hardening reverted. Check your sshd_config manually."
    fi
}

# ── Step 3: UFW Firewall ─────────────────────────────────────────────────────

step_ufw() {
    log_step "Step 3/10: UFW firewall"

    apt-get install -y -qq ufw 2>/dev/null

    # Reset to clean state (non-interactive)
    ufw --force reset >/dev/null 2>&1

    # Default policies
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null

    # Allow SSH (current port — critical to not lock ourselves out)
    ufw allow "${SSH_PORT}/tcp" comment "SSH" >/dev/null
    log_info "Allowed SSH on port ${SSH_PORT}/tcp"

    # Allow HTTP/HTTPS for nginx (if installed or planned)
    ufw allow 80/tcp comment "HTTP" >/dev/null
    ufw allow 443/tcp comment "HTTPS" >/dev/null
    log_info "Allowed HTTP (80) and HTTPS (443)"

    # Allow Tailscale WireGuard port
    ufw allow 41641/udp comment "Tailscale" >/dev/null
    log_info "Allowed Tailscale (41641/udp)"

    # Enable UFW (non-interactive)
    ufw --force enable >/dev/null

    CHANGES_MADE+=("UFW: enabled, default deny, allowed SSH/${SSH_PORT} HTTP HTTPS Tailscale")
    log_info "UFW firewall enabled."
}

# ── Step 4: fail2ban ─────────────────────────────────────────────────────────

step_fail2ban() {
    log_step "Step 4/10: fail2ban"

    apt-get install -y -qq fail2ban 2>/dev/null

    local jail_local="/etc/fail2ban/jail.local"
    backup_file "$jail_local"

    cat > "$jail_local" << JAILEOF
# Factory Control Bot — fail2ban config
# Generated by secure.sh

[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5
backend  = systemd

[sshd]
enabled  = true
port     = ${SSH_PORT}
filter   = sshd
logpath  = %(sshd_log)s
maxretry = 5
bantime  = 3600
findtime = 600
JAILEOF

    systemctl enable fail2ban >/dev/null 2>&1
    systemctl restart fail2ban

    CHANGES_MADE+=("fail2ban: SSH jail (maxretry=5, bantime=1h, findtime=10m)")
    log_info "fail2ban installed and configured."
}

# ── Step 5: Tailscale ────────────────────────────────────────────────────────

step_tailscale() {
    log_step "Step 5/10: Tailscale"

    if command -v tailscale &>/dev/null; then
        log_info "Tailscale already installed: $(tailscale version 2>/dev/null || echo 'unknown version')"
    else
        curl -fsSL https://tailscale.com/install.sh | sh
        log_info "Tailscale installed."
    fi

    systemctl enable tailscaled >/dev/null 2>&1
    systemctl start tailscaled 2>/dev/null || true

    echo ""
    echo -e "  ${BOLD}Tailscale authentication:${NC}"
    echo "  You can authenticate now or later."
    echo ""
    read -rp "  Enter Tailscale auth key (or press Enter for interactive login): " ts_authkey

    if [[ -n "$ts_authkey" ]]; then
        tailscale up --authkey="$ts_authkey" --ssh 2>/dev/null && {
            CHANGES_MADE+=("Tailscale: installed, authenticated with auth key, SSH enabled")
            log_info "Tailscale authenticated with auth key. Tailscale SSH enabled."
        } || {
            log_warn "Tailscale auth key failed. Run 'tailscale up --ssh' manually."
            CHANGES_MADE+=("Tailscale: installed, auth key failed — manual auth needed")
        }
    else
        log_info "Run 'sudo tailscale up --ssh' to authenticate interactively."
        CHANGES_MADE+=("Tailscale: installed, manual authentication needed")
    fi

    echo ""
    read -rp "  Lock SSH to Tailscale only? (removes public SSH access) [y/N]: " lock_ssh
    if [[ "$lock_ssh" =~ ^[Yy]$ ]]; then
        if ufw status | grep -q "${SSH_PORT}/tcp"; then
            ufw delete allow "${SSH_PORT}/tcp" >/dev/null 2>&1 || true
            log_info "Removed public SSH port ${SSH_PORT} from UFW."
            log_info "SSH now accessible ONLY via Tailscale."
            CHANGES_MADE+=("SSH: locked to Tailscale only (public port ${SSH_PORT} removed from UFW)")
        fi
    else
        log_info "Public SSH access kept on port ${SSH_PORT}."
    fi
}

# ── Step 6: Kernel Hardening ─────────────────────────────────────────────────

step_kernel() {
    log_step "Step 6/10: Kernel hardening (sysctl)"

    local sysctl_file="/etc/sysctl.d/99-factory-hardening.conf"
    backup_file "$sysctl_file"

    cat > "$sysctl_file" << 'KERNEOF'
# Factory Control Bot — Kernel hardening
# Generated by secure.sh

# Enable SYN cookie protection
net.ipv4.tcp_syncookies = 1

# Disable ICMP redirects (prevent MITM)
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Disable source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# Enable reverse path filtering (anti-spoofing)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Log martian packets
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Ignore bogus ICMP errors
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Keep IP forwarding enabled (required for Docker)
net.ipv4.ip_forward = 1
KERNEOF

    sysctl --system >/dev/null 2>&1

    CHANGES_MADE+=("Kernel: SYN cookies, no redirects, no source routing, rp_filter, log martians")
    log_info "Kernel hardening applied."
}

# ── Step 7: Shared Memory Hardening ──────────────────────────────────────────

step_shm() {
    log_step "Step 7/10: Shared memory hardening"

    local fstab="/etc/fstab"
    backup_file "$fstab"

    # Check if /run/shm or /dev/shm is already hardened in fstab
    if grep -qE '^\s*(tmpfs|none)\s+/run/shm\s' "$fstab" 2>/dev/null; then
        log_info "/run/shm already has an fstab entry. Skipping."
    elif grep -qE '^\s*(tmpfs|none)\s+/dev/shm\s' "$fstab" 2>/dev/null; then
        log_info "/dev/shm already has an fstab entry. Skipping."
    else
        echo "" >> "$fstab"
        echo "# Factory hardening: restrict shared memory" >> "$fstab"
        echo "tmpfs /run/shm tmpfs defaults,nosuid,noexec,nodev 0 0" >> "$fstab"

        # Remount if /run/shm exists
        if mountpoint -q /run/shm 2>/dev/null; then
            mount -o remount,nosuid,noexec,nodev /run/shm 2>/dev/null || true
        elif mountpoint -q /dev/shm 2>/dev/null; then
            mount -o remount,nosuid,noexec,nodev /dev/shm 2>/dev/null || true
        fi

        CHANGES_MADE+=("Shared memory: /run/shm nosuid,noexec,nodev")
        log_info "Shared memory hardened."
    fi
}

# ── Step 8: Automatic Security Updates ───────────────────────────────────────

step_unattended() {
    log_step "Step 8/10: Automatic security updates"

    apt-get install -y -qq unattended-upgrades apt-listchanges 2>/dev/null

    local auto_conf="/etc/apt/apt.conf.d/20auto-upgrades"
    backup_file "$auto_conf"

    cat > "$auto_conf" << 'AUTOEOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
AUTOEOF

    local unattended_conf="/etc/apt/apt.conf.d/50unattended-upgrades"
    backup_file "$unattended_conf"

    cat > "$unattended_conf" << 'UAEOF'
// Factory Control Bot — Unattended upgrades config
// Generated by secure.sh

Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};

// Remove unused kernel packages
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";

// Remove unused dependencies
Unattended-Upgrade::Remove-Unused-Dependencies "true";

// Auto-reboot if needed (at 04:00)
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";

// Log to syslog
Unattended-Upgrade::SyslogEnable "true";
UAEOF

    systemctl enable unattended-upgrades >/dev/null 2>&1
    systemctl restart unattended-upgrades 2>/dev/null || true

    CHANGES_MADE+=("Unattended-upgrades: security patches auto-installed, auto-reboot at 04:00")
    log_info "Automatic security updates configured."
}

# ── Step 9: Docker Hardening ─────────────────────────────────────────────────

step_docker_harden() {
    log_step "Step 9/10: Docker hardening"

    if ! command -v docker &>/dev/null; then
        log_info "Docker not installed. Skipping Docker hardening."
        return
    fi

    local daemon_json="/etc/docker/daemon.json"
    backup_file "$daemon_json"

    # Read existing daemon.json if it exists, or start fresh
    # We use a simple approach: write a known-good config
    cat > "$daemon_json" << 'DOCKEREOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "no-new-privileges": true,
    "live-restore": true,
    "userland-proxy": false,
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 65536,
            "Soft": 32768
        }
    }
}
DOCKEREOF

    systemctl restart docker 2>/dev/null || true

    CHANGES_MADE+=("Docker: log rotation (10m x 3), no-new-privileges, live-restore, no userland proxy")
    log_info "Docker daemon hardened."
}

# ── Step 10: Summary ─────────────────────────────────────────────────────────

step_summary() {
    log_step "Step 10/10: Security hardening summary"

    echo ""
    echo "================================================"
    echo -e "${GREEN}${BOLD}Security hardening complete!${NC}"
    echo "================================================"
    echo ""
    echo -e "  ${BOLD}Changes applied:${NC}"
    for change in "${CHANGES_MADE[@]}"; do
        echo -e "    ${GREEN}✓${NC} ${change}"
    done

    echo ""
    echo -e "  ${BOLD}Firewall status:${NC}"
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw status numbered 2>/dev/null | head -20 | while IFS= read -r line; do
            echo "    $line"
        done
    else
        echo "    UFW not active (skipped or not installed)"
    fi

    echo ""
    echo -e "  ${BOLD}SSH:${NC}"
    echo "    Port: ${SSH_PORT}"
    if [[ -f /etc/ssh/sshd_config.d/99-factory-hardening.conf ]]; then
        echo "    Root login: disabled"
        echo "    Max auth tries: 3"
        if grep -q "PasswordAuthentication no" /etc/ssh/sshd_config.d/99-factory-hardening.conf 2>/dev/null; then
            echo "    Password auth: disabled (key-only)"
        else
            echo -e "    Password auth: ${YELLOW}enabled${NC} (add SSH keys then re-run)"
        fi
    fi

    echo ""
    echo -e "  ${BOLD}Tailscale:${NC}"
    if command -v tailscale &>/dev/null; then
        tailscale status 2>/dev/null | head -5 | while IFS= read -r line; do
            echo "    $line"
        done
    else
        echo "    Not installed (skipped)"
    fi

    echo ""
    echo -e "  ${BOLD}fail2ban:${NC}"
    if systemctl is-active fail2ban &>/dev/null; then
        echo "    Status: active"
        fail2ban-client status sshd 2>/dev/null | grep -E "Currently|Total" | while IFS= read -r line; do
            echo "    $line"
        done
    else
        echo "    Not active (skipped or not installed)"
    fi

    echo ""
    echo -e "  ${BOLD}Important reminders:${NC}"
    if [[ "$SSH_PORT" != "22" ]]; then
        echo -e "    ${YELLOW}!${NC} SSH port changed to ${SSH_PORT}. Connect with: ssh -p ${SSH_PORT} user@host"
    fi
    echo "    - Test SSH access in a NEW terminal before closing this session"
    echo "    - Config backups saved with .bak.<timestamp> suffix"
    echo "    - Auto-reboot for security updates at 04:00 (change in /etc/apt/apt.conf.d/50unattended-upgrades)"
    echo ""
}

# ── Execute Steps ────────────────────────────────────────────────────────────

[[ "$SKIP_UPDATES" == false ]]       && step_updates       || log_info "Skipping: system updates"
[[ "$SKIP_SSH" == false ]]           && step_ssh           || log_info "Skipping: SSH hardening"
[[ "$SKIP_UFW" == false ]]           && step_ufw           || log_info "Skipping: UFW firewall"
[[ "$SKIP_FAIL2BAN" == false ]]      && step_fail2ban      || log_info "Skipping: fail2ban"
[[ "$SKIP_TAILSCALE" == false ]]     && step_tailscale     || log_info "Skipping: Tailscale"
[[ "$SKIP_KERNEL" == false ]]        && step_kernel        || log_info "Skipping: kernel hardening"
[[ "$SKIP_SHM" == false ]]           && step_shm           || log_info "Skipping: shared memory hardening"
[[ "$SKIP_UNATTENDED" == false ]]    && step_unattended    || log_info "Skipping: automatic security updates"
[[ "$SKIP_DOCKER_HARDEN" == false ]] && step_docker_harden || log_info "Skipping: Docker hardening"

step_summary
