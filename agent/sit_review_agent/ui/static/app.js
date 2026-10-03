// SIT review page (dra ui). Vanilla JS, no framework, nothing loaded from the network but this server.
// Rules this file keeps (docs/design/ui_design.md, tests/test_ui_honesty.py):
// - every number shown comes from the run directory (via the server's JSON) or the event stream;
// - the run view draws from each event's `event` and `fields` only and never parses `message`;
// - review text is inserted as textContent, exactly as report.json has it (no rewording);
// - no animation; times are as of the last event, never ticked by the browser clock.
"use strict";

const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
function tpl(id) { return $(id).content.cloneNode(true); }
function words(v) { return v === null || v === undefined ? "" : String(v).split("_").join(" "); }
function sentence(v) { const s = words(v); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function pad2(n) { return String(n).padStart(2, "0"); }
function clock(s) { if (typeof s !== "number") return "–"; const t = Math.max(0, Math.floor(s)); return pad2(Math.floor(t / 60)) + ":" + pad2(t % 60); }
function dur(s) { if (typeof s !== "number") return "–"; const t = Math.max(0, Math.round(s)); return Math.floor(t / 60) + ":" + pad2(t % 60); }
function money(c, lower) { return typeof c === "number" ? (lower ? "≥ $" : "$") + c.toFixed(2) : "–"; }
function conf(c) { return typeof c === "number" ? c.toFixed(2) : "–"; }
function intl(n) { return typeof n === "number" ? n.toLocaleString("en-US") : "–"; }

async function api(url, opts) {
  const res = await fetch(url, opts);
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (!res.ok) throw new Error((body && body.error) || ("HTTP " + res.status));
  return body;
}

const S = { meta: null, runId: null, es: null, model: null };

function topBar({ doc, tabs, meta, action }) {
  $("top-doc").textContent = doc || "";
  const t = clear($("top-tabs"));
  t.hidden = !tabs || !tabs.length;
  for (const tab of tabs || []) t.append(h("button", { class: "tab" + (tab.on ? " on" : ""), type: "button", onclick: tab.go, text: tab.label }));
  const m = clear($("top-meta"));
  for (const part of meta || []) m.append(part);
  const a = clear($("top-action"));
  if (action) a.append(action);
}

function joinMeta(parts) {
  const out = [];
  parts.filter((p) => p !== null && p !== undefined && p !== "").forEach((p, i) => { if (i) out.push(" · "); out.push(p); });
  return out;
}

// ------------------------------------------------------------------ frame 1: the drop screen

async function showDrop() {
  closeStream();
  const meta = S.meta;
  topBar({ doc: "no run open", meta: joinMeta([meta.commit ? "agent " + meta.commit : null, h("span", { title: meta.runs_dir, text: "run directories in " + meta.runs_dir_name + "/" })]) });
  const app = clear($("app"));
  app.append(tpl("tpl-drop"));
  const sel = $("profile-select");
  for (const p of meta.profiles) sel.append(h("option", { value: p.name, text: p.label + " · " + dur(p.deadline_s) }));
  const demo = meta.profiles.find((p) => p.name === "demo");
  if (demo) sel.value = "demo";
  const enabled = meta.tools.filter((t) => t.enabled).map((t) => t.name);
  $("tools-help").textContent = enabled.length ? "Enabled in config/tools.yaml: " + enabled.join(", ") + "." : "No tool server is enabled in config/tools.yaml.";
  let doc = null;
  const refresh = () => {
    const p = meta.profiles.find((x) => x.name === sel.value);
    $("profile-help").textContent = p ? "Stage 1 ends by " + clock(p.stage_limits_s.stage_1_end) + ", refine by " + clock(p.stage_limits_s.refine_end) + ", verdict by " + clock(p.stage_limits_s.verdict_end) + ", deadline " + clock(p.deadline_s) + "." : "";
    const prev = $("prev-input").files[0];
    const rid = $("run-id").value.trim() || "<new run>";
    const parts = ["dra", "review", doc ? "runs/" + rid + "/ui/input/" + doc.name : "<document>"];
    if (sel.value) parts.push("--profile", sel.value);
    if (prev) parts.push("--v1", "runs/" + rid + "/ui/input/previous/" + prev.name);
    if ($("no-tools").checked) parts.push("--no-tools");
    parts.push("--run-id", rid);
    $("cmd-preview").textContent = parts.join(" ");
    $("start-btn").disabled = !doc || !meta.can_launch;
  };
  const choose = (f) => { doc = f || null; const c = $("doc-chosen"); c.hidden = !doc; c.textContent = doc ? doc.name : ""; refresh(); };
  $("doc-input").addEventListener("change", (e) => choose(e.target.files[0]));
  $("prev-input").addEventListener("change", () => { const f = $("prev-input").files[0]; $("prev-chosen").textContent = f ? f.name : "No file chosen"; $("prev-chosen").classList.toggle("muted", !f); refresh(); });
  for (const id of ["profile-select", "no-tools"]) $(id).addEventListener("change", refresh);
  $("run-id").addEventListener("input", refresh);
  const dz = $("dropzone");
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over"); if (e.dataTransfer.files.length) choose(e.dataTransfer.files[0]); });
  if (!meta.can_launch) $("start-note").textContent = meta.launch_note;
  $("start-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!doc) return;
    const fd = new FormData();
    fd.append("document", doc);
    const prev = $("prev-input").files[0];
    if (prev) fd.append("previous", prev);
    fd.append("profile", sel.value);
    if ($("run-id").value.trim()) fd.append("run_id", $("run-id").value.trim());
    if ($("no-tools").checked) fd.append("no_tools", "1");
    $("start-btn").disabled = true;
    try {
      const r = await api("/runs", { method: "POST", body: fd });
      go(r.run_id);
    } catch (err) {
      const box = $("start-error"); box.hidden = false; box.textContent = err.message; refresh();
    }
  });
  refresh();
  const runs = await api("/runs");
  const tb = $("runs-table").querySelector("tbody");
  if (!runs.runs.length) $("runs-note").textContent = "No run directory yet. A run started here, or with dra review in a terminal, appears in this list.";
  for (const r of runs.runs) {
    const verdict = r.status === "running" ? h("span", { class: "pill running", text: "running" })
      : (r.verdict ? words(r.verdict) + " · " + conf(r.confidence) : (r.status === "ended" ? "no report" : "–"));
    tb.append(h("tr", { class: "link", onclick: () => go(r.run_id) },
      h("td", {}, h("a", { href: "/?run=" + encodeURIComponent(r.run_id), text: r.run_id, onclick: (e) => { e.preventDefault(); go(r.run_id); } })),
      h("td", { text: r.document || "–" }), h("td", { style: "white-space:nowrap" }, verdict),
      h("td", { class: "r", text: r.findings === null ? "–" : r.findings }),
      h("td", { class: "r", text: dur(r.wall_s) }), h("td", { class: "r", text: money(r.cost_usd, r.cost_lower_bound) })));
  }
}

