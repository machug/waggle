#!/usr/bin/env bash
# ============================================================================
# Waggle Install Script
#
# Installs and configures the Waggle beehive monitoring system on a
# Raspberry Pi. Idempotent — safe to re-run on an existing installation.
#
# Usage:
#   sudo ./scripts/install.sh          # from repo root
#   sudo bash scripts/install.sh       # alternative
#
# Prerequisites:
#   - Raspberry Pi OS (Debian-based)
#   - Python 3.11+
#   - Internet access (for pip install)
#   - NTP synchronized clock
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

step()    { echo -e "\n${BLUE}${BOLD}==>${NC}${BOLD} $1${NC}"; }
info()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${YELLOW}!${NC} $1"; }
fail()    { echo -e "\n${RED}${BOLD}ERROR:${NC} $1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Resolve repo root (script lives at <repo>/scripts/install.sh)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Installation paths
# ---------------------------------------------------------------------------
INSTALL_DIR="/opt/waggle"
DATA_DIR="/var/lib/waggle"
HEALTH_DIR="${DATA_DIR}/health"
CONFIG_DIR="/etc/waggle"
ENV_FILE="${CONFIG_DIR}/.env"
DB_PATH="${DATA_DIR}/waggle.db"
VENV_DIR="${INSTALL_DIR}/.venv"
BACKEND_DIR="${INSTALL_DIR}/backend"
SERVICE_USER="waggle"

# ============================================================================
# Step 1: Prerequisites
# ============================================================================
step "Checking prerequisites"

# Must be root
if [[ $EUID -ne 0 ]]; then
    fail "This script must be run as root (use sudo)."
fi
info "Running as root"

# Python 3.11+
PYTHON3=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON3="$(command -v "$candidate")"
        break
    fi
done

if [[ -z "$PYTHON3" ]]; then
    fail "Python 3 not found. Install python3 (>= 3.11) and re-run."
fi

PYTHON_VERSION="$("$PYTHON3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PYTHON_MAJOR="$("$PYTHON3" -c 'import sys; print(sys.version_info.major)')"
PYTHON_MINOR="$("$PYTHON3" -c 'import sys; print(sys.version_info.minor)')"

if [[ "$PYTHON_MAJOR" -lt 3 ]] || { [[ "$PYTHON_MAJOR" -eq 3 ]] && [[ "$PYTHON_MINOR" -lt 11 ]]; }; then
    fail "Python >= 3.11 required, found ${PYTHON_VERSION} at ${PYTHON3}."
fi
info "Python ${PYTHON_VERSION} at ${PYTHON3}"

# python3-venv module
if ! "$PYTHON3" -m venv --help &>/dev/null; then
    fail "python3-venv is not installed. Run: apt-get install python3-venv"
fi
info "python3-venv available"

# SQLite >= 3.25.0 (window functions, RENAME COLUMN)
SQLITE_VERSION="$("$PYTHON3" -c 'import sqlite3; print(sqlite3.sqlite_version)')"
SQLITE_PARTS=(${SQLITE_VERSION//./ })
SQLITE_MAJ="${SQLITE_PARTS[0]}"
SQLITE_MIN="${SQLITE_PARTS[1]}"
SQLITE_PATCH="${SQLITE_PARTS[2]:-0}"

if [[ "$SQLITE_MAJ" -lt 3 ]] || { [[ "$SQLITE_MAJ" -eq 3 ]] && [[ "$SQLITE_MIN" -lt 25 ]]; }; then
    fail "SQLite >= 3.25.0 required, found ${SQLITE_VERSION}."
fi
info "SQLite ${SQLITE_VERSION}"

# NTP sync check (warn, don't fail — devs may not have NTP)
if command -v timedatectl &>/dev/null; then
    NTP_SYNC="$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || echo "unknown")"
    if [[ "$NTP_SYNC" == "yes" ]]; then
        info "NTP synchronized"
    else
        warn "NTP not synchronized (NTPSynchronized=${NTP_SYNC}). Sensor timestamps may drift."
        warn "Fix with: sudo timedatectl set-ntp true"
    fi
else
    warn "timedatectl not found — cannot verify NTP sync"
fi

# ============================================================================
# Step 2: System user
# ============================================================================
step "Creating system user '${SERVICE_USER}'"

if id "$SERVICE_USER" &>/dev/null; then
    info "User '${SERVICE_USER}' already exists"
else
    useradd --system --create-home --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    info "Created user '${SERVICE_USER}'"
fi

# Ensure dialout group membership (for serial port access)
if id -nG "$SERVICE_USER" | grep -qw dialout; then
    info "User '${SERVICE_USER}' already in dialout group"
else
    usermod -aG dialout "$SERVICE_USER"
    info "Added '${SERVICE_USER}' to dialout group"
fi

# ============================================================================
# Step 3: Directories
# ============================================================================
step "Creating directories"

mkdir -p "$DATA_DIR" "$HEALTH_DIR" "$CONFIG_DIR" "$INSTALL_DIR"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "$DATA_DIR"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "$INSTALL_DIR"
info "${DATA_DIR} (data + health)"
info "${CONFIG_DIR} (config)"
info "${INSTALL_DIR} (application)"

# ============================================================================
# Step 4: Copy application files
# ============================================================================
step "Copying application files"

if [[ ! -d "${REPO_ROOT}/backend" ]]; then
    fail "Cannot find backend/ directory at ${REPO_ROOT}/backend. Run this script from the repo root."
fi

# Use rsync if available for cleaner updates; fall back to cp
if command -v rsync &>/dev/null; then
    rsync -a --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='*.egg-info' \
        --exclude='test_temp*' \
        --exclude='waggle.db' \
        "${REPO_ROOT}/backend/" "${BACKEND_DIR}/"
    info "Synced backend/ -> ${BACKEND_DIR}/ (rsync)"
else
    # Remove stale pycache before copy
    find "${REPO_ROOT}/backend" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    cp -r "${REPO_ROOT}/backend/" "${BACKEND_DIR}/"
    info "Copied backend/ -> ${BACKEND_DIR}/ (cp)"
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${BACKEND_DIR}"
info "Ownership set to ${SERVICE_USER}:${SERVICE_USER}"

# ============================================================================
# Step 5: Python virtual environment
# ============================================================================
step "Setting up Python virtual environment"

if [[ -d "${VENV_DIR}" ]]; then
    info "Virtual environment already exists at ${VENV_DIR}"
else
    sudo -u "$SERVICE_USER" "$PYTHON3" -m venv "$VENV_DIR"
    info "Created virtual environment at ${VENV_DIR}"
fi

# Upgrade pip first (suppress "already up-to-date" noise)
sudo -u "$SERVICE_USER" "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
info "pip upgraded"

# Install/update the waggle package (editable for easy updates)
sudo -u "$SERVICE_USER" "${VENV_DIR}/bin/pip" install --quiet -e "${BACKEND_DIR}/"
info "Installed waggle package (editable)"

# ============================================================================
# Step 6: Default configuration
# ============================================================================
step "Configuring environment"

if [[ -f "$ENV_FILE" ]]; then
    info "Config already exists at ${ENV_FILE} — not overwriting"
else
    API_KEY="$("$PYTHON3" -c "import secrets; print(secrets.token_urlsafe(32))")"
    cat > "$ENV_FILE" <<EOF
API_KEY=${API_KEY}
DB_PATH=${DB_PATH}
API_HOST=127.0.0.1
API_PORT=8000
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
SERIAL_DEVICE=/dev/ttyUSB0
EOF
    chown "${SERVICE_USER}:${SERVICE_USER}" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    info "Created ${ENV_FILE}"
    echo ""
    echo -e "  ${YELLOW}${BOLD}IMPORTANT:${NC} Generated API key. Save this now:"
    echo -e "  ${BOLD}${API_KEY}${NC}"
    echo ""
fi

# ============================================================================
# Step 7: Mosquitto MQTT broker
# ============================================================================
step "Installing Mosquitto MQTT broker"

if command -v mosquitto &>/dev/null; then
    info "Mosquitto already installed"
else
    apt-get update -qq
    apt-get install -y -qq mosquitto >/dev/null
    info "Installed Mosquitto"
fi

# Copy waggle-specific config
if [[ -f "${REPO_ROOT}/deploy/mosquitto/mosquitto.conf" ]]; then
    cp "${REPO_ROOT}/deploy/mosquitto/mosquitto.conf" /etc/mosquitto/conf.d/waggle.conf
    info "Installed Mosquitto config -> /etc/mosquitto/conf.d/waggle.conf"
else
    warn "deploy/mosquitto/mosquitto.conf not found — skipping Mosquitto config"
fi

systemctl enable mosquitto >/dev/null 2>&1
systemctl restart mosquitto
info "Mosquitto enabled and restarted"

# ============================================================================
# Step 8: Systemd services
# ============================================================================
step "Installing systemd services"

SERVICES_INSTALLED=0
for svc_file in "${REPO_ROOT}"/deploy/systemd/waggle-*.service; do
    if [[ -f "$svc_file" ]]; then
        cp "$svc_file" /etc/systemd/system/
        info "Installed $(basename "$svc_file")"
        SERVICES_INSTALLED=$((SERVICES_INSTALLED + 1))
    fi
done

if [[ "$SERVICES_INSTALLED" -eq 0 ]]; then
    warn "No service files found in deploy/systemd/"
else
    systemctl daemon-reload
    info "Reloaded systemd daemon"

    # Enable but do NOT start (user should review config first)
    systemctl enable waggle-bridge waggle-worker waggle-api 2>/dev/null || true
    info "Enabled waggle-bridge, waggle-worker, waggle-api"
fi

# ============================================================================
# Step 9: Database migration
# ============================================================================
step "Running database migration"

if [[ -f "${BACKEND_DIR}/alembic.ini" ]]; then
    sudo -u "$SERVICE_USER" \
        DB_PATH="$DB_PATH" \
        "${VENV_DIR}/bin/alembic" -c "${BACKEND_DIR}/alembic.ini" upgrade head
    info "Database migrated to latest revision"
else
    warn "alembic.ini not found — skipping migration"
fi

# ============================================================================
# Step 10: Summary
# ============================================================================
echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}  Waggle installation complete!${NC}"
echo -e "${GREEN}${BOLD}============================================${NC}"
echo ""
echo -e "  ${BOLD}Install dir:${NC}   ${INSTALL_DIR}"
echo -e "  ${BOLD}Data dir:${NC}      ${DATA_DIR}"
echo -e "  ${BOLD}Config:${NC}        ${ENV_FILE}"
echo -e "  ${BOLD}Database:${NC}      ${DB_PATH}"
echo -e "  ${BOLD}Venv:${NC}          ${VENV_DIR}"
echo -e "  ${BOLD}Python:${NC}        ${PYTHON3} (${PYTHON_VERSION})"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "    1. Review config:    ${YELLOW}sudo cat ${ENV_FILE}${NC}"
echo -e "    2. Plug in serial:   ${YELLOW}ls /dev/ttyUSB*${NC}"
echo -e "    3. Start services:   ${YELLOW}sudo systemctl start waggle-bridge waggle-worker waggle-api${NC}"
echo -e "    4. Check status:     ${YELLOW}sudo systemctl status waggle-bridge waggle-worker waggle-api${NC}"
echo -e "    5. View logs:        ${YELLOW}sudo journalctl -u waggle-bridge -f${NC}"
echo ""
