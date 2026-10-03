"""Guard: the scripted fakes serve every assess shard group the config gives (USER_DECISIONS #40).

The config went from four groups to six with only the config tests run; the synthetic fake held
answers for four shards, so the fifth raised ``KeyError: 5`` in about 17 test files. These tests
read the group count from the committed ``config/agent.yaml`` and assert that each fake has an
answer for every group, that each planted finding is dealt to exactly one shard whatever the
grouping (checked again on a one-criterion-per-group split), and that the expected merged IDs match
the configured shard order.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent / "robustness"))

from robustness_harness import build_script as robustness_script  # noqa: E402

import test_e2e_synthetic as synth  # noqa: E402
import test_merged_id_references as refs  # noqa: E402
from sit_review_agent.config import AssessShard, load_config  # noqa: E402
from sit_review_agent.llm.gateway import FakeResponse  # noqa: E402
from sit_review_agent.selftest import fixture_script, request_shard  # noqa: E402


def configured() -> list[AssessShard]:
    cfg = load_config()
    return list(cfg.agent.assess.shards_for(cfg.criteria.ids()))


def one_per_criterion() -> list[AssessShard]:
    """A different grouping: every criterion its own shard (eleven shards)."""
    return [AssessShard(name=c, criteria=[c]) for c in load_config().criteria.ids()]


class _Req:
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id


@pytest.mark.parametrize("grouping", [configured, one_per_criterion], ids=["configured", "one_per_criterion"])
def test_synthetic_fake_answers_every_shard_and_deals_each_finding_once(grouping: Any) -> None:
    shards = grouping()
    dealt = synth.shard_findings(shards)
    assert sorted(dealt) == list(range(1, len(shards) + 1))
    planted = [f["id"] for f in synth.assess_findings()]
    assert sorted(x for ids in dealt.values() for x in ids) == sorted(planted)
    script = synth.build_script(shards)
    assert len(script["assess"]) == len(shards)
    assert all(isinstance(r, FakeResponse) and "findings" in r.parsed for r in script["assess"])


def test_merged_ids_follow_the_configured_shard_order() -> None:
    """``MERGED_ID`` is shard order, then rank order within a shard, under the configured groups
    (the four-group and the six-group configs give the same order; a regrouping that changes it
    fails here first, naming the order to write into ``MERGED_ID``)."""
    dealt = synth.shard_findings(configured())
    order = [x for k in sorted(dealt) for x in dealt[k]]
    assert {x: f"FND-{n:03d}" for n, x in enumerate(order, 1)} == synth.MERGED_ID


def test_merged_id_fixture_answers_every_configured_shard() -> None:
    shards = configured()
    script = refs.build(shards)
    assert len(script["assess"]) == len(shards)
    names = [s.name for s in shards]
    answered = {s.name for s, r in zip(shards, script["assess"], strict=True) if r.parsed["findings"]}
    assert answered == set(refs.SHARDS) <= set(names)


def test_selftest_and_robustness_fixtures_answer_every_configured_shard() -> None:
    shards = configured()
    groups = [list(s.criteria) for s in shards]
    criteria = load_config().criteria.ids()
    for k, group in enumerate(groups, 1):
        assert request_shard(_Req(f"assess-0-s{k}"), groups) == group
        assert request_shard(_Req(f"assess-0-s{k}-r1"), groups) == group
    assert request_shard(_Req(f"assess-0-s{len(groups) + 1}"), groups) is None
    assert fixture_script(criteria, groups)["assess"]
    assert len(robustness_script(criteria, None, groups)["assess"]) >= 2 * len(groups)   # a retry each
