// The Architectural design view of dra ui (5 Oct 2026): the agent's architecture as a diagram whose every box opens
// a panel with two tabs, Simple and Advanced. Loaded before app.js and drawn by its router (page=architecture).
// Rules this file keeps (tests/test_ui_architecture.py):
// - every word comes from GET /architecture (static/architecture.json, its numbers and names filled by the server
//   from the config and the code); the shard boxes, the tool layers and the servers are drawn from its facts;
// - "In this run" values come only from GET /runs/<id>/stage/<name>, the stage panel's own route;
// - the panel is the run page's stage panel (same classes, Esc, Close, focus in and back, aria-expanded on the box);
// - text is inserted as textContent only; no number literal, no colour, no animation in this file.
"use strict";

const ARCH = {
  data: null,          // GET /architecture
  topic: null,         // the open topic key, or null
  from: null,          // the element that opened it (focus goes back there on close)
  tab: "simple",       // "simple" | "advanced", kept as the topics are walked
  run: null,           // the run whose stage files fill "In this run"
  views: new Map(),    // "<run>/<stage>" -> the stage view (or {error})
  ask: 0,
};
const ARCH_TAB_KEY = "sit-architecture-tab";

// A bare hash such as #architecture/understand (or #understand) opens that topic: rewritten to the app's query
// convention before the router runs.
(function archHash() {
  const m = /^#(?:architecture\/?)?([a-z-]*)$/.exec(location.hash || "");
  if (!m || !location.hash) return;
  const q = new URLSearchParams(location.search);
  if (q.get("page") && q.get("page") !== "architecture") return;
  const u = "/?page=architecture" + (m[1] ? "&topic=" + encodeURIComponent(m[1]) : "");
  history.replaceState(null, "", u);
})();

try { const t = localStorage.getItem(ARCH_TAB_KEY); if (t === "simple" || t === "advanced") ARCH.tab = t; } catch (e) { /* storage off */ }

async function showArchitecture() {
  const app = clear($("app"));
  app.className = "surface wide arch-surface";
  app.append(tpl("tpl-architecture"));
  if (!ARCH.data) {
    try { ARCH.data = await api("/architecture"); }
    catch (e) { $("arch-diagram").append(h("p", { class: "error", text: "The architecture could not be read: " + e.message })); return; }
  }
  const q = new URLSearchParams(location.search);
  ARCH.run = archPickRun(q.get("from"));
  $("arch-sub").append(ARCH.data.tagline, h("br"), h("span", { class: "arch-subnote", text: "Every name, count and limit in the diagram is read from the config and the code this server runs." }));
  archRunNote();
  archDiagram($("arch-diagram"));
  archImportant($("arch-diagram"));
  archGuide();
  $("ap-close").addEventListener("click", () => archClose());
  $("arch-panel").addEventListener("keydown", archKeys);
  // Esc closes the open panel wherever the focus is (a click on the diagram or the page moves it out of the panel).
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !e.defaultPrevented && ARCH.topic) { e.preventDefault(); archClose(); }
  });
  const t = q.get("topic");
  ARCH.topic = null;
  if (t && ARCH.data.topics[t]) archOpen(t, null, false);
  else archPaint();
}

// The newest run with a report (or the one named by ?from=), for the "In this run" values.
function archPickRun(named) {
  const runs = (typeof S !== "undefined" && S.runs) || [];
  if (named && runs.some((r) => r.run_id === named)) return named;
  const done = runs.find((r) => r.has_report && r.status !== "running");
  return done ? done.run_id : null;
}

function archRunNote() {
  const box = clear($("arch-run"));
  if (!ARCH.run) { box.append(h("span", { class: "notice", text: "No finished run here, so no run values." })); return; }
  box.append(h("span", { class: "notice" }, "Run values from ", h("a", { class: "mono arch-runref", href: "/?run=" + encodeURIComponent(ARCH.run), text: ARCH.run,
    onclick: (ev) => { ev.preventDefault(); go(ARCH.run); } })));
}

// ------------------------------------------------------------------ the diagram

function archTitle(key) { const t = ARCH.data.topics[key]; return t ? t.title : key; }

