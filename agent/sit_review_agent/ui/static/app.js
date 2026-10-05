// SIT review page (dra ui), v2: the DBSearch idiom with a rail (docs/design/ui_restyle.md). Vanilla JS, no
// framework, nothing loaded from the network but this server.
// Rules this file keeps (docs/design/ui_design.md, tests/test_ui_honesty.py):
// - every number shown comes from the run directory (via the server's JSON) or the event stream;
// - the run view draws from each event's `event` and `fields` only and never parses `message`;
// - review text is inserted as textContent, exactly as report.json has it (no rewording);
// - no animation; event times are the record's own run clock; the head clock and the axis cursor add only the wall
//   seconds since the last event arrived (one tick a second, Date.now, nowhere else), never an estimate of completion;
//   the stage limits and the deadline are the run_started record's;
// - the rail's running entry is the open run's stream state; the tools dots are GET /tools; no probe on load.
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
  for (const kid of kids.flat(Infinity)) {
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
// hh:mm of an ISO-8601 UTC stamp, as the server recorded it (no browser clock, no time zone of the viewer).
function hhmm(iso) { return typeof iso === "string" && iso.length >= 16 ? iso.slice(11, 16) + " UTC" : "–"; }

async function api(url, opts) {
  const res = await fetch(url, opts);
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (!res.ok) throw new Error((body && body.error) || ("HTTP " + res.status));
  return body;
}

const S = { meta: null, runId: null, es: null, model: null, info: null, page: "review", runs: [], tools: null, profile: null, samples: null,
  // The Stop control's state across repaints (every event repaints the head): armed by a first click, sent by the second.
  stop: null,
  // The browser's clock when the last event arrived, and the one-second tick that adds the seconds since to the head clock.
  lastAt: null, tick: null,
  // The open run's progress.log tail (GET /runs/<id>/log): the lines kept, the byte offset to read from next.
  log: null,
  // The Run log's stage panel (one stage at a time), the findings funnel and the legend, each as the server read
  // them from the run directory (GET /runs/<id>/stage/<name>, /funnel, /glossary); stale: a stage ended since.
  panel: null, funnel: null, glossary: null, stale: false };
const PAGES = ["review", "runs", "replay", "tools", "settings", "developer"];
const RAIL_KEY = "navrail-collapsed";

// ------------------------------------------------------------------ the rail and the topbar

function railActive(page) {
  for (const a of document.querySelectorAll(".navrail-item")) a.classList.toggle("active", a.dataset.page === page);
}

function runMetaText(r) {
  const m = S.model;
  if (r.status === "running") {
    // The open run's entry is its stream: the stage, the run clock and the open shards come from the model the
    // page reduced from progress.jsonl, never from a browser clock.
    if (m && r.run_id === S.runId) {
      const inFlight = [...m.tracks.values()].filter((t) => t.status === "running" || t.status === "replayed");
      const shards = inFlight.filter((t) => t.key.startsWith("assess ")).length;
      const stage = inFlight.length ? (shards ? "assess" : inFlight[inFlight.length - 1].key) : (S.runs.find((x) => x.run_id === r.run_id) || r).stage;
      const open = shards ? intl(shards) + " shard" + (shards === 1 ? "" : "s") + " open" : (inFlight.length ? intl(inFlight.length) + " call" + (inFlight.length === 1 ? "" : "s") + " open" : null);
      return [h("span", { class: "live", text: stage || "starting" }), " · " + clock(m.lastT) + (m.deadline ? " of " + clock(m.deadline) : ""), open ? " · " + open : ""];
    }
    const open = r.open_calls ? " · " + intl(r.open_calls) + " call" + (r.open_calls === 1 ? "" : "s") + " open" : "";
    return [h("span", { class: "live", text: r.stage || "starting" }), " · " + clock(r.run_s) + open];
  }
  if (r.verdict) return [words(r.verdict) + " · " + conf(r.confidence) + " · " + dur(r.wall_s)];
  return [(r.status === "ended" ? "no report" : "no report yet") + (typeof r.wall_s === "number" ? " · " + dur(r.wall_s) : "")];
}

function renderRailRuns() {
  const box = $("rail-runs"), kept = box.scrollTop;  // a re-render keeps a hand scroll of the list
  clear(box);
  const running = S.runs.filter((r) => r.status === "running").length;
  $("rail-runs-note").textContent = running ? intl(running) + " running" : "none running";
  if (!S.runs.length) box.append(h("div", { class: "rail-empty", text: "no run directory yet" }));
  for (const r of S.runs) {
    const dot = r.status === "running" ? "live" : (r.verdict ? "done" : "ended");
    box.append(h("a", { class: "rail-run" + (r.run_id === S.runId ? " active" : ""), href: "/?run=" + encodeURIComponent(r.run_id), "data-run": r.run_id, title: r.document || r.run_id,
      onclick: (e) => { e.preventDefault(); go(r.run_id); } },
      h("span", { class: "dot " + dot }), h("span", { class: "title", text: r.run_id }), h("span", { class: "meta num" }, runMetaText(r))));
  }
  // the open run's row is always in view: the list keeps one row's height (app.css) and scrolls itself, and
  // only itself (scrollIntoView would also scroll the rail's slot away from the Logs panel), to that row
  const open = box.querySelector(".rail-run.active");
  const top = open ? open.offsetTop - box.offsetTop : kept;
  box.scrollTop = open ? Math.min(Math.max(kept, top + open.offsetHeight - box.clientHeight), top) : kept;
}

function toolMeta(t, noTools) {
  if (!t.enabled) return "off in config/tools.yaml";
  if (noTools) return "this run: --no-tools";
  if (t.warm) return "warm at " + hhmm(t.at) + (typeof t.tools === "number" ? " · " + intl(t.tools) + " tool" + (t.tools === 1 ? "" : "s") : "") + (t.calls_failed ? " · " + intl(t.calls_failed) + " call" + (t.calls_failed === 1 ? "" : "s") + " failed" : "");
  if (t.warm === false) return t.status === "failed" ? "warm-up failed in the last run" : "no tools/list answer in the last run";
  return "no warm-up recorded";
}

function renderRailTools() {
  const box = clear($("rail-tools"));
  const T = S.tools;
  if (!T) { $("rail-tools-note").textContent = ""; return; }
  const noTools = !!(S.info && S.info.run_id === S.runId && S.info.no_tools);
  const warm = T.servers.filter((t) => t.warm).length;
  $("rail-tools-note").textContent = noTools ? "not in use" : (T.from_run ? intl(warm) + " of " + intl(T.servers.length) + " warm" : "no warm-up recorded");
  for (const t of T.servers) {
    box.append(h("div", { class: "rail-tool", "data-server": t.name, title: T.from_run ? "from run " + T.from_run : "" },
      h("span", { class: "dot " + (t.warm && !noTools ? "warm" : "off") }), h("span", { class: "name", text: t.name }), h("span", { class: "meta", text: toolMeta(t, noTools) })));
  }
  const chip = clear($("top-tools"));
  chip.append("tools: ", h("b", { text: intl(warm) + " of " + intl(T.servers.length) }), " servers warm");
}

function renderTopbar() {
  const meta = S.meta;
  const pill = $("top-edition");
  pill.classList.toggle("off", meta.backend !== "claude_code");
  $("top-edition-text").textContent = meta.backend === "claude_code" ? "local · your subscription · no API key" : (meta.backend ? "local · " + words(meta.backend) : "local");
  const sel = clear($("top-profile"));
  for (const p of meta.profiles) sel.append(h("option", { value: p.name, text: p.label + " · " + dur(p.deadline_s) }));
  if (S.profile === null) S.profile = meta.profiles.some((p) => p.name === "demo") ? "demo" : (meta.profiles[0] ? meta.profiles[0].name : "");
  sel.value = S.profile;
  sel.addEventListener("change", () => { S.profile = sel.value; const f = $("profile-select"); if (f) { f.value = S.profile; f.dispatchEvent(new Event("change")); } });
}

function setupRail() {
  for (const a of document.querySelectorAll(".navrail-item")) a.addEventListener("click", (e) => { e.preventDefault(); goPage(a.dataset.page); });
  $("top-tools").addEventListener("click", (e) => { e.preventDefault(); goPage("tools"); });
  document.querySelector(".navrail-brand").addEventListener("click", (e) => { e.preventDefault(); goPage("review"); });
  const grid = $("app-grid"), toggle = $("navrail-toggle");
  let collapsed = false;
  try { collapsed = localStorage.getItem(RAIL_KEY) === "1"; } catch (e) { collapsed = false; }
  const apply = () => { grid.classList.toggle("rail-collapsed", collapsed); toggle.setAttribute("aria-label", collapsed ? "Expand the rail" : "Collapse the rail"); toggle.querySelector(".label").textContent = collapsed ? "Expand" : "Collapse"; };
  toggle.addEventListener("click", () => { collapsed = !collapsed; try { localStorage.setItem(RAIL_KEY, collapsed ? "1" : "0"); } catch (e) { /* storage off: the rail still toggles */ } apply(); });
  apply();
}

// The Logs panel: the open run's progress.log, read from the server's route only (never a file the page guesses at),
// first the last lines, then what was appended since the last read; the tick and the stream's end re-read it.
function openLog(runId) {
  S.log = runId ? { runId, lines: [], offset: 0, exists: null, skipped: 0, keep: null, busy: false, error: null } : null;
  renderRailLog();
  if (runId) pollLog();
}

async function pollLog() {
  const L = S.log;
  if (!L || L.busy) return;
  L.busy = true;
  try {
    const r = await api("/runs/" + encodeURIComponent(L.runId) + "/log" + (L.offset ? "?after=" + L.offset : ""));
    if (S.log !== L) return;
    if (r.offset < L.offset) L.lines = [];                   // the file was replaced: the server started over
    L.lines.push(...r.lines); L.offset = r.offset; L.exists = r.exists; L.keep = r.tail; L.skipped += r.skipped; L.error = null;
    if (L.lines.length > L.keep) { L.skipped += L.lines.length - L.keep; L.lines.splice(0, L.lines.length - L.keep); }
  } catch (e) { if (S.log === L) L.error = e.message; }
  L.busy = false;
  renderRailLog();
}

function renderRailLog() {
  const box = clear($("rail-log")), note = $("rail-log-note");
  const L = S.log;
  if (!L) { note.textContent = ""; box.append(h("div", { class: "rail-empty", text: "open a run" })); return; }
  if (L.error) { note.textContent = "not read"; box.append(h("div", { class: "rail-empty", text: L.error })); return; }
  if (L.exists === false) { note.textContent = "no progress.log yet"; box.append(h("div", { class: "rail-empty", text: L.runId + "/progress.log is not written yet" })); return; }
  note.textContent = L.exists === null ? "" : "last " + intl(L.lines.length) + (L.skipped ? " of " + intl(L.lines.length + L.skipped) : "") + " lines";
  for (const line of L.lines) box.append(h("div", { class: "rail-logline" + (line.includes("| WARN ") ? " warn" : ""), text: line, title: line }));
  box.scrollTop = box.scrollHeight;
}

async function refreshRuns() { const r = await api("/runs"); S.runs = r.runs; renderRailRuns(); }
async function refreshTools() { S.tools = await api("/tools"); renderRailTools(); }

// A pasted link: https only (the server checks it again under config/url_policy.yaml), and the name the
// server saves it under (ui/fetch.py file_name: the last path segment, made safe, ending in .pdf).
function httpsLink(v) { try { return new URL(v).protocol === "https:" && !/\s/.test(v); } catch (e) { return false; } }
function linkName(v) {
  let seg = "";
  try { seg = decodeURIComponent(new URL(v).pathname.split("/").pop() || ""); } catch (e) { seg = ""; }
  const n = seg.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "") || "document";
  return /\.pdf$/i.test(n) ? n : n + ".pdf";
}

function surfaceHead(title, sub, right) {
  return h("div", { class: "surface-head" }, h("div", {}, h("div", { class: "surface-title", text: title }), sub ? h("div", { class: "surface-sub num" }, sub) : null), right || null);
}

// ------------------------------------------------------------------ the Review page: the drop screen

function toolsHelp(meta) {
  const enabled = meta.tools.filter((t) => t.enabled).map((t) => t.name);
  if (!enabled.length) return "No tool server is enabled in config/tools.yaml.";
  let s = "Enabled in config/tools.yaml: " + enabled.join(", ") + ".";
  const T = S.tools;
  if (T && T.from_run) {
    const warm = T.servers.filter((t) => t.enabled && t.warm);
    if (warm.length === enabled.length && warm.every((t) => t.at === warm[0].at)) s += " " + (warm.length === 1 ? "It" : (warm.length === 2 ? "Both" : "All")) + " answered the last recorded warm-up at " + hhmm(warm[0].at) + " (run " + T.from_run + ").";
    else s += " Last recorded warm-up (run " + T.from_run + "): " + T.servers.filter((t) => t.enabled).map((t) => t.name + " " + (t.warm ? "at " + hhmm(t.at) : "no answer")).join(", ") + ".";
  } else s += " No warm-up is recorded in a run directory yet.";
  return s;
}

