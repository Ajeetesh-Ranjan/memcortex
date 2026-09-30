#!/usr/bin/env bash
# Install the AI Architecture Lab Memory Brain bar widget for Omarchy.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="io.github.aial.memory-brain"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/$PLUGIN_ID"

if ! command -v omarchy >/dev/null 2>&1; then
  echo "error: 'omarchy' not found. This widget targets the Omarchy desktop shell." >&2
  exit 1
fi

echo "Installing $PLUGIN_ID -> $DEST"
mkdir -p "$DEST"
# Copy contents, never clobber the plugin id directory itself.
cp -r "$SRC/." "$DEST/"
rm -rf "$DEST/.git" "$DEST/__pycache__" "$DEST/install.sh"
chmod +x "$DEST/bin/aal-brain-collector.py"

omarchy plugin enable "$PLUGIN_ID"

cat <<MSG

Installed. Restart the bar shell to load it:

  kill "\$(pgrep -f 'quickshell -n -p /usr/share/omarchy/shell' | head -1)"

Hyprland's exec-once will bring the shell back automatically.
MSG