// One clickable part: a box (title and a line under it) or a chip; every one is a real button for its topic.
function archBtn(key, label, sub, cls) {
  return h("button", { class: (cls || "arch-box"), type: "button", "data-topic": key, "aria-controls": "arch-panel", "aria-expanded": "false",
    title: "Open " + archTitle(key), onclick: (ev) => archToggle(key, ev.currentTarget) },
  h("span", { class: "ab-title", text: label }), sub ? h("span", { class: "ab-sub", text: sub }) : null);
}
function archChip(key, label, extra) { return archBtn(key, label, null, "arch-chip" + (extra ? " " + extra : "")); }
function down(label) { return h("div", { class: "arch-down", "aria-hidden": "true" }, label ? h("span", { text: label }) : null); }
// An arrow that fills the rest of its lane, down to the box under the lanes.
function feed(label) { return h("div", { class: "arch-down arch-feed", "aria-hidden": "true" }, h("span", { text: label })); }
function right() { return h("span", { class: "arch-right", "aria-hidden": "true" }); }
function group(cls, label, ...kids) { return h("div", { class: "arch-group " + cls }, label ? h("div", { class: "ag-label", text: label }) : null, ...kids); }

// The topic each tool gateway layer opens.
const ARCH_LAYER_TOPIC = { LoggingToolGateway: "tool-logging", PolicyToolGateway: "policy", SelfReplayGateway: "checkpoints",
  FaultInjectingGateway: "faults", RecordingGateway: "tool-recording", "MCPToolGateway | ReplayGateway | FakeToolGateway": "tool-base" };