async function showDrop() {
  closeStream();
  S.info = null;
  const meta = S.meta;
  const app = clear($("app"));
  app.className = "surface";
  app.append(tpl("tpl-drop"));
  const sel = $("profile-select");
  for (const p of meta.profiles) sel.append(h("option", { value: p.name, text: p.label + " · " + dur(p.deadline_s) }));
  sel.value = S.profile;
  $("tools-help").textContent = toolsHelp(meta);
  let doc = null;
  $("link-max").textContent = meta.link_max_mb;
  const link = () => { const v = $("doc-link").value.trim(); return httpsLink(v) ? v : null; };
  // The deadline field is in minutes; the command and the server take whole seconds within GET /meta deadline_bounds_s.
  const dl = $("deadline-min");
  const [dmin, dmax] = meta.deadline_bounds_s;
  dl.min = String(dmin / 60); dl.max = String(dmax / 60);
  const profileOf = () => meta.profiles.find((x) => x.name === sel.value) || null;
  const resetDeadline = () => { const p = profileOf(); dl.value = p ? String(p.deadline_s / 60) : ""; };
  // Whole seconds, null for an empty field (the profile's own deadline), NaN for a value outside the bounds.
  const deadlineS = () => { if (dl.value.trim() === "") return null; const sec = Math.round(Number(dl.value) * 60); return Number.isFinite(sec) && sec >= dmin && sec <= dmax ? sec : NaN; };
  // --deadline only when the field differs from the profile's own deadline (the server drops it otherwise too).
  const deadlineArg = () => { const p = profileOf(), d = deadlineS(); return d !== null && !Number.isNaN(d) && (!p || d !== p.deadline_s) ? d : null; };
  const keyMissing = () => !$("no-tools").checked && S.tools && S.tools.key_missing ? S.tools.key_missing : null;
  let limitsAsk = 0;
  const showLimits = async () => {
    const p = profileOf(), d = deadlineS(), mine = ++limitsAsk;
    const help = $("profile-help"), dhelp = $("deadline-help");
    const say = (lim, dd) => "Stage 1 ends by " + clock(lim.stage_1_end) + ", refine by " + clock(lim.refine_end) + ", verdict by " + clock(lim.verdict_end) + ", deadline " + clock(dd) + ".";
    if (Number.isNaN(d)) { help.textContent = ""; dhelp.className = "help error"; dhelp.textContent = "Give a number of minutes from " + intl(dmin / 60) + " to " + intl(dmax / 60) + "."; return; }
    dhelp.className = "help";
    if (!p) { help.textContent = ""; dhelp.textContent = ""; return; }
    // At the profile's own deadline (the field empty or equal to it) the run gets no --deadline, so the server is asked
    // without one and applies no scaling; it still states research's end and the warnings, at every deadline.
    const own = d === null || d === p.deadline_s;
    dhelp.textContent = d === null ? "Empty: the " + p.label + " profile's own deadline." : (own ? "The " + p.label + " profile's own deadline." : "Passed as --deadline " + d + "; the profile's own is " + dur(p.deadline_s) + ".");
    help.textContent = own ? say(p.stage_limits_s, p.deadline_s) : "Reading the limits for " + clock(d) + " from the server.";
    try {
      const L = await api("/limits?profile=" + encodeURIComponent(p.name) + (own ? "" : "&deadline_s=" + d));
      if (mine !== limitsAsk) return;
      const parts = [say(L.stage_limits_s, L.deadline_s)];
      if (L.scaled) parts.push("Scaled from the profile's, with the reserves (" + intl(L.report_reserve_s) + " s for verify and verdict, " + intl(L.refine_reserve_s) + " s for refine); the run says so first.");
      if (typeof L.research_end_s === "number") parts.push("Research ends by " + clock(L.research_end_s) + ".");
      for (const w of L.warnings) parts.push(sentence(w) + ".");
      help.textContent = parts.join(" ");
    } catch (err) { if (mine === limitsAsk) help.textContent = (own ? say(p.stage_limits_s, p.deadline_s) + " " : "") + "The limits for this deadline could not be read: " + err.message; }
  };
  const refresh = () => {
    const prev = $("prev-input").files[0];
    const rid = $("run-id").value.trim() || "<new run>";
    const source = doc ? doc.name : (link() ? linkName(link()) : null);
    const parts = ["dra", "review", source ? "runs/" + rid + "/ui/input/" + source : "<document>"];
    if (sel.value) parts.push("--profile", sel.value);
    if (deadlineArg() !== null) parts.push("--deadline", String(deadlineArg()));
    if (prev) parts.push("--v1", "runs/" + rid + "/ui/input/previous/" + prev.name);
    if ($("no-tools").checked) parts.push("--no-tools");
    parts.push("--run-id", rid);
    $("cmd-preview").textContent = parts.join(" ");
    const missing = keyMissing();
    const warn = $("key-warn");
    warn.hidden = !missing;
    clear(warn);
    if (missing) warn.append(missing + " ", h("span", { class: "fix" }, "Tick Document only, or stop this server and start it again from a shell that ran ", h("span", { class: "mono", text: "export " + S.tools.auth_env + "=<key>" }), "."));
    $("start-btn").disabled = !(doc || link()) || !meta.can_launch || !!missing || Number.isNaN(deadlineS());
    $("link-error").hidden = !$("doc-link").value.trim() || !!link();
    const c = $("doc-chosen");
    c.hidden = !doc && !link();
    c.textContent = doc ? doc.name : (link() ? "Link: " + link() + " (fetched when the review starts)" : "");
    for (const chip of document.querySelectorAll(".starter")) chip.setAttribute("aria-pressed", String(!!doc && chip.dataset.file === doc.name));
  };
  const choose = (f) => { doc = f || null; if (doc) $("doc-link").value = ""; refresh(); };
  $("doc-link").addEventListener("input", () => { if ($("doc-link").value.trim()) { doc = null; $("doc-input").value = ""; } refresh(); });
  $("doc-input").addEventListener("change", (e) => choose(e.target.files[0]));
  $("prev-input").addEventListener("change", () => { const f = $("prev-input").files[0]; $("prev-chosen").textContent = f ? f.name : "No file chosen"; $("prev-chosen").classList.toggle("muted", !f); refresh(); });
  sel.addEventListener("change", () => { S.profile = sel.value; $("top-profile").value = sel.value; resetDeadline(); showLimits(); refresh(); });
  dl.addEventListener("input", () => { showLimits(); refresh(); });
  $("no-tools").addEventListener("change", refresh);
  $("run-id").addEventListener("input", refresh);
  const dz = $("dropzone");
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault(); dz.classList.remove("over");
    if (e.dataTransfer.files.length) { choose(e.dataTransfer.files[0]); return; }
    const uri = (e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain") || "").split("\n")[0].trim();
    if (uri) { $("doc-link").value = uri; doc = null; refresh(); }
  });
  const startNote = $("start-note").textContent;
  if (!meta.can_launch) $("start-note").textContent = meta.launch_note;
  $("start-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!doc && !link()) return;
    const fd = new FormData();
    if (doc) fd.append("document", doc);
    else fd.append("document_url", link());
    const prev = $("prev-input").files[0];
    if (prev) fd.append("previous", prev);
    fd.append("profile", sel.value);
    if ($("run-id").value.trim()) fd.append("run_id", $("run-id").value.trim());
    if ($("no-tools").checked) fd.append("no_tools", "1");
    if (deadlineArg() !== null) fd.append("deadline_s", String(deadlineArg()));
    $("start-btn").disabled = true;
    $("start-error").hidden = true;
    if (!doc) $("start-note").textContent = "Fetching the PDF from the link, then starting the review.";
    try {
      const r = await api("/runs", { method: "POST", body: fd });
      go(r.run_id);
    } catch (err) {
      const box = $("start-error"); box.hidden = false; box.textContent = err.message;
      $("start-note").textContent = meta.can_launch ? startNote : meta.launch_note; refresh();
    }
  });
  resetDeadline();
  showLimits();
  refresh();
  // The sample documents of config/ui.yaml as chips: a chip fetches the file from this server and fills the form
  // with it (the same path as a drop); it never submits. The run starts only with the Start review button.
  if (!S.samples) S.samples = (await api("/documents")).items;
  const starters = $("starters");
  if (!starters) return;
  for (const item of S.samples) {
    starters.append(h("button", { class: "starter", type: "button", "data-file": item.file, "aria-pressed": "false", title: item.path, text: item.label, onclick: async (e) => {
      const chip = e.currentTarget;
      chip.disabled = true;
      try {
        const res = await fetch("/documents/" + encodeURIComponent(item.name));
        if (!res.ok) throw new Error("HTTP " + res.status);
        choose(new File([await res.blob()], item.file, { type: res.headers.get("content-type") || "" }));
      } catch (err) { const box = $("start-error"); box.hidden = false; box.textContent = "The sample document could not be read: " + err.message; }
      chip.disabled = false;
    } }));
  }
}

// ------------------------------------------------------------------ the Runs, Replay, Tools, Settings and Developer pages

function runsTable(rows, withStarted) {
  const head = h("tr", {}, h("th", { text: "Run" }), h("th", { text: "Document" }), h("th", { text: "Verdict" }), h("th", { class: "r", text: "Findings" }), h("th", { class: "r", text: "Wall" }), h("th", { class: "r", text: "Cost" }), withStarted ? h("th", { class: "r", text: "Started" }) : null);
  const body = h("tbody");
  for (const r of rows) {
    const verdict = r.status === "running" ? h("span", { class: "pill running", text: "running" })
      : (r.verdict ? words(r.verdict) + " · " + conf(r.confidence) : (r.status === "ended" ? "no report" : "–"));
    body.append(h("tr", { class: "link", onclick: () => go(r.run_id) },
      h("td", {}, h("a", { href: "/?run=" + encodeURIComponent(r.run_id), text: r.run_id, onclick: (e) => { e.preventDefault(); go(r.run_id); } }), r.replayed ? [" ", h("span", { class: "pill replayed", text: "replayed evidence" })] : null),
      h("td", { text: r.document || "–" }), h("td", { style: "white-space:nowrap" }, verdict),
      h("td", { class: "r", text: r.findings === null ? "–" : r.findings }),
      h("td", { class: "r", text: dur(r.wall_s) }), h("td", { class: "r", text: money(r.cost_usd, r.cost_lower_bound) }),
      withStarted ? h("td", { class: "r", text: hhmm(r.started_at) }) : null));
  }
  return h("table", { class: "grid num", id: "runs-table", style: "margin-top:18px" }, h("thead", {}, head), body);
}

function showRuns() {
  const app = clear($("app"));
  app.className = "surface wide";
  const running = S.runs.filter((r) => r.status === "running").length;
  app.append(surfaceHead("Runs", [h("b", { text: intl(S.runs.length) + " run director" + (S.runs.length === 1 ? "y" : "ies") }), " in " + S.meta.runs_dir_name + "/ · " + (running ? intl(running) + " running" : "none running") + " · opening one reads its files, nothing is re-run"]));
  if (!S.runs.length) app.append(h("p", { class: "page-intro", id: "runs-note", text: "No run directory yet. A run started here, or with dra review in a terminal, appears in this list." }));
  else app.append(runsTable(S.runs, true));
}

function showReplay() {
  const app = clear($("app"));
  app.className = "surface wide";
  app.append(surfaceHead("Replay", ["a recorded run served again from its own directory: no model call, no tool call"]));
  app.append(h("p", { class: "page-intro" }, h("b", { text: "dra replay" }), " serves a finished run from its recorded model calls (llm.jsonl) and tool calls; the page then draws the same timeline and the same review, stamped ", h("span", { class: "pill replayed", text: "replayed evidence" }), " in the head. Nothing is re-run, and a replay is never shown as live: a track in flight reads \"replayed\", never \"running\"."));
  const replayed = S.runs.filter((r) => r.replayed), sources = S.runs.filter((r) => !r.replayed && r.status === "finished");
  app.append(h("div", { class: "sec" }, h("h2", {}, "Replayed runs ", h("span", { class: "n num", text: String(replayed.length) })),
    replayed.length ? runsTable(replayed, true) : h("p", { class: "notice", style: "margin-top:8px", text: "No run directory in " + S.meta.runs_dir_name + "/ was served by dra replay." })));
  app.append(h("div", { class: "sec" }, h("h2", {}, "Finished runs that can be replayed ", h("span", { class: "n num", text: String(sources.length) })),
    h("div", { class: "notice", style: "margin-top:4px", text: "Each line is the command to type; the replay writes a new run directory and this page lists it above." }),
    h("div", { class: "tool-list", style: "margin-top:8px" }, sources.map((r) => h("div", { class: "tool-row", style: "grid-template-columns:220px minmax(0,1fr)" }, h("div", { class: "name", text: r.run_id }), h("div", { class: "cmd", style: "margin:0", text: "dra replay " + S.meta.runs_dir_name + "/" + r.run_id }))))));
}

function toolRow(t, T) {
  const state = !t.enabled ? "off" : (t.warm ? "warm" : (t.warm === false ? "no answer" : "unknown"));
  const detail = [];
  if (!t.enabled) detail.push("off in config/tools.yaml; not offered to the model");
  else if (t.warm) { detail.push(h("b", { text: "answered tools/list at " + hhmm(t.at) }), " in run " + T.from_run + (typeof t.tools === "number" ? ": " + intl(t.tools) + " tool" + (t.tools === 1 ? "" : "s") : "")); }
  else if (t.warm === false) detail.push("enabled, but run " + T.from_run + " recorded no tools/list answer from it" + (t.status ? " (warm-up " + words(t.status) + ")" : ""));
  else detail.push("enabled; no run directory has recorded a warm-up yet");
  if (t.calls_ok || t.calls_failed) detail.push(" · calls in that run: " + intl(t.calls_ok) + " ok, " + intl(t.calls_failed) + " failed");
  return h("div", { class: "tool-row", "data-server": t.name }, h("span", { class: "dot" + (t.warm ? " warm" : "") }), h("div", { class: "name", text: t.name }), h("div", { class: "state", text: state }), h("div", { class: "detail" }, detail));
}

function probeRows(p) {
  const box = h("div", { class: "sec", id: "probe-result" }, h("h2", {}, "Probe at " + hhmm(p.at), h("span", { class: "n", text: p.auth_failed ? "the servers refused the key" : "initialize and tools/list on every enabled server" })));
  const list = h("div", { class: "tool-list" });
  for (const s of p.servers) list.append(h("div", { class: "tool-row" }, h("span", { class: "dot" + (s.warm ? " warm" : "") }), h("div", { class: "name", text: s.name }), h("div", { class: "state", text: s.health }), h("div", { class: "detail", text: s.warm ? intl(s.tools) + " tool" + (s.tools === 1 ? "" : "s") + " listed" : (s.error || "no answer") })));
  box.append(list);
  if ((p.lines || []).length) box.append(h("div", { class: "raw", text: p.lines.join("\n") }));
  return box;
}

async function showTools() {
  const app = clear($("app"));
  app.className = "surface wide";
  if (!S.tools) await refreshTools();
  const T = S.tools;
  const warm = T.servers.filter((t) => t.warm).length;
  app.append(surfaceHead("Tools", [h("b", { text: intl(warm) + " of " + intl(T.servers.length) + " servers warm" }), T.from_run ? " at the last recorded warm-up, run " + T.from_run : " · no run directory has recorded a warm-up"]));
  app.append(h("p", { class: "page-intro" }, h("b", { text: "What the dot means." }), " A warm dot says the server answered the agent's warm-up (initialize and tools/list) in the newest run directory that recorded one, at the time shown. It does not say the server is awake now: the servers scale to zero, so a live answer needs a live probe, which is the button below and never the page loading."));
  const list = h("div", { class: "tool-list", id: "tool-list", style: "margin-top:18px" });
  for (const t of T.servers) list.append(toolRow(t, T));
  app.append(list);
  const btn = h("button", { class: "btn", type: "button", id: "probe-btn", text: "Probe now" });
  const note = h("span", { class: "note", id: "probe-note", text: T.key_present ? "Runs the preflight warm-up on the enabled servers with the key from " + T.auth_env + " in the server's environment (a cold start can take over a minute); the result is shown here and kept until the server restarts." : T.auth_env + " is not set in the server's environment, so a probe would be refused: export it in the shell that starts dra ui." });
  const err = h("div", { class: "error", id: "probe-error", hidden: true });
  const result = h("div", { id: "probe-box" });
  if (T.probe) result.append(probeRows(T.probe));
  btn.addEventListener("click", async () => {
    btn.disabled = true; err.hidden = true; btn.textContent = "Probing…";
    try { const p = await api("/tools/probe", { method: "POST" }); clear(result).append(probeRows(p)); }
    catch (e) { err.hidden = false; err.textContent = e.message; }
    btn.disabled = false; btn.textContent = "Probe now";
  });
  app.append(h("div", { class: "probe" }, btn, note), err, result);
}