// ------------------------------------------------------------------ frame 2: the run, from the event stream
// Each record of progress.jsonl (spec/progress_event.schema.json; ui/events.py) is applied to a model by its
// `type` and `fields`; `message` is shown verbatim in the status feed and read nowhere else.

const STAGE1 = ["ingest", "understand", "plan", "research"];
const SEQ = [
  { phase: "merge", when: "code", about: "renumbers the shard findings in shard order, writes shard evidence to the ledger" },
  { phase: "refine", limit: "refine_end", about: "one call: merge duplicates, withdraw, rank, severity, disposition, decision links" },
  { phase: "verify", when: "code", about: "every quote checked against the canonical page text" },
  { phase: "verdict", limit: "verdict_end", about: "verdict-only call, else the rule-based verdict" },
  { phase: "report", limit: "deadline", about: "report.md and report.json rendered in code, invariants checked" },
];
// call_closed outcomes that end the call without an answer (the schema's enum, less ok, cut and replaced).
const CALL_FAILED = ["refusal", "truncated", "error", "cancelled", "interrupted"];

function newRunModel() {
  return { limits: null, deadline: null, profile: null, mode: null, replay: false, resumed: false, shardCount: null, lastT: 0,
    tracks: new Map(), byCall: new Map(), drafts: [], seen: new Set(), events: [], finished: null, error: null, verdict: null,
    stopRule: null, doc: null, runId: null };
}

function track(m, key, label) {
  if (!m.tracks.has(key)) m.tracks.set(key, { key, label: label || key, status: "waiting", call: null, start: null, end: null, text: null, strong: null, cutAt: null, skippedAt: null, shard: null });
  return m.tracks.get(key);
}

// The run clock (resume-adjusted, the clock the stage limits use) when the record has it, else the sink clock.
function at(ev) { return typeof ev.run_s === "number" ? ev.run_s : ev.t; }
function shardKey(m, shard) { return shard ? "assess " + shard + "/" + (m.shardCount || "?") : null; }
function whoOf(m, shard, callId) { return shard ? shard + "/" + (m.shardCount || "?") : (callId || ""); }
// A track in flight: "running" live, "replayed" when the stream is dra replay serving recorded calls.
function inFlight(m) { return m.replay ? "replayed" : "running"; }

function addDraft(m, key, t, d, who) {
  if (m.seen.has(key) || !d) return;
  m.seen.add(key);
  m.drafts.unshift({ t, severity: d.severity, kind: d.kind, title: d.title, who });
}

