#!/usr/bin/env python3
"""Per-agent token, context and module telemetry for the AAI bar widget.

Reads whatever the agent CLIs already persist on disk. Nothing here writes,
and nothing spawns a subprocess, so it is safe to run on a timer:

    opencode   ~/.local/share/opencode/opencode.db   (SQLite, session+message)
    codex      ~/.codex/sessions/**/*.jsonl           (token_count events)
    claude     ~/.claude/projects/**/*.jsonl           (assistant usage blocks)
    hermes     ~/.hermes/sessions/request_dump_*.json  (model + failures)

The point of this module is that /api/brain only knows about agents that wrote
an agent_sessions row. These readers see agents that are actually running.
"""

import glob
import json
import os
import sqlite3
import time

HOME = os.path.expanduser("~")

# Context windows are not recorded by every CLI, so fall back to a lookup and
# mark the result as estimated rather than pretending it is exact.
CONTEXT_LIMITS = {
    "gemini": 1048576,
    "gpt-6": 400000,
    "qwen3": 262144,
    "glm-5": 200000,
    "kilo": 200000,
    "opus": 200000,
    "sonnet": 200000,
    "haiku": 200000,
    "gpt-5": 400000,
}
DEFAULT_LIMIT = 200000

TAIL_BYTES = 400_000  # read only the tail of a JSONL; sessions can be huge
MAX_SESSIONS = 3


def _limit_for(model):
    m = (model or "").lower()
    for key, val in CONTEXT_LIMITS.items():
        if key in m:
            return val, False
    return DEFAULT_LIMIT, True


def _ctx(used, limit):
    used = int(used or 0)
    pct = round(100.0 * used / limit) if limit else 0
    return {"used": used, "limit": limit, "pct": max(0, min(pct, 100)),
            "free": max(0, limit - used)}


def _tokens(**kw):
    t = {k: int(kw.get(k) or 0) for k in
         ("input", "output", "reasoning", "cache_read", "cache_write")}
    t["total"] = sum(t.values())
    return t


