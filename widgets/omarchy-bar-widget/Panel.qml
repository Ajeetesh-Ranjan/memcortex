import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

/*
  AI Architecture Lab — segmented brain panel.

  Reads the bounded JSON snapshot written by bin/aal-brain-collector.py and
  renders the same lateral-view anatomy as the dashboard's SVG brain, using
  QtQuick.Shapes PathSvg so the lobe geometry has a single definition.

  Lobe area, fill saturation and glow all scale with each subject's live share
  of stored memory, so the picture is a readout rather than decoration.
*/
Panel {
  id: root
  moduleName: "io.github.aial.memory-brain"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null

  property string apiBase: "http://localhost:8080"
  property int refreshSec: 30

  property var snap: null
  property string dataError: ""

  // Which agent nodes are open in the tree. Names, not indices, so the state
  // survives a refresh that reorders the roster.
  property var expanded: ["opencode", "codex", "hermes"]

  function isOpen(name) { return expanded.indexOf(name) >= 0 }
  function toggleAgent(name) {
    var next = expanded.slice()
    var i = next.indexOf(name)
    if (i >= 0) next.splice(i, 1)
    else next.push(name)
    expanded = next
  }

  // Resolve our own directory from this file rather than depending on the
  // host widget injecting a path: Panel.qml sits in the plugin root, so
  // Qt.resolvedUrl(".") is always correct even before the panel is injected.
  // The file:// scheme must be stripped -- Process.command needs a real path,
  // and "file:///..." silently fails to exec.
  readonly property string pluginDir: Qt.resolvedUrl(".").toString()
                                      .replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string collector: pluginDir + "/bin/aal-brain-collector.py"
  readonly property string snapshotPath: {
    var base = Quickshell.env("XDG_STATE_HOME")
    if (!base || base === "") base = Quickshell.env("HOME") + "/.local/state"
    return base + "/aial-memory-brain/snapshot.json"
  }

  // Theme colours. The shell exposes no `Theme` singleton; `Color` is the
  // singleton and the bar object (when present) carries the per-theme values.
  readonly property color foreground: (bar && bar.foreground) ? bar.foreground : Color.foreground
  readonly property color accent: Color.accent || foreground
  readonly property color surface: Color.popups.background
  readonly property color muted: Color.muted
  readonly property color dimText: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.55)
  readonly property color faint: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.14)
  readonly property color divider: faint
  readonly property string fontFamily: (bar && bar.fontFamily) ? bar.fontFamily : Style.font.family
  // The brand accent carried by the logo: warm sand.
  readonly property color brand: "#7A715F"

  // Ordered the same way as widgets/brain3d/brain-svg.js: the visual order of
  // the lobes in the lateral view, independent of the API's subject ordering.
  readonly property var lobeGeom: [
    { key: "Frontal Lobe",       path: "M132 300 C96 268 84 224 100 186 C118 142 168 112 224 108 C258 105 286 116 302 132 C276 150 254 176 244 208 C232 248 234 288 254 320 C212 330 168 322 132 300 Z", z: 3 },
    { key: "Parietal Lobe",      path: "M302 132 C286 116 258 105 224 108 C262 84 320 70 380 74 C430 77 470 96 494 124 C468 136 434 150 400 176 C362 206 330 224 302 232 C286 208 282 166 302 132 Z", z: 3 },
    { key: "Occipital Lobe",     path: "M494 124 C520 148 540 178 548 210 C556 244 552 276 540 302 C524 276 500 244 468 214 C444 192 418 176 400 176 C434 150 468 136 494 124 Z", z: 3 },
    { key: "Temporal Lobe",      path: "M244 232 C272 246 306 244 336 226 C372 204 408 190 446 192 C470 193 492 202 508 218 C486 246 456 274 420 296 C378 320 320 328 274 316 C258 296 250 266 244 232 Z", z: 4 },
    { key: "Association Cortex", path: "M282 156 C314 138 356 128 400 132 C436 136 466 150 484 172 C456 190 424 208 392 222 C352 240 306 240 276 224 C266 202 268 176 282 156 Z", z: 5 },
    { key: "Cerebellum",         path: "M540 300 C562 300 578 318 574 340 C570 362 548 378 524 374 C500 370 484 350 486 330 C488 312 512 300 540 300 Z", z: 2 },
    { key: "Brainstem",          path: "M296 318 C318 314 336 322 340 340 C344 358 336 376 320 384 C304 392 288 384 284 368 C280 350 284 326 296 318 Z", z: 2 }
  ]

  function lobeFor(key) {
    var lobes = (root.snap && root.snap.brain && root.snap.brain.lobes) || []
    for (var i = 0; i < lobes.length; i++)
      if (lobes[i].lobe === key) return lobes[i]
    return null
  }

  // log1p so a 1-memory subject stays visible next to a 10k one.
  function weightOf(n) {
    var brain = root.snap && root.snap.brain ? root.snap.brain : null
    if (!brain) return 0
    var max = 0
    for (var i = 0; i < brain.lobes.length; i++)
      if (brain.lobes[i].memories > max) max = brain.lobes[i].memories
    if (!n) return 0
    if (!max) return 0.25
    return Math.max(0.18, Math.log(n + 1) / Math.log(max + 1))
  }

  function collect() {
    if (root.collector === "" || collectProc.running) return
    collectProc.running = true
  }

  function refresh() {
    collect()
    if (timer.running) timer.restart()
  }

  Timer {
    id: timer
    interval: root.refreshSec * 1000
    running: true
    repeat: true
    triggeredOnStart: false
    onTriggered: root.collect()
  }

  Process {
    id: collectProc
    command: ["python3", root.collector,
              "--api", root.apiBase, "--quiet"]
    stdout: StdioCollector { onStreamFinished: {} }
    onExited: {
      // Bare id, not root.collectProc: an id is not a property of its parent
      // object, and dereferencing it here would throw before the reload.
      collectProc.running = false
      snapFile.reload()
    }
  }

  component BoundedJson: Item {
    id: bj
    property string path: ""
    property int limit: 512 * 1024
    signal parsed(var obj)
    signal rejected(string why)
    property bool again: false
    function reload() {
      if (!path) return
      if (bjProc.running) { bj.again = true; return }
      bjProc.running = true
    }
    Process {
      id: bjProc
      command: ["head", "-c", String(bj.limit + 1), "--", bj.path]
      stdout: StdioCollector {
        onStreamFinished: {
          var t = text
          if (!t) return
          if (t.length > bj.limit) {
            bj.rejected(bj.path + " larger than " + Math.round(bj.limit / 1024) + " KB")
            return
          }
          try { bj.parsed(JSON.parse(t)) } catch (e) { /* keep last good data */ }
        }
      }
      onExited: if (bj.again) { bj.again = false; bj.reload() }
    }
  }

  BoundedJson {
    id: snapFile
    path: root.snapshotPath
    Component.onCompleted: reload()
    onPathChanged: reload()
    onParsed: function(o) {
      var first = !root.snap
      root.snap = o
      root.dataError = ""
      if (first) root.collect()
    }
    onRejected: function(why) { root.dataError = why }
  }

  Component.onCompleted: root.collect()

  // open()/close()/toggle()/closeForPopoutSwitch() and the readonly `opened`
  // all come from the base Panel -- do not shadow them here.
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }

  readonly property var tokenSegments: [
    { k: "input",     c: "#7A715F" },
    { k: "output",    c: "#00e6a8" },
    { k: "reasoning", c: "#8ab4f8" },
    { k: "cache",     c: "#5c656e" }
  ]

  readonly property var sortedGeom: {
  var out = []
  for (var i = 0; i < root.lobeGeom.length; i++) {
  var g = root.lobeGeom[i]
  var l = root.lobeFor(g.key)
  var hex = l ? l.color : "#3a3f44"
  var r = parseInt(hex.slice(1, 3), 16) / 255
  var gg = parseInt(hex.slice(3, 5), 16) / 255
  var b = parseInt(hex.slice(5, 7), 16) / 255
  out.push({
  key: g.key, path: g.path, z: g.z, r: r, g: gg, b: b,
  w: root.weightOf(l ? l.memories : 0),
  live: !!(l && l.memories > 0)
  })
  }
  out.sort(function (a, b) { return a.z - b.z })
  return out
  }
  readonly property int maxMemories: {
  var b = root.snap && root.snap.brain ? root.snap.brain : null
  if (!b) return 1
  var m = 0
  for (var i = 0; i < b.lobes.length; i++)
  if (b.lobes[i].memories > m) m = b.lobes[i].memories
  return Math.max(1, m)
  }
  readonly property var agentRows: {
  var ag = (root.snap && root.snap.brain && root.snap.brain.agents) || []
  var out = []
  for (var i = 0; i < ag.length; i++) {
  var a = ag[i]
  var tel = a.telemetry || []
  var best = null
  for (var j = 0; j < tel.length; j++) {
  var c = tel[j].context ? tel[j].context.pct : 0
  var bc = (best && best.context) ? best.context.pct : 0
  if (!best || c > bc) best = tel[j]
  }
  out.push({
  name: a.type || "?",
  live: !!a.live,
  pid: a.pid !== undefined ? a.pid : null,
  procs: a.processes || 0,
  uptime: a.uptime || "",
  modules: a.modules || [],
  models: a.models || [],
  tokens: a.tokens || null,
  ctxPct: a.context_pct || 0,
  multi: (a.multi_sessions || []).length,
  sessions: tel,
  alerts: (best && best.alerts) ? best.alerts : []
  })
  }
  return out
  }
  readonly property int maxTokens: {
  var m = 0
  var rows = root.agentRows
  for (var i = 0; i < rows.length; i++)
  if (rows[i].tokens && rows[i].tokens.total > m) m = rows[i].tokens.total
  return Math.max(1, m)
  }

  function fmtNum(n) {
    n = Number(n || 0)
    if (n >= 1e9) return (n / 1e9).toFixed(2) + "B"
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M"
    if (n >= 1e4) return (n / 1e3).toFixed(0) + "k"
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "k"
    return String(Math.round(n))
  }
  function ctxColor(pct) {
    if (pct >= 85) return "#ff6b6b"
    if (pct >= 65) return "#ffb454"
    return "#00e6a8"
  }

  KeyboardPanel {
    id: kp
    visible: root.opened
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    contentWidth: kp.fittedContentWidth(Style.space(430))
    contentHeight: kp.fittedContentHeight(Style.space(660))

    // ---- formatting helpers -------------------------------------------------



  // Token bars are stacked by where the tokens actually went, so the bar is
  // readable without a legend next to it.

  // ---- reusable bits ------------------------------------------------------

  component MeterRow: ColumnLayout {
    id: mr
    property string label: ""
    property real pct: 0
    property color barColor: root.brand
    property string value: ""
    property string sub: ""
    spacing: 2
    RowLayout {
      Layout.fillWidth: true
      spacing: Style.space(5)
      Text {
        text: mr.label
        color: root.dimText
        font.family: root.fontFamily
        font.pixelSize: 9
        Layout.preferredWidth: 40
      }
      Text {
        text: mr.value
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        Layout.fillWidth: true
      }
    }
    Rectangle {
      Layout.fillWidth: true
      implicitHeight: 6
      radius: 3
      color: root.faint
      Rectangle {
        width: parent.width * Math.max(0, Math.min(1, mr.pct))
        height: parent.height
        radius: 3
        color: mr.barColor
        Behavior on width { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
      }
    }
    Text {
      visible: mr.sub !== ""
      text: mr.sub
      color: root.dimText
      font.family: root.fontFamily
      font.pixelSize: 9
      Layout.fillWidth: true
      elide: Text.ElideRight
    }
  }

  component TokenStack: ColumnLayout {
    id: ts
    property var tokens: null
    property real share: 0
    spacing: 2
    Rectangle {
      Layout.fillWidth: true
      implicitHeight: 6
      radius: 3
      color: root.faint
      Row {
        anchors.fill: parent
        spacing: 0
        Repeater {
          model: root.tokenSegments
          delegate: Rectangle {
            required property var modelData
            readonly property var tk: ts.tokens
            readonly property real parts: {
              if (!tk) return 0
              if (modelData.k === "cache") return (tk.cache_read || 0) + (tk.cache_write || 0)
              return tk[modelData.k] || 0
            }
            width: parent.width * (tk ? Math.min(1, ts.share) : 0) * (parts / Math.max(1, tk ? tk.total : 1))
            height: parent.height
            color: modelData.c
          }
        }
      }
    }
    RowLayout {
      Layout.fillWidth: true
      spacing: Style.space(6)
      Repeater {
        model: root.tokenSegments
        delegate: RowLayout {
          required property var modelData
          spacing: 2
          readonly property var tk: ts.tokens
          readonly property real parts: {
            if (!tk) return 0
            if (modelData.k === "cache") return (tk.cache_read || 0) + (tk.cache_write || 0)
            return tk[modelData.k] || 0
          }
          Rectangle { width: 5; height: 5; radius: 1; color: modelData.c }
          Text {
            text: modelData.k.slice(0, 4) + " " + root.fmtNum(parts)
            color: root.dimText
            font.family: root.fontFamily
            font.pixelSize: 8
          }
        }
      }
      Item { Layout.fillWidth: true }
    }
  }

  ColumnLayout {
      anchors.fill: parent
      spacing: Style.space(8)

      // ---- header -------------------------------------------------------
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(8)
        Image {
          source: Qt.resolvedUrl("assets/logo-32.png")
          sourceSize.width: 20
          sourceSize.height: 20
            fillMode: Image.PreserveAspectFit
        }
        Text {
          text: "Unified Memory Brain"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: 13
          font.weight: Font.DemiBold
        }
        Item { Layout.fillWidth: true }
        Text {
          text: root.snap && root.snap.generated_at
            ? String(root.snap.generated_at).slice(11, 19) + "Z" : "—"
          color: root.dimText
          font.family: root.fontFamily
          font.pixelSize: 10
        }
        PanelActionButton {
          iconText: "↻"
          tooltipText: "Refresh now"
          onClicked: root.refresh()
        }
      }

      // ---- status line --------------------------------------------------
      Rectangle {
        Layout.fillWidth: true
        implicitHeight: statusRow.implicitHeight + Style.space(12)
        radius: Style.cornerRadius
        color: root.surface
        border.width: 1
        border.color: root.faint
        RowLayout {
          id: statusRow
          anchors.fill: parent
          anchors.margins: Style.space(6)
          spacing: Style.space(8)
          Repeater {
            model: ["Supermemory", "Qdrant", "Redis", "PostgreSQL", "Headroom"]
            delegate: RowLayout {
              required property string modelData
              spacing: Style.space(3)
              Rectangle {
                width: 7; height: 7; radius: 4
                color: {
                  var o = root.snap && root.snap.overview ? root.snap.overview : null
                  if (!o) return "#5c656e"
                  var key = modelData.toLowerCase()
                  var up = key === "supermemory" ? o.supermemory.up
                          : key === "qdrant" ? o.qdrant.up
                          : key === "redis" ? o.redis.up
                          : key === "postgresql" ? o.postgres.up
                          : o.headroom.up
                  return up ? "#00e6a8" : "#ff6b6b"
                }
              }
              Text {
                text: modelData
                color: root.dimText
                font.family: root.fontFamily
                font.pixelSize: 10
              }
            }
          }
          Item { Layout.fillWidth: true }
          Text {
            text: root.snap && root.snap.overview
              ? (root.snap.overview.postgres.bytes > 0
                 ? (root.snap.overview.postgres.bytes / 1048576).toFixed(1) + " MB pg"
                 : "pg —")
              : "unreachable"
            color: root.dimText
            font.family: root.fontFamily
            font.pixelSize: 10
          }
        }
      }

      // A bare `if` cannot be a direct child of a layout, so gate visibility.
      Text {
        visible: root.dataError !== ""
        Layout.fillWidth: true
        text: root.dataError
        color: "#ff6b6b"
        font.family: root.fontFamily
        font.pixelSize: 10
        wrapMode: Text.WordWrap
      }

      // ---- the brain ----------------------------------------------------
      Rectangle {
        Layout.fillWidth: true
        implicitHeight: Style.space(190)
        radius: Style.cornerRadius
        color: root.surface
        border.width: 1
        border.color: root.faint

        Text {
          anchors.left: parent.left
          anchors.top: parent.top
          anchors.margins: Style.space(6)
          text: "SEGMENTED BRAIN"
          color: root.brand
          font.family: root.fontFamily
          font.pixelSize: 9
          font.letterSpacing: 1.2
        }

        Shape {
          id: brainShape
          anchors.fill: parent
          anchors.margins: Style.space(4)
          preferredRendererType: Shape.CurveRenderer
          // Lateral view of the brain, same 720x460 coordinate space as the
          // dashboard SVG so both renderings line up.
          transform: [
            { type: "scale", x: width / 720, y: height / 460 },
            { type: "translate", x: 0, y: 0 }
          ]
          // A Shape only accepts ShapePaths as direct children, so a Repeater
          // delegate cannot be parented to it. Instantiator plus an explicit
          // push into Shape.data is the supported route.
          Instantiator {
            model: root.sortedGeom
            onObjectAdded: (index, object) => brainShape.data.push(object)
            delegate: ShapePath {
              id: lobePath
              required property var modelData
              // Paint order comes from the Repeater's model order (sorted by
              // z in sortedGeom); ShapePath itself has no `z` property.
              PathSvg { path: modelData.path }
              strokeColor: Qt.rgba(modelData.r, modelData.g, modelData.b, modelData.live ? 0.9 : 0.32)
              strokeWidth: modelData.live ? 1.6 : 1.0
              fillRule: ShapePath.OddEvenFill
              fillColor: Qt.rgba(modelData.r, modelData.g, modelData.b,
                                 modelData.live ? (0.38 + 0.46 * modelData.w) : 0.12)
            }
          }
          // A Shape only accepts ShapePaths as direct children, so a Repeater
          // delegate cannot be parented to it. Instantiator plus an explicit
          // push into Shape.data is the supported route.
          Instantiator {
            model: root.sortedGeom
            onObjectAdded: (index, object) => brainShape.data.push(object)
            delegate: ShapePath {
              required property var modelData
              PathSvg { path: modelData.path }
              // Specular pass: a soft light rim on the same silhouette. The
              // outer half of the wide stroke survives past the base fill and
              // reads as a highlight, which is what gives the lobes roundness.
              fillColor: "transparent"
              strokeColor: Qt.rgba(1, 1, 1, modelData.live ? 0.13 : 0.035)
              strokeWidth: 7
            }
          }

          // Cortex outline
          ShapePath {
            strokeColor: Qt.rgba(0.478, 0.443, 0.373, 0.55)
            strokeWidth: 1.4
            fillColor: "transparent"
            PathSvg {
              path: "M132 300 C96 268 84 224 100 186 C118 142 168 112 224 108 C262 84 320 70 380 74 C430 77 470 96 494 124 C520 148 540 178 548 210 C556 244 552 276 540 302"
            }
          }
        }

        Text {
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          anchors.margins: Style.space(6)
          text: root.snap && root.snap.brain
            ? (root.snap.brain.total + " memories · " + root.snap.brain.classified + " classified")
            : "no data"
          color: root.dimText
          font.family: root.fontFamily
          font.pixelSize: 10
        }
      }

      // Geometry with colour, weight and liveness resolved from the snapshot,
      // sorted back-to-front so the cortex paints above the cerebellum.
      // ---- subjects -----------------------------------------------------
      PanelSectionHeader { text: "Memory by subject" }
      Repeater {
        model: root.snap && root.snap.brain ? root.snap.brain.lobes : []
        delegate: RowLayout {
          required property var modelData
          required property int index
          Layout.fillWidth: true
          spacing: Style.space(6)
          Rectangle {
            width: 8; height: 8; radius: 4
            color: modelData.color
            Layout.alignment: Qt.AlignVCenter
          }
          Text {
            text: modelData.subject
            color: root.dimText
            font.family: root.fontFamily
            font.pixelSize: 11
            Layout.preferredWidth: 84
          }
          Text {
            text: modelData.lobe
            color: root.dimText
            font.family: root.fontFamily
            font.pixelSize: 10
            Layout.fillWidth: true
            elide: Text.ElideRight
          }
          Rectangle {
            Layout.preferredWidth: 54; Layout.preferredHeight: 4; radius: 2
            color: root.faint
            Rectangle {
              width: parent.width * (root.snap && root.snap.brain && root.snap.brain.total
                                     ? modelData.memories / Math.max(1, root.maxMemories) : 0)
              height: parent.height; radius: 2
              color: modelData.color
            }
          }
          Text {
            text: (modelData.memories > 0 ? modelData.memories : "—")
                  + "  " + modelData.pct + "%"
            color: root.dimText
            font.family: root.fontFamily
            font.pixelSize: 10
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: 62
          }
        }
      }

      // ---- agents tree ---------------------------------------------------
      PanelSectionHeader {
        text: {
          var ag = root.agentRows
          var live = 0
          for (var i = 0; i < ag.length; i++) if (ag[i].live) live++
          return "Agents · " + live + " running of " + ag.length
        }
      }

      // Newest session per agent, which is the one worth showing first.
      // Largest token total, so the token bars are comparable between agents.
      Repeater {
        model: root.agentRows
        delegate: Rectangle {
          id: node
          required property var modelData
          required property int index

          readonly property bool open: root.isOpen(modelData.name)
          readonly property var ctx: {
            for (var i = 0; i < modelData.sessions.length; i++) {
              var c = modelData.sessions[i].context
              if (c && c.used > 0) return c
            }
            return null
          }

          Layout.fillWidth: true
          implicitHeight: col.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.surface
          border.width: 1
          border.color: modelData.live ? Qt.rgba(root.brand.r, root.brand.g, root.brand.b, 0.5) : root.faint

          ColumnLayout {
            id: col
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(5)
            spacing: Style.space(4)

            // --- header row ------------------------------------------------
            RowLayout {
              Layout.fillWidth: true
              spacing: Style.space(5)

              Text {
                text: node.open ? "▾" : "▸"
                color: root.dimText
                font.family: root.fontFamily
                font.pixelSize: 9
              }
              Rectangle {
                width: 7; height: 7; radius: 4
                color: modelData.live ? "#00e6a8" : "#5c656e"
              }
              Text {
                text: modelData.name
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
              }
              Text {
                visible: modelData.multi > 0
                text: modelData.multi + " session" + (modelData.multi > 1 ? "s" : "") + " · 2+ modules"
                color: "#ffb454"
                font.family: root.fontFamily
                font.pixelSize: 8
                elide: Text.ElideRight
                Layout.fillWidth: true
              }
              Item { Layout.fillWidth: true }
              Text {
                text: modelData.live
                  ? (modelData.procs > 1 ? modelData.procs + " proc · " : "") + modelData.uptime
                  : "idle"
                color: root.dimText
                font.family: root.fontFamily
                font.pixelSize: 9
              }
            }

            // --- always-visible summary (the self-explaining part) ---------
            GridLayout {
              Layout.fillWidth: true
              Layout.leftMargin: Style.space(12)
              columns: 2
              columnSpacing: Style.space(8)
              rowSpacing: Style.space(4)

              Text {
                text: "modules"
                color: root.dimText
                font.family: root.fontFamily
                font.pixelSize: 9
              }
              Text {
                Layout.fillWidth: true
                text: modelData.modules.length
                  ? modelData.modules.join(" · ")
                  : (modelData.models.length ? modelData.models[0] : "—")
                color: modelData.modules.length ? root.foreground : root.dimText
                font.family: root.fontFamily
                font.pixelSize: 10
                elide: Text.ElideRight
              }

              Text {
                text: "tokens"
                color: root.dimText
                font.family: root.fontFamily
                font.pixelSize: 9
              }
              TokenStack {
                Layout.fillWidth: true
                tokens: modelData.tokens
                share: modelData.tokens ? modelData.tokens.total / root.maxTokens : 0
              }

              Text {
                text: "context"
                color: root.dimText
                font.family: root.fontFamily
                font.pixelSize: 9
              }
              ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                MeterRow {
                  Layout.fillWidth: true
                  label: "ctx"
                  pct: modelData.ctxPct / 100
                  barColor: root.ctxColor(modelData.ctxPct)
                  value: node.ctx && node.ctx.limit
                    ? modelData.ctxPct + "%"
                    : (modelData.ctx && modelData.ctx.unknown ? "not reported" : "—")
                  sub: node.ctx && node.ctx.limit
                    ? root.fmtNum(node.ctx.used) + " used / " + root.fmtNum(node.ctx.limit)
                      + " · " + root.fmtNum(node.ctx.free) + " free"
                      + (node.ctx.estimated ? " (est)" : "")
                    : (node.ctx && node.ctx.messages
                       ? node.ctx.messages + " messages in flight" : "")
                }
              }
            }

            // --- expanded detail ------------------------------------------
            ColumnLayout {
              Layout.fillWidth: true
              Layout.leftMargin: Style.space(12)
              spacing: Style.space(3)
              visible: node.open

              Repeater {
                model: modelData.alerts
                delegate: RowLayout {
                  required property var modelData
                  Layout.fillWidth: true
                  spacing: Style.space(4)
                  Text {
                    text: modelData.level === "error" ? "⚠" : (modelData.level === "warn" ? "△" : "ⓘ")
                    color: modelData.level === "error" ? "#ff6b6b"
                         : (modelData.level === "warn" ? "#ffb454" : "#8ab4f8")
                    font.family: root.fontFamily
                    font.pixelSize: 9
                  }
                  Text {
                    Layout.fillWidth: true
                    text: modelData.text
                    color: modelData.level === "error" ? "#ff9d9d" : root.dimText
                    font.family: root.fontFamily
                    font.pixelSize: 9
                    wrapMode: Text.WordWrap
                  }
                }
              }

              Repeater {
                model: modelData.sessions
                delegate: Rectangle {
                  required property var modelData
                  readonly property var s: modelData
                  Layout.fillWidth: true
                  implicitHeight: srow.implicitHeight + Style.space(6)
                  radius: 3
                  color: Qt.rgba(0, 0, 0, 0.18)
                  border.width: s.multi ? 1 : 0
                  border.color: Qt.rgba(1, 0.706, 0.33, 0.55)

                  RowLayout {
                    id: srow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 3
                    spacing: Style.space(4)

                    Text {
                      text: s.multi ? "⤫" : "·"
                      color: s.multi ? "#ffb454" : root.dimText
                      font.family: root.fontFamily
                      font.pixelSize: 9
                    }
                    Text {
                      Layout.fillWidth: true
                      text: s.title
                      color: root.dimText
                      font.family: root.fontFamily
                      font.pixelSize: 9
                      elide: Text.ElideRight
                    }
                    Text {
                      text: s.multi
                        ? (s.models.length ? s.models.length + " models" : "2+ modules")
                        : (s.context && s.context.limit ? s.context.pct + "% ctx" : s.updated)
                      color: s.multi ? "#ffb454" : root.dimText
                      font.family: root.fontFamily
                      font.pixelSize: 9
                    }
                  }
                }
              }
            }
          }

          MouseArea {
            anchors.fill: parent
            anchors.bottomMargin: Style.space(4)
            onClicked: root.toggleAgent(node.modelData.name)
          }
        }
      }

      Text {
        visible: root.agentRows.length === 0
        text: "No agent CLIs detected. Start opencode, codex, claude or hermes and the roster fills in on the next refresh."
        color: root.dimText
        font.family: root.fontFamily
        font.pixelSize: 10
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
      }


      // ---- value --------------------------------------------------------
      PanelSectionHeader { text: "Value delivered" }
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(6)
        Repeater {
          model: [
            { k: "Memories", v: root.snap && root.snap.brain ? root.snap.brain.total : null },
            { k: "Tokens saved", v: root.snap && root.snap.overview ? root.snap.overview.tokens.saved : null },
            { k: "Autopilot", v: root.snap && root.snap.autopilot ? root.snap.autopilot.actions : null },
            { k: "Docs", v: root.snap && root.snap.overview ? root.snap.overview.supermemory.documents : null }
          ]
          delegate: ColumnLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 1
            Text {
              text: modelData.v == null ? "—" : Number(modelData.v).toLocaleString(Qt.locale(), "f", 0)
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: 14
              font.weight: Font.DemiBold
              Layout.fillWidth: true
              horizontalAlignment: Text.AlignHCenter
            }
            Text {
              text: modelData.k
              color: root.dimText
              font.family: root.fontFamily
              font.pixelSize: 9
              Layout.fillWidth: true
              horizontalAlignment: Text.AlignHCenter
            }
          }
        }
      }
    }
  }
}