function applyEvent(m, ev) {
  const f = ev.fields || {};
  const now = at(ev);
  m.lastT = Math.max(m.lastT, now);
  if (ev.console) m.events.push(ev);
  switch (ev.type) {
    case "run_started":
      m.runId = f.run_id; m.mode = f.mode ?? null; m.replay = f.mode === "replay"; m.resumed = m.resumed || !!f.resumed;
      m.limits = f.stage_limits_s || null; m.deadline = f.deadline_s ?? null; m.profile = f.profile ?? null;
      if (Array.isArray(f.shards) && f.shards.length) m.shardCount = f.shards.length;
      m.doc = (f.documents || []).find((d) => d.role === "under_review") || (f.documents || [])[0] || m.doc;
      break;
    case "run_resuming": m.resumed = true; break;
    case "document_ingested":
      if (f.role === "under_review" || !m.doc) m.doc = { ...(m.doc || {}), title: f.title, pages: f.pages, sections: f.sections };
      break;
    case "phase_started": { const t = track(m, ev.phase); if (t.status !== "cut") t.status = inFlight(m); if (t.start === null) t.start = now; break; }
    case "phase_done": {
      const t = track(m, ev.phase);
      if (t.status !== "cut" && t.status !== "failed") t.status = "done";
      t.end = now; if (t.start === null) t.start = now - (f.seconds || 0);
      if (f.stopped_at_limit) { t.strong = null; t.text = "stopped at the stage limit"; }
      break;
    }
    case "research_started": { const t = track(m, "research"); t.strong = null; t.text = intl(f.questions) + " question(s) to research"; break; }
    case "research_stopped": { const t = track(m, "research"); t.strong = null; t.text = words(f.code) + ": " + intl(f.answered) + " of " + intl(f.questions) + " question(s) answered, " + intl(f.tool_calls) + " tool call(s)"; break; }
    case "phase_skipped": { const t = track(m, ev.phase); t.status = "skipped"; t.skippedAt = now; t.strong = null; t.text = words(f.reason); break; }
    case "research_skipped": { const t = track(m, "research"); t.status = "skipped"; t.skippedAt = now; t.strong = null; t.text = words(f.reason); break; }
    case "research_doc_only": { const t = track(m, "research"); t.strong = f.degradation_id || null; t.text = (f.degradation_id ? " in the report · " : "") + "document only: " + (f.detail || ""); break; }
    case "call_opened": {
      const key = (ev.phase === "assess" && shardKey(m, f.shard)) || ev.phase;
      const t = track(m, key);
      t.call = f.call_id; if (t.status !== "cut") t.status = inFlight(m); if (t.start === null) t.start = now; if (f.shard_name) t.shard = f.shard_name;
      m.byCall.set(f.call_id, t);
      break;
    }
    case "call_status":
      for (const c of f.calls || []) {
        const t = m.byCall.get(c.call_id); if (!t) continue;
        if (typeof c.items === "number" && c.items > 0) { t.strong = intl(c.items); t.text = (c.items === 1 ? " item" : " items") + " streamed" + (typeof c.chars === "number" ? " (" + intl(c.chars) + " chars)" : ""); }
        else if (typeof c.chars === "number" && c.chars > 0) { t.strong = null; t.text = "answer streaming (" + intl(c.chars) + " chars)"; }
        else if (typeof c.thinking_tokens === "number" && c.thinking_tokens > 0) { t.strong = null; t.text = "thinking ~" + intl(c.thinking_tokens) + " tokens"; }
        else { t.strong = null; t.text = "starting"; }
      }
      break;
    case "call_retry": { const t = track(m, ev.phase); t.strong = null; t.text = "retry: " + words(f.reason); break; }
    case "call_closed": {
      const t = m.byCall.get(f.call_id); if (!t) break;
      t.end = now;
      if (f.outcome === "cut") { t.status = "cut"; t.cutAt = now; t.strong = null; t.text = typeof f.kept_items === "number" ? "kept " + intl(f.kept_items) + " finished item(s)" : t.text; }
      else if (f.outcome === "replaced") { t.end = null; }
      else if (CALL_FAILED.includes(f.outcome)) { t.status = "failed"; t.strong = null; t.text = words(f.outcome); }
      else if (t.key.startsWith("assess ")) t.status = "done";
      break;
    }
    case "draft_item":
      if (f.list === "findings") addDraft(m, f.call_id + "#" + f.index, now, f, whoOf(m, f.shard, f.call_id));
      break;
    case "shard_drafted": {
      const t = m.byCall.get(f.call_id) || track(m, shardKey(m, f.shard));
      t.strong = intl(f.findings); t.text = " draft finding(s), " + intl(f.sound_areas) + " sound area(s), unverified";
      for (const d of f.drafts || []) addDraft(m, f.call_id + "#" + d.index, now, d, whoOf(m, f.shard, f.call_id));
      break;
    }
    case "shard_cut": {
      const t = (f.call_id && m.byCall.get(f.call_id)) || track(m, shardKey(m, f.shard));
      t.status = "cut"; t.cutAt = f.cut_at_s ?? now; t.end = t.cutAt;
      t.strong = f.degradation_id || null;
      t.text = (f.degradation_id ? " in the report · " : "") + "kept " + intl(f.kept) + " finished finding(s)" + ((f.criteria_not_assessed || []).length ? "; not assessed: " + f.criteria_not_assessed.join(", ") : "");
      for (const d of f.kept_drafts || []) addDraft(m, f.call_id + "#" + d.index, now, d, whoOf(m, f.shard, f.call_id));
      break;
    }
    case "shard_failed": { const t = track(m, shardKey(m, f.shard)); t.status = "failed"; t.end = now; t.strong = null; t.text = f.error || "failed"; break; }
    case "shards_merged": {
      const t = track(m, "merge"); t.status = "done"; if (t.start === null) t.start = now; t.end = now;
      t.strong = intl(f.findings); t.text = " findings, " + intl(f.sound_areas) + " sound area(s) from " + intl(f.shards) + " shard(s)" + ((f.degraded_shards || []).length ? "; degraded: " + f.degraded_shards.join(", ") : "");
      break;
    }
    case "call_cut": {
      const t = m.byCall.get(f.call_id); if (!t) break;
      t.status = "cut"; t.cutAt = f.at_s ?? now; t.end = t.cutAt; t.strong = null; t.text = "kept " + intl(f.kept_items) + " finished item(s)";
      break;
    }
    case "stop_rule": m.stopRule = f; break;
    case "milestone": {
      const t = track(m, ev.phase); const counts = Object.entries(f).filter(([k, v]) => k !== "name" && typeof v === "number");
      t.strong = null; t.text = f.name + (counts.length ? ": " + counts.map(([k, v]) => intl(v) + " " + words(k)).join(", ") : "");
      break;
    }
    case "verdict": {
      m.verdict = f; const t = track(m, "verdict"); t.status = "done"; if (t.start === null) t.start = now; t.end = now;
      t.strong = words(f.label); t.text = " · confidence " + conf(f.confidence) + " · " + intl(f.findings) + " findings";
      break;
    }
    case "run_error":
      m.error = f;
      for (const t of m.tracks.values()) if (t.status === "running" || t.status === "replayed") { t.status = "stopped"; t.end = now; }
      break;
    case "run_finished": m.finished = f; break;
    default: break;
  }
}