function archDiagram(root) {
  const F = ARCH.data.facts;
  clear(root);
  // The shards are plain labels under the Assess box, which is the one that opens their panel.
  const shards = F.shards.map((s) => h("div", { class: "arch-chip shard" }, h("span", { class: "ab-title", text: s.name.split("_").join(" ") })));
  // LoggingToolGateway -> "Logging", SelfReplayGateway -> "Self replay"; the class name stays in the chip's title
  const layerName = (n) => n.replace(/(Tool)?Gateway$/, "").replace(/([a-z])([A-Z])/g, (_, a, b) => a + " " + b.toLowerCase());
  const layers = [];
  F.tool_layers.forEach((l, i) => {
    if (i) layers.push(h("span", { class: "arch-sep", "aria-hidden": "true" }));
    const chip = archChip(ARCH_LAYER_TOPIC[l] || "research-act", l.split(" | ").map(layerName).join(" | "));
    chip.title = l + ": open " + archTitle(chip.dataset.topic);
    layers.push(chip);
  });
  const backends = [archChip("llm-gateway", "Claude Code CLI" + (F.backend_default === "claude_code" ? " (default)" : "")),
    archChip("llm-gateway", "Anthropic API" + (F.backend_default === "anthropic_api" ? " (default)" : "")),
    archChip("checkpoints", "Replay"), archChip("llm-gateway", "Fake"), archChip("faults", "Fault injection")];
  root.append(
    h("div", { class: "arch-row arch-entry" },
      archBtn("user", "User", "the design document: PDF, text or Markdown", "arch-box tone-plain"), right(),
      archBtn("cli", "CLI", "dra review <pdf>, one command; this page runs the same", "arch-box tone-plain")),
    down(),
    h("section", { class: "arch-agent", "aria-label": "The " + F.agent_label },
      h("div", { class: "aa-label", text: F.agent_label }),
      h("div", { class: "arch-row arch-control" },
        archBtn("orchestrator", "Orchestrator", "sets up the run, drives the stages, checkpoints, caps, exit codes", "arch-box tone-ink"), right(),
        archBtn("state-machine", "State machine", F.stage_order, "arch-box tone-ink")),
      down(),
      archBtn("ingest", "Ingest", "code: PDF -> pdfplumber -> canonical text -> Document (pages, sections, requirement IDs)", "arch-box tone-blue wide"),
      down(),
      group("tone-blue arch-stage1", "Stage 1: " + F.stage_1_members + " run side by side",
        h("div", { class: "arch-lanes" },
          h("div", { class: "arch-lane" },
            h("div", { class: "al-head", text: "Start at once" }),
            archBtn("understand", "Understand", "one model call: intent summary, decision registry (frozen)", "arch-box tone-blue"),
            archBtn("plan", "Plan", "one model call: questions per criterion, external or not, capability, queries", "arch-box tone-blue")),
          h("div", { class: "arch-lane lane-research" },
            h("div", { class: "al-head", text: "Waits for " + F.research_waits_for }),
            group("tone-green arch-loop", null,
              archBtn("research", "Research", "reason, act, observe", "arch-box tone-green head"),
              // reason, act and observe, with the arrow from observe back up to reason drawn beside them
              h("div", { class: "arch-cycle" },
                archBtn("research-reason", "Reason", "LLMGateway: what to look up, which tool, which query", "arch-box tone-green"),
                h("div", { class: "arch-down small", "aria-hidden": "true" }),
                archBtn("research-act", "Act", "ToolGateway: policy, then the MCP servers", "arch-box tone-green"),
                h("div", { class: "arch-down small", "aria-hidden": "true" }),
                archBtn("research-observe", "Observe", "results become EV-(n) ledger entries", "arch-box tone-green")),
              h("div", { class: "arch-chips" }, archChip("state", "State"), archChip("evidence", "Evidence ledger")),
              h("div", { class: "arch-loopnote", text: "repeat until done, or a limit hits" })),
            feed("answers, evidence")),
          h("div", { class: "arch-lane" },
            h("div", { class: "al-head", text: "Start at once" }),
            archBtn("assess", "Assess", F.shard_count + " shards, one model call each", "arch-box tone-blue head"),
            h("div", { class: "arch-shards" }, shards),
            // each shard reads its inputs from its own copy of the run state and writes its draft findings back
            h("div", { class: "arch-twoway" }, h("span", { class: "arch-updown", "aria-hidden": "true" }),
              h("span", { text: "reads the document and its criteria, writes draft findings" })),
            archChip("state", "Isolated copy of the run state", "wide"),
            feed("draft findings"))),
        archBtn("merge", "Merge", "code, when stage 1 closes: findings renumbered FND-(n) in shard order, ranked by severity", "arch-box tone-blue merge")),
      down("findings, registry, research answers, ledger"),
      h("div", { class: "arch-row arch-post" },
        archBtn("refine", "Refine", "one call: keep, merge or withdraw each finding; research evidence joins here", "arch-box tone-red"), right(),
        archBtn("verify", "Verify", "code: every quote against the page, evidence from the ledger; one repair call", "arch-box tone-red"), right(),
        archBtn("report", "Report", "verdict call, then code: invariants, report.json, report.md", "arch-box tone-red")),
      down(),
      h("div", { class: "arch-row arch-output" },
        h("span", { class: "ao-label", text: "Output" }),
        archChip("verify", "Verified findings"), archChip("evidence", "Evidence ledger"), archChip("report", "Report"), archChip("outputs", "Run directory")),
      h("div", { class: "arch-row arch-under" },
        group("tone-violet", null, archBtn("llm-gateway", "Every model phase: LLMGateway", "one protocol; phases never touch an SDK", "arch-box tone-violet head"),
          h("div", { class: "arch-stack" }, backends)),
        group("tone-violet", null, archBtn("tool-gateway", "Every tool call: ToolGateway", "layers, outermost first", "arch-box tone-violet head"),
          h("div", { class: "arch-stack layers" }, layers),
          h("div", { class: "arch-chips" }, archChip("tool-gateway", "MCP: " + F.servers_enabled_count + " of " + F.server_count + " servers enabled")))),
      group("tone-amber arch-concepts", "Key platform concepts",
        h("div", { class: "arch-chips" },
          archChip("state-machine", "Explicit state machine, not just an LLM"), archChip("state", "Structured state"),
          archChip("evidence", "Evidence ledger, not just the prompt"), archChip("checkpoints", "Checkpoints, resume and replay"),
          archChip("faults", "Fault injection"), archChip("verify", "Deterministic verification"),
          archChip("budgets", "Budgets and stop rules")))),
    down(),
    h("div", { class: "arch-row arch-outside" },
      archBtn("evaluation", "Evaluation harness", "a separate package the agent never imports; scores a finished run", "arch-box tone-plain dashed")),
    h("div", { class: "arch-philosophy" },
      archBtn("philosophy", "LLM proposes, the platform controls", null, "arch-box tone-ink head"),
      h("div", { class: "arch-chips" }, archChip("state", "State"), archChip("policy", "Policy"), archChip("tool-gateway", "Tools"),
        archChip("evidence", "Evidence"), archChip("checkpoints", "Checkpoints"), archChip("verify", "Verification"), archChip("budgets", "Budgets"))));
}

