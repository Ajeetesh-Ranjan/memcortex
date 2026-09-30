/* AI Architecture Lab — Segmented Brain Renderer
 *
 * Dependency-free SVG brain visualisation. Deliberately does NOT use Three.js:
 * the Brain UI runs inside a Docker network that must work air-gapped, and the
 * same renderer has to be reusable inside a Waybar popup and a tray tooltip.
 *
 * Anatomy: lateral (left-profile) view. Each lobe is a real anatomical region
 * bound to a subject by brain_taxonomy.py. Lobe area + saturation + glow scale
 * with live memory share, so the picture is a data display, not decoration.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BrainSVG = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var VIEW = { w: 720, h: 460 };

  /* Anatomical regions in lateral view. Coordinates are in viewBox units.
   * `z` controls paint order (cerebellum/brainstem sit behind the cortex). */
  var LOBES = {
    Frontal: {
      d: "M132 300 C96 268 84 224 100 186 C118 142 168 112 224 108 C258 105 286 116 302 132 C276 150 254 176 244 208 C232 248 234 288 254 320 C212 330 168 322 132 300 Z",
      cx: 196, cy: 218, z: 3
    },
    Parietal: {
      d: "M302 132 C286 116 258 105 224 108 C262 84 320 70 380 74 C430 77 470 96 494 124 C468 136 434 150 400 176 C362 206 330 224 302 232 C286 208 282 166 302 132 Z",
      cx: 372, cy: 138, z: 3
    },
    Occipital: {
      d: "M494 124 C520 148 540 178 548 210 C556 244 552 276 540 302 C524 276 500 244 468 214 C444 192 418 176 400 176 C434 150 468 136 494 124 Z",
      cx: 500, cy: 208, z: 3
    },
    Temporal: {
      d: "M244 232 C272 246 306 244 336 226 C372 204 408 190 446 192 C470 193 492 202 508 218 C486 246 456 274 420 296 C378 320 320 328 274 316 C258 296 250 266 244 232 Z",
      cx: 372, cy: 264, z: 4
    },
    Association: {
      d: "M282 156 C314 138 356 128 400 132 C436 136 466 150 484 172 C456 190 424 208 392 222 C352 240 306 240 276 224 C266 202 268 176 282 156 Z",
      cx: 380, cy: 184, z: 5
    },
    Cerebellum: {
      d: "M540 300 C562 300 578 318 574 340 C570 362 548 378 524 374 C500 370 484 350 486 330 C488 312 512 300 540 300 Z",
      cx: 530, cy: 338, z: 2
    },
    Brainstem: {
      d: "M296 318 C318 314 336 322 340 340 C344 358 336 376 320 384 C304 392 288 384 284 368 C280 350 284 326 296 318 Z",
      cx: 312, cy: 350, z: 2
    }
  };

  var SUBJECT_TO_LOBE = {
    "Frontal Lobe": "Frontal",
    "Parietal Lobe": "Parietal",
    "Temporal Lobe": "Temporal",
    "Occipital Lobe": "Occipital",
    "Cerebellum": "Cerebellum",
    "Brainstem": "Brainstem",
    "Association Cortex": "Association"
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hexToRgb(h) {
    h = (h || "#888888").replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgba(h, a) {
    var c = hexToRgb(h);
    return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a + ")";
  }

  /* Log scale: memory counts span 0..1e6, so raw shares of 0.1% would be
   * invisible. log1p keeps small-but-nonzero subjects legible. */
  function weightOf(n, maxN) {
    if (!n) return 0;
    if (!maxN) return 0.25;
    return Math.max(0.18, Math.log1p(n) / Math.log1p(maxN));
  }

  function render(data, opts) {
    opts = opts || {};
    var lobes = (data && data.lobes) || [];
    var byLobe = {};
    lobes.forEach(function (l) {
      var k = SUBJECT_TO_LOBE[l.lobe];
      if (k) byLobe[k] = l;
    });

    var maxN = lobes.reduce(function (m, l) { return Math.max(m, l.memories || 0); }, 0);
    var total = (data && data.total) || 0;
    var showLabels = opts.labels !== false;

    var defs = [], body = [], labels = [];

    /* ---- gradients + filters ---- */
    Object.keys(LOBES).forEach(function (key) {
      var g = LOBES[key];
      var d = byLobe[key];
      var col = (d && d.color) || "#3a3f44";
      var w = d ? weightOf(d.memories, maxN) : 0;
      var gid = "grad-" + key;
      defs.push(
        '<radialGradient id="' + gid + '" cx="38%" cy="32%" r="78%">',
        '<stop offset="0%" stop-color="' + rgba(col, 0.55 + 0.45 * w) + '"/>',
        '<stop offset="55%" stop-color="' + rgba(col, 0.35 + 0.4 * w) + '"/>',
        '<stop offset="100%" stop-color="' + rgba(col, 0.18 + 0.3 * w) + '"/>',
        "</radialGradient>"
      );
      defs.push(
        '<filter id="glow-' + key + '" x="-40%" y="-40%" width="180%" height="180%">',
        '<feGaussianBlur stdDeviation="' + (3 + 7 * w).toFixed(2) + '" result="b"/>',
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>',
        "</filter>"
      );
    });

    /* ambient cortex shell + sulci texture */
    defs.push(
      '<linearGradient id="shell" x1="0" y1="0" x2="1" y2="1">',
      '<stop offset="0%" stop-color="#1a1c1e"/>',
      '<stop offset="100%" stop-color="#0a0c0c"/>',
      "</linearGradient>",
      '<radialGradient id="vign" cx="50%" cy="42%" r="72%">',
      '<stop offset="0%" stop-color="#20242a" stop-opacity="0.55"/>',
      '<stop offset="100%" stop-color="#08090a" stop-opacity="0.9"/>',
      "</radialGradient>"
    );

    /* ---- lobes, painted back-to-front ---- */
    var order = Object.keys(LOBES).sort(function (a, b) {
      return LOBES[a].z - LOBES[b].z;
    });

    order.forEach(function (key) {
      var g = LOBES[key];
      var d = byLobe[key];
      var col = (d && d.color) || "#3a3f44";
      var w = d ? weightOf(d.memories, maxN) : 0;
      var live = d && d.memories > 0;
      body.push(
        '<path d="' + g.d + '" fill="url(#grad-' + key + ')"',
        ' stroke="' + rgba(col, live ? 0.9 : 0.35) + '"',
        ' stroke-width="' + (live ? 1.6 : 1) + '"',
        ' filter="url(#glow-' + key + ')"',
        live ? ' class="aal-lobe aal-live"' : ' class="aal-lobe"',
        ' data-subject="' + esc(d ? d.subject : key) + '"',
        '><title>' + esc((d ? d.subject : key) + (d ? " — " + d.lobe : "")) +
        (d && d.memories ? " — " + d.memories + " memories" : " — empty") +
        "</title></path>"
      );

      /* neural activity spark: dot count scales with live volume */
      if (live) {
        var dots = Math.min(9, 2 + Math.round(w * 7));
        for (var i = 0; i < dots; i++) {
          var a = (i / dots) * Math.PI * 2 + key.length;
          var rad = 12 + w * 20;
          body.push(
            '<circle class="aal-spark" cx="' + (g.cx + Math.cos(a) * rad).toFixed(1) +
            '" cy="' + (g.cy + Math.sin(a) * rad * 0.72).toFixed(1) +
            '" r="' + (1.1 + w * 1.5).toFixed(2) + '" fill="' + rgba(col, 0.85) + '"/>'
          );
        }
      }
    });

    /* ---- outline on top ---- */
    body.push(
      '<path d="M132 300 C96 268 84 224 100 186 C118 142 168 112 224 108 C262 84 320 70 380 74 C430 77 470 96 494 124 C520 148 540 178 548 210 C556 244 552 276 540 302"',
      ' fill="none" stroke="#7A715F" stroke-opacity="0.55" stroke-width="1.4" stroke-linecap="round"/>'
    );

    /* ---- labels with leader lines ---- */
    if (showLabels) {
      var slots = [
        { x: 40, y: 96 }, { x: 40, y: 176 }, { x: 40, y: 256 },
        { x: 40, y: 336 }, { x: 566, y: 120 }, { x: 566, y: 200 },
        { x: 566, y: 280 }, { x: 300, y: 424 }
      ];
      var si = 0;
      Object.keys(LOBES).forEach(function (key) {
        var g = LOBES[key];
        var d = byLobe[key];
        if (!d) return;
        var s = slots[si % slots.length];
        si++;
        var w = weightOf(d.memories, maxN);
        var anchorRight = s.x > 400;
        var lx = s.x, ly = s.y;
        var tx = anchorRight ? lx : lx + 96;
        var ty = ly + 5;
        var lbl = d.memories > 0
          ? d.subject + "  " + d.memories.toLocaleString()
          : d.subject + "  —";
        var pct = total ? Math.round((d.memories / total) * 100) : 0;

        labels.push(
          '<g class="aal-label" data-subject="' + esc(d.subject) + '">',
          '<circle cx="' + g.cx + '" cy="' + g.cy + '" r="3" fill="' + d.color + '"/>',
          '<line x1="' + g.cx + '" y1="' + g.cy + '" x2="' +
          (anchorRight ? lx + 88 : lx) + '" y2="' + ly + '"',
          ' stroke="' + rgba(d.color, 0.5) + '" stroke-width="1" stroke-dasharray="3 3"/>',
          '<text x="' + tx + '" y="' + ty + '" fill="#e8e4dc" font-size="12.5"',
          ' font-family="Inter,system-ui,sans-serif" ' +
          (anchorRight ? 'text-anchor="end"' : "") + '>',
          esc(lbl),
          '<tspan fill="#7A715F" font-size="11">' + (total ? pct + "%" : "") + "</tspan>",
          "</text>",
          '<text x="' + tx + '" y="' + (ty + 14) + '" fill="#7d8792" font-size="10"',
          ' font-family="Inter,system-ui,sans-serif" ' +
          (anchorRight ? 'text-anchor="end"' : "") + ">",
          esc(d.lobe + " · " + d.role),
          "</text></g>"
        );
      });
    }

    var agents = (data && data.agents) || [];
    var agentChips = agents.slice(0, 6).map(function (a) {
      var live = a.status === "active";
      return '<span class="aal-agent' + (live ? " is-active" : "") + '">' +
        esc(a.agent_type || "unknown") +
        (a.model ? '<i>' + esc(a.model) + "</i>" : "") + "</span>";
    }).join("");

    return '' +
      '<svg class="aal-brain" viewBox="0 0 ' + VIEW.w + ' ' + VIEW.h +
      '" xmlns="http://www.w3.org/2000/svg" role="img" ' +
      'aria-label="Segmented memory brain by subject">' +
      "<defs>" + defs.join("") + "</defs>" +
      '<rect width="' + VIEW.w + '" height="' + VIEW.h + '" fill="url(#vign)" rx="14"/>' +
      body.join("") + labels.join("") +
      '<text x="24" y="34" fill="#7A715F" font-size="11" letter-spacing="2.4" ' +
      'font-family="Inter,system-ui,sans-serif">THE AI ARCHITECTURE LAB</text>' +
      '<text x="24" y="' + (VIEW.h - 16) + '" fill="#5c656e" font-size="10.5" ' +
      'font-family="Inter,system-ui,sans-serif">' +
      total.toLocaleString() + " memories · " +
      ((data && data.classified) || 0) + " classified · " +
      agents.length + " agent" + (agents.length === 1 ? "" : "s") + "</text>" +
      (agentChips ? '<g transform="translate(24 52)">' + agentChips + "</g>" : "") +
      "</svg>";
  }

  return { render: render, LOBES: LOBES, SUBJECT_TO_LOBE: SUBJECT_TO_LOBE, VIEW: VIEW };
});