function trackRow(m, t, limit) {
  const pillText = t.status === "cut" ? "cut at " + clock(t.cutAt) : t.status;
  const pos = t.status === "waiting" ? null : (t.end ?? m.lastT);
  let time;
  if (t.status === "skipped") time = h("div", { class: "time num muted", text: "at " + clock(t.skippedAt) });
  else if (pos === null) time = h("div", { class: "time num muted", text: limit !== null && limit !== undefined ? "by " + clock(limit) : "" });
  else {
    const kids = [];
    if (limit) kids.push(h("span", { class: "bar" + (t.end !== null ? " closed" : "") }, h("i", { style: "width:" + Math.min(100, (100 * pos) / limit).toFixed(1) + "%" })));
    kids.push(clock(pos) + (limit ? " / " + clock(limit) : ""));
    time = h("div", { class: "time num" }, kids);
  }
  const status = h("div", { class: "status" });
  { if (t.shard) status.append(t.shard + (t.strong || t.text ? " · " : "")); if (t.strong) status.append(h("b", { text: t.strong })); if (t.text) status.append(t.text); }
  status.title = status.textContent;
  return h("div", { class: "track", "data-track": t.key, "data-status": t.status },
    h("div", { class: "name" }, t.label, t.call ? h("span", { class: "call mono", text: t.call }) : null),
    h("div", {}, h("span", { class: "pill " + t.status, text: pillText })), time, status);
}

function renderRun(m) {
  const lim = m.limits || {};
  const s1 = clear($("stage1-tracks"));
  const keys = [...m.tracks.keys()];
  const shards = keys.filter((k) => k.startsWith("assess ")).sort((a, b) => parseInt(a.slice(7), 10) - parseInt(b.slice(7), 10));
  const order = [...STAGE1, ...(shards.length ? shards : ["assess"])];
  for (const k of order) s1.append(trackRow(m, track(m, k), lim.stage_1_end ?? null));
  $("stage1-limit").textContent = lim.stage_1_end !== undefined ? "ends by " + clock(lim.stage_1_end) : "";
  const seq = clear($("seq-tracks"));
  for (const row of SEQ) {
    const t = track(m, row.phase);
    const limit = row.limit === "deadline" ? m.deadline : (row.limit ? lim[row.limit] : null);
    if (t.status === "waiting" && row.when) {
      seq.append(h("div", { class: "track", "data-track": row.phase, "data-status": "waiting" }, h("div", { class: "name", text: row.phase }), h("div", {}, h("span", { class: "pill waiting", text: "waiting" })),
        h("div", { class: "time num muted", text: row.when }), h("div", { class: "status", text: row.about })));
    } else {
      const r = trackRow(m, t, limit ?? null);
      if (t.status === "waiting") r.querySelector(".status").textContent = row.about;
      seq.append(r);
    }
  }
  const stop = $("stop-rule");
  if (stop) { stop.hidden = !m.stopRule; stop.textContent = m.stopRule ? "Stop rule " + m.stopRule.code + " fired in " + words(m.stopRule.stage) + ": " + m.stopRule.detail + "; skipped to " + words(m.stopRule.to) + "." : ""; }
  $("draft-count").textContent = String(m.drafts.length);
  const d = clear($("drafts"));
  for (const x of m.drafts) {
    const sev = x.kind === "strength" ? "strength" : (x.severity || "");
    d.append(h("div", { class: "draft" }, h("div", { class: "t num mono", text: clock(x.t) }),
      h("div", { class: "line" }, sev ? h("span", { class: "pill " + sev, text: sev }) : null, h("span", { class: "text", text: x.title || "" }), h("span", { class: "who mono", text: x.who }))));
  }
  const feed = clear($("status-feed"));
  for (const ev of [...m.events].reverse()) {
    const marker = { step: "", wait: "... ", warn: "WARN ", done: "OK ", draft: "DRAFT " }[ev.kind] || "";
    const msg = h("div", { class: "msg", text: marker + ev.message }); msg.title = msg.textContent;
    feed.append(h("div", { class: "row" + (ev.kind === "warn" ? " warn" : "") }, h("div", { class: "num mono", text: clock(ev.t) }), h("div", { class: "ph", text: ev.phase }), msg));
  }
}

function closeStream() { if (S.es) { S.es.close(); S.es = null; } }

function runTop(info, m, tabs) {
  const doc = m.doc;
  const docText = [info.run_id, doc ? [doc.title, typeof doc.pages === "number" ? intl(doc.pages) + " pages" : null, typeof doc.sections === "number" ? intl(doc.sections) + " sections" : null].filter(Boolean).join(", ") : info.document].filter(Boolean).join(" · ");
  const metaParts = [h("span", {}, "run clock ", h("b", { text: clock(m.lastT) }), m.deadline ? " of " + clock(m.deadline) : "")];
  if (m.profile) metaParts.push("profile " + m.profile);
  if (m.resumed || info.resumed) metaParts.push(h("span", { class: "pill", text: "resumed" }));
  if (info.replayed || m.replay) metaParts.push(h("span", { class: "pill", id: "replay-stamp", text: "replayed evidence" }));
  let action = null;
  if (info.status === "running" && info.argv && !m.replay) {
    action = h("button", { class: "btn ghost", type: "button", text: "Stop run", onclick: async (e) => {
      e.target.disabled = true;
      try { await api("/runs/" + encodeURIComponent(info.run_id) + "/stop", { method: "POST" }); e.target.textContent = "SIGINT sent"; }
      catch (err) { e.target.textContent = err.message; }
    } });
  }
  topBar({ doc: docText, tabs, meta: joinMeta(metaParts), action });
}