// The Important points under the diagram: one card per point, marked up like a panel, with an optional small
// diagram drawn from its steps. The cards are an accordion: all closed at first, at most one open; its title
// toggles it, and Previous and Next inside open the card before or after it and close this one.
function archImportant(root) {
  const cards = ARCH.data.important || [];
  if (!cards.length) return;
  const last = cards.length - 1;
  const step = (i, label, cls) => h("button", { class: "btn " + cls, type: "button", title: label + ": " + cards[i].title,
    onclick: () => archImpOpen(i, true) }, label + ": " + cards[i].title);
  root.append(h("section", { class: "arch-important", "aria-labelledby": "ai-title" },
    h("h2", { class: "ai-title", id: "ai-title", text: "Important points" }),
    cards.map((c, i) => h("article", { class: "ai-card" },
      h("h3", { class: "ai-head" },
        h("button", { class: "ai-toggle", type: "button", id: "ai-toggle-" + i, "aria-expanded": "false", "aria-controls": "ai-body-" + i,
          onclick: (ev) => archImpOpen(ev.currentTarget.getAttribute("aria-expanded") === "true" ? null : i, false) },
          h("span", { class: "ai-chev", "aria-hidden": "true" }), h("span", { text: c.title }))),
      h("div", { class: "ai-body", id: "ai-body-" + i, role: "region", "aria-labelledby": "ai-toggle-" + i, hidden: true },
        c.lead ? h("p", { class: "ai-lead" }, archInline(c.lead)) : null,
        c.diagram ? h("div", { class: "ai-diagram" }, archSteps(c.diagram)) : null,
        c.points ? h("ul", { class: "ai-points" + (c.columns ? " cols" : "") }, c.points.map(archPoint)) : null,
        c.foot ? h("p", { class: "ai-foot" }, archInline(c.foot)) : null,
        h("div", { class: "ai-nav" },
          i > 0 ? step(i - 1, "Previous", "quiet ai-prev") : h("span"),
          i < last ? step(i + 1, "Next", "ai-next") : null))))));
}
// Open card i (null closes them all) and close every other; from Previous or Next, the opened card's title takes the
// focus and is scrolled into view, so the reader stays at the top of what they asked for.
function archImpOpen(i, moved) {
  document.querySelectorAll(".ai-card").forEach((card, k) => {
    const open = k === i;
    card.classList.toggle("open", open);
    card.querySelector(".ai-toggle").setAttribute("aria-expanded", String(open));
    card.querySelector(".ai-body").hidden = !open;
  });
  if (moved && i !== null) {
    const t = document.getElementById("ai-toggle-" + i);
    t.focus({ preventScroll: true });
    t.scrollIntoView({ block: "nearest" });
  }
}
// A column of steps with an arrow between each two. A step is a box (a button when it names a topic), two lanes
// side by side ({split}), the layers a fact lists ({layers}, e.g. the tool gateway's, outermost first) or chips.
function archSteps(steps) {
  const out = [];
  steps.forEach((s, i) => { if (i) out.push(down()); out.push(archCardStep(s)); });
  return h("div", { class: "ai-steps" }, out);
}
function archCardStep(s) {
  if (s.split) return h("div", { class: "ai-split" }, s.split.map(archSteps));
  if (s.layers) {
    const col = archSteps(ARCH.data.facts[s.layers].map((l) => ({ box: l, topic: ARCH_LAYER_TOPIC[l] || "tool-gateway" })));
    col.classList.add("ai-layers");
    return col;
  }
  if (s.chips) return h("div", { class: "arch-chips ai-chips" }, s.chips.map((t) => h("span", { class: "ai-chip", text: t })));
  const cls = "arch-box " + (s.tone ? "tone-" + s.tone + " head" : "tone-plain");
  if (s.topic) return archBtn(s.topic, s.box, s.sub || null, cls);
  return h("div", { class: cls + " static" }, h("span", { class: "ab-title", text: s.box }), s.sub ? h("span", { class: "ab-sub", text: s.sub }) : null);
}

