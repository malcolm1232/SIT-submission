"""The chat panel: a reading aid over one finished run, not the review (design note section 6).

* Corpus: that run's ``report.json`` (findings with their anchors and evidence, verdict, unresolved,
  limitations, sound areas, intent, decision registry, degradations), the evidence ledger entries a
  finding cites, and the coverage outcomes per criterion (what ``dra explain`` and ``dra coverage``
  read; the integration pass of 2026-10-03 cut the uncited ledger entries, the ledger excerpts the
  findings already quote, the anchor rows and the coverage rows, planner ruling on cache reads).
  Never the PDF, the prompts, ``llm.jsonl`` or the model's own earlier answers: every question is
  one fresh call.
* One call per question: Opus 5.5 at ``medium`` effort through headless Claude Code (the agent's
  backend, ADR-010), with a strict JSON schema (:data:`ANSWER_SCHEMA`) and no tools. The corpus is
  the tail of the system prompt (``--system-prompt-file``), the question the whole user turn: the
  system prompt is where the CLI sets a cache breakpoint, so the second question of a run reads the
  cache the first wrote. In the user turn (the first live pair) a byte-identical corpus prefix was
  written again on the second call (71,451 then 70,511 tokens written, 943 read); in the system
  prompt (the second live pair, docs/live_runs/ui_flow_1) the second call read 54,984 tokens and
  wrote 705 (0.45 then 0.03 USD).
* Citations are checked against the run: an ID that does not resolve is dropped and the answer is
  flagged; an answer with ``supported: false``, or with no citation left, is shown as
  :data:`UNSUPPORTED_TEXT` with no prose.
* Logged to ``runs/<id>/ui/chat.jsonl`` by this module's own client, never through the agent's
  ``LLMGateway``, so nothing reaches ``llm.jsonl`` or the manifest.
* Capped per run at :data:`MAX_CALLS` calls or :data:`MAX_COST_USD` (planner ruling 2026-10-03; the
  note's 0.50 USD was sized for Sonnet). A failed call counts as a call, and so does one the reader stopped
  (:data:`STOPPED_ERROR`). The cap is enforced here, on the server; the page does not show the money (Malcolm,
  6 Oct 2026), only the calls.
* Streamed (6 Oct 2026): with ``on_partial`` the answer's text is passed on as the model writes it, read from the
  CLI's ``stream-json`` events (the ``StructuredOutput`` block's ``input_json_delta``, the same stream the agent's
  gateway reads) by :func:`partial_field`. Only the final answer, resolved as above, is logged and shown as the
  answer: the streamed text is a preview of it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
from collections.abc import Callable
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
#: The error of a call the reader stopped (the page's Stop, or the page closed while it streamed), and what the page
#: and the export say for it.
STOPPED_ERROR = "stopped by the reader before the answer was complete"
STOPPED_TEXT = "Stopped before the answer was complete. The call counts toward this run's cap."

#: Called with the answer's text so far, each time it grows.
PartialCallback = Callable[[str], None]

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

SYSTEM_FILE = "chat_system_prompt.txt"
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


def cited_evidence_ids(report: dict[str, Any]) -> set[str]:
    """The ledger entries the findings rest on: their evidence items and their recommendations'
    supporting evidence."""
    out: set[str] = set()
    for f in report.get("findings") or []:
        out |= {str(e.get("evidence_id")) for e in f.get("evidence") or [] if e.get("evidence_id")}
        out |= {str(i) for i in (f.get("recommendation") or {}).get("supporting_evidence_ids") or []}
    return out


def corpus(run_dir: Path) -> dict[str, Any]:
    """The run data the model sees: ``report.json`` without provenance hashes, the ledger entries a
    finding cites (without their excerpt, which the finding quotes), and the coverage outcomes. The
    run manifest, tool-call logs, uncited ledger entries, anchor rows and coverage rows are left
    out; finding, verdict and registry text is kept verbatim."""
    report = read_json(run_dir / "report.json") or {}
    findings = []
    for f in report.get("findings") or []:
        g = {k: v for k, v in f.items() if k != "provenance"}
        findings.append(g)
    cited = cited_evidence_ids(report)
    ledger = [{k: e.get(k) for k in ("evidence_id", "source_type", "authority", "url_or_citation", "title",
                                     "derived_from") if e.get(k) not in (None, [], "")}
              for e in _ledger(run_dir, report) if str(e.get("evidence_id")) in cited]
    cov = _coverage(run_dir)
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
        "coverage": {k: cov.get(k) for k in ("criteria", "outcomes", "criterion_findings", "notes") if k in cov},
    }


def system_for(run_dir: Path) -> str:
    """The system prompt of every call about ``run_dir``: the rules, then the corpus. Byte-identical
    from one question to the next, so the cache written by the first call is read by the second."""
    data = json.dumps(corpus(run_dir), ensure_ascii=False, separators=(",", ":"))
    return f"{SYSTEM_PROMPT}\n\n<review_data>\n{data}\n</review_data>"


def prompt_for(question: str) -> str:
    """The user turn: the question alone."""
    return f"<question>\n{question}\n</question>"


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
                  max_budget_usd: float | None, on_partial: PartialCallback | None = None) -> ChatReply: ...


def partial_field(text: str, key: str) -> str | None:
    """The string value of the root object's field ``key`` as far as ``text``, JSON that is still streaming, has
    it: decoded, with an escape cut in half left out. ``None`` until the value has started. Never guesses: a field
    of a nested object is not the root's, and a key is read only once its closing quote has arrived."""
    depth, i, n = 0, 0, len(text)
    expect_key, current = False, None
    while i < n:
        c = text[i]
        if c == '"':
            raw, i, closed = _raw_string(text, i + 1)
            if depth == 1 and expect_key:
                if not closed:
                    return None
                current, expect_key = _decode(raw), False
            elif depth == 1 and current == key:
                return _decode(raw if closed else _cut_escape(raw))
            continue
        if c in "{[":
            depth += 1
            expect_key = depth == 1 and c == "{"
        elif c in "}]":
            depth -= 1
        elif c == "," and depth == 1:
            expect_key, current = True, None
        i += 1
    return None


