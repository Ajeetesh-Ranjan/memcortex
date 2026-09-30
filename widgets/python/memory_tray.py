#!/usr/bin/env python3
"""
Unified Memory Stack — Cross-Platform System Tray Widget
Works on Windows, macOS, Linux (GNOME, KDE, Hyprland, etc.)

Features:
- Live status indicator (green/yellow/red)
- Click to open Brain UI dashboard
- Right-click menu: Open UI, View Logs, Restart Stack, Quit
- Auto-refresh every 30 seconds
- Shows memory count, token savings, service health

Requirements:
    pip install pystray pillow requests

Optional (for native notifications):
    Windows: pip install win10toast
    macOS: pip install pync
    Linux: notify-send (usually pre-installed)
"""

import sys
import os
import json
import time
import threading
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from PIL import Image, ImageDraw
import pystray

# Optional notification backends
try:
    from win10toast import ToastNotifier
    HAS_WINTOAST = True
except ImportError:
    HAS_WINTOAST = False

try:
    from pync import Notifier
    HAS_PYNC = True
except ImportError:
    HAS_PYNC = False


# =============================================================================
# Configuration
# =============================================================================

API_BASE = os.environ.get("MEMORY_API_BASE", "http://localhost:8080")
REFRESH_INTERVAL = int(os.environ.get("MEMORY_REFRESH_INTERVAL", "30"))
ICON_SIZE = 64

# Status colors
COLORS = {
    "healthy": "#00e6a8",   # green
    "degraded": "#ffb454",  # orange
    "unhealthy": "#ff6b6b", # red
    "unknown": "#8fa3bb",   # gray
}

SERVICE_NAMES = {
    "supermemory": "Supermemory",
    "brain-ui": "Brain UI",
    "headroom-proxy": "Headroom",
    "postgres": "PostgreSQL",
    "qdrant": "Qdrant",
    "redis": "Redis",
    "traefik": "Traefik",
}


# =============================================================================
# Icon Generation
# =============================================================================

