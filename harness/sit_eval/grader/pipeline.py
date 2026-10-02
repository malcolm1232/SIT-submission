"""The lecturer grader pipeline (GR §6.1) behind :func:`grade_review` and ``sit-eval grade run``.

0. Preprocess: grader-facing projection (``projection.py``), canonical page text through the
   agent's own ingest, injection pre-scan, verdict fact.
1. Segment: skipped. Every Tier A condition emits a structured Review, whose ``Finding.id`` values
   are used verbatim (grader_prompt.md §1, §4: the segmenter is only for unstructured reviews).
2. Pass A x ``samples``: findings shuffled with a recorded seed per sample, framing withheld.
3. Verify (no model): anchors and evidence quotes (``verify.py``); grader design quotes.
4. Pass B x ``samples``: intact review plus the merged Pass A table.
5-6. Aggregate in code (``scoring.py``); a third Pass B sample on disagreement; median per dimension.
7. Key-aware (optional): Pass B again in fresh contexts with the key; diagnostic counts only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sit_eval import lc12
from sit_eval.grader import answer_key as ak
from sit_eval.grader import costs, prompts, schemas, scoring, verify
from sit_eval.grader.projection import (
    evidence_register,
    leak_report,
    load_review,
    project_review,
    review_full_text,
    shuffle_findings,
)
from sit_eval.judge import JudgeClient, JudgeError, JudgeRequest, JudgeResult
from sit_review_agent.ingest import Document, ingest

DEFAULT_MODEL = "claude-opus-5-5"     # prereg grader.primary.model
DEFAULT_EFFORT = "high"               # prereg grader.primary.effort
MAX_TOKENS = 32000
CALL_LOG = "grader_calls.jsonl"
NONE = "NONE"
LC12_KEY_BLIND_ALTERNATIVE = "or drop --answer-key for the key-blind grade, which reads no key"
CONVENTIONS = [
    "Segmenter not run: the review is a structured Review; FND IDs used verbatim (grader_prompt.md §1, §4).",
    "Pass A hides each finding's rank and resolves affected_decisions against the decision registry.",
    "Caps per sample, then median per dimension over samples (two samples: their mean); caps re-applied "
    "to the medians with the median count of material verified-false hallucinations.",
    "G3 with >= 2 hallucinations also keeps D9 <= 2 and grade <= C.",
    "Samples that disagree on the count of material verified-false hallucinations are flagged for human review.",
    "A third Pass B sample is added only to a two-sample grade (prereg: 2, a third on disagreement).",
    "G4 (verdict present) is computed in code from the structured review.",
    "G5 fails on the harness injection pre-scan or any model flag (Pass A or B); needs human review.",
    "A verified_false hallucination whose design_quote is not in the design text is downgraded to suspected.",
    "One repair call per sample if the output fails the full schema; the repair note is a harness addition.",
]


class GraderError(RuntimeError):
    """The grade could not be completed (judge failure or output still invalid after one repair)."""


@dataclass
class GradeResult:
    """What :func:`grade_review` returns; ``report`` is the content of ``grade.json``."""

    report: dict[str, Any]
    out_dir: Path
    grade_json: Path
    grade_md: Path
    call_log: Path

    @property
    def S(self) -> float | None:  # noqa: N802 - the rubric's name for the weighted score
        return self.report.get("S")

    @property
    def grade(self) -> str | None:
        return self.report.get("grade")

    @property
    def passed(self) -> bool | None:
        return self.report.get("pass")

    @property
    def dimensions(self) -> dict[str, float]:
        return dict(self.report.get("dimensions_final") or {})


def load_document(src: str | Path | Document, *, doc_id: str | None = None) -> Document:
    """A PDF through the agent's ingest, or an already canonical page-marked ``.txt``."""
    if isinstance(src, Document):
        return src
    p = Path(src)
    if p.suffix.lower() == ".pdf":
        return ingest(p, doc_id=doc_id)
    text = p.read_text(encoding="utf-8")
    return Document.from_page_marked_text(text, doc_id=doc_id or f"DOC-{p.stem.split('.')[0]}")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _family(model: str | None) -> str | None:
    return model.split("-")[0].lower() if model else None


def _under_review(review: dict[str, Any]) -> dict[str, Any]:
    docs = (review.get("metadata") or {}).get("documents") or []
    return next((d for d in docs if isinstance(d, dict) and d.get("role") == "under_review"),
                docs[0] if docs else {})


def _agent_models(review: dict[str, Any]) -> list[str]:
    out: set[str] = set()
    for m in (review.get("run_manifest") or {}).get("models_used") or []:
        if isinstance(m, dict):
            out.update(m.get("served_models") or [])
            if m.get("requested_model"):
                out.add(m["requested_model"])
    for f in review.get("findings") or []:
        prov = f.get("provenance") if isinstance(f, dict) else None
        if isinstance(prov, dict) and prov.get("model"):
            out.add(prov["model"])
    return sorted(out)


