"""The chat panel: a reading aid over one finished run, not the review (design note section 6).

* Corpus: that run's ``report.json`` (findings, verdict, unresolved, limitations, sound areas,
  intent, decision registry, degradations), its evidence ledger, ``anchors.json`` and the coverage
  map (what ``dra explain`` and ``dra coverage`` read). Never the PDF, the prompts, ``llm.jsonl``
  or the model's own earlier answers: every question is one fresh call.
* One call per question: Opus 5.5 at ``medium`` effort through headless Claude Code (the agent's
  backend, ADR-010), with a strict JSON schema (:data:`ANSWER_SCHEMA`) and no tools.
* Citations are checked against the run: an ID that does not resolve is dropped and the answer is
  flagged; an answer with ``supported: false``, or with no citation left, is shown as
  :data:`UNSUPPORTED_TEXT` with no prose.
* Logged to ``runs/<id>/ui/chat.jsonl`` by this module's own client, never through the agent's
  ``LLMGateway``, so nothing reaches ``llm.jsonl`` or the manifest.
* Capped per run at :data:`MAX_CALLS` calls or :data:`MAX_COST_USD` (planner ruling 2026-10-03; the
  note's 0.50 USD was sized for Sonnet). A failed call counts as a call.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sit_review_agent.hashing import sha256_text
from sit_review_agent.ui.rundata import UI_DIR, read_json

MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_CALLS = 20
MAX_COST_USD = 3.00
MAX_QUESTION_CHARS = 2000
CALL_TIMEOUT_S = 240.0
MAX_OUTPUT_TOKENS = 16000
LOG_NAME = "chat.jsonl"
UNSUPPORTED_TEXT = "The review does not answer this."
LABEL = "reading aid, not the review"

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "cited_finding_ids", "cited_evidence_ids", "cited_other_ids", "supported"],
    "properties": {
        "answer": {"type": "string", "description": "the answer, using only the review's content"},
        "cited_finding_ids": {"type": "array", "items": {"type": "string"},
                              "description": "FND- IDs the answer rests on"},
        "cited_evidence_ids": {"type": "array", "items": {"type": "string"},
                               "description": "EV- IDs the answer rests on"},
        "cited_other_ids": {"type": "array", "items": {"type": "string"},
                            "description": "AD-, DEG-, SA- IDs or coverage:<criterion> the answer rests on"},
        "supported": {"type": "boolean",
                      "description": "false when the review does not contain an answer to the question"},
    },
}

SYSTEM_PROMPT = """You answer questions about one finished design review, using only the review data given \
below in <review_data>. You are a reading aid, not the reviewer.

Rules:
1. Use only <review_data>. You have not seen the design document, and you must not add a finding, change a \
finding's severity, rank or disposition, or judge the design yourself.
2. Cite the IDs your answer rests on: findings (FND-), evidence ledger entries (EV-), decision registry \
entries (AD-), degradations (DEG-), sound areas (SA-) and coverage entries as coverage:<criterion id>. \
Cite only IDs that appear in <review_data>.
3. If the review data does not answer the question, set supported to false and leave answer empty. \
Do not guess.
4. You cannot start, re-run, stop or modify a review. If asked to, set supported to false and say in \
answer which command the person would run (dra review <document> --profile <profile>).
5. Plain sentences, no headings, no lists, at most 150 words. Quote the review's own wording where it helps."""

ID_PATTERNS = {"finding": re.compile(r"^FND-\d+$"), "evidence": re.compile(r"^EV-\d+$"),
               "decision": re.compile(r"^AD-\d+$"), "degradation": re.compile(r"^DEG-\d+$"),
               "sound_area": re.compile(r"^SA-\d+$"), "coverage": re.compile(r"^coverage:\s*\S+$")}


# ------------------------------------------------------------------ corpus and resolver


@dataclass
class RunIds:
    findings: set[str] = field(default_factory=set)
    evidence: set[str] = field(default_factory=set)
    decisions: set[str] = field(default_factory=set)
    degradations: set[str] = field(default_factory=set)
    sound_areas: set[str] = field(default_factory=set)
    criteria: set[str] = field(default_factory=set)

    def resolves(self, cid: str) -> bool:
        cid = cid.strip()
        if ID_PATTERNS["finding"].match(cid):
            return cid in self.findings
        if ID_PATTERNS["evidence"].match(cid):
            return cid in self.evidence
        if ID_PATTERNS["decision"].match(cid):
            return cid in self.decisions
        if ID_PATTERNS["degradation"].match(cid):
            return cid in self.degradations
        if ID_PATTERNS["sound_area"].match(cid):
            return cid in self.sound_areas
        if ID_PATTERNS["coverage"].match(cid):
            return cid.split(":", 1)[1].strip() in self.criteria
        return False


