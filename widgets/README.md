# Unified Memory Stack — Live Widgets

Cross-platform desktop widgets for monitoring your Unified Memory Stack.

## Available Widgets

| Widget | Platform | Language | Best For |
|--------|----------|----------|----------|
| **Menubar/Tray** | Windows, macOS, Linux | Python/Swift | Native menubar/tray with full menu |
| **Python Tray** | Windows, macOS, Linux | Python + pystray | Universal desktop tray |
| **Waybar Module** | Omarchy, Hyprland, Sway, i3 | Python | Linux status bars |
| **HTML/JS** | Any browser, Electron, Tauri | HTML/JS | Web embed, custom dashboards |
| **Go Binary** | Windows, macOS, Linux | Go | Zero-dependency single binary |

---

## Quick Start

### 1. Menubar/Tray Widget (Recommended — Native Menubar/Taskbar)

**One-command install (all platforms):**

```bash
# From repo root
./widgets/menubar/install.sh
```

This detects your platform and runs the appropriate installer:

| Platform | Installer | Result |
|----------|-----------|--------|
| **macOS** | `widgets/menubar/macos/install.sh` | Native Swift app in `/Applications/MemoryMenubar.app` |
| **Linux** | `widgets/menubar/linux/install.sh` | Systemd service + autostart desktop entry |
| **Windows** | `widgets/menubar/windows/install.bat` | Startup shortcut + desktop shortcut |

**Manual run (Python, all platforms):**
```bash
cd widgets/menubar
pip install pystray pillow requests
python memory_menubar.py

# With custom API base
python memory_menubar.py http://your-server:8080
```

**Build single binary (optional):**
```bash
cd widgets/menubar
pip install pyinstaller
pyinstaller memory_menubar.spec
# Output: dist/memory-menubar (or .exe on Windows)
```

**Features:**
- **Native menubar/tray** on all platforms (macOS menubar, Windows taskbar, Linux panel)
- **Color-coded status**: 🟢 Healthy, 🟡 Degraded, 🔴 Unhealthy
- **Memory count badge** on icon
- **Rich menu**: Open Dashboard, Refresh, View Logs, Restart Stack, Quit
- **Per-service status** in menu
- **Auto-refresh** every 30s (configurable via `MEMORY_REFRESH_SEC`)
- **Desktop notifications** on status change (macOS/Windows/Linux)
- **Auto-start** on login (all platforms)

**Requirements:** Python 3.8+, `pip install pystray pillow requests`

**macOS Native (Swift) — Best Experience:**
```bash
cd widgets/menubar/macos
swift build -c release
# Run: .build/release/MemoryMenubar
# Or install: ./install.sh
```
This provides true native macOS menubar with zero dependencies.

---

### 2. Python System Tray (Universal)

```bash
cd widgets/python
pip install pystray pillow requests

# Run (auto-detects localhost:8080)
python memory_tray.py

# Or with custom API base
python memory_tray.py http://your-server:8080
```

**Features:**
- Native system tray icon (Windows taskbar, macOS menu bar, Linux panel)
- Color-coded status: 🟢 Healthy, 🟡 Degraded, 🔴 Unhealthy
- Memory count badge on icon
- Right-click menu: Open Dashboard, Refresh, View Logs, Restart Stack, Quit
- Auto-refresh every 30s (configurable via `MEMORY_REFRESH_SEC`)
- Desktop notifications on status change

**Requirements:** Python 3.8+, `pip install pystray pillow requests`

---

### 3. Waybar Module (Omarchy/Hyprland/Sway/i3)

```bash
cd widgets/waybar
pip install requests

# Copy to waybar scripts dir
cp memory-module.py ~/.config/waybar/scripts/
cp style.css ~/.config/waybar/style.css  # or append to existing
chmod +x ~/.config/waybar/scripts/memory-module.py
```

**waybar config (`~/.config/waybar/config.jsonc`):**

