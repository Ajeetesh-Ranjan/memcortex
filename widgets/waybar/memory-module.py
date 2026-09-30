#!/usr/bin/env python3
"""
Unified Memory Stack — Waybar Module for Omarchy/Hyprland/Sway

Outputs JSON for waybar with:
- Custom icon/color based on stack health
- Tooltip with detailed status
- Click to open dashboard
- Right-click menu (requires waybar 0.9.20+)

Add to waybar config:
```json
"custom/memory": {
    "exec": "~/.config/waybar/scripts/memory-module.py",
    "interval": 30,
    "format": "{}",
    "return-type": "json",
    "on-click": "xdg-open http://localhost:8080",
    "on-click-right": "~/.config/waybar/scripts/memory-module.py --menu"
}
```

Requirements: pip install requests
"""

import sys
import json
import os
import subprocess
from pathlib import Path

import requests


API_BASE = os.environ.get("MEMORY_API_BASE", "http://localhost:8080")
BRAND = "The AI Architecture Lab"
ICON_HEALTHY = "󰗠"  # brain
ICON_DEGRADED = "󰗟"  # brain with warning
ICON_UNHEALTHY = "󰖂"  # brain off
ICON_UNKNOWN = "󰋗"   # question

COLORS = {
    "healthy": "#00e6a8",
    "degraded": "#ffb454",
    "unhealthy": "#ff6b6b",
    "unknown": "#8fa3bb",
}


def fetch_overview():
    try:
        r = requests.get(f"{API_BASE}/api/overview", timeout=3)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def fetch_health():
    try:
        r = requests.get(f"{API_BASE}/healthz", timeout=2)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def fetch_autopilot():
    try:
        r = requests.get(f"{API_BASE}/api/autopilot/status", timeout=3)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def fetch_brain():
    try:
        r = requests.get(f"{API_BASE}/api/brain", timeout=3)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def brain_lines(brain):
    """Top subjects by memory share, with the bound anatomical lobe."""
    if not brain or not brain.get("lobes"):
        return []
    total = brain.get("total") or 0
    lobes = sorted(brain["lobes"],
                   key=lambda l: l.get("memories", 0), reverse=True)
    out = []
    for l in lobes:
        n = l.get("memories", 0)
        if not n:
            continue
        pct = round(100.0 * n / total) if total else 0
        out.append(f"  ● {l['subject']:<13} {n:>6,} ({pct:>2}%)  {l['lobe']}")
    return out


def compute_status(data):
    """Determine overall status from overview data."""
    if not data:
        return "unknown", ICON_UNKNOWN

    services = [
        data.get("supermemory", {}).get("up", False),
        data.get("qdrant", {}).get("up", False),
        data.get("redis", {}).get("up", False),
        data.get("postgres", {}).get("up", False),
        data.get("headroom", {}).get("up", False),
    ]

    up = sum(1 for s in services if s)
    total = len(services)

    if up == 0:
        return "unhealthy", ICON_UNHEALTHY
    if up == total:
        return "healthy", ICON_HEALTHY
    return "degraded", ICON_DEGRADED


def build_tooltip(data, health, autopilot, brain=None):
    """Build detailed tooltip."""
    if not data:
        return "Unified Memory Stack — Unreachable"

    sm = data.get("supermemory", {})
    qd = data.get("qdrant", {})
    rd = data.get("redis", {})
    pg = data.get("postgres", {})
    hr = data.get("headroom", {})
    tk = data.get("tokens", {})

    services = [
        ("Supermemory", sm.get("up")),
        ("Qdrant", qd.get("up")),
        ("Redis", rd.get("up")),
        ("PostgreSQL", pg.get("up")),
        ("Headroom", hr.get("up")),
    ]

    lines = [
        f"{BRAND} — Unified Memory Stack",
        f"Memories: {sm.get('memories', 0):,} ({sm.get('static', 0)} static, {sm.get('dynamic', 0)} dynamic)",
        f"Documents: {sm.get('documents', 0):,}",
        f"Tokens saved: {tk.get('saved', 0):,} ({tk.get('ratio', 0)*100:.1f}%)",
        "",
        "Services:",
    ]

    for name, up in services:
        status = "●" if up else "○"
        lines.append(f"  {status} {name}")

    if brain:
        lines.extend(["", f"Brain — {brain.get('total', 0):,} memories "
                          f"({brain.get('classified', 0)} classified)"])
        bl = brain_lines(brain)
        lines.extend(bl or ["  no classified memories yet"])
        agents = brain.get("agents") or []
        if agents:
            act = sum(1 for a in agents if a.get("status") == "active")
            lines.extend(["", f"Agents: {len(agents)} registered, {act} active"])
            for a in agents[:4]:
                lines.append(f"  {'●' if a.get('status') == 'active' else '○'} "
                             f"{a.get('agent_type')}"
                             f"{' · ' + a['model'] if a.get('model') else ''}")

    if autopilot and autopilot.get("enabled"):
        recent = autopilot.get("recent") or []
        lines.extend(["", f"Autopilot: enabled, {len(recent)} recent actions"])

    return "\n".join(lines)


def print_menu():
    """Print right-click menu JSON for waybar."""
    menu = [
        {"label": "Open Brain Monitor", "command": f"xdg-open {API_BASE}"},
        {"label": "Refresh", "command": f"pkill -RTMIN+10 waybar"},
        {"label": "View Logs", "command": "kitty -e docker compose logs -f --tail 100"},
        {"label": "Restart Stack", "command": "docker compose restart"},
        {"label": "Quit", "command": "pkill waybar"},
    ]
    print(json.dumps(menu))


def main():
    # Handle menu request
    if "--menu" in sys.argv:
        print_menu()
        return

    overview = fetch_overview()
    health = fetch_health()
    autopilot = fetch_autopilot()
    brain = fetch_brain()

    if overview:
        status, icon = compute_status(overview)
        tooltip = build_tooltip(overview, health, autopilot, brain)
        color = COLORS.get(status, COLORS["unknown"])
    else:
        status = "unknown"
        icon = ICON_UNKNOWN
        tooltip = "Unified Memory Stack — Unreachable"
        color = COLORS["unknown"]

    output = {
        "text": f" {icon} ",
        "tooltip": tooltip,
        "class": f"memory-{status}",
        "percentage": 100 if status == "healthy" else 50 if status == "degraded" else 0,
    }

    # Add CSS for coloring
    css = f"""
    #custom-memory.memory-healthy {{ color: {COLORS['healthy']}; }}
    #custom-memory.memory-degraded {{ color: {COLORS['degraded']}; }}
    #custom-memory.memory-unhealthy {{ color: {COLORS['unhealthy']}; }}
    #custom-memory.memory-unknown {{ color: {COLORS['unknown']}; }}
    """

    # Print JSON for waybar
    print(json.dumps(output))


if __name__ == "__main__":
    main()