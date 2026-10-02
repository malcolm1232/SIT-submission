"""``sit-review selftest`` and ``sit-review preflight``.

selftest: runs the full pipeline offline on the built-in fixture in
``sit_review_agent/fixtures/selftest/`` (an invented "campus room-booking" design, prompt-safe:
``design.pages.txt``; tool cassettes under ``cassettes/``; a scripted :class:`FakeGateway`
response per phase to be added as ``script.json``) with ``transport=replay`` (strict), then runs
:func:`sit_review_agent.invariants.check_all` on the produced Review and run directory. No key and
no network are needed (ADR-008). ``make smoke`` wraps it (runbook §1, ≤ 60 s).

preflight: keys present (by name only), ``models.retrieve`` + 1-token call, each enabled MCP
server initialised and listed (with ``--warm``: in parallel with a 150 s cold-start allowance,
then pinged every ``--keep-warm`` seconds), fallback run directories present (runbook §2-§3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

from sit_review_agent.config import EffectiveConfig
from sit_review_agent.invariants import InvariantResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "selftest"


#: ``DOC-`` ID the orchestrator gives ``design.pages.txt`` (``phases.ingest.doc_id_for``).
FIXTURE_DOC_ID = "DOC-design"
#: The one search the scripted research turn issues; its cassette is under ``cassettes/tools/``.
FIXTURE_QUERY = "transactional e-mail service plan daily sending limit"
FIXTURE_TOOL = "mcp-internet-search__search"
#: Selftest wall-time budget (``make smoke`` allows 60 s for everything).
SELFTEST_MAX_S = 60.0

# Verbatim passages of design.pages.txt (canonical form) the script quotes.
_Q_OVERVIEW = "The service lets students reserve study rooms for one-hour slots across campus."
_Q_LOAD = "Peak exam-week days generate about 5,000 bookings, each with one reminder."
_Q_MAIL = ("The selected e-mail service has no daily sending limit, so reminders are sent individually as each "
           "slot approaches.")
_Q_A11Y = ("Every booking screen is tested against WCAG 2.2 level AA with automated checks and a manual "
           "screen-reader pass.")
_Q_DECISION = "D-3 Confirmed: the booking front end is built from the campus design system component library."


def _anchor(section: str, page: int, quote: str, req: list[str] | None = None) -> dict[str, object]:
    return {"doc_id": FIXTURE_DOC_ID, "section_ref": section, "requirement_ids": req or [], "quote": quote,
            "page": page}


def _external_ids(ledger: list[dict[str, object]]) -> list[str]:
    return [str(e["evidence_id"]) for e in ledger if e.get("source_type") == "external"
            and e.get("read_before_cite")] or [str(e["evidence_id"]) for e in ledger
                                               if e.get("source_type") == "external"] or ["EV-001"]


def _findings(ev: str, *, refined: bool) -> list[dict[str, object]]:
    """FND-001 (refinement with external evidence; its second anchor cites the wrong page so the
    verify repair turn is exercised), FND-002 (strength, no change, preserves AD-001), FND-003
    (needs_testing: next step + unresolved), FND-004 (an invented quote: stays unresolved, so the
    finding is reported as unverified)."""
    return [
        {"id": "FND-001", "rank": 1, "kind": "risk", "category": "unsupported_or_incorrect_claim", "severity": "high",
         "confidence": 0.92 if refined else 0.85, "disposition": "refinement_now",
         "secondary_dispositions": ["needs_testing"], "title": "E-mail plan cannot send peak-day reminders",
         "statement": "Section 6.2 assumes the e-mail service has no daily sending limit, but the published plan "
                      "allows 2,000 messages a day, below the 5,000 reminders sent on peak exam-week days, so "
                      "most peak-day reminders would be rejected.",
         "doc_anchors": [_anchor("6.2", 11, _Q_MAIL), _anchor("4.1", 2, _Q_LOAD)],
         "evidence": [{"evidence_id": ev, "source_type": "external",
                       "quote": "The Starter plan allows up to 2,000 messages per day.", "supports_claim": True,
                       "derived_from": []}],
         "recommendation": {"issue": "The reminder design relies on a sending limit the chosen plan does not have.",
                            "rationale": "Reminders over the daily quota are rejected, so the plan rather than the "
                                         "design decides which students are reminded.",
                            "expected_benefit": "Every booking receives its reminder on peak days as well.",
                            "change_summary": "In 6.2, state the plan's daily quota and move to a plan that allows "
                                              "at least 10,000 messages a day.",
                            "objective_refs": ["Reminder before each slot"], "supporting_evidence_ids": [ev],
                            "verification": "Peak-day load test with 5,000 reminders in one day."},
         "no_change_rationale": None,
         "next_step": {"owner": "Notification service owner", "action": "Confirm the contracted daily quota."},
         "affected_decisions": [], "acknowledged_in_doc": False, "tags": ["notifications"], "reassessment": None,
         "criterion_ids": ["claims_and_external_constraints"]},
        {"id": "FND-002", "rank": 2, "kind": "strength", "category": None, "severity": None, "confidence": 0.85,
         "disposition": "no_change", "secondary_dispositions": [],
         "title": "Accessibility is verified, not just promised",
         "statement": "Section 11.3 backs the accessibility objective with automated checks and a manual "
                      "screen-reader pass on every booking screen, so it is verifiable as written.",
         "doc_anchors": [_anchor("11.3", 18, _Q_A11Y)], "evidence": [], "recommendation": None,
         "no_change_rationale": "Automated checks alone miss screen-reader problems; the manual pass covers them.",
         "next_step": None,
         "affected_decisions": [{"registry_id": "AD-001", "relation": "preserves",
                                 "justification": "The screens come from the campus design system (D-3)."}],
         "acknowledged_in_doc": False, "tags": ["accessibility"], "reassessment": None,
         "criterion_ids": ["fitness_for_objectives"]},
        {"id": "FND-003", "rank": 3, "kind": "validation_need", "category": "acceptance_criterion_cannot_validate",
         "severity": "medium", "confidence": 0.7, "disposition": "needs_testing", "secondary_dispositions": [],
         "title": "Peak-day reminder volume is not tested",
         "statement": "Section 4.1 sizes peak days at about 5,000 bookings with one reminder each, but no test "
                      "shows that the reminder path delivers that volume within one day.",
         "doc_anchors": [_anchor("4.1", 6, _Q_LOAD)],
         "evidence": [{"evidence_id": ev, "source_type": "external",
                       "quote": "Higher plans allow 10,000 or more messages per day.", "supports_claim": True,
                       "derived_from": []}],
         "recommendation": {"issue": "Peak-day reminder delivery is asserted but never demonstrated.",
                            "rationale": "Only a load test at peak volume shows the quota and the worker hold.",
                            "expected_benefit": "Evidence that every peak-day booking is reminded on time.",
                            "change_summary": "Add a peak-day load test of 5,000 reminders to the acceptance "
                                              "criteria for section 4.1.",
                            "objective_refs": ["Reminder before each slot"], "supporting_evidence_ids": [ev],
                            "verification": None},
         "no_change_rationale": None,
         "next_step": {"owner": "Test lead", "action": "Design and run the peak-day reminder load test."},
         "affected_decisions": [], "acknowledged_in_doc": False, "tags": ["testing"], "reassessment": None,
         "criterion_ids": ["verifiability"]},
        {"id": "FND-004", "rank": 4, "kind": "gap", "category": "missing_or_unverifiable_requirement",
         "severity": "low", "confidence": 0.4, "disposition": "refinement_now", "secondary_dispositions": [],
         "title": "Room cancellation window is unspecified",
         "statement": "The design does not say how late a student may cancel a booking.",
         "doc_anchors": [_anchor("1", 2, "Students may cancel a booking at any time before the slot begins "
                                         "without any penalty.")],
         "evidence": [{"evidence_id": ev, "source_type": "external", "quote": None, "supports_claim": True,
                       "derived_from": []}],
         "recommendation": {"issue": "Late cancellations leave rooms empty during peak days.",
                            "rationale": "A stated cancellation window lets others rebook the room in time.",
                            "expected_benefit": "Fewer empty rooms on peak days for students who need them.",
                            "change_summary": "State a cancellation window in the booking rules of section 1.",
                            "objective_refs": ["Reserve study rooms"], "supporting_evidence_ids": [ev],
                            "verification": None},
         "no_change_rationale": None, "next_step": None, "affected_decisions": [], "acknowledged_in_doc": False,
         "tags": [], "reassessment": None, "criterion_ids": ["requirement_completeness"]},
    ]


def fixture_script(criteria_ids: list[str]) -> dict[str, list[object]]:
    """The scripted model responses for every phase of the selftest run (the "fixture script").

    Entries are ``FakeResponse`` objects, or callables ``(ledger_entries, request) -> FakeResponse``
    resolved at call time so findings cite the ``EV-`` IDs research actually created (the model
    may only cite what is in the ledger)."""
    from sit_review_agent.llm.gateway import FakeResponse, ToolUse

    def final_research(ledger: list[dict[str, object]], _req: object) -> FakeResponse:
        ids = _external_ids(ledger)
        return FakeResponse(parsed={"answers": [{"question_id": "RQ-001", "status": "answered",
                                                 "summary": "The published plan allows 2,000 messages a day.",
                                                 "evidence_ids": ids[:1]}],
                                    "stop_requested": True, "stop_rationale": "The one external premise is resolved."})

    def assess(ledger: list[dict[str, object]], _req: object) -> FakeResponse:
        ev = _external_ids(ledger)[0]
        used = {"claims_and_external_constraints": ["FND-001"], "fitness_for_objectives": ["FND-002"],
                "verifiability": ["FND-003"], "requirement_completeness": ["FND-004"]}
        coverage = [{"criterion_id": c, "outcome": "findings" if c in used else "no_issue",
                     "finding_ids": used.get(c, []), "note": "selftest"} for c in criteria_ids]
        return FakeResponse(parsed={
            "findings": _findings(ev, refined=False),
            "sound_areas": [{"section_refs": ["11.3"], "why_sound": "Accessibility is verified by automated and "
                             "manual testing.", "doc_anchors": [_anchor("11.3", 18, _Q_A11Y)], "evidence_ids": [],
                             "related_finding_ids": ["FND-002"]}],
            "coverage": coverage})

    def refine(ledger: list[dict[str, object]], _req: object) -> FakeResponse:
        ev = _external_ids(ledger)[0]
        return FakeResponse(parsed={
            "findings": _findings(ev, refined=True),
            "revisions": [{"finding_id": "FND-001", "change": "revised", "reason": "Confidence raised: the quota "
                           "is stated by the provider itself.", "evidence_ids": [ev]},
                          *[{"finding_id": f"FND-00{i}", "change": "unchanged", "reason": "Still accurate.",
                             "evidence_ids": []} for i in (2, 3, 4)]]})

    def research_final(n: int) -> list[object]:
        return [final_research for _ in range(n)]

    understand = FakeResponse(parsed={
        "intent_summary": {
            "statement": "A campus service that lets students reserve study rooms for one-hour slots, with a "
                         "reminder before each slot and accessible booking screens.",
            "objectives": [{"ref": None, "text": "Reserve study rooms for one-hour slots"},
                           {"ref": None, "text": "Reminder before each slot"}],
            "constraints": [{"ref": "D-3", "text": "The front end uses the campus design system components."}],
            "key_assumptions": [{"ref": None, "text": "Peak exam-week days bring about 5,000 bookings."}],
            "doc_anchors": [_anchor("1", 2, _Q_OVERVIEW)]},
        "registry": [{"type": "approved_decision", "doc_ref": "D-3",
                      "statement": "The booking front end is built from the campus design system component library.",
                      "doc_anchor": _anchor("20", 19, _Q_DECISION, ["D-3"])}],
        "document_version": "1.0", "review_inputs_found": []})
    plan = FakeResponse(parsed={
        "questions": [{"id": "RQ-001", "criterion_id": "claims_and_external_constraints",
                       "question": "Does the selected e-mail service plan have a daily sending limit below the "
                                   "peak reminder volume?",
                       "rationale": "Section 6.2 claims there is no limit; peak days need about 5,000 reminders.",
                       "needs_external": True, "capability": "search", "queries": [FIXTURE_QUERY],
                       "section_refs": ["6.2"]}],
        "criteria_skipped": []})
    research_tool = FakeResponse(tool_uses=[ToolUse(id="toolu_selftest_1", name=FIXTURE_TOOL,
                                                    input={"query": FIXTURE_QUERY})])
    verify = FakeResponse(parsed={"repairs": [{"owner_id": "FND-001", "anchor_index": 1,
                                               "doc_anchor": _anchor("4.1", 6, _Q_LOAD)}]})
    report = FakeResponse(parsed={
        "verdict": {"label": "fit_with_conditions",
                    "rationale": "Booking and accessibility are sound; peak-day reminders fail until the e-mail "
                                 "quota is addressed.",
                    "confidence": 0.75,
                    "conditions": [{"text": "Move to an e-mail plan whose daily quota covers peak-day reminders.",
                                    "finding_ids": ["FND-001"]}],
                    "per_objective": [{"objective_ref": "Reminder before each slot", "label": "fit_with_conditions",
                                       "finding_ids": ["FND-001", "FND-003"]},
                                      {"objective_ref": "Reserve study rooms for one-hour slots", "label": "fit",
                                       "finding_ids": ["FND-002"]}],
                    "what_would_change_it": "A contract showing a daily quota above peak volume."},
        "unresolved": [{"text": "Peak-day reminder delivery has not been demonstrated.", "finding_ids": ["FND-003"],
                        "next_step": {"owner": "Test lead", "action": "Run the peak-day reminder load test."}}],
        "limitations": []})
    return {"understand": [understand], "plan": [plan],
            "research": [research_tool, *research_final(6)],
            "assess": [assess, assess], "refine": [refine, refine], "verify": [verify], "report": [report, report]}


def fixture_gateway(run_dir: object, *, clock: object = None, model: str = "claude-opus-5-5",
                    criteria_ids: list[str] | None = None) -> object:
    """``FakeGateway`` loaded with :func:`fixture_script` (``transport: fake``). Script entries that
    are callables are resolved against the run's ledger journal when their turn comes."""
    from sit_review_agent.config import load_config
    from sit_review_agent.llm.gateway import FakeGateway, LLMRequest, LLMResult
    from sit_review_agent.rundir import JsonlWriter

    if criteria_ids is None:
        eff = Path(run_dir.effective_config) if hasattr(run_dir, "effective_config") else None  # type: ignore[union-attr]
        if eff is not None and eff.is_file():
            import json

            data = json.loads(eff.read_text(encoding="utf-8"))
            criteria_ids = [c["id"] for c in data["criteria"]["criteria"]]
        else:
            criteria_ids = load_config().criteria.ids()

    class _FixtureGateway(FakeGateway):
        async def call(self, request: LLMRequest) -> LLMResult:  # type: ignore[type-arg]
            q = self.script.get(str(request.phase))
            if q and callable(q[0]):
                entries = JsonlWriter(run_dir.ledger_journal).read()  # type: ignore[union-attr]
                q[0] = q[0](entries, request)
            return await super().call(request)

    return _FixtureGateway(fixture_script(criteria_ids), run_dir=run_dir, model=model, clock=clock)  # type: ignore[arg-type]


