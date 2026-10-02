"""``scripts/leakage_grep.py`` (robustness OVF-07; prereg LC8 and the static half of LC10):
mechanics on invented sources and files, the eval/blind refusal, and that the agent never imports
it. The repository-wide gate itself runs as the OVF-07 case of the robustness suite."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from sit_review_agent.paths import repo_root

SCRIPT = repo_root() / "scripts" / "leakage_grep.py"


@pytest.fixture(scope="module")
def lg() -> ModuleType:
    spec = importlib.util.spec_from_file_location("leakage_grep_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


KEY = ("The Quillmoor Gateway forwards the full card number to the fraud vendor QMV-7, contradicting "
       "section 12.2. Quillmoor Gateway handles settlement through the Brackwater ledger and the Quillmoor "
       "Gateway retries within 250 ms. The `settle_batch_id` column is never indexed. Brackwater ledger "
       "entries are reconciled nightly by the Brackwater ledger job.")
OTHER = ("The clinic scheduler sends reminders through the regional messaging hub and stores consent in the "
         "patient registry; the regional messaging hub retries twice and the patient registry keeps history.")


def _files(tmp: Path, agent_text: str) -> dict[str, tuple[tuple[str, ...], bool]]:
    (tmp / "agent").mkdir()
    (tmp / "agent" / "code.py").write_text(agent_text, encoding="utf-8")
    (tmp / "fixtures").mkdir()
    (tmp / "fixtures" / "f.json").write_text('{"note": "the Quillmoor Gateway sample"}', encoding="utf-8")
    return {"agent": ((str(tmp / "agent" / "**" / "*"),), True), "fixtures": ((str(tmp / "fixtures" / "*"),), False)}


def test_planted_terms_are_found_in_gated_areas_only(lg: ModuleType, tmp_path: Path) -> None:
    sources = [lg.Source("eval/synthetic/item_a/key.json", KEY), lg.Source("eval/synthetic/item_b/doc.md", OTHER)]
    terms = lg.extract_terms(sources)
    kinds = {t.text: t.kind for t in terms.values()}
    assert kinds.get("brackwater ledger") == "tfidf" and kinds.get("QMV-7") == "id"
    assert kinds.get("settle_batch_id") == "name" and kinds.get("Quillmoor") == "proper"
    areas = _files(tmp_path, "# routes payments via the Quillmoor gateway (QMV-7)\n")
    res = lg.run(sources, terms, areas=areas, defaults=False)
    assert not res["passed"]
    assert {h["term"] for h in res["unresolved"]} >= {"QMV-7", "Quillmoor"}
    assert all(h["area"] == "agent" for h in res["unresolved"])            # fixtures are reported, not gated
    assert any(h["area"] == "fixtures" for h in res["hits"])
    strict = lg.run(sources, terms, areas=areas, defaults=False, strict=True)
    assert any(h["area"] == "fixtures" for h in strict["unresolved"])


def test_allow_list_resolves_and_clean_code_passes(lg: ModuleType, tmp_path: Path) -> None:
    sources = [lg.Source("eval/synthetic/item_a/key.json", KEY), lg.Source("eval/synthetic/item_b/doc.md", OTHER)]
    terms = lg.extract_terms(sources)
    areas = _files(tmp_path, "# a generic review tool: plan, research, assess, verify, report\n")
    assert lg.run(sources, terms, areas=areas, defaults=False)["passed"]
    (tmp_path / "agent" / "code.py").write_text("x = 'Quillmoor'\n", encoding="utf-8")
    res = lg.run(sources, terms, areas=areas, defaults=False, allow={"quillmoor": "test"})
    assert res["passed"] and res["hits"][0]["resolved"] == "test"


def test_thirteen_word_overlap_is_a_hit(lg: ModuleType, tmp_path: Path) -> None:
    sources = [lg.Source("eval/synthetic/item_a/key.json", KEY)]
    copied = " ".join(KEY.split()[:16])
    areas = _files(tmp_path, f"PROMPT = '''{copied}'''\n")
    res = lg.run(sources, {}, areas=areas, defaults=False)
    assert not res["passed"] and res["overlap_failures"][0]["max_overlap_words"] >= 13


def test_known_sample_hosts_and_blind_refusal(lg: ModuleType, tmp_path: Path) -> None:
    terms = lg.extract_terms([])
    assert {"github.com/pgvector", "pgvector.dev", "kafka.apache.org"} <= set(terms)
    with pytest.raises(lg.UsageError, match="eval/blind"):
        lg.load_sources(["eval/blind/item/answer_key.json"], [], [])   # refused before any read
    assert lg.main(["--keys", "eval/blind/x.json", "--docs", ""]) == 2


def test_cli_passes_on_the_repository_and_is_never_imported_by_the_agent() -> None:
    res = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=repo_root(), timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PASS" in res.stdout
    pkg = repo_root() / "agent" / "sit_review_agent"
    assert not [p for p in pkg.rglob("*.py") if "leakage_grep" in p.read_text(encoding="utf-8")]