// The column beside the diagram while no topic is open (wide screens): how to read it and where to start.
function archGuide() {
  const g = clear($("arch-guide"));
  const first = ARCH.data.order[0];
  g.append(h("h2", { text: "Read the diagram" }),
    h("p", { text: "Every box and every chip is a part of the agent. Select one to read about it: Simple in plain words, Advanced with the schemas, limits, failure paths and the files that hold them." }),
    h("p", { text: "The left and right arrow keys, or Next, walk the parts in pipeline order." }),
    h("button", { class: "btn", type: "button", text: "Start with " + archTitle(first), onclick: (ev) => archToggle(first, ev.currentTarget) }),
    h("div", { class: "arch-legend" },
      h("span", { class: "lg tone-blue", text: "ingest and stage 1" }), h("span", { class: "lg tone-green", text: "research" }),
      h("span", { class: "lg tone-red", text: "after stage 1" }), h("span", { class: "lg tone-violet", text: "gateways" }),
      h("span", { class: "lg tone-amber", text: "platform concepts" })));
}

// ------------------------------------------------------------------ the panel

function archToggle(key, el) {
  if (ARCH.topic === key) { archClose(); return; }
  archOpen(key, el);
}

// focus: false when the page opens on a topic from its address (the reader has not acted yet)
function archOpen(key, el, focus) {
  if (el) ARCH.from = el;
  ARCH.topic = key;
  archUrl();
  archPaint();
  if (focus !== false) $("ap-title").focus();
  archLoadRun();
}

function archClose() {
  const key = ARCH.topic;
  ARCH.topic = null;
  archUrl();
  archPaint();
  const back = ARCH.from && document.contains(ARCH.from) ? ARCH.from : (key ? document.querySelector('.arch-surface [data-topic="' + key + '"]') : null);
  ARCH.from = null;
  if (back) back.focus();
}

function archUrl() {
  const u = "/?page=architecture" + (ARCH.topic ? "&topic=" + encodeURIComponent(ARCH.topic) : "") +
    (new URLSearchParams(location.search).get("from") ? "&from=" + encodeURIComponent(ARCH.run || "") : "");
  history.replaceState(null, "", u);
}

function archStep(delta) {
  const order = ARCH.data.order;
  const i = order.indexOf(ARCH.topic);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= order.length) return;
  ARCH.from = null;
  archOpen(order[j], null);
}

function archKeys(e) {
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
  if (e.key === "ArrowRight" && !e.target.closest('[role="tablist"]')) { e.preventDefault(); archStep(1); }
  else if (e.key === "ArrowLeft" && !e.target.closest('[role="tablist"]')) { e.preventDefault(); archStep(-1); }
}

function archSetTab(tab) {
  ARCH.tab = tab;
  try { localStorage.setItem(ARCH_TAB_KEY, tab); } catch (e) { /* storage off */ }
  archPaint();
  const on = document.querySelector('#ap-tabs [data-tab="' + tab + '"]');
  if (on) on.focus();
}

function archPaint() {
  const panel = $("arch-panel");
  if (!panel) return;
  const key = ARCH.topic;
  $("arch-wrap").classList.toggle("panel-open", !!key);
  panel.hidden = !key;
  for (const b of document.querySelectorAll(".arch-surface [data-topic]")) {
    const on = b.dataset.topic === key;
    b.classList.toggle("on", on);
    b.setAttribute("aria-expanded", String(on));
  }
  if (!key) return;
  const T = ARCH.data.topics[key];
  $("ap-kicker").textContent = T.kind;
  $("ap-title").textContent = T.title;
  const tabs = clear($("ap-tabs"));
  for (const [k, label] of [["simple", "Simple"], ["advanced", "Advanced"]]) {
    tabs.append(h("button", { class: "tab" + (ARCH.tab === k ? " on" : ""), type: "button", role: "tab", id: "ap-tab-" + k, "data-tab": k,
      "aria-selected": String(ARCH.tab === k), "aria-controls": "ap-content", tabindex: ARCH.tab === k ? "0" : "-1", text: label,
      onclick: () => archSetTab(k),
      onkeydown: (e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); archSetTab(k === "simple" ? "advanced" : "simple"); } } }));
  }
  const c = clear($("ap-content"));
  c.setAttribute("aria-labelledby", "ap-tab-" + ARCH.tab);
  c.dataset.tab = ARCH.tab;
  if (ARCH.tab === "simple") archSimple(c, T); else archAdvanced(c, T);
  archNav();
}

