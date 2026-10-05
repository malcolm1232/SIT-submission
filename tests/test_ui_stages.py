"""The Run log's stage panel (5 Oct 2026): ``ui/stages.py`` reads what each stage produced from the run's files, the
``/runs/<id>/stage/<name>``, ``/funnel`` and ``/glossary`` routes serve it, and the page lists it whole beside the
stage rows. Offline: a small synthetic run directory written here (a cut refine call whose revisions were salvaged,
a merge, a finding left unrefined and moved to unresolved by verify, a shard stream that started over), and a
replay of the committed rehearsal run for the browser checks on real data."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from sit_review_agent.ui import export, stages, xref
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import UIState, build_app

REPO = Path(__file__).resolve().parents[1]
REHEARSAL = REPO / "docs" / "live_runs" / "rehearsal_concurrent_1"
REHEARSAL_PDF = REPO / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
RUN = "synthetic-run"


# ------------------------------------------------------------------ a synthetic run directory


def _finding(fid: str, title: str, *, kind: str = "risk", severity: str | None = "high",
             rank: int = 1) -> dict[str, Any]:
    return {"id": fid, "title": title, "kind": kind, "severity": severity, "rank": rank, "confidence": 0.7,
            "category": "internal_contradiction", "disposition": "refinement_now", "secondary_dispositions": [],
            "criterion_ids": ["design_intent"], "statement": f"The statement of {title}.",
            "doc_anchors": [{"doc_id": "DOC-x", "page": 2, "section_ref": "1", "quote": f"a quote for {title}",
                             "requirement_ids": ["FR-1"]}],
            "evidence": [], "recommendation": None, "next_step": None, "no_change_rationale": None,
            "affected_decisions": [], "acknowledged_in_doc": False, "tags": [], "reassessment": None}


LONG_TITLE = ("A deliberately long finding title that runs well past the width of the panel so that any ellipsis or "
              "clipping of an opened list would cut it short, which the page must never do")


def _ev(seq: int, type_: str, phase: str, fields: dict[str, Any], kind: str = "step") -> str:
    return json.dumps({"v": 1, "seq": seq, "t": float(seq), "run_s": float(seq), "type": type_, "phase": phase,
                       "kind": kind, "console": False, "message": type_, "fields": fields}) + "\n"


def make_run(root: Path, *, report: bool = True) -> Path:
    rd = root / RUN
    (rd / "checkpoints").mkdir(parents=True)
    (rd / "shards").mkdir()
    (rd / "text").mkdir()
    a1, a2 = _finding("FND-001", LONG_TITLE), _finding("FND-002", "Duplicate of the first", severity="medium", rank=2)
    b1 = _finding("FND-001", "Left unrefined by the cut", kind="gap", severity="low", rank=1)
    shard = lambda n, name, fs: {"hashes": {}, "result": {  # noqa: E731
        "name": name, "index": n, "call_id": f"llm-000{n + 2}", "criteria": ["design_intent"], "outcome": "done",
        "model": "m", "detail": "", "salvaged": 0, "delta": {"budget": {"output_tokens": 10}},
        "output": {"findings": fs, "sound_areas": [{"doc_anchors": [], "evidence_ids": [], "related_finding_ids": [],
                                                    "section_refs": ["1"], "why_sound": f"Sound part of {name}."}],
                   "coverage": [{"criterion_id": "design_intent", "finding_ids": [f["id"] for f in fs],
                                 "note": f"Checked {name}.", "outcome": "findings"}]}}}
    (rd / "shards" / "01-alpha.json").write_text(json.dumps(shard(1, "alpha", [a1, a2])))
    (rd / "shards" / "02-beta.json").write_text(json.dumps(shard(2, "beta", [b1])))
    merged = [dict(a1), dict(a2), dict(b1, id="FND-003", rank=3)]
    maps = {"shards": {"alpha": {"FND-001": "FND-001", "FND-002": "FND-002"}, "beta": {"FND-001": "FND-003"}},
            "refine": {}, "refine_fields": {}, "verify": {}, "unverified": [], "prior": [], "rewrites": {}}
    cut = {"id": "DEG-001", "type": "budget_or_deadline_hit", "event": "the refine call was cut",
           "impact": "2 of 3 refine revisions were applied from the cut answer"}
    meta = {"FND-001": {"history": [{"phase": "refine", "call_id": "llm-0009", "changed_fields": {"rank": [1, 1]},
                                     "note": "revised: sharper wording"}]},
            "FND-002": {"history": [{"phase": "refine", "call_id": "llm-0009", "note": "merged into FND-001: same"}]}}
    reg = [{"registry_id": "AD-001", "type": "approved_decision", "statement": "The store is Postgres.",
            "doc_ref": "Decisions", "doc_anchor": {"doc_id": "DOC-x", "page": 3, "section_ref": "2",
                                                   "quote": "the store is postgres", "requirement_ids": []}}]
    plan = {"approved": True, "criteria_skipped": [], "questions": [
        {"id": "RQ-001", "criterion_id": "design_intent", "question": "Is the intent clear?", "needs_external": False,
         "capability": "none", "queries": [], "rationale": "r", "section_refs": ["1"], "status": "open", "summary": "",
         "evidence_ids": []},
        {"id": "RQ-002", "criterion_id": "design_intent", "question": "Does the vendor allow it?",
         "needs_external": True, "capability": "search", "queries": ["vendor limit"], "rationale": "r",
         "section_refs": ["2"], "status": "unanswered", "summary": "", "evidence_ids": []}]}
    base = {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X design", "page_count": 3,
                           "sha256_pdf": "a" * 64, "sha256_text": "b" * 64, "native_pdf": False}],
            "registry": reg, "registry_frozen": True, "registry_hashes": [{"iteration": 0, "sha256": "c" * 64}],
            "review_inputs_found": ["A reviewer says FR-1 was fixed."], "plan": plan, "degradations": [],
            "intent_summary": {"statement": "X does Y.", "objectives": [{"ref": "O1", "text": "Be fast."}],
                               "constraints": [], "key_assumptions": [], "doc_anchors": []},
            "tool_calls": [], "queries_issued": 0, "stop_reason": {"code": "tool_failure", "detail": "no_tools"},
            "completed_phases": []}
    states = {
        "01-ingest": base, "02-understand": base, "03-plan": base, "04-research": base,
        "05-assess": {**base, "finding_drafts": merged, "sound_area_drafts": [], "coverage": [], "finding_ids": maps},
        "06-refine": {**base, "finding_drafts": [dict(a1, title=LONG_TITLE), merged[2]], "finding_meta": meta,
                      "degradations": [cut], "finding_ids": {**maps, "refine": {"FND-002": "FND-001"},
                                                             "refine_fields": {"FND-001": ["affected_decisions"]}}},
        "07-verify": {**base, "findings": [a1], "finding_drafts": [a1], "degradations": [cut],
                      "unresolved": [{"finding_ids": ["FND-003"], "text": "FND-003 could not be verified."}],
                      "finding_ids": {**maps, "refine": {"FND-002": "FND-001"},
                                      "refine_fields": {"FND-001": ["affected_decisions"]}, "unverified": ["FND-003"]}},
    }
    for name, st in states.items():
        (rd / "checkpoints" / f"{name}.json").write_text(json.dumps({"state": st}))
    (rd / "text" / "DOC-x.sections.json").write_text(json.dumps({
        "pages": [{"number": n, "char_start": 10 * n, "char_end": 10 * n + 8, "image_only": n == 3} for n in (1, 2, 3)],
        "sections": [{"section_id": "1", "heading": "Scope", "level": 1, "order": 0, "page_start": 1, "page_end": 2,
                      "char_start": 0, "char_end": 20}], "warnings": []}))
    summary = {"anchors": 2, "resolved": 1, "repaired": 0, "unresolved": 1}
    (rd / "anchors.json").write_text(json.dumps({"summary": summary, "rules": {"fuzzy_threshold": 0.9},
                                                 "repair_call_id": None, "rows": [
        {"owner_id": "FND-001", "anchor_index": 0, "anchor_status": "resolved", "method": "exact", "score": 1.0,
         "page": 2, "section_ref": "1", "reasons": []},
        {"owner_id": "FND-003", "anchor_index": 0, "anchor_status": "unresolved", "method": "none", "score": 0.0,
         "page": 2, "section_ref": "1", "reasons": ["not_found"]}]}))
    (rd / "ledger.json").write_text("[]")
    (rd / "effective_config.json").write_text(json.dumps({"criteria": {"criteria": [
        {"id": "design_intent", "question": "Is the intent clear enough to review against?"}]},
        "stop_rules": {"max_research_iterations": 4, "max_tool_calls": 30}}))
    (rd / "manifest.json").write_text(json.dumps({"extra": {"finding_ids": {"final": {
        "FND-001": "FND-001", "FND-002": "FND-001", "FND-003": None}}}}))
    if report:
        (rd / "report.json").write_text(json.dumps({
            "findings": [a1], "unresolved": [{"finding_ids": ["FND-003"], "text": "FND-003 could not be verified."}],
            "limitations": [], "metadata": {"documents": []},
            "verdict": {"label": "fit_with_conditions", "confidence": 0.6, "rationale": "Because.",
                        "conditions": [{"text": "Fix it.", "finding_ids": ["FND-001"]}], "per_objective": []}}))
    groups = [{"index": 1, "name": "alpha", "criteria": ["design_intent"]},
              {"index": 2, "name": "beta", "criteria": ["design_intent"]}]
    evs = [("run_started", "run", {"run_id": RUN, "shards": groups, "stage_limits_s": {"stage_1_end": 100,
                                                                                       "refine_end": 200,
                                                                                       "verdict_end": 290},
                                    "deadline_s": 300, "documents": [], "criteria": ["design_intent"]}),
           ("assess_started", "assess", {"criteria": 1, "shards": 2, "groups": groups}),
           ("shard_started", "assess", {"shard": 1, "shard_name": "alpha", "shards": 2, "criteria": ["design_intent"]}),
           ("call_opened", "assess", {"call_id": "llm-0003", "stage": "assess", "shard": 1, "shard_name": "alpha",
                                      "purpose": "assess", "attempt": 0, "iteration": 0}),
           ("call_opened", "assess", {"call_id": "llm-0004", "stage": "assess", "shard": 2, "shard_name": "beta",
                                      "purpose": "assess", "attempt": 0, "iteration": 0})]
    for i in (1, 2, 1, 2):                    # the stream of shard 1 started over: its answer written twice
        evs.append(("draft_item", "assess", {"list": "findings", "index": i, "call_id": "llm-0003", "shard": 1,
                                             "item": "finding", "title": "t", "severity": "high", "kind": "risk"}))
    evs += [("call_closed", "assess", {"call_id": "llm-0003", "outcome": "ok", "shard": 1}),
            ("call_closed", "assess", {"call_id": "llm-0004", "outcome": "ok", "shard": 2}),
            ("shards_merged", "assess", {"shards": 2, "findings": 3, "sound_areas": 0, "degraded_shards": []}),
            ("refine_started", "refine", {"findings": 3}),
            ("call_opened", "refine", {"call_id": "llm-0009", "stage": "refine", "shard": None, "purpose": "refine",
                                       "attempt": 0, "iteration": 0}),
            ("call_cut", "refine", {"stage": "refine", "call_id": "llm-0009", "at_s": 190.0, "kept_items": 3,
                                    "complete": True, "kept": {"revisions": 3}}),
            ("refined", "refine", {"call_id": "llm-0009", "revised": 1, "unchanged": 1, "merged": 1, "withdrawn": 0,
                                   "findings": 2, "salvaged": True, "salvaged_items": 3, "applied": 2, "dropped": 1}),
            ("anchors_verified", "verify", {"anchors": 2, "resolved": 1, "repaired": 0, "unresolved": 1,
                                            "findings_verified": 1, "findings_unverified": 1}),
            ("verdict", "report", {"label": "fit_with_conditions", "confidence": 0.6, "findings": 1, "unresolved": 1,
                                   "limitations": 0}),
            ("run_finished", "run", {"run_id": RUN, "outcome": "completed_degraded", "exit_code": 0})]
    (rd / "progress.jsonl").write_text("".join(_ev(i + 1, t, ph, f) for i, (t, ph, f) in enumerate(evs)))
    return rd


@pytest.fixture
def run(tmp_path: Path) -> Path:
    return make_run(tmp_path / "runs")


def _list(view: dict[str, Any], key: str) -> dict[str, Any]:
    return next(x for x in view["lists"] if x["key"] == key)


# ------------------------------------------------------------------ the readers


def test_every_stage_lists_what_its_file_holds(run: Path) -> None:
    und = stages.stage_view(run, "understand")
    reg = _list(und, "registry")
    assert reg["count"] == 1 and reg["groups"][0]["term"] == "reg-approved_decision"
    assert _list(und, "review_inputs")["items"][0]["text"] == "A reviewer says FR-1 was fixed."
    plan = stages.stage_view(run, "plan")
    assert [q["id"] for q in _list(plan, "questions")["items"]] == ["RQ-001", "RQ-002"]
    assert next(f["value"] for f in plan["facts"] if f["label"].startswith("research budget")).startswith("at most 4")
    res = stages.stage_view(run, "research")
    assert [q["id"] for q in _list(res, "questions")["items"]] == ["RQ-002"]          # the external one only
    ing = stages.stage_view(run, "ingest")
    assert next(f["value"] for f in ing["facts"] if f["label"].startswith("pages with no text")) == "3"
    a1 = stages.stage_view(run, "assess-1")
    finds = _list(a1, "findings")["items"]
    assert [f["rec"]["title"] for f in finds] == [LONG_TITLE, "Duplicate of the first"]
    assert all(f["draft"] for f in finds)
    assert [f["merged_id"] for f in finds] == ["FND-001", "FND-002"]
    assert finds[1]["fate"] == "merged into FND-001, reported as FND-001"
    assert _list(a1, "sound_areas")["count"] == 1 and _list(a1, "coverage")["count"] == 1
    # the stream carried 4 finding items and started over; the shard's answer holds 2, and the panel says so
    assert any("started over 1 time(s)" in n["text"] and "2 findings" in n["text"] for n in a1["notes"])
    merge = stages.stage_view(run, "merge")
    assert [(f["id"], f["shard"], f["local_id"]) for f in _list(merge, "findings")["items"]] == [
        ("FND-001", "alpha", "FND-001"), ("FND-002", "alpha", "FND-002"), ("FND-003", "beta", "FND-001")]
    assert stages.stage_view(run, "nope") is None


def test_refine_states_what_the_salvage_applied_and_what_the_cut_lost(run: Path) -> None:
    v = stages.stage_view(run, "refine")
    revs = {r["id"]: (r["group"], r["into"], r["note"]) for r in _list(v, "revisions")["items"]}
    assert revs == {"FND-001": ("revised", None, "revised: sharper wording"),
                    "FND-002": ("merged", "FND-001", "merged into FND-001: same"),
                    "FND-003": ("not refined (counted as unchanged)", None, None)}
    assert any("were applied: 2 of them" in n["text"] for n in v["notes"])
    assert [d["id"] for d in _list(v, "lost")["items"]] == ["DEG-001"]
    assert [(f["id"], f["refined"]) for f in _list(v, "result")["items"]] == [("FND-001", True), ("FND-003", False)]


def test_the_funnel_traces_every_draft_and_adds_up(run: Path) -> None:
    f = stages.funnel(run)
    rows = {r["draft_id"]: r for r in f["lists"][0]["items"]}
    assert {k: r["fate"] for k, r in rows.items()} == {
        "FND-001": "reported as FND-001", "FND-002": "merged into FND-001, reported as FND-001",
        "FND-003": "moved to unresolved (unverified)"}
    t = f["totals"]
    assert t["drafts"] == 3 and sum(t["refine"].values()) == 3 and t["after_refine"] == 2
    assert t["verify"]["verified"] == 1 and t["verify"]["moved to unresolved (unverified)"] == 1
    assert t["reported"] == t["report_findings"] == 1
    assert f["manifest_disagrees"] == [] and all(r["agrees"] for r in rows.values())


def test_the_funnel_flags_a_manifest_that_disagrees(run: Path) -> None:
    m = json.loads((run / "manifest.json").read_text())
    m["extra"]["finding_ids"]["final"]["FND-002"] = "FND-009"
    (run / "manifest.json").write_text(json.dumps(m))
    assert stages.funnel(run)["manifest_disagrees"] == ["FND-002"]


def test_invariants_read_their_result_from_the_run(run: Path) -> None:
    items = _list(stages.stage_view(run, "verify"), "invariants")["items"]
    assert [i["id"] for i in items][:2] == ["INV-03", "INV-04"] and {i["result"] for i in items} == {"passed"}
    assert all("``" not in i["about"] and ":func:" not in i["about"] for i in items)
    (run / "report.json").unlink()
    (run / "failure.json").write_text(json.dumps({"problems": ["INV-05: EV-009 is not in the ledger"]}))
    items = {i["id"]: i for i in _list(stages.stage_view(run, "verify"), "invariants")["items"]}
    assert items["INV-05"]["result"] == "failed"
    assert items["INV-05"]["problems"] == ["INV-05: EV-009 is not in the ledger"]
    assert items["INV-03"]["result"] == "failed (another check)"


def test_a_run_with_no_checkpoints_names_what_is_missing(tmp_path: Path) -> None:
    rd = tmp_path / "runs" / "early"
    rd.mkdir(parents=True)
    (rd / "progress.jsonl").write_text(_ev(1, "run_started", "run", {"run_id": "early"}))
    for name in ("ingest", "understand", "plan", "research", "assess-1", "merge", "refine", "verify", "report"):
        v = stages.stage_view(rd, name)
        assert v is not None and v["missing"], name
        assert all(set(m) == {"file", "what"} for m in v["missing"])
    assert stages.funnel(rd)["totals"]["drafts"] == 0


# ------------------------------------------------------------------ the routes


@pytest.fixture
def client(run: Path) -> TestClient:
    state = UIState(runs_dir=run.parent.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO),
                    chat_client=None, profiles=[], tools=[])  # type: ignore[arg-type]
    return TestClient(build_app(state))


def test_the_routes_serve_the_views_and_never_error(client: TestClient, run: Path) -> None:
    r = client.get(f"/runs/{RUN}/stage/refine")
    assert r.status_code == 200 and _list(r.json(), "revisions")["count"] == 3
    assert client.get(f"/runs/{RUN}/stage/assess-9").json()["missing"][0]["file"].startswith("shards/09-")
    assert client.get(f"/runs/{RUN}/stage/nope").status_code == 404
    assert client.get("/runs/no-such-run/stage/refine").status_code == 404
    assert client.get(f"/runs/{RUN}/funnel").json()["totals"]["drafts"] == 3
    # a file in a shape this reader does not expect is said, never a server error
    (run / "checkpoints" / "05-assess.json").write_text(json.dumps({"state": {"finding_drafts": [],
                                                                            "finding_ids": {"shards": ["x"]}}}))
    for path in ("stage/merge", "funnel", "stage/refine", "stage/assess-1"):
        r = client.get(f"/runs/{RUN}/{path}")
        assert r.status_code == 200 and r.json()["unreadable"].startswith("AttributeError"), (path, r.text)


def test_the_glossary_is_the_export_vocabulary_with_the_run_log_words(client: TestClient, run: Path) -> None:
    terms = client.get(f"/runs/{RUN}/glossary").json()["terms"]
    for key in ("kind-strength", "kind-risk", "kind-gap", "kind-ambiguity", "kind-validation_need", "sev-critical",
                "sev-high", "sev-medium", "sev-low", "run-draft", "run-shard", "reg-approved_decision", "rev-merge",
                "cov-no_issue", "anchor-unresolved", "q-external", "crit-design_intent", "confidence", "rank"):
        assert key in terms, key
        assert terms[key]["paras"] and re.match(r"[\w/.-]+(:\d+(-\d+)?)?", terms[key]["src"]), key
        assert not any("<" in p or "`" in p for p in terms[key]["paras"]), key
    assert terms["sev-high"]["src"].startswith("prompts/system.md:")
    assert terms["reg-approved_decision"]["src"].startswith("prompts/understand.md:")


def test_the_new_words_do_not_change_the_export(run: Path) -> None:
    """The export's "How to read this review" lists its own groups only; the Run log's words stay out of it."""
    words = xref.run_log_terms(REPO)
    assert {k.split("-")[0] for k in words} == {"reg", "rev", "cov", "review", "anchor", "run", "q"}
    (run / "report.md").write_text("# Review\n\nFND-001 is high.\n")
    html = export.export_html(run, replayed=False)
    assert not any(f'id="g-{k}"' in html for k in words)


# ------------------------------------------------------------------ the page, in a real browser


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """``dra replay`` of the committed rehearsal run (offline), as tests/test_ui_page.py does."""
    from sit_review_agent.replay import replay_run

    root = tmp_path_factory.mktemp("stages_replay_root")
    out = asyncio.run(replay_run(REHEARSAL, run_root=str(root), run_id="stages_replay", pdf=REHEARSAL_PDF))
    assert out.report_md is not None, out.message
    return Path(out.run_dir)


@pytest.fixture
def page(tmp_path: Path, replayed: Path):
    uvicorn = pytest.importorskip("uvicorn")
    sync_api = pytest.importorskip("playwright.sync_api")
    runs = tmp_path / "runs"
    make_run(runs)
    shutil.copytree(replayed, runs / replayed.name, ignore=shutil.ignore_patterns("llm.jsonl"))
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
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg, f"http://127.0.0.1:{port}", runs, replayed.name
        browser.close()
    server.should_exit = True
    th.join(timeout=5)
    assert errors == []


def open_log(pg: Any, base: str, run_id: str) -> None:
    pg.goto(f"{base}/?run={run_id}&tab=log")
    pg.wait_for_function("document.querySelector('#finished-bar') && !document.querySelector('#finished-bar').hidden")


def open_panel(pg: Any, key: str) -> dict[str, Any]:
    pg.locator(f'[data-panel="{key}"]').click()
    pg.wait_for_function("(k) => { const P = window.SIT.state.panel; return P && P.key === k && P.data !== null"
                         " && document.querySelector('#sp-content .sp-list, #sp-content .sp-missing') !== null; }",
                         arg=key)
    return pg.evaluate("window.SIT.state.panel.data")


NO_CLIP = """() => [...document.querySelectorAll('#stage-panel .sp-tx, #stage-panel .sp-after, #stage-panel dd')]
  .filter((el) => { const cs = getComputedStyle(el); return cs.textOverflow === 'ellipsis' || cs.whiteSpace === 'nowrap'
    || el.scrollWidth > el.clientWidth + 1; }).map((el) => el.textContent.slice(0, 60))"""


def test_every_stage_row_opens_its_whole_output(page) -> None:
    """Each row's name opens its panel (aria-expanded on the row), every list shows as many items as its count, the
    long title is shown whole (no ellipsis, nothing clipped), and the panel takes the feed's place beside the rows,
    which do not move."""
    pg, base, _runs, _replay = page
    open_log(pg, base, RUN)
    where = "(() => { const r = document.querySelector('.track[data-track=\"merge\"]').getBoundingClientRect();" \
            " return [r.left, r.top + window.scrollY, r.width]; })()"
    first = pg.evaluate(where)
    for key in ("ingest", "understand", "plan", "research", "assess 1/2", "assess 2/2", "merge", "refine", "verify",
                "verdict", "report"):
        data = open_panel(pg, key)
        assert pg.locator(f'[data-panel="{key}"]').get_attribute("aria-expanded") == "true"
        assert pg.locator("#stage-panel").is_visible() and not pg.locator("#feed").is_visible()
        for lst in data["lists"]:
            shown = pg.locator(f'#sp-content .sp-list[data-list="{lst["key"]}"] .sp-item').count()
            assert shown == lst["count"] == len(lst["items"]), (key, lst["key"])
        assert pg.evaluate(NO_CLIP) == [], key
        assert pg.evaluate(where) == first                                     # the rows never moved
    open_panel(pg, "assess 1/2")
    item = pg.locator('#sp-content .sp-list[data-list="findings"] .sp-item').first
    assert item.locator(".sp-tx").inner_text() == LONG_TITLE
    assert pg.locator('#sp-content .sp-list[data-list="findings"] .pill.draft').inner_text() == "draft, unverified"
    item.locator(".sp-toggle").click()
    assert item.locator(".sp-detail .statement").inner_text() == f"The statement of {LONG_TITLE}."
    assert "“a quote for " in item.locator(".sp-detail .qrow").inner_text()


def test_refine_row_and_banner_say_the_salvage_was_applied(page) -> None:
    pg, base, _runs, _replay = page
    open_log(pg, base, RUN)
    status = pg.locator('.track[data-track="refine"] .status').inner_text()
    assert status == "2 findings: 1 revised, 1 merged, 0 withdrawn, 1 unchanged; 2 of 3 finished revisions applied"
    note = pg.locator("#limit-notes .limit-note").inner_text()
    assert "3 finished item(s) kept. Refine then applied 2 of the 3 finished revisions (1 merges into kept findings" \
           " among them) and dropped 1" in note


def test_the_funnel_adds_up_and_traces_each_draft(page) -> None:
    pg, base, _runs, _replay = page
    open_log(pg, base, RUN)
    pg.wait_for_function("!document.querySelector('#funnel').hidden")
    nums = pg.locator("#funnel .fnum").all_inner_texts()
    assert nums == ["3", "2", "1", "1"]
    assert pg.locator("#funnel .fcheck").inner_text().startswith("Adds up")
    data = open_panel(pg, "funnel")
    fates = pg.locator('#sp-content .sp-list[data-list="fates"] .sp-item')
    assert fates.count() == data["totals"]["drafts"] == 3
    assert "Merged into FND-001, reported as FND-001" in pg.locator(
        '#sp-content .sp-item[data-key="FND-002"] .sp-after').inner_text()


def test_a_funnel_that_disagrees_with_the_run_says_so(page) -> None:
    """The run's own refined record against the rows: a difference is shown, never smoothed over."""
    pg, base, runs, _replay = page
    log = runs / RUN / "progress.jsonl"
    log.write_text(log.read_text().replace('"revised": 1, "unchanged": 1', '"revised": 2, "unchanged": 0'))
    open_log(pg, base, RUN)
    pg.wait_for_function("!document.querySelector('#funnel').hidden")
    check = pg.locator("#funnel .fcheck")
    assert "warn" in (check.get_attribute("class") or "")
    assert "The run's refined record: 2 revised, 0 unchanged" in check.inner_text()


