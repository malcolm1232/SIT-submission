"""Cross-links for the HTML export (5 Oct 2026): every identifier a cold reader cannot resolve becomes a link.

The review's words are ``report.md`` rendered by :mod:`sit_review_agent.ui.export`; this module never changes them.
It only wraps text that is already there in ``<a>`` (and ``<abbr>`` / ``<span>``) elements, so the page with the
tags stripped reads exactly as the plain rendering (``tests/test_ui_export_links.py`` checks this). What a link
points at is either a place in the review itself (a finding card, a limitation, a sound area, a research
question, a row of the evidence register) or an entry of the reference part the export adds after the review,
visibly labelled as added by the export:

* the run's decision registry (``report.json`` ``decision_registry``), the evidence ledger (``evidence_ledger``),
  each with its place in the reviewed document and the findings that cite it;
* the reviewed document's extracted text (``text/<doc>.pages.txt``), page by page with its sections marked and
  every passage the review quotes highlighted, so a page or section reference resolves inside the one file even
  when it is emailed alone; where the PDF is beside the page (the zip, the server, the app's Review tab) each page
  links to it;
* "How to read this review": the review's own vocabulary taken from the code and the prompts (kinds,
  categories, severities, dispositions, verdict labels, the confidence number, rank, the reporting threshold,
  the tools rows, the coverage criteria of this run's config) and the abbreviations the document defines.

Generic by pattern and by the run's data: a target is made only from what the run holds, and a mention whose
target does not exist stays plain text (never a dead link, never an invented target).
"""

from __future__ import annotations

import html as _html
import json
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from sit_review_agent.ui.rundata import read_json

#: The run's own identifier families (``models.py`` id patterns, plus the research-question ids of the
#: research log and the document id). A mention matches only when the id is in the run's data.
RUN_ID_RE = re.compile(r"\b(?:FND|EV|DEG|SA|RQ|AD)-\d{3,}\b")
DOC_ID_RE = re.compile(r"\bDOC-[A-Za-z0-9_.-]*[A-Za-z0-9_]\b")
TAG_RE = re.compile(r"(<[^>]*>)")
SENT = "\x00"


def _attr(s: str) -> str:
    return escape(s, quote=True)


def _norm_char(c: str) -> str:
    return {"—": "-", "–": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
            " ": " "}.get(c, c)


def _normalise(text: str) -> tuple[str, list[int]]:
    """``text`` with dashes and quotes made plain and every whitespace run one space, and for each kept
    character its index in ``text``."""
    out: list[str] = []
    where: list[int] = []
    for i, c in enumerate(text):
        c = _norm_char(c)
        if c.isspace():
            if out and out[-1] == " ":
                continue
            c = " "
        out.append(c)
        where.append(i)
    return "".join(out), where


# ------------------------------------------------------------------ the reviewed document's text


@dataclass
class Doc:
    """One document's extracted text as the run read it: pages, sections, and the passages the export marks."""

    doc_id: str
    prefix: str                     # "doc" for the document under review, "doc2", ... for the others
    title: str
    text: str
    pages: list[tuple[int, int, int]]                       # (number, char_start, char_end)
    sections: list[dict[str, Any]]
    norm: str = ""
    nmap: list[int] = field(default_factory=list)
    ranges: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.norm, self.nmap = _normalise(self.text)
        self._starts = [p[1] for p in self.pages]
        self.section_ids = {str(s.get("section_id")): s for s in self.sections if s.get("section_id")}

    def page_of(self, pos: int) -> int | None:
        i = bisect_right(self._starts, pos) - 1
        return self.pages[i][0] if 0 <= i < len(self.pages) else None

    def page_range(self, n: int) -> tuple[int, int] | None:
        return next(((s, e) for num, s, e in self.pages if num == n), None)

    def has_page(self, n: int) -> bool:
        return self.page_range(n) is not None

    def locate(self, quote: str, page: int | None = None) -> tuple[int, int] | None:
        """The span of ``quote`` in the text (dashes, quotes and whitespace normalised), searched on ``page``
        first, then anywhere; ``None`` when it is not there."""
        q = _normalise(_html.unescape(quote).strip())[0].strip()
        if len(q) < 8:
            return None
        lo, hi = 0, len(self.norm)
        if page is not None and (pr := self.page_range(page)) is not None:
            lo = bisect_right(self.nmap, pr[0] - 1)
            hi = bisect_right(self.nmap, pr[1])
        for a, b in ((lo, hi), (0, len(self.norm))):
            i = self.norm.find(q, a, b) if b - a >= len(q) else -1
            if i >= 0:
                return self.nmap[i], self.nmap[i + len(q) - 1] + 1
        return None

    def mark(self, span: tuple[int, int]) -> str:
        """A placeholder href for the passage ``span``; :meth:`resolve` turns it into the mark's id once every
        passage is known (overlapping passages share one mark)."""
        self.ranges.append(span)
        return f"#{SENT}P{self.prefix}:{span[0]}:{span[1]}{SENT}"

    def segments(self) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for s, e in sorted(set(self.ranges)):
            if out and s <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], e))
            else:
                out.append((s, e))
        return out

    def mark_id(self, segs: list[tuple[int, int]], start: int) -> str:
        i = bisect_right([s for s, _ in segs], start) - 1
        return f"{self.prefix}-q{i + 1}"

    def section_label(self, sid: str) -> str:
        s = self.section_ids.get(sid)
        return f"§{sid} {s.get('heading')}" if s else f"§{sid}"

    def definition_line(self, ident: str) -> tuple[int, int] | None:
        """The line of the document's text that defines ``ident``: the first line that starts with it. Only that
        line is marked: the extracted text of a table can put the rest of a multi-line cell on the lines around
        it, interleaved with the neighbouring rows, so the export does not guess which of those belong to it."""
        m = re.search(rf"(?m)^{re.escape(ident)}(?=[ :.\t]|$)", self.text)
        if not m:
            return None
        end = self.text.find("\n", m.start())
        return m.start(), len(self.text) if end < 0 else end