function showSettings() {
  const app = clear($("app"));
  app.className = "surface wide";
  const meta = S.meta;
  app.append(surfaceHead("Settings", ["the effective configuration this server read when it started, by file; the page changes nothing"]));
  app.append(h("p", { class: "page-intro", text: "Settings are files under config/. Edit a file and start the next review; a running review read its configuration when it started." }));
  const files = meta.config_files || [];
  const block = (name, body) => h("div", { class: "cfg" }, h("h2", {}, h("span", { class: "mono", text: name })), body);
  const kv = (pairs) => h("dl", { class: "kv wide" }, pairs.map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
  for (const name of files) {
    if (/\/agent\.yaml$/.test(name)) app.append(block(name, kv([["llm.backend", meta.backend || "–"], ["model", meta.model || "–"], ["run root", meta.runs_dir]])));
    else if (/\/profiles\//.test(name)) {
      const p = meta.profiles.find((x) => name.endsWith("/" + x.name + ".yaml"));
      app.append(block(name, p ? kv([["deadline", clock(p.deadline_s)], ["stage 1 ends by", clock(p.stage_limits_s.stage_1_end)], ["refine ends by", clock(p.stage_limits_s.refine_end)], ["verdict ends by", clock(p.stage_limits_s.verdict_end)], ["effort (assess)", p.effort || "–"]]) : h("div", { class: "notice", text: "overlay of agent.yaml and stop_rules.yaml" })));
    } else if (/\/tools\.yaml$/.test(name)) {
      app.append(block(name, kv([["servers", h("span", {}, meta.tools.map((t) => [h("span", { class: "pill " + (t.enabled ? "done" : "waiting"), text: t.name + (t.enabled ? "" : " (off)") }), " "]))], ["key", "read from " + meta.auth_env + " in the server's environment; never shown"]])));
    } else if (/\/ui\.yaml$/.test(name)) {
      app.append(block(name, kv([["ask the review", meta.chat.model + ", effort " + meta.chat.effort + ", at most " + intl(meta.chat.max_calls) + " asks or " + money(meta.chat.max_cost_usd) + " per run"], ["email", "SMTP settings for the Email action; the password comes from the environment"]])));
    } else if (/\/url_policy\.yaml$/.test(name)) {
      app.append(block(name, kv([["pasted link", "https only, public hosts, at most " + intl(meta.link_max_mb) + " MB"]])));
    } else if (/\/stop_rules\.yaml$/.test(name)) {
      const base = meta.profiles.find((x) => x.name === "");
      app.append(block(name, base ? kv([["deadline", clock(base.deadline_s)], ["stage 1 ends by", clock(base.stage_limits_s.stage_1_end)], ["refine ends by", clock(base.stage_limits_s.refine_end)], ["verdict ends by", clock(base.stage_limits_s.verdict_end)]]) : h("div", { class: "notice", text: "read by the agent" })));
    } else app.append(block(name, h("div", { class: "notice", text: "read by the agent at the start of a run; hashed into the manifest" })));
  }
}

function showDeveloper() {
  const app = clear($("app"));
  app.className = "surface wide";
  const meta = S.meta;
  app.append(surfaceHead("Developer", ["sit-review-agent " + meta.version + (meta.commit ? " · commit " + meta.commit : "")]));
  const restart = ["dra", "ui", "--host", meta.bind_host, "--port", String(meta.port), ...(meta.ui_args || [])].join(" ");
  app.append(h("div", { class: "cfg" }, h("h2", { text: "This server" }), h("dl", { class: "kv wide" },
    h("dt", { text: "command" }), h("dd", {}, h("div", { class: "cmd", style: "margin:0", text: restart })),
    h("dt", { text: "run directory" }), h("dd", {}, h("span", { class: "mono", text: meta.runs_dir })),
    h("dt", { text: "version" }), h("dd", { text: "sit-review-agent " + meta.version + (meta.commit ? ", git " + meta.commit : "") }),
    h("dt", { text: "backend" }), h("dd", { text: (meta.backend || "–") + (meta.model ? " · " + meta.model : "") }))));
  const open = S.runs.find((r) => r.run_id === S.runId) || S.runs[0];
  if (open) app.append(h("div", { class: "cfg" }, h("h2", {}, (S.runId === open.run_id ? "The open run" : "The newest run") + " ", h("span", { class: "mono", text: open.run_id })), h("dl", { class: "kv wide" },
    h("dt", { text: "command" }), h("dd", {}, h("div", { class: "cmd", style: "margin:0", text: open.argv || "not recorded (no ui/launch.json and no manifest argv)" })),
    h("dt", { text: "directory" }), h("dd", {}, h("span", { class: "mono", text: meta.runs_dir + "/" + open.run_id })),
    h("dt", { text: "replay" }), h("dd", {}, h("span", { class: "mono", text: "dra replay " + meta.runs_dir_name + "/" + open.run_id })))));
  app.append(h("div", { class: "cfg" }, h("h2", { text: "Routes this page reads" }), h("div", { class: "notice", text: "GET /meta · GET /runs · GET /runs/<id> · GET /runs/<id>/events (SSE) · GET /runs/<id>/log · GET /runs/<id>/report · GET /runs/<id>/coverage · GET /runs/<id>/stage/<name> · GET /runs/<id>/funnel · GET /runs/<id>/glossary · GET /runs/<id>/outputs · GET /runs/<id>/chat · GET /tools · GET /documents. Writes: POST /runs, POST /runs/<id>/stop, POST /runs/<id>/email, POST /runs/<id>/chat, POST /tools/probe, each only on a button." })));
}

// ------------------------------------------------------------------ the run, from the event stream
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
// The records after which a stage's or a shard's file can have been written (ui/stages.py reads those files).
const STAGE_ENDS = ["phase_done", "shard_drafted", "shard_cut", "shard_failed", "shards_merged", "refined", "refine_fallback", "anchors_verified", "verdict", "run_finished", "run_error"];
// call_closed outcomes that end the call without an answer (the schema's enum, less ok, cut and replaced).
const CALL_FAILED = ["refusal", "truncated", "error", "cancelled", "interrupted"];

function newRunModel() {
  return { limits: null, deadline: null, profile: null, mode: null, replay: false, resumed: false, shardCount: null, lastT: 0,
    tracks: new Map(), byCall: new Map(), drafts: [], seen: new Set(), events: [], finished: null, error: null, verdict: null,
    stopRule: null, doc: null, runId: null,
    // The limit note of a cut refine call, completed by the refined or refine_fallback record that follows it.
    refineCut: null,
    // Whether the run was launched with --no-tools (ui/launch.json, set by showRun); null for a run started elsewhere.
    noTools: null,
    // A limit that fired, in plain words, with the run clock it fired at; drafted finding count per call (for "n of m kept").
    limitNotes: [], draftedByCall: new Map(),
    // The counts the "What is happening" panel fills in (recordFacts), each the fields of one record type; and the rows
    // (track keys, or "limits" for the axis) whose Why is open.
    x: { ended: false, criteria: null, intent: null, plan: null, research: null, servers: [], toolCalls: null, researchStop: null, merged: null,
      refineFindings: null, retry: null, refined: null, anchors: null },
    why: new Set() };
}

// One model call of a track (call_opened), with the latest call_status fields and the draft items streamed from it.
function callRecord(t, callId, ev, f, now) {
  if (!t.calls.has(callId)) {
    t.calls.set(callId, { id: callId, phase: ev.phase, purpose: f.purpose ?? null, attempt: f.attempt ?? null, iteration: f.iteration ?? null,
      openedAt: now, closedAt: null, outcome: null, kept: null, status: null, statusAt: null, drafts: [], lists: {}, seen: new Set() });
  }
  return t.calls.get(callId);
}
function callDraft(cr, key, d) {
  if (!cr || cr.seen.has(key) || !d) return;
  cr.seen.add(key);
  cr.drafts.push({ severity: d.severity, kind: d.kind, title: d.title });
}

// Which recorded limit a stage runs against: stage 1 and its members, refine, verdict; report runs to the deadline.
function limitFor(m, stage) {
  const lim = m.limits || {};
  const s = { stage_1: lim.stage_1_end, ingest: lim.stage_1_end, understand: lim.stage_1_end, plan: lim.stage_1_end, research: lim.stage_1_end,
    assess: lim.stage_1_end, merge: lim.stage_1_end, refine: lim.refine_end, verify: lim.refine_end, verdict: lim.verdict_end, report: m.deadline }[stage];
  return typeof s === "number" ? s : null;
}
function limitName(stage) { return stage === "stage_1" || STAGE1.includes(stage) || stage === "assess" || stage === "merge" ? "stage 1" : words(stage); }
function noteLimit(m, t, text) { const n = { t, text }; m.limitNotes.push(n); return n; }

function track(m, key, label) {
  if (!m.tracks.has(key)) m.tracks.set(key, { key, label: label || key, status: "waiting", call: null, start: null, end: null, text: null, strong: null, cutAt: null, skippedAt: null, shard: null, disclose: null, calls: new Map() });
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
  recordFacts(m, ev, f);
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
      if (t.status !== "cut" && t.status !== "failed" && !t.docOnly) t.status = "done";
      t.end = now; if (t.start === null) t.start = now - (f.seconds || 0);
      if (f.stopped_at_limit) {
        t.strong = null; t.text = "stopped at the stage limit";
        const lim = limitFor(m, f.stage);
        noteLimit(m, now, sentence(limitName(f.stage)) + " limit" + (lim !== null ? " " + clock(lim) : "") + " reached; " + ev.phase + " stopped there at " + clock(now) + ".");
      }
      break;
    }
    case "stage_limit_passed": {
      const lname = f.limit === "stage_1_end" ? "stage 1" : words(f.limit);
      noteLimit(m, now, sentence(lname) + " limit" + (typeof f.limit_s === "number" ? " " + clock(f.limit_s) : "") + " passed" + (typeof f.grace_s === "number" ? " by the " + dur(f.grace_s) + " grace" : "") + "; stopping " + (f.stopped || []).map(words).join(", ") + ".");
      break;
    }
    case "research_started": { const t = track(m, "research"); t.strong = null; t.text = intl(f.questions) + " question(s) to research"; break; }
    case "research_stopped": {
      const t = track(m, "research");
      if (researchWasOff(f)) {
        // No tool gateway at all (phases/research.py _doc_only "no_tools"): research was never attempted, so nothing failed.
        // Its disclosure ID stays on the stage's disclosure line (t.disclose, from research_doc_only).
        t.status = "skipped"; t.skippedAt = now; t.docOnly = true; t.strong = null;
        t.text = "document only (" + (m.noTools ? "--no-tools" : "no tool server in use") + "): " + intl(f.questions) + " question(s) left to the document";
      } else { t.strong = null; t.text = researchStopWords(f) + ": " + intl(f.answered) + " of " + intl(f.questions) + " question(s) answered, " + intl(f.tool_calls) + " tool call(s)"; }
      break;
    }
    case "phase_skipped": { const t = track(m, ev.phase); t.status = "skipped"; t.skippedAt = now; t.strong = null; t.text = words(f.reason); break; }
    case "research_skipped": { const t = track(m, "research"); t.status = "skipped"; t.skippedAt = now; t.strong = null; t.text = words(f.reason); break; }
    case "research_doc_only": {
      const t = track(m, "research"); t.strong = f.degradation_id || null; t.text = (f.degradation_id ? " in the report · " : "") + "document only: " + (f.detail || "");
      if (f.degradation_id) t.disclose = { id: f.degradation_id, text: f.detail || "" };
      break;
    }
    case "call_opened": {
      const key = (ev.phase === "assess" && shardKey(m, f.shard)) || ev.phase;
      const t = track(m, key);
      t.call = f.call_id; if (t.status !== "cut") t.status = inFlight(m); if (t.start === null) t.start = now; if (f.shard_name) t.shard = f.shard_name;
      m.byCall.set(f.call_id, t);
      callRecord(t, f.call_id, ev, f, now);
      break;
    }
    case "call_status":
      for (const c of f.calls || []) {
        const t = m.byCall.get(c.call_id); if (!t) continue;
        if (typeof c.items === "number" && c.items > 0) { t.strong = intl(c.items); t.text = (c.items === 1 ? " item" : " items") + " streamed" + (typeof c.chars === "number" ? " (" + intl(c.chars) + " chars)" : ""); }
        else if (typeof c.chars === "number" && c.chars > 0) { t.strong = null; t.text = "answer streaming (" + intl(c.chars) + " chars)"; }
        else if (typeof c.thinking_tokens === "number" && c.thinking_tokens > 0) { t.strong = null; t.text = "thinking ~" + intl(c.thinking_tokens) + " tokens"; }
        else { t.strong = null; t.text = "starting"; }
        const cr = t.calls.get(c.call_id);
        if (cr) { cr.status = { phase: c.phase ?? null, label: c.label || null, thinking: c.thinking_tokens ?? null, items: c.items ?? null, chars: c.chars ?? null }; cr.statusAt = now; }
      }
      break;
    case "call_retry": { const t = track(m, ev.phase); t.strong = null; t.text = "retry: " + words(f.reason); break; }
    case "call_closed": {
      const t = m.byCall.get(f.call_id); if (!t) break;
      const cr = t.calls.get(f.call_id);
      if (cr) { cr.closedAt = now; cr.outcome = f.outcome; if (typeof f.kept_items === "number") cr.kept = f.kept_items; }
      if (f.outcome === "cut") { t.status = "cut"; t.cutAt = now; t.end = now; t.strong = null; t.text = typeof f.kept_items === "number" ? "kept " + intl(f.kept_items) + " finished item(s)" : t.text; }
      else if (CALL_FAILED.includes(f.outcome)) { t.status = "failed"; t.end = now; t.strong = null; t.text = words(f.outcome); }
      else if (t.key.startsWith("assess ")) { t.status = "done"; t.end = now; }
      break;
    }
    case "draft_item": {
      const t = m.byCall.get(f.call_id), cr = t ? t.calls.get(f.call_id) : null;
      if (cr && f.list) cr.lists[f.list] = (cr.lists[f.list] || 0) + 1;
      if (f.list === "findings") {
        // Distinct drafts only: a record repeated for the same call and index (a second stream of the same call) is one draft.
        if (!m.seen.has(f.call_id + "#" + f.index)) m.draftedByCall.set(f.call_id, (m.draftedByCall.get(f.call_id) || 0) + 1);
        addDraft(m, f.call_id + "#" + f.index, now, f, whoOf(m, f.shard, f.call_id));
        callDraft(cr, f.call_id + "#" + f.index, f);
      }
      break;
    }
    case "shard_drafted": {
      const t = m.byCall.get(f.call_id) || track(m, shardKey(m, f.shard));
      t.strong = intl(f.findings); t.text = " draft finding(s), " + intl(f.sound_areas) + " sound area(s), unverified";
      for (const d of f.drafts || []) { addDraft(m, f.call_id + "#" + d.index, now, d, whoOf(m, f.shard, f.call_id)); callDraft(t.calls.get(f.call_id), f.call_id + "#" + d.index, d); }
      break;
    }
    case "shard_cut": {
      const t = (f.call_id && m.byCall.get(f.call_id)) || track(m, shardKey(m, f.shard));
      t.status = "cut"; t.cutAt = f.cut_at_s ?? now; t.end = t.cutAt;
      t.strong = f.degradation_id || null;
      const kept = "kept " + intl(f.kept) + " finished finding(s)" + ((f.criteria_not_assessed || []).length ? "; not assessed: " + f.criteria_not_assessed.join(", ") : "");
      t.text = (f.degradation_id ? " in the report · " : "") + kept;
      if (f.degradation_id) t.disclose = { id: f.degradation_id, text: t.key + " cut at " + clock(t.cutAt) + ": " + kept };
      for (const d of f.kept_drafts || []) { addDraft(m, f.call_id + "#" + d.index, now, d, whoOf(m, f.shard, f.call_id)); callDraft(t.calls.get(f.call_id), f.call_id + "#" + d.index, d); }
      { const cr = t.calls.get(f.call_id); if (cr) { cr.outcome = cr.outcome || "cut"; cr.closedAt = cr.closedAt ?? t.cutAt; cr.kept = f.kept; } }
      {
        const lim = limitFor(m, "stage_1"), drafted = m.draftedByCall.get(f.call_id) || 0;
        const keptText = drafted ? intl(f.kept) + " of " + intl(drafted) + " drafts kept" : intl(f.kept) + " draft(s) kept";
        noteLimit(m, now, "Stage 1 limit" + (lim !== null ? " " + clock(lim) : "") + " reached; assess shard " + f.shard + (f.shard_name ? " (" + words(f.shard_name) + ")" : "") + " ended there at " + clock(t.cutAt) + ", " + keptText + ((f.criteria_not_assessed || []).length ? "; not assessed: " + f.criteria_not_assessed.join(", ") : "") + ".");
      }
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
      { const cr = t.calls.get(f.call_id); if (cr) { cr.outcome = "cut"; cr.closedAt = t.cutAt; cr.kept = f.kept_items; } }
      {
        const lim = limitFor(m, f.stage);
        const note = noteLimit(m, now, sentence(words(f.stage)) + ": the model call " + f.call_id + " was cut at " + clock(t.cutAt) + (lim !== null ? " (" + limitName(f.stage) + " ends by " + clock(lim) + ")" : "") + "; " + intl(f.kept_items) + " finished item(s) kept.");
        if (f.stage === "refine") m.refineCut = note;
      }
      break;
    }
    // What refine did with the cut call's finished revisions (phases/refine.py): applied (salvaged) or none (fallback).
    // The row and the limit note say it, so neither stops at "kept"; the counts are the record's.
    case "refined": {
      const t = track(m, "refine");
      t.strong = intl(f.findings);
      t.text = " findings: " + intl(f.revised) + " revised, " + intl(f.merged) + " merged, " + intl(f.withdrawn) + " withdrawn, " + intl(f.unchanged) + " unchanged" +
        (f.salvaged ? "; " + intl(f.applied) + " of " + intl(f.salvaged_items) + " finished revisions applied" : "");
      if (f.salvaged && m.refineCut) m.refineCut.text += " Refine then applied " + intl(f.applied) + " of the " + intl(f.salvaged_items) + " finished revisions (" + intl(f.merged) + " merges into kept findings among them) and dropped " + intl(f.dropped) + "; a finding without an applied revision stays as merged.";
      break;
    }
    case "refine_fallback": {
      const t = track(m, "refine");
      t.strong = null; t.text = "fallback: no revision applied; the merged findings stand, in severity and confidence order";
      if (m.refineCut) m.refineCut.text += " No revision could be applied: the merged findings stand, in severity and confidence order.";
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

// ------------------------------------------------------------------ "What is happening": explanation, never the record
// The text is the #explain-map JSON in index.html (one entry per stage, written in advance from docs/ARCHITECTURE.md and
// the code each entry's "src" names). A {name} in it is filled by FACTS from the model this reducer built from the
// run's own records; a sentence whose names are not all known yet gives way to its "else" or is left out, so the panel
// never shows an empty or made-up number. tests/test_ui_explain.py pins every name to FACTS.

const EXPLAIN = (() => { const el = $("explain-map"); try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; } })();
// The qualified tool name is <server>__<tool> (tools/gateway.py QUALIFIER, qualify).
const QUALIFIER = "__";

// The fields of the records the explanation reads, kept as the record has them (spec/progress_event.schema.json).
function recordFacts(m, ev, f) {
  const x = m.x;
  switch (ev.type) {
    // A run that ended and was resumed (dra resume appends to the same file) is running again until its next end.
    case "run_started": x.ended = false; if (Array.isArray(f.criteria)) x.criteria = f.criteria.length; break;
    case "run_resuming": x.ended = false; break;
    case "run_finished": case "run_error": x.ended = true; break;
    case "assess_started": if (typeof f.criteria === "number") x.criteria = f.criteria; break;
    case "intent_ready": x.intent = f; break;
    case "plan_ready": x.plan = f; break;
    case "research_started": x.research = f; break;
    case "tool_round":
      x.toolCalls = (x.toolCalls || 0) + (typeof f.calls === "number" ? f.calls : 0);
      for (const name of f.tools || []) { const server = String(name).split(QUALIFIER)[0]; if (server && !x.servers.includes(server)) x.servers.push(server); }
      break;
    case "research_stopped": x.researchStop = f; break;
    case "shards_merged": x.merged = f; break;
    case "refine_started": x.refineFindings = f.findings ?? null; break;
    case "call_retry": if (ev.phase === "refine" && f.reason === "rule_repair") x.retry = f; break;
    case "refined": x.refined = f; break;
    case "anchors_verified": x.anchors = f; break;
    default: break;
  }
}

// research_stopped with detail "no_tools": the run had no tool gateway (--no-tools, or every server off), which the
// record files under the tool_failure code; every other stop keeps its code and its reason.
function researchWasOff(f) { return !!f && f.code === "tool_failure" && f.detail === "no_tools"; }
function researchStopWords(f) { return words(f.code) + (f.detail && f.detail !== f.code ? ", " + words(f.detail) : ""); }

function clk(s) { return typeof s === "number" ? clock(s) : null; }
function listWords(xs) { return xs.length > 1 ? xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1] : xs.join(""); }
function shardTracks(m) { return [...m.tracks.values()].filter((t) => t.key.startsWith("assess ")); }
function field(o, k) { return o ? o[k] : null; }