def test_a_finished_shard_lists_its_file_not_its_stream(page) -> None:
    """Once the shard's answer is written, the panel lists it in full and no longer the streamed titles."""
    pg, base, _runs, _replay = page
    open_log(pg, base, RUN)
    open_panel(pg, "assess 1/2")
    assert pg.locator("#sp-calls .callrow").count() == 1 and pg.locator("#sp-calls .cdraft").count() == 0


def test_a_chip_opens_its_definition_with_its_source(page) -> None:
    pg, base, _runs, _replay = page
    open_log(pg, base, RUN)
    open_panel(pg, "assess 1/2")
    first = pg.locator('#sp-content .sp-list[data-list="findings"] .sp-item').first
    chip = first.locator('.chip[data-term="sev-high"]')
    chip.click()
    pg.wait_for_selector(".term-def .term-entry")
    assert chip.get_attribute("aria-expanded") == "true"
    text = pg.locator(".term-def").inner_text()
    assert "high" in text and "From prompts/system.md:" in text
    chip.click()                                               # a second click closes it
    assert pg.locator(".term-def").count() == 0
    pg.locator('#sp-content .sp-list[data-list="findings"] .legend-btn').click()
    legend = pg.locator('#sp-content .sp-list[data-list="findings"] .term-legend')
    assert "draft, unverified" in legend.inner_text() and "n/N (shard marker)" not in legend.inner_text()
    pg.locator("#sp-close").click()                            # the feed is back in the panel's place
    pg.locator('#drafts .draft .chip[data-term="run-shard"]').first.click()
    assert "n/N (shard marker)" in pg.locator(".term-def").inner_text()


