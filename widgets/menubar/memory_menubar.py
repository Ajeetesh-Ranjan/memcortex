#!/usr/bin/env python3
"""
The AI Architecture Lab — Unified Memory Stack Menubar/Status Bar Widget
Works on: macOS (menubar), Windows (system tray), Linux (system tray/AppIndicator)

Features:
- Native menubar/tray integration on all platforms
- Real-time status: 🟢 healthy, 🟡 degraded, 🔴 unhealthy
- Memory count, tokens saved, service health
- Click to open dashboard, right-click for actions
- Auto-refresh configurable
- Single binary via PyInstaller (optional)

Requirements:
    pip install pystray pillow requests
    # Linux: sudo apt install libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1
    # macOS: Works with pystray (uses Cocoa via pyobjc if available, fallback to basic)
    # Windows: Works natively
"""

import sys
import os
import json
import time
import threading
import platform
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw
import requests

# Platform detection
IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY")

# Try to import pystray
try:
    import pystray
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Check for AppIndicator on Linux
HAS_APPINDICATOR = False
if IS_LINUX and HAS_PYSTRAY:
    try:
        import gi
        gi.require_version('AyatanaAppIndicator3', '0.1')
        from gi.repository import AyatanaAppIndicator3
        HAS_APPINDICATOR = True
    except (ImportError, ValueError):
        pass
    print("Warning: pystray not installed. Install with: pip install pystray pillow requests")

# =============================================================================
# Configuration
# =============================================================================

API_BASE = os.environ.get("MEMORY_API_BASE", "http://localhost:8080")
REFRESH_INTERVAL = int(os.environ.get("MEMORY_REFRESH_SEC", "30"))
ICON_SIZE = 22  # macOS menubar standard size

# Colors for status
COLORS = {
    "healthy": "#00e6a8",
    "degraded": "#ffb454", 
    "unhealthy": "#ff6b6b",
    "unknown": "#8fa3bb",
}

# =============================================================================
# API Client
# =============================================================================

class MemoryAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.timeout = 5

    def health(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/healthz")
            return {"status": "healthy" if r.ok else "unhealthy", "data": r.json() if r.ok else None}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def overview(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/api/overview")
            return {"status": "healthy" if r.ok else "unhealthy", "data": r.json() if r.ok else None}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def autopilot_status(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/api/autopilot/status")
            return {"status": "healthy" if r.ok else "unhealthy", "data": r.json() if r.ok else None}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

# =============================================================================
# Icon Generation
# =============================================================================

def create_icon(status: str, count: int = 0, size: int = ICON_SIZE) -> Image.Image:
    """Generate a colored menubar/tray icon with optional badge."""
    color = COLORS.get(status, COLORS["unknown"])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main circle (brain indicator)
    margin = 2
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline="#0b0f14",
        width=1 if size <= 22 else 2
    )

    # Brain symbol (simplified)
    cx, cy = size // 2, size // 2
    brain_size = max(6, size // 3)
    draw.ellipse(
        [cx - brain_size, cy - brain_size + 2, cx + brain_size, cy + brain_size + 2],
        outline="#0b0f14",
        width=1
    )
    draw.line([cx - brain_size//2, cy, cx + brain_size//2, cy], fill="#0b0f14", width=1)
    draw.line([cx, cy - brain_size//2 + 2, cx, cy + brain_size//2 + 2], fill="#0b0f14", width=1)

    # Badge with count
    if count > 0:
        badge_text = str(min(count, 99))
        text_bbox = draw.textbbox((0, 0), badge_text)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        bx, by = size - 2 - text_w - 4, 2
        badge_color = "#ff6b6b" if count > 50 else "#ffb454" if count > 10 else "#00e6a8"
        draw.rounded_rectangle(
            [bx - 3, by - 1, bx + text_w + 3, by + text_h + 1],
            radius=6, fill=badge_color
        )
        draw.text((bx, by), badge_text, fill="#0b0f14", font_size=max(8, size//3))

    return img

# =============================================================================
# Platform-Specific Tray Implementation
# =============================================================================

class TrayApp:
    def __init__(self):
        self.api = MemoryAPI(API_BASE)
        self.icon = None
        self.running = True
        self.memory_count = 0
        self.tokens_saved = 0
        self.services_up = 0
        self.services_total = 0
        self.current_status = "unknown"
        
    def fetch_data(self):
        """Fetch latest data from API."""
        try:
            overview = self.api.overview()
            if overview.get("status") == "healthy" and overview.get("data"):
                data = overview["data"]
                self.memory_count = data.get("supermemory", {}).get("memories", 0)
                self.tokens_saved = data.get("tokens", {}).get("saved", 0)
                
                services = [
                    data.get("supermemory", {}).get("up", False),
                    data.get("qdrant", {}).get("up", False),
                    data.get("redis", {}).get("up", False),
                    data.get("postgres", {}).get("up", False),
                    data.get("headroom", {}).get("up", False),
                ]
                self.services_total = len(services)
                self.services_up = sum(1 for s in services if s)
                
                if self.services_up == 0:
                    self.current_status = "unhealthy"
                elif self.services_up == self.services_total:
                    self.current_status = "healthy"
                else:
                    self.current_status = "degraded"
            else:
                self.current_status = "unknown"
                self.memory_count = 0
                self.tokens_saved = 0
                self.services_up = 0
                self.services_total = 0
        except Exception as e:
            print(f"Fetch error: {e}")
            self.current_status = "unknown"

    def update_icon(self):
        """Update tray icon."""
        if self.icon:
            self.icon.icon = create_icon(self.current_status, self.memory_count)
            self.icon.title = self.build_tooltip()

    def build_tooltip(self) -> str:
        return f"""The AI Architecture Lab — Unified Memory Stack
Memories: {self.memory_count:,}
Tokens saved: {self.tokens_saved:,}
Services: {self.services_up}/{self.services_total} healthy
Status: {self.current_status.title()}
Click to open dashboard"""

    def build_menu(self):
        """Build right-click context menu."""
        if not HAS_PYSTRAY:
            return None
            
        items = [
            pystray.MenuItem(
                "Open Dashboard",
                lambda: webbrowser.open(API_BASE),
                default=True
            ),
            pystray.MenuItem(
                f"Status: {self.current_status.title()} ({self.services_up}/{self.services_total})",
                None,
                enabled=False
            ),
            pystray.MenuItem(
                f"Memories: {self.memory_count:,} | Tokens: {self.tokens_saved:,}",
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
        ]
        
        # Add per-service status
        try:
            overview = self.api.overview()
            if overview.get("status") == "healthy" and overview.get("data"):
                data = overview["data"]
                services = [
                    ("Supermemory", data.get("supermemory", {}).get("up")),
                    ("Qdrant", data.get("qdrant", {}).get("up")),
                    ("Redis", data.get("redis", {}).get("up")),
                    ("PostgreSQL", data.get("postgres", {}).get("up")),
                    ("Headroom", data.get("headroom", {}).get("up")),
                ]
                for name, up in services:
                    if up is not None:
                        status = "●" if up else "○"
                        items.append(pystray.MenuItem(
                            f"{status} {name}",
                            None,
                            enabled=False
                        ))
        except Exception:
            pass
        
        items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh Now", self.force_refresh),
            pystray.MenuItem("View Logs", self.view_logs),
            pystray.MenuItem("Restart Stack", self.restart_stack),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit),
        ])
        return pystray.Menu(*items)

    def force_refresh(self, icon=None, item=None):
        self.fetch_data()
        self.update_icon()

    def view_logs(self, icon=None, item=None):
        try:
            subprocess.Popen(["docker", "compose", "logs", "-f", "--tail", "100"], 
                           cwd=Path(__file__).parent)
        except Exception:
            pass

    def restart_stack(self, icon=None, item=None):
        try:
            subprocess.run(["docker", "compose", "restart"], 
                         cwd=Path(__file__).parent, check=True)
            time.sleep(5)
            self.force_refresh()
        except Exception as e:
            print(f"Restart failed: {e}")

    def quit(self, icon=None, item=None):
        self.running = False
        if self.icon:
            self.icon.stop()

    def refresh_loop(self):
        """Background refresh loop."""
        while self.running:
            try:
                self.fetch_data()
                self.update_icon()
            except Exception as e:
                print(f"Refresh error: {e}")
            time.sleep(REFRESH_INTERVAL)

    def run(self):
        """Run the tray application."""
        if not HAS_PYSTRAY:
            print("Error: pystray not installed. Run: pip install pystray pillow requests")
            sys.exit(1)
            
        # Initial fetch
        self.fetch_data()
        
        # Create initial icon
        initial_icon = create_icon(self.current_status, self.memory_count)
        
        # Create tray icon
        self.icon = pystray.Icon(
            "unified-memory-stack",
            initial_icon,
            "The AI Architecture Lab — Unified Memory",
            self.build_menu()
        )
        
        # Start refresh thread
        refresh_thread = threading.Thread(target=self.refresh_loop, daemon=True)
        refresh_thread.start()
        
        # Run icon (blocks until quit)
        self.icon.run()


# =============================================================================
# macOS Native Menubar (Alternative - uses osascript for simple menubar)
# =============================================================================

class MacOSMenubar:
    """Lightweight macOS menubar using osascript (no pyobjc needed)."""
    
    def __init__(self):
        self.api = MemoryAPI(API_BASE)
        self.running = True
        
    def fetch_data(self):
        """Fetch latest data."""
        try:
            overview = self.api.overview()
            if overview.get("status") == "healthy" and overview.get("data"):
                data = overview["data"]
                self.memory_count = data.get("supermemory", {}).get("memories", 0)
                self.tokens_saved = data.get("tokens", {}).get("saved", 0)
                services = [
                    data.get("supermemory", {}).get("up", False),
                    data.get("qdrant", {}).get("up", False),
                    data.get("redis", {}).get("up", False),
                    data.get("postgres", {}).get("up", False),
                    data.get("headroom", {}).get("up", False),
                ]
                self.services_up = sum(1 for s in services if s)
                self.services_total = len(services)
                if self.services_up == 0:
                    self.current_status = "unhealthy"
                elif self.services_up == self.services_total:
                    self.current_status = "healthy"
                else:
                    self.current_status = "degraded"
            else:
                self.current_status = "unknown"
        except Exception:
            self.current_status = "unknown"
    
    def update_menubar(self):
        """Update macOS menubar via osascript."""
        # This is a simplified approach - for full native menubar, 
        # a proper Swift/ObjC app is recommended
        pass
    
    def run(self):
        """Run with periodic updates."""
        while self.running:
            self.fetch_data()
            # For a real menubar, you'd use rumps or a native Swift app
            # This is a placeholder showing the concept
            time.sleep(REFRESH_INTERVAL)


# =============================================================================
# Platform-Specific Launchers
# =============================================================================

def run_macos():
    """Run on macOS - try pystray first, fallback to native."""
    if HAS_PYSTRAY:
        print("Running with pystray on macOS...")
        app = TrayApp()
        app.run()
    else:
        print("pystray not available. Install: pip install pystray pillow requests")
        print("For native macOS menubar, consider the Swift version in widgets/macos/")
        # Fallback: run headless with periodic notifications
        run_headless()


def run_windows():
    """Run on Windows - use pystray."""
    if HAS_PYSTRAY:
        print("Running with pystray on Windows...")
        app = TrayApp()
        app.run()
    else:
        print("pystray not available. Install: pip install pystray pillow requests")
        sys.exit(1)


def run_linux():
    """Run on Linux - use pystray with AppIndicator if available, fallback to headless."""
    if not HAS_PYSTRAY:
        print("pystray not available. Install: pip install pystray pillow requests")
        sys.exit(1)
    
    if IS_WAYLAND and not HAS_APPINDICATOR:
        warn("Wayland detected without AppIndicator support.")
        warn("For system tray on Wayland, install: sudo apt install libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1")
        warn("Or use the Waybar module (widgets/waybar/) for native Wayland support.")
        warn("Falling back to headless mode...")
        run_headless()
        return
    
    if not HAS_APPINDICATOR and not IS_WAYLAND:
        warn("AppIndicator not available. System tray may not work properly.")
        warn("Install: sudo apt install libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1")
    
    print("Running with pystray on Linux...")
    app = TrayApp()
    app.run()


def warn(msg: str):
    print(f"\033[1;33m[warn]\033[0m {msg}", file=sys.stderr)

def run_headless():
    """Headless mode - periodic status output (for Wayland/headless environments)."""
    api = MemoryAPI(API_BASE)
    print("Running in headless mode (no system tray). Press Ctrl+C to stop.")
    print(f"API: {API_BASE} | Refresh: {REFRESH_INTERVAL}s")
    try:
        while True:
            overview = api.overview()
            if overview.get("status") == "healthy" and overview.get("data"):
                data = overview["data"]
                mem = data.get("supermemory", {}).get("memories", 0)
                tok = data.get("tokens", {}).get("saved", 0)
                svc_up = sum(1 for k in ["supermemory","qdrant","redis","postgres","headroom"] 
                            if data.get(k, {}).get("up"))
                status = "🟢" if svc_up == 5 else "🟡" if svc_up > 0 else "🔴"
                print(f"[{time.strftime('%H:%M:%S')}] {status} Memories: {mem:,} | Tokens: {tok:,} | Services: {svc_up}/5")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] 🔴 Stack unreachable")
            time.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.")


# =============================================================================
# Entry Point
# =============================================================================

def main():
    # Allow API base override
    global API_BASE, REFRESH_INTERVAL
    if len(sys.argv) > 1:
        API_BASE = sys.argv[1]
    if len(sys.argv) > 2:
        REFRESH_INTERVAL = int(sys.argv[2])
    
    print(f"The AI Architecture Lab — Menubar Widget")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"API Base: {API_BASE}")
    print(f"Refresh: {REFRESH_INTERVAL}s")
    
    system = platform.system()
    if system == "Darwin":
        run_macos()
    elif system == "Windows":
        run_windows()
    elif system == "Linux":
        run_linux()
    else:
        print(f"Unsupported platform: {system}")
        run_headless()


if __name__ == "__main__":
    main()