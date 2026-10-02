"""``llm.partial``: the finished items of a structured answer that is still streaming (latency W1).

Synthetic JSON text fed in every chunking; the recorded CLI streams are in ``test_stream_fixtures.py``.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from sit_review_agent.llm.gateway import Usage
from sit_review_agent.llm.partial import (
    JSON_CHARS_PER_TOKEN,
    JsonItemScanner,
    StreamParser,
    parse_cli_stdout,
)


def finding(i: int) -> dict[str, Any]:
    """A finding whose strings hold every character that could fool a naive scanner."""
    return {"id": f"FND-{i:03d}", "rank": i, "severity": "high", "title": f"Finding {i} with {{braces}} and [brackets]",
            "statement": 'a "quoted" word, a comma, a colon: and a backslash \\ and \\"escaped\\" text',
            "evidence": [{"evidence_id": "E-1", "quote": "]}"}], "tags": ["x", "y"], "confidence": 0.75,
            "note": 'an escaped quote before structure: ", [x]} {"k": 1}, and a trailing backslash \\',
            "recommendation": None, "acknowledged_in_doc": False}


def answer(n: int) -> str:
    return json.dumps({"findings": [finding(i) for i in range(1, n + 1)], "sound_areas": [], "coverage": "ok"},
                      ensure_ascii=False)


@pytest.mark.parametrize("chunk", [1, 3, 17, 10_000])
def test_items_finish_exactly_when_their_json_closes(chunk: int) -> None:
    text = answer(6)
    seen: list[tuple[str, int, Any]] = []
    sc = JsonItemScanner(on_item=lambda k, i, v: seen.append((k, i, v)))
    for k in range(0, len(text), chunk):
        sc.feed(text[k:k + chunk])
    assert [s[1] for s in seen] == [0, 1, 2, 3, 4, 5] and all(s[0] == "findings" for s in seen)
    assert [s[2] for s in seen] == [finding(i) for i in range(1, 7)]
    assert sc.closed and sc.snapshot() == json.loads(text)
    assert sc.item_count() == 6


def test_a_cut_after_three_of_six_findings_salvages_three() -> None:
    text = answer(6)
    full = json.loads(text)
    fourth_end = text.index('"FND-004"')                 # cut inside the fourth finding
    sc = JsonItemScanner()
    sc.feed(text[:fourth_end + 30])
    snap = sc.snapshot()
    assert snap == {"findings": full["findings"][:3]}
    assert sc.item_count() == 3 and not sc.closed


def test_an_item_counts_only_once_its_closing_bracket_streamed() -> None:
    text = answer(2)
    end_of_first = text.index('"FND-002"')
    close = text.rindex("}", 0, end_of_first)            # the first finding's closing brace
    sc = JsonItemScanner()
    sc.feed(text[:close])
    assert sc.snapshot() is None
    sc.feed(text[close:close + 1])
    assert sc.item_count() == 1


def test_root_scalars_count_when_closed_and_scalars_in_lists() -> None:
    sc = JsonItemScanner()
    sc.feed('{"version": "v1", "n": 12, "ids": ["a", 2, true, null, {"k": [1]}], "flag": fal')
    assert sc.snapshot() == {"version": "v1", "n": 12, "ids": ["a", 2, True, None, {"k": [1]}]}
    sc.feed("se}")
    assert sc.snapshot() == {"version": "v1", "n": 12, "ids": ["a", 2, True, None, {"k": [1]}], "flag": False}
    open_list = JsonItemScanner()
    open_list.feed('{"ids": [1, 22, 33')
    assert open_list.snapshot() == {"ids": [1, 22]}            # 33 may still grow: not finished


def test_nested_lists_are_not_root_items() -> None:
    sc = JsonItemScanner()
    seen: list[int] = []
    sc.on_item = lambda k, i, v: seen.append(i)
    sc.feed('{"findings": [{"evidence": [{"a": 1}, {"a": 2}], "tags": ["t"]}, {"evidence": [')
    assert seen == [0] and sc.item_count() == 1


def test_the_envelope_salvages_the_final_answer() -> None:
    env = {"tool_calls": [{"id": "call-0001", "name": "s", "input": {"findings": [1]}}],
           "final": {"findings": [finding(1), finding(2)], "summary": "x"}}
    text = json.dumps(env)
    cut = text.index('"FND-002"')
    sc = JsonItemScanner(root=("final",))
    sc.feed(text[:cut])
    assert sc.snapshot() == {"findings": [finding(1)]}
    sc.feed(text[cut:])
    assert sc.snapshot() == env["final"]


def test_unicode_and_escapes_survive_any_split() -> None:
    item = {"title": "caf\u00e9 \u2014 \U0001f600 \\u0041 tab\there", "q": "\\\\"}
    text = json.dumps({"findings": [item, item]}, ensure_ascii=True)
    for cut in range(1, len(text)):
        sc = JsonItemScanner()
        sc.feed(text[:cut])
        sc.feed(text[cut:])
        assert sc.snapshot() == {"findings": [item, item]}, cut


# ------------------------------------------------------------------------------ the event stream


def ev(inner: dict[str, Any]) -> str:
    return json.dumps({"type": "stream_event", "event": inner, "session_id": "S", "uuid": "U"})


def stream_lines(answer_text: str, *, cut_at: int | None = None, thinking: int = 900) -> list[str]:
    body = answer_text if cut_at is None else answer_text[:cut_at]
    lines = [json.dumps({"type": "system", "subtype": "init", "model": "m"}),
             ev({"type": "message_start", "message": {"usage": {"input_tokens": 1137, "cache_read_input_tokens": 40,
                                                               "cache_creation_input_tokens": 7, "output_tokens": 5}}}),
             ev({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}}),
             json.dumps({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": thinking // 2}),
             json.dumps({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": thinking}),
             ev({"type": "content_block_stop", "index": 0}),
             ev({"type": "content_block_start", "index": 1,
                 "content_block": {"type": "tool_use", "name": "StructuredOutput", "input": {}}})]
    lines += [ev({"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta",
                                                                        "partial_json": body[k:k + 40]}})
              for k in range(0, len(body), 40)]
    if cut_at is None:
        lines += [ev({"type": "content_block_stop", "index": 1}),
                  json.dumps({"type": "result", "subtype": "success", "is_error": False,
                              "structured_output": json.loads(answer_text), "usage": {"input_tokens": 1137}})]
    return lines


def test_stream_parser_reads_usage_thinking_answer_and_result() -> None:
    text = answer(3)
    items: list[int] = []
    p = StreamParser(on_item=lambda k, i, v: items.append(i))
    p.feed_text("\n".join(stream_lines(text)) + "\n")
    assert items == [0, 1, 2]
    assert p.result is not None and p.result["structured_output"] == json.loads(text)
    assert p.message_usage is not None and p.message_usage["input_tokens"] == 1137
    assert p.thinking_tokens == 900 and p.answer_chars == len(text) and p.started


def test_cut_stream_estimate_is_input_plus_thinking_plus_streamed_chars() -> None:
    text = answer(6)
    cut = text.index('"FND-004"') + 10
    p = StreamParser()
    for line in stream_lines(text, cut_at=cut):
        p.feed_line(line)
    assert p.result is None and p.item_count() == 3
    est = p.estimated_usage()
    assert est == Usage(1137, 900 + math.ceil(cut / JSON_CHARS_PER_TOKEN), 7, 40)
    assert p.estimate_basis() == {"thinking_tokens": 900, "streamed_chars": cut,
                                  "chars_per_token": JSON_CHARS_PER_TOKEN}


def test_no_estimate_before_the_api_message_started() -> None:
    p = StreamParser()
    p.feed_line(json.dumps({"type": "system", "subtype": "init"}))
    assert p.estimated_usage() is None and not p.started and p.partial() is None


def test_chunked_stdout_and_a_last_line_without_newline() -> None:
    raw = "\n".join(stream_lines(answer(2)))            # no trailing newline
    p = StreamParser()
    for k in range(0, len(raw), 7):
        p.feed_text(raw[k:k + 7])
    assert p.result is None                            # the result line has not ended yet
    p.flush()
    assert p.result is not None and p.item_count() == 2


def test_only_the_structured_output_block_is_the_answer_and_a_new_one_restarts() -> None:
    p = StreamParser()
    p.feed_line(ev({"type": "content_block_start", "index": 2,
                    "content_block": {"type": "tool_use", "name": "OtherTool", "input": {}}}))
    p.feed_line(ev({"type": "content_block_delta", "index": 2,
                    "delta": {"type": "input_json_delta", "partial_json": '{"findings": [1, 2, '}}))
    assert p.answer_chars == 0
    for i, part in ((3, '{"findings": [{"a": 1}, '), (5, '{"findings": [{"b": 2}, ')):
        p.feed_line(ev({"type": "content_block_start", "index": i,
                        "content_block": {"type": "tool_use", "name": "StructuredOutput", "input": {}}}))
        p.feed_line(ev({"type": "content_block_delta", "index": i,
                        "delta": {"type": "input_json_delta", "partial_json": part}}))
    assert p.partial() == {"findings": [{"b": 2}]}      # the re-asked answer, not a mix of both


def test_noise_lines_are_counted_not_fatal() -> None:
    p = StreamParser()
    p.feed_text("warning: something\n[1, 2]\n\n" + json.dumps({"type": "result", "is_error": False}) + "\n")
    assert p.non_json_lines == 2 and p.result == {"type": "result", "is_error": False}


def test_parse_cli_stdout_reads_a_stream_or_a_single_json_object() -> None:
    out, _ = parse_cli_stdout("\n".join(stream_lines(answer(1))) + "\n")
    assert out is not None and out["type"] == "result"
    legacy = json.dumps({"type": "result", "structured_output": {"text": "x"}, "is_error": False})
    out2, _ = parse_cli_stdout(legacy)
    assert out2 is not None and out2["structured_output"] == {"text": "x"}
    untyped = json.dumps({"structured_output": {"text": "y"}})
    out3, _ = parse_cli_stdout(untyped)
    assert out3 == {"structured_output": {"text": "y"}}
    assert parse_cli_stdout("Segmentation fault")[0] is None
    assert parse_cli_stdout("")[0] is None