def test_the_panel_is_reachable_by_keyboard(page) -> None:
    pg, base, _runs, _replay = page
    open_log(pg, base, RUN)
    btn = pg.locator('[data-panel="merge"]')
    btn.focus()
    pg.keyboard.press("Enter")
    pg.wait_for_function("window.SIT.state.panel && window.SIT.state.panel.data !== null")
    assert btn.get_attribute("aria-expanded") == "true"
    assert pg.evaluate("document.activeElement.id") == "sp-title"
    pg.keyboard.press("Escape")
    assert pg.locator("#stage-panel").is_hidden() and btn.get_attribute("aria-expanded") == "false"
    assert pg.evaluate("document.activeElement.dataset.panel") == "merge"


def test_on_the_replayed_rehearsal_every_panel_lists_its_count(page) -> None:
    """Real data: the replayed run's every stage panel lists as many items as the server read, and the funnel's rows
    add up to the merged drafts and agree with the run's own records."""
    pg, base, _runs, replay = page
    open_log(pg, base, replay)
    keys = pg.evaluate("[...document.querySelectorAll('.track .name-btn')].map((b) => b.dataset.panel)")
    assert "merge" in keys and any(k.startswith("assess ") for k in keys)
    for key in keys:
        data = open_panel(pg, key)
        assert not data.get("unreadable"), key
        for lst in data["lists"]:
            assert pg.locator(f'#sp-content .sp-list[data-list="{lst["key"]}"] .sp-item').count() == lst["count"]
        assert pg.evaluate(NO_CLIP) == [], key
    pg.wait_for_function("!document.querySelector('#funnel').hidden")
    assert not pg.locator("#funnel .fcheck.warn").count(), pg.locator("#funnel .fcheck").inner_text()