```jsonc
"custom/memory": {
    "exec": "~/.config/waybar/scripts/memory-module.py",
    "interval": 30,
    "format": "{}",
    "return-type": "json",
    "on-click": "xdg-open http://localhost:8080",
    "on-click-right": "~/.config/waybar/scripts/memory-module.py --menu"
},
```

**Features:**
- Color-coded text/icon in bar
- Rich tooltip with per-service status, memory counts, token savings
- Right-click menu (waybar 0.9.20+): Open Dashboard, Refresh, View Logs, Restart, Quit
- CSS animations for status changes
- Autopilot action summary in tooltip

**Style:** Append `style.css` to your waybar CSS for color classes and animations.

---

### 4. HTML/JS Widget (Embed Anywhere)

```html
<!-- Simple embed -->
<div id="memory-widget"></div>
<script src="https://your-server/widgets/html/memory-widget.js"></script>

<!-- Or self-hosted -->
<iframe src="https://your-server/widgets/html/memory-widget.html" width="340" height="400" frameborder="0"></iframe>
```

**Or as a standalone file:**

```bash
# Open directly in browser
open widgets/html/memory-widget.html

# Or serve locally
cd widgets/html && python -m http.server 8081
# Then open http://localhost:8081/memory-widget.html
```

**Features:**
- Zero dependencies, runs in any browser
- Responsive: full, compact, minimal modes
- Auto-refresh configurable via `MEMORY_REFRESH_SEC`
- Click anywhere to open dashboard
- Shows: overall status, memory count, tokens saved, documents, service list
- Autopilot status when enabled

**Configuration (global JS vars):**
```js
window.MEMORY_API_BASE = 'http://your-server:8080';
window.MEMORY_REFRESH_SEC = 30;
```

---

### 5. Go Single Binary (Zero Dependencies)

```bash
cd widgets/go
go mod init memory-widget
go get github.com/getlantern/systray github.com/skratchdot/open-golang/open
go build -ldflags="-s -w" -o memory-widget

# Run
./memory-widget

# Or with custom API
./memory-widget http://your-server:8080
```

**Cross-compile for all platforms:**

```bash
# Linux (amd64, arm64)
GOOS=linux GOARCH=amd64 go build -o memory-widget-linux-amd64
GOOS=linux GOARCH=arm64 go build -o memory-widget-linux-arm64

# macOS (Intel, Apple Silicon)
GOOS=darwin GOARCH=amd64 go build -o memory-widget-darwin-amd64
GOOS=darwin GOARCH=arm64 go build -o memory-widget-darwin-arm64

# Windows
GOOS=windows GOARCH=amd64 go build -o memory-widget-windows-amd64.exe
```

**Features:**
- True single binary (~5MB), no runtime needed
- Native tray on all platforms via `systray` library
- Same menu: Open Dashboard, Refresh, View Logs, Restart, Quit
- Minimal memory footprint (~5MB RSS)
- Fast startup (<100ms)

---

## Configuration

All widgets respect these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_API_BASE` | `http://localhost:8080` | Brain UI API endpoint |
| `MEMORY_REFRESH_SEC` | `30` | Refresh interval in seconds |

**Set per-platform:**

```bash
# Linux/macOS (bash/zsh)
export MEMORY_API_BASE=http://memory.local:8080
export MEMORY_REFRESH_SEC=60

# Windows (PowerShell)
$env:MEMORY_API_BASE = "http://memory.local:8080"
$env:MEMORY_REFRESH_SEC = "60"

# Windows (cmd)
set MEMORY_API_BASE=http://memory.local:8080
```

---

## Platform-Specific Notes

### Windows
- Python: Works with `pystray` (uses Win32 API)
- Go: Native Windows tray icon
- HTML: Open in Edge/Chrome, or package with Tauri/Electron

### macOS
- Python: Works with `pystray` (uses Cocoa via `pyobjc`)
- Go: Native macOS menu bar item
- **Note:** May need `sudo` for first run to allow menu bar access

