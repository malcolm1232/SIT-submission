"""Inputs of one scoring run: the Review, the canonical answer key and the document text.

* The Review is validated twice: by the agent's own Pydantic model
  (:class:`sit_review_agent.models.Review`) and by ``spec/finding.schema.json#/$defs/Review``.
* The key is validated against ``spec/answer_key.schema.json`` (with the finding schema registered
  for its ``$ref``\\ s).
* The document text is the canonical page-marked text produced by the agent's own ingest
  (``sit_review_agent.ingest.ingest``, pdfplumber; prereg ``grounding.text``), so grounding reads the
  same text as the agent's verify stage. Its SHA-256 is checked against the Review's
  ``metadata.documents[].sha256_text``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from sit_eval.paths import answer_key_schema_path, finding_schema_path
from sit_eval.usage import UsageCompleteness, usage_completeness
from sit_review_agent.ingest import Document, ingest
from sit_review_agent.invariants import spec_validator
from sit_review_agent.models import Review

FINDING_SCHEMA_ID = "https://sit-design-review.invalid/spec/finding.schema.json"
KEY_SCHEMA_ID = "https://sit-design-review.invalid/spec/answer_key.schema.json"


class LoadError(ValueError):
    """An input file is missing or invalid."""


@dataclass
class ReviewInput:
    data: dict[str, Any]                 # report.json as loaded (validated)
    review: Review
    report_path: Path
    run_dir: Path | None                 # directory holding report.json, if it looks like a run dir
    manifest: dict[str, Any] | None      # manifest.json next to report.json, if present
    usage: UsageCompleteness | None = None   # whether every billed model call's usage was recorded (sit_eval.usage)

    @property
    def under_review(self) -> dict[str, Any]:
        docs = self.data["metadata"]["documents"]
        return next((d for d in docs if d.get("role") == "under_review"), docs[0])


@dataclass
class DocInput:
    document: Document
    source: str                          # where the text came from
    sha256_text: str
    sha256_matches_review: bool | None   # None when the Review records no hash for this doc
    warnings: list[str] = field(default_factory=list)


def _schema_errors(validator: Draft202012Validator, data: Any, limit: int = 5) -> list[str]:
    errs = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in errs[:limit]]


def load_review(path: str | Path) -> ReviewInput:
    """``path`` is a run directory (holding ``report.json``) or a ``report.json`` file."""
    p = Path(path)
    report = p / "report.json" if p.is_dir() else p
    if not report.exists():
        raise LoadError(f"no report.json at {p}")
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise LoadError(f"{report}: not JSON ({exc})") from exc
    errs = _schema_errors(spec_validator("Review"), data)
    if errs:
        raise LoadError(f"{report}: not a valid Review (spec/finding.schema.json): " + "; ".join(errs))
    try:
        review = Review.model_validate(data)
    except ValidationError as exc:
        raise LoadError(f"{report}: rejected by sit_review_agent.models.Review: {str(exc)[:500]}") from exc
    manifest_path = report.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    # usage completeness: the manifest field, else the legacy rule over llm.jsonl beside the report, else unknown
    usage = usage_completeness(manifest if manifest is not None else data.get("run_manifest"), report.parent)
    return ReviewInput(data=data, review=review, report_path=report, run_dir=report.parent, manifest=manifest,
                       usage=usage)


@lru_cache(maxsize=1)
def key_validator() -> Draft202012Validator:
    finding = json.loads(finding_schema_path().read_text(encoding="utf-8"))
    key = json.loads(answer_key_schema_path().read_text(encoding="utf-8"))
    registry = Registry().with_resources([(FINDING_SCHEMA_ID, Resource.from_contents(finding)),
                                          (KEY_SCHEMA_ID, Resource.from_contents(key))])
    return Draft202012Validator(key, registry=registry)


def load_key(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise LoadError(f"no answer key at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    errs = _schema_errors(key_validator(), data)
    if errs:
        raise LoadError(f"{p}: not a valid canonical answer key (spec/answer_key.schema.json): " + "; ".join(errs))
    return data


def infer_doc_version(rin: ReviewInput, key: dict[str, Any], doc_path: str | Path | None) -> str:
    """``v2`` for a delta review or when the document's file stem is the key's v2 document stem;
    else ``v1``."""
    if rin.data["metadata"].get("review_mode") == "delta":
        return "v2"
    v2 = (key.get("item", {}).get("documents") or {}).get("v2")
    if doc_path is not None and v2 and Path(doc_path).stem == Path(v2["path"]).stem:
        return "v2"
    return "v1"


def load_document(rin: ReviewInput, *, key: dict[str, Any] | None = None, key_path: str | Path | None = None,
                  doc: str | Path | None = None, version: str = "v1") -> DocInput:
    """Canonical text of the document under review.

    Resolution order: ``doc`` (a PDF, ingested with the agent's own ``ingest``, or a page-marked
    ``.pages.txt``); the run's ``text_path``; the PDF next to the key (the key's
    ``item.documents.<version>.path`` with suffix ``.pdf``).
    """
    meta = rin.under_review
    doc_id = meta["doc_id"]
    candidates: list[Path] = []
    if doc is not None:
        candidates.append(Path(doc))
    else:
        if rin.run_dir is not None and meta.get("text_path"):
            candidates.append(rin.run_dir / meta["text_path"])
        if key is not None and key_path is not None:
            ref = (key.get("item", {}).get("documents") or {}).get(version)
            if ref:
                candidates.append((Path(key_path).parent / ref["path"]).with_suffix(".pdf"))
    for c in candidates:
        if not c.exists():
            if doc is not None:
                raise LoadError(f"document {c} does not exist")
            continue
        if c.suffix.lower() == ".pdf":
            d = ingest(c, doc_id=doc_id)
            source = f"pdf:{c} (sit_review_agent.ingest.ingest, pdfplumber)"
        else:
            d = Document.from_page_marked_text(c.read_text(encoding="utf-8"), doc_id=doc_id)
            source = f"text:{c}"
        want = meta.get("sha256_text")
        same = None if not want else (want == d.sha256_text)
        warnings = [] if same is not False else [
            f"canonical text sha256 {d.sha256_text[:12]} differs from the Review's {want[:12]}: grounding "
            "reads different text from the agent's verify stage"]
        return DocInput(document=d, source=source, sha256_text=d.sha256_text, sha256_matches_review=same,
                        warnings=warnings)
    raise LoadError("cannot find the document text: pass --doc (the PDF or a .pages.txt file)")
