"""The "What is happening" panel of the run page (docs/USER_DECISIONS.md #45): explanation of the current stage,
written in advance as the ``#explain-map`` JSON in index.html, with the run's own numbers filled in by app.js
``FACTS`` from the records the page's reducer holds.

Static checks: every ``{name}`` of the map is a FACT and every FACT reads a field the reducer writes; every decision
number the text cites is a row of USER_DECISIONS.md about what the text says; every file the text names exists and
holds the symbol named after it. Browser checks (skipped where Playwright or its Chromium is missing): fed record by
record through the page's reducer, no entry ever shows an empty or undefined value; and on the served page the panel
follows a growing progress.jsonl from assess to refine to the finished run."""

from __future__ import annotations

import json
import re
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import STATIC_DIR, UIState, build_app

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "ui"
HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
DECISIONS = (REPO / "docs" / "USER_DECISIONS.md").read_text(encoding="utf-8")

#: The entries the page can show: one per stage, the limits and the finished run.
ENTRIES = {"ingest", "understand", "plan", "assess", "research", "refine", "verify", "report", "limits", "finished"}

#: What each decision the text cites is about: a phrase of that row of USER_DECISIONS.md. A new citation needs a line
#: here, so a number cannot drift onto an unrelated row.
DECISION_ABOUT = {
    "31": "six sequential model phases cannot fit",
    "34": "states no time limit for the live execution",
    "37": "Refine applies the external evidence to the merged findings",
    "40": "six assess shard groups",
}


def explain_map() -> dict[str, Any]:
    raw = HTML.split('<script type="application/json" id="explain-map">', 1)[1].split("</script>", 1)[0]
    return json.loads(raw)


def sentences(item: Any) -> list[str]:
    """Every text of a sentence item and its chain of ``else`` alternatives."""
    if isinstance(item, str):
        return [item]
    return [item["text"], *(sentences(item["else"]) if "else" in item else [])]


def all_text() -> list[str]:
    out = []
    for entry in explain_map().values():
        out += [entry["title"], entry["src"]]
        for item in entry["says"]:
            out += sentences(item)
    return out


def js_block(start: str) -> str:
    return JS.split(start, 1)[1].split("\n}", 1)[0]


FACTS = dict(re.findall(r"^  ([a-z_0-9]+): (\(m\) => .*),$", js_block("const FACTS = {"), flags=re.M))


# ------------------------------------------------------------------ the map and FACTS


def test_the_map_has_one_entry_per_stage_and_reads_aloud_in_two_to_four_sentences() -> None:
    m = explain_map()
    assert set(m) == ENTRIES
    for key, entry in m.items():
        assert set(entry) == {"title", "says", "src"}, key
        assert 1 <= len(entry["says"]) <= 4, key
    assert "\u2014" not in HTML.split('id="explain-map"', 1)[1]          # plain hyphens only


def test_every_placeholder_is_a_fact_and_every_fact_is_used() -> None:
    names = {n for text in all_text() for n in re.findall(r"\{([^}]*)\}", text)}
    assert names and all(re.fullmatch(r"\w+", n) for n in names), names     # the JS split matches {\w+}
    assert len(FACTS) > 30
    assert names <= set(FACTS), sorted(names - set(FACTS))
    assert set(FACTS) <= names, sorted(set(FACTS) - names)


