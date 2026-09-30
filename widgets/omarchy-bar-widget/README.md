# AI Architecture Lab — Memory Brain (Omarchy bar widget)

A live Unified Memory Stack widget for the Omarchy desktop bar. Left click
opens a panel with a **segmented brain** of your memory by subject, database
health, the agents currently registered, and the value the stack has delivered.
Right click jumps to the Brain Monitor dashboard.

## What it shows

| Section | Source |
|---|---|
| Service pills (Supermemory, Qdrant, Redis, PostgreSQL, Headroom) | `GET /api/overview` |
| Segmented brain — lobe size/glow scale with each subject's share | `GET /api/brain` |
| Memory by subject (count, %, anatomical lobe) | `GET /api/brain` |
| Agents registered / active, with model | `GET /api/brain` |
| Value delivered (memories, tokens saved, autopilot actions, docs) | `/api/overview`, `/api/autopilot/value` |

## Subjects and lobes

`brain-ui/brain_taxonomy.py` maps memory into seven subjects, each bound to an
anatomical lobe. Classification is keyword-scored and deterministic — no model
call, so it is instant, free, and works offline.

| Subject | Anatomical lobe | Role |
|---|---|---|
| Architecture | Frontal Lobe | System design, patterns, decisions |
| Code | Parietal Lobe | Source, refactors, tests, debugging |
| Data | Temporal Lobe | Datasets, embeddings, indexes, storage |
| Security | Cerebellum | Credentials, TLS, access control, secrets |
| Operations | Brainstem | Deploys, health, incidents, automation |
| Research | Occipital Lobe | Notes, papers, experiments, decisions |
| General | Association Cortex | Unclassified / cross-cutting |

## Install

```bash
./install.sh
omarchy plugin enable io.github.aial.memory-brain
```

Then restart the bar shell:

```bash
kill "$(pgrep -f 'quickshell -n -p /usr/share/omarchy/shell' | head -1)"
```

Hyprland's `exec-once` brings it straight back.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MEMORY_API_BASE` | `http://localhost:8080` | Brain UI base URL (also used by the collector) |
| refresh interval | 30s | `refreshSec` in `Panel.qml` |

The collector writes a bounded snapshot (currently ~2 KB) to
`$XDG_STATE_HOME/aial-memory-brain/snapshot.json`, read by the panel through
`head -c` so a malformed or oversized file can never stall the bar.

## Files

- `manifest.json` — plugin descriptor (`kinds: ["bar-widget"]`)
- `BarWidget.qml` — bar glyph, tooltip, panel loader
- `Panel.qml` — the panel: brain (`QtQuick.Shapes` + `PathSvg`), subjects, agents, value
- `bin/aal-brain-collector.py` — stdlib-only collector, no third-party deps
- `assets/logo-32.png` — The AI Architecture Lab mark

## Notes

- The brain geometry is the same lateral-view path data as
  `widgets/brain3d/brain-svg.js` used by the dashboard and the HTML widget, so
  all three renderings line up.
- QML has no `fetch`; the panel shells out to the collector and re-reads the
  snapshot, which is the pattern the other Omarchy bar widgets use.
- QML hot-reloads on file change, but it caches parsed QML aggressively. If a
  fix does not appear to take effect, restart the shell rather than waiting for
  a reload.
