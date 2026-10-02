"""Matching findings to key flaws (metrics.md §2, prereg ``matcher``).

Procedure:

1. Candidates per flaw (``candidate_rule``):

   * ``shortlist_bounded`` (default; metrics.md §2.3 and prereg ``matcher.candidates`` as amended by
     the owner on 2026-10-02, docs/USER_DECISIONS.md #10): the listwise LLM shortlist of up to
     ``shortlist_k`` findings (one call per flaw; findings shuffled per call with a recorded seed)
     is the candidate set. Location overlap (:mod:`sit_eval.locations`) adds no pair by itself; the
     shortlist prompt names the overlapping findings as a hint. If the shortlist call fails after
     the runner's retries the flaw gets no candidates (it counts as unmatched, like a pair whose
     samples all failed), the failure is listed, and it is never replaced by the overlap set.
   * ``union`` (the earlier rule; a DEVIATION from the amended prereg, kept for comparison):
     location overlap union the same shortlist (same prompt, so shortlist answers are shared with a
     ``shortlist_bounded`` run through the result cache).

   Per flaw, ``shortlist`` records the overlap hint and which shortlisted findings also overlap, so
   the provenance of every candidate stays auditable. The optional embedding prefilter is not
   implemented (prereg: used only if an embedding model is recorded at freeze).
2. Pairwise 0-3 scores, ``samples`` per pair, median (lower median when a sample failed and an even
   number remains). With ``adaptive_third_sample`` (on in config/eval.yaml by owner decision
   2026-10-02, USER_DECISIONS #15; off in a bare ``MatcherSettings``) the third sample is asked
   only when the first two disagree or one failed: the median of three is the agreed value whenever
   two agree, so the result is identical and about a third of calls are saved.
   ``call_granularity: pairwise`` (prereg-faithful) makes one call per pair and
   sample; ``per_flaw_batch`` (a DEVIATION) makes one call per flaw and sample scoring all its
   candidates. A score of 3 with ``location_ok: false`` is capped at 2 (MATCH requires a
   compatible location, §2.2).
3. Hungarian assignment on ``score + 0.01 * primary weight`` for eligible pairs (strict: 3,
   lenient: >= 2), plus a tie-break below 1e-4 favouring the agent's higher-ranked finding.
4. Unmatched findings (metrics.md §2.3 step 4): deterministic DUPLICATE when the finding scores >= 2
   against a flaw that is assigned to another finding; else, in the strict setting, deterministic
   PARTIAL_KEY_MATCH when its best median is 2 (PARTIAL) against a flaw nobody matched (the flaw is
   recorded in ``partial_key_flaw_id``; owner decision 2026-10-02, docs/USER_DECISIONS.md #14: it is
   a real issue, counts as correct for adjudicated precision, and is not "missing from the key", so it
   is never VALID_UNPLANTED, never enters the pooled key G+ and never removes a sound unit);
   otherwise the LLM adjudicator gives one of the six classes, and a still-valid observation match is
   VALID_UNPLANTED. Both deterministic rules use scored pairs only, so under ``shortlist_bounded`` a
   finding the shortlist left out never gets either label. (History: the first version labelled the
   partial case VALID_UNPLANTED deterministically; verifier E1 then sent it to the LLM adjudicator,
   where it could still come back VALID_UNPLANTED; the owner gave it its own class.)

The prompts never contain the review's run id, model, condition, provenance or confidence.
"""

from __future__ import annotations

import asyncio
import json
import random
import statistics
from dataclasses import dataclass, field
from typing import Any

from sit_eval import prompts
from sit_eval.calls import BudgetStop, JudgeRunner, derive_seed
from sit_eval.hungarian import linear_sum_assignment_max
from sit_eval.judge import JudgeError
from sit_eval.locations import Loc, anchors_location, key_location
from sit_review_agent.ingest import Document