def test_every_fact_reads_a_field_the_reducer_writes() -> None:
    """A fact is a getter over the model ``applyEvent`` builds: ``m.x.<k>`` is written by ``recordFacts`` from the
    record of the same name, and every other ``m.<k>`` is a field of ``newRunModel`` that ``applyEvent`` sets."""
    record = js_block("function recordFacts(m, ev, f) {")
    model = js_block("function newRunModel() {")
    reducer = js_block("function applyEvent(m, ev) {")
    for name, getter in FACTS.items():
        for k in re.findall(r"m\.x\.([A-Za-z]+)", getter):
            assert re.search(rf"\bx\.{k}\b(?:\s*=(?!=)|\.push\()", record), (name, k)
            assert re.search(rf"\b{k}: ", model), (name, k)
        for k in re.findall(r"\bm\.(?!x\b)([A-Za-z]+)", getter):
            assert re.search(rf"\b{k}: ", model), (name, k)
            assert re.search(rf"\bm\.{k}\b", reducer) or k in ("tracks", "drafts", "limitNotes"), (name, k)
    # The record fields recordFacts keeps are the schema's (spec/progress_event.schema.json).
    schema = json.loads((REPO / "spec" / "progress_event.schema.json").read_text(encoding="utf-8"))
    required = {}
    for cond in schema["allOf"]:
        t = cond.get("if", {}).get("properties", {}).get("type", {}).get("const")
        if t:
            required[t] = set(cond.get("then", {}).get("properties", {}).get("fields", {}).get("required", []))
    kept = {"intent": "intent_ready", "plan": "plan_ready", "research": "research_started",
            "researchStop": "research_stopped", "merged": "shards_merged", "refined": "refined",
            "anchors": "anchors_verified"}
    for name, getter in FACTS.items():
        for obj, key in re.findall(r'field\(m\.x\.([A-Za-z]+), "([a-z_]+)"\)', getter):
            if obj in kept:
                assert key in required[kept[obj]], (name, obj, key)


# ------------------------------------------------------------------ the claims: decisions and files


def test_every_cited_decision_is_a_row_about_that_claim() -> None:
    cited = {n for text in all_text() for n in re.findall(r"#(\d+)", text)}
    assert cited == set(DECISION_ABOUT), cited
    for n, phrase in DECISION_ABOUT.items():
        row = next((ln for ln in DECISIONS.splitlines() if ln.startswith(f"| {n} |")), None)
        assert row is not None, n
        assert phrase in row, (n, phrase)


PATH = re.compile(r"(?:agent|config|docs|spec)/[A-Za-z0-9_./-]+\.(?:py|yaml|md|json)")


def test_every_named_file_exists_and_holds_the_symbols_named_after_it() -> None:
    for text in all_text():
        for p in PATH.findall(text):
            assert (REPO / p).is_file(), p
    for entry in explain_map().values():
        for part in entry["src"].split(";"):
            words = part.strip().split()
            if not words or not PATH.fullmatch(words[0]):
                continue
            body = (REPO / words[0]).read_text(encoding="utf-8")
            if words[0].endswith(".py"):
                for sym in (w.strip(",") for w in words[1:]):
                    pat = rf"\b(def|class) {re.escape(sym)}\b|^{re.escape(sym)}\b"
                    assert re.search(pat, body, flags=re.M), (words[0], sym)
            elif words[0].endswith(".yaml"):
                for sym in words[1:]:
                    assert f"{sym.split('.')[-1]}:" in body, (words[0], sym)


def test_the_panel_is_labelled_explanation_never_the_record() -> None:
    run = HTML.split('<template id="tpl-run">', 1)[1].split("</template>", 1)[0]
    assert '<h2 id="explain-title">What is happening</h2>' in run
    assert '<span class="pill explain-pill" id="explain-label">explanation, not the record</span>' in run
    assert run.index('id="explain"') < run.index('id="stage1-tracks"')          # above the stage rows
    assert "only the numbers are this run's, read from its event stream" in run


# ------------------------------------------------------------------ in a browser


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def served(tmp_path: Path):
    uvicorn = pytest.importorskip("uvicorn")
    runs = tmp_path / "runs"
    runs.mkdir()
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO), chat_client=None,
                    profiles=[], tools=[])  # type: ignore[arg-type]
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", runs
    server.should_exit = True
    th.join(timeout=5)


@pytest.fixture
def page(served):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, runs = served
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg, base, runs
        browser.close()
    assert errors == []