def _tail(path, nbytes=TAIL_BYTES):
    """Read the last nbytes of a text file without loading all of it."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > nbytes:
                f.seek(size - nbytes)
                f.readline()  # discard the partial first line
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _ago(ts):
    if not ts:
        return ""
    d = max(0, time.time() - ts)
    if d < 60:
        return "%ds" % d
    if d < 3600:
        return "%dm" % (d // 60)
    if d < 86400:
        return "%dh%02dm" % (d // 3600, (d % 3600) // 60)
    return "%dd" % (d // 86400)


def _alerts_for(ctx, models, agents):
    """Turn raw state into things a human should act on."""
    out = []
    if ctx["pct"] >= 90:
        out.append({"level": "error",
                    "text": "context %d%% full — compact or switch module" % ctx["pct"]})
    elif ctx["pct"] >= 75:
        out.append({"level": "warn",
                    "text": "context %d%% used — plan a compaction" % ctx["pct"]})
    if len(models) > 1:
        out.append({"level": "info",
                    "text": "auto-switched models: " + " → ".join(models[:4])})
    if len(agents) > 1:
        out.append({"level": "info",
                    "text": "modules used: " + ", ".join(agents[:4])})
    return out


# --------------------------------------------------------------- opencode

def opencode_telemetry():
    path = os.path.join(HOME, ".local/share/opencode/opencode.db")
    if not os.path.exists(path):
        return []
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=2)
    except sqlite3.Error:
        return []
    sessions = []
    try:
        rows = con.execute(
            "SELECT id, title, agent, model, tokens_input, tokens_output,"
            " tokens_reasoning, tokens_cache_read, tokens_cache_write,"
            " time_updated FROM session ORDER BY time_updated DESC LIMIT ?",
            (MAX_SESSIONS,)).fetchall()

        for (sid, title, agent, model, ti, to, tr, cr, cw, upd) in rows:
            # A session's "modules" are the opencode agent modes it ran, and
            # its context is the last assistant turn, not the cumulative sum.
            mods = [r[0] for r in con.execute(
                "SELECT DISTINCT json_extract(data,'$.agent') FROM message"
                " WHERE session_id=? AND json_extract(data,'$.agent') IS NOT NULL",
                (sid,))]
            mdls = [r[0] for r in con.execute(
                "SELECT DISTINCT json_extract(data,'$.model.modelID') FROM message"
                " WHERE session_id=? AND json_extract(data,'$.model.modelID') IS NOT NULL",
                (sid,))]
            last = con.execute(
                "SELECT data FROM message WHERE session_id=? AND"
                " json_extract(data,'$.role')='assistant'"
                " ORDER BY time_updated DESC LIMIT 1", (sid,)).fetchone()

            used = 0
            if last:
                try:
                    t = (json.loads(last[0]) or {}).get("tokens") or {}
                    cache = t.get("cache") or {}
                    used = (t.get("input") or 0) + (t.get("output") or 0) \
                        + (t.get("reasoning") or 0) + (cache.get("read") or 0)
                except (ValueError, TypeError):
                    used = 0

            limit, est = _limit_for(model)
            ctx = _ctx(used, limit)
            ctx["estimated"] = est
            sessions.append({
                "id": sid, "title": title or sid[:8],
                "updated": _ago((upd or 0) / 1000.0),
                "modules": mods, "models": mdls,
                "multi": len(mods) > 1 or len(mdls) > 1,
                "tokens": _tokens(input=ti, output=to, reasoning=tr,
                                  cache_read=cr, cache_write=cw),
                "context": ctx,
                "alerts": _alerts_for(ctx, mdls, mods),
            })
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return sessions


# ------------------------------------------------------------------- codex

def codex_telemetry():
    files = glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True)
    if not files:
        return []
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    sessions = []
    for path in files[:MAX_SESSIONS]:
        info, models = None, []
        for line in _tail(path).splitlines():
            if '"token_count"' not in line:
                continue
            try:
                payload = json.loads(line).get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
            except ValueError:
                continue
        for line in _tail(path, 120_000).splitlines():
            if '"model"' in line:
                try:
                    m = json.loads(line)
                    name = m.get("model") or (m.get("payload") or {}).get("model")
                    if name and name not in models:
                        models.append(name)
                except ValueError:
                    pass
        if not info:
            continue
        total = info.get("total_token_usage") or {}
        last = info.get("last_token_usage") or {}
        limit = int(info.get("model_context_window") or 0) or DEFAULT_LIMIT
        ctx = _ctx(last.get("total_tokens"), limit)
        ctx["estimated"] = "model_context_window" not in info
        sessions.append({
            "id": os.path.basename(path).replace("rollout-", "").replace(".jsonl", "")[:12],
            "title": os.path.basename(path)[:34],
            "updated": _ago(os.path.getmtime(path)),
            "modules": [], "models": models,
            "multi": len(models) > 1,
            "tokens": _tokens(input=total.get("input_tokens"),
                              output=total.get("output_tokens"),
                              reasoning=total.get("reasoning_output_tokens"),
                              cache_read=total.get("cached_input_tokens"),
                              cache_write=total.get("cache_write_input_tokens")),
            "context": ctx,
            "alerts": _alerts_for(ctx, models, []),
        })
    return sessions


# ------------------------------------------------------------------ claude

def claude_telemetry():
    files = glob.glob(os.path.join(HOME, ".claude/projects/**/*.jsonl"), recursive=True)
    if not files:
        return []
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    sessions = []
    for path in files[:MAX_SESSIONS]:
        agg = _tokens()
        last_used, models = 0, []
        for line in _tail(path).splitlines():
            if '"usage"' not in line:
                continue
            try:
                msg = json.loads(line).get("message") or {}
            except ValueError:
                continue
            if msg.get("model") and msg["model"] not in models:
                models.append(msg["model"])
            u = msg.get("usage") or {}
            agg["input"] += u.get("input_tokens") or 0
            agg["output"] += u.get("output_tokens") or 0
            agg["cache_read"] += u.get("cache_read_input_tokens") or 0
            agg["cache_write"] += u.get("cache_creation_input_tokens") or 0
            agg["total"] = (agg["input"] + agg["output"] + agg["reasoning"]
                            + agg["cache_read"] + agg["cache_write"])
            last_used = ((u.get("input_tokens") or 0)
                         + (u.get("cache_read_input_tokens") or 0)
                         + (u.get("output_tokens") or 0))
        if agg["total"] == 0:
            continue
        model = models[-1] if models else ""
        limit, est = _limit_for(model)
        ctx = _ctx(last_used, limit)
        ctx["estimated"] = est
        sessions.append({
            "id": os.path.basename(path).replace(".jsonl", "")[:12],
            "title": os.path.basename(os.path.dirname(path)),
            "updated": _ago(os.path.getmtime(path)),
            "modules": [], "models": models,
            "multi": len(models) > 1,
            "tokens": agg, "context": ctx,
            "alerts": _alerts_for(ctx, models, []),
        })
    return sessions


# ------------------------------------------------------------------ hermes

def hermes_telemetry():
    """Hermes dumps each outbound request on failure.

    That makes the failure path the interesting one: a dump means the model
    panel is unhappy, which is exactly the 'needs a different module' signal.
    """
    files = glob.glob(os.path.join(HOME, ".hermes/sessions/request_dump_*.json"))
    if not files:
        return []
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    grouped, alerts, models, newest = {}, [], set(), 0.0
    for path in files[:12]:
        try:
            d = json.load(open(path))
        except (OSError, ValueError):
            continue
        newest = max(newest, os.path.getmtime(path))
        sid = d.get("session_id") or "hermes"
        body = (d.get("request") or {}).get("body") or {}
        model = body.get("model") or ""
        if model:
            models.add(model)
        msgs = len(body.get("messages") or [])
        grouped[sid] = max(grouped.get(sid, 0), msgs)

        err = d.get("error") or {}
        msg = str(err.get("message") or "")[:220]
        if msg:
            alerts.append({"level": "error",
                           "text": "%s: %s" % (d.get("reason") or "error", msg),
                           "when": _ago(os.path.getmtime(path))})

    if not alerts and not grouped:
        return []

    # Hermes does not persist usage in the dump; be explicit about that rather
    # than inventing a number from the message count.
    ctx = _ctx(0, 0)
    ctx["messages"] = max(grouped.values()) if grouped else 0
    ctx["unknown"] = True
    sessions = [{
        "id": "hermes", "title": "gateway",
        "updated": _ago(newest),
        "modules": sorted(models), "models": sorted(models),
        "multi": len(models) > 1,
        "tokens": None, "context": ctx,
        "alerts": alerts[:3],
    }]
    return sessions


READERS = {
    "opencode": opencode_telemetry,
    "codex": codex_telemetry,
    "claude": claude_telemetry,
    "hermes": hermes_telemetry,
}


def collect(only=None):
    """Return {agent: {"sessions": [...], "modules": [...], "alerts": [...]}}."""
    out = {}
    for name, fn in READERS.items():
        if only and name not in only:
            continue
        try:
            sessions = fn()
        except Exception:
            sessions = []
        if not sessions:
            continue
        mods, mdls, alerts = [], [], []
        for s in sessions:
            for m in s.get("modules") or []:
                if m not in mods:
                    mods.append(m)
            for m in s.get("models") or []:
                if m not in mdls:
                    mdls.append(m)
            alerts.extend(s.get("alerts") or [])
        top = max((s.get("context") or {}).get("pct", 0) for s in sessions)
        tok = _tokens()
        has_tok = False
        for s in sessions:
            if s.get("tokens"):
                has_tok = True
                for k, v in s["tokens"].items():
                    tok[k] += v
        out[name] = {
            "sessions": sessions,
            "modules": mods,
            "models": mdls,
            "tokens": tok if has_tok else None,
            "context_pct": top,
            "multi_sessions": [s["id"] for s in sessions if s.get("multi")],
            "alerts": alerts[:4],
        }
    return out