def load_docs(run_dir: Path, report: dict[str, Any]) -> list[Doc]:
    docs = ((report.get("metadata") or {}).get("documents") or []) if isinstance(report, dict) else []
    docs = sorted(docs, key=lambda d: d.get("role") != "under_review")
    out: list[Doc] = []
    for d in docs:
        did = str(d.get("doc_id") or "")
        rel = d.get("text_path") or f"text/{did}.pages.txt"
        tp = run_dir / rel
        sp = run_dir / "text" / f"{did}.sections.json"
        if not did or not tp.is_file():
            continue
        text = tp.read_text(encoding="utf-8")
        sec = read_json(sp) or {}
        pages = [(int(p["number"]), int(p["char_start"]), int(p["char_end"])) for p in sec.get("pages") or []
                 if isinstance(p, dict) and {"number", "char_start", "char_end"} <= set(p)]
        if not pages:                                   # no sections file: cut at the [[PAGE n]] markers
            marks = list(re.finditer(r"\[\[PAGE (\d+)\]\]\n?", text))
            pages = [(int(m.group(1)), m.end(), marks[i + 1].start() if i + 1 < len(marks) else len(text))
                     for i, m in enumerate(marks)]
        if not pages:
            continue
        out.append(Doc(did, "doc" if not out else f"doc{len(out) + 1}", str(d.get("title") or did), text, pages,
                       [s for s in sec.get("sections") or [] if isinstance(s, dict)]))
    return out


# ------------------------------------------------------------------ the review's own vocabulary


@dataclass
class Term:
    key: str                # the glossary entry's id, without the "g-" prefix
    label: str
    html: str               # the definition (already escaped)
    src: str                # where the definition comes from


def _system_md_terms(root: Path) -> dict[str, Term]:
    """Kinds, categories, severities and dispositions as ``prompts/system.md`` defines them for the model."""
    path = root / "prompts" / "system.md"
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    out: dict[str, Term] = {}
    groups = {"Finding kinds": "kind", "Severity": "sev", "Disposition": "disp"}
    group = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("## "):
            group = next((g for h, g in groups.items() if ln[3:].startswith(h)), None)
            if ln[3:].startswith("Defect categories"):
                para, j = [], i + 1
                while j < len(lines) and not lines[j].startswith("## "):
                    para.append((j, lines[j]))
                    j += 1
                text = " ".join(t for _, t in para)
                for m in re.finditer(r"`([a-z_]+)`(?: \(([^)]*)\))?", text):
                    at = next((k + 1 for k, t in para if f"`{m.group(1)}`" in t), i + 1)
                    desc = m.group(2) or m.group(1).replace("_", " ")
                    out[f"cat-{m.group(1)}"] = Term(f"cat-{m.group(1)}", m.group(1).replace("_", " "),
                                                    escape(desc[0].upper() + desc[1:] + "."), f"prompts/system.md:{at}")
                i = j
                continue
        elif group and (m := re.match(r"- `([a-z_]+)`: (.*)", ln)):
            body, j = [m.group(2)], i + 1
            while j < len(lines) and lines[j].startswith("  "):
                body.append(lines[j].strip())
                j += 1
            text = " ".join(body)
            out[f"{group}-{m.group(1)}"] = Term(f"{group}-{m.group(1)}", m.group(1).replace("_", " "),
                                                escape(text[0].upper() + text[1:]), f"prompts/system.md:{i + 1}")
            i = j
            continue
        i += 1
    return out