// Every name the explanation may use, and where its value comes from. A value of null or undefined is "not known yet".
const FACTS = {
  pages: (m) => field(m.doc, "pages"),
  sections: (m) => field(m.doc, "sections"),
  criteria: (m) => m.x.criteria,
  objectives: (m) => field(m.x.intent, "objectives"),
  constraints: (m) => field(m.x.intent, "constraints"),
  registry_entries: (m) => field(m.x.intent, "registry_entries"),
  questions: (m) => field(m.x.plan, "questions"),
  external: (m) => field(m.x.plan, "external"),
  shards: (m) => m.shardCount,
  shards_drafted: (m) => shardTracks(m).filter((t) => t.status === "done").length,
  shards_cut: (m) => shardTracks(m).filter((t) => t.status === "cut").length,
  drafts: (m) => m.drafts.length,
  merged_findings: (m) => field(m.x.merged, "findings") ?? m.x.refineFindings,
  stage_1_end: (m) => clk(field(m.limits, "stage_1_end")),
  refine_end: (m) => clk(field(m.limits, "refine_end")),
  verdict_end: (m) => clk(field(m.limits, "verdict_end")),
  deadline: (m) => clk(m.deadline),
  // Null when research never ran (no tool gateway), so no sentence says the servers were asked these questions.
  research_questions: (m) => (researchWasOff(m.x.researchStop) ? null : field(m.x.research, "questions") ?? field(m.x.researchStop, "questions")),
  tools_offered: (m) => field(m.x.research, "tools"),
  servers: (m) => (m.x.servers.length ? listWords(m.x.servers) : null),
  tool_calls: (m) => field(m.x.researchStop, "tool_calls") ?? m.x.toolCalls,
  research_stop: (m) => (m.x.researchStop && !researchWasOff(m.x.researchStop) ? researchStopWords(m.x.researchStop) : null),
  research_left: (m) => (researchWasOff(m.x.researchStop) ? field(m.x.researchStop, "questions") : null),
  answered: (m) => field(m.x.researchStop, "answered"),
  ledger_entries: (m) => field(m.x.researchStop, "ledger_entries"),
  refine_kept: (m) => field(m.x.retry, "kept"),
  refine_retry: (m) => field(m.x.retry, "retry"),
  revised: (m) => field(m.x.refined, "revised"),
  merged: (m) => field(m.x.refined, "merged"),
  withdrawn: (m) => field(m.x.refined, "withdrawn"),
  unchanged: (m) => field(m.x.refined, "unchanged"),
  refined_findings: (m) => field(m.x.refined, "findings"),
  anchors: (m) => field(m.x.anchors, "anchors"),
  resolved: (m) => field(m.x.anchors, "resolved"),
  unresolved_anchors: (m) => field(m.x.anchors, "unresolved"),
  findings_verified: (m) => field(m.x.anchors, "findings_verified"),
  findings_unverified: (m) => field(m.x.anchors, "findings_unverified"),
  verdict: (m) => (m.verdict ? words(m.verdict.label) : null),
  confidence: (m) => (m.verdict && typeof m.verdict.confidence === "number" ? conf(m.verdict.confidence) : null),
  final_findings: (m) => field(m.verdict, "findings"),
  unresolved: (m) => field(m.verdict, "unresolved"),
  limitations: (m) => field(m.verdict, "limitations"),
  limits_reached: (m) => m.limitNotes.length,
  outcome: (m) => (m.finished ? words(m.finished.outcome) : null),
  wall: (m) => (m.finished && typeof m.finished.wall_s === "number" ? dur(m.finished.wall_s) : null),
  cost: (m) => (m.finished && typeof m.finished.cost_usd === "number" && !m.finished.cost_is_lower_bound ? money(m.finished.cost_usd, false) : null),
  cost_lower_bound: (m) => (m.finished && typeof m.finished.cost_usd === "number" && m.finished.cost_is_lower_bound ? money(m.finished.cost_usd, false) : null),
  run_error: (m) => field(m.error, "error"),
};

function factText(m, name) {
  const get = FACTS[name];
  const v = get ? get(m) : null;
  if (typeof v === "number") return Number.isFinite(v) ? intl(v) : null;
  return typeof v === "string" && v !== "" ? v : null;
}

// One sentence with its names filled (strings and <b> values), or null when a name is not known yet.
function fillSentence(m, text) {
  const parts = String(text).split(/\{(\w+)\}/);
  const out = [];
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { if (parts[i]) out.push(parts[i]); continue; }
    const v = factText(m, parts[i]);
    if (v === null) return null;
    out.push(h("b", { class: "num", text: v }));
  }
  return out;
}
function saySentence(m, item) {
  if (typeof item === "string") return fillSentence(m, item);
  if (!item || typeof item !== "object") return null;
  return fillSentence(m, item.text) || (item.else !== undefined ? saySentence(m, item.else) : null);
}

// Which entry a track row stands for: every assess shard and the merge are "assess", the verdict call is "report".
function entryOf(key) {
  if (key.startsWith("assess") || key === "merge") return "assess";
  if (key === "verdict") return "report";
  return EXPLAIN[key] ? key : null;
}

// The entries for now: the finished run's summary; else the stage in flight, latest first for the stages in order and
// every member in flight for stage 1 (they run side by side); between two records, the stage that started last. A
// stop at a limit since the stage began adds the limits entry.
function explainKeys(m) {
  if (m.x.ended) return ["finished"];
  const live = [...m.tracks.values()].filter((t) => t.status === "running" || t.status === "replayed");
  const keys = live.map((t) => entryOf(t.key)).filter(Boolean);
  let now = ["report", "verify", "refine"].filter((k) => keys.includes(k)).slice(0, 1);
  if (!now.length) now = ["understand", "plan", "research", "assess", "ingest"].filter((k) => keys.includes(k));
  if (!now.length) {
    let last = null;
    for (const t of m.tracks.values()) if (t.start !== null && entryOf(t.key) && (last === null || t.start >= last.start)) last = t;
    if (last) now = [entryOf(last.key)];
  }
  const begun = [...m.tracks.values()].filter((t) => t.start !== null && now.includes(entryOf(t.key))).map((t) => t.start);
  if (begun.length && m.limitNotes.some((n) => n.t >= Math.min(...begun))) now.push("limits");
  return now;
}

function explainEntry(m, key, cls) {
  const e = EXPLAIN[key];
  if (!e) return null;
  const said = (e.says || []).map((item) => saySentence(m, item)).filter(Boolean);
  const p = h("p", { class: "xtext" });
  said.forEach((s, i) => { if (i) p.append(" "); p.append(...s); });
  return h("div", { class: "xentry" + (cls ? " " + cls : ""), "data-stage": key },
    h("div", { class: "xtitle", text: e.title || key }), p, e.src ? h("div", { class: "xsrc" }, "From ", h("span", { class: "mono", text: e.src })) : null);
}
// The text of one entry as the panel shows it (the tests read every entry through this).
function explainText(m, key) { const el = explainEntry(m, key); return el ? el.querySelector(".xtext").textContent : null; }

function renderExplain(m) {
  const body = $("explain-body");
  if (!body) return;
  clear(body);
  const keys = explainKeys(m);
  body.dataset.stages = keys.join(" ");
  if (!keys.length) { body.append(h("p", { class: "xtext muted", text: "No stage has started yet; the run's first records fill this in." })); return; }
  const stage1 = keys.filter((k) => ["understand", "plan", "research", "assess"].includes(k));
  if (stage1.length > 1) body.append(h("div", { class: "xnote", text: "Stage 1 runs these side by side, so each is explained here:" }));
  for (const k of keys) body.append(explainEntry(m, k, k === "limits" ? "limits" : null));
}

// The Why control of a row (or of the axis, for the limits): opens the entry of that stage under the row, in place.
function whyButton(m, rowKey, entry) {
  if (!entry || !EXPLAIN[entry]) return h("span", {});
  const open = m.why.has(rowKey);
  return h("button", { class: "why-btn", type: "button", "data-why": rowKey, "aria-expanded": String(open), title: (open ? "Hide" : "Show") + " why this stage works this way",
    onclick: () => { if (open) m.why.delete(rowKey); else m.why.add(rowKey); renderRun(m); }, text: "Why" });
}
function whyBlock(m, rowKey, entry) {
  if (!m.why.has(rowKey) || !entry) return null;
  return h("div", { class: "why", "data-why": rowKey }, explainEntry(m, entry));
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
  const open = panelOpen(t.key);
  return h("div", { class: "track" + (open ? " open" : ""), "data-track": t.key, "data-status": t.status },
    h("div", { class: "name" }, nameButton(m, t.key, t.label, t.calls.size), t.call ? h("span", { class: "call mono", text: t.call }) : null),
    h("div", {}, h("span", { class: "pill " + t.status, text: pillText })), time, status, whyButton(m, t.key, entryOf(t.key)));
}

// A row's name opens what its stage produced in the panel beside the rows (one stage at a time); the row of the
// shards before their number is known has nothing to open yet.
function nameButton(m, key, label, calls) {
  if (!stageOf(key)) return label;
  const open = panelOpen(key);
  return h("button", { class: "name-btn", type: "button", "aria-expanded": String(open), "aria-controls": "stage-panel", "data-panel": key, "data-calls": String(calls),
    title: (open ? "Close" : "Open") + " what " + label + " produced", onclick: () => togglePanel(m, key) },
  h("span", { class: "chev", "aria-hidden": "true", text: "▸" }), label);
}

// The latest call_status fields of a call, as the record has them: label, reasoning tokens, items, chars.
function callStatusText(cr) {
  const st = cr.status;
  if (!st) return cr.closedAt === null ? "no status yet" : "";
  const bits = [];
  if (st.label) bits.push(st.label);
  if (typeof st.thinking === "number" && st.thinking > 0) bits.push("thinking ~" + intl(st.thinking) + " tokens");
  if (typeof st.items === "number" && st.items > 0) bits.push(intl(st.items) + (st.items === 1 ? " item" : " items"));
  if (typeof st.chars === "number" && st.chars > 0) bits.push(intl(st.chars) + " chars");
  return (bits.length ? bits.join(" · ") : "starting") + " · as of " + clock(cr.statusAt);
}

function callState(m, cr) {
  if (cr.closedAt === null) return [inFlight(m), inFlight(m)];
  if (cr.outcome === "cut") return ["cut", "cut at " + clock(cr.closedAt) + (typeof cr.kept === "number" ? ", " + intl(cr.kept) + " kept" : "")];
  if (CALL_FAILED.includes(cr.outcome)) return ["failed", words(cr.outcome)];
  return ["done", "closed at " + clock(cr.closedAt)];
}

// The calls of one track: one row per call_id with its purpose, state and latest status, and while the stage's own
// file is not written yet, what its stream has carried so far: the finding drafts by title, every other list by its
// count, since the stream carries no text for those (the file, listed below once written, holds them in full).
function callsBlock(m, t, streamed) {
  const box = h("div", { class: "calls", "data-track": t.key });
  for (const cr of t.calls.values()) {
    const [st, stText] = callState(m, cr);
    const about = [cr.purpose, typeof cr.attempt === "number" && cr.attempt > 0 ? "attempt " + intl(cr.attempt) : null].filter(Boolean).join(", ");
    const lists = Object.entries(cr.lists).filter(([k]) => k !== "findings").map(([k, v]) => intl(v) + " " + words(k) + (v === 1 ? " item" : " items"));
    const row = h("div", { class: "callrow", "data-call": cr.id, "data-status": st },
      h("div", { class: "cid mono", text: cr.id }),
      h("div", { class: "about" }, h("span", { class: "mono", text: about }), " · opened " + clock(cr.openedAt)),
      h("div", {}, h("span", { class: "pill " + st, text: stText })),
      h("div", { class: "cstatus", text: callStatusText(cr) }));
    box.append(row);
    if (streamed && (cr.drafts.length || lists.length)) {
      const d = h("div", { class: "cdrafts" });
      if (cr.drafts.length) d.append(h("div", { class: "clists" }, "Findings streamed so far ", chip("draft, unverified", "run-draft", "draft")));
      cr.drafts.forEach((x, i) => {
        const sev = x.kind === "strength" ? "strength" : (x.severity || "");
        d.append(h("div", { class: "cdraft" }, h("span", { class: "num mono", text: String(i + 1) }), sev ? chip(sev, sev === "strength" ? "kind-strength" : "sev-" + sev, sev) : null, x.kind && x.kind !== "strength" ? h("span", { class: "kind", text: words(x.kind) }) : null, h("span", { class: "text", text: x.title || "" })));
      });
      for (const l of lists) d.append(h("div", { class: "clists", text: l + " streamed so far: the stream carries their count, the stage's file their text." }));
      box.append(d);
    }
  }
  return box;
}

// ------------------------------------------------------------------ the stage panel: what each stage produced
// GET /runs/<id>/stage/<name> (ui/stages.py) reads the files the run wrote when each stage ended; this page only lays
// them out. One stage at a time, in the Draft findings column's place beside the rows, so opening a stage never
// moves the rows. Every list is whole: its count is its length, its text wraps and nothing is cut short; a long one
// gets a filter and group headings. Drafts keep their draft, unverified chip. A file the run has not written is named
// with what it would hold. A chip opens its definition from GET /runs/<id>/glossary, the export's one vocabulary.

// The panel a row opens: a shard row its shard, the verdict row the report; "funnel" is the findings funnel.
function stageOf(key) {
  if (key === "funnel") return "funnel";
  if (key.startsWith("assess ")) return "assess-" + parseInt(key.slice(7), 10);
  if (key === "assess") return null;
  return key === "verdict" ? "report" : key;
}
function panelOpen(key) { return !!S.panel && S.panel.key === key; }
let UID = 0;

function togglePanel(m, key) {
  if (panelOpen(key)) { closePanel(m); return; }
  S.panel = { key, stage: stageOf(key), data: null, error: null, ask: 0, open: new Set(), filters: new Map(), legends: new Set(), focus: true };
  renderRun(m);
  renderFunnel();
  loadGlossary();
  loadPanel();
}

function closePanel(m) {
  const key = S.panel ? S.panel.key : null;
  S.panel = null;
  renderRun(m);
  renderFunnel();
  const back = key ? document.querySelector('[data-panel="' + key + '"]') : null;
  if (back) back.focus();
}

async function loadPanel() {
  const P = S.panel;
  if (!P || !P.stage || !S.runId) return;
  const ask = ++P.ask;
  const url = "/runs/" + encodeURIComponent(S.runId) + (P.stage === "funnel" ? "/funnel" : "/stage/" + encodeURIComponent(P.stage));
  try { const d = await api(url); if (S.panel !== P || ask !== P.ask) return; P.data = d; P.error = null; }
  catch (e) { if (S.panel !== P || ask !== P.ask) return; P.error = e.message; }
  renderPanel();
}

async function loadGlossary() {
  const runId = S.runId;
  if (!runId || (S.glossary && S.glossary.runId === runId)) return S.glossary;
  const G = { runId, terms: null, error: null };
  S.glossary = G;
  try { G.terms = (await api("/runs/" + encodeURIComponent(runId) + "/glossary")).terms || {}; }
  catch (e) { G.error = e.message; }
  return G;
}

// The panel's frame on every repaint of the run (open or not, the live model calls); its content only when read.
function renderPanelFrame(m) {
  const box = $("stage-panel");
  if (!box) return;
  const P = S.panel;
  box.parentElement.classList.toggle("panel-open", !!P);
  box.hidden = !P;
  const calls = $("sp-calls");
  clear(calls);
  if (!P || !m || P.stage === "funnel") return;
  const t = m.tracks.get(P.key);
  if (!t || !t.calls.size) return;
  // The streamed items only while the stage's own file is missing: once written, the lists below hold them in full.
  const streamed = !P.data || (P.data.missing || []).length > 0;
  calls.append(h("div", { class: "sp-list-head" }, h("h3", {}, "Model calls ", h("span", { class: "n num", text: intl(t.calls.size) }))), callsBlock(m, t, streamed));
}