# ================================================================================== the grader
@dataclass
class _Grader:
    review_path: Path
    document: Document
    out_dir: Path
    judge: JudgeClient | None
    answer_key_path: Path | None = None
    v1_review_path: Path | None = None
    v1_document: Document | None = None
    samples: int = 2
    seed: int = 0
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    budget: costs.Budget = field(default_factory=costs.Budget)
    validity_tier: str = "unvalidated (GR §7 smoke calibration not yet run)"
    exploratory: bool = False      # LC12 override (--exploratory); marks every artefact
    prereg_frozen: bool = False

    # ------------------------------------------------------------------ preparation (no calls)
    def prepare(self) -> None:
        self.review = load_review(self.review_path)
        self.warnings: list[str] = []
        self.delta = self.v1_review_path is not None
        if (self.review.get("metadata") or {}).get("review_mode") == "delta" and not self.delta:
            self.warnings.append("review_mode is delta but no v1 review was given: graded without D11")
        self.mode = "key_blind+delta" if self.delta else "key_blind"
        self.dims = scoring.dims_for(self.delta)

        doc = self.document
        ur = _under_review(self.review)
        self.doc_matches = bool(ur.get("sha256_text")) and ur.get("sha256_text") == doc.sha256_text
        if not self.doc_matches:
            self.warnings.append(f"document text sha256 {doc.sha256_text[:12]} does not match the review's "
                                 f"{str(ur.get('sha256_text'))[:12]}: is this the reviewed document?")
        try:
            from sit_review_agent.invariants import spec_validator

            self.review_schema_errors = sorted(
                f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message[:200]}"
                for e in spec_validator("Review").iter_errors(self.review))[:20]
        except Exception as exc:  # noqa: BLE001 - schema check is informative only
            self.review_schema_errors = [f"schema check unavailable: {exc}"]

        self.design_text = prompts.neutralise_delimiters(doc.text)
        self.proj, self.proj_audit = project_review(self.review, design_text=doc.text)
        self.register = prompts.neutralise_delimiters(evidence_register(self.proj))
        self.review_text = prompts.neutralise_delimiters(review_full_text(self.proj))
        self.search = verify.DocSearch(doc)
        self.harness_checks = verify.verify_findings(self.proj, doc)
        self.injection_scan = verify.scan_injection(self.proj)
        self.verdict_present = verify.verdict_present(self.proj)

        self.prior_review_text = NONE
        self.prior_doc_text = NONE
        self.v1_review: dict[str, Any] | None = None
        if self.delta:
            self.v1_review = load_review(self.v1_review_path)
            v1_doc_text = self.v1_document.text if self.v1_document else ""
            v1_proj, _ = project_review(self.v1_review, design_text=v1_doc_text)
            self.prior_review_text = prompts.neutralise_delimiters(review_full_text(v1_proj))
            self.prior_doc_text = (prompts.neutralise_delimiters(self.v1_document.text) if self.v1_document
                                   else "NONE (the prior design document was not supplied to the grader)")

        self.key_loaded = ak.load_answer_key(self.answer_key_path) if self.answer_key_path else None
        self.key_ready: bool | None = None
        if self.key_loaded:
            self.key_ready, self.key_pending, self.key_reason = ak.signoff(self.key_loaded)
            self.key_legacy, self.key_id_map = ak.project_key(
                self.key_loaded, review_mode="delta" if self.delta else "full")
        self.warnings[:0] = lc12.notes(self.exploratory, prereg_frozen=self.prereg_frozen)
        if self.key_ready is False:
            self.warnings.append(f"answer key {self.answer_key_path} is not signed off ("
                                 + (self.key_reason or "scored_run_ready = false; pending: "
                                    + ", ".join(self.key_pending)) + "): "
                                 + ("key-aware diagnostic run under --exploratory (LC12 override)" if self.exploratory
                                    else "a real run refuses it without --exploratory (LC12)"))
        self.system = prompts.load_prompt("system.txt")
        self.n_findings = len(self.proj.get("findings") or [])

    def require_signed_key(self) -> None:
        """LC12: refuse a key-aware diagnostic on a key that is not signed off (key-blind grades read no key)."""
        if self.key_loaded:
            lc12.require_signed(self.answer_key_path, bool(self.key_ready), self.key_pending,
                                exploratory=self.exploratory, reason=self.key_reason,
                                alternative=LC12_KEY_BLIND_ALTERNATIVE)

    # ------------------------------------------------------------------------------ rendering
    def shuffle_seed(self, i: int) -> int:
        return self.seed * 1000 + i + 1

    def render_pass_a(self, i: int) -> tuple[str, str, list[str]]:
        sseed = self.shuffle_seed(i)
        text, order = shuffle_findings(self.proj, sseed)
        label = f"s{i + 1}"
        user = prompts.render(prompts.load_prompt("pass_a.txt"), {
            "MODE": self.mode, "SEED": f"{label}-{sseed}",
            "PASS_A_SCHEMA": schemas.schema_text(schemas.PASS_A),
            "DESIGN_DOC_PAGE_MARKED": self.design_text,
            "EVIDENCE_REGISTER": self.register,
            "SHUFFLED_FINDINGS_WITH_IDS": prompts.neutralise_delimiters(text),
        })
        return label, user, order

    def render_pass_b(self, i: int, merged_json: str, *, key_aware: bool) -> tuple[str, str, str]:
        mode = ("key_aware" if key_aware else "key_blind") + ("+delta" if self.delta else "")
        label = f"s{i + 1}"
        user = prompts.render(prompts.load_prompt("pass_b.txt"), {
            "MODE": mode, "SEED": label,
            "PASS_B_SCHEMA": schemas.schema_text(schemas.PASS_B),
            "DESIGN_DOC_PAGE_MARKED": self.design_text,
            "EVIDENCE_REGISTER": self.register,
            "PRIOR_DESIGN_DOC_PAGE_MARKED": self.prior_doc_text,
            "PRIOR_REVIEW": self.prior_review_text,
            "PASS_A_MERGED_JSON": merged_json,
            "ANSWER_KEY": prompts.neutralise_delimiters(ak.render_key(self.key_legacy)) if key_aware else NONE,
            "REVIEW_FULL_TEXT": self.review_text,
        })
        return label, mode, user

    # ------------------------------------------------------------------------------------ plan
    def plan(self) -> dict[str, Any]:
        """Planned calls and a cost estimate, without calling anything (``--dry-run``)."""
        _, ua, _ = self.render_pass_a(0)
        merged_est = "x" * (self.n_findings * 1800 + 200)
        _, _, ub = self.render_pass_b(0, merged_est, key_aware=False)
        sys_chars = len(self.system)
        a_out = costs.PASS_A_OUT_BASE + costs.PASS_A_OUT_PER_FINDING * self.n_findings
        est_a = costs.estimate_call(self.model, sys_chars + len(ua), a_out)
        est_b = costs.estimate_call(self.model, sys_chars + len(ub), costs.PASS_B_OUT)
        rows = []
        if self.n_findings:
            rows.append({"call": "Pass A", "count": self.samples, **est_a})
        rows.append({"call": "Pass B key-blind", "count": self.samples, **est_b})
        rows.append({"call": "Pass B key-blind 3rd sample (only on disagreement)", "count": 1, "conditional": True,
                     **est_b})
        if self.key_loaded:
            key_chars = len(ak.render_key(self.key_legacy))
            est_k = costs.estimate_call(self.model, sys_chars + len(ub) + key_chars, costs.PASS_B_OUT + 800)
            rows.append({"call": "Pass B key-aware (diagnostic)", "count": self.samples, **est_k})
            rows.append({"call": "Pass B key-aware 3rd sample (only on disagreement)", "count": 1,
                         "conditional": True, **est_k})
        n_min = sum(r["count"] for r in rows if not r.get("conditional"))
        n_max = sum(r["count"] for r in rows)
        usd_min = sum(r["count"] * r["cost_usd"] for r in rows if not r.get("conditional"))
        usd_max = sum(r["count"] * r["cost_usd"] for r in rows)
        lo, hi = costs.SECONDS_PER_CALL
        return {"mode": self.mode, "key_aware": bool(self.key_loaded), "findings": self.n_findings,
                "design_chars": len(self.design_text), "evidence_register_chars": len(self.register),
                "review_chars": len(self.review_text), "model": self.model, "effort": self.effort,
                "calls": rows, "calls_min": n_min, "calls_max": n_max,
                "cost_usd_min": round(usd_min, 2), "cost_usd_max": round(usd_max, 2),
                "wall_time_s": [n_min * lo, n_max * hi],
                "price_basis": "list price per MTok from research/models/cost_model.py, no caching or batch "
                               "discount (upper bound for the API path); repair calls not included",
                "warnings": list(self.warnings)}

    # ------------------------------------------------------------------------------- the calls
    def _log(self, entry: dict[str, Any]) -> None:
        with (self.out_dir / CALL_LOG).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**entry, "exploratory": self.exploratory}, ensure_ascii=False) + "\n")

    async def _call(self, purpose: str, user: str, schema_name: str, sample_index: int, out_tokens: int,
                    extra_check: Callable[[dict[str, Any]], list[str]]) -> tuple[dict[str, Any], JudgeResult]:
        assert self.judge is not None
        leaks = leak_report([self.system, user], self.review, design_text=self.document.text)
        if self.v1_review is not None:
            leaks += leak_report([user.replace(self.document.text, "")], self.v1_review,
                                 design_text=self.v1_document.text if self.v1_document else "")
        if leaks:
            raise GraderError(f"{purpose}: grader input would leak {leaks[:5]}; nothing sent")
        attempt_user = user
        for attempt in (0, 1):
            tag = purpose + (":repair" if attempt else "")
            est = costs.estimate_call(self.model, len(self.system) + len(attempt_user), out_tokens)
            self.budget.check(tag, est["cost_usd"])
            self.n_calls += 1
            stem = f"{self.n_calls:02d}_{tag.replace(':', '_')}"
            (self.out_dir / "inputs" / f"{stem}.user.txt").write_text(attempt_user, encoding="utf-8")
            req = JudgeRequest(purpose=f"grader:{tag}", system=self.system, user=attempt_user,
                               schema=schemas.llm_facing(schema_name), model=self.model, effort=self.effort,
                               max_tokens=MAX_TOKENS, sample_index=sample_index)
            t0 = time.monotonic()
            try:
                res = await self.judge.complete(req)
            except Exception as exc:  # noqa: BLE001 - any client failure ends the grade cleanly
                # A live client should raise JudgeError, but a timeout or client bug must still leave
                # grade.json, the call log and a clean CLI exit (3) instead of a traceback.
                err = str(exc) if isinstance(exc, JudgeError) else f"{type(exc).__name__}: {exc}"
                self._log({"purpose": req.purpose, "sample_index": sample_index, "ok": False,
                           "error": err[:500], "user_sha256": _sha(attempt_user)})
                raise GraderError(f"{tag}: judge failed: {err}") from exc
            cost = res.cost_usd
            if cost is None:
                cost = (costs.actual_cost(self.model, res.input_tokens, res.output_tokens)
                        if (res.input_tokens or res.output_tokens) else est["cost_usd"])
            self.budget.add(cost)
            data = res.data if isinstance(res.data, dict) else {}
            errs = schemas.errors(schema_name, data) or extra_check(data)
            self.served_models.add(res.model)
            self._log({"ts": datetime.now(UTC).isoformat(timespec="seconds"), "purpose": req.purpose,
                       "sample_index": sample_index, "model_requested": self.model, "model_served": res.model,
                       "effort": self.effort, "cost_usd": round(cost, 6), "cost_reported": res.cost_usd is not None,
                       "estimate_usd": est["cost_usd"], "input_tokens": res.input_tokens,
                       "output_tokens": res.output_tokens,
                       "elapsed_s": round(res.elapsed_s or (time.monotonic() - t0), 2),
                       "system_sha256": _sha(self.system), "user_sha256": _sha(attempt_user),
                       "user_chars": len(attempt_user), "schema": schema_name, "valid": not errs,
                       "errors": errs[:8], "input_file": f"inputs/{stem}.user.txt"})
            (self.out_dir / "outputs" / f"{stem}.json").write_text(
                json.dumps(res.data, indent=2, ensure_ascii=False), encoding="utf-8")
            if not errs:
                return data, res
            attempt_user = user + prompts.render(prompts.load_prompt("repair_note.txt"),
                                                 {"ERRORS": "\n".join(f"- {e}" for e in errs[:15])})
        raise GraderError(f"{purpose}: output invalid after one repair: {errs[:5]}")

    # ------------------------------------------------------------------------------ Pass A
    async def run_pass_a(self) -> None:
        self.pass_a: list[dict[str, Any]] = []
        if not self.n_findings:
            self.merged = {"findings": [], "hallucinations": [], "prompt_injection_flagged_in": []}
            return
        for i in range(self.samples):
            label, user, order = self.render_pass_a(i)

            def check(d: dict[str, Any], shown: list[str] = order) -> list[str]:
                got = [f.get("finding_id") for f in d.get("findings") or []]
                errs = [f"findings: missing {x}" for x in shown if x not in got]
                errs += [f"findings: {x} was not shown" for x in got if x not in shown]
                errs += [f"findings: {x} appears {got.count(x)} times" for x in set(got) if got.count(x) > 1]
                return errs

            out_tokens = costs.PASS_A_OUT_BASE + costs.PASS_A_OUT_PER_FINDING * self.n_findings
            data, _ = await self._call("passA", user, schemas.PASS_A, i, out_tokens, check)
            data = {**data, "hallucinations": verify.vet_hallucinations(data.get("hallucinations") or [],
                                                                        self.search)}
            self.pass_a.append({"seed": label, "shuffle_seed": self.shuffle_seed(i), "order": order,
                                "output": data})
        self.merged = merge_pass_a(self.pass_a, self.harness_checks)

    # ------------------------------------------------------------------------------ Pass B
    async def _pass_b_sample(self, i: int, *, key_aware: bool) -> dict[str, Any]:
        merged_json = prompts.neutralise_delimiters(json.dumps(self.merged, ensure_ascii=False))
        label, mode, user = self.render_pass_b(i, merged_json, key_aware=key_aware)

        def check(d: dict[str, Any]) -> list[str]:
            errs = [] if d.get("mode") == mode else [f"mode: expected {mode!r}, got {d.get('mode')!r}"]
            if self.delta and "D11" not in (d.get("dimensions") or {}):
                errs.append("dimensions: D11 is required in delta mode")
            return errs

        data, _ = await self._call("passB_key_aware" if key_aware else "passB", user, schemas.PASS_B, i,
                                   costs.PASS_B_OUT, check)
        return self.score_pass_b(label, data, key_aware=key_aware)

    def score_pass_b(self, label: str, data: dict[str, Any], *, key_aware: bool) -> dict[str, Any]:
        dims = {k: float(data["dimensions"][k]["score"]) for k in self.dims}
        halls = verify.vet_hallucinations(data.get("hallucinations") or [], self.search)
        n_ver, n_sus = scoring.material_verified(halls), scoring.material_suspected(halls)
        model_inj = bool((data.get("gate_facts") or {}).get("prompt_injection_detected"))
        inj = bool(self.injection_scan) or bool(self.merged.get("prompt_injection_flagged_in")) or model_inj
        sc = scoring.score(dims, delta=self.delta, n_verified=n_ver, verdict_present=self.verdict_present,
                           injection=inj)
        rec = {"seed": label, "dimensions": dims, "dimensions_capped": sc["dimensions_capped"], "S_raw": sc["S"],
               "caps_applied": sc["caps_applied"], "gates": sc["gates"], "grade": sc["grade"], "pass": sc["pass"],
               "n_material_verified": n_ver, "n_material_suspected": n_sus,
               "injection_flag": inj, "model_injection_flag": model_inj,
               "verdict_present_model": bool((data.get("verdict_extracted") or {}).get("present")),
               "hallucinations": halls, "output": {**data, "hallucinations": halls}}
        if key_aware:
            rec["key_alignment_counts"] = ak.alignment_counts(data.get("answer_key_alignment"), self.key_legacy)
        return rec

    async def run_pass_b(self, *, key_aware: bool) -> dict[str, Any]:
        recs = [await self._pass_b_sample(i, key_aware=key_aware) for i in range(self.samples)]
        dis = scoring.disagreement(recs) if len(recs) >= 2 else {"max_dim_delta": 0.0, "S_delta": 0.0}
        # prereg grader.samples: "2 per review ... a third if ...". Only a two-sample grade gets a third;
        # a grade asked for 3+ samples already has them (it used to get a 4th).
        third = len(recs) == 2 and scoring.needs_third_sample(dis)
        if third:
            recs.append(await self._pass_b_sample(len(recs), key_aware=key_aware))
        return {"samples": recs, "disagreement": {**dis, "third_sample_run": third}}

    # ------------------------------------------------------------------------------- run
    async def run(self) -> dict[str, Any]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "inputs").mkdir(exist_ok=True)
        (self.out_dir / "outputs").mkdir(exist_ok=True)
        (self.out_dir / CALL_LOG).write_text("", encoding="utf-8")
        (self.out_dir / "inputs" / "system.txt").write_text(self.system, encoding="utf-8")
        (self.out_dir / "grader_projection.json").write_text(
            json.dumps(self.proj, indent=1, ensure_ascii=False), encoding="utf-8")
        self.n_calls, self.served_models = 0, set()
        self.status, self.error = "complete", None
        self.blind: dict[str, Any] | None = None
        self.key_aware: dict[str, Any] | None = None
        self.pass_a, self.merged = [], {"findings": [], "hallucinations": [], "prompt_injection_flagged_in": []}
        try:
            await self.run_pass_a()
            self.blind = await self.run_pass_b(key_aware=False)
            if self.key_loaded:
                self.key_aware = await self.run_pass_b(key_aware=True)
        except costs.BudgetExceeded as exc:
            self.status, self.error = "aborted_budget", str(exc)
        except GraderError as exc:
            self.status, self.error = "failed", str(exc)
        return self.build_report()

    # ------------------------------------------------------------------------------ report
    def build_report(self) -> dict[str, Any]:
        lock = prompts.lock_status()
        served = sorted(self.served_models)
        agent_models = _agent_models(self.review)
        grader_family = _family(served[0] if served else self.model)
        same_family = (None if not agent_models else
                       any(_family(m) == grader_family for m in agent_models))
        fake = bool(served) and all("fake" in m for m in served)
        rep: dict[str, Any] = {
            "report_version": 1,
            "status": self.status,
            "error": self.error,
            "label": ("PLUMBING ONLY: graded by a fake judge; the scores carry no meaning." if fake else
                      f"Grader-derived score; validity tier: {self.validity_tier}"
                      + ("; same-family grader" if same_family else "")),
            "review_id": (self.review.get("metadata") or {}).get("review_id"),
            "review_path": str(self.review_path),
            "document": {"doc_id": self.document.doc_id, "title": self.document.title,
                         "page_count": self.document.page_count, "sha256_text": self.document.sha256_text,
                         "matches_review": self.doc_matches},
            "grader_model": ", ".join(served) if served else None,
            "grader_model_requested": self.model, "grader_effort": self.effort,
            "grader_prompt_version": prompts.PROMPT_VERSION,
            "grader_prompt_sha256": lock["bundle_sha256"], "grader_prompt_lock_ok": lock["ok"],
            "mode": self.mode,
            "labels": {"validity_tier": self.validity_tier, "same_family": same_family,
                       "agent_models": agent_models, "grader_family": grader_family},
            "samples": [], "disagreement": None, "dimensions_final": None, "caps_applied": [],
            "gates": None, "S": None, "grade": None, "pass": None, "hallucinations": [],
            "key_alignment_diagnostic": None, "needs_human_review": True, "human_review_reasons": [],
            **lc12.marker(self.exploratory, prereg_frozen=self.prereg_frozen),
        }
        reasons: list[str] = []
        if self.blind:
            recs = self.blind["samples"]
            final_dims = scoring.median_dims(recs, self.dims)
            n_final = float(statistics.median(r["n_material_verified"] for r in recs))
            inj = any(r["injection_flag"] for r in recs)
            final = scoring.score(final_dims, delta=self.delta, n_verified=n_final,
                                  verdict_present=self.verdict_present, injection=inj)
            halls = merge_hallucinations([(r["seed"], r["hallucinations"]) for r in recs])
            rep.update({
                "samples": [{k: r[k] for k in ("seed", "dimensions", "dimensions_capped", "S_raw", "caps_applied",
                                               "gates", "grade", "pass", "n_material_verified",
                                               "n_material_suspected", "injection_flag", "model_injection_flag",
                                               "verdict_present_model")} for r in recs],
                "disagreement": self.blind["disagreement"],
                "dimensions_final": final["dimensions_capped"], "caps_applied": final["caps_applied"],
                "gates": final["gates"], "S": final["S"], "grade": final["grade"], "pass": final["pass"],
                "material_hallucinations_verified_median": n_final,
                "hallucinations": halls,
            })
            if self.blind["disagreement"]["third_sample_run"]:
                reasons.append("samples disagreed (a dimension by >= 2 or S by >= 8); third sample run")
            elif scoring.needs_third_sample(self.blind["disagreement"]):   # 3+ samples were requested
                reasons.append("samples disagreed (a dimension by >= 2 or S by >= 8)")
            if not final["gates"]["G5"]:
                reasons.append("G5: text addressed to the grader (prompt injection) flagged")
            if any(h["severity"] == "material" and h["status"] == "suspected" for h in halls):
                reasons.append("suspected material hallucinations need verification (GR §4.3)")
            if any(h.get("harness_downgraded") for h in halls):
                reasons.append("grader cited design text that is not in the document (flag downgraded)")
            if len({r["n_material_verified"] for r in recs}) > 1:
                # e.g. one sample flags a verified-false material hallucination and the other none: the
                # median count (0.5) triggers no G3 cap, yet the merged list shows the flag as verified_false.
                reasons.append("samples disagree on the number of material verified-false hallucinations "
                               "(" + ", ".join(f"{r['n_material_verified']:g}" for r in recs) + "); G3 used the median")
            if any(r["verdict_present_model"] != self.verdict_present for r in recs):
                reasons.append("grader and harness disagree on whether an explicit verdict is present")
        else:
            reasons.append(f"grade not completed: {self.status}")
        if not self.doc_matches:
            reasons.append("document text hash does not match the review's under-review document")
        rep["needs_human_review"] = bool(reasons)
        rep["human_review_reasons"] = reasons

        if self.key_aware:
            recs = self.key_aware["samples"]
            counts = ak.aggregate_counts([r["key_alignment_counts"] for r in recs])
            rep["key_alignment_diagnostic"] = {
                "label": ak.DIAGNOSTIC_LABEL, "source": self.key_loaded["source"],
                "format": self.key_loaded["format"], "counts_median": counts,
                "per_sample": [r["key_alignment_counts"] for r in recs],
                "dimensions_diagnostic": scoring.median_dims(recs, self.dims),
                "disagreement": self.key_aware["disagreement"],
                "key_id_map": self.key_id_map,
                "scored_run_ready": bool(self.key_ready), "exploratory": self.exploratory,
            }

        anchors = [a for v in self.harness_checks.values() for a in v["doc_anchors"]]
        rep["harness_checks"] = {
            "verdict_present": self.verdict_present,
            "injection_scan": self.injection_scan,
            "anchors": {c: sum(1 for a in anchors if a["check"] == c)
                        for c in ("verified", "not_found", "other_document")},
            "per_finding": self.harness_checks,
            "review_schema_errors": self.review_schema_errors,
        }
        rep["pass_a"] = {"samples": self.pass_a, "merged_table": self.merged}
        rep["pass_b"] = {"samples": [{"seed": r["seed"], "output": r["output"]}
                                     for r in (self.blind or {}).get("samples", [])]}
        if self.key_aware:
            rep["pass_b_key_aware"] = {"label": ak.DIAGNOSTIC_LABEL,
                                       "samples": [{"seed": r["seed"], "output": r["output"]}
                                                   for r in self.key_aware["samples"]]}
        rep["projection_audit"] = self.proj_audit
        rep["calls"] = {"count": self.n_calls, "log": CALL_LOG}
        rep["budget"] = {"max_cost_usd": self.budget.max_cost_usd, "spent_usd": round(self.budget.spent_usd, 4),
                         "refused": self.budget.refused}
        rep["seed"] = self.seed
        rep["samples_requested"] = self.samples
        rep["conventions"] = CONVENTIONS
        rep["warnings"] = self.warnings
        return rep