def selftest_config(workdir: Path) -> EffectiveConfig:
    """The repo config with ``transport: fake`` over the fixture cassettes, only the search server
    enabled, no fault schedule or plan approval, and runs under ``workdir``."""
    from sit_review_agent.config import ConfigOverrides, Transport, load_config

    cfg = load_config(overrides=ConfigOverrides(transport=Transport.FAKE,
                                                replay_fixtures=str(FIXTURE_DIR / "cassettes")))
    servers = [s.model_copy(update={"enabled": s.name == "mcp-internet-search",
                                    "allow_tools": ["*"] if s.name == "mcp-internet-search" else s.allow_tools})
               for s in cfg.tools.servers]
    if not any(s.name == "mcp-internet-search" for s in servers):
        from sit_review_agent.config import ServerConfig

        servers.append(ServerConfig(name="mcp-internet-search", enabled=True, allow_tools=["*"]))
    agent = cfg.agent.model_copy(update={"run_root": str(workdir), "fault_schedule": None, "plan_approval": False,
                                         "replay": cfg.agent.replay.model_copy(update={"strict": True})})
    endpoints = cfg.endpoints.model_copy(update={"servers": {**cfg.endpoints.servers, "mcp-internet-search":
                                                             cfg.endpoints.servers.get("mcp-internet-search",
                                                                                       "https://selftest.invalid/mcp")}})
    return cfg.model_copy(update={"agent": agent, "tools": cfg.tools.model_copy(update={"servers": servers}),
                                  "endpoints": endpoints})


