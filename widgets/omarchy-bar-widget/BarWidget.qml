import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

/*
  AI Architecture Lab — Unified Memory Brain bar widget.

  Left click toggles the panel (segmented brain, subjects, agents, value).
  Right click opens the Brain Monitor dashboard in the browser.
*/
BarWidget {
  id: root
  moduleName: "io.github.aial.memory-brain"

  property string apiBase: "http://localhost:8080"
  // Strip the file:// scheme: Process.command needs a real filesystem path.
  readonly property string pluginDir: Qt.resolvedUrl(".").toString()
                                      .replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string collectorPath: pluginDir + "/bin/aal-brain-collector.py"
  readonly property string snapshotPath: {
    var base = Quickshell.env("XDG_STATE_HOME")
    if (!base || base === "") base = Quickshell.env("HOME") + "/.local/state"
    return base + "/aial-memory-brain/snapshot.json"
  }

  readonly property bool opened: panelLoader.item
    ? panelLoader.item.opened === true
    : false
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true
    : false

  // Live-ish status for the bar glyph: red if the collector cannot reach the
  // stack, sand otherwise. The glyph itself stays a brain.
  readonly property string glyph: {
    if (!panelLoader.item) return "󰗠"
    var s = panelLoader.item.snap
    if (s && s.ok === true) return "󰗠"
    return "󰗢"
  }

  // `opened` on the base Panel is readonly -- drive it through its own
  // open()/close()/toggle() rather than assigning to it.
  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root, direction)
    return false
  }

  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = root.bar
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.glyph
    tooltipText: {
      var p = panelLoader.item
      if (!p || !p.snap) return "The AI Architecture Lab — Unified Memory (connecting…)"
      if (p.snap.ok !== true) return "The AI Architecture Lab — Unified Memory (stack unreachable)"
      var b = p.snap.brain || {}
      var o = p.snap.overview || {}
      var t = o.tokens || {}
      var lines = []
      lines.push("The AI Architecture Lab — Unified Memory Stack")
      lines.push("Memories: " + ((o.supermemory || {}).memories || 0))
      lines.push("Tokens saved: " + (t.saved || 0) + " (" + ((t.ratio || 0) * 100).toFixed(1) + "%)")
      if (b.total) {
        lines.push("")
        lines.push("Brain — " + b.total + " memories (" + b.classified + " classified)")
        var ls = (b.lobes || []).slice().sort(function (x, y) { return y.memories - x.memories })
        for (var i = 0; i < ls.length; i++)
          if (ls[i].memories > 0)
            lines.push("  ● " + ls[i].subject + "  " + ls[i].memories + " (" + ls[i].pct + "%)  " + ls[i].lobe)
      }
      var ag = b.agents || []
      if (ag.length) {
        var act = 0
        for (var j = 0; j < ag.length; j++) if (ag[j].status === "active") act++
        lines.push("")
        lines.push("Agents: " + ag.length + " registered, " + act + " active")
      }
      return lines.join("\n")
    }

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.toggle()
      else if (buttonCode === Qt.RightButton) Quickshell.openUrl(root.apiBase + "/")
    }
  }

  Component.onCompleted: injectPanel()
}
