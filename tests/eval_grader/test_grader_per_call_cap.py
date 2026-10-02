"""The grader's claude_code judge gets the grader's own per-call cap, not the matcher default."""

from pathlib import Path

from sit_eval.config import load_eval_config
from sit_eval.grader import cli as grader_cli


def test_grader_claude_code_judge_uses_grader_per_call_cap(tmp_path: Path, monkeypatch) -> None:
    seen: dict = {}

    def fake_build_judge(kind, *, out_dir, **options):
        seen.update(kind=kind, **options)
        return object()

    monkeypatch.setattr("sit_eval.judge.build_judge", fake_build_judge)
    grader_cli._judge("claude_code", tmp_path / "out")
    cfg = load_eval_config()
    assert seen["max_budget_usd_per_call"] == cfg.grader.max_budget_usd_per_call
    assert cfg.grader.max_budget_usd_per_call > cfg.judge.max_budget_usd_per_call


def test_grader_anthropic_judge_gets_no_cli_only_option(tmp_path: Path, monkeypatch) -> None:
    seen: dict = {}

    def fake_build_judge(kind, *, out_dir, **options):
        seen.update(options)
        return object()

    monkeypatch.setattr("sit_eval.judge.build_judge", fake_build_judge)
    grader_cli._judge("anthropic_api", tmp_path / "out")
    assert "max_budget_usd_per_call" not in seen