function renderPanel() {
  const P = S.panel;
  if (!P || !$("stage-panel")) return;
  renderPanelFrame(S.model);
  const D = P.data;
  $("sp-title").textContent = D && D.title ? D.title : (P.stage === "funnel" ? "The findings, from drafts to the report" : words(P.key));
  $("sp-kicker").textContent = P.stage === "funnel" ? "Every merged draft and its fate" : "What this stage produced";
  const c = clear($("sp-content"));
  if (P.error) c.append(h("p", { class: "error", text: "This stage could not be read: " + P.error }));
  else if (!D) c.append(h("p", { class: "sp-empty", text: "Reading the run's files." }));
  else {
    if (D.unreadable) c.append(h("div", { class: "sp-missing" }, "The run's files for this stage are not in the shape this page reads (" + D.unreadable + "), so nothing is listed from them."));
    for (const x of D.missing || []) c.append(missingLine(x));
    for (const n of D.notes || []) c.append(h("div", { class: "sp-note" + (n.tone === "warn" ? " warn" : "") }, h("span", { text: n.text }), n.src ? h("span", { class: "sp-src" }, " From ", h("span", { class: "mono", text: n.src }), ".") : null));
    if (P.stage === "funnel") c.append(funnelSummary(D));
    const facts = (D.facts || []).filter((f) => f.value !== null && f.value !== undefined && f.value !== "");
    if (facts.length) c.append(h("dl", { class: "kv sp-facts" }, facts.map((f) => [h("dt", { text: sentence(f.label) }), h("dd", { class: f.mono ? "mono" : null, title: f.src ? "From " + f.src : null }, String(typeof f.value === "number" ? intl(f.value) : f.value))])));
    if ((D.files || []).length) c.append(h("div", { class: "sp-src sp-files" }, "Read from ", h("span", { class: "mono", text: D.files.join(", ") })));
    for (const [k, label] of [["statement", "The design's purpose and scope, as understand summarised it"], ["rationale", "Rationale"], ["what_would_change_it", "What would change it"]]) {
      if (D[k]) c.append(h("div", { class: "sp-prose" }, h("h3", { text: label }), h("p", { text: D[k] })));
    }
    for (const L of D.lists || []) c.append(listBlock(P, L, D));
  }
  if (P.focus) { P.focus = false; $("sp-title").focus({ preventScroll: true }); }
}

function missingLine(x) {
  const running = S.info && S.info.status === "running";
  return h("div", { class: "sp-missing" }, h("span", { class: "mono", text: x.file }), running
    ? " is not written yet; the stage writes it when it ends. It holds " + x.what + "."
    : " is not in this run directory (a run cut short, or one written before the file existed), so this panel cannot list " + x.what + ".");
}

// The glossary terms a list's chips and headings use, and the ones the list names: its legend.
function listTerms(L) {
  const out = [...(L.terms || [])];
  for (const g of L.groups || []) if (g.term) out.push(g.term);
  for (const it of L.items || []) for (const t of itemTerms(it)) out.push(t);
  return [...new Set(out)].filter((t) => !S.glossary || !S.glossary.terms || S.glossary.terms[t]);
}

function listBlock(P, L, D) {
  const sec = h("section", { class: "sp-list", "data-list": L.key });
  const legendOn = P.legends.has(L.key);
  const terms = listTerms(L);
  const shown = h("span", { class: "n num", text: intl(L.count) });
  const legend = terms.length ? h("button", { class: "legend-btn", type: "button", "aria-expanded": String(legendOn), text: "What do these mean?",
    onclick: () => { if (P.legends.has(L.key)) P.legends.delete(L.key); else P.legends.add(L.key); renderPanel(); } }) : null;
  sec.append(h("div", { class: "sp-list-head" }, h("h3", {}, L.title + " ", shown), L.draft ? chip("draft, unverified", "run-draft", "draft") : null, legend));
  if (legendOn) sec.append(legendBlock(terms));
  if (L.src) sec.append(h("div", { class: "sp-src" }, "From ", h("span", { class: "mono", text: L.src })));
  if (L.note) sec.append(h("p", { class: "sp-lnote", text: L.note }));
  if (!(L.items || []).length) { sec.append(h("p", { class: "sp-empty", text: L.empty })); return sec; }
  const body = h("div", { class: "sp-items" });
  const groups = (L.groups || []).length ? L.groups : [{ key: null }];
  for (const g of groups) {
    const gbox = h("div", { class: "sp-groupbox", "data-group": g.key === null ? "" : g.key });
    if (g.key !== null) gbox.append(h("h4", { class: "sp-group" }, g.term ? chip(g.label, g.term, chipClass(g.term)) : h("span", { class: "sp-glabel", text: g.label }), h("span", { class: "n num", text: intl(g.count) })));
    for (const it of L.items) if (g.key === null || it.group === g.key) gbox.append(itemEl(P, L, it, D));
    body.append(gbox);
  }
  if (L.items.length >= 10) {
    const input = h("input", { class: "input sp-filter", type: "search", autocomplete: "off", spellcheck: "false", placeholder: "Filter the " + intl(L.count) + " items", "aria-label": "Filter: " + L.title });
    input.value = P.filters.get(L.key) || "";
    const apply = () => {
      const q = input.value.trim().toLowerCase();
      P.filters.set(L.key, input.value);
      let n = 0;
      for (const el of body.querySelectorAll(".sp-item")) { const on = !q || el.dataset.search.includes(q); el.hidden = !on; if (on) n++; }
      for (const gb of body.querySelectorAll(".sp-groupbox")) gb.hidden = !gb.querySelector(".sp-item:not([hidden])");
      shown.textContent = q ? intl(n) + " of " + intl(L.count) : intl(L.count);
    };
    input.addEventListener("input", apply);
    sec.append(input);
    sec.append(body);
    apply();
    return sec;
  }
  sec.append(body);
  return sec;
}

function legendBlock(terms) {
  const G = S.glossary;
  const box = h("div", { class: "term-legend" });
  if (!G || !G.terms) { box.append(h("p", { class: "sp-empty", text: G && G.error ? "The glossary could not be read: " + G.error : "Reading the glossary." })); return box; }
  for (const t of terms) box.append(termBody(t, G.terms[t]));
  return box;
}

function termBody(key, T) {
  if (!T) return h("div", { class: "term-entry" }, h("b", { text: key }), h("p", { text: "This word has no entry in the glossary." }));
  return h("div", { class: "term-entry", "data-term": key }, h("b", { class: "term-label", text: T.label }), T.paras.map((p) => h("p", { text: p })),
    h("div", { class: "sp-src" }, "From ", h("span", { class: "mono", text: T.src })));
}

// A chip: a pill that opens its glossary entry in place (one at a time on the page); without a term, a plain pill.
function chip(text, term, cls) {
  const c = "pill" + (cls ? " " + cls : "");
  if (!term) return h("span", { class: c, text });
  return h("button", { class: c + " chip", type: "button", "data-term": term, "aria-expanded": "false", title: "What “" + text + "” means", text });
}
function chipClass(term) {
  const [fam, val] = [term.split("-")[0], term.split("-").slice(1).join("-")];
  if (fam === "sev") return val;
  if (term === "kind-strength") return "strength";
  return "plain";
}

// One click on a chip opens its definition right under the line that holds it, and closes any other.
async function showTerm(btn) {
  const term = btn.dataset.term;
  const prev = document.querySelector(".term-def");
  const same = prev && prev.dataset.for === term && btn.getAttribute("aria-expanded") === "true";
  if (prev) prev.remove();
  for (const b of document.querySelectorAll('.chip[aria-expanded="true"]')) b.setAttribute("aria-expanded", "false");
  if (same) return;
  const host = btn.closest(".sp-meta, .sp-group, .sp-list-head, dd, .cdraft, .clists, .line, h2, .fhead") || btn.parentElement;
  const id = "term-" + (++UID);
  const box = h("div", { class: "term-def", id, role: "note", "data-for": term });
  const close = h("button", { class: "btn ghost td-close", type: "button", text: "Close", onclick: () => { box.remove(); btn.setAttribute("aria-expanded", "false"); btn.focus(); } });
  box.append(h("div", { class: "td-head" }, h("span", { class: "td-kicker", text: "What it means" }), close));
  host.after(box);
  btn.setAttribute("aria-expanded", "true");
  btn.setAttribute("aria-controls", id);
  const G = await loadGlossary();
  if (!box.isConnected) return;
  box.append(G && G.terms ? termBody(term, G.terms[term]) : h("p", { class: "sp-empty", text: "The glossary could not be read" + (G && G.error ? ": " + G.error : ".") }));
}
document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest(".chip[data-term]"); if (b) { e.preventDefault(); e.stopPropagation(); showTerm(b); } });

// ---------- the items: one renderer per type of record (ui/stages.py), each a meta line, its text and its full record

function ids(xs) { return (xs || []).filter(Boolean).join(", "); }
function loc(a) { return a ? "p." + (a.page ?? "–") + (a.section_ref ? " §" + a.section_ref : "") : ""; }
function quoteLine(a, extra) {
  return h("div", { class: "qrow" }, h("span", { class: "qloc num", text: loc(a) }), h("span", { class: "quote", text: "“" + (a.quote || "") + "”" }),
    (a.requirement_ids || []).length ? h("span", { class: "qreq", text: " " + a.requirement_ids.join(", ") }) : null, extra || null);
}
function sevChip(f) { return f.kind === "strength" ? chip("strength", "kind-strength", "strength") : (f.severity ? chip(f.severity, "sev-" + f.severity, f.severity) : null); }
function kindChip(kind) { return kind && kind !== "strength" ? chip(words(kind), "kind-" + kind, "plain") : null; }
function kvBlock(rows) {
  const kv = h("dl", { class: "kv" });
  for (const [k, v] of rows) if (v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length)) kv.append(h("dt", {}, k), h("dd", {}, v));
  return kv;
}
// Whether a list's groups are its items' own chip (a kind, a registry type, an outcome): the item then does not repeat it.
function groupedBy(L, fam) { return !!L && (L.groups || []).some((g) => g.term && g.term.startsWith(fam + "-")); }
function termWord(text, term) { return h("button", { class: "chip term-word", type: "button", "data-term": term, "aria-expanded": "false", text }); }

function anchorStatus(rows, i) {
  const r = (rows || []).find((x) => x.anchor_index === i);
  if (!r) return null;
  return h("span", { class: "qstat" }, " ", chip(r.anchor_status, "anchor-" + r.anchor_status, r.anchor_status === "unresolved" ? "high" : "plain"),
    " " + [r.method && r.method !== "none" ? r.method + " match" : null, typeof r.score === "number" && r.method !== "none" ? "score " + conf(r.score) : null, (r.reasons || []).join(", ") || null].filter(Boolean).join(", "));
}

// A finding in full: every field of its record as the stage's file holds it.
function findingRecord(it) {
  const f = it.rec || {};
  const box = h("div", { class: "rec" });
  box.append(h("p", { class: "statement", text: f.statement || "" }));
  box.append(kvBlock([
    [termWord("Rank", "rank"), typeof f.rank === "number" ? String(f.rank) : null],
    [termWord("Confidence", "confidence"), typeof f.confidence === "number" ? conf(f.confidence) : null],
    ["Category", f.category ? chip(words(f.category), "cat-" + f.category, "plain") : null],
    ["Disposition", f.disposition ? [chip(words(f.disposition), "disp-" + f.disposition, "plain"), ...(f.secondary_dispositions || []).map((d) => [" also ", chip(words(d), "disp-" + d, "plain")])] : null],
    ["Criteria", (f.criterion_ids || []).map((c) => [chip(words(c), "crit-" + c, "plain"), " "])],
    ["Acknowledged in the document", f.acknowledged_in_doc ? "yes" : null],
    ["Tags", ids(f.tags)],
    ["Provenance", f.provenance ? [f.provenance.phase, f.provenance.model].filter(Boolean).join(", ") : null],
  ]));
  if ((f.doc_anchors || []).length) {
    box.append(h("h4", { text: "Where in the document" }));
    f.doc_anchors.forEach((a, i) => box.append(quoteLine(a, anchorStatus(it.anchors, i))));
  }
  if ((f.evidence || []).length) {
    box.append(h("h4", { text: "Evidence" }));
    for (const e of f.evidence) {
      const kind = words(e.source_type) + (e.source_type === "inference" ? "" : (e.supports_claim === false ? ", contrary" : ", supports"));
      box.append(h("div", { class: "evrow" }, h("span", { class: "evid mono", text: e.evidence_id }), h("span", { class: "evkind", text: kind }),
        h("span", { class: "evtext" }, e.quote ? "“" + e.quote + "”" : (e.url_or_citation || ""), (e.derived_from || []).length ? h("span", { class: "muted", text: " derived from " + e.derived_from.join(", ") }) : null)));
    }
  }
  const r = f.recommendation;
  if (r) {
    box.append(h("h4", { text: "Recommendation" }));
    box.append(kvBlock([["Change", r.change_summary], ["Issue", r.issue], ["Rationale", r.rationale], ["Expected benefit", r.expected_benefit], ["Verification", r.verification],
      ["Objectives", ids(r.objective_refs)], ["Evidence", ids(r.supporting_evidence_ids)]]));
  }
  if (f.next_step) box.append(h("h4", { text: "Next step" }), h("p", { text: (f.next_step.owner ? f.next_step.owner + ": " : "") + (f.next_step.action || "") }));
  if (f.no_change_rationale) box.append(h("h4", { text: "No change, because" }), h("p", { text: f.no_change_rationale }));
  if ((f.affected_decisions || []).length) {
    box.append(h("h4", { text: "Decisions it touches" }));
    for (const d of f.affected_decisions) box.append(h("div", { class: "dec" }, h("span", { class: "rel", text: d.relation }), h("span", {}, h("b", { text: d.registry_id }), " " + (d.justification || ""))));
  }
  if (f.reassessment) box.append(h("h4", { text: "Re-assessment" }), h("p", { text: words(f.reassessment.status) + (f.reassessment.prior_finding_id ? " (was " + f.reassessment.prior_finding_id + ")" : "") + (f.reassessment.note ? ": " + f.reassessment.note : "") }));
  return box;
}

function rawRecord(rec) {
  return kvBlock(Object.entries(rec || {}).map(([k, v]) => [sentence(k), typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)]));
}

