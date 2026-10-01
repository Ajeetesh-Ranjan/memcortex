#!/usr/bin/env python3
"""AI Architecture Lab — bar-widget collector for the Unified Memory Stack.

Fetches the Brain UI's /api/overview and /api/brain endpoints and writes a
single bounded JSON snapshot that the QML panel reads.

The QML side never talks HTTP itself (Quickshell has no fetch), it shells out
to this script and re-reads the file, matching the pattern used by the other
Omarchy bar widgets.

Usage:
    aal-brain-collector.py [--out PATH] [--api URL] [--timeout SEC]

Exit codes: 0 on success (including a "degraded" snapshot when the stack is
down, so the panel can show a real outage instead of freezing on stale data).
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_API = os.environ.get("MEMORY_API_BASE", "http://localhost:8080")


def _load_token():
    """Find the operator credential.

    The environment variable is checked first, but it cannot be the only
    source: this collector is normally launched by the panel process, and a
    panel manager started at login inherits nothing from an interactive shell.
    So exporting MEMORY_API_TOKEN in .bashrc does not reach it, the API
    answers 401, and the widget renders an empty brain -- which looks exactly
    like an empty account.

    Fall back to a dotenv file, preferring an explicit path and then the
    per-user one written by the stack installer.
    """
    tok = os.environ.get("MEMORY_API_TOKEN", "").strip()
    if tok:
        return tok

    candidates = []
    if os.environ.get("MEMCORTEX_ENV_FILE"):
        candidates.append(os.environ["MEMCORTEX_ENV_FILE"])
    candidates.append(os.path.join(
        os.path.expanduser("~/.config/memcortex"), "env"))
    if os.environ.get("MEMORY_STACK_DIR"):
        candidates.append(os.path.join(os.environ["MEMORY_STACK_DIR"], ".env"))

    for path in candidates:
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if v and k in ("MEMORY_API_TOKEN",
                                   "BRAIN_UI_SERVICE_TOKEN"):
                        return v
        except OSError:
            continue
    return ""


MEMORY_API_TOKEN = _load_token()
DEFAULT_OUT = os.path.join(
    os.environ.get("XDG_STATE_HOME",
                   os.path.expanduser("~/.local/state")),
    "aial-memory-brain", "snapshot.json")

# The panel draws every subject and agent; keep the file small so the QML
# reader never has to deal with a huge payload.
MAX_AGENTS = 12
MAX_RECENT = 5

# --- live process discovery -------------------------------------------------
#
# /api/brain only knows about agents that have written an agent_sessions row,
# which means a manually-inserted session and nothing else. A real agent CLI
# that is running right now -- hermes, opencode, codex -- is invisible to that
# path. The collector runs on the host, so it can simply look.
#
# Everything here is read-only from /proc; no subprocess is spawned, which also
# means the scan cannot match itself.

# Executable basename -> canonical agent name.
EXE_AGENTS = {
    "opencode": "opencode",
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
    "crush": "crush",
    "aider": "aider",
    "goose": "goose",
    "copilot": "copilot",
    "amp": "amp",
    "hermes": "hermes",
    "cursor-agent": "cursor",
}

# Agents whose real process is a wrapper interpreter, so argv[0] is
# python/node and only the cmdline carries the agent identity.
CMDLINE_HINTS = {
    "hermes": ("hermes_cli", "hermes-agent", "hermes_bootstrap"),
    "claude": ("claude_code", "claude-code"),
    "opencode": ("opencode-ai", "opencode_cli"),
}

INTERPRETERS = {"python", "python3", "node", "bun", "deno"}
# Shells and text utilities are excluded outright: the scanner's own shell
# commands mention agent names in their arguments and would self-match.
SHELLS = {"bash", "sh", "zsh", "fish", "dash"}
UTILITIES = {"grep", "egrep", "rg", "ps", "pgrep", "sed", "awk", "tr",
             "cut", "head", "tail", "fd", "find", "journalctl"}


def _exe_base(pid):
    try:
        return os.path.basename(os.readlink("/proc/%d/exe" % pid)).lower()
    except OSError:
        return ""


def _cmdline(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return f.read().decode("utf-8", "replace").replace("\x00", " ").strip()
    except OSError:
        return ""


def _start_ticks(pid):
    """Field 22 of /proc/pid/stat: process start time in clock ticks."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            data = f.read().decode("utf-8", "replace")
        rest = data[data.rindex(")") + 1:].split()
        return int(rest[19])
    except (OSError, ValueError, IndexError):
        return None