function finishedText(m, end) {
  const f = m.finished;
  if (f) {
    const parts = ["Run finished: " + words(f.outcome) + ", exit " + f.exit_code];
    if (typeof f.wall_s === "number") parts.push(dur(f.wall_s) + " on the run clock");
    if (typeof f.cost_usd === "number") parts.push(money(f.cost_usd, f.cost_is_lower_bound));
    if (m.verdict) parts.push("verdict " + words(m.verdict.label) + ", " + intl(m.verdict.findings) + " findings");
    if (f.exit_code !== 0 && m.error && m.error.resumable) parts.push("resumable with " + m.error.resume);
    return parts.join(" · ") + ".";
  }
  if (m.error) return "The run stopped: " + m.error.error + ", exit " + m.error.exit_code + (m.error.resumable ? "; resumable with " + m.error.resume : "") + ".";
  if (end.exit_code !== null && end.exit_code !== undefined) return "The process exited with code " + end.exit_code + " before a run_finished event.";
  return "The event stream ended.";
}

function showRun(info, tabs) {
  closeStream();
  const app = clear($("app"));
  app.append(tpl("tpl-run"));
  const m = newRunModel();
  S.model = m;
  renderRun(m);
  runTop(info, m, tabs);
  if (info.argv) $("status-feed").before(h("div", { class: "cmd", id: "run-cmd", text: info.argv }));
  if (!info.has_events) {
    $("legend").after(h("p", { class: "notice", text: "This run directory has no progress.jsonl (it was recorded before the structured event stream), so there is no timeline to show." }));
    return;
  }
  const es = new EventSource("/runs/" + encodeURIComponent(info.run_id) + "/events");
  S.es = es;
  let pending = false;
  const paint = () => { pending = false; renderRun(m); runTop(info, m, tabs); };
  es.addEventListener("progress", (e) => {
    applyEvent(m, JSON.parse(e.data));
    if (!pending) { pending = true; requestAnimationFrame(paint); }
  });
  es.addEventListener("end", async (e) => {
    es.close(); S.es = null;
    const end = JSON.parse(e.data || "{}");
    const fresh = await api("/runs/" + encodeURIComponent(info.run_id));
    info.status = fresh.status;
    paint();
    const bar = $("finished-bar");
    if (!bar) return;
    clear(bar).hidden = false;
    bar.append(finishedText(m, end));
    if (fresh.has_report && !tabs) bar.append(h("button", { class: "btn primary", type: "button", text: "Open the review", onclick: () => go(info.run_id) }));
  });
}

// ------------------------------------------------------------------ frame 3: the review

function sevPill(f) {
  const s = f.kind === "strength" ? "strength" : f.severity;
  return s ? h("span", { class: "pill " + s, text: s }) : h("span", { class: "pill", text: words(f.kind) });
}

function pdfLink(P, a) {
  const label = "p." + a.page + " §" + a.section_ref;
  const underReview = (P.report.metadata.documents || []).find((d) => d.role === "under_review");
  if (!P.derived.pdf_available || !underReview || a.doc_id !== underReview.doc_id) return h("span", { text: label });
  return h("a", { href: "/runs/" + encodeURIComponent(S.runId) + "/doc.pdf#page=" + a.page, target: "_blank", rel: "noopener", text: label });
}

function expanded(P, f) {
  const rows = P.derived.anchors[f.id] || [];
  const ok = rows.filter((r) => r.anchor_status === "resolved" || r.anchor_status === "repaired").length;
  const prov = f.provenance || {};
  const metaLine = [words(f.kind), words(f.category), (f.secondary_dispositions || []).length ? "also: " + f.secondary_dispositions.map(words).join(", ") : null,
    prov.phase ? "provenance: " + prov.phase + (prov.model ? ", " + prov.model : "") : null,
    "anchors " + ok + "/" + (f.doc_anchors || []).length + " verified", f.acknowledged_in_doc ? "acknowledged in the document" : null].filter(Boolean).join(" · ");
  const box = h("div", { class: "expanded" },
    h("div", { class: "muted micro" }, metaLine + " · ", h("a", { href: "/runs/" + encodeURIComponent(S.runId) + "/explain/" + f.id, target: "_blank", rel: "noopener", text: "dra explain " + f.id })),
    h("p", { style: "margin-top:8px", class: "statement", text: f.statement }));
  if ((f.doc_anchors || []).length) {
    box.append(h("h3", { text: "Where in the document" }));
    f.doc_anchors.forEach((a, i) => {
      const row = rows.find((r) => r.anchor_index === i && r.anchor_status !== "unresolved");
      const where = row ? row.anchor_status + ", " + row.method + " match" + (row.score !== null && row.score !== undefined ? ", score " + row.score : "") + (row.char_start !== null && row.char_start !== undefined ? ", chars " + intl(row.char_start) + "-" + intl(row.char_end) : "") : null;
      box.append(h("div", { class: "ev" }, h("div", { class: "id" }, pdfLink(P, a)), h("div", { class: "kind", text: (a.requirement_ids || []).join(", ") }),
        h("div", { class: "q" }, h("span", { class: "quote", text: "“" + a.quote + "”" }), where ? h("span", { class: "where", text: " " + where }) : null)));
    });
  }
  if ((f.evidence || []).length) {
    box.append(h("h3", { text: "Evidence (ledger)" }));
    for (const e of f.evidence) {
      const kind = words(e.source_type) + (e.source_type === "inference" ? "" : (e.supports_claim ? ", supports" : ", contrary"));
      const body = e.quote ? "“" + e.quote + "”" : e.url_or_citation;
      const where = e.source_type === "inference" && (e.derived_from || []).length ? " derived from " + e.derived_from.join(", ") : (e.quote ? " " + e.url_or_citation : "");
      box.append(h("div", { class: "ev" }, h("div", { class: "id", text: e.evidence_id }), h("div", { class: "kind", text: kind }),
        h("div", { class: "q" }, h("span", { text: body }), where ? h("span", { class: "where", text: where }) : null)));
    }
  }
  const r = f.recommendation;
  if (r) {
    box.append(h("h3", { text: "Recommendation" }));
    const kv = h("dl", { class: "kv" });
    for (const [k, label] of [["change_summary", "Change"], ["issue", "Issue"], ["rationale", "Rationale"], ["expected_benefit", "Expected benefit"], ["verification", "Verification"]]) {
      if (r[k]) kv.append(h("dt", { text: label }), h("dd", { text: r[k] }));
    }
    if ((r.objective_refs || []).length) kv.append(h("dt", { text: "Objectives" }), h("dd", { text: r.objective_refs.join(", ") }));
    if ((r.supporting_evidence_ids || []).length) kv.append(h("dt", { text: "Evidence" }), h("dd", { text: r.supporting_evidence_ids.join(", ") }));
    if (f.next_step) kv.append(h("dt", { text: "Next step" }), h("dd", { text: f.next_step.owner + ": " + f.next_step.action }));
    box.append(kv);
  } else if (f.next_step) {
    box.append(h("h3", { text: "Next step" }), h("p", { text: f.next_step.owner + ": " + f.next_step.action }));
  }
  if (f.no_change_rationale) box.append(h("h3", { text: "No change, because" }), h("p", { text: f.no_change_rationale }));
  if ((f.affected_decisions || []).length) {
    box.append(h("h3", { text: "Approved decisions" }));
    for (const d of f.affected_decisions) box.append(h("div", { class: "dec" }, h("span", { class: "rel", text: d.relation }), h("span", {}, h("b", { style: "font-weight:500", text: d.registry_id }), " " + d.justification)));
  }
  if (f.reassessment) {
    box.append(h("h3", { text: "Re-assessment" }), h("p", { text: words(f.reassessment.status) + (f.reassessment.prior_finding_id ? " (was " + f.reassessment.prior_finding_id + ")" : "") + (f.reassessment.note ? ": " + f.reassessment.note : "") }));
  }
  return box;
}