const ITEM = {
  section: { meta: (it) => [h("span", { class: "mono", text: "§" + it.id }), "p." + it.page_start + (it.page_end !== it.page_start ? "–" + it.page_end : ""), intl(it.chars) + " characters"],
    text: (it) => it.heading, cls: (it) => "lvl" + Math.min(it.level || 1, 2) },
  page: { meta: () => [], text: (it) => "Page " + it.number + ": " + intl(it.chars) + " characters of text" + (it.image_only ? ", image only (no text extracted)" : "") },
  degradation: { meta: (it) => [chip(it.id, "id-DEG", "plain"), words(it.dtype)], text: (it) => it.event, after: (it) => h("p", { class: "sp-after", text: "Impact: " + it.impact }) },
  registry: { meta: (it, D, L) => [h("b", { class: "mono", text: it.id }), groupedBy(L, "reg") ? null : chip(words(it.rtype), "reg-" + it.rtype, "plain"), it.doc_ref || ""], text: (it) => it.statement,
    detail: (it) => h("div", { class: "rec" }, it.anchor ? quoteLine(it.anchor) : h("p", { class: "muted", text: "No location recorded." })) },
  text: { meta: (it) => [chip("review input found", it.term, "plain")], text: (it) => it.text },
  intent: { meta: (it) => (it.ref ? [h("b", { class: "mono", text: it.ref })] : []), text: (it) => it.text },
  anchor_quote: { meta: () => [], text: (it) => loc(it.anchor) + " “" + (it.anchor.quote || "") + "”" },
  criterion: { meta: (it) => [chip(words(it.id), "crit-" + it.id, "plain")], text: (it) => it.question || it.id },
  question: { meta: (it) => [h("b", { class: "mono", text: it.id }), it.needs_external ? chip("needs external research", "q-external", "plain") : "from the document", it.status && it.status !== "open" ? words(it.status) : ""],
    text: (it) => it.question,
    detail: (it) => h("div", { class: "rec" }, kvBlock([["Criterion", chip(words(it.criterion), "crit-" + it.criterion, "plain")], ["Why it matters", it.rationale], ["Sections", ids(it.section_refs)],
      ["Tool (capability)", it.needs_external ? it.capability : null], ["Search queries", (it.queries || []).length ? h("ul", { class: "plain" }, it.queries.map((q) => h("li", { text: q }))) : null],
      ["Status", words(it.status)], ["Answer", it.summary], ["Ledger entries it cites", ids(it.evidence_ids)]])) },
  skip: { meta: () => [], text: (it) => JSON.stringify(it.rec), detail: (it) => rawRecord(it.rec) },
  tool_call: { meta: (it) => [h("b", { class: "mono", text: it.rec.call_id }), it.rec.server || ""], text: (it) => (it.rec.tool_name || "") + " · " + words(it.rec.status) + " · " + (it.rec.started_at || "") },
  ledger: { meta: (it) => [h("b", { class: "mono", text: it.rec.evidence_id }), words(it.rec.source_type)], text: (it) => it.rec.title || it.rec.url_or_citation || "", detail: (it) => rawRecord(it.rec) },
  finding: {
    meta: (it, D, L) => [h("b", { class: "mono", text: it.id || it.local_id }),
      it.merged_id ? "numbered " + it.merged_id + " at the merge" : "", it.shard ? "shard " + (it.shard_index || "?") + "'s " + it.local_id : "", sevChip(it.rec || {}), groupedBy(L, "kind") ? null : kindChip((it.rec || {}).kind),
      typeof (it.rec || {}).confidence === "number" ? "confidence " + conf(it.rec.confidence) : "", typeof (it.rec || {}).rank === "number" && !it.draft ? "rank " + it.rec.rank : ""],
    text: (it) => (it.rec || {}).title,
    after: (it) => (it.fate ? h("p", { class: "sp-after", text: "Became: " + it.fate }) : (it.refined === false ? h("p", { class: "sp-after warn", text: "Not refined: no revision was applied to it." }) : null)),
    detail: findingRecord },
  sound_area: { meta: (it) => [it.rec.id ? h("b", { class: "mono", text: it.rec.id }) : null, (it.rec.section_refs || []).map((x) => "§" + x).join(", ")],
    text: (it) => it.rec.why_sound,
    detail: (it) => { const b = h("div", { class: "rec" }); (it.rec.doc_anchors || []).forEach((a) => b.append(quoteLine(a))); b.append(kvBlock([["Related findings", ids(it.rec.related_finding_ids)], ["Evidence", ids(it.rec.evidence_ids)]])); return b; } },
  coverage: { meta: (it, D, L) => [chip(words(it.rec.criterion_id), "crit-" + it.rec.criterion_id, "plain"), groupedBy(L, "cov") ? null : chip(words(it.rec.outcome), "cov-" + it.rec.outcome, "plain"), (it.rec.finding_ids || []).join(", ")],
    text: (it) => it.rec.note || "" },
  revision: { meta: (it) => [h("b", { class: "mono", text: it.id }), it.group === "merged" ? chip("merge", "rev-merge", "plain") : (it.group === "withdrawn" ? chip("withdraw", "rev-withdraw", "plain") : (it.group.startsWith("not") ? "no revision applied" : chip("keep", "rev-keep", "plain"))),
    it.into ? "into " + it.into : "", sevChip({ kind: it.kind, severity: it.severity }), kindChip(it.kind)],
    text: (it) => it.title,
    after: (it) => h("p", { class: "sp-after" + (it.note ? "" : " muted"), text: it.note ? sentence(it.note) : (it.group.startsWith("not refined") ? "No revision of the cut answer was applied to it: it stays as merged." : "No reason recorded.") }),
    detail: (it) => kvBlock([["Fields refine changed", ids(it.changed)], ["From the call", it.call_id]]) },
  anchor: { meta: (it) => [h("b", { class: "mono", text: it.owner + " #" + (it.index + 1) }), chip(it.status, "anchor-" + it.status, it.status === "unresolved" ? "high" : "plain"),
    loc(it), it.method && it.method !== "none" ? it.method + " match" : "", typeof it.score === "number" && it.method !== "none" ? "score " + conf(it.score) : "", (it.reasons || []).join(", ")],
    text: (it) => (it.quote ? "“" + it.quote + "”" : "(the quote is not in this stage's state)") },
  verified: { meta: (it) => [h("b", { class: "mono", text: it.id }), it.severity || it.kind ? [sevChip({ kind: it.kind, severity: it.severity }), kindChip(it.kind)] : null], text: (it) => it.title || "",
    after: (it) => h("p", { class: "sp-after", text: sentence(it.why) }),
    detail: (it) => { const b = h("div", { class: "rec" }); for (const a of it.anchors || []) b.append(h("div", { class: "qrow" }, chip(a.status, "anchor-" + a.status, a.status === "unresolved" ? "high" : "plain"), h("span", { class: "qloc num", text: " " + loc(a) }), h("span", { class: "quote", text: a.quote ? "“" + a.quote + "”" : "" }))); return b; } },
  invariant: { meta: (it) => [h("b", { class: "mono", text: it.id }), h("span", { class: "pill " + (it.result === "passed" ? "done" : (it.result.startsWith("failed") ? "high" : "plain")), text: it.result })], text: (it) => it.about,
    after: (it) => ((it.problems || []).length ? h("ul", { class: "plain small" }, it.problems.map((x) => h("li", { text: x }))) : null) },
  condition: { meta: (it) => [h("span", { class: "mono", text: ids(it.ids) })], text: (it) => it.text },
  objective: { meta: (it) => [it.ref ? h("b", { text: it.ref }) : null, chip(words(it.label), "verdict-" + it.label, "plain"), (it.ids || []).join(", ")], text: (it) => it.text || it.ref || "",
    after: (it) => (it.rationale ? h("p", { class: "sp-after", text: it.rationale }) : null) },
  unresolved: { meta: (it) => [h("span", { class: "mono", text: ids(it.rec.finding_ids) })], text: (it) => it.rec.text,
    after: (it) => (it.rec.next_step ? h("p", { class: "sp-after", text: "Next step: " + (it.rec.next_step.owner ? it.rec.next_step.owner + ": " : "") + (it.rec.next_step.action || "") }) : null) },
  limitation: { meta: (it) => [h("span", { class: "mono", text: ids(it.rec.degradation_ids) })], text: (it) => it.rec.text },
  fate: { meta: (it) => [h("b", { class: "mono", text: it.draft_id }), it.shard ? "shard " + words(it.shard) + (it.shard_local_id ? " (its " + it.shard_local_id + ")" : "") : "", sevChip({ kind: it.kind, severity: it.severity }), kindChip(it.kind)],
    text: (it) => it.title,
    after: (it) => h("p", { class: "sp-after" + (it.agrees === false ? " warn" : "") }, h("b", { text: sentence(it.fate) }),
      " · refine: " + it.refine + (it.verify ? " · verify" + (it.merged_into ? " of " + it.merged_into : "") + ": " + it.verify : "") + (it.agrees === false ? " · the manifest's finding_ids.final says " + (it.manifest_final || "nothing") : "")) },
};
ITEM.raw = { meta: () => [], text: (it) => JSON.stringify(it), detail: null };

// The glossary terms an item's chips use (for its list's legend).
function itemTerms(it) {
  const r = it.rec || {};
  const out = [];
  const sevOf = (kind, sev) => (kind === "strength" ? "kind-strength" : (sev ? "sev-" + sev : null));
  if (it.type === "finding") out.push(sevOf(r.kind, r.severity), r.kind && r.kind !== "strength" ? "kind-" + r.kind : null);
  if (["revision", "verified", "fate"].includes(it.type)) out.push(sevOf(it.kind, it.severity), it.kind && it.kind !== "strength" ? "kind-" + it.kind : null);
  if (it.type === "registry") out.push("reg-" + it.rtype);
  if (it.type === "coverage") out.push("crit-" + r.criterion_id, "cov-" + r.outcome);
  if (it.type === "criterion") out.push("crit-" + it.id);
  if (it.type === "anchor") out.push("anchor-" + it.status);
  if (it.type === "objective") out.push("verdict-" + it.label);
  if (it.type === "question" && it.needs_external) out.push("q-external");
  return out.filter(Boolean);
}

function searchText(it) { return JSON.stringify(it).toLowerCase(); }

function itemEl(P, L, it, D) {
  const R = ITEM[it.type] || ITEM.raw;
  const key = L.key + ":" + it.key;
  const el = h("div", { class: "sp-item" + (it.draft ? " is-draft" : "") + (R.cls ? " " + R.cls(it) : ""), "data-key": it.key, "data-type": it.type });
  el.dataset.search = searchText(it);
  const meta = R.meta(it, D, L).flat(Infinity).filter((x) => x !== null && x !== undefined && x !== "").map((x) => (typeof x === "string" ? h("span", { text: x.trim() }) : x)).filter((x) => x.textContent !== "");
  if (meta.length) el.append(h("div", { class: "sp-meta" }, meta));
  const text = R.text(it, D);
  if (R.detail) {
    const open = P.open.has(key), id = "spd-" + (++UID);
    const det = h("div", { class: "sp-detail", id, hidden: !open });
    const btn = h("button", { class: "sp-text sp-toggle", type: "button", "aria-expanded": String(open), "aria-controls": id, title: "Show the whole record" },
      h("span", { class: "chev", "aria-hidden": "true", text: "▸" }), h("span", { class: "sp-tx", text: text || "" }));
    btn.addEventListener("click", () => {
      const on = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(on));
      if (on) { P.open.add(key); if (!det.firstChild) det.append(R.detail(it, D)); } else P.open.delete(key);
      det.hidden = !on;
    });
    if (open) det.append(R.detail(it, D));
    el.append(btn);
    const after = R.after ? R.after(it, D) : null;
    if (after) el.append(after);
    el.append(det);
  } else {
    el.append(h("div", { class: "sp-text" }, h("span", { class: "sp-tx", text: text || "" })));
    const after = R.after ? R.after(it, D) : null;
    if (after) el.append(after);
  }
  return el;
}

// ---------- the findings funnel, across the "Then, in order" block: every merged draft to its fate (GET /runs/<id>/funnel)

async function loadFunnel() {
  const runId = S.runId;
  if (!runId || !$("funnel")) return;
  try { const d = await api("/runs/" + encodeURIComponent(runId) + "/funnel"); if (S.runId === runId) S.funnel = { runId, data: d }; }
  catch (e) { if (S.runId === runId) S.funnel = { runId, data: null, error: e.message }; }
  renderFunnel();
  if (S.panel && S.panel.stage === "funnel" && S.funnel && S.funnel.data) { S.panel.data = S.funnel.data; renderPanel(); }
}

function parts(pairs) { return pairs.filter(([n, , always]) => always || n).map(([n, label]) => intl(n) + " " + label).join(", "); }

// The totals by step, from the rows, and whether they add up and agree with the run's own records.
function funnelChecks(F) {
  const T = F.totals, R = T.refine, V = T.verify, rec = F.recorded || {}, out = [];
  const refineSum = Object.values(R).reduce((a, b) => a + b, 0);
  out.push(refineSum === T.drafts ? { ok: true, text: "Every draft has one fate: " + intl(refineSum) + " of " + intl(T.drafts) + "." }
    : { ok: false, text: "The refine fates cover " + intl(refineSum) + " of the " + intl(T.drafts) + " drafts." });
  const r = rec.refined || {};
  if (typeof r.findings === "number") {
    const unchanged = R["kept as drafted"] + R["not refined (counted as unchanged)"];
    const same = r.revised === R.revised && r.unchanged === unchanged && r.merged === R.merged && r.withdrawn === R.withdrawn && r.findings === T.after_refine;
    out.push({ ok: same, text: "The run's refined record: " + intl(r.revised) + " revised, " + intl(r.unchanged) + " unchanged, " + intl(r.merged) + " merged, " + intl(r.withdrawn) + " withdrawn, " + intl(r.findings) + " findings" + (same ? ", the same." : "; the rows above differ.") });
  }
  const a = rec.anchors_verified || {};
  if (typeof a.findings_verified === "number") out.push({ ok: a.findings_verified === V.verified, text: "Verify recorded " + intl(a.findings_verified) + " verified and " + intl(a.findings_unverified) + " unverified" + (a.findings_verified === V.verified ? ", the same." : "; the rows above differ.") });
  if (typeof T.report_findings === "number") out.push({ ok: T.report_findings === T.reported, text: "report.json holds " + intl(T.report_findings) + " findings" + (T.report_findings === T.reported ? ", the same." : "; the rows above differ.") });
  if ((F.manifest_disagrees || []).length) out.push({ ok: false, text: "The manifest's finding_ids.final disagrees for " + F.manifest_disagrees.join(", ") + "." });
  return out;
}

function funnelSteps(F) {
  const T = F.totals, R = T.refine, V = T.verify;
  const step = (n, label, sub) => h("div", { class: "fstep" }, h("div", { class: "fnum num", text: typeof n === "number" ? intl(n) : "–" }), h("div", { class: "flabel", text: label }), sub ? h("div", { class: "fsub num", text: sub }) : null);
  const arrow = () => h("span", { class: "farrow", "aria-hidden": "true", text: "→" });
  return h("div", { class: "fsteps" },
    step(T.drafts, "merged drafts", "from the assess shards"), arrow(),
    step(T.after_refine, "after refine", parts([[R.revised, "revised", true], [R["kept as drafted"], "kept as drafted"], [R["not refined (counted as unchanged)"], "not refined"], [R.merged, "merged into another", true], [R.withdrawn, "withdrawn", true], [R["not recorded"], "not recorded"]])), arrow(),
    step(T.after_refine === null ? null : V.verified, "verified", parts([[V["moved to unresolved (unverified)"], "moved to unresolved", true], [V["dropped by verify"], "dropped", true], [V.renumbered, "renumbered"], [V["not verified yet"], "not verified yet"]])), arrow(),
    step(T.reported, "reported", "in report.json"));
}

function funnelSummary(F) {
  const box = h("div", { class: "funnel in-panel" });
  if (!F.totals || !F.totals.drafts) return box;
  box.append(funnelSteps(F));
  for (const c of funnelChecks(F)) box.append(h("div", { class: "fcheck" + (c.ok ? "" : " warn"), text: c.text }));
  return box;
}

function renderFunnel() {
  const box = $("funnel");
  if (!box) return;
  const F = S.funnel && S.funnel.runId === S.runId ? S.funnel.data : null;
  box.hidden = !F || !F.totals || !F.totals.drafts;
  clear(box);
  if (box.hidden) return;
  const open = panelOpen("funnel");
  box.append(h("div", { class: "fhead" }, h("h3", {}, "The findings, from drafts to the report"),
    h("button", { class: "why-btn funnel-open", type: "button", "data-panel": "funnel", "aria-controls": "stage-panel", "aria-expanded": String(open), text: open ? "Close the trace" : "Trace every finding",
      onclick: () => togglePanel(S.model, "funnel") })));
  box.append(funnelSteps(F));
  const checks = funnelChecks(F), bad = checks.filter((c) => !c.ok);
  box.append(h("div", { class: "fcheck" + (bad.length ? " warn" : "") }, bad.length ? bad.map((c) => c.text).join(" ") : "Adds up: every draft has one fate, and the counts match the run's refined and verify records and report.json."));
}

function stage1Summary(m, shards) {
  const st = (k) => track(m, k).status;
  const parts = [];
  const done = ["understand", "plan"].filter((k) => st(k) === "done");
  if (done.length) parts.push(done.join(" and ") + " done");
  if (st("research") === "skipped") parts.push("research skipped");
  const open = shards.filter((k) => ["running", "replayed"].includes(st(k))).length;
  if (shards.length) parts.push(open ? intl(open) + " of " + intl(shards.length) + " assess shards open" : (shards.every((k) => ["done", "cut", "failed"].includes(st(k))) ? "assess done" : null));
  return parts.filter(Boolean).join(", ");
}