W_PRIMARY = {"critical": 8, "high": 4, "medium": 2, "low": 1}
W_SENSITIVITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}
RANK_TIE_BREAK = 1e-4
ADJ_CLASSES = ("DUPLICATE", "VALID_UNPLANTED", "HALLUCINATED", "NON_SPECIFIC", "INVALID_OPINION", "OUT_OF_SCOPE")
#: Assigned by the harness only (never by the LLM adjudicator): strict-unmatched, median 2 against a free flaw
PARTIAL_KEY_MATCH = "PARTIAL_KEY_MATCH"


@dataclass
class FindingView:
    id: str
    position: int                 # 0-based position in rank order
    rank: int
    data: dict[str, Any]
    loc: Loc

    @property
    def severity(self) -> str | None:
        return self.data.get("severity")


@dataclass
class FlawView:
    id: str
    severity: str
    data: dict[str, Any]
    loc: Loc


@dataclass
class PairScore:
    finding_id: str
    flaw_id: str
    sources: list[str]                      # shortlist and/or overlap (overlap alone: union rule only)
    samples: list[int | None] = field(default_factory=list)
    raw: list[dict[str, Any]] = field(default_factory=list)
    capped: int = 0
    skipped: int = 0                         # adaptive third sample: not asked because samples 1-2 agreed

    @property
    def scored(self) -> list[int]:
        return [s for s in self.samples if s is not None]

    @property
    def median(self) -> float | None:
        s = self.scored
        return float(statistics.median_low(s)) if s else None


@dataclass
class Assignment:
    setting: str                            # strict | lenient
    threshold: int
    pairs: list[tuple[str, str, float]]     # (finding_id, flaw_id, median score)

    @property
    def finding_to_flaw(self) -> dict[str, str]:
        return {f: g for f, g, _ in self.pairs}

    @property
    def flaw_to_finding(self) -> dict[str, str]:
        return {g: f for f, g, _ in self.pairs}


@dataclass
class Adjudication:
    finding_id: str
    cls: str
    basis: str    # llm | deterministic_duplicate | deterministic_partial | still_valid_observation | llm_failed
    duplicate_of: str | None = None
    related_flaw_id: str | None = None
    observation_id: str | None = None
    rationale: str | None = None
    partial_key_flaw_id: str | None = None   # PARTIAL_KEY_MATCH only: the free flaw it scores PARTIAL (2) against


@dataclass
class MatchResult:
    findings: list[FindingView]
    flaws: list[FlawView]
    candidates: dict[str, dict[str, list[str]]]      # flaw_id -> finding_id -> sources
    shortlist: dict[str, dict[str, Any]]             # flaw_id -> {ids, seed, ok, overlap hint and provenance}
    pairs: dict[tuple[str, str], PairScore]
    assignments: dict[str, Assignment]
    adjudication: dict[str, dict[str, Adjudication]]  # setting -> finding_id -> Adjudication
    llm_adjudication: dict[str, dict[str, Any]]       # finding_id -> raw answer (or error)
    failures: list[str] = field(default_factory=list)
    granularity: str = "pairwise"
    candidate_rule: str = "shortlist_bounded"

    @property
    def shortlist_failed(self) -> list[str]:
        """Flaws whose shortlist call failed (under ``shortlist_bounded`` they had no candidates)."""
        return [g for g, r in self.shortlist.items() if not r.get("ok")]

    def score(self, fid: str, gid: str) -> float:
        p = self.pairs.get((fid, gid))
        return (p.median or 0.0) if p else 0.0


# ----------------------------------------------------------------------------- views and rendering


def finding_views(review: dict[str, Any]) -> list[FindingView]:
    """Non-strength findings in the agent's priority order (rank, ties by output order)."""
    rows = [(f.get("rank", 10**6), i, f) for i, f in enumerate(review["findings"]) if f.get("kind") != "strength"]
    rows.sort(key=lambda t: (t[0], t[1]))
    return [FindingView(id=f["id"], position=p, rank=r, data=f, loc=anchors_location(f.get("doc_anchors", [])))
            for p, (r, _, f) in enumerate(rows)]