function findingList(P, list) {
  const wrap = h("div", { class: "flist" });
  for (const f of list) {
    let box = null;
    const row = h("button", { class: "frow", type: "button", "data-fid": f.id, "aria-expanded": "false" },
      h("div", { class: "rank num", text: f.rank }), h("div", { class: "fid", text: f.id }), h("div", {}, sevPill(f)),
      h("div", { class: "title", text: f.title }), h("div", { class: "disp", text: words(f.disposition) }),
      h("div", { class: "conf num", text: conf(f.confidence) }));
    row.addEventListener("click", () => {
      if (box) { box.remove(); box = null; row.classList.remove("open"); row.setAttribute("aria-expanded", "false"); return; }
      box = expanded(P, f); row.after(box); row.classList.add("open"); row.setAttribute("aria-expanded", "true");
    });
    wrap.append(row);
  }
  return wrap;
}

function openFinding(fid) {
  const row = document.querySelector('.frow[data-fid="' + fid + '"]');
  if (!row) return;
  if (row.getAttribute("aria-expanded") !== "true") row.click();
  row.scrollIntoView({ block: "center" });
}

function idsNotIn(ids, text) {
  const missing = (ids || []).filter((id) => !String(text || "").includes(id));
  return missing.length ? h("b", { style: "font-weight:500", text: missing.join(", ") + " " }) : null;
}

function reviewBody(P) {
  const R = P.report, D = P.derived, v = R.verdict || {};
  const box = h("div", {});
  const vline = h("div", { class: "verdict" }, h("span", { class: "label", text: sentence(v.label) }),
    h("span", { class: "conf num", text: "confidence " + conf(v.confidence) + (D.verdict_band ? ", " + D.verdict_band : "") }));
  if (D.previous_verdict) vline.append(h("span", { class: "prev num", text: "previous version (" + D.previous_verdict.run_id + "): " + words(D.previous_verdict.label) + " · " + conf(D.previous_verdict.confidence) }));
  box.append(vline);
  const c = D.counts;
  const cs = h("div", { class: "counts num" });
  for (const [n, label] of [[c.findings, "findings"], [c.critical, "critical"], [c.high, "high"], [c.medium, "medium"], [c.low, "low"], [c.strengths, "strengths"], [c.sound_areas, "areas checked, no issue"], [c.unresolved, "unresolved"], [c.limitations, "limitations"]]) {
    cs.append(h("span", {}, h("b", { text: n }), " " + label));
  }
  box.append(cs, h("p", { class: "rationale small", text: v.rationale || "" }));
  if ((v.conditions || []).length) {
    box.append(h("h3", { text: "Conditions" }), h("ul", { class: "plain small" }, v.conditions.map((x) => h("li", {}, x.text + ((x.finding_ids || []).length ? " (" + x.finding_ids.join(", ") + ")" : "")))));
  }
  if (v.what_would_change_it) box.append(h("p", { class: "small muted", text: "What would change it: " + v.what_would_change_it }));
  if ((v.per_objective || []).length) {
    box.append(h("table", { class: "grid obj", style: "margin:16px 0 24px" },
      h("thead", {}, h("tr", {}, h("th", { text: "Objective" }), h("th", { text: "Verdict" }), h("th", { text: "Findings" }))),
      h("tbody", {}, v.per_objective.map((o) => h("tr", {}, h("td", { text: o.objective_ref }), h("td", { text: words(o.label) }), h("td", { class: "ids", text: (o.finding_ids || []).join(", ") || "–" }))))));
  }
  const all = [...(R.findings || [])].sort((a, b) => a.rank - b.rank);
  const issues = all.filter((f) => f.kind !== "strength"), strengths = all.filter((f) => f.kind === "strength");
  box.append(h("div", { class: "sec" }, h("h2", {}, "Findings ", h("span", { class: "n num", text: issues.length + ", ordered by rank" })), findingList(P, issues)));
  if (strengths.length) box.append(h("div", { class: "sec" }, h("h2", {}, "Strengths ", h("span", { class: "n num", text: String(strengths.length) })), findingList(P, strengths)));
  if ((R.sound_areas || []).length) {
    box.append(h("div", { class: "sec" }, h("h2", {}, "Checked, no issue ", h("span", { class: "n num", text: String(R.sound_areas.length) })),
      h("ul", { class: "plain small" }, R.sound_areas.map((s) => h("li", {}, h("b", { style: "font-weight:500", text: s.id }), " " + (s.section_refs || []).map((x) => "§" + x).join(", ") + " · " + s.why_sound)))));
  }
  box.append(h("div", { class: "sec two" },
    h("div", {}, h("h2", {}, "Unresolved issues ", h("span", { class: "n num", text: String((R.unresolved || []).length) })),
      h("ul", { class: "plain small" }, (R.unresolved || []).map((u) => h("li", {}, idsNotIn(u.finding_ids, u.text), u.text + (u.next_step ? " · " + u.next_step.owner + ": " + u.next_step.action : ""))))),
    h("div", {}, h("h2", {}, "Evidence limitations ", h("span", { class: "n num", text: String((R.limitations || []).length) })),
      h("ul", { class: "plain small" }, (R.limitations || []).map((l) => h("li", {}, idsNotIn(l.degradation_ids, l.text), l.text))))));
  return box;
}