def merge_pass_a(samples: list[dict[str, Any]], harness: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """One row per finding: fields on which the samples agree appear once, others per sample;
    the harness marks are attached; hallucinations are de-duplicated with the samples that flagged them."""
    by_id: dict[str, dict[str, dict[str, Any]]] = {}
    for s in samples:
        for rec in s["output"].get("findings") or []:
            by_id.setdefault(str(rec.get("finding_id")), {})[s["seed"]] = rec
    rows = []
    for fid in sorted(by_id):
        recs = by_id[fid]
        row: dict[str, Any] = {"finding_id": fid}
        keys = sorted({k for r in recs.values() for k in r if k != "finding_id"})
        for k in keys:
            vals = {lab: r.get(k) for lab, r in recs.items()}
            distinct = {json.dumps(v, sort_keys=True) for v in vals.values()}
            row[k] = next(iter(vals.values())) if len(distinct) == 1 else {"per_sample": vals}
        row["harness_checks"] = harness.get(fid, {})
        rows.append(row)
    halls = merge_hallucinations([(s["seed"], s["output"].get("hallucinations") or []) for s in samples])
    flagged = [s["seed"] for s in samples if s["output"].get("prompt_injection_detected")]
    return {"findings": rows, "hallucinations": halls, "prompt_injection_flagged_in": flagged}


def merge_hallucinations(per_sample: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for label, items in per_sample:
        for h in items:
            key = (h.get("finding_id"), h.get("type"), " ".join(str(h.get("review_quote") or "").split())[:80].lower())
            if key in out:
                out[key]["flagged_in"].append(label)
                # keep the most severe reading: material over minor, verified_false over suspected
                if h.get("severity") == "material":
                    out[key]["severity"] = "material"
                if h.get("status") == "verified_false":
                    out[key]["status"] = "verified_false"
            else:
                out[key] = {**h, "flagged_in": [label]}
    return list(out.values())


# ====================================================================================== API
def _make(review_path: str | Path, document_pdf: str | Path | Document, out_dir: str | Path,
          judge: JudgeClient | None, answer_key: str | Path | None, v1_review: str | Path | None,
          v1_document: str | Path | Document | None, samples: int, seed: int, budget: costs.Budget,
          model: str, effort: str, validity_tier: str | None, exploratory: bool = False,
          prereg_frozen: bool = False) -> _Grader:
    if samples < 1:
        raise ValueError("samples must be >= 1 (prereg: 2)")
    review = load_review(review_path)
    doc = load_document(document_pdf, doc_id=_under_review(review).get("doc_id"))
    v1_doc = None
    if v1_document is not None:
        v1 = load_review(v1_review) if v1_review else {}
        v1_doc = load_document(v1_document, doc_id=_under_review(v1).get("doc_id"))
    g = _Grader(review_path=Path(review_path), document=doc, out_dir=Path(out_dir), judge=judge,
                answer_key_path=Path(answer_key) if answer_key else None,
                v1_review_path=Path(v1_review) if v1_review else None, v1_document=v1_doc,
                samples=samples, seed=seed, model=model, effort=effort, budget=budget, exploratory=exploratory,
                prereg_frozen=prereg_frozen)
    if validity_tier:
        g.validity_tier = validity_tier
    g.prepare()
    return g


def plan_grade(review_path: str | Path, document_pdf: str | Path | Document, *, answer_key: str | Path | None = None,
               v1_review: str | Path | None = None, v1_document: str | Path | Document | None = None,
               samples: int = 2, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT,
               exploratory: bool = False) -> dict[str, Any]:
    """The ``--dry-run`` plan: call count, token and cost estimate. Makes no call; an unsigned key is planned,
    and its warning says whether a real run would refuse it (LC12)."""
    g = _make(review_path, document_pdf, ".", None, answer_key, v1_review, v1_document, samples, 0,
              costs.Budget(), model, effort, None, exploratory=exploratory)
    return g.plan()


async def grade_review_async(review_path: str | Path, document_pdf: str | Path | Document, out_dir: str | Path, *,
                             judge: JudgeClient, answer_key: str | Path | None = None,
                             v1_review: str | Path | None = None, v1_document: str | Path | Document | None = None,
                             samples: int = 2, seed: int = 0, max_cost_usd: float | None = None,
                             model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT,
                             budget: costs.Budget | None = None, validity_tier: str | None = None,
                             raise_on_error: bool = True, exploratory: bool = False) -> GradeResult:
    """Async form of :func:`grade_review`. ``budget`` lets several grades share one spend limit.

    Raises :class:`~sit_eval.lc12.UnsignedKeyRefusal` before any call or file write when ``answer_key`` is
    not signed off and ``exploratory`` is false (LC12)."""
    from sit_eval import prereg as prereg_mod
    from sit_eval.grader.report import render_markdown

    bud = budget or costs.Budget(max_cost_usd=max_cost_usd)
    g = _make(review_path, document_pdf, out_dir, judge, answer_key, v1_review, v1_document, samples, seed,
              bud, model, effort, validity_tier, exploratory=exploratory,
              prereg_frozen=prereg_mod.prereg_status()["frozen"])
    g.require_signed_key()
    report = await g.run()
    out = Path(out_dir)
    gj, gm = out / "grade.json", out / "grade.md"
    gj.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    gm.write_text(render_markdown(report), encoding="utf-8")
    result = GradeResult(report=report, out_dir=out, grade_json=gj, grade_md=gm, call_log=out / CALL_LOG)
    if raise_on_error and report["status"] == "aborted_budget":
        raise costs.BudgetExceeded(report["error"])
    if raise_on_error and report["status"] == "failed":
        raise GraderError(report["error"])
    return result


def grade_review(review_path: str | Path, document_pdf: str | Path | Document, out_dir: str | Path, *,
                 judge: JudgeClient, answer_key: str | Path | None = None, v1_review: str | Path | None = None,
                 samples: int = 2, seed: int = 0, max_cost_usd: float | None = None,
                 v1_document: str | Path | Document | None = None, model: str = DEFAULT_MODEL,
                 effort: str = DEFAULT_EFFORT, validity_tier: str | None = None,
                 exploratory: bool = False) -> GradeResult:
    """Grade one Review with the lecturer grader and write ``grade.json``, ``grade.md`` and
    ``grader_calls.jsonl`` (plus ``inputs/``, ``outputs/`` and ``grader_projection.json``) to ``out_dir``.

    Key-blind is the score; ``answer_key`` adds a key-aware diagnostic that never changes it. A key that
    is not signed off (``scored_run_ready`` false, or any legacy YAML key) is refused unless
    ``exploratory`` is true, and then every artefact is marked exploratory (LC12, ``sit_eval.lc12``).
    ``v1_review`` switches on delta mode (D11); ``v1_document`` optionally supplies the prior design.
    ``max_cost_usd`` stops before any call that would cross it (outputs are still written, then
    :class:`~sit_eval.grader.costs.BudgetExceeded` is raised).
    """
    return asyncio.run(grade_review_async(
        review_path, document_pdf, out_dir, judge=judge, answer_key=answer_key, v1_review=v1_review,
        v1_document=v1_document, samples=samples, seed=seed, max_cost_usd=max_cost_usd, model=model,
        effort=effort, validity_tier=validity_tier, exploratory=exploratory))