def flaw_views(key: dict[str, Any], version: str) -> list[FlawView]:
    flaws = [g for g in key["flaws"] if version == "v2" or g.get("introduced_in", "v1") == "v1"]
    return [FlawView(id=g["id"], severity=g["severity"], data=g, loc=key_location(g["location"])) for g in flaws]


def _heading(doc: Document | None, section_ref: str) -> str | None:
    if doc is None:
        return None
    sec = doc.find_section(section_ref)
    return sec.heading if sec else None


def render_finding(f: dict[str, Any], doc: Document | None = None) -> str:
    """Blind finding block: id, title, statement and locations only (no labels, confidence,
    provenance or anything naming the run, model or condition)."""
    locs = [{"section": a.get("section_ref"), "heading": _heading(doc, a.get("section_ref", "")),
             "requirement_ids": a.get("requirement_ids", []), "quote": a.get("quote")}
            for a in f.get("doc_anchors", [])]
    return json.dumps({"finding_id": f["id"], "title": f.get("title"), "statement": f.get("statement"),
                       "locations": locs}, ensure_ascii=False, indent=1)


def credit_rule(g: dict[str, Any]) -> str:
    c = g["credit"]
    mode = c["mode"]
    required = [i for i in c["items"] if i["role"] == "required"]
    if mode == "substance":
        return ("substance: the finding must state the core insight as a whole, in substance; the credit items are "
                "guidance only")
    if mode == "all_of":
        return (f"all_of: MATCH requires every required credit item ({', '.join(i['id'] for i in required)}); "
                "stating only some of them is at most PARTIAL")
    n = c.get("min_required") or 1
    return (f"any_of: MATCH requires at least {n} of the required credit items "
            f"({', '.join(i['id'] for i in required)}); fewer is at most PARTIAL")


def render_flaw(g: dict[str, Any]) -> str:
    core = g.get("core_insight")
    lines = [f"id: {g['id']}"]
    if g.get("title"):
        lines.append(f"title: {g['title']}")
    lines.append(f"description: {g['description']}")
    if core:
        lines.append(f"core insight: {core}")
    else:
        lines.append("core insight: (not yet written in the key; treat the description together with the required "
                     "credit items as the core insight)")
    lines.append(f"credit rule: {credit_rule(g)}")
    lines.append("credit items:")
    lines += [f"  - {i['id']} ({i['role']}): {i['text']}" for i in g["credit"]["items"]]
    lines.append(f"why it is a flaw: {g['rationale']}")
    loc = g["location"]
    ids = list(loc.get("requirement_ids", [])) + list(loc.get("decision_ids", []))
    lines.append(f"location: sections {'; '.join(loc['sections'])}" + (f"; ids {', '.join(ids)}" if ids else ""))
    if loc.get("anchor_quote"):
        lines.append(f"anchor quote: {loc['anchor_quote']}")
    if g.get("distractor_notes"):
        lines.append(f"distractor notes (these are NOT this flaw): {g['distractor_notes']}")
    if g.get("disambiguation"):
        lines.append(f"disambiguation: {g['disambiguation']}")
    return "\n".join(lines)


def shuffled(items: list[Any], seed: int) -> list[Any]:
    out = list(items)
    random.Random(seed).shuffle(out)
    return out


# ----------------------------------------------------------------------------- the matcher


CANDIDATE_RULES = ("shortlist_bounded", "union")


@dataclass
class MatcherSettings:
    granularity: str = "pairwise"
    candidate_rule: str = "shortlist_bounded"   # union = the pre-2026-10-02 rule (DEVIATION; comparison only)
    samples: int = 3
    shortlist_k: int = 3
    severity_epsilon: float = 0.01
    seed: int = 0
    adaptive_third_sample: bool = False   # with samples = 3: skip sample 3 when samples 1 and 2 agree


