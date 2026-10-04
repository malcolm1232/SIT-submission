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
  lastAt: null, tick: null };
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
  const box = clear($("rail-runs"));
  const running = S.runs.filter((r) => r.status === "running").length;
  $("rail-runs-note").textContent = running ? intl(running) + " running" : "none running";
  if (!S.runs.length) box.append(h("div", { class: "rail-empty", text: "no run directory yet" }));
  for (const r of S.runs) {
    const dot = r.status === "running" ? "live" : (r.verdict ? "done" : "ended");
    box.append(h("a", { class: "rail-run" + (r.run_id === S.runId ? " active" : ""), href: "/?run=" + encodeURIComponent(r.run_id), "data-run": r.run_id, title: r.document || r.run_id,
      onclick: (e) => { e.preventDefault(); go(r.run_id); } },
      h("span", { class: "dot " + dot }), h("span", { class: "title", text: r.run_id }), h("span", { class: "meta num" }, runMetaText(r))));
  }
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
  const refresh = () => {
    const p = meta.profiles.find((x) => x.name === sel.value);
    $("profile-help").textContent = p ? "Stage 1 ends by " + clock(p.stage_limits_s.stage_1_end) + ", refine by " + clock(p.stage_limits_s.refine_end) + ", verdict by " + clock(p.stage_limits_s.verdict_end) + ", deadline " + clock(p.deadline_s) + "." : "";
    const prev = $("prev-input").files[0];
    const rid = $("run-id").value.trim() || "<new run>";
    const source = doc ? doc.name : (link() ? linkName(link()) : null);
    const parts = ["dra", "review", source ? "runs/" + rid + "/ui/input/" + source : "<document>"];
    if (sel.value) parts.push("--profile", sel.value);
    if (prev) parts.push("--v1", "runs/" + rid + "/ui/input/previous/" + prev.name);
    if ($("no-tools").checked) parts.push("--no-tools");
    parts.push("--run-id", rid);
    $("cmd-preview").textContent = parts.join(" ");
    $("start-btn").disabled = !(doc || link()) || !meta.can_launch;
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
  sel.addEventListener("change", () => { S.profile = sel.value; $("top-profile").value = sel.value; refresh(); });
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
  app.append(h("div", { class: "cfg" }, h("h2", { text: "Routes this page reads" }), h("div", { class: "notice", text: "GET /meta · GET /runs · GET /runs/<id> · GET /runs/<id>/events (SSE) · GET /runs/<id>/report · GET /runs/<id>/coverage · GET /runs/<id>/outputs · GET /runs/<id>/chat · GET /tools · GET /documents. Writes: POST /runs, POST /runs/<id>/stop, POST /runs/<id>/email, POST /runs/<id>/chat, POST /tools/probe, each only on a button." })));
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
// call_closed outcomes that end the call without an answer (the schema's enum, less ok, cut and replaced).
const CALL_FAILED = ["refusal", "truncated", "error", "cancelled", "interrupted"];

function newRunModel() {
  return { limits: null, deadline: null, profile: null, mode: null, replay: false, resumed: false, shardCount: null, lastT: 0,
    tracks: new Map(), byCall: new Map(), drafts: [], seen: new Set(), events: [], finished: null, error: null, verdict: null,
    stopRule: null, doc: null, runId: null,
    // A limit that fired, in plain words, with the run clock it fired at; drafted finding count per call (for "n of m kept").
    limitNotes: [], draftedByCall: new Map() };
}

// Which recorded limit a stage runs against: stage 1 and its members, refine, verdict; report runs to the deadline.
function limitFor(m, stage) {
  const lim = m.limits || {};
  const s = { stage_1: lim.stage_1_end, ingest: lim.stage_1_end, understand: lim.stage_1_end, plan: lim.stage_1_end, research: lim.stage_1_end,
    assess: lim.stage_1_end, merge: lim.stage_1_end, refine: lim.refine_end, verify: lim.refine_end, verdict: lim.verdict_end, report: m.deadline }[stage];
  return typeof s === "number" ? s : null;
}
function limitName(stage) { return stage === "stage_1" || STAGE1.includes(stage) || stage === "assess" || stage === "merge" ? "stage 1" : words(stage); }
function noteLimit(m, t, text) { m.limitNotes.push({ t, text }); }

function track(m, key, label) {
  if (!m.tracks.has(key)) m.tracks.set(key, { key, label: label || key, status: "waiting", call: null, start: null, end: null, text: null, strong: null, cutAt: null, skippedAt: null, shard: null, disclose: null });
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
    case "research_stopped": { const t = track(m, "research"); t.strong = null; t.text = words(f.code) + ": " + intl(f.answered) + " of " + intl(f.questions) + " question(s) answered, " + intl(f.tool_calls) + " tool call(s)"; break; }
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
      if (f.outcome === "cut") { t.status = "cut"; t.cutAt = now; t.end = now; t.strong = null; t.text = typeof f.kept_items === "number" ? "kept " + intl(f.kept_items) + " finished item(s)" : t.text; }
      else if (CALL_FAILED.includes(f.outcome)) { t.status = "failed"; t.end = now; t.strong = null; t.text = words(f.outcome); }
      else if (t.key.startsWith("assess ")) { t.status = "done"; t.end = now; }
      break;
    }
    case "draft_item":
      if (f.list === "findings") {
        m.draftedByCall.set(f.call_id, (m.draftedByCall.get(f.call_id) || 0) + 1);
        addDraft(m, f.call_id + "#" + f.index, now, f, whoOf(m, f.shard, f.call_id));
      }
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
      const kept = "kept " + intl(f.kept) + " finished finding(s)" + ((f.criteria_not_assessed || []).length ? "; not assessed: " + f.criteria_not_assessed.join(", ") : "");
      t.text = (f.degradation_id ? " in the report · " : "") + kept;
      if (f.degradation_id) t.disclose = { id: f.degradation_id, text: t.key + " cut at " + clock(t.cutAt) + ": " + kept };
      for (const d of f.kept_drafts || []) addDraft(m, f.call_id + "#" + d.index, now, d, whoOf(m, f.shard, f.call_id));
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
      {
        const lim = limitFor(m, f.stage);
        noteLimit(m, now, sentence(words(f.stage)) + ": the model call " + f.call_id + " was cut at " + clock(t.cutAt) + (lim !== null ? " (" + limitName(f.stage) + " ends by " + clock(lim) + ")" : "") + "; " + intl(f.kept_items) + " finished item(s) kept.");
      }
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
  for (const k of order) s1.append(trackRow(m, track(m, k), lim.stage_1_end ?? null));
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
  renderAxis(m);
  const notes = clear($("limit-notes"));
  for (const n of m.limitNotes) notes.append(h("div", { class: "limit-note" }, h("span", { class: "num mono", text: clock(n.t) }), h("span", { text: n.text })));
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

function showRun(info, tabs) {
  closeStream();
  const app = clear($("app"));
  app.className = "surface wide";
  app.append(tpl("tpl-run"));
  const m = newRunModel();
  S.model = m;
  S.stop = null;
  S.lastAt = null;
  renderRun(m);
  runTop(info, m, tabs);
  renderRailTools();
  if (info.argv) $("legend").after(h("div", { class: "cmd", id: "run-cmd", text: info.argv }));
  // A run just started has no progress.jsonl until the child's first event: the stream is opened anyway and
  // the server follows the file from the moment it appears. Only a run that ended without one has no timeline.
  if (!info.has_events && info.status !== "running") {
    $("legend").after(h("p", { class: "notice", text: "This run directory has no progress.jsonl (it was recorded before the structured event stream), so there is no timeline to show." }));
    return;
  }
  const es = new EventSource("/runs/" + encodeURIComponent(info.run_id) + "/events");
  S.es = es;
  if (info.status === "running" && !info.replayed) startTick();
  let pending = false;
  const paint = () => { pending = false; renderRun(m); runTop(info, m, tabs); };
  es.addEventListener("progress", (e) => {
    const ev = JSON.parse(e.data);
    S.lastAt = Date.now();
    applyEvent(m, ev);
    if (!pending) { pending = true; requestAnimationFrame(paint); }
    // The other rail rows are re-read at the open run's status cadence (one call_status record per tick),
    // never on a browser timer.
    if (ev.type === "call_status") refreshRuns().catch(() => {});
  });
  es.addEventListener("end", async (e) => {
    stopTick(); es.close(); S.es = null;
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
  $("out-download-label").textContent = "Download review (HTML" + (out.export ? ", " + out.export.size : "") + ")";
  $("out-download-help").textContent = "One file, no script, nothing loaded from the network: this run's report.md shown as HTML" +
    (info.replayed ? ", stamped replayed evidence" : "") +
    (out.export && out.export.has_chat ? ", then the chat transcript, marked as not part of the review." : ".");
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
      if (info.status === "running" || !info.has_report) showRun(info, null);
      else await showReview(info, q.get("tab"));
      renderRailTools();
      return;
    }
    S.info = null;
    closeStream();
    S.model = null;
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
window.SIT = { applyEvent, newRunModel, state: S };
window.addEventListener("popstate", route);
route();