def discover_processes():
    """Return {agent: {pid, processes, uptime_s}} for agents running now."""
    try:
        boot = float(open("/proc/uptime").read().split()[0])
    except (OSError, ValueError, IndexError):
        boot = 0.0
    hz = os.sysconf("SC_CLK_TCK") or 100
    me = os.getpid()
    found = {}

    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == me:
            continue

        exe = _exe_base(pid)
        if exe in SHELLS or exe in UTILITIES:
            continue
        stem = exe.split(".")[0]
        if stem in SHELLS or stem in UTILITIES:
            continue

        cmd = _cmdline(pid)
        if not cmd or "aal-brain-collector" in cmd:
            continue

        name = EXE_AGENTS.get(exe) or EXE_AGENTS.get(stem)
        if name is None and stem in INTERPRETERS:
            for agent, hints in CMDLINE_HINTS.items():
                if any(h in cmd for h in hints):
                    name = agent
                    break
        if name is None:
            continue

        ticks = _start_ticks(pid)
        age = int(boot - ticks / hz) if ticks is not None else None

        rec = found.setdefault(name, {"processes": 0, "uptime_s": 0, "pid": pid})
        rec["processes"] += 1
        if age is not None and age > rec["uptime_s"]:
            rec["uptime_s"] = age
            rec["pid"] = pid

    return found


def merge_agents(db_agents, live):
    """Overlay process discovery onto the DB roster.

    A running process is ground truth: it flips a session to live and adds
    agents the database has never heard of. DB-only sessions are kept but
    marked stale so the panel can show the difference.
    """
    merged, seen = [], set()
    for a in db_agents or []:
        name = (a.get("type") or "unknown").lower()
        proc = live.get(name)
        row = dict(a)
        row["live"] = bool(proc)
        if proc:
            row["pid"] = proc["pid"]
            row["processes"] = proc["processes"]
            row["uptime_s"] = proc["uptime_s"]
        merged.append(row)
        seen.add(name)

    for name, proc in live.items():
        if name in seen:
            continue
        merged.append({
            "type": name, "status": "running", "model": "", "project": "",
            "live": True, "pid": proc["pid"],
            "processes": proc["processes"], "uptime_s": proc["uptime_s"],
        })

    merged.sort(key=lambda r: (not r.get("live"), r.get("type") or ""))
    return merged[:MAX_AGENTS]