class Matcher:
    def __init__(self, runner: JudgeRunner, settings: MatcherSettings, *, doc: Document | None = None) -> None:
        self.runner = runner
        self.s = settings
        self.doc = doc

    # -- candidates
    async def shortlist(self, g: FlawView, findings: list[FindingView]) -> dict[str, Any]:
        overlap = [f.id for f in findings if f.loc.overlaps(g.loc)]          # rank order
        if self.s.shortlist_k <= 0 or not findings:
            return _with_provenance({"ids": [], "seed": None, "ok": True}, overlap)
        seed = derive_seed(self.s.seed, "shortlist", g.id)
        order = shuffled(findings, seed)
        hinted = set(overlap)
        hint = ", ".join(f.id for f in order if f.id in hinted) or "none"   # listed in the shuffled order
        user = prompts.render("matcher_shortlist", FLAW=render_flaw(g.data), K=str(self.s.shortlist_k),
                              FINDINGS="\n".join(render_finding(f.data, self.doc) for f in order),
                              OVERLAP_IDS=hint)
        known = {f.id for f in findings}
        try:
            data = await self.runner.ask("shortlist", f"match.shortlist:{g.id}", prompts.template("matcher_system"),
                                         user, seed=seed)
        except BudgetStop:
            raise
        except JudgeError as exc:
            return _with_provenance({"ids": [], "seed": seed, "ok": False, "error": str(exc)[:300]}, overlap)
        valid = [i for i in dict.fromkeys(data.get("candidate_ids", [])) if i in known]
        ids = valid[: self.s.shortlist_k]
        # ids past shortlist_k are never scored (the shortlist bounds pairwise scoring); they are recorded
        return _with_provenance({"ids": ids, "seed": seed, "ok": True,
                                 "unknown_ids": [i for i in data.get("candidate_ids", []) if i not in known],
                                 "ids_beyond_k": valid[self.s.shortlist_k:]},
                                overlap)

    def candidates_for(self, g: FlawView, findings: list[FindingView], sl: dict[str, Any]) -> dict[str, list[str]]:
        """finding_id -> sources for one flaw under the configured candidate rule."""
        overlap = set(sl["overlap_hint_ids"])
        c: dict[str, list[str]] = {}
        if self.s.candidate_rule == "union":
            for f in findings:
                if f.id in overlap:
                    c.setdefault(f.id, []).append("overlap")
            for fid in sl["ids"]:
                c.setdefault(fid, []).append("shortlist")
            return c
        if self.s.candidate_rule != "shortlist_bounded":
            raise ValueError(f"unknown candidate_rule {self.s.candidate_rule!r}")
        # shortlist_bounded: only shortlisted findings; "overlap" records that the finding also shares a
        # location with the flaw (provenance), it never adds a pair
        for fid in sl["ids"]:
            c[fid] = (["overlap"] if fid in overlap else []) + ["shortlist"]
        return c

    # -- pairwise scoring
    @staticmethod
    def _sample_score(answer: dict[str, Any]) -> tuple[int, bool]:
        s = int(answer["score"])
        if s == 3 and answer.get("location_ok") is False:
            return 2, True
        return s, False

    async def score_pair(self, g: FlawView, f: FindingView, pair: PairScore, failures: list[str]) -> None:
        user = prompts.render("matcher_pair", FLAW=render_flaw(g.data), FINDING=render_finding(f.data, self.doc))
        system = prompts.template("matcher_system")

        async def one(k: int) -> None:
            try:
                ans = await self.runner.ask("pair", f"match.pair:{g.id}:{f.id}", system, user, sample_index=k)
            except BudgetStop:
                raise
            except JudgeError as exc:
                failures.append(f"pair {g.id}/{f.id} sample {k}: {str(exc)[:200]}")
                pair.samples[k] = None
                return
            s, capped = self._sample_score(ans)
            pair.samples[k] = s
            pair.capped += int(capped)
            pair.raw[k] = ans

        pair.samples = [None] * self.s.samples
        pair.raw = [{} for _ in range(self.s.samples)]
        if self.s.adaptive_third_sample and self.s.samples == 3:
            # The median of 3 equals the common value whenever two samples agree, so the third call
            # cannot change the result; it is asked only on disagreement or a failed sample.
            await asyncio.gather(one(0), one(1))
            if pair.samples[0] is not None and pair.samples[0] == pair.samples[1]:
                pair.skipped = 1
                return
            await one(2)
            return
        await asyncio.gather(*(one(k) for k in range(self.s.samples)))

    async def score_flaw_batch(self, g: FlawView, cands: list[FindingView], pairs: dict[tuple[str, str], PairScore],
                               failures: list[str], seeds: dict[str, list[int]]) -> None:
        system = prompts.template("matcher_system")
        for f in cands:
            pairs[(f.id, g.id)].samples = [None] * self.s.samples
            pairs[(f.id, g.id)].raw = [{} for _ in range(self.s.samples)]

        async def one(k: int) -> None:
            seed = derive_seed(self.s.seed, "batch", g.id, k)
            seeds.setdefault(g.id, []).append(seed)
            order = shuffled(cands, seed)
            user = prompts.render("matcher_batch", FLAW=render_flaw(g.data),
                                  FINDINGS="\n".join(render_finding(f.data, self.doc) for f in order))
            try:
                ans = await self.runner.ask("batch", f"match.batch:{g.id}", system, user, sample_index=k, seed=seed)
            except BudgetStop:
                raise
            except JudgeError as exc:
                failures.append(f"batch {g.id} sample {k}: {str(exc)[:200]}")
                return
            got = {e["finding_id"]: e for e in ans.get("scores", [])}
            for f in cands:
                e = got.get(f.id)
                p = pairs[(f.id, g.id)]
                if e is None:
                    failures.append(f"batch {g.id} sample {k}: no score for {f.id}")
                    continue
                s, capped = self._sample_score(e)
                p.samples[k] = s
                p.capped += int(capped)
                p.raw[k] = e

        if self.s.adaptive_third_sample and self.s.samples == 3:
            await asyncio.gather(one(0), one(1))
            agreed = all(pairs[(f.id, g.id)].samples[0] is not None
                         and pairs[(f.id, g.id)].samples[0] == pairs[(f.id, g.id)].samples[1] for f in cands)
            if agreed:
                for f in cands:
                    pairs[(f.id, g.id)].skipped = 1
                return
            await one(2)
            return
        await asyncio.gather(*(one(k) for k in range(self.s.samples)))

    # -- assignment
    def assign(self, findings: list[FindingView], flaws: list[FlawView], pairs: dict[tuple[str, str], PairScore],
               threshold: int, setting: str) -> Assignment:
        n = len(findings)
        weights = [[0.0] * len(flaws) for _ in findings]
        for i, f in enumerate(findings):
            for j, g in enumerate(flaws):
                p = pairs.get((f.id, g.id))
                m = p.median if p else None
                if m is not None and m >= threshold:
                    weights[i][j] = (m + self.s.severity_epsilon * W_PRIMARY[g.severity]
                                     + RANK_TIE_BREAK * (1 - f.position / max(n, 1)))
        chosen = [(findings[r].id, flaws[c].id, pairs[(findings[r].id, flaws[c].id)].median or 0.0)
                  for r, c in linear_sum_assignment_max(weights) if weights[r][c] > 0]
        return Assignment(setting=setting, threshold=threshold, pairs=chosen)

    # -- adjudication
    def pre_adjudicate(self, f: FindingView, a: Assignment, flaws: list[FlawView],
                       pairs: dict[tuple[str, str], PairScore]) -> Adjudication | None:
        taken = a.flaw_to_finding
        best_taken = max(((pairs[(f.id, g.id)].median or 0.0, g.id) for g in flaws
                          if (f.id, g.id) in pairs and g.id in taken and taken[g.id] != f.id), default=(0.0, None))
        if best_taken[0] >= 2:
            return Adjudication(f.id, "DUPLICATE", "deterministic_duplicate", duplicate_of=taken[best_taken[1]],
                                related_flaw_id=best_taken[1],
                                rationale=f"scores {best_taken[0]:g} against {best_taken[1]}, already matched to "
                                          f"{taken[best_taken[1]]}")
        return None

    @staticmethod
    def partial_free_flaw(f: FindingView, a: Assignment, flaws: list[FlawView],
                          pairs: dict[tuple[str, str], PairScore]) -> str | None:
        """Strict setting: the unassigned flaw this unmatched finding scores PARTIAL (2) against, if any
        (scored pairs only; ties go to the more severe flaw, then the earlier flaw in the key)."""
        if a.setting != "strict":
            return None
        taken = a.flaw_to_finding
        best = max(((pairs[(f.id, g.id)].median or 0.0, W_PRIMARY[g.severity], -j, g.id) for j, g in enumerate(flaws)
                    if (f.id, g.id) in pairs and g.id not in taken), default=(0.0, 0, 0, None))
        return best[3] if best[0] >= 2 else None

    async def adjudicate_llm(self, f: FindingView, findings: list[FindingView], key: dict[str, Any],
                             key_summary: str, doc_text: str) -> dict[str, Any]:
        seed = derive_seed(self.s.seed, "adjudicate", f.id)
        others = shuffled([o for o in findings if o.id != f.id], seed)
        user = prompts.render("adjudicator_user", DOCUMENT=doc_text, KEY_SUMMARY=key_summary,
                              OTHER_FINDINGS="\n".join(render_finding(o.data, self.doc) for o in others) or "(none)",
                              FINDING=render_finding(f.data, self.doc))
        try:
            ans = await self.runner.ask("adjudicate", f"adjudicate:{f.id}", prompts.template("adjudicator_system"),
                                        user, seed=seed)
        except BudgetStop:
            raise
        except JudgeError as exc:
            return {"ok": False, "error": str(exc)[:300], "seed": seed}
        return {"ok": True, "seed": seed, **ans}

    async def run(self, review: dict[str, Any], key: dict[str, Any], version: str, doc_text: str) -> MatchResult:
        findings = finding_views(review)
        flaws = flaw_views(key, version)
        failures: list[str] = []
        # 1. candidates
        sl = await asyncio.gather(*(self.shortlist(g, findings) for g in flaws))
        shortlist = {g.id: r for g, r in zip(flaws, sl, strict=True)}
        candidates: dict[str, dict[str, list[str]]] = {}
        pairs: dict[tuple[str, str], PairScore] = {}
        for g in flaws:
            c = self.candidates_for(g, findings, shortlist[g.id])
            candidates[g.id] = c
            for fid, src in c.items():
                pairs[(fid, g.id)] = PairScore(fid, g.id, src)
            if not shortlist[g.id]["ok"]:
                consequence = ("flaw has no candidates and counts as unmatched" if self.s.candidate_rule
                               == "shortlist_bounded" else "candidates are location overlap only")
                failures.append(f"shortlist {g.id}: {shortlist[g.id].get('error')} ({consequence})")
        # 2. pairwise scores
        by_id = {f.id: f for f in findings}
        batch_seeds: dict[str, list[int]] = {}
        if self.s.granularity == "per_flaw_batch":
            await asyncio.gather(*(self.score_flaw_batch(g, [by_id[i] for i in candidates[g.id]], pairs, failures,
                                                         batch_seeds) for g in flaws if candidates[g.id]))
        else:
            await asyncio.gather(*(self.score_pair(g, by_id[fid], pairs[(fid, g.id)], failures)
                                   for g in flaws for fid in candidates[g.id]))
        for g in flaws:
            if g.id in batch_seeds:
                shortlist[g.id]["batch_seeds"] = sorted(batch_seeds[g.id])
        # 3. assignment
        assignments = {"strict": self.assign(findings, flaws, pairs, 3, "strict"),
                       "lenient": self.assign(findings, flaws, pairs, 2, "lenient")}
        # 4. adjudication
        pre: dict[str, dict[str, Adjudication | None]] = {}
        need_llm: set[str] = set()
        for setting, a in assignments.items():
            matched = a.finding_to_flaw
            pre[setting] = {}
            for f in findings:
                if f.id in matched:
                    continue
                d = self.pre_adjudicate(f, a, flaws, pairs)
                if d is None:
                    g_partial = self.partial_free_flaw(f, a, flaws, pairs)
                    if g_partial is not None:
                        d = Adjudication(f.id, PARTIAL_KEY_MATCH, "deterministic_partial",
                                         related_flaw_id=g_partial, partial_key_flaw_id=g_partial,
                                         rationale=f"median {pairs[(f.id, g_partial)].median:g} (PARTIAL) against "
                                                   f"{g_partial}, which no finding matches strictly")
                pre[setting][f.id] = d
                if d is None:
                    need_llm.add(f.id)
        key_summary = render_key_summary(key, version)
        llm_ids = [f.id for f in findings if f.id in need_llm]
        answers = await asyncio.gather(*(self.adjudicate_llm(by_id[i], findings, key, key_summary, doc_text)
                                         for i in llm_ids))
        llm = dict(zip(llm_ids, answers, strict=True))
        observations = {o["id"] for o in all_observations(key)}
        adjudication: dict[str, dict[str, Adjudication]] = {}
        for setting in assignments:
            adjudication[setting] = {}
            for fid, d in pre[setting].items():
                if d is None:
                    ans = llm[fid]
                    if not ans.get("ok"):
                        failures.append(f"adjudicate {fid}: {ans.get('error')}")
                        d = Adjudication(fid, "UNADJUDICATED", "llm_failed", rationale=ans.get("error"))
                    elif ans.get("matches_observation_id") in observations:
                        d = Adjudication(fid, "VALID_UNPLANTED", "still_valid_observation",
                                         observation_id=ans["matches_observation_id"], rationale=ans.get("rationale"))
                    else:
                        d = Adjudication(fid, ans["class"], "llm", duplicate_of=ans.get("duplicate_of"),
                                         rationale=ans.get("rationale"))
                adjudication[setting][fid] = d
        return MatchResult(findings=findings, flaws=flaws, candidates=candidates, shortlist=shortlist, pairs=pairs,
                           assignments=assignments, adjudication=adjudication, llm_adjudication=llm,
                           failures=failures, granularity=self.s.granularity,
                           candidate_rule=self.s.candidate_rule)