function deltaBody(P) {
  const byId = new Map((P.report.findings || []).map((f) => [f.id, f]));
  const box = h("div", {});
  if (P.derived.previous_verdict) box.append(h("p", { class: "small muted", text: "Previous version (" + P.derived.previous_verdict.run_id + "): " + words(P.derived.previous_verdict.label) + " · " + conf(P.derived.previous_verdict.confidence) + "; this version: " + words(P.report.verdict.label) + " · " + conf(P.report.verdict.confidence) }));
  for (const g of P.derived.delta) {
    const list = g.finding_ids.map((id) => byId.get(id)).filter(Boolean);
    box.append(h("div", { class: "sec" }, h("h2", {}, g.heading + " ", h("span", { class: "n num", text: String(list.length) })), findingList(P, list)));
  }
  return box;
}

async function coverageBody(runId) {
  const cm = await api("/runs/" + encodeURIComponent(runId) + "/coverage");
  const box = h("div", {}, h("h2", { text: "Coverage: criteria by section" }));
  const head = h("tr", {}, h("th", { text: "Section" }), cm.criteria.map((c) => h("th", { class: "mono", text: c })));
  const body = h("tbody", {}, cm.rows.map((r) => h("tr", {}, h("td", {}, h("b", { style: "font-weight:500", text: r.section }), " " + (r.heading || "")), cm.criteria.map((c) => h("td", { class: "mono", text: (r.cells || {})[c] || "" })))));
  box.append(h("table", { class: "grid", style: "margin-top:8px" }, h("thead", {}, head), body));
  box.append(h("h3", { text: "Outcome per criterion" }), h("ul", { class: "plain small" }, cm.criteria.map((c) => h("li", {}, h("span", { class: "mono", text: c }), " " + words(cm.outcomes[c]) + ((cm.criterion_findings[c] || []).length ? ": " + cm.criterion_findings[c].join(", ") : "") + (cm.notes[c] ? " · " + cm.notes[c] : "")))));
  return box;
}

function evidenceBody(P) {
  const led = P.report.evidence_ledger || [];
  return h("div", {}, h("h2", {}, "Evidence register ", h("span", { class: "n num muted", style: "font-weight:400", text: String(led.length) })),
    h("table", { class: "grid", style: "margin-top:8px" }, h("thead", {}, h("tr", {}, h("th", { text: "ID" }), h("th", { text: "Source" }), h("th", { text: "Citation" }), h("th", { text: "Excerpt" }))),
      h("tbody", {}, led.map((e) => h("tr", {}, h("td", { text: e.evidence_id }), h("td", { text: words(e.source_type) + (e.authority ? " (" + e.authority + ")" : "") }),
        h("td", { text: e.url_or_citation }), h("td", { text: (e.excerpt || "") + ((e.derived_from || []).length ? " (derived from " + e.derived_from.join(", ") + ")" : "") }))))));
}

async function showReview(info, tab) {
  closeStream();
  const P = await api("/runs/" + encodeURIComponent(info.run_id) + "/report");
  const R = P.report;
  const doc = (R.metadata.documents || []).find((d) => d.role === "under_review") || (R.metadata.documents || [])[0] || {};
  const tabs = [{ key: "review", label: "Review" }];
  if (P.derived.delta) tabs.push({ key: "delta", label: "Delta" });
  tabs.push({ key: "coverage", label: "Coverage" }, { key: "evidence", label: "Evidence" });
  if (info.has_events) tabs.push({ key: "log", label: "Run log" });
  const current = tabs.some((t) => t.key === tab) ? tab : "review";
  const tabList = tabs.map((t) => ({ label: t.label, on: t.key === current, go: () => go(info.run_id, t.key) }));
  if (current === "log") { showRun(info, tabList); return; }
  const s = P.summary;
  const metaParts = [s.outcome ? words(s.outcome) : null, s.wall_s !== null ? dur(s.wall_s) : null, s.cost_usd !== null ? money(s.cost_usd, s.cost_lower_bound) : null, s.commit ? String(s.commit).slice(0, 7) : null];
  if (s.replayed) metaParts.push(h("span", { class: "pill", text: "replayed evidence" }));
  topBar({ doc: info.run_id + " · " + [doc.title, doc.page_count !== undefined ? doc.page_count + " pages" : null].filter(Boolean).join(", "), tabs: tabList, meta: joinMeta(metaParts) });
  const app = clear($("app"));
  app.append(tpl("tpl-review"));
  const main = $("review");
  if (current === "review") main.append(reviewBody(P));
  else if (current === "delta") main.append(deltaBody(P));
  else if (current === "coverage") main.append(await coverageBody(info.run_id));
  else if (current === "evidence") main.append(evidenceBody(P));
  await setupChat(info);
}