def _ledger(run_dir: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    led = read_json(run_dir / "ledger.json")
    return led if isinstance(led, list) else list(report.get("evidence_ledger") or [])


def _coverage(run_dir: Path) -> dict[str, Any]:
    from sit_review_agent.report.coverage import build_coverage

    try:
        return build_coverage(run_dir).as_dict()
    except Exception:  # noqa: BLE001 - a run without coverage data still has a report to ask about
        return {}


def run_ids(run_dir: Path) -> RunIds:
    report = read_json(run_dir / "report.json") or {}
    cov = _coverage(run_dir)
    return RunIds(
        findings={f["id"] for f in report.get("findings") or [] if f.get("id")},
        evidence={e["evidence_id"] for e in _ledger(run_dir, report) if e.get("evidence_id")},
        decisions={r["registry_id"] for r in report.get("decision_registry") or [] if r.get("registry_id")},
        degradations={d["id"] for d in (report.get("research_log") or {}).get("degradations") or [] if d.get("id")},
        sound_areas={s["id"] for s in report.get("sound_areas") or [] if s.get("id")},
        criteria={str(c) for c in cov.get("criteria") or []})


def corpus(run_dir: Path) -> dict[str, Any]:
    """The run data the model sees. Provenance hashes, the run manifest and tool-call logs are left
    out; finding, evidence and registry text is kept verbatim."""
    report = read_json(run_dir / "report.json") or {}
    findings = []
    for f in report.get("findings") or []:
        g = {k: v for k, v in f.items() if k != "provenance"}
        findings.append(g)
    ledger = [{k: e.get(k) for k in ("evidence_id", "source_type", "authority", "url_or_citation", "title",
                                     "excerpt", "derived_from") if e.get(k) not in (None, [], "")}
              for e in _ledger(run_dir, report)]
    anchors_doc = read_json(run_dir / "anchors.json") or {}
    rows = anchors_doc.get("rows", []) if isinstance(anchors_doc, dict) else anchors_doc
    anchors: dict[str, list[str]] = {}
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("owner_id"):
            anchors.setdefault(str(r["owner_id"]), []).append(
                f"p.{r.get('page')} §{r.get('section_ref')}: {r.get('anchor_status')} ({r.get('method')} match)")
    cov = _coverage(run_dir)
    cov_rows = []
    for row in cov.get("rows") or []:
        cells = {k: v for k, v in (row.get("cells") or {}).items() if v not in ("", "-", None)}
        if cells or row.get("sound_areas"):
            cov_rows.append({"section": row.get("section"), "heading": row.get("heading"), "cells": cells,
                             **({"sound_areas": row["sound_areas"]} if row.get("sound_areas") else {})})
    cov = {**cov, "rows": cov_rows}
    rlog = report.get("research_log") or {}
    return {
        "run_id": (report.get("metadata") or {}).get("run_id", run_dir.name),
        "documents": [{k: d.get(k) for k in ("doc_id", "title", "version", "role", "page_count")}
                      for d in (report.get("metadata") or {}).get("documents") or []],
        "verdict": report.get("verdict"),
        "intent_summary": {k: v for k, v in (report.get("intent_summary") or {}).items() if k != "doc_anchors"},
        "findings": findings,
        "sound_areas": report.get("sound_areas"),
        "unresolved": report.get("unresolved"),
        "limitations": report.get("limitations"),
        "degradations": rlog.get("degradations"),
        "unanswered_research_questions": rlog.get("unanswered_questions"),
        "decision_registry": [{k: r.get(k) for k in ("registry_id", "type", "doc_ref", "statement")}
                              for r in report.get("decision_registry") or []],
        "evidence_ledger": ledger,
        "anchors": anchors,
        "coverage": {k: cov.get(k) for k in ("criteria", "outcomes", "criterion_findings", "notes", "rows")
                     if k in cov},
    }


def prompt_for(run_dir: Path, question: str) -> str:
    data = json.dumps(corpus(run_dir), ensure_ascii=False, separators=(",", ":"))
    return f"<review_data>\n{data}\n</review_data>\n\n<question>\n{question}\n</question>"


def resolve(answer: dict[str, Any], ids: RunIds) -> dict[str, Any]:
    """Split the model's citations into the ones that exist in this run and the ones that do not,
    and decide how the answer is shown: ``answer`` or ``unsupported``."""
    cited: list[str] = []
    for key in ("cited_finding_ids", "cited_evidence_ids", "cited_other_ids"):
        for c in answer.get(key) or []:
            c = str(c).strip()
            if c and c not in cited:
                cited.append(c)
    ok = [c for c in cited if ids.resolves(c)]
    dropped = [c for c in cited if c not in ok]
    supported = answer.get("supported") is True and bool(ok) and bool(str(answer.get("answer") or "").strip())
    reason = None
    if answer.get("supported") is not True:
        reason = "the model reported that the review does not answer this"
    elif not ok:
        reason = "no citation resolves in this run"
    return {"citations": ok, "dropped": dropped, "rendered_as": "answer" if supported else "unsupported",
            "answer": str(answer.get("answer") or "") if supported else "", "unsupported_reason": reason}


# ------------------------------------------------------------------ the model client


@dataclass
class ChatReply:
    data: dict[str, Any] | None
    usage: dict[str, Any] | None
    cost_usd: float | None
    model: str | None
    duration_s: float
    error: str | None = None


class ChatClient(Protocol):
    async def ask(self, *, system: str, prompt: str, schema: dict[str, Any], cwd: Path,
                  max_budget_usd: float | None) -> ChatReply: ...


class ClaudeCodeChatClient:
    """One ``claude -p`` per question, built like ``ClaudeCodeGateway.build_argv`` (every CLI tool,
    MCP server and slash command off, the system prompt replaced, ``--json-schema``), but logging to
    ``ui/chat.jsonl`` only. No ``--resume``: every question starts a fresh session."""

    def __init__(self, *, executable: str = "claude", extra_args: tuple[str, ...] = (),
                 inherit_api_key: bool = False, runner: Any = None) -> None:
        from sit_review_agent.llm.claude_code import subprocess_runner

        self.executable = executable
        self.extra_args = list(extra_args)
        self.inherit_api_key = inherit_api_key
        self.runner = runner or subprocess_runner

    @classmethod
    def from_config(cls, config: Any) -> ClaudeCodeChatClient:
        cc = config.agent.claude_code
        return cls(executable=cc.executable, extra_args=tuple(cc.extra_args), inherit_api_key=cc.inherit_api_key)

    def argv(self, system: str, schema: dict[str, Any], max_budget_usd: float | None) -> list[str]:
        from sit_review_agent.llm.claude_code import STREAM_FLAGS

        out = [self.executable, "-p", "--model", MODEL, "--system-prompt", system, "--tools", "",
               "--strict-mcp-config", "--disallowedTools", "mcp__*", "--disable-slash-commands", *STREAM_FLAGS,
               "--effort", EFFORT, "--json-schema", json.dumps(schema, separators=(",", ":"))]
        if max_budget_usd is not None:
            out += ["--max-budget-usd", f"{max(max_budget_usd, 0.01):.2f}"]
        return out + self.extra_args

    def env(self) -> dict[str, str]:
        from sit_review_agent.llm.claude_code import API_KEY_ENV_VARS

        env = dict(os.environ)
        if not self.inherit_api_key:
            for name in API_KEY_ENV_VARS:
                env.pop(name, None)
        env.update({"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
                    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(MAX_OUTPUT_TOKENS)})
        return env

    async def ask(self, *, system: str, prompt: str, schema: dict[str, Any], cwd: Path,
                  max_budget_usd: float | None) -> ChatReply:
        from sit_review_agent.llm.partial import parse_cli_stdout

        t0 = time.monotonic()
        try:
            done = await self.runner(self.argv(system, schema, max_budget_usd), prompt, self.env(), cwd,
                                     CALL_TIMEOUT_S)
        except (TimeoutError, OSError) as exc:
            return ChatReply(None, None, None, None, time.monotonic() - t0, f"{type(exc).__name__}: {exc}")
        out, _ = parse_cli_stdout(done.stdout)
        elapsed = time.monotonic() - t0
        if out is None:
            return ChatReply(None, None, None, None, elapsed, f"claude -p exited {done.returncode} with no result")
        usage = out.get("usage") if isinstance(out.get("usage"), dict) else None
        cost = float(out["total_cost_usd"]) if isinstance(out.get("total_cost_usd"), int | float) else None
        models = list((out.get("modelUsage") or {}).keys()) if isinstance(out.get("modelUsage"), dict) else []
        model = models[0] if len(models) == 1 else (",".join(models) or None)
        if out.get("is_error") or done.returncode != 0:
            err = str(out.get("result") or out.get("subtype") or f"exit {done.returncode}")[:300]
            return ChatReply(None, usage, cost, model, elapsed, f"claude -p error: {err}")
        data = out.get("structured_output")
        if data is None:
            try:
                data = json.loads(str(out.get("result") or ""))
            except ValueError:
                data = None
        if not isinstance(data, dict):
            return ChatReply(None, usage, cost, model, elapsed, "no structured output")
        return ChatReply(data, usage, cost, model, elapsed)


# ------------------------------------------------------------------ the log and the cap


def log_path(run_dir: Path) -> Path:
    return run_dir / UI_DIR / LOG_NAME


def history(run_dir: Path) -> list[dict[str, Any]]:
    p = log_path(run_dir)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def budget(run_dir: Path) -> dict[str, Any]:
    rows = history(run_dir)
    calls = sum(1 for r in rows if r.get("counted"))
    cost = sum(float(r["cost_usd"]) for r in rows if isinstance(r.get("cost_usd"), int | float))
    unknown = sum(1 for r in rows if r.get("counted") and r.get("cost_usd") is None)
    stopped = calls >= MAX_CALLS or cost >= MAX_COST_USD
    return {"calls_used": calls, "max_calls": MAX_CALLS, "cost_usd": round(cost, 6), "max_cost_usd": MAX_COST_USD,
            "calls_with_unknown_cost": unknown, "stopped": stopped, "model": MODEL, "effort": EFFORT,
            "log": f"{run_dir.name}/{UI_DIR}/{LOG_NAME}"}


class ChatRefused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


_LOCKS: dict[str, asyncio.Lock] = {}


async def ask(run_dir: Path, question: str, client: ChatClient, *, running: bool) -> dict[str, Any]:
    """Answer ``question`` about ``run_dir``. Raises :class:`ChatRefused` when the chat may not run."""
    question = question.strip()
    if not question:
        raise ChatRefused(400, "Empty question.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ChatRefused(400, f"Questions are limited to {MAX_QUESTION_CHARS} characters.")
    if running:
        raise ChatRefused(409, "The chat is off while the run is in progress.")
    if not (run_dir / "report.json").is_file():
        raise ChatRefused(409, "This run has no report.json, so there is nothing to ask about.")
    lock = _LOCKS.setdefault(str(run_dir.resolve()), asyncio.Lock())
    async with lock:
        b = budget(run_dir)
        if b["stopped"]:
            raise ChatRefused(429, f"The chat cap for this run is reached ({b['calls_used']} of {MAX_CALLS} calls, "
                                   f"${b['cost_usd']:.2f} of ${MAX_COST_USD:.2f}).")
        prompt = prompt_for(run_dir, question)
        # The CLI runs in ui/ (its session files stay out of the run directory proper); it must exist first.
        (run_dir / UI_DIR).mkdir(parents=True, exist_ok=True)
        reply = await client.ask(system=SYSTEM_PROMPT, prompt=prompt, schema=ANSWER_SCHEMA,
                                 cwd=(run_dir / UI_DIR), max_budget_usd=MAX_COST_USD - b["cost_usd"])
        entry: dict[str, Any] = {
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "question": question,
            "prompt_sha256": sha256_text(SYSTEM_PROMPT + "\n" + prompt), "requested_model": MODEL, "effort": EFFORT,
            "served_model": reply.model, "usage": reply.usage, "cost_usd": reply.cost_usd,
            "duration_s": round(reply.duration_s, 3), "counted": True, "error": reply.error}
        if reply.data is not None:
            res = resolve(reply.data, run_ids(run_dir))
            entry.update(res)
            entry["model_supported"] = reply.data.get("supported")
        else:
            entry.update({"citations": [], "dropped": [], "rendered_as": "error", "answer": "",
                          "unsupported_reason": None})
        p = log_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return {"turn": entry, "budget": budget(run_dir)}