function archSimple(c, T) {
  const S1 = T.simple;
  c.append(h("p", { class: "arch-lead" }, archInline(S1.lead)));
  if (S1.table) {
    c.append(h("table", { class: "arch-table arch-simple-table" },
      h("thead", {}, h("tr", {}, S1.table.cols.map((t) => h("th", { text: t })))),
      h("tbody", {}, S1.table.rows.map((r) => h("tr", {}, r.map((cell) => h("td", {}, archInline(cell))))))));
  }
  if (S1.points && S1.points.length) c.append(h("ul", { class: "arch-points" }, S1.points.map(archPoint)));
  if (S1.flow) c.append(h("div", { class: "arch-flow" }, h("span", { class: "ac-label", text: "Flow" }), h("span", {}, archInline(S1.flow))));
  if (S1.contrast) {
    c.append(h("div", { class: "arch-contrast" },
      h("div", { class: "ac-row bad" }, h("span", { class: "ac-label", text: S1.contrast.bad_label || "Bad" }), h("span", {}, archInline(S1.contrast.bad))),
      h("div", { class: "ac-row better" }, h("span", { class: "ac-label", text: S1.contrast.better_label || "Much better" }), h("span", {}, archInline(S1.contrast.better)))));
  }
}

// A point is a sentence, or { text, sub } with its examples as a nested list under it.
function archPoint(p) {
  if (typeof p === "string") return h("li", {}, archInline(p));
  return h("li", {}, archInline(p.text), h("ul", { class: "arch-sub" }, (p.sub || []).map((q) => h("li", {}, archInline(q)))));
}

// The lead, a point, the flow or a contrast line may mark words **bold** or __underlined__, nested either way, and link
// [words](tip:key), [words](run:stage) or [words](https link); the rest stays plain text.
function archInline(text) {
  return String(text).split(/(\[[^\]]+\]\(https:\/\/[^)\s]+\)|\*\*.+?\*\*|__.+?__|\[[^\]]+\]\((?:tip|run):\w+\))/).filter(Boolean).flatMap((part) => {
    const out = /^\[(?<label>[^\]]+)\]\((?<href>https:\/\/[^)\s]+)\)$/.exec(part);
    if (out) return [archOutLink(out.groups.label, out.groups.href)];
    const tip = /^\[(?<label>[^\]]+)\]\(tip:(?<key>\w+)\)$/.exec(part);
    if (tip) return [archTip(tip.groups.label, tip.groups.key)];
    const run = /^\[(?<label>[^\]]+)\]\(run:(?<stage>\w+)\)$/.exec(part);
    if (run) return [archSeeLink(run.groups.label, run.groups.stage)];
    const m = /^(?<mark>\*\*|__)(?<body>.+)\k<mark>$/.exec(part);
    return m ? [h(m.groups.mark === "**" ? "strong" : "u", {}, archInline(m.groups.body))] : archNoBreak(part);
  });
}
// [words](https link): the words open that page in a new tab.
function archOutLink(label, href) {
  return h("a", { class: "arch-out", href, target: "_blank", rel: "noopener noreferrer", text: label + "\u00a0↗" });
}
// [words](run:stage): the words open that stage's panel on the Run log of the run the page reads its values from
// (ARCH.run, the same link as "Open this stage in the run log"); with no finished run they stay plain words.
function archSeeLink(label, stage) {
  if (!ARCH.run) return label;
  const a = archRunLink(stage);
  a.className = "arch-see";
  a.textContent = label + "\u00a0→";   // the arrow never wraps onto a line of its own
  return a;
}
// [words](tip:key): the words (which may be marked up), then a "?", show the tip ARCH.data.tips[key] on hover or keyboard focus.
function archTip(label, key) {
  const T = (ARCH.data.tips || {})[key];
  if (!T) return label;
  const id = "arch-tip-" + key;
  return h("span", { class: "arch-tip", tabindex: "0", "aria-describedby": id,
    onmouseenter: (ev) => archPlaceTip(ev.currentTarget), onfocus: (ev) => archPlaceTip(ev.currentTarget) }, archInline(label),
    h("span", { class: "arch-tipq", "aria-hidden": "true", text: "?" }),
    h("span", { class: "arch-tipbox", role: "tooltip", id },
      T.head ? h("span", { class: "atb-head", text: T.head }) : null,
      h("span", { class: "atb-items" }, (T.items || []).map((t) => h("span", { class: "atb-item", text: t }))),
      T.foot ? h("span", { class: "atb-foot", text: T.foot }) : null));
}
// The tip is fixed to the viewport (the panel's scroll box would clip it): under the term's line, as wide as its
// point, or above the line when the space below is too small.
function archPlaceTip(term) {
  const box = term.querySelector(".arch-tipbox");
  const line = term.closest("li") || term;
  const r = line.getBoundingClientRect(), t = term.getBoundingClientRect();
  box.style.left = r.left + "px";
  box.style.width = r.width + "px";
  box.classList.remove("up");
  box.style.top = t.bottom + "px";
  if (t.bottom + box.offsetHeight > window.innerHeight) { box.classList.add("up"); box.style.top = t.top - box.offsetHeight + "px"; }
}
// A hyphenated name (mcp-internet-search, EV-(n)) never breaks across lines at its hyphens.
function archNoBreak(text) {
  // split() puts the matched names at the odd indices; only those are kept whole.
  return text.split(/(\w+(?:-[\w()]+)+)/).map((t, i) => (i & 1 ? h("span", { class: "nobr", text: t }) : t)).filter(Boolean);
}