def _line_of(path: Path, needle: str) -> int | None:
    try:
        for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in ln:
                return n
    except OSError:
        return None
    return None


def _src(root: Path, rel: str, needle: str, span: int = 0) -> str:
    n = _line_of(root / rel, needle)
    if n is None:
        return rel
    return f"{rel}:{n}" + (f"-{n + span}" if span else "")


def confidence_entry(root: Path) -> Term:
    """How the confidence number and its band are made, as the code does it (no formula of the export's own)."""
    sysmd = _src(root, "prompts/system.md", "## Confidence (", 4)
    band = _src(root, "agent/sit_review_agent/report/render.py", "def confidence_band", 2)
    clamp = _src(root, "agent/sit_review_agent/phases/_model_calls.py", "def _clamp", 1)
    vclamp = _src(root, "agent/sit_review_agent/phases/report.py", "confidence=min(1.0, max(0.0, float(v.confidence)))")
    rule = _src(root, "agent/sit_review_agent/phases/report.py", "confidence=0.5,")
    vprompt = _src(root, "prompts/report.md", "Let the degradations listed below set your confidence", 1)
    refine = _src(root, "agent/sit_review_agent/phases/refine.py", "CONCLUSION_FIELDS =")
    body = (
        "<p>The number is the model's own estimate, not computed by code. For a finding, the assess call gives it "
        "under the review standard's calibration rule: \"a number between 0 and 1: the probability that the "
        "finding is correct and material\"; 0.8 or more only when the location is exact and any external premise "
        "rests on a primary source or on two independent sources; 0.5 to 0.8 when an external premise rests on one "
        "secondary source or on reasoning alone; below 0.5 when a key premise is unverified or sources conflict "
        f"(<code>{escape(sysmd)}</code>).</p>"
        f"<p>Code only clamps it to the range 0 to 1 (<code>{escape(clamp)}</code>). Refine does not change it: a "
        f"refine revision carries rank, severity and disposition but no confidence (<code>{escape(refine)}</code>).</p>"
        "<p>For the verdict, the verdict call gives the number and is told to let the run's degradations set it "
        f"(<code>{escape(vprompt)}</code>); code clamps it to 0 to 1 (<code>{escape(vclamp)}</code>). When no model "
        f"verdict is available, the verdict is derived by rule with a fixed confidence of 0.5 (<code>{escape(rule)}"
        "</code>).</p>"
        "<p>The word in brackets is a band that code derives from the number: <b>high</b> at 0.80 or more, "
        f"<b>medium</b> at 0.50 or more, <b>low</b> below 0.50 (<code>{escape(band)}</code>).</p>")
    return Term("confidence", "Confidence (and its band)", body, f"{sysmd}; {band}")


def vocabulary(root: Path, run_dir: Path, report: dict[str, Any]) -> dict[str, Term]:
    terms = _system_md_terms(root)
    rp = "prompts/report.md"
    terms["verdict-fit"] = Term("verdict-fit", "fit", escape(
        "The verdict without conditions. The verdict must agree with the findings: an open critical or high finding "
        "is not compatible with an unconditional fit."), _src(root, rp, "critical or high finding is not compatible"))
    terms["verdict-fit_with_conditions"] = Term("verdict-fit_with_conditions", "fit with conditions", escape(
        "The verdict with conditions: each condition is stated and linked to the finding IDs it depends on (the "
        "Conditions list under Fitness for purpose)."), _src(root, rp, "For `fit_with_conditions`"))
    terms["verdict-not_fit"] = Term("verdict-not_fit", "not fit", escape(
        "One of the three verdicts the review gives (fit, fit with conditions, not fit), each with a rationale, a "
        "confidence, a verdict per objective and what evidence would change it."), _src(root, rp, "- Give one verdict"))
    terms["verdict-not_assessed"] = Term("verdict-not_assessed", "not assessed", escape(
        "Set by code only, when the run produced no assessment: no judgement of the design."),
        _src(root, "agent/sit_review_agent/models.py", "NOT_ASSESSED = "))
    terms["confidence"] = confidence_entry(root)
    terms["rank"] = Term("rank", "Rank", escape(
        "The finding's place in the review's order; rank 1 comes first. Assess ranks the merged findings by severity "
        "(critical first; a strength, which has none, last), then by confidence; the refine call may re-rank them."),
        _src(root, "agent/sit_review_agent/phases/assess.py", "Ranks 1..n by severity"))
    cfg = read_json(run_dir / "effective_config.json") or {}
    sev = str(((cfg.get("agent") or {}).get("report") or {}).get("min_severity") or "")
    terms["threshold"] = Term("threshold", "Reporting threshold", escape(
        "Findings below this severity are listed only in the appendix (config/agent.yaml, report.min_severity"
        + (f"; this run: {sev}" if sev else "") + ")."), _src(root, "config/agent.yaml", "min_severity:"))
    terms["tools-used"] = Term("tools-used", "Tools used", escape(
        "The enabled research tool servers that received at least one call in this run; \"none\" means no "
        "external research tool was called."), _src(root, "agent/sit_review_agent/report/render.py",
                                                    '# "Tools used"'))
    terms["tools-disabled"] = Term("tools-disabled", "Tools disabled", escape(
        "The research tool servers that were switched off for this run."),
        _src(root, "agent/sit_review_agent/report/render.py", '"disabled_tools":'))
    for c in cfg.get("criteria", {}).get("criteria", []) if isinstance(cfg.get("criteria"), dict) else []:
        if isinstance(c, dict) and c.get("id") and c.get("question"):
            terms[f"crit-{c['id']}"] = Term(f"crit-{c['id']}", str(c["id"]), escape(str(c["question"])),
                                            "this run's effective_config.json, criteria")
    for k, (label, text) in ID_FAMILIES.items():
        terms[f"id-{k}"] = Term(f"id-{k}", f"{k}-nnn: {label}", escape(text), "agent/sit_review_agent/models.py")
    terms.update(run_log_terms(root))
    return terms


