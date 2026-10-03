#!/usr/bin/env python3
"""Export a public snapshot of this repository (tracked files at HEAD, minus the private material).

The private repository keeps the evaluation material and its history; the snapshot carries the code,
the architecture and the trade-offs for an outside reader. Nothing is pushed, ever: the script writes
a directory, scans it, and (with ``--init-git``) makes ONE local commit with no history behind it.

    python scripts/export_public_snapshot.py --target /path/outside/the/repo            # export + scan
    python scripts/export_public_snapshot.py --target DIR --init-git                    # + one local commit
    python scripts/export_public_snapshot.py --target DIR --allow 'hex64:docs/live_runs/*/manifest.json'

What goes in: every path of ``git ls-tree -r HEAD`` (tracked, committed files only; their content is
read from the HEAD blobs, so an uncommitted edit, an untracked file or an ignored file can never leak),
except the files matched by :data:`RULES`. Every exclusion is logged file by file with its rule
(the sealed ``eval/blind/`` names are withheld from the log: only a count is printed).

The scan (count-only; a value is never printed, only the rule, the file, the field or line and the
length): 64-character ``[A-Za-z0-9_-]`` tokens (``hex64`` for pure lower-case hex such as sha256
digests, ``token64`` otherwise), 32-character hex tokens, ``Bearer`` values, ``sk-`` keys, ``api_key``
assignments, the word oauth, e-mail addresses, the exporting user's name and any home path,
claude.ai session links, MCP session id values, and ``scripts/leakage_grep.py`` of the export run
with the answer keys from HEAD (written to a temporary directory outside the export). A finding fails
the run (exit 1) unless ``--allow RULE:GLOB`` names it; ``--init-git`` only commits a clean scan.

Exit codes: 0 export good, 1 unallowed scan finding or leakage failure, 2 usage error (dirty
worktree without ``--allow-dirty``, target not empty or inside the repository, git failure).
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SNAPSHOT_NOTE = "PUBLIC_SNAPSHOT.md"
ALLOW_FILE = ".public-allow"
REPO_SLUG = "malcolm1232/SIT"

# --------------------------------------------------------------------------------------------- rules

#: Files kept in a run directory directly under docs/live_runs/<run>/; everything else in a run
#: directory (ledgers, state, checkpoints, shards, snapshots, page text, scores, judge material) is dropped.
RUN_KEEP = frozenset({"report.md", "report.json", "manifest.json", "MEASUREMENT.md", "effective_config.json",
                      "anchors.json"})

#: Field names that only an answer key (or a draft of one) carries.
KEY_FIELDS = re.compile(rb"core_insight|scored_run_ready")

#: Files that name the key fields and were read on 2026-10-03 and kept: the harness and spec code, the
#: tests, and documents that describe the schema or the sign-off process without quoting a key's
#: content. A NEW file that names a key field is excluded until it is reviewed and added here.
KEY_FIELD_REVIEWED = (
    "harness/**", "spec/**", "tests/**", "scripts/export_public_snapshot.py", "scripts/README.md",
    "docs/HANDOVER_FULL.md", "docs/USER_DECISIONS.md", "docs/live_runs/QUALITY_COMPARISON.md",
    "eval/EVAL_PLAN.md", "eval/human_labelling_protocol.md", "eval/prereg.yaml", "eval/prereg_deviations.md",
    "research/audit/fresh_eyes.md", "research/audit/lc12_guard_editlog.md", "research/audit/research_audit.md",
    "research/audit/verify_spec.md", "research/methodology/README.md", "research/methodology/metrics.md",
)

#: Key drafts named explicitly (they quote drafted or signed core insights, or hold a key for the lab's
#: own document), excluded even if the field grep stops matching them.
KEY_DRAFT_FILES = frozenset({
    "research/audit/verify_key_drafts_editlog.md",
    "research/audit/verify_key_signoff_s4_editlog.md",
    "research/grading/worked_examples.md",   # its section 6 is an illustrative key for the lab's document
})

GROUP_WHY = {
    "sealed": "sealed held-out evaluation items (eval/blind/), every file",
    "local-secrets": "local agent configuration and secret-shaped files (.claude/, .env*, *.pem, *.key)",
    "lab-material": "the lab's own material: its sample document runs, MCP probe results, lab documents",
    "answer-keys": "answer keys, the key sign-off sheet and key drafts",
    "recorded-streams": "recorded model streams and recorded tool responses (fixtures)",
    "transcripts": "raw model transcripts, judge and grader logs, and run internals beyond the reports",
    "unscannable": "compressed archives, which the scan cannot read",
    "private-tooling": "the reviewed list of accepted scan findings (.public-allow), a private review record",
}


def _match(path: str, *globs: str) -> bool:
    """fnmatch on a POSIX path where ``**/`` may also match nothing (``**/x`` matches ``x``)."""
    for g in globs:
        if fnmatch.fnmatchcase(path, g):
            return True
        if g.startswith("**/") and fnmatch.fnmatchcase(path, g[3:]):
            return True
    return False


def _live_run_internal(p: str) -> bool:
    parts = PurePosixPath(p).parts
    if len(parts) < 3 or parts[:2] != ("docs", "live_runs"):
        return False
    if len(parts) == 3:                      # docs/live_runs/<file>: a cross-run document, kept
        return False
    if len(parts) == 4:                      # docs/live_runs/<run>/<file>
        return parts[3] not in RUN_KEEP
    return True                              # anything deeper: checkpoints/, shards/, text/, *_pilot*/ ...


@dataclass(frozen=True)
class Rule:
    group: str
    name: str
    test: Callable[[str, bytes], bool]


def _name_has(*needles: str) -> Callable[[str, bytes], bool]:
    return lambda p, _b: any(n.lower() in PurePosixPath(p).name.lower() for n in needles)


def _glob(*globs: str) -> Callable[[str, bytes], bool]:
    return lambda p, _b: _match(p, *globs)


def _answer_key_file(p: str, _b: bytes) -> bool:
    name = PurePosixPath(p).name
    if name.endswith(".schema.json"):        # spec/answer_key.schema.json is the schema, not a key
        return False
    return _match(name, "answer_key*.json", "answer_key*.yaml", "answer_key*.yml")


def _key_field_hit(p: str, b: bytes) -> bool:
    return bool(KEY_FIELDS.search(b)) and not _match(p, *KEY_FIELD_REVIEWED)


#: Ordered; the first matching rule names the exclusion.
RULES: tuple[Rule, ...] = (
    Rule("sealed", "eval/blind/**", _glob("eval/blind/*")),
    Rule("private-tooling", ".public-allow", _glob(ALLOW_FILE)),
    Rule("local-secrets", ".claude/**", _glob(".claude/*", "**/.claude/*")),
    Rule("local-secrets", ".env*", lambda p, _b: PurePosixPath(p).name.startswith(".env")),
    Rule("local-secrets", "*.pem / *.key", _glob("*.pem", "**/*.pem", "*.key", "**/*.key")),
    Rule("lab-material", "docs/live_runs/sit_sample*/**", _glob("docs/live_runs/sit_sample*/*")),
    Rule("lab-material", "research/robustness/mcp_probe_results*.json",
         _glob("research/robustness/mcp_probe_results*.json")),
    Rule("lab-material", "name contains SIT_Memory or Lab Exercise", _name_has("SIT_Memory", "Lab Exercise")),
    Rule("answer-keys", "**/answer_key*.json|yaml", _answer_key_file),
    Rule("answer-keys", "eval/KEY_SIGNOFF.md", _glob("eval/KEY_SIGNOFF.md")),
    Rule("answer-keys", "named key draft", lambda p, _b: p in KEY_DRAFT_FILES),
    Rule("recorded-streams", "tests/fixtures/stream/**", _glob("tests/fixtures/stream/*")),
    Rule("recorded-streams", "**/cassettes/** (recorded tool and model responses)",
         _glob("tests/fixtures/cassettes/*", "**/cassettes/*")),
    Rule("transcripts", "docs/transcripts/** (session transcripts and raw subagent logs)",
         _glob("docs/transcripts/*")),
    Rule("unscannable", "*.gz|zip|tar|tgz|bz2|xz|7z", _glob(*(f"*.{x}" for x in ("gz", "zip", "tar", "tgz", "bz2",
                                                                                   "xz", "7z")))),
    Rule("transcripts", "**/llm.jsonl", _glob("**/llm.jsonl")),
    Rule("transcripts", "**/judge_calls|judge_results|grader_calls.jsonl",
         _glob("**/judge_calls.jsonl", "**/judge_results.jsonl", "**/grader_calls.jsonl")),
    Rule("transcripts", "**/ui/chat.jsonl", _glob("**/ui/chat.jsonl")),
    Rule("transcripts", "docs/live_runs/**/eval_pilot*/** and grade_pilot*/**",
         _glob("docs/live_runs/*/eval_pilot*/*", "docs/live_runs/*/grade_pilot*/*")),
    Rule("transcripts", "docs/live_runs/<run>/ file not on the keep list", lambda p, _b: _live_run_internal(p)),
    Rule("answer-keys", "names a key field (core_insight, scored_run_ready), not reviewed", _key_field_hit),
)


def classify(path: str, blob: bytes) -> Rule | None:
    """The first rule that excludes ``path``, or None when the file is exported."""
    for r in RULES:
        if r.test(path, blob):
            return r
    return None


# ---------------------------------------------------------------------------------------------- scan

def _j(*parts: str) -> str:
    """Join a needle at run time so this file does not trip its own scan."""
    return "".join(parts)


@dataclass
class Finding:
    rule: str
    path: str
    where: str
    length: int


def _scan_rules(user: str | None, home: str | None) -> list[tuple[str, re.Pattern[str]]]:
    tok = r"A-Za-z0-9_\-"
    rules = [
        ("token64", re.compile(rf"(?<![{tok}])[{tok}]{{64}}(?![{tok}])")),
        ("hex32", re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{32}(?![0-9A-Za-z])")),
        ("bearer", re.compile(_j("Bear", r"er\s+") + r"[A-Za-z0-9._~+/=\-]{8,}")),
        ("sk-key", re.compile(r"(?<![A-Za-z0-9])" + _j("s", "k-") + r"[A-Za-z0-9_\-]{6,}")),
        ("api_key", re.compile(_j("api", r"[_\-]?key") + r"\s*[=:]\s*[\"']?[A-Za-z0-9_\-./+]{8,}", re.I)),
        ("oauth", re.compile(_j("o", "auth"), re.I)),
        ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")),
        ("home-path", re.compile(r"(?:/" + _j("Us", "ers") + r"/|/home/)[A-Za-z0-9._\-]+")),
        ("session-link", re.compile(re.escape(_j("claude.ai/code/", "session_")))),
        ("mcp-session-id", re.compile(_j("mcp-", "session-id") + r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-_]{8,}",
                                      re.I)),
    ]
    if user:
        rules.append(("owner-user", re.compile(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", re.I)))
    if home and home not in ("/", ""):
        rules.append(("owner-home", re.compile(re.escape(home))))
    return rules


def _subkind(rule: str, value: str) -> str:
    if rule == "token64" and re.fullmatch(r"[0-9a-f]{64}", value):
        return "hex64"
    if rule == "email" and re.search(r"@(?:[a-z0-9\-]+\.)*example\.(?:com|org|net)$|\.test$|\.invalid$",
                                     value, re.I):
        return "email-example"
    return rule


def _walk_json(v: object, where: str) -> Iterable[tuple[str, str]]:
    if isinstance(v, str):
        yield where, v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield f"{where}.{k}<key>", str(k)
            yield from _walk_json(x, f"{where}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _walk_json(x, f"{where}[{i}]")


def _units(path: str, text: str) -> Iterable[tuple[str, str]]:
    """(field or line, text) pairs: JSON paths for .json and .jsonl, line numbers otherwise."""
    if path.endswith(".json"):
        try:
            yield from _walk_json(json.loads(text), "$")
            return
        except ValueError:
            pass
    for n, line in enumerate(text.splitlines(), 1):
        if path.endswith(".jsonl") and line.strip():
            try:
                yield from _walk_json(json.loads(line), f"line {n} $")
                continue
            except ValueError:
                pass
        yield f"line {n}", line


def scan_tree(root: Path, *, user: str | None, home: str | None) -> tuple[list[Finding], int]:
    rules = _scan_rules(user, home)
    out: list[Finding] = []
    n = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or ".git" in p.relative_to(root).parts:
            continue
        n += 1
        rel = p.relative_to(root).as_posix()
        text = p.read_bytes().decode("utf-8", errors="replace")
        for where, s in _units(rel, text):
            for name, rx in rules:
                for m in rx.finditer(s):
                    if name == "token64" and len(set(m.group(0))) <= 2:
                        continue                       # a ruler such as 64 dashes, not a token
                    out.append(Finding(_subkind(name, m.group(0)), rel, where, len(m.group(0))))
    return out, n


def run_leakage_grep(export: Path, keys: dict[str, bytes]) -> dict[str, object]:
    """The export's own scripts/leakage_grep.py (stdlib only), run in a temporary mirror of the export that
    also holds HEAD's synthetic answer keys at their repository paths, so the script groups key and
    documents per item exactly as it does in the private repository. Only counts are returned."""
    if not (export / "scripts" / "leakage_grep.py").is_file():
        return {"ran": False, "why": "scripts/leakage_grep.py is not in the export"}
    if not keys:
        return {"ran": False, "why": "no synthetic answer key at HEAD to take terms from"}
    with tempfile.TemporaryDirectory(prefix="snapshot_leak_") as tmp:
        mirror = Path(tmp) / "repo"
        shutil.copytree(export, mirror, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for rel, blob in keys.items():
            (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
            (mirror / rel).write_bytes(blob)
        cp = subprocess.run([sys.executable, str(mirror / "scripts" / "leakage_grep.py"), "--json"], cwd=mirror,
                            capture_output=True, text=True, check=False)
    try:
        res = json.loads(cp.stdout)
    except ValueError:
        return {"ran": True, "passed": False, "exit": cp.returncode, "why": "output was not JSON"}
    return {"ran": True, "exit": cp.returncode, "passed": bool(res.get("passed")),
            "sources": len(res.get("sources", [])), "terms": res.get("terms"),
            "files_scanned": res.get("files_scanned"), "hits": len(res.get("hits", [])),
            "unresolved": len(res.get("unresolved", [])), "overlap_failures": len(res.get("overlap_failures", []))}


# ----------------------------------------------------------------------------------------------- git

def _git(repo: Path, *args: str, input_: bytes | None = None) -> bytes:
    cp = subprocess.run(["git", "-C", str(repo), *args], input=input_, capture_output=True, check=False)
    if cp.returncode != 0:
        raise UsageError(f"git {' '.join(args)}: {cp.stderr.decode(errors='replace').strip()}")
    return cp.stdout


class UsageError(Exception):
    pass


@dataclass
class Entry:
    mode: str
    kind: str
    sha: str
    path: str
    blob: bytes = field(default=b"", repr=False)


def head_entries(repo: Path, ref: str) -> list[Entry]:
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", ref)
    out = []
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        mode, kind, sha = meta.decode().split()
        out.append(Entry(mode, kind, sha, path.decode("utf-8")))
    blobs = [e for e in out if e.kind == "blob"]
    if blobs:
        data = _git(repo, "cat-file", "--batch", input_=b"".join(f"{e.sha}\n".encode() for e in blobs))
        pos = 0
        for e in blobs:
            nl = data.index(b"\n", pos)
            size = int(data[pos:nl].split()[2])
            e.blob = data[nl + 1: nl + 1 + size]
            pos = nl + 1 + size + 1
    return out


# ---------------------------------------------------------------------------------------------- note

def snapshot_note(sha: str, date: str, counts: Counter[str], included: int) -> str:
    lines = [
        "# Public snapshot",
        "",
        f"This repository is a snapshot, taken on {date}, of the private working repository {REPO_SLUG}.",
        f"It was exported from commit `{sha}` by `scripts/export_public_snapshot.py`.",
        "No history is carried: this repository has one commit, and the private repository keeps the history.",
        f"It holds {included} files: the agent, the evaluation harness, the schemas, the configuration, "
        "the tests, the documents and the research notes.",
        "",
        "## What was removed, and why",
        "",
    ]
    why = {
        "sealed": "Sealed evaluation items: the held-out set stays unseen so that a later scored run is honest.",
        "answer-keys": "Answer keys, the key sign-off sheet and key drafts: the synthetic design documents are "
                       "here, their keys are not, so they stay usable as a test set.",
        "transcripts": "Raw model transcripts (the working sessions' transcripts and subagent logs, model call "
                       "logs, judge and grader logs) and run internals: each kept run under docs/live_runs/ keeps "
                       "its report, manifest, measurement, configuration and anchors.",
        "lab-material": "The lab's own documents and their runs: they belong to the lab, not to this project.",
        "recorded-streams": "Recorded model streams and recorded tool responses used as test fixtures: they are "
                            "raw model and service output.",
        "local-secrets": "Local agent configuration and secret-shaped files.",
        "unscannable": "Compressed archives: the secret scan cannot read them.",
    }
    for g in ("sealed", "answer-keys", "transcripts", "lab-material", "recorded-streams", "local-secrets",
              "unscannable"):
        if g in why and (counts.get(g, 0) or g != "unscannable"):
            lines.append(f"- {why[g]} ({counts.get(g, 0)} files)")
    lines += [
        "",
        "Some tests and the agent's offline self-test read fixtures or answer keys that were removed, so they "
        "do not all run from this snapshot.",
        "",
        "## Reading the numbers",
        "",
        "The evaluation numbers in `docs/live_runs/QUALITY_COMPARISON.md` are exploratory: the answer key they "
        "were scored against was not signed off, the preregistration was not frozen, and no scored run had "
        "been made.",
        "",
        "## The lab's MCP key",
        "",
        "The lab's MCP API key is not in this tree and never was in the private repository's tree: the probe "
        "script reads it from the environment and redacts it from everything it writes.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- main

def _allowed(f: Finding, allows: list[tuple[str, str]]) -> bool:
    return any(f.rule == r and fnmatch.fnmatchcase(f.path, g) for r, g in allows)


def read_allow_file(path: Path) -> list[str]:
    """``RULE:GLOB  # reason`` per line; blank lines and comment lines are skipped. A reason is required."""
    out = []
    for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        entry, _, reason = ln.partition("#")
        if not entry.strip():
            continue
        if not reason.strip():
            raise UsageError(f"{path}:{n}: an accepted finding needs a reason after '#'")
        out.append(entry.strip())
    return out


