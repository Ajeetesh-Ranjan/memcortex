#!/usr/bin/env bash
# Unified Memory Stack — macOS Menubar Installer
# Installs the native Swift menubar app

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
MACOS_DIR="$REPO_ROOT/widgets/menubar/macos"
BUILD_DIR="$MACOS_DIR/.build/release"
INSTALL_DIR="/Applications"
APP_NAME="MemoryMenubar"

log "Unified Memory Stack — macOS Menubar Installer"
log "Repo: $REPO_ROOT"

# Check for Swift
if ! command -v swift &> /dev/null; then
    err "Swift not found. Install Xcode Command Line Tools: xcode-select --install"
    exit 1
fi

# Check macOS version
MACOS_VERSION=$(sw_vers -productVersion)
log "macOS $MACOS_VERSION detected"

# Build
log "Building MemoryMenubar..."
cd "$MACOS_DIR"
swift build -c release

if [[ ! -f "$BUILD_DIR/$APP_NAME" ]]; then
    err "Build failed - binary not found at $BUILD_DIR/$APP_NAME"
    exit 1
fi

log "Build successful!"

# Install to Applications
log "Installing to $INSTALL_DIR/$APP_NAME..."
if [[ -d "$INSTALL_DIR/$APP_NAME.app" ]]; then
    warn "Removing existing installation..."
    rm -rf "$INSTALL_DIR/$APP_NAME.app"
fi

# Create app bundle
APP_BUNDLE="$INSTALL_DIR/$APP_NAME.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy binary
cp "$BUILD_DIR/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/"

# Create Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>MemoryMenubar</string>
    <key>CFBundleIdentifier</key>
    <string>com.unifiedmemory.MemoryMenubar</string>
    <key>CFBundleName</key>
    <string>Unified Memory Stack</string>
    <key>CFBundleDisplayName</key>
    <string>Memory Stack</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>MIT License</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
</dict>
</plist>
EOF

# Create a simple icon (optional - would need a proper .icns)
# For now, the app will generate its own status icons programmatically

log "Installation complete!"
log ""
log "To run:"
log "  1. Open $APP_BUNDLE"
log "  2. The app will appear in your menubar (top-right)"
log "  3. Right-click for menu, left-click for dashboard"
log ""
log "To auto-start on login:"
log "  System Settings → General → Login Items → Add $APP_BUNDLE"
log ""
log "Environment variables (optional):"
log "  export MEMORY_API_BASE=http://localhost:8080"
log "  export MEMORY_REFRESH_SEC=30"
log ""
log "Uninstall: rm -rf $APP_BUNDLE"