def _bullets(root: Path, rel: str, after: str, prefix: str) -> dict[str, Term]:
    """The ``- `name`: text`` bullets of ``rel`` that follow the first line holding ``after`` (a bullet's
    continuation lines are indented deeper than its dash; the list ends at the first other line), each as the
    term ``prefix-name`` with its own words and line."""
    try:
        lines = (root / rel).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    start = next((i for i, ln in enumerate(lines) if after in ln), None)
    out: dict[str, Term] = {}
    i = len(lines) if start is None else start + 1
    while i < len(lines):
        m = re.match(r"( *)- `([a-z_]+)`: (.*)", lines[i])
        if not m:
            if out:
                break
            i += 1
            continue
        body, j = [m.group(3)], i + 1
        while j < len(lines) and lines[j].startswith(" " * (len(m.group(1)) + 1)) and lines[j].strip() \
                and not re.match(r" *- `", lines[j]):
            body.append(lines[j].strip())
            j += 1
        text = " ".join(body).rstrip(";").rstrip()
        text = text[0].upper() + text[1:] + ("" if text.endswith(".") else ".")
        out[f"{prefix}-{m.group(2)}"] = Term(f"{prefix}-{m.group(2)}", m.group(2).replace("_", " "), escape(text),
                                            f"{rel}:{i + 1}")
        i = j
    return out


def _coverage_terms(root: Path) -> dict[str, Term]:
    """The outcomes of an assess coverage row, as ``prompts/assess.md`` asks for them."""
    rel = "prompts/assess.md"
    try:
        lines = (root / rel).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    at = next((i for i, ln in enumerate(lines) if "`coverage`: exactly one row per criterion" in ln), None)
    if at is None:
        return {}
    para = []
    for ln in lines[at:]:
        if not ln.strip() or (para and re.match(r"\d+\. ", ln)):
            break
        para.append(ln.strip())
    text = " ".join(para)
    out: dict[str, Term] = {}
    for m in re.finditer(r"`(findings|no_issue|not_applicable)` \(([^)]*)\)", text):
        desc = m.group(2).replace("`", "")
        out[f"cov-{m.group(1)}"] = Term(
            f"cov-{m.group(1)}", m.group(1).replace("_", " "),
            escape(f"A coverage row's outcome for one criterion of the shard ({desc}). Each shard gives exactly one "
                   "row per criterion it assessed."), f"{rel}:{at + 1}")
    return out