def _comparable(report: dict[str, object]) -> dict[str, object]:
    """A report without the parts that legitimately differ between two runs of the same inputs
    (run IDs and the run manifest)."""
    import copy

    r = copy.deepcopy(report)
    r.pop("run_manifest", None)
    meta = dict(r["metadata"])  # type: ignore[arg-type]
    meta.pop("run_id", None)
    meta.pop("review_id", None)
    r["metadata"] = meta
    return r


async def run_selftest(workdir: Path | None = None) -> list[InvariantResult]:
    """Run the offline pipeline in ``workdir`` (default: a temp dir) and return INV-03..INV-10.

    Two runs of the bundled fixture (``design.pages.txt``, strict cassettes, the scripted
    ``FakeGateway``; no key, no network): one straight through, and one interrupted (Ctrl-C) at
    the start of ``refine`` and then resumed. The result holds INV-03..INV-10 of the first run,
    followed by ``selftest:*`` checks: report schema, explain, resume (exit 130 then 0, same
    report, no repeated tool call, no duplicate ledger ID), research evidence cited, anchor repair
    (exactly one repair call), and wall time."""
    import json
    import tempfile
    import time

    from sit_review_agent.clock import FakeClock
    from sit_review_agent.invariants import check_all, spec_validator
    from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
    from sit_review_agent.phases import default_phases
    from sit_review_agent.progress import NullProgress
    from sit_review_agent.report.explain import explain, format_explain
    from sit_review_agent.rundir import JsonlWriter, RunDir
    from sit_review_agent.states import PhaseName

    t0 = time.monotonic()
    tmp = None
    if workdir is None:
        tmp = tempfile.TemporaryDirectory(prefix="sit-selftest-")
        workdir = Path(tmp.name)
    try:
        cfg = selftest_config(Path(workdir))
        pdf = FIXTURE_DIR / "design.pages.txt"
        results: list[InvariantResult] = []

        def check(name: str, problems: list[str]) -> None:
            results.append(InvariantResult(inv_id=f"selftest:{name}", passed=not problems, problems=problems))

        # ---- run 1: straight through
        out1 = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="selftest-full"), clock=FakeClock(),
                                progress=NullProgress())
        rd1 = RunDir(out1.run_dir)
        if out1.exit_code != 0 or not rd1.report_json.is_file():
            failure = rd1.failure.read_text(encoding="utf-8") if rd1.failure.is_file() else "no failure.json"
            check("run", [f"exit {out1.exit_code}: {failure[:1500]}"])
            return results
        report1 = json.loads(rd1.report_json.read_text(encoding="utf-8"))
        results += check_all(report1, rd1.root)
        check("schema", [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                         for e in spec_validator("Review").iter_errors(report1)])

        # ---- explain on the produced run directory
        probs: list[str] = []
        if report1["findings"]:
            fid = report1["findings"][0]["id"]
            try:
                text = format_explain(explain(rd1.root, fid))
                for needle in (fid, "Document anchors", "Evidence", "History", "LLM calls"):
                    if needle not in text:
                        probs.append(f"explain output lacks {needle!r}")
            except Exception as exc:  # noqa: BLE001 - reported as a failed check
                probs.append(f"explain {fid}: {type(exc).__name__}: {exc}")
            try:
                explain(rd1.root, "FND-999")
                probs.append("explain accepted an unknown finding ID")
            except KeyError:
                pass
        else:
            probs.append("no findings to explain")
        check("explain", probs)

        # ---- research evidence and the anchor repair turn
        cited_ext = {e["evidence_id"] for f in report1["findings"] for e in f["evidence"]
                     if e["source_type"] == "external"}
        check("evidence", [] if cited_ext else ["no external ledger entry is cited (research produced no evidence "
                                                "from the fixture cassette)"])
        anchors = json.loads(rd1.anchors.read_text(encoding="utf-8"))
        repairs = [e for e in JsonlWriter(rd1.llm_log).read() if e.get("purpose") == "anchor_repair"]
        probs = []
        if anchors["summary"]["repaired"] < 1:
            probs.append("no anchor was repaired")
        if len(repairs) != 1:
            probs.append(f"{len(repairs)} anchor-repair calls (expected exactly 1)")
        check("anchor_repair", probs)

        # ---- run 2: interrupted at the start of refine, then resumed (ADR-009)
        class _Interrupt:
            name = PhaseName.REFINE

            async def run(self, ctx: object) -> object:
                raise KeyboardInterrupt

        phases = default_phases()
        phases[PhaseName.REFINE] = _Interrupt()  # type: ignore[assignment]
        out2 = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="selftest-resume"), phases=phases,
                                clock=FakeClock(), progress=NullProgress())
        rd2 = RunDir(out2.run_dir)
        probs = []
        if out2.exit_code != 130:
            probs.append(f"interrupted run exited {out2.exit_code}, expected 130")
        ckpts = sorted(p.name for p in rd2.checkpoints.glob("*.json"))
        if not ckpts or not ckpts[-1].endswith("-assess.json"):
            probs.append(f"last checkpoint before resume is {ckpts[-1:] or 'none'}, expected assess")
        tools_before = len(JsonlWriter(rd2.tools_log).read())
        out3 = await resume_run(rd2.root, cfg, clock=FakeClock(), progress=NullProgress())
        if out3.exit_code != 0 or not rd2.report_json.is_file():
            failure = rd2.failure.read_text(encoding="utf-8") if rd2.failure.is_file() else ""
            probs.append(f"resume exited {out3.exit_code} {failure[:800]}")
        else:
            report2 = json.loads(rd2.report_json.read_text(encoding="utf-8"))
            if _comparable(report2) != _comparable(report1):
                probs.append("resumed report differs from the uninterrupted report")
            bad = [f"{r.inv_id}: {r.problems}" for r in check_all(report2, rd2.root) if not r.passed]
            probs += [f"resumed run: {b}" for b in bad]
            ids = [e["evidence_id"] for e in JsonlWriter(rd2.ledger_journal).read()]
            if len(ids) != len(set(ids)):
                probs.append("duplicate ledger IDs after resume")
            new_calls = [e for e in JsonlWriter(rd2.tools_log).read()[tools_before:] if not e.get("replayed")]
            if new_calls:
                probs.append(f"{len(new_calls)} tool call(s) repeated live after resume")
        check("resume", probs)
        elapsed = time.monotonic() - t0
        check("wall_time", [] if elapsed <= SELFTEST_MAX_S else [f"{elapsed:.1f} s > {SELFTEST_MAX_S:.0f} s"])
        results[-1] = InvariantResult(inv_id="selftest:wall_time", passed=results[-1].passed,
                                      problems=results[-1].problems, reason=f"{elapsed:.1f} s")
        return results
    finally:
        if tmp is not None:
            tmp.cleanup()