def _raw_string(text: str, i: int) -> tuple[str, int, bool]:
    """The raw characters of the string starting at ``i`` (after its opening quote), the index after it, and
    whether its closing quote has arrived."""
    j, n = i, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == '"':
            return text[i:j], j + 1, True
        j += 1
    return text[i:n], n, False


def _cut_escape(raw: str) -> str:
    """``raw`` without an escape the stream has cut in half (a lone backslash or a short ``\\u``), and without the
    first half of a surrogate pair whose second half has not arrived."""
    i, n = 0, len(raw)
    while i < n:
        if raw[i] != "\\":
            i += 1
            continue
        size = 6 if raw[i + 1:i + 2] == "u" else 2
        if i + size > n:
            return raw[:i]
        if size == 6 and raw[i + 2:i + 3] in "dD" and raw[i + 3:i + 4] in "89abAB" and i + 12 > n:
            return raw[:i]
        i += size
    return raw


def _decode(raw: str) -> str:
    try:
        return str(json.loads(f'"{raw}"'))
    except ValueError:
        return raw


class ClaudeCodeChatClient:
    """One ``claude -p`` per question, built like ``ClaudeCodeGateway.build_argv`` (every CLI tool,
    MCP server and slash command off, the system prompt replaced, ``--json-schema``), but logging to
    ``ui/chat.jsonl`` only. No ``--resume``: every question starts a fresh session. The system
    prompt (rules plus the corpus, well over an argument's size on Linux) goes through
    ``--system-prompt-file``: written to ``cwd`` for the call and removed after it."""

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

    def argv(self, system_file: Path, schema: dict[str, Any], max_budget_usd: float | None) -> list[str]:
        from sit_review_agent.llm.claude_code import STREAM_FLAGS

        out = [self.executable, "-p", "--model", MODEL, "--system-prompt-file", str(system_file), "--tools", "",
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
                  max_budget_usd: float | None, on_partial: PartialCallback | None = None) -> ChatReply:
        from sit_review_agent.llm.claude_code import _takes_on_line
        from sit_review_agent.llm.partial import StreamParser, parse_cli_stdout

        t0 = time.monotonic()
        system_file = Path(cwd) / SYSTEM_FILE
        parser = StreamParser()
        shown = ""

        def on_line(line: str) -> None:
            """Each stdout line as it arrives: parsed once, and the answer's text so far passed on when it grew."""
            nonlocal shown
            parser.feed_line(line)
            text = partial_field(parser.scanner.text, "answer")
            if on_partial is not None and text and text != shown:
                shown = text
                on_partial(text)

        live = on_partial is not None and _takes_on_line(self.runner)
        try:
            system_file.write_text(system, encoding="utf-8")
            done = await self.runner(self.argv(system_file, schema, max_budget_usd), prompt, self.env(), cwd,
                                     CALL_TIMEOUT_S, **({"on_line": on_line} if live else {}))
        except (TimeoutError, OSError) as exc:
            return ChatReply(None, None, None, None, time.monotonic() - t0, f"{type(exc).__name__}: {exc}")
        finally:
            system_file.unlink(missing_ok=True)
        out, _ = parse_cli_stdout(done.stdout, parser if live else None)
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