def create_icon(status: str, count: int = 0) -> Image.Image:
    """Generate a colored tray icon with optional badge."""
    color = COLORS.get(status, COLORS["unknown"])
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main circle
    margin = 4
    draw.ellipse(
        [margin, margin, ICON_SIZE - margin, ICON_SIZE - margin],
        fill=color,
        outline="#0b0f14",
        width=2
    )

    # Brain symbol (simplified)
    cx, cy = ICON_SIZE // 2, ICON_SIZE // 2
    draw.ellipse([cx - 12, cy - 10, cx + 12, cy + 10], outline="#0b0f14", width=2)
    draw.line([cx - 8, cy, cx + 8, cy], fill="#0b0f14", width=2)
    draw.line([cx, cy - 6, cx, cy + 6], fill="#0b0f14", width=2)

    # Badge with count
    if count > 0:
        badge_text = str(min(count, 99))
        badge_color = "#ff6b6b" if count > 50 else "#ffb454" if count > 10 else "#00e6a8"
        text_bbox = draw.textbbox((0, 0), badge_text)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        bx, by = ICON_SIZE - 4 - text_w - 6, 4
        draw.rounded_rectangle(
            [bx - 4, by - 2, bx + text_w + 4, by + text_h + 2],
            radius=8, fill=badge_color
        )
        draw.text((bx, by), badge_text, fill="#0b0f14", font_size=11)

    return img


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
            return {"status": "healthy" if r.ok else "unhealthy", "data": r.json()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def overview(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/api/overview")
            return {"status": "healthy" if r.ok else "unhealthy", "data": r.json()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def autopilot_status(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/api/autopilot/status")
            return {"status": "healthy" if r.ok else "unhealthy", "data": r.json()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# =============================================================================
# Notifications
# =============================================================================

def notify(title: str, message: str, level: str = "info"):
    """Cross-platform desktop notification."""
    system = sys.platform

    if system == "win32" and HAS_WINTOAST:
        ToastNotifier().show_toast(title, message, duration=5)
    elif system == "darwin" and HAS_PYNC:
        Notifier.notify(message, title=title)
    elif system.startswith("linux"):
        try:
            subprocess.run(["notify-send", "-u", "normal", title, message], check=False)
        except FileNotFoundError:
            pass
    # Fallback: print to console
    print(f"[{level.upper()}] {title}: {message}")


# =============================================================================
# Tray Application
# =============================================================================

class MemoryTray:
    def __init__(self):
        self.api = MemoryAPI(API_BASE)
        self.icon: Optional[pystray.Icon] = None
        self.running = True
        self.last_data: Dict[str, Any] = {}
        self.memory_count = 0
        self.tokens_saved = 0
        self.services_up = 0
        self.services_total = 0

    def fetch_data(self):
        """Fetch latest data from API."""
        overview = self.api.overview()
        health = self.api.health()
        autopilot = self.api.autopilot_status()

        self.last_data = {
            "overview": overview,
            "health": health,
            "autopilot": autopilot,
        }

        if overview.get("status") == "healthy" and overview.get("data"):
            data = overview["data"]
            sm = data.get("supermemory", {})
            self.memory_count = sm.get("memories", 0)
            self.tokens_saved = data.get("tokens", {}).get("saved", 0)

            # Count healthy services
            services = [
                ("supermemory", sm.get("up", False)),
                ("qdrant", data.get("qdrant", {}).get("up", False)),
                ("redis", data.get("redis", {}).get("up", False)),
                ("postgres", data.get("postgres", {}).get("up", False)),
                ("headroom-proxy", data.get("headroom", {}).get("up", False)),
            ]
            self.services_up = sum(1 for _, up in services if up)
            self.services_total = len(services)

    def compute_overall_status(self) -> str:
        """Determine overall status for icon color."""
        if self.services_up == 0:
            return "unhealthy"
        if self.services_up == self.services_total:
            return "healthy"
        return "degraded"

    def update_icon(self):
        """Update tray icon based on current status."""
        if not self.icon:
            return
        status = self.compute_overall_status()
        self.icon.icon = create_icon(status, self.memory_count)
        self.icon.title = self.build_tooltip()

    def build_tooltip(self) -> str:
        """Build hover tooltip text."""
        lines = [
            f"Unified Memory Stack",
            f"Memories: {self.memory_count:,}",
            f"Tokens saved: {self.tokens_saved:,}",
            f"Services: {self.services_up}/{self.services_total} healthy",
            "",
            "Click to open dashboard",
            "Right-click for menu",
        ]
        return "\n".join(lines)

    def build_menu(self):
        """Build right-click context menu."""
        items = [
            pystray.MenuItem(
                "Open Dashboard",
                self.open_dashboard,
                default=True
            ),
            pystray.MenuItem(
                f"Services: {self.services_up}/{self.services_total} UP",
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
        ]

        # Add per-service status
        if self.last_data.get("overview", {}).get("data"):
            data = self.last_data["overview"]["data"]
            services = [
                ("supermemory", "Supermemory", data.get("supermemory", {}).get("up")),
                ("qdrant", "Qdrant", data.get("qdrant", {}).get("up")),
                ("redis", "Redis", data.get("redis", {}).get("up")),
                ("postgres", "PostgreSQL", data.get("postgres", {}).get("up")),
                ("headroom-proxy", "Headroom", data.get("headroom", {}).get("up")),
            ]
            for key, name, up in services:
                status = "●" if up else "○"
                items.append(pystray.MenuItem(
                    f"{status} {name}",
                    None,
                    enabled=False
                ))

        items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh Now", self.force_refresh),
            pystray.MenuItem("View Logs", self.view_logs),
            pystray.MenuItem("Restart Stack", self.restart_stack),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit),
        ])
        return pystray.Menu(*items)

    def open_dashboard(self, icon=None, item=None):
        webbrowser.open(f"{API_BASE}")

    def force_refresh(self, icon=None, item=None):
        self.fetch_data()
        self.update_icon()

    def view_logs(self, icon=None, item=None):
        try:
            subprocess.Popen(["docker", "compose", "logs", "-f", "--tail", "100"],
                           cwd=Path(__file__).parent.parent.parent)
        except Exception:
            notify("Error", "Could not open logs. Run 'docker compose logs -f' manually.")

    def restart_stack(self, icon=None, item=None):
        try:
            subprocess.run(["docker", "compose", "restart"],
                         cwd=Path(__file__).parent.parent.parent, check=True)
            notify("Memory Stack", "Restarting all services...")
            time.sleep(5)
            self.force_refresh()
        except Exception as e:
            notify("Error", f"Restart failed: {e}", "error")

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
        """Start the tray application."""
        # Initial fetch
        self.fetch_data()

        # Create initial icon
        status = self.compute_overall_status()
        initial_icon = create_icon(status, self.memory_count)

        # Create tray icon
        self.icon = pystray.Icon(
            "unified-memory-stack",
            initial_icon,
            "Unified Memory Stack",
            self.build_menu()
        )

        # Start refresh thread
        refresh_thread = threading.Thread(target=self.refresh_loop, daemon=True)
        refresh_thread.start()

        # Run icon (blocks until quit)
        self.icon.run()


# =============================================================================
# Entry Point
# =============================================================================

def main():
    # Allow override via command line
    global API_BASE
    if len(sys.argv) > 1:
        API_BASE = sys.argv[1]

    print(f"Starting Memory Tray Widget")
    print(f"API Base: {API_BASE}")
    print(f"Refresh interval: {REFRESH_INTERVAL}s")

    try:
        app = MemoryTray()
        app.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()