function renderRun(m) {
  const lim = m.limits || {};
  const s1 = clear($("stage1-tracks"));
  const keys = [...m.tracks.keys()];
  const shards = keys.filter((k) => k.startsWith("assess ")).sort((a, b) => parseInt(a.slice(7), 10) - parseInt(b.slice(7), 10));
  const order = [...STAGE1, ...(shards.length ? shards : ["assess"])];
  for (const k of order) {
    const t = track(m, k);
    s1.append(trackRow(m, t, lim.stage_1_end ?? null));
    const why = whyBlock(m, k, entryOf(k)); if (why) s1.append(why);
  }
  const summary = stage1Summary(m, shards);
  $("stage1-limit").textContent = (lim.stage_1_end !== undefined ? "ends by " + clock(lim.stage_1_end) : "") + (summary ? " · " + summary : "");
  const dis = clear($("stage1-disclosures"));
  for (const k of order) {
    const t = track(m, k);
    if (t.disclose) dis.append(h("div", { class: "disclose", "data-track": k }, h("span", { class: "k" }, "disclosed in the report as ", h("b", { text: t.disclose.id })), h("span", { text: t.disclose.text })));
  }
  const seq = clear($("seq-tracks"));
  for (const row of SEQ) {
    const t = track(m, row.phase);
    const limit = row.limit === "deadline" ? m.deadline : (row.limit ? lim[row.limit] : null);
    if (t.status === "waiting" && row.when) {
      seq.append(h("div", { class: "track" + (panelOpen(row.phase) ? " open" : ""), "data-track": row.phase, "data-status": "waiting" }, h("div", { class: "name" }, nameButton(m, row.phase, row.phase, 0)), h("div", {}, h("span", { class: "pill waiting", text: "waiting" })),
        h("div", { class: "time num muted", text: row.when }), h("div", { class: "status", text: row.about }), whyButton(m, row.phase, entryOf(row.phase))));
    } else {
      const r = trackRow(m, t, limit ?? null);
      if (t.status === "waiting") r.querySelector(".status").textContent = row.about;
      seq.append(r);
    }
    const why = whyBlock(m, row.phase, entryOf(row.phase)); if (why) seq.append(why);
  }
  const axisWhy = $("axis-why");
  if (axisWhy) {
    const open = m.why.has("limits");
    axisWhy.setAttribute("aria-expanded", String(open));
    axisWhy.onclick = () => { if (m.why.has("limits")) m.why.delete("limits"); else m.why.add("limits"); renderRun(m); };
    const box = clear($("axis-why-text"));
    if (open) box.append(h("div", { class: "why", "data-why": "limits" }, explainEntry(m, "limits")));
  }
  renderExplain(m);
  const stop = $("stop-rule");
  if (stop) { stop.hidden = !m.stopRule; stop.textContent = m.stopRule ? "Stop rule " + m.stopRule.code + " fired in " + words(m.stopRule.stage) + ": " + m.stopRule.detail + "; skipped to " + words(m.stopRule.to) + "." : ""; }
  renderAxis(m);
  const notes = clear($("limit-notes"));
  for (const n of m.limitNotes) notes.append(h("div", { class: "limit-note" }, h("span", { class: "num mono", text: clock(n.t) }), h("span", { text: n.text })));
  $("draft-count").textContent = String(m.drafts.length);
  const d = clear($("drafts"));
  for (const x of m.drafts) {
    const sev = x.kind === "strength" ? "strength" : (x.severity || "");
    d.append(h("div", { class: "draft" }, h("div", { class: "t num mono", text: clock(x.t) }),
      h("div", { class: "line" }, sev ? chip(sev, sev === "strength" ? "kind-strength" : "sev-" + sev, sev) : null, h("span", { class: "text", text: x.title || "" }),
        x.who.includes("/") ? chip(x.who, "run-shard", "who mono") : h("span", { class: "who mono", text: x.who }))));
  }
  renderPanelFrame(m);
  const feed = clear($("status-feed"));
  for (const ev of [...m.events].reverse()) {
    const marker = { step: "", wait: "... ", warn: "WARN ", done: "OK ", draft: "DRAFT " }[ev.kind] || "";
    const msg = h("div", { class: "msg", text: marker + ev.message }); msg.title = msg.textContent;
    feed.append(h("div", { class: "row" + (ev.kind === "warn" ? " warn" : "") }, h("div", { class: "num mono", text: clock(ev.t) }), h("div", { class: "ph", text: ev.phase }), msg));
  }
}

function closeStream() { stopTick(); if (S.es) { S.es.close(); S.es = null; } }

// ------------------------------------------------------------------ the head clock, the axis and the tick
// A run is live while its stream is open and it is neither a replay nor ended. Only then does the head clock add the
// seconds since the last event arrived, counted on this browser's clock; every other time on the page is the record's.

function isLive(m) { return S.es !== null && !m.replay && !m.finished && !m.error; }
function liveT(m) {
  const since = isLive(m) && S.lastAt !== null ? (Date.now() - S.lastAt) / 1000 : 0;
  return m.lastT + since;
}
function startTick() { stopTick(); S.tick = setInterval(tick, 1000); }
function stopTick() { if (S.tick !== null) { clearInterval(S.tick); S.tick = null; } }
function tick() {
  const m = S.model;
  if (!m || !isLive(m)) { stopTick(); return; }
  renderClock(m, S.info || {});
  renderAxis(m);
  pollLog();
}

function renderClock(m, info) {
  const meta = clear($("top-meta"));
  const live = isLive(m);
  meta.append(h("div", { class: "t" }, h("b", { text: clock(liveT(m)) }), m.deadline ? h("span", { text: " / " + clock(m.deadline) }) : null));
  const l = h("div", { class: "l" });
  if (live) l.append(h("span", { id: "clock-label" }, "run clock: last event at ", h("b", { class: "num", id: "clock-last", text: clock(m.lastT) }), ", plus the seconds since it arrived (this browser's clock)"));
  else l.append(h("span", { id: "clock-label", text: "run clock, as of the last event" }));
  if (m.resumed || info.resumed) l.append(h("span", { class: "pill", text: "resumed" }));
  if (info.replayed || m.replay) l.append(h("span", { class: "pill replayed", id: "replay-stamp", text: "replayed evidence" }));
  meta.append(l);
}

// The recorded limits as markers on one axis from the start to the deadline (run_started: stage_limits_s, deadline_s).
function limitMarks(m) {
  const lim = m.limits || {};
  return [["stage 1 ends", lim.stage_1_end], ["refine ends", lim.refine_end], ["verdict ends", lim.verdict_end], ["deadline", m.deadline]].filter(([, s]) => typeof s === "number");
}

function renderAxis(m) {
  const box = $("run-axis");
  if (!box) return;
  const marks = limitMarks(m);
  const span = typeof m.deadline === "number" ? m.deadline : (marks.length ? marks[marks.length - 1][1] : null);
  box.hidden = span === null;
  if (span === null) return;
  const pct = (s) => Math.min(100, (100 * s) / span).toFixed(1) + "%";
  const now = liveT(m), live = isLive(m);
  const line = clear($("axis-line")), labels = clear($("axis-labels"));
  line.append(h("i", { class: "fill" + (live ? "" : " closed"), style: "width:" + pct(now) }));
  for (const [name, s] of marks) {
    const passed = now >= s;
    line.append(h("i", { class: "mark" + (passed ? " passed" : ""), style: "left:" + pct(s), title: name + " " + clock(s) }));
    labels.append(h("span", { class: "lbl num" + (passed ? " passed" : "") + (s === span ? " end" : ""), style: "left:" + pct(s) }, name + " ", h("b", { text: clock(s) })));
  }
  line.append(h("i", { class: "cursor" + (live ? " live" : ""), style: "left:" + pct(now), title: clock(now) }));
  // Two limits close together (verdict and the deadline) would overlap: a label that would step on the one before
  // it on its row goes down a row. Measured once per render from the laid-out boxes, no timer involved.
  const rights = [], edge = labels.getBoundingClientRect().right;
  for (const el of labels.children) {
    let r = el.getBoundingClientRect();
    if (r.right > edge) { el.classList.add("end"); r = el.getBoundingClientRect(); }   // anchored to its right at the axis's end
    let row = rights.findIndex((right) => r.left > right);
    if (row < 0) row = rights.length;
    rights[row] = r.right;
    el.dataset.row = String(row);
  }
  labels.dataset.rows = String(rights.length);
  const next = marks.find(([, s]) => s > now);
  $("axis-note").textContent = (live ? "elapsed " : (m.finished || m.error ? "ended at " : "last event at ")) + clock(live ? now : m.lastT) + " of " + clock(span) +
    (live && next ? " · next limit: " + next[0] + " " + clock(next[1]) : "") + (live ? " · the cursor adds the seconds since the last event; the markers are the record's limits" : "");
}

function renderTabs(tabs, note) {
  const t = clear($("top-tabs"));
  // A tab with ``off`` is drawn disabled (aria-disabled, class ``off``) but still opens, so its reason can be read.
  for (const tab of tabs || []) t.append(h("button", { class: "tab" + (tab.on ? " on" : "") + (tab.off ? " off" : ""), type: "button", "aria-disabled": tab.off ? "true" : null, title: tab.title || null, onclick: tab.go, text: tab.label }));
  const n = $("tab-note");
  if (n) n.textContent = note || "";
}

function runTop(info, m, tabs) {
  const doc = m.doc;
  $("top-doc").textContent = (doc && doc.title) || info.document || info.run_id;
  const sub = clear($("top-sub"));
  const bits = [h("b", { text: info.run_id })];
  const about = doc ? [doc.version ? String(doc.version).toLowerCase() : null, typeof doc.pages === "number" ? intl(doc.pages) + " pages" : null, typeof doc.sections === "number" ? intl(doc.sections) + " sections" : null].filter(Boolean).join(", ") : (typeof info.pages === "number" ? intl(info.pages) + " pages" : null);
  if (about) bits.push(about);
  if (m.profile || info.profile) bits.push("profile " + (m.profile || info.profile));
  if (info.no_tools) bits.push(h("span", {}, "document only (", h("span", { class: "mono", text: "--no-tools" }), ")"));
  if (info.started_at) bits.push("started " + hhmm(info.started_at));
  bits.forEach((b, i) => { if (i) sub.append(" · "); sub.append(b); });
  renderClock(m, info);
  const a = clear($("top-action"));
  if (info.status === "running" && info.argv && !m.replay) renderStop(a, info);
  $("run-tabrow").hidden = !tabs || !tabs.length;
  renderTabs(tabs);
  renderRailRuns();
}

// What Stop does, from the code (ui/launcher.py Launcher.stop, cli.py _guarded, orchestrator.py: the interrupt flushes
// state.json and raises RunInterrupted; a report is written only by a completed run, a partial one only by a stage
// crash; cli.py _resolve_run_dir takes a run ID under the run root). The exit code comes from GET /meta.
function stopSentence(info) {
  return ["Stop sends SIGINT to the dra review process, as Ctrl-C in its terminal does: the run ends with exit " + S.meta.stop_exit_code +
    ", the state of the last completed phase is kept in state.json, no report is written, and ",
    h("span", { class: "mono", text: "dra resume " + info.run_id }), " continues it from there."];
}

// Two clicks send the signal: the first arms the button (Confirm stop, with Keep running beside it), the second posts.
function renderStop(box, info) {
  const st = S.stop || (S.stop = { armed: false, text: null, busy: false });
  const stop = h("button", { class: "btn quiet" + (st.armed ? " armed" : ""), type: "button", id: "stop-btn", disabled: st.busy || st.text !== null,
    text: st.text || (st.armed ? "Confirm stop" : "Stop run") });
  const keep = h("button", { class: "btn ghost", type: "button", id: "stop-keep", text: "Keep running", hidden: !st.armed || st.busy || st.text !== null });
  const paint = () => renderStop(clear(box), info);
  stop.addEventListener("click", async () => {
    if (!st.armed) { st.armed = true; paint(); return; }
    st.busy = true; paint();
    try { await api("/runs/" + encodeURIComponent(info.run_id) + "/stop", { method: "POST" }); st.text = "SIGINT sent"; }
    catch (err) { st.text = err.message; }
    st.busy = false; paint();
  });
  keep.addEventListener("click", () => { st.armed = false; paint(); });
  box.append(h("div", { class: "row" }, keep, stop), h("div", { class: "note", id: "stop-note" }, stopSentence(info)));
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

// A run that ended before its first event: the process's own words from ui/console.txt (rundata.console_tail), shown
// as they were printed, with the command that started it. Usually a usage error such as a missing key.
function consoleBlock(info) {
  const c = info.console;
  const code = info.exit_code !== null && info.exit_code !== undefined ? ", exit " + info.exit_code : "";
  return h("div", { class: "console-box", id: "run-console" },
    h("div", { class: "console-head" }, h("b", { text: "The process ended before its first event" + code + "." }),
      " What it printed, from ", h("span", { class: "mono", text: "runs/" + info.run_id + "/" + c.file }), c.truncated ? " (the end of it)" : "", ":"),
    h("pre", { class: "console-text", text: c.lines.join("\n") || "(nothing)" }));
}

function showRun(info, tabs) {
  closeStream();
  const app = clear($("app"));
  app.className = "surface wide";
  app.append(tpl("tpl-run"));
  S.panel = null;
  if (S.funnel && S.funnel.runId !== info.run_id) S.funnel = null;
  const m = newRunModel();
  m.noTools = typeof info.no_tools === "boolean" ? info.no_tools : null;
  S.model = m;
  S.stop = null;
  S.lastAt = null;
  renderRun(m);
  runTop(info, m, tabs);
  renderRailTools();
  $("sp-close").addEventListener("click", () => closePanel(m));
  $("stage-panel").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); closePanel(m); } });
  if (info.argv) $("legend").after(h("div", { class: "cmd", id: "run-cmd", text: info.argv }));
  // A run just started has no progress.jsonl until the child's first event: the stream is opened anyway and
  // the server follows the file from the moment it appears. Only a run that ended without one has no timeline.
  if (!info.has_events && info.status !== "running") {
    $("finished-bar").after(info.console ? consoleBlock(info) : h("p", { class: "notice", text: info.launched_here
      ? "This run wrote no progress.jsonl and no console output, so there is no timeline to show."
      : "This run directory has no progress.jsonl (it was recorded before the structured event stream), so there is no timeline to show." }));
    // Nothing will arrive, so no empty stage rows, "first records fill this in" or 00:00 head clock are drawn.
    app.querySelector(".run-wrap").hidden = true;
    $("top-meta").hidden = true;
    return;
  }
  const es = new EventSource("/runs/" + encodeURIComponent(info.run_id) + "/events");
  S.es = es;
  if (info.status === "running" && !info.replayed) startTick();
  let pending = false;
  // A record that ends a stage (or a shard) means its file may now be written: the open panel and the funnel are read
  // again, once per repaint, so a run in progress fills them in as it goes.
  const paint = () => { pending = false; renderRun(m); runTop(info, m, tabs); if (S.stale) { S.stale = false; loadPanel(); if (m.x.merged) loadFunnel(); } };
  es.addEventListener("progress", (e) => {
    const ev = JSON.parse(e.data);
    S.lastAt = Date.now();
    applyEvent(m, ev);
    if (STAGE_ENDS.includes(ev.type)) S.stale = true;
    if (!pending) { pending = true; requestAnimationFrame(paint); }
    // The other rail rows are re-read at the open run's status cadence (one call_status record per tick),
    // never on a browser timer.
    if (ev.type === "call_status") refreshRuns().catch(() => {});
  });
  es.addEventListener("end", async (e) => {
    stopTick(); es.close(); S.es = null;
    pollLog();
    loadPanel();
    loadFunnel();
    const end = JSON.parse(e.data || "{}");
    const fresh = await api("/runs/" + encodeURIComponent(info.run_id));
    info.status = fresh.status;
    S.info = fresh;
    paint();
    await refreshRuns();
    const bar = $("finished-bar");
    if (!bar) return;
    clear(bar).hidden = false;
    bar.append(finishedText(m, end));
    if (fresh.console && !$("run-console")) { $("finished-bar").after(consoleBlock(fresh)); if (!fresh.has_events) app.querySelector(".run-wrap").hidden = true; }
    if (fresh.has_report && !tabs) bar.append(h("button", { class: "btn primary", type: "button", text: "Open the review", onclick: () => go(info.run_id) }));
  });
}

// ------------------------------------------------------------------ the three outputs: download, email, share

// One plain address, the same rule as ui/mail.py ADDRESS_RE; the server checks it again.
const ADDRESS = /^[^\s@,;<>"]+@[^\s@,;<>"]+\.[^\s@,;<>"]+$/;

function disclosure(btn, box, onOpen) {
  btn.addEventListener("click", () => {
    const open = box.hidden;
    box.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open && onOpen) onOpen();
  });
}

async function setupOutputs(info) {
  const base = "/runs/" + encodeURIComponent(info.run_id);
  const out = await api(base + "/outputs");
  $("out-download").href = base + "/export.html?download=1";
  $("out-open").href = base + "/export.html";
  $("out-md").href = base + "/report.md";
  $("out-json").href = base + "/report.json";
  $("out-download-label").textContent = "Download review (zip" + (out.export ? ", " + out.export.size : "") + ")";
  $("out-download-help").textContent = "A zip of one cross-linked review page with a sidebar, whose one script only shows and " +
    "hides sections and previews links, the reviewed PDF its page references open, report.md and report.json, nothing " +
    "loaded from the network" +
    (info.replayed ? ", stamped replayed evidence" : "") +
    (out.export && out.export.has_chat ? ", the chat transcript after the review, marked as not part of it." : ".");
  $("out-line").hidden = false;
  const to = $("email-to"), send = $("email-send"), help = $("email-help"), result = $("email-result");
  const e = out.email;
  const ready = () => { send.disabled = !e.enabled || !ADDRESS.test(to.value.trim()); };
  if (e.enabled) {
    help.textContent = "Sends the HTML file and report.md as attachments from this laptop through " + e.host + ", from " + e.from + ". Logged to " + info.run_id + "/ui/outbox.jsonl without the content.";
  } else {
    to.disabled = true;
    send.title = e.reason;
    $("email-btn").title = e.reason;
    help.textContent = e.reason + " (" + e.detail + ").";
  }
  ready();
  disclosure($("email-btn"), $("email-box"), () => { if (!to.disabled) to.focus(); });
  to.addEventListener("input", () => { ready(); result.hidden = true; help.hidden = false; });
  $("email-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (send.disabled) return;
    send.disabled = true; to.disabled = true;
    help.hidden = true;
    result.hidden = false; result.className = ""; result.textContent = "Sending to " + to.value.trim() + "…";
    try {
      const r = await api(base + "/email", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ to: to.value.trim() }) });
      result.className = "ok"; result.textContent = "Sent to " + r.to + " at " + (r.at || "").slice(11, 16) + " UTC.";
    } catch (err) {
      result.className = "bad"; result.textContent = err.message;
    }
    to.disabled = false; ready();
  });
  const s = out.share;
  disclosure($("share-btn"), $("share-box"));
  $("share-line").textContent = s.url || s.restart || "";
  $("share-line").hidden = !(s.url || s.restart);
  $("share-text").textContent = s.text;
  $("outputs").hidden = false;
}