### Linux (GNOME/KDE/XFCE)
- Python: Uses `libappindicator` or `libayatana`
- **Ubuntu/Debian:** `sudo apt install libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1`
- **Fedora:** `sudo dnf install libayatana-appindicator`
- **Arch/Omarchy:** `sudo pacman -S libayatana-appindicator`

### Omarchy / Hyprland / Wayland
- **Best option:** Waybar module (native Wayland support)
- Python tray: Works via `libayatana-appindicator` but may need XWayland
- Go: Works but prefer Waybar module

---

## Screenshots

### Python Tray (Windows/macOS/Linux)
```
┌─────────────────────────────────┐
│ 🟢 Unified Memory Stack         │
│ Memories: 1,234                 │
│ Tokens saved: 56,789            │
│ Services: 5/5 healthy           │
├─────────────────────────────────┤
│ 🟢 Supermemory    UP            │
│ 🟢 Qdrant         UP            │
│ 🟢 Redis          UP            │
│ 🟢 PostgreSQL     UP            │
│ 🟢 Headroom       UP            │
├─────────────────────────────────┤
│ Open Dashboard                  │
│ Refresh Now                     │
│ View Logs                       │
│ Restart Stack                   │
│ Quit                            │
└─────────────────────────────────┘
```

### Waybar (Omarchy/Hyprland)
```
┌────────────────────────────────────┐
│ 🟢 1,234  56.8K  5/5  ▼            │  ← Bar (click to open)
│                                    │
│ Tooltip on hover:                  │
│ ┌────────────────────────────────┐ │
│ │ Unified Memory Stack           │ │
│ │ Memories: 1,234 (100 static)   │ │
│ │ Tokens saved: 56,789 (12.3%)   │ │
│ │ Services:                      │ │
│ │   ● Supermemory                │ │
│ │   ● Qdrant                     │ │
│ │   ● Redis                      │ │
│ │   ● PostgreSQL                 │ │
│ │   ● Headroom                   │ │
│ │ Autopilot: 3 recent actions    │ │
│ └────────────────────────────────┘ │
└────────────────────────────────────┘
```

### HTML Widget
```
┌──────────────────────────────────┐
│ 🟢 Unified Memory          v1.0  │
├──────────────┬───────────────────┤
│  Memories    │  Tokens Saved     │
│   1,234      │    56,789         │
├──────────────┼───────────────────┤
│  Documents   │  Services Up      │
│     42       │      5/5          │
├──────────────────────────────────┤
│ 🟢 Supermemory    UP             │
│ 🟢 Qdrant         UP             │
│ 🟢 Redis          UP             │
│ 🟢 PostgreSQL     UP             │
│ 🟢 Headroom       UP             │
├──────────────────────────────────┤
│ Autopilot: active · 3 actions    │
├──────────────────────────────────┤
│ Open Dashboard →  Updated 14:32  │
└──────────────────────────────────┘
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Tray icon not appearing (Linux) | Install `libayatana-appindicator` |
| "Permission denied" on macOS | Grant menu bar access in System Settings → Privacy |
| Widget shows "Unreachable" | Check `MEMORY_API_BASE`, verify Brain UI is running |
| Wrong status color | Ensure `/api/overview` returns `up: true/false` for each service |
| Go build fails | Run `go mod tidy`, ensure Go 1.21+ |

---

## Development

### Adding a New Widget

1. Create folder under `widgets/`
2. Implement:
   - `fetchOverview()` → GET `/api/overview`
   - `fetchHealth()` → GET `/healthz`
   - `fetchAutopilot()` → GET `/api/autopilot/status`
   - Display logic for status, memory count, tokens, services
3. Respect `MEMORY_API_BASE` and `MEMORY_REFRESH_SEC`
4. Add to this README

### API Contract

All widgets use these Brain UI endpoints:

```
GET /healthz                    → {"status":"ok"} (lightweight)
GET /api/overview               → Full status + metrics
GET /api/autopilot/status       → Autopilot config + recent actions
GET /api/autopilot/value        → Lifetime value summary
```

---

## License

MIT — Part of Unified Memory Stack