def _with_provenance(res: dict[str, Any], overlap: list[str]) -> dict[str, Any]:
    """Add the location hint and the candidate provenance to one flaw's shortlist record."""
    ids, ov = res["ids"], set(overlap)
    res["overlap_hint_ids"] = list(overlap)
    res["shortlisted_with_overlap"] = [i for i in ids if i in ov]
    res["shortlisted_without_overlap"] = [i for i in ids if i not in ov]
    res["overlap_not_shortlisted"] = [i for i in overlap if i not in set(ids)]
    return res


def all_observations(key: dict[str, Any]) -> list[dict[str, Any]]:
    obs = list(key.get("still_valid_observations", []))
    for s in key.get("sound_sections", []):
        obs += s.get("still_valid_observations", [])
    return obs


def render_key_summary(key: dict[str, Any], version: str) -> str:
    """What the adjudicator sees of the key: every flaw (id, description, location), every sound
    section (location, why sound, trap) and every still-valid observation."""
    lines = ["Key flaws (findings that state these were scored separately):"]
    for g in key["flaws"]:
        if version == "v1" and g.get("introduced_in") == "v2":
            continue
        lines.append(f"- {g['id']} [{'; '.join(g['location']['sections'])}]: {g['description']}")
    lines.append("")
    lines.append("Sections the key author considers sound, with the false positives a careless reviewer raises there:")
    for s in key.get("sound_sections", []):
        if version not in s.get("applies_to_versions", ["v1", "v2"]):
            continue
        lines.append(f"- {s['id']} [{'; '.join(s['location']['sections'])}] sound because: {s['why_sound']} "
                     f"Trap: {s['trap']}")
    obs = all_observations(key)
    lines.append("")
    lines.append("Still-valid observations (correct issues that are not key flaws):")
    lines += [f"- {o['id']}: {o['text']}" for o in obs] or ["- (none)"]
    return "\n".join(lines)
