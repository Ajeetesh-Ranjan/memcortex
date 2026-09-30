#!/usr/bin/env bash
# Unified Memory Stack — Universal Menubar/Tray Installer
# Detects platform and runs appropriate installer

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[install]${NC} $*"; }
err() { echo -e "${RED}[install]${NC} $*" >&2; }
info() { echo -e "${BLUE}[info]${NC} $*"; }

# Paths
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log "Unified Memory Stack — Universal Menubar Installer"
log "Repo: $REPO_ROOT"

# Detect platform
OS="$(uname -s)"
case "$OS" in
    Darwin)
        PLATFORM="macos"
        INSTALLER="$REPO_ROOT/widgets/menubar/macos/install.sh"
        ;;
    Linux)
        PLATFORM="linux"
        INSTALLER="$REPO_ROOT/widgets/menubar/linux/install.sh"
        ;;
    CYGWIN*|MINGW*|MSYS*)
        PLATFORM="windows"
        INSTALLER="$REPO_ROOT/widgets/menubar/windows/install.bat"
        ;;
    *)
        err "Unsupported platform: $OS"
        exit 1
        ;;
esac

log "Detected platform: $PLATFORM"

# Check if installer exists
if [[ ! -f "$INSTALLER" ]]; then
    err "Installer not found: $INSTALLER"
    exit 1
fi

# Make executable
chmod +x "$INSTALLER" 2>/dev/null || true

# Run platform-specific installer
log "Running $PLATFORM installer..."
exec "$INSTALLER" "$@"