// ------------------------------------------------------------------ the review

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
    h("span", { class: "conf num", text: "confidence " + conf(v.confidence) + (D.verdict_band ? ", " + D.verdict_band : "") + ((v.conditions || []).length ? " · " + intl(v.conditions.length) + " condition" + (v.conditions.length === 1 ? "" : "s") : "") }));
  if (D.previous_verdict) vline.append(h("span", { class: "prev num", text: "previous version (" + D.previous_verdict.run_id + "): " + words(D.previous_verdict.label) + " · " + conf(D.previous_verdict.confidence) }));
  box.append(vline);
  const c = D.counts;
  const cs = h("div", { class: "counts num" });
  for (const [n, label] of [[c.findings, "findings"], [c.critical, "critical"], [c.high, "high"], [c.medium, "medium"], [c.low, "low"], [c.strengths, "strengths"], [c.sound_areas, "areas checked, no issue"], [c.unresolved, "unresolved"], [c.limitations, "limitations"]]) {
    cs.append(h("span", {}, h("b", { text: n }), " " + label));
  }
  box.append(cs, h("p", { class: "rationale", text: v.rationale || "" }));
  if ((v.conditions || []).length) {
    box.append(h("h3", { text: "Conditions" }), h("ul", { class: "plain small" }, v.conditions.map((x) => h("li", {}, x.text + ((x.finding_ids || []).length ? " (" + x.finding_ids.join(", ") + ")" : "")))));
  }
  if (v.what_would_change_it) box.append(h("p", { class: "rationale muted" }, h("b", { style: "font-weight:500;color:var(--fg)", text: "What would change it." }), " " + v.what_would_change_it));
  if ((v.per_objective || []).length) {
    // The objective's own text, as intent_summary.objectives records it under the same ref; the ref alone otherwise.
    const texts = new Map((((R.intent_summary || {}).objectives) || []).map((o) => [o.ref, o.text]));
    box.append(h("table", { class: "grid obj", style: "margin:18px 0 0" },
      h("thead", {}, h("tr", {}, h("th", { text: "Objective" }), h("th", { text: "Verdict" }), h("th", { text: "Findings" }))),
      h("tbody", {}, v.per_objective.map((o) => h("tr", {}, h("td", { class: "obj", title: texts.get(o.objective_ref) || o.objective_ref }, h("b", { style: "font-weight:500", text: o.objective_ref }), texts.has(o.objective_ref) ? " " + texts.get(o.objective_ref) : ""), h("td", { text: words(o.label) }), h("td", { class: "ids", text: (o.finding_ids || []).join(", ") || "–" }))))));
  }
  const all = [...(R.findings || [])].sort((a, b) => a.rank - b.rank);
  const issues = all.filter((f) => f.kind !== "strength"), strengths = all.filter((f) => f.kind === "strength");
  box.append(h("div", { class: "sec" }, h("h2", {}, "Findings ", h("span", { class: "n num", text: issues.length + " issues, ordered by rank" })), findingList(P, issues)));
  if (strengths.length) box.append(h("div", { class: "sec" }, h("h2", {}, "Strengths ", h("span", { class: "n num", text: String(strengths.length) })), findingList(P, strengths)));
  if ((R.sound_areas || []).length) {
    box.append(h("div", { class: "sec" }, h("h2", {}, "Checked, no issue ", h("span", { class: "n num", text: String(R.sound_areas.length) })),
      h("ul", { class: "plain small" }, R.sound_areas.map((s) => h("li", {}, h("b", { style: "font-weight:500", text: s.id }), " " + (s.section_refs || []).map((x) => "§" + x).join(", ") + " · " + s.why_sound)))));
  }
  box.append(h("div", { class: "sec two" },
    h("div", {}, h("h2", {}, "Unresolved issues ", h("span", { class: "n num", text: String((R.unresolved || []).length) + ((R.unresolved || []).every((u) => u.next_step) && (R.unresolved || []).length ? ", each with an owner" : "") })),
      h("ul", { class: "plain small" }, (R.unresolved || []).map((u) => h("li", {}, idsNotIn(u.finding_ids, u.text), u.text + (u.next_step ? " · " + u.next_step.owner + ": " + u.next_step.action : ""))))),
    h("div", {}, h("h2", {}, "Evidence limitations ", h("span", { class: "n num", text: String((R.limitations || []).length) })),
      h("ul", { class: "plain small" }, (R.limitations || []).map((l) => h("li", {}, idsNotIn(l.degradation_ids, l.text), l.text))))));
  return box;
}

// The Delta tab (design note section 7), keyed on the prior review's IDs: one row per prior finding with
// its status, this review's ID(s) and the re-assessment note, then the findings new in the update, a
// regression marked. Rows come from ui/rundata.delta_view; a run with no previous version never gets here.
const DELTA_COLS = ["prior", "now", "status", "title", "note"];

function deltaStatus(r) {
  if (r.status === "new_in_update") return r.regression ? "new (regression)" : "new";
  const st = r.status === "withdrawn_on_reassessment" ? "withdrawn on re-assessment" : words(r.status);
  return st + (r.re_examined ? "" : ", not re-examined");
}

function deltaBody(P) {
  const D = P.derived.delta;
  const byId = new Map((P.report.findings || []).map((f) => [f.id, f]));
  const box = h("div", {});
  if (P.derived.previous_verdict) box.append(h("p", { class: "small muted", text: "Previous version (" + P.derived.previous_verdict.run_id + "): " + words(P.derived.previous_verdict.label) + " · " + conf(P.derived.previous_verdict.confidence) + "; this version: " + words(P.report.verdict.label) + " · " + conf(P.report.verdict.confidence) }));
  if (D.table) {
    box.append(h("p", { class: "small delta-sum", text: D.prior_count + " prior findings, each with one status" + (D.not_re_examined ? "; " + D.not_re_examined + " recorded as still open because they were not re-examined" : "") + (D.regressions ? "; " + D.regressions + " new finding(s) in a changed section (regression)" : "") + ". Prior IDs are the prior review's own numbering." }));
  } else {
    box.append(h("p", { class: "small muted delta-notice", text: D.notice }));
  }
  for (const g of D.groups) {
    if (!g.rows.length) continue;
    const body = h("tbody", {});
    for (const r of g.rows) {
      const f = byId.get((r.finding_ids || [])[0]);
      const tr = h("tr", { class: "drow" + (f ? " link" : "") },
        h("td", { class: r.prior_id ? "mono" : "muted", text: r.prior_id || "new" }),
        h("td", { class: (r.finding_ids || []).length ? "mono" : "muted", text: (r.finding_ids || []).join(", ") || "none" }),
        h("td", { text: deltaStatus(r) }),
        h("td", { text: r.title || "" }),
        h("td", { class: "muted", text: r.note || "" }));
      if (f) {
        let box2 = null;
        tr.setAttribute("aria-expanded", "false");
        tr.addEventListener("click", () => {
          if (box2) { box2.remove(); box2 = null; tr.setAttribute("aria-expanded", "false"); return; }
          box2 = h("tr", { class: "ddetail" }, h("td", { colspan: String(DELTA_COLS.length) }, expanded(P, f)));
          tr.after(box2); tr.setAttribute("aria-expanded", "true");
        });
      }
      body.append(tr);
    }
    box.append(h("div", { class: "sec" }, h("h2", {}, g.heading + " ", h("span", { class: "n num", text: String(g.rows.length) })),
      h("table", { class: "grid delta" }, h("colgroup", {}, DELTA_COLS.map((c) => h("col", { class: "c-" + c }))),
        h("thead", {}, h("tr", {}, h("th", { text: "Prior ID" }), h("th", { text: "This review" }), h("th", { text: "Status" }), h("th", { text: "Title" }), h("th", { text: "Re-assessment note" }))), body)));
  }
  return box;
}

function deltaOff(P) {
  return h("div", {}, h("p", { class: "delta-off muted", text: P.derived.delta.reason + "." }));
}

async function coverageBody(runId) {
  const cm = await api("/runs/" + encodeURIComponent(runId) + "/coverage");
  const box = h("div", { class: "sec" }, h("h2", { text: "Coverage: criteria by section" }));
  const head = h("tr", {}, h("th", { text: "Section" }), cm.criteria.map((c) => h("th", { class: "mono", text: c })));
  const body = h("tbody", {}, cm.rows.map((r) => h("tr", {}, h("td", {}, h("b", { style: "font-weight:500", text: r.section }), " " + (r.heading || "")), cm.criteria.map((c) => h("td", { class: "mono", text: (r.cells || {})[c] || "" })))));
  box.append(h("table", { class: "grid", style: "margin-top:8px" }, h("thead", {}, head), body));
  box.append(h("h3", { text: "Outcome per criterion" }), h("ul", { class: "plain small" }, cm.criteria.map((c) => h("li", {}, h("span", { class: "mono", text: c }), " " + words(cm.outcomes[c]) + ((cm.criterion_findings[c] || []).length ? ": " + cm.criterion_findings[c].join(", ") : "") + (cm.notes[c] ? " · " + cm.notes[c] : "")))));
  return box;
}

function evidenceBody(P) {
  const led = P.report.evidence_ledger || [];
  return h("div", { class: "sec" }, h("h2", {}, "Evidence register ", h("span", { class: "n num", text: String(led.length) })),
    h("table", { class: "grid", style: "margin-top:8px" }, h("thead", {}, h("tr", {}, h("th", { text: "ID" }), h("th", { text: "Source" }), h("th", { text: "Citation" }), h("th", { text: "Excerpt" }))),
      h("tbody", {}, led.map((e) => h("tr", {}, h("td", { text: e.evidence_id }), h("td", { text: words(e.source_type) + (e.authority ? " (" + e.authority + ")" : "") }),
        h("td", { text: e.url_or_citation }), h("td", { text: (e.excerpt || "") + ((e.derived_from || []).length ? " (derived from " + e.derived_from.join(", ") + ")" : "") }))))));
}

const NO_DELTA = "No previous version was given for this run";

async function showReview(info, tab) {
  closeStream();
  S.model = null;
  const P = await api("/runs/" + encodeURIComponent(info.run_id) + "/report");
  const R = P.report;
  const doc = (R.metadata.documents || []).find((d) => d.role === "under_review") || (R.metadata.documents || [])[0] || {};
  // The Delta tab is always drawn: live when the server's delta view is available, else shown disabled with
  // its reason (no silent absence); it still opens, so the reason can be read on the tab itself.
  const D = P.derived.delta || {};
  const deltaOn = !!D.available;
  const deltaReason = deltaOn ? null : (D.reason || NO_DELTA);
  const tabs = [{ key: "review", label: "Review" }, { key: "delta", label: "Delta", off: !deltaOn, title: deltaReason }];
  tabs.push({ key: "coverage", label: "Coverage" }, { key: "evidence", label: "Evidence" });
  if (info.has_events) tabs.push({ key: "log", label: "Run log" });
  const current = tabs.some((t) => t.key === tab) ? tab : "review";
  const tabList = tabs.map((t) => ({ label: t.label, on: t.key === current, off: t.off, title: t.title, go: () => go(info.run_id, t.key) }));
  if (current === "log") { showRun(info, tabList); return; }
  const app = clear($("app"));
  app.className = "surface wide";
  app.append(tpl("tpl-review"));
  const s = P.summary;
  $("top-doc").textContent = doc.title || info.run_id;
  const sub = clear($("top-sub"));
  const bits = [h("b", { text: info.run_id })];
  const about = [doc.version ? String(doc.version).toLowerCase() : null, doc.page_count !== undefined ? intl(doc.page_count) + " pages" : null].filter(Boolean).join(", ");
  if (about) bits.push(about);
  if (s.outcome) bits.push(words(s.outcome));
  if (s.wall_s !== null) bits.push(dur(s.wall_s));
  if (s.cost_usd !== null) bits.push(money(s.cost_usd, s.cost_lower_bound));
  if (typeof s.model_calls === "number") bits.push(intl(s.model_calls) + " model call" + (s.model_calls === 1 ? "" : "s"));
  if (s.commit) bits.push(String(s.commit).slice(0, 7));
  if (s.replayed) bits.push(h("span", { class: "pill replayed", id: "replay-stamp", text: "replayed evidence" }));
  bits.forEach((b, i) => { if (i) sub.append(" · "); sub.append(b); });
  renderTabs(tabList, deltaOn ? "" : "Delta is off: " + deltaReason.charAt(0).toLowerCase() + deltaReason.slice(1) + ".");
  const main = $("review");
  if (current === "review") main.append(reviewBody(P));
  else if (current === "delta") main.append(deltaOn ? deltaBody(P) : deltaOff(P));
  else if (current === "coverage") main.append(await coverageBody(info.run_id));
  else if (current === "evidence") main.append(evidenceBody(P));
  renderRailRuns();
  renderRailTools();
  await setupOutputs(info);
  await setupChat(info);
}

// ------------------------------------------------------------------ the ask: a reading aid, not the review

function budgetLine(b) {
  return b.calls_used + " of " + b.max_calls + " calls used · " + money(b.cost_usd) + " of " + money(b.max_cost_usd) + (b.calls_with_unknown_cost ? " (" + b.calls_with_unknown_cost + " call(s) with unknown cost)" : "") + " · " + b.model + ", effort " + b.effort + " · logged to " + b.log + " · outside the evaluated agent and its manifest";
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
  const cap = S.meta.chat;
  $("chat-hint").textContent = "Trimmed to this review · " + intl(cap.max_calls) + " asks or " + money(cap.max_cost_usd) + " per run";
  const input = $("chat-input"), send = $("chat-send"), err = $("chat-error"), ready = $("chat-ready");
  const setBudget = (b, running, hasReport) => {
    $("chat-budget").textContent = budgetLine(b);
    const off = running ? "The chat is off while the run is in progress." : (!hasReport ? "This run has no report.json, so there is nothing to ask about." : (b.stopped ? "The chat cap for this run is reached." : null));
    input.disabled = !!off; send.disabled = !!off;
    ready.classList.toggle("off", !!off);
    ready.textContent = off ? (running ? "Off while the run is in progress" : (b.stopped ? "Cap reached" : "No report to ask")) : "Grounded in this review";
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
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
}

// ------------------------------------------------------------------ routing

function go(runId, tab) {
  const u = runId ? "/?run=" + encodeURIComponent(runId) + (tab ? "&tab=" + tab : "") : "/";
  history.pushState(null, "", u);
  route();
}

function goPage(page) {
  history.pushState(null, "", page === "review" ? "/" : "/?page=" + page);
  route();
}

async function route() {
  const q = new URLSearchParams(location.search);
  const runId = q.get("run");
  const page = runId ? "runs" : (PAGES.includes(q.get("page")) ? q.get("page") : "review");
  S.runId = runId;
  S.page = page;
  railActive(page);
  try {
    if (!S.meta) { S.meta = await api("/meta"); renderTopbar(); setupRail(); }
    await refreshRuns();
    // The tools dots are GET /tools, a read of recorded files: the page never probes a server on load.
    if (!S.tools) await refreshTools(); else renderRailTools();
    if (runId) {
      const info = await api("/runs/" + encodeURIComponent(runId));
      S.info = info;
      if (!S.log || S.log.runId !== runId) openLog(runId);
      if (info.status === "running" || !info.has_report) showRun(info, null);
      else await showReview(info, q.get("tab"));
      renderRailTools();
      return;
    }
    S.info = null;
    closeStream();
    S.model = null;
    openLog(null);
    if (page === "review") await showDrop();
    else if (page === "runs") showRuns();
    else if (page === "replay") showReplay();
    else if (page === "tools") await showTools();
    else if (page === "settings") showSettings();
    else if (page === "developer") showDeveloper();
    renderRailRuns();
  } catch (e) {
    closeStream();
    const app = clear($("app"));
    app.className = "surface";
    app.append(h("div", { style: "padding:48px 0" }, h("p", { class: "error", text: e.message }), h("a", { href: "/", text: "Back to the Review page", onclick: (ev) => { ev.preventDefault(); goPage("review"); } })));
  }
}

// The run model and its reducer, reachable by tests that feed a recorded stream through the page.
window.SIT = { applyEvent, newRunModel, state: S, explainKeys, explainText, facts: Object.keys(FACTS), factText, explain: EXPLAIN, stageOf };
window.addEventListener("popstate", route);
route();