#: The panel's entry keys as the page last drew them.
STAGES = "document.querySelector('#explain-body') && document.querySelector('#explain-body').dataset.stages === '{}'"


def lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines(keepends=True)


#: Facts no fixture stream fills, and why: the refine answers of the three fixtures pass the rules at once, so no
#: rule repair call is recorded (test_the_refine_repair_counts_and_a_lower_bound_cost_fill_in feeds one).
NEVER_IN_FIXTURES = {"refine_kept", "refine_retry", "research_left"}   # research_left: a --no-tools run


def test_no_entry_ever_shows_an_empty_value_record_by_record(page) -> None:
    pg, base, _runs = page
    pg.goto(base + "/")
    pg.wait_for_function("window.SIT !== undefined")
    filled: set[str] = set()
    for name in ("progress.jsonl", "progress_cut.jsonl", "progress_resume.jsonl"):
        evs = [json.loads(ln) for ln in lines(name) if ln.strip()]
        got = pg.evaluate("""(evs) => {
            const m = SIT.newRunModel(); const bad = []; const seen = new Set(); const keys = new Set();
            for (const ev of evs) {
              SIT.applyEvent(m, ev);
              for (const k of SIT.explainKeys(m)) keys.add(k);
              const now = SIT.explainKeys(m);
              for (const k of Object.keys(SIT.explain)) {
                if (k === "finished" && !now.includes(k)) continue;      // shown only once the run has ended
                const t = SIT.explainText(m, k);
                if (!t || /undefined|NaN|null|[{}]|–|\\s[,.;:]/.test(t)) bad.push([ev.seq, k, t]);
              }
              for (const f of SIT.facts) if (SIT.factText(m, f) !== null) seen.add(f);
            }
            return { bad, seen: [...seen], keys: [...keys] };
        }""", evs)
        assert got["bad"] == [], (name, got["bad"][:3])
        assert {"assess", "refine", "verify", "report", "finished"} <= set(got["keys"]), (name, got["keys"])
        filled |= set(got["seen"])
    facts = set(pg.evaluate("SIT.facts"))
    assert facts - filled == NEVER_IN_FIXTURES, sorted(facts - filled)


def test_the_refine_repair_counts_and_a_lower_bound_cost_fill_in(page) -> None:
    """The facts no fixture fills, fed as the agent writes them (phases/_model_calls.py call_retry rule_repair,
    progress_event.schema.json run_finished)."""
    pg, base, _runs = page
    pg.goto(base + "/")
    pg.wait_for_function("window.SIT !== undefined")
    evs = [json.loads(ln) for ln in lines("progress.jsonl") if ln.strip()]
    i = next(k for k, e in enumerate(evs) if e["type"] == "refine_started")
    retry = {**evs[i], "seq": evs[i]["seq"], "type": "call_retry", "kind": "warn", "console": True,
             "fields": {"reason": "rule_repair", "stage": "refine", "call_id": "llm-x", "problems": 1, "kept": 54,
                        "retry": 1}}
    out = pg.evaluate("""([evs, retry]) => {
        const m = SIT.newRunModel();
        for (const ev of evs) SIT.applyEvent(m, ev);
        SIT.applyEvent(m, retry);
        const refine = SIT.explainText(m, "refine");
        SIT.applyEvent(m, { ...retry, type: "run_finished", fields: { run_id: "r", outcome: "completed_degraded",
          exit_code: 0, report_md: "", report_json: "", partial_report: null, wall_s: 508.9, cost_usd: 7.366,
          cost_is_lower_bound: true } });
        return [refine, SIT.explainText(m, "finished")];
    }""", [evs[:i + 1], retry])
    assert "54 revisions passed and were kept, 1 went to the repair call." in out[0]
    assert "The model cost is at least $7.37:" in out[1]