// A snake_case name may wrap after an underscore (a zero-width space), never inside a word.
function archBreakable(name) { return String(name).split("_").join("_\u200b"); }

function archAdvanced(c, T) {
  const F = ARCH.data.facts;
  for (const b of T.advanced || []) {
    const block = h("div", { class: "arch-block" }, h("h3", { text: b.h }));
    if (b.shards) {
      block.append(h("table", { class: "arch-table" }, h("thead", {}, h("tr", {}, h("th", { text: "Shard" }), h("th", { text: "Criteria" }))),
        h("tbody", {}, F.shards.map((s) => h("tr", {}, h("td", { class: "mono", text: archBreakable(s.name) }), h("td", { text: s.criteria.map((x) => x.split("_").join(" ")).join(", ") }))))));
    }
    if (b.servers) {
      block.append(h("ul", { class: "arch-servers" }, F.servers.map((s) => h("li", {}, h("span", { class: "mono", text: s.name }),
        h("span", { class: "pill " + (s.enabled ? "done" : "waiting"), text: s.enabled ? "enabled" : "off" })))));
    }
    if (b.items && b.items.length) block.append(h("ul", { class: "arch-items" }, b.items.map((i) => h("li", { text: i }))));
    if (b.src) block.append(h("div", { class: "xsrc" }, "From ", h("span", { class: "mono", text: b.src.split(";").map((s) => s.trim()).join(" · ") })));
    c.append(block);
  }
  if (T.stages && T.stages.length) c.append(h("div", { class: "arch-block arch-inrun", id: "ap-inrun" }));
  archInRun();
}

function archNav() {
  const order = ARCH.data.order;
  const i = order.indexOf(ARCH.topic);
  const nav = clear($("ap-nav"));
  const prev = i > 0 ? order[i - 1] : null;
  const next = i >= 0 && i + 1 < order.length ? order[i + 1] : null;
  nav.append(
    prev ? h("button", { class: "btn quiet", type: "button", "data-step": "prev", text: "Previous: " + archTitle(prev), onclick: () => archStep(-1) }) : h("span", {}),
    next ? h("button", { class: "btn", type: "button", "data-step": "next", text: "Next: " + archTitle(next), onclick: () => archStep(1) }) : h("span", {}));
}

// ------------------------------------------------------------------ "In this run": the stage panel's own route