def precheck(run_dir: Path, question: str, *, running: bool) -> str:
    """The question as it will be asked, or :class:`ChatRefused` when the chat may not run: an empty or too long
    question, a run in progress, no report, or the cap reached (the cap in calls or in cost, both counted here)."""
    question = question.strip()
    if not question:
        raise ChatRefused(400, "Empty question.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ChatRefused(400, f"Questions are limited to {MAX_QUESTION_CHARS} characters.")
    if running:
        raise ChatRefused(409, "The chat is off while the run is in progress.")
    if not (run_dir / "report.json").is_file():
        raise ChatRefused(409, "This run has no report.json, so there is nothing to ask about.")
    _check_cap(budget(run_dir))
    return question


def _check_cap(b: dict[str, Any]) -> None:
    if b["stopped"]:
        raise ChatRefused(429, f"The chat cap for this run is reached ({b['calls_used']} of {MAX_CALLS} calls, "
                               "or the spending cap).")


async def ask(run_dir: Path, question: str, client: ChatClient, *, running: bool,
              on_partial: PartialCallback | None = None, stop: asyncio.Event | None = None) -> dict[str, Any]:
    """Answer ``question`` about ``run_dir``. Raises :class:`ChatRefused` when the chat may not run. With
    ``on_partial`` the answer's text is passed on as it streams. A call the reader stops is logged as counted, with
    :data:`STOPPED_ERROR`: when ``stop`` is set the call is ended and the stopped turn returned (``"stopped": True``);
    when the task itself is cancelled (the page went away) the line is written before the cancellation goes on."""
    question = precheck(run_dir, question, running=running)
    lock = _LOCKS.setdefault(str(run_dir.resolve()), asyncio.Lock())
    async with lock:
        b = budget(run_dir)
        _check_cap(b)
        system, prompt = system_for(run_dir), prompt_for(question)
        # The CLI runs in ui/ (its session files stay out of the run directory proper); it must exist first.
        (run_dir / UI_DIR).mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()

        def stopped() -> dict[str, Any]:
            return _entry(question, system, prompt,
                          ChatReply(None, None, None, None, time.monotonic() - t0, STOPPED_ERROR), run_dir)

        call = asyncio.ensure_future(client.ask(system=system, prompt=prompt, schema=ANSWER_SCHEMA,
                                                cwd=(run_dir / UI_DIR), max_budget_usd=MAX_COST_USD - b["cost_usd"],
                                                **({"on_partial": on_partial} if on_partial is not None else {})))
        waiter = asyncio.ensure_future(stop.wait()) if stop is not None else None
        try:
            await asyncio.wait({call, waiter} if waiter is not None else {call}, return_when=asyncio.FIRST_COMPLETED)
            if not call.done():                         # stopped: the call is ended (its process killed) and logged
                call.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await call
                entry = stopped()
                _log(run_dir, entry)
                return {"turn": entry, "budget": budget(run_dir), "stopped": True}
            reply = call.result()
        except asyncio.CancelledError:
            call.cancel()
            _log(run_dir, stopped())
            raise
        finally:
            if waiter is not None:
                waiter.cancel()
        entry = _entry(question, system, prompt, reply, run_dir)
        _log(run_dir, entry)
        return {"turn": entry, "budget": budget(run_dir)}


def _entry(question: str, system: str, prompt: str, reply: ChatReply, run_dir: Path) -> dict[str, Any]:
    """One line of ``ui/chat.jsonl``: the question, the call, and the answer as it is shown."""
    entry: dict[str, Any] = {
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "question": question,
        "prompt_sha256": sha256_text(system + "\n" + prompt), "system_sha256": sha256_text(system),
        "requested_model": MODEL, "effort": EFFORT,
        "served_model": reply.model, "usage": reply.usage, "cost_usd": reply.cost_usd,
        "duration_s": round(reply.duration_s, 3), "counted": True, "error": reply.error}
    if reply.data is not None:
        res = resolve(reply.data, run_ids(run_dir))
        entry.update(res)
        entry["model_supported"] = reply.data.get("supported")
    else:
        entry.update({"citations": [], "dropped": [], "rendered_as": "error", "answer": "",
                      "unsupported_reason": None})
    return entry


def _log(run_dir: Path, entry: dict[str, Any]) -> None:
    p = log_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