def run_log_terms(root: Path) -> dict[str, Term]:
    """The words the page's Run log uses beyond the review's own vocabulary: the registry types, the review
    inputs, the coverage outcomes, the refine actions, the anchor states, a draft, the shard marker and an
    external research question. Each is the prompt's or the code's own text where one defines the word, else
    a sentence that says what the named code does."""
    terms: dict[str, Term] = {}
    terms.update(_bullets(root, "prompts/understand.md", "4. `registry`:", "reg"))
    terms.update(_bullets(root, "prompts/refine.md", "## Revision rules", "rev"))
    terms.update(_coverage_terms(root))
    und = "prompts/understand.md"
    terms["review-input"] = Term("review-input", "review input found", escape(
        "Comments, review notes or claims of fixes by other people that the document contains (for example a change "
        "log entry saying an issue was fixed, or a reviewer's remark), each as one short sentence with its location. "
        "Treated as claims to check, not as facts."), _src(root, und, "`review_inputs_found`: comments"))
    anchor = "agent/sit_review_agent/ingest/anchor.py"
    terms["anchor-resolved"] = Term("anchor-resolved", "resolved", escape(
        "The verbatim quote was found in the canonical text of the cited page and the pages next to it, narrowed to "
        "the cited section and its neighbours: first as the normalised text holds it word for word, else as a "
        "close match (partial ratio at or above the run's fuzzy threshold)."),
        _src(root, anchor, 'status = "unresolved"'))
    terms["anchor-repaired"] = Term("anchor-repaired", "repaired", escape(
        "The quote first failed, and the one repair call's new quote for it was found by the same rules."),
        _src(root, anchor, 'status = "unresolved"'))
    terms["anchor-unresolved"] = Term("anchor-unresolved", "unresolved", escape(
        "The quote was not found in its window by those rules (the reasons name why, such as not_found). A finding "
        "with no anchor that resolves moves to the unresolved list as Unverified."),
        _src(root, anchor, 'status = "unresolved"'))
    terms["run-draft"] = Term("run-draft", "draft, unverified", escape(
        "An item as a model call wrote it, before refine and verify: it has not been checked against the page text "
        "or merged with the other shards' findings, so its ID, rank and severity can change and it can be "
        "withdrawn."), _src(root, "agent/sit_review_agent/progress.py", "and unverified (it has not been through"))
    terms["run-shard"] = Term("run-shard", "n/N (shard marker)", escape(
        "Assess shard n of the run's N shards: the criterion groups of config/agent.yaml assess.shards, one model "
        "call each, run side by side in stage 1. Each criterion is in exactly one group."),
        _src(root, "config/agent.yaml", "# shards: criterion groups"))
    terms["q-external"] = Term("q-external", "needs external research", escape(
        "Set only when the document alone cannot settle the question: a product's documented capability or limit, "
        "the text of a standard or regulation the design relies on, published performance or failure behaviour of "
        "a named component, or a recognised test method. Other questions are answered from the document."),
        _src(root, "prompts/plan.md", "Set `needs_external: true` only when"))
    return terms


def term_text(term: Term) -> dict[str, Any]:
    """A term for a page that inserts text only: its label, its definition as plain paragraphs (tags dropped,
    entities decoded) and its source."""
    paras = [p for p in re.split(r"</p>\s*<p>|</?p>", term.html) if p.strip()] or [term.html]
    return {"label": term.label, "paras": [_html.unescape(re.sub(r"<[^>]+>", "", p)).replace("`", "").strip()
                                           for p in paras], "src": term.src}


ID_FAMILIES: dict[str, tuple[str, str]] = {
    "FND": ("finding", "One finding of the review: a strength, risk, gap, ambiguity, unresolved assumption or "
                       "validation need, with its card under its kind's heading."),
    "EV": ("evidence item", "One entry of the run's evidence ledger: a quoted passage of the document (doc), an "
                            "external source (external), or a conclusion drawn from other items (inference)."),
    "DEG": ("degradation", "Something that limited this run (an input, tool, model or time limit), listed under "
                           "Evidence limitations."),
    "SA": ("sound area", "An area of the design the review found sound, listed under Areas where no change is "
                         "needed."),
    "AD": ("decision registry entry", "A decision, constraint or requirement the review extracted from the "
                                      "document and checked its findings against (preserves, refines or "
                                      "challenges)."),
    "RQ": ("research question", "A question the review planned to answer from external sources."),
}


# ------------------------------------------------------------------ the index of targets


