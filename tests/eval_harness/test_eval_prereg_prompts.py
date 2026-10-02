"""Prereg freeze check, prompt lock, loaders and aggregate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from eval_builders import LIVE_RUN, PAYMENTS_KEY
from typer.testing import CliRunner

from sit_eval import prompts
from sit_eval.aggregate import aggregate
from sit_eval.cli import app
from sit_eval.loaders import LoadError, infer_doc_version, load_key, load_review
from sit_eval.prereg import PreregRefusal, enforce, prereg_status


def _prereg(tmp_path: Path, frozen: bool, lock: str | None) -> tuple[Path, Path]:
    p = tmp_path / "prereg.yaml"
    p.write_text(f"frozen: {'true' if frozen else 'false'}\nmatcher:\n  prompt_sha256: null\n")
    lk = tmp_path / "prereg.lock"
    if lock is not None:
        lk.write_text(lock)
    return p, lk


def test_freeze_check(tmp_path: Path):
    p, lk = _prereg(tmp_path, False, None)
    st = prereg_status(p, lk)
    assert st["label"] == "pilot_unfrozen" and "UNFROZEN" in st["message"]
    enforce(st, prompt_bundle_sha256="x", prompt_lock_problems=["drift"])        # unfrozen: never refuses
    p, lk = _prereg(tmp_path, True, None)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    st = prereg_status(p, lk)
    assert st["label"] == "refused" and not st["ok_to_score"]
    with pytest.raises(PreregRefusal):
        enforce(st, prompt_bundle_sha256="x", prompt_lock_problems=[])
    lk.write_text(f"{sha}  4278b5f9 (signed tag prereg-frozen)\n")
    st = prereg_status(p, lk)
    assert st["label"] == "frozen" and st["ok_to_score"]
    enforce(st, prompt_bundle_sha256="x", prompt_lock_problems=[])
    with pytest.raises(PreregRefusal, match="PROMPTS.lock"):
        enforce(st, prompt_bundle_sha256="x", prompt_lock_problems=["matcher_pair.md changed"])
    lk.write_text("0" * 64 + " abc\n")
    assert prereg_status(p, lk)["label"] == "refused"


def test_repository_prereg_is_read():
    st = prereg_status()
    assert st["exists"] and len(st["sha256"]) == 64
    if not st["frozen"]:
        assert st["label"] == "pilot_unfrozen"


def test_prompt_lock_matches_and_detects_drift(tmp_path: Path):
    assert prompts.check_lock() == [], "run `sit-eval prompts --write-lock` after editing a judge prompt"
    lock = json.loads(prompts.PROMPTS_LOCK.read_text())
    lock["files"]["prompts/matcher_pair.md"] = "0" * 64
    bad = tmp_path / "PROMPTS.lock"
    bad.write_text(json.dumps(lock))
    assert any("matcher_pair.md" in x for x in prompts.check_lock(bad))
    assert prompts.check_lock(tmp_path / "missing.lock")[0].startswith("missing.lock is missing")
    res = CliRunner().invoke(app, ["prompts"])
    assert res.exit_code == 0 and lock["bundle_sha256"] in res.output


def test_render_is_strict():
    with pytest.raises(KeyError, match="missing"):
        prompts.render("matcher_pair", FLAW="x")
    with pytest.raises(KeyError, match="unused"):
        prompts.render("matcher_pair", FLAW="x", FINDING="y", EXTRA="z")
    assert "$schema" not in prompts.judge_schema("pair")


def test_loaders():
    rin = load_review(LIVE_RUN)
    assert rin.manifest is not None and rin.under_review["doc_id"] == "DOC-design_v1"
    key = load_key(PAYMENTS_KEY)
    assert infer_doc_version(rin, key, None) == "v1"
    assert infer_doc_version(rin, key, "x/design_v2.pdf") == "v2"
    with pytest.raises(LoadError):
        load_review(LIVE_RUN / "nope")


def _fake_scores(cond: str, doc: str, run: str, recall: float, detected: list[bool]) -> dict:
    return {"kind": "sit_eval.scores", "status": "pilot_unfrozen", "exploratory": False,   # confirmatory (LC12)
            "inputs": {"item_id": doc, "doc_version": "v1", "run_id": run, "condition": cond},
            "metrics": {"recall": {"value": recall, "tp": int(recall * 14), "g": 14, "status": "primary",
                                   "reason": None},
                        "cdr": {"value": None, "reason": "x", "status": "key_secondary"}},
            "flaws": [{"flaw_id": f"F{i:02d}", "matched_finding_strict": "FND-001" if d else None}
                      for i, d in enumerate(detected, start=1)]}


def test_aggregate_and_compare(tmp_path: Path):
    paths = []
    for cond, base in (("FULL", 0.7), ("B0", 0.4)):
        for d, off in (("doc-a", 0.0), ("doc-b", 0.1), ("doc-c", -0.1)):
            for j in range(2):
                r = round(base + off + 0.05 * j, 3)
                det = [i < int(r * 14) for i in range(14)]
                p = tmp_path / f"{cond}-{d}-{j}.json"
                p.write_text(json.dumps(_fake_scores(cond, d, f"run{j}", r, det)))
                paths.append(p)
    res = aggregate(paths, metrics=["recall", "cdr"], compare=("FULL", "B0"), B=500)
    full = res["conditions"]["FULL"]
    assert full["recall"]["macro"] == pytest.approx(0.725) and full["recall"]["ci95"][0] <= 0.725
    assert full["cdr"]["macro"] is None and full["cdr"]["undefined_runs"] == 6
    cmp_ = res["comparison"]
    assert cmp_["recall"]["paired_bootstrap"]["point"] == pytest.approx(0.3)
    assert cmp_["recall"]["sign_flip"]["p_greater"] == pytest.approx(1 / 8)
    assert cmp_["flaw_level"]["mcnemar"]["c_b_only"] == 0 and cmp_["flaw_level"]["mcnemar"]["b_a_only"] > 0
    out = CliRunner().invoke(app, ["aggregate", *map(str, paths), "--compare", "FULL", "--compare", "B0",
                                   "--bootstrap-b", "200", "--out", str(tmp_path / "agg.json")])
    assert out.exit_code == 0, out.output
    assert json.loads((tmp_path / "agg.json").read_text())["comparison"]["a"] == "FULL"