def fmt_uptime(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 86400:
        return "%dh%02dm" % (seconds // 3600, (seconds % 3600) // 60)
    return "%dd%02dh" % (seconds // 86400, (seconds % 86400) // 3600)


def fetch(url, timeout):
    # The dashboard now requires a compartment credential. Without this header
    # every /api route answers 401 and the widget would silently show an empty
    # brain, which looks like a broken stack rather than a missing token.
    headers = {"Accept": "application/json"}
    token = MEMORY_API_TOKEN.strip()
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def pct(n, total):
    return round(100.0 * n / total) if total else 0


def slim_brain(brain):
    """Reduce /api/brain to exactly what the panel renders."""
    lobes = []
    for l in (brain or {}).get("lobes") or []:
        lobes.append({
            "subject": l.get("subject"),
            "lobe": l.get("lobe"),
            "role": l.get("role"),
            "color": l.get("color") or "#4A4F55",
            "memories": l.get("memories") or 0,
            "share": l.get("share") or 0.0,
            "imp": l.get("avg_importance") or 0.0,
        })
    total = (brain or {}).get("total") or 0
    for l in lobes:
        l["pct"] = pct(l["memories"], total)

    agents = [{
        "type": a.get("agent_type") or "unknown",
        "status": a.get("status") or "unknown",
        "model": a.get("model") or "",
        "project": a.get("project_id") or "",
    } for a in ((brain or {}).get("agents") or [])][:MAX_AGENTS]

    return {
        "lobes": lobes,
        "total": total,
        "classified": (brain or {}).get("classified") or 0,
        "unclassified": (brain or {}).get("unclassified") or 0,
        "source": (brain or {}).get("source") or "empty",
        "agents": agents,
    }


def slim_overview(o):
    return {
        "supermemory": {"up": o["supermemory"]["up"],
                        "memories": o["supermemory"].get("memories", 0),
                        "documents": o["supermemory"].get("documents", 0)},
        "qdrant": {"up": o["qdrant"]["up"],
                   "points": o["qdrant"].get("points", 0)},
        "postgres": {"up": o["postgres"]["up"],
                     "bytes": o["postgres"].get("db_bytes", 0),
                     "tables": o["postgres"].get("tables") or {}},
        "redis": {"up": o["redis"]["up"],
                  "keys": o["redis"].get("keys", 0)},
        "headroom": {"up": o["headroom"]["up"]},
        "tokens": {"saved": o["tokens"].get("saved", 0),
                   "ratio": o["tokens"].get("ratio", 0.0)},
    }


def build(api, timeout):
    snap = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api": api,
        "ok": False,
    }
    try:
        overview = fetch(f"{api}/api/overview", timeout)
        snap["overview"] = slim_overview(overview)
        snap["ok"] = True
    except Exception as e:
        snap["error"] = f"overview: {type(e).__name__}: {e}"[:160]
        snap["overview"] = None

    try:
        brain = fetch(f"{api}/api/brain", timeout)
        slim = slim_brain(brain)
        # Host process discovery is independent of the API: if /api/brain is
        # down we still report which agents are genuinely running.
        slim["agents"] = merge_agents(slim.get("agents"), discover_processes())
        # Attach telemetry to the process-detected roster.
        tel = None
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import aal_agent_telemetry
            tel = aal_agent_telemetry.collect()
        except Exception:
            tel = {}
        for a in slim["agents"]:
            a["uptime"] = fmt_uptime(a.get("uptime_s"))
            t = (tel or {}).get((a.get("type") or "").lower()) or {}
            a["modules"] = (t.get("modules") or [])[:6]
            a["models"] = (t.get("models") or [])[:4]
            a["tokens"] = t.get("tokens")
            a["context_pct"] = t.get("context_pct") or 0
            a["multi_sessions"] = t.get("multi_sessions") or []
            a["telemetry"] = (t.get("sessions") or [])[:MAX_AGENTS]
        snap["brain"] = slim
    except Exception as e:
        snap.setdefault("error", f"brain: {type(e).__name__}: {e}"[:160])
        snap["brain"] = None

    try:
        snap["live_agents"] = sorted(discover_processes())
    except Exception:
        snap["live_agents"] = []

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aal_agent_telemetry
        snap["telemetry"] = aal_agent_telemetry.collect()
    except Exception as e:
        snap["telemetry"] = {}
        snap.setdefault("error", f"telemetry: {type(e).__name__}: {e}"[:160])

    try:
        ap = fetch(f"{api}/api/autopilot/value", timeout)
        # /api/autopilot/value wraps the rows: {"value_summary": [...]}
        if isinstance(ap, dict):
            rows = ap.get("value_summary") or []
        else:
            rows = ap or []
        snap["autopilot"] = {
            "actions": sum((r.get("runs") or 0) for r in rows),
            "auto_fixed": sum((r.get("auto_fixed") or 0) for r in rows),
        }
    except Exception:
        snap["autopilot"] = None

    return snap


def write_atomic(path, obj):
    """Write via temp+rename so the QML reader never sees a half-written file."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".snapshot-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--timeout", type=float, default=4.0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    snap = build(a.api.rstrip("/"), a.timeout)
    write_atomic(a.out, snap)
    if not a.quiet:
        b = snap.get("brain") or {}
        o = snap.get("overview") or {}
        print(f"ok={snap['ok']} total={b.get('total', 0)} "
              f"lobes={len(b.get('lobes') or [])} "
              f"agents={len(b.get('agents') or [])} "
              f"memories={o.get('supermemory', {}).get('memories', '-')}")
    # Always exit 0: a down stack is reportable data, not a collector failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