def _research_off(ev: dict, detail: str) -> dict:
    """``ev`` (a research_stopped record) as ``phases/research.py`` ``_doc_only`` writes it for ``detail``."""
    return {**ev, "fields": {"code": "tool_failure", "detail": detail, "answered": 0, "questions": 6,
                             "tool_calls": 0, "ledger_entries": 0}}


@pytest.mark.parametrize("no_tools", [True, None])
def test_research_with_no_tool_gateway_is_skipped_never_a_tool_failure(page, no_tools) -> None:
    """Owner's run ui-261005-125426-adaa (--no-tools): the record files "no tool gateway" under the
    tool_failure code with detail no_tools; the research row and its Why say document only, with the
    questions left to the document, and are not drawn as a failure. A run started elsewhere (no launch.json,
    ``no_tools`` unknown) names no flag it cannot know."""
    pg, base, _runs = page
    pg.goto(base + "/")
    pg.wait_for_function("window.SIT !== undefined")
    evs = [json.loads(ln) for ln in lines("progress.jsonl") if ln.strip()]
    i = next(k for k, e in enumerate(evs) if e["type"] == "research_stopped")
    evs[i] = _research_off(evs[i], "no_tools")
    out = pg.evaluate("""([evs, noTools, upTo]) => {
        const m = SIT.newRunModel(); m.noTools = noTools;
        for (const ev of evs.slice(0, upTo)) SIT.applyEvent(m, ev);
        const why = SIT.explainText(m, "research");
        for (const ev of evs.slice(upTo)) SIT.applyEvent(m, ev);
        const t = m.tracks.get("research");
        return [t.status, t.text, why];
    }""", [evs, no_tools, i + 1])
    flag = "--no-tools" if no_tools else "no tool server in use"
    assert out[0] == "skipped", out                                    # kept through its phase_done
    assert out[1] == f"document only ({flag}): 6 question(s) left to the document", out[1]
    assert "Research did not run" in out[2] and "6 outside questions are left to the document" in out[2]
    assert "tool failure" not in out[1] + out[2]
    assert "asks the SIT MCP servers the plan's outside questions in rounds" in out[2]   # the general text, no count


def test_a_real_tool_failure_keeps_its_failure_wording_and_reason(page) -> None:
    pg, base, _runs = page
    pg.goto(base + "/")
    pg.wait_for_function("window.SIT !== undefined")
    evs = [json.loads(ln) for ln in lines("progress.jsonl") if ln.strip()]
    i = next(k for k, e in enumerate(evs) if e["type"] == "research_stopped")
    evs[i] = _research_off(evs[i], "tools_unavailable")
    out = pg.evaluate("""(evs) => {
        const m = SIT.newRunModel(); m.noTools = false;
        for (const ev of evs) SIT.applyEvent(m, ev);
        const t = m.tracks.get("research");
        return [t.status, t.text, SIT.explainText(m, "research")];
    }""", evs)
    assert out[0] == "done"
    assert out[1] == "tool failure, tools unavailable: 0 of 6 question(s) answered, 0 tool call(s)", out[1]
    assert "Research stopped (tool failure, tools unavailable) with 0 of " in out[2]