function archStagesOf(T) {
  const out = [];
  for (const s of T.stages || []) {
    if (s === "shards") ARCH.data.facts.shards.forEach((_, i) => out.push("assess-" + (i + 1)));
    else out.push(s);
  }
  return out;
}

async function archLoadRun() {
  const T = ARCH.topic ? ARCH.data.topics[ARCH.topic] : null;
  if (!T || !ARCH.run) return;
  const want = archStagesOf(T).filter((s) => !ARCH.views.has(ARCH.run + "/" + s));
  if (!want.length) return;
  const ask = ++ARCH.ask;
  await Promise.all(want.map(async (s) => {
    const k = ARCH.run + "/" + s;
    try { ARCH.views.set(k, await api("/runs/" + encodeURIComponent(ARCH.run) + "/stage/" + encodeURIComponent(s))); }
    catch (e) { ARCH.views.set(k, { error: e.message }); }
  }));
  if (ask === ARCH.ask) archInRun();
}

function archFacts(v) {
  const dl = h("dl", { class: "kv sp-facts" });
  for (const f of v.facts || []) {
    if (f.value === null || f.value === undefined || f.value === "" || /SHA-256/.test(f.label)) continue;
    dl.append(h("dt", { text: sentence(f.label) }), h("dd", { class: f.mono ? "mono" : null, text: typeof f.value === "number" ? intl(f.value) : String(f.value) }));
  }
  const labels = new Set((v.facts || []).map((f) => String(f.label).toLowerCase()));
  for (const l of v.lists || []) {
    if (labels.has(String(l.title).toLowerCase())) continue;
    dl.append(h("dt", { text: sentence(l.title) }), h("dd", { class: "num", text: intl(l.count) }));
  }
  return dl;
}

function archRunLink(stage) {
  const key = stage === "report" ? "verdict" : (stage.startsWith("assess-") ? "assess " + stage.slice("assess-".length) : stage);
  const u = "/?run=" + encodeURIComponent(ARCH.run) + "&tab=log&stage=" + encodeURIComponent(key);
  return h("a", { class: "arch-runlink", href: u, text: "Open this stage in the run log" });
}

function archInRun() {
  const box = $("ap-inrun");
  if (!box || !ARCH.topic) return;
  const T = ARCH.data.topics[ARCH.topic];
  clear(box);
  box.append(h("h3", {}, "In this run ", ARCH.run ? h("span", { class: "mono arch-runid", text: ARCH.run }) : null));
  if (!ARCH.run) { box.append(h("p", { class: "notice", text: "No finished run in this server's runs directory." })); return; }
  const stages = archStagesOf(T);
  if (stages.some((s) => !ARCH.views.has(ARCH.run + "/" + s))) { box.append(h("p", { class: "notice", text: "Reading the run's files." })); return; }
  if (T.stages.includes("shards")) {
    const rows = stages.map((s) => ARCH.views.get(ARCH.run + "/" + s)).filter((v) => v && !v.error && (v.lists || []).length);
    box.append(h("table", { class: "arch-table" },
      h("thead", {}, h("tr", {}, h("th", { text: "Shard" }), h("th", { text: "Outcome" }), h("th", { class: "num", text: "Draft findings" }))),
      h("tbody", {}, rows.map((v) => {
        const fact = (label) => ((v.facts || []).find((f) => f.label === label) || {}).value;
        const findings = (v.lists || []).find((l) => l.key === "findings");
        return h("tr", {}, h("td", { class: "mono", text: archBreakable(fact("shard") || v.stage) }), h("td", { text: String(fact("outcome") || "") }),
          h("td", { class: "num", text: findings ? intl(findings.count) : "" }));
      }))));
    box.append(archRunLink("merge"));
    return;
  }
  for (const s of stages) {
    const v = ARCH.views.get(ARCH.run + "/" + s);
    if (stages.length > 1) box.append(h("div", { class: "arch-inrun-stage", text: v && v.title ? v.title : s }));
    if (!v || v.error) { box.append(h("p", { class: "notice", text: "This stage could not be read" + (v && v.error ? ": " + v.error : ".") })); continue; }
    box.append(archFacts(v), archRunLink(s));
  }
}