def _parse_allow(items: Iterable[str]) -> list[tuple[str, str]]:
    out = []
    for a in items:
        rule, sep, glob = a.partition(":")
        if not sep or not rule or not glob:
            raise UsageError(f"--allow {a!r}: expected RULE:GLOB, e.g. hex64:docs/live_runs/*/manifest.json")
        out.append((rule, glob))
    return out


def export(repo: Path, target: Path, *, ref: str = "HEAD", allow: Iterable[str] = (), allow_dirty: bool = False,
           init_git: bool = False, user: str | None = None, home: str | None = None,
           today: str | None = None, out: Callable[[str], None] = print) -> int:
    repo = Path(_git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    target = target.resolve()
    allows = _parse_allow(allow)
    if target == repo or repo in target.parents:
        raise UsageError(f"target {target} is inside the repository")
    if target.exists() and any(target.iterdir()):
        raise UsageError(f"target {target} is not empty")
    dirty = _git(repo, "status", "--porcelain").decode().splitlines()
    if dirty and not allow_dirty:
        raise UsageError(f"worktree has {len(dirty)} uncommitted or untracked paths; commit them or pass "
                         "--allow-dirty (the export reads HEAD either way)")
    if dirty:
        out(f"note: worktree dirty ({len(dirty)} paths); exporting the committed HEAD only")
    sha = _git(repo, "rev-parse", ref).decode().strip()
    entries = head_entries(repo, sha)

    target.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    by_rule: Counter[tuple[str, str]] = Counter()
    sealed = 0
    included = 0
    keys: dict[str, bytes] = {}
    for e in entries:
        if e.kind != "blob":
            out(f"SKIP     {e.kind:<16} {e.path} (not a file)")
            continue
        rule = classify(e.path, e.blob)
        if rule is not None:
            counts[rule.group] += 1
            by_rule[(rule.group, rule.name)] += 1
            if rule.group == "sealed":
                sealed += 1
                continue                                   # names withheld
            if rule.group == "answer-keys" and _match(e.path, "eval/synthetic/*/answer_key*.json"):
                keys[e.path] = e.blob
            out(f"EXCLUDE  {rule.group:<16} {e.path}  [{rule.name}]")
            continue
        dst = target / e.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if e.mode == "120000":
            os.symlink(e.blob.decode(), dst)
        else:
            dst.write_bytes(e.blob)
            if e.mode == "100755":
                dst.chmod(0o755)
        included += 1
    if sealed:
        out(f"EXCLUDE  {'sealed':<16} eval/blind/** ({sealed} files, names withheld)")

    date = today or dt.date.today().isoformat()
    (target / SNAPSHOT_NOTE).write_text(snapshot_note(sha, date, counts, included + 1), encoding="utf-8")
    included += 1

    out("")
    out(f"source {repo} at {sha}")
    out(f"included {included} files (with {SNAPSHOT_NOTE}); excluded {sum(counts.values())}")
    for (g, name), n in sorted(by_rule.items()):
        out(f"  {g:<16} {n:>4}  {name}")

    findings, scanned = scan_tree(target, user=user, home=home)
    per_rule = Counter(f.rule for f in findings)
    unallowed = [f for f in findings if not _allowed(f, allows)]
    out("")
    out(f"scan: {scanned} files")
    for name in ("token64", "hex64", "hex32", "bearer", "sk-key", "api_key", "oauth", "email", "email-example",
                 "home-path", "owner-user", "owner-home", "session-link", "mcp-session-id"):
        n = per_rule.get(name, 0)
        n_ok = sum(1 for f in findings if f.rule == name and _allowed(f, allows))
        out(f"  {name:<15} {n:>5}" + (f"  ({n_ok} allowed)" if n_ok else ""))
    grouped: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for f in findings:
        grouped[(f.rule, f.path)].append(f)
    for (rule, path), fs in sorted(grouped.items()):
        tag = "allowed" if all(_allowed(f, allows) for f in fs) else "FINDING"
        lens = sorted(Counter(f.length for f in fs).items())
        wheres = ", ".join(f.where for f in fs[:4]) + (f", ... ({len(fs)} in all)" if len(fs) > 4 else "")
        out(f"  {tag} {rule}:{path}  n={len(fs)} lengths={dict(lens)}  at {wheres}")
    for r, g in allows:
        if not any(f.rule == r and fnmatch.fnmatchcase(f.path, g) for f in findings):
            out(f"  note: --allow {r}:{g} matched nothing")

    leak = run_leakage_grep(target, keys)
    out("")
    out("leakage_grep: " + json.dumps(leak, sort_keys=True))

    leak_ok = (not leak.get("ran")) or bool(leak.get("passed"))
    if unallowed or not leak_ok:
        out("")
        out(f"NOT GOOD: {len(unallowed)} unallowed scan findings; leakage_grep "
            f"{'passed' if leak_ok else 'FAILED'}. No commit made.")
        return 1
    out("")
    out("scan clean (every finding allowed)" if findings else "scan clean")
    if init_git:
        _git(target, "init", "-q", "-b", "main")
        _git(target, "add", "--all", ".")
        _git(target, "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify",
             "-m", f"Public snapshot of {REPO_SLUG} at {sha[:12]}")
        out(_git(target, "log", "--oneline").decode().rstrip())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--target", required=True, type=Path, help="empty directory outside the repository")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--allow", action="append", default=[], metavar="RULE:GLOB",
                    help="accept the findings of RULE in files matching GLOB (repeatable)")
    ap.add_argument("--allow-file", type=Path, help=f"file of RULE:GLOB  # reason lines (e.g. {ALLOW_FILE})")
    ap.add_argument("--allow-dirty", action="store_true", help="run although the worktree has uncommitted changes")
    ap.add_argument("--init-git", action="store_true", help="git init the target with ONE commit (never pushed)")
    ap.add_argument("--user", default=Path.home().name, help="user name to scan for (default: this account's)")
    ap.add_argument("--home", default=str(Path.home()), help="home path to scan for (default: this account's)")
    a = ap.parse_args(argv)
    try:
        allow = [*a.allow, *(read_allow_file(a.allow_file) if a.allow_file else [])]
        return export(a.repo, a.target, ref=a.ref, allow=allow, allow_dirty=a.allow_dirty, init_git=a.init_git,
                      user=a.user, home=a.home)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