def test_the_panel_follows_the_run_from_assess_to_refine_to_finished(page) -> None:
    pg, base, runs = page
    evs_lines = lines("progress.jsonl")
    evs = [json.loads(ln) for ln in evs_lines]
    run = runs / "explain_live"
    run.mkdir()
    feed = run / "progress.jsonl"

    def upto(pred) -> int:
        return next(k for k, e in enumerate(evs) if pred(e))

    # 1. Stage 1 with understand and plan done and the shards still open: the assess entry, with the run's numbers.
    first_research = upto(lambda e: e["type"] == "phase_started" and e["phase"] == "research")
    feed.write_text("".join(evs_lines[:first_research]), encoding="utf-8")
    pg.goto(base + "/?run=explain_live")
    pg.wait_for_function(STAGES.format("assess"))
    shards = next(e["fields"]["shards"] for e in evs if e["type"] == "run_started")
    text = pg.locator("#explain-body .xentry[data-stage='assess'] .xtext").inner_text()
    assert text.startswith(f"Assess is {len(shards)} model calls running at the same time")
    assert pg.locator("#explain-title").inner_text() == "What is happening"
    assert pg.locator("#explain-label").inner_text() == "explanation, not the record"

    # 2. The records up to the refine call: the panel now explains refine, with the merged count of the record.
    refine_call = upto(lambda e: e["type"] == "call_opened" and e["phase"] == "refine")
    with feed.open("a", encoding="utf-8") as fh:
        fh.write("".join(evs_lines[first_research:refine_call + 1]))
    pg.wait_for_function("document.querySelector('#explain-body').dataset.stages === 'refine'")
    merged = next(e["fields"]["findings"] for e in evs if e["type"] == "shards_merged")
    text = pg.locator("#explain-body .xentry[data-stage='refine'] .xtext").inner_text()
    assert text.startswith(f"Refine is one model call over all {merged} merged findings")
    assert pg.locator("#explain-body .xentry[data-stage='assess']").count() == 0

    # 3. A row's Why opens an earlier stage's entry in place, and closes again.
    why = pg.locator('.track[data-track="understand"] .why-btn')
    assert why.get_attribute("aria-expanded") == "false"
    why.click()
    # Each Why click repaints the run in one task; wait for the repaint the next read needs (it raced under load).
    pg.wait_for_function("document.querySelector('.track[data-track=\"understand\"] .why-btn')"
                         ".getAttribute('aria-expanded') === 'true'"
                         " && document.querySelector('.why[data-why=\"understand\"] .xtext') !== null")
    block = pg.locator('.why[data-why="understand"] .xtext')
    assert block.inner_text().startswith("Understand is one model call that reads the whole document once")
    assert pg.locator('.track[data-track="understand"] .why-btn').get_attribute("aria-expanded") == "true"
    pg.locator('.track[data-track="understand"] .why-btn').click()
    pg.wait_for_function("document.querySelector('.why[data-why=\"understand\"]') === null")
    assert pg.locator('.why[data-why="understand"]').count() == 0
    pg.locator("#axis-why").click()
    pg.wait_for_function("document.querySelector('#axis-why-text .xentry[data-stage=\"limits\"] .xtext') !== null")
    assert pg.locator('#axis-why-text .xentry[data-stage="limits"] .xtext').inner_text().startswith(
        "Every stage has a fixed end on the run clock")

    # 4. The rest of the record: the finished run's paragraph with its own counts.
    with feed.open("a", encoding="utf-8") as fh:
        fh.write("".join(evs_lines[refine_call + 1:]))
    pg.wait_for_function("document.querySelector('#explain-body').dataset.stages === 'finished'")
    fin = next(e["fields"] for e in evs if e["type"] == "run_finished")
    verdict = next(e["fields"] for e in evs if e["type"] == "verdict")
    text = pg.locator("#explain-body .xentry[data-stage='finished'] .xtext").inner_text()
    assert f"with the verdict {verdict['label'].replace('_', ' ')} at confidence {verdict['confidence']:.2f}" in text
    assert f"{verdict['findings']} findings" in text
    if not fin["cost_is_lower_bound"]:
        assert f"The model cost was ${fin['cost_usd']:.2f}." in text


def test_the_page_shows_the_panel_on_a_finished_run(page) -> None:
    pg, base, runs = page
    run = runs / "explain_done"
    run.mkdir()
    shutil.copy2(FIXTURES / "progress_cut.jsonl", run / "progress.jsonl")
    pg.goto(base + "/?run=explain_done")
    pg.wait_for_function(STAGES.format("finished"))
    text = pg.locator("#explain-body .xtext").inner_text()
    assert text.startswith("The run finished (")
    assert "undefined" not in text and "NaN" not in text
