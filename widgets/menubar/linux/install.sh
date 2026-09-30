#!/usr/bin/env bash
# Unified Memory Stack — Linux System Tray Installer
# Installs the Python system tray app with autostart for GNOME/KDE/XFCE

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[install]${NC} $*"; }
err() { echo -e "${RED}[install]${NC} $*" >&2; }

# Paths
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON_SCRIPT="$REPO_ROOT/widgets/menubar/memory_menubar.py"
DESKTOP_FILE="$HOME/.config/autostart/unified-memory-stack.desktop"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/unified-memory-stack-tray.service"

log "Unified Memory Stack — Linux System Tray Installer"
log "Repo: $REPO_ROOT"

# Check Python
if ! command -v python3 &> /dev/null; then
    err "Python 3 not found. Install: sudo apt install python3 python3-pip"
    exit 1
fi

log "Python found: $(python3 --version)"

# Install system dependencies
log "Installing system dependencies..."
if command -v apt &> /dev/null; then
    sudo apt update -qq
    sudo apt install -y -qq \
        python3-pip \
        python3-gi \
        gir1.2-ayatanaappindicator3-0.1 \
        libayatana-appindicator3-1 \
        libnotify-bin \
        2>/dev/null || warn "Some packages may not be available on this distro"
elif command -v dnf &> /dev/null; then
    sudo dnf install -y python3-pip libayatana-appindicator-gtk3 libnotify
elif command -v pacman &> /dev/null; then
    sudo pacman -S --noconfirm python-pip libayatana-appindicator libnotify
else
    warn "Unknown package manager. Please install: python3-pip, libayatana-appindicator, libnotify"
fi

# Install Python dependencies
log "Installing Python dependencies..."
pip3 install --user pystray pillow requests --quiet

if [[ $? -ne 0 ]]; then
    err "Failed to install Python dependencies"
    exit 1
fi

log "Dependencies installed"

# Create autostart desktop entry
log "Creating autostart entry..."
mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Unified Memory Stack
Comment=System tray widget for Unified Memory Stack
Exec=python3 $PYTHON_SCRIPT
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=System;Monitor;
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
X-GNOME-Autostart-Delay=5
Env=MEMORY_API_BASE=http://localhost:8080;MEMORY_REFRESH_SEC=30
EOF

log "Autostart entry created: $DESKTOP_FILE"

# Also create systemd user service (more robust)
log "Creating systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Unified Memory Stack System Tray
After=graphical-session.target network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $PYTHON_SCRIPT
Restart=on-failure
RestartSec=10
Environment=MEMORY_API_BASE=http://localhost:8080
Environment=MEMORY_REFRESH_SEC=30
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/%U

[Install]
WantedBy=default.target
EOF

# Enable and start
systemctl --user daemon-reload
systemctl --user enable unified-memory-stack-tray.service
systemctl --user start unified-memory-stack-tray.service

log "Systemd service enabled and started"

# Test run
log "Testing installation..."
python3 "$PYTHON_SCRIPT" --help 2>&1 | head -5

log ""
log "============================================"
log "Installation complete!"
log "============================================"
log ""
log "The Unified Memory Stack system tray will:"
log "  - Start automatically on login (via autostart + systemd)"
log "  - Appear in system tray (top/bottom panel)"
log "  - Show status: Green=healthy, Yellow=degraded, Red=unhealthy"
log "  - Left-click: Open dashboard"
log "  - Right-click: Menu (Refresh, Logs, Restart, Quit)"
log ""
log "To run manually now:"
log "  python3 $PYTHON_SCRIPT"
log ""
log "To check status:"
log "  systemctl --user status unified-memory-stack-tray"
log ""
log "To view logs:"
log "  journalctl --user -u unified-memory-stack-tray -f"
log ""
log "To uninstall:"
log "  systemctl --user disable --now unified-memory-stack-tray"
log "  rm -f $DESKTOP_FILE $SERVICE_FILE"
log "  systemctl --user daemon-reload"
log ""
log "Note: For AppIndicator support, ensure your desktop environment supports it."
log "GNOME: Install 'gnome-shell-extension-appindicator' extension"
log "KDE: Built-in support"
log "XFCE: Built-in support"