// ------------------------------------------------------------------ the chat: a reading aid, not the review

function budgetLine(b) {
  return b.calls_used + " of " + b.max_calls + " calls used · " + money(b.cost_usd) + " of " + money(b.max_cost_usd) + (b.calls_with_unknown_cost ? " (" + b.calls_with_unknown_cost + " call(s) with unknown cost)" : "") + " · logged to " + b.log + " · outside the evaluated agent and its manifest";
}

function citeEl(id) {
  if (/^FND-\d+$/.test(id)) return h("a", { class: "cite", href: "#", text: id, onclick: (e) => { e.preventDefault(); openFinding(id); } });
  return h("span", { class: "cite", text: id });
}

function turnEls(t) {
  const out = [h("div", { class: "turn" }, h("div", { class: "who", text: "You · " + (t.at || "").slice(11, 16) + " UTC" }), h("div", { class: "q", text: t.question }))];
  const a = h("div", { class: "a" });
  if (t.rendered_as === "answer") {
    a.append(h("p", { class: "answer", text: t.answer }), h("div", { class: "cites" }, (t.citations || []).map(citeEl)));
    a.append(h("div", { class: "foot", text: (t.dropped || []).length ? (t.dropped.length + " citation(s) did not resolve in this run and were dropped: " + t.dropped.join(", ") + ".") : "Every citation resolves in this run." }));
  } else if (t.rendered_as === "unsupported") {
    a.append(h("p", { class: "unsupported", text: "The review does not answer this." }));
    const why = [t.unsupported_reason, (t.dropped || []).length ? "dropped, not in this run: " + t.dropped.join(", ") : null].filter(Boolean).join("; ");
    if (why) a.append(h("div", { class: "foot", text: why.charAt(0).toUpperCase() + why.slice(1) + "." }));
  } else {
    a.append(h("p", { class: "error", text: "The call failed: " + (t.error || "unknown error") + "." }));
  }
  const cost = typeof t.cost_usd === "number" ? ", " + money(t.cost_usd) : ", cost unknown";
  out.push(h("div", { class: "turn" }, h("div", { class: "who", text: "Review assistant · 1 model call, " + (typeof t.duration_s === "number" ? t.duration_s.toFixed(1) + " s" : "–") + cost }), a));
  return out;
}

async function setupChat(info) {
  const runId = info.run_id;
  const data = await api("/runs/" + encodeURIComponent(runId) + "/chat");
  const turns = $("chat-turns");
  for (const t of data.turns) turns.append(...turnEls(t));
  $("chat-model").textContent = data.budget.model + " · effort " + data.budget.effort;
  const input = $("chat-input"), send = $("chat-send"), err = $("chat-error");
  const setBudget = (b, running, hasReport) => {
    $("chat-budget").textContent = budgetLine(b);
    const off = running ? "The chat is off while the run is in progress." : (!hasReport ? "This run has no report.json, so there is nothing to ask about." : (b.stopped ? "The chat cap for this run is reached." : null));
    input.disabled = !!off; send.disabled = !!off;
    err.hidden = !off; err.textContent = off || "";
  };
  setBudget(data.budget, data.running, data.has_report);
  const submit = async () => {
    const q = input.value.trim();
    if (!q || send.disabled) return;
    send.disabled = true; input.disabled = true; err.hidden = true;
    try {
      const r = await api("/runs/" + encodeURIComponent(runId) + "/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      turns.append(...turnEls(r.turn));
      input.value = "";
      setBudget(r.budget, false, true);
    } catch (e) {
      err.hidden = false; err.textContent = e.message; send.disabled = false; input.disabled = false;
    }
  };
  $("chat-form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); } });
}

// ------------------------------------------------------------------ routing

function go(runId, tab) {
  const u = runId ? "/?run=" + encodeURIComponent(runId) + (tab ? "&tab=" + tab : "") : "/";
  history.pushState(null, "", u);
  route();
}

async function route() {
  const q = new URLSearchParams(location.search);
  const runId = q.get("run");
  S.runId = runId;
  try {
    if (!S.meta) S.meta = await api("/meta");
    if (!runId) { await showDrop(); return; }
    const info = await api("/runs/" + encodeURIComponent(runId));
    if (info.status === "running" || !info.has_report) showRun(info, null);
    else await showReview(info, q.get("tab"));
  } catch (e) {
    closeStream();
    topBar({ doc: runId || "no run open" });
    clear($("app")).append(h("div", { style: "padding:48px 64px" }, h("p", { class: "error", text: e.message }), h("a", { href: "/", text: "Back to the run list" })));
  }
}

// The run model and its reducer, reachable by tests that feed a recorded stream through the page.
window.SIT = { applyEvent, newRunModel, state: S };
window.addEventListener("popstate", route);
route();