async def run_preflight(config: EffectiveConfig, *, warm: bool = False, keep_warm_s: int | None = None,
                        mcp: Any | None = None, llm: Any | None = None, stream: TextIO | None = None) -> bool:
    """Print the preflight status table; return True if every dependency is green or its
    degraded mode is named.

    Rows (robustness DEMO-14, INF-08, LLM-11; runbook §2-§3):

    * the MCP key: the env var named by ``tools.auth_env`` is set (its value is never printed);
      unset with servers enabled is a FAIL that names ``--no-tools`` (INF-08);
    * each enabled MCP server: ``initialize`` + ``tools/list`` through
      :class:`~sit_review_agent.tools.gateway.MCPToolGateway` (all servers in parallel). Without
      ``--warm`` the connect allowance is capped at 20 s with no cold-start retry (a quick
      reachability check); with ``--warm`` it is the full ``connect_timeout_s`` (150 s) plus
      ``cold_start_retries``, and ``--keep-warm S`` then re-lists every server every S seconds until
      interrupted. One unreachable server is a WARN (the run continues without it); every server
      unreachable, or an auth refusal, is a FAIL (the run would be doc-only);
    * the LLM backend: ``build_llm_gateway(...).preflight()`` (``claude --version`` for
      ``claude_code``; a 1-token call naming ``ANTHROPIC_API_KEY`` for ``anthropic_api``);
    * fallback data: the cassette directory and replay fixtures exist (WARN only).

    ``mcp``, ``llm`` and ``stream`` let tests inject fakes and capture the table. The CLI maps
    ``False`` to a non-zero exit code.
    """
    import os
    import sys
    import tempfile

    from sit_review_agent.clock import SystemClock
    from sit_review_agent.errors import AgentError
    from sit_review_agent.progress import ConsoleProgress
    from sit_review_agent.tools.cassette import Redactor
    from sit_review_agent.tools.gateway import MCPToolGateway, ServerHealth

    out = stream or sys.stdout
    redact = Redactor.from_env((config.tools.auth_env, "ANTHROPIC_API_KEY"))
    rows: list[tuple[str, str, str]] = []
    ok = True
    tools_cfg = config.tools
    enabled = tools_cfg.enabled_servers()
    key_set = bool(os.environ.get(tools_cfg.auth_env, "").strip())

    if not enabled:
        rows.append(("MCP servers", "SKIP", "every server disabled: document-only review (--no-tools)"))
    elif not key_set:
        ok = False
        rows.append((f"MCP key {tools_cfg.auth_env}", "FAIL",
                     f"not set: export {tools_cfg.auth_env}, or run with --no-tools for a document-only review"))
    else:
        rows.append((f"MCP key {tools_cfg.auth_env}", "OK", "set (value not shown)"))

    gw = mcp
    if enabled and key_set:
        if gw is None:
            check_cfg = tools_cfg if warm else tools_cfg.model_copy(
                update={"connect_timeout_s": min(tools_cfg.connect_timeout_s, 20.0), "cold_start_retries": 0})
            gw = MCPToolGateway(check_cfg, config.endpoints.servers, clock=SystemClock(),
                                progress=ConsoleProgress(stream=out))
        try:
            health = await gw.warm_up()
            listed = {s.server for s in await gw.list_tools()}
            up = 0
            for s in enabled:
                h = health.get(s.name, ServerHealth.DOWN)
                n = sum(1 for t in getattr(gw, "_tools", {}).get(s.name, []))
                proto = getattr(gw, "protocol_versions", {}).get(s.name)
                if h is ServerHealth.OK and s.name in listed:
                    up += 1
                    rows.append((f"MCP {s.name}", "OK", f"{n} tools" + (f", protocol {proto}" if proto else "")))
                else:
                    err = getattr(gw, "last_errors", {}).get(s.name, h.value)
                    rows.append((f"MCP {s.name}", "WARN", f"{err}; the run continues without it "
                                 f"(or --disable-tool {s.name})"))
            if getattr(gw, "auth_failed", False):
                ok = False
                rows.append(("MCP auth", "FAIL", f"the servers refused the key in {tools_cfg.auth_env}; fix it or "
                             "run with --no-tools"))
            elif up == 0:
                ok = False
                rows.append(("MCP reachability", "FAIL", "no server reachable: the run would be document-only "
                             "(--no-tools), or use --replay <fixtures>"))
            if keep_warm_s and up:
                print(redact.text(_format_rows(rows)), file=out, flush=True)
                rows = []
                clock = SystemClock()
                while True:                                  # until Ctrl-C (runbook §3, keep servers warm)
                    await clock.sleep(float(keep_warm_s))
                    for s in enabled:
                        try:
                            await gw._list_server_tools(s.name)  # noqa: SLF001 - our own gateway
                            print(f"keep-warm {s.name}: ok", file=out, flush=True)
                        except Exception as exc:  # noqa: BLE001
                            print(redact.text(f"keep-warm {s.name}: {exc}"), file=out, flush=True)
        finally:
            await gw.aclose()

    backend = config.agent.llm.backend
    if backend == "anthropic_api" and not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        rows.append(("LLM key ANTHROPIC_API_KEY", "FAIL", "not set (llm.backend: anthropic_api)"))
        ok = False
    with tempfile.TemporaryDirectory(prefix="sit-preflight-") as tmp:
        try:
            gateway = llm
            if gateway is None:
                from sit_review_agent.llm.backend import build_llm_gateway
                from sit_review_agent.rundir import RunDir

                gateway = build_llm_gateway(config, RunDir(Path(tmp) / "preflight").create(), clock=SystemClock())
            await gateway.preflight()
            rows.append((f"LLM backend {backend}", "OK", f"model {config.agent.model}"))
        except NotImplementedError as exc:
            ok = False
            rows.append((f"LLM backend {backend}", "FAIL", f"not built yet ({exc})"))
        except AgentError as exc:
            ok = False
            rows.append((f"LLM backend {backend}", "FAIL", str(exc)))
        except Exception as exc:  # noqa: BLE001 - preflight reports, never crashes
            ok = False
            rows.append((f"LLM backend {backend}", "FAIL", f"{type(exc).__name__}: {exc}"))

    cassettes = config.resolve_repo_path(config.agent.record.cassette_dir)
    rows.append(("Cassettes", "OK" if cassettes.exists() else "WARN",
                 str(cassettes) if cassettes.exists() else f"{cassettes} missing: no --replay fallback recorded"))
    if config.agent.replay.fixtures:
        fx = config.resolve_repo_path(config.agent.replay.fixtures)
        rows.append(("Replay fixtures", "OK" if fx.exists() else "WARN", str(fx)))

    print(redact.text(_format_rows(rows)), file=out, flush=True)
    print("preflight: " + ("OK" if ok else "FAILED (see the rows marked FAIL)"), file=out, flush=True)
    return ok


def _format_rows(rows: list[tuple[str, str, str]]) -> str:
    if not rows:
        return ""
    w0 = max(len(r[0]) for r in rows)
    lines = [f"{'check'.ljust(w0)}  status  detail", f"{'-' * w0}  ------  ------"]
    lines += [f"{a.ljust(w0)}  {b.ljust(6)}  {c}" for a, b, c in rows]
    return "\n".join(lines)
