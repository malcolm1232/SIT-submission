"""Leakage control LC12 in code (eval/prereg.yaml ``leakage_controls.after_runs_before_scoring``).

LC12: every key used for scoring has ``scored_run_ready = true``, i.e. the owner has signed it off
(eval/human_labelling_protocol.md T3/T6a, eval/KEY_SIGNOFF.md section 4). SIT FABLE ruling #26
(docs/USER_DECISIONS.md, 2026-10-03) turns it from a warning into a refusal:

* every command that reads an answer key to produce a score or a key-aware diagnostic (``sit-eval
  score``, ``sit-eval grade run --answer-key``) refuses a key that is not signed off, before any judge
  is built: non-zero exit, no model call, no cost;
* ``--exploratory`` overrides it; the run then marks every artefact it writes with ``exploratory: true``
  and :data:`EXPLORATORY_NOTE`;
* ``sit-eval aggregate`` refuses exploratory inputs (alone or mixed with confirmatory ones) unless it
  is given ``--exploratory`` too, and then marks its own output exploratory;
* ``sit-eval score`` refuses an exploratory ``--prior-scores`` (the v1 scores read by the v2 copy-through)
  unless it is given ``--exploratory`` too, so an exploratory score never feeds a confirmatory one;
* with a frozen prereg, an ``--exploratory`` run says it is outside the pre-registered analysis
  (:data:`OUTSIDE_PREREG_NOTE`); it can never be a confirmatory run.

The flag always marks: a run given ``--exploratory`` is exploratory even on a signed key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

FLAG = "--exploratory"
EXPLORATORY_NOTE = ("EXPLORATORY: this run was started with --exploratory (eval/prereg.yaml LC12 override); "
                    "these scores are exploratory and may not be reported as confirmatory")
OUTSIDE_PREREG_NOTE = ("OUTSIDE THE PRE-REGISTERED ANALYSIS: eval/prereg.yaml is frozen and this run was started "
                       "with --exploratory, so it is not part of the pre-registered analysis and may not be "
                       "reported as one")
LEGACY_KEY_REASON = "the legacy grader key format carries no sign-off, so it is never scored_run_ready"


class UnsignedKeyRefusal(RuntimeError):
    """LC12: a scoring run on an answer key that is not signed off, without ``--exploratory``."""


class ExploratoryInputRefusal(RuntimeError):
    """LC12: an aggregate over exploratory scores (alone or mixed with confirmatory ones) without
    ``--exploratory``."""


def key_signoff(key: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """``(scored_run_ready, pending)`` of a canonical key; anything else is not signed off."""
    status = (key or {}).get("authoring_status")
    if not isinstance(status, dict):
        return False, ["authoring_status"]
    return status.get("scored_run_ready") is True, [str(p) for p in status.get("pending") or []]


def refusal_message(key_path: str | Path, pending: list[str], *, reason: str | None = None,
                    alternative: str | None = None) -> str:
    """The message of a refused run: names the key, the missing sign-off and the override."""
    why = reason or ("scored_run_ready is false" + (f" (pending: {', '.join(pending)})" if pending else ""))
    msg = (f"answer key {key_path} is not signed off: {why}. eval/prereg.yaml LC12 allows a scored run only on a "
           "key the owner has signed off (eval/KEY_SIGNOFF.md section 4 sets scored_run_ready). No judge call was "
           f"made. Pass {FLAG} to run anyway: every artefact is then marked exploratory and may not be reported "
           "as confirmatory")
    return msg + (f"; {alternative}" if alternative else "")


def require_signed(key_path: str | Path, ready: bool, pending: list[str], *, exploratory: bool,
                   reason: str | None = None, alternative: str | None = None) -> None:
    """Raise :class:`UnsignedKeyRefusal` unless the key is signed off or the run is exploratory."""
    if not ready and not exploratory:
        raise UnsignedKeyRefusal(refusal_message(key_path, pending, reason=reason, alternative=alternative))


def notes(exploratory: bool, *, prereg_frozen: bool) -> list[str]:
    """Human-readable lines an exploratory run puts in every artefact (empty for a confirmatory run)."""
    if not exploratory:
        return []
    return [EXPLORATORY_NOTE] + ([OUTSIDE_PREREG_NOTE] if prereg_frozen else [])


def marker(exploratory: bool, *, prereg_frozen: bool) -> dict[str, Any]:
    """The machine-readable marker fields of an artefact: ``exploratory``, ``exploratory_note`` (``None``
    for a confirmatory run) and ``outside_preregistered_analysis``."""
    lines = notes(exploratory, prereg_frozen=prereg_frozen)
    return {"exploratory": bool(exploratory), "exploratory_note": ". ".join(lines) if lines else None,
            "outside_preregistered_analysis": bool(exploratory and prereg_frozen)}


def scores_are_exploratory(scores: dict[str, Any]) -> bool:
    """Whether a ``scores.json`` is exploratory. A file written before the guard has no marker; it is
    exploratory when its key was not signed off (LC12 would have refused it)."""
    if "exploratory" in scores:
        return scores["exploratory"] is True
    return (scores.get("inputs") or {}).get("scored_run_ready") is not True


def describe_exploratory(path: str, scores: dict[str, Any]) -> str:
    """``path``, plus why a file without a marker counts as exploratory."""
    return path if "exploratory" in scores else f"{path} (predates the LC12 guard; its key was not signed off)"


def require_confirmatory_prior(prior_path: str | Path | None, prior: dict[str, Any] | None, *,
                               exploratory: bool) -> None:
    """Raise :class:`ExploratoryInputRefusal` when a confirmatory ``sit-eval score`` is given an exploratory
    ``--prior-scores`` (the v1 scores its v2 copy-through reads): an exploratory score never feeds a
    confirmatory one (hub verification, session 4)."""
    if exploratory or prior is None or not scores_are_exploratory(prior):
        return
    raise ExploratoryInputRefusal(
        f"--prior-scores {describe_exploratory(str(prior_path or 'scores'), prior)} is exploratory, and "
        "eval/prereg.yaml LC12 lets no exploratory score feed a confirmatory run. No judge call was made. Pass "
        f"{FLAG} to run anyway: every artefact is then marked exploratory and may not be reported as confirmatory")


def require_confirmatory_inputs(exploratory_inputs: list[str], n_inputs: int, *, exploratory: bool) -> None:
    """Raise :class:`ExploratoryInputRefusal` when exploratory inputs reach a run without ``--exploratory``."""
    if exploratory or not exploratory_inputs:
        return
    listed = "; ".join(exploratory_inputs)
    if len(exploratory_inputs) < n_inputs:
        head = (f"the inputs mix exploratory and confirmatory scores ({len(exploratory_inputs)} of {n_inputs} "
                f"exploratory: {listed})")
    else:
        head = f"every input is exploratory, so no confirmatory analysis can be made from them ({listed})"
    raise ExploratoryInputRefusal(
        f"{head}. eval/prereg.yaml LC12: a score on a key that is not signed off is exploratory and never enters a "
        f"confirmatory analysis. Pass {FLAG} to aggregate anyway: the output is then marked exploratory and may not "
        "be reported as confirmatory")