class Index:
    """Every target of the export's links, from the run's data, and the linker that uses it."""

    def __init__(self, run_dir: Path, report: dict[str, Any], *, root: Path, pdf_href: str | None) -> None:
        self.run_dir, self.report, self.pdf_href = run_dir, report if isinstance(report, dict) else {}, pdf_href
        r = self.report
        self.docs = load_docs(run_dir, r)
        self.doc = self.docs[0] if self.docs else None
        self.by_doc = {d.doc_id: d for d in self.docs}
        self.findings = {str(f.get("id")): f for f in r.get("findings") or [] if isinstance(f, dict)}
        self.ledger = {str(e.get("evidence_id")): e for e in r.get("evidence_ledger") or [] if isinstance(e, dict)}
        self.registry = {str(e.get("registry_id")): e for e in r.get("decision_registry") or [] if isinstance(e, dict)}
        self.degs = {str(d.get("id")): d for d in (r.get("research_log") or {}).get("degradations") or []
                     if isinstance(d, dict)}
        self.sound = {str(s.get("id")): s for s in r.get("sound_areas") or [] if isinstance(s, dict)}
        self.terms = vocabulary(root, run_dir, r)
        #: id -> href for the targets that exist in the page (filled by :meth:`declare` as the page is built)
        self.targets: dict[str, str] = {}
        self.doc_ids: dict[str, str] = {}
        self.doc_prefixes = self._doc_id_prefixes()
        self.abbrs = self._abbreviations()
        self.counts: dict[str, list[int]] = {}

    # -------------------------------------------------------------- targets

    def declare(self, ident: str, href: str | None = None) -> None:
        self.targets.setdefault(ident, href or f"#{ident}")

    def _doc_id_prefixes(self) -> list[str]:
        """The document's own ids (requirements, principles, ...) the registry or the intent names, each to its
        registry entry (by ``doc_ref`` first, then ``requirement_ids``) or to the row of the document that
        defines it. The prefixes found there also admit ids of the same family the registry does not hold."""
        known: set[str] = set()
        for e in self.registry.values():
            known.update(str(x) for x in (e.get("doc_anchor") or {}).get("requirement_ids") or [])
            ref = str(e.get("doc_ref") or "")
            if re.fullmatch(r"[A-Z]{1,5}-?\d+", ref):
                known.add(ref)
        intent = self.report.get("intent_summary") or {}
        for k in ("objectives", "constraints", "key_assumptions"):
            for o in intent.get(k) or []:
                if isinstance(o, dict) and o.get("ref") and re.fullmatch(r"[A-Z]{1,5}-?\d+", str(o["ref"])):
                    known.add(str(o["ref"]))
        return sorted({re.match(r"[A-Z]+-?", k).group(0) for k in known}, key=len, reverse=True)

    def doc_id_href(self, ident: str) -> str | None:
        if ident in self.doc_ids:
            return self.doc_ids[ident] or None
        href: str | None = None
        by_ref = [k for k, e in self.registry.items() if str(e.get("doc_ref") or "") == ident]
        by_req = [k for k, e in self.registry.items()
                  if ident in [str(x) for x in (e.get("doc_anchor") or {}).get("requirement_ids") or []]]
        if by_ref or by_req:
            href = f"#{(by_ref or by_req)[0]}"
        elif self.doc is not None and (span := self.doc.definition_line(ident)) is not None:
            href = self.doc.mark(span)
        self.doc_ids[ident] = href or ""
        return href

    def _abbreviations(self) -> dict[str, tuple[str, str]]:
        """Abbreviations the document defines as "Long Name (ABBR)": the shortest run of words before the bracket
        whose initials spell the abbreviation. ABBR -> (expansion, where)."""
        out: dict[str, tuple[str, str]] = {}
        if self.doc is None:
            return out
        for m in re.finditer(r"((?:[A-Za-z][\w-]*[ ]){1,8})\(([A-Z]{2,6})\)", self.doc.text):
            abbr, words = m.group(2), m.group(1).split()
            if abbr in out:
                continue
            for k in range(1, len(words) + 1):
                cand = words[-k:]
                initials = "".join(w[0] for w in cand if w[0].isupper())
                if initials == abbr and cand[0][0].isupper():
                    page = self.doc.page_of(m.start())
                    out[abbr] = (" ".join(cand), f"p.{page}" if page else "")
                    break
        return out

    # -------------------------------------------------------------- linking text

    def count(self, family: str, linked: bool) -> None:
        c = self.counts.setdefault(family, [0, 0])
        c[0] += 1
        c[1] += int(linked)

    def a(self, href: str, text: str, cls: str, family: str, title: str | None = None) -> str:
        self.count(family, True)
        t = f' title="{_attr(title)}"' if title else ""
        return f'<a class="xref {cls}" href="{href}"{t}>{text}</a>'

    def page_href(self, page: int, doc: Doc | None = None) -> str | None:
        d = doc or self.doc
        return f"#{d.prefix}-p{page}" if d is not None and d.has_page(page) else None

    def section_href(self, sid: str, doc: Doc | None = None) -> str | None:
        d = doc or self.doc
        return f"#{d.prefix}-s{sid}" if d is not None and sid in d.section_ids else None

    def location(self, page: str, sec: str, quote: str | None, doc: Doc | None = None) -> str | None:
        d = doc or self.doc
        if d is None:
            return None
        pg = int(page) if page.isdigit() else None
        if quote and (span := d.locate(quote, pg)) is not None:
            return d.mark(span)
        return (self.page_href(pg, d) if pg is not None else None) or self.section_href(sec, d)

    def link_ids(self, text: str) -> str:
        """Run ids, document ids, the document id and the confidence number in one escaped text run."""
        def run_id(m: re.Match[str]) -> str:
            ident = m.group(0)
            fam = ident.split("-", 1)[0]
            href = self.targets.get(ident)
            if href is None:
                self.count(fam, False)
                return ident
            return self.a(href, ident, f"x-{fam.lower()}", fam)

        def doc_id(m: re.Match[str]) -> str:
            ident = m.group(0)
            href = self.doc_id_href(ident)
            if not href:
                self.count("doc-id", False)
                return ident
            title = None
            if href.startswith("#AD-") and (e := self.registry.get(href[1:])):
                title = f"{ident}: {e.get('statement')}"
            return self.a(href, ident, "x-docid", "doc-id", title)

        def doc_name(m: re.Match[str]) -> str:
            d = self.by_doc.get(m.group(0))
            if d is None:
                self.count("DOC", False)
                return m.group(0)
            return self.a(f"#{d.prefix}-text", m.group(0), "x-doc", "DOC", d.title)

        def conf(m: re.Match[str]) -> str:
            return self.a("#g-confidence", m.group(0), "x-term", "confidence",
                          "How confidence is derived")

        pats: list[tuple[re.Pattern[str], Any]] = [(RUN_ID_RE, run_id), (DOC_ID_RE, doc_name),
                                                   (re.compile(r"\bconfidence \d\.\d\d\b"), conf)]
        if self.doc_prefixes:
            pats.append((re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(p) for p in self.doc_prefixes)
                                    + r")\d+\b(?!-)"), doc_id))
        if self.abbrs:
            pats.append((re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, self.abbrs), key=len, reverse=True))
                                    + r")\b"), self._abbr))
        pats.append((re.compile(r"\b(?:fit_with_conditions|not_fit|not_assessed|refinement_now|needs_investigation"
                                r"|needs_prototyping|needs_testing|governance_decision|no_change)\b"), self._word))
        return _multi_sub(text, pats)

    def _abbr(self, m: re.Match[str]) -> str:
        exp, where = self.abbrs[m.group(0)]
        self.count("abbr", True)
        title = exp + (f" (defined in the document, {where})" if where else "")
        return (f'<abbr class="x-abbr" title="{_attr(title)}">'
                f"{m.group(0)}</abbr>")

    def _word(self, m: re.Match[str]) -> str:
        w = m.group(0)
        key = f"verdict-{w}" if w in ("fit_with_conditions", "not_fit", "not_assessed") else f"disp-{w}"
        if key not in self.terms:
            return w
        return self.a(f"#g-{key}", w, "x-term", "term", self.terms[key].label)

    def link_text(self, text: str, *, quotes: bool = True) -> str:
        """One escaped text run of the review with every reference in it linked. ``quotes=False`` for the text
        inside a quotation, which holds no location with a quote of its own."""
        store: list[str] = []

        uid = f"k{id(store)}"

        def keep(s: str) -> str:
            store.append(s)
            return f"{SENT}{uid}.{len(store) - 1}{SENT}"

        def where(m: re.Match[str]) -> str:
            page, sec, ids, quote = m.group(1), m.group(2), m.group(3), m.group(4)
            href = self.location(page, sec, quote)
            loc = f"p.{page} §{sec}"
            out = self.a(href, loc, "x-loc", "page/section", self._loc_title(page, sec)) if href else loc
            if not href:
                self.count("page/section", False)
            if ids is not None:
                out += " (" + self.link_ids(ids) + ")"
            if quote is not None:
                out += f': <span class="x-q">&quot;{self.link_text(quote, quotes=False)}&quot;</span>'
            return keep(out)

        def doc_cite(m: re.Match[str]) -> str:
            quote, did, page, sec = m.group(1), m.group(2), m.group(3), m.group(4)
            d = self.by_doc.get(did)
            href = self.location(page, sec, quote, d) if d else None
            cite = f"[doc:{did}#p{page}/s{sec}]"
            out = ""
            if quote is not None:
                out = f'<span class="x-q">&quot;{self.link_text(quote, quotes=False)}&quot;</span> '
            if href:
                out += self.a(href, cite, "x-loc x-cite", "doc anchor", f"{did} p.{page} §{sec}")
            else:
                self.count("doc anchor", False)
                out += cite
            return keep(out)

        def sections(m: re.Match[str]) -> str:
            word, body = m.group(1), m.group(2)

            def one(n: re.Match[str]) -> str:
                href = self.section_href(n.group(0))
                if href is None:
                    self.count("section", False)
                    return n.group(0)
                return self.a(href, n.group(0), "x-loc", "section", self._sec_title(n.group(0)))
            if re.fullmatch(r"\d+(?:\.\d+)*", body):               # one section: the whole phrase is the link
                href = self.section_href(body)
                if href is not None:
                    return keep(self.a(href, f"{word} {body}", "x-loc", "section", self._sec_title(body)))
            return keep(word + " " + re.sub(r"\d+(?:\.\d+)*", one, body))

        def bare_sec(m: re.Match[str]) -> str:
            href = self.section_href(m.group(1))
            if href is None:
                self.count("section", False)
                return m.group(0)
            return keep(self.a(href, m.group(0), "x-loc", "section", self._sec_title(m.group(1))))

        if quotes:
            text = self._locations(text, keep, where, doc_cite)
        text = re.sub(r"\b([Ss]ections?) ((?:\d+(?:\.\d+)*)(?:(?:, and |, | and | or | to |/|-)\d+(?:\.\d+)*)*)",
                      sections, text)
        text = re.sub(r"(?<![\w.])§(\d+(?:\.\d+)*)", bare_sec, text)
        text = re.sub(r"\bdoc:([A-Za-z0-9_.-]+)#p(\d+)/s([0-9.]*[0-9])\b",
                      lambda m: keep(self._bare_cite(m)), text)
        text = self.link_ids(text)
        while SENT in text:
            new = re.sub(f"{SENT}{uid}\\.(\\d+){SENT}", lambda m: store[int(m.group(1))], text)
            if new == text:
                break
            text = new
        return text

    def _locations(self, text: str, keep: Any, where: Any, doc_cite: Any) -> str:
        text = re.sub(r"p\.(\d+|-) §(\d+(?:\.\d+)*)(?: \(((?:[A-Z]{1,5}-?\d+(?:, )?)+)\))?"
                      r"(?:: &quot;((?:(?!&quot;).)*)&quot;)?", where, text)
        text = re.sub(r": &quot;((?:(?!&quot;).)*)&quot; (?=\[(?!doc:)[a-z]+:)",
                      lambda m: keep(': <span class="x-q">&quot;' + self.link_text(m.group(1), quotes=False)
                                     + "&quot;</span> "),
                      text)
        text = re.sub(r"(?:&quot;((?:(?!&quot;).)*)&quot; )?\[doc:([A-Za-z0-9_.-]+)#p(\d+)/s([0-9.]*[0-9])\]",
                      doc_cite, text)
        return text

    def _bare_cite(self, m: re.Match[str]) -> str:
        d = self.by_doc.get(m.group(1))
        href = self.page_href(int(m.group(2)), d) if d else None
        if href is None:
            self.count("doc anchor", False)
            return m.group(0)
        return self.a(href, m.group(0), "x-loc x-cite", "doc anchor", f"p.{m.group(2)} §{m.group(3)}")

    def _loc_title(self, page: str, sec: str) -> str:
        return f"Page {page}, {self.doc.section_label(sec)}" if self.doc else f"p.{page} §{sec}"

    def _sec_title(self, sid: str) -> str:
        return self.doc.section_label(sid) if self.doc else f"§{sid}"

    def link_html(self, html: str, *, skip: tuple[str, ...] = ("a", "h1", "h2", "h3", "abbr")) -> str:
        """Every text run of ``html`` outside ``skip`` elements, linked; tags kept byte for byte."""
        parts = TAG_RE.split(html)
        depth = 0
        out = []
        for p in parts:
            if p.startswith("<"):
                m = re.match(r"<(/?)([a-zA-Z0-9]+)", p)
                if m and m.group(2).lower() in skip and not p.endswith("/>"):
                    depth += -1 if m.group(1) else 1
                out.append(p)
            elif p and depth == 0:
                out.append(self.link_text(p))
            else:
                out.append(p)
        return "".join(out)

    def resolve(self, html: str) -> str:
        """Placeholder passage hrefs to the ids of the marks the document text will carry."""
        segs = {d.prefix: d.segments() for d in self.docs}
        by = {d.prefix: d for d in self.docs}

        def sub(m: re.Match[str]) -> str:
            d = by[m.group(1)]
            return d.mark_id(segs[d.prefix], int(m.group(2)))
        return re.sub(f"{SENT}P([a-z0-9]+):(\\d+):(\\d+){SENT}", sub, html)


def _multi_sub(text: str, pats: list[tuple[re.Pattern[str], Any]]) -> str:
    """Apply several patterns in one left-to-right pass: at each place the earliest match wins (the first
    pattern on a tie), so no pattern sees another's output."""
    out: list[str] = []
    pos = 0
    while pos < len(text):
        best: tuple[int, int, re.Match[str], Any] | None = None
        for i, (rx, fn) in enumerate(pats):
            m = rx.search(text, pos)
            if m and m.end() > m.start() and (best is None or (m.start(), i) < (best[0], best[1])):
                best = (m.start(), i, m, fn)
        if best is None:
            break
        m, fn = best[2], best[3]
        out.append(text[pos:m.start()])
        out.append(fn(m))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def load_report(run_dir: Path) -> dict[str, Any]:
    try:
        r = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return r if isinstance(r, dict) else {}
