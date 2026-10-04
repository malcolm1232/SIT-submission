# No early end for a call with tools, 4 Oct 2026

Worker note for branch `s4/repeat-off-with-tools`, based on `cf71546`.
Covered by Malcolm's word of 3 Oct 2026 22:55 ("fix what u need to fix") under his delegation of 3 Oct 02:50.

## What changed

- `agent/sit_review_agent/llm/claude_code.py` `_stream_parser`: `stop_on_repeat=self._runner_streams` became `stop_on_repeat=self._runner_streams and not request.tools`, with a one-line comment.
  Research is the only conversation with `request.tools` set and the only one that resumes across calls.
  Ended at its first accepted envelope, its next call would resume a session whose transcript ends with the CLI's rejection of that very envelope, followed by the gateway's user turn with the tool results; the model could re-issue the calls.
  So a call with tools keeps the CLI's own flow and ends on the result event.
  The double emission was measured on assess shards, which have no tools, so nothing measured is lost.
- The module docstring's "First complete answer" paragraph gains two lines stating the exception.
- `tests/test_stream_gateway.py`:
  - `test_a_repeated_tool_call_envelope_ends_at_the_first` is replaced by `test_a_repeated_tool_call_envelope_is_not_ended_early`: a tools request whose stream repeats an envelope gets every line through the result event, the CLI's answer (the second envelope), 3 turns, no `ended_at_first_answer`, the result event's usage.
  - New `test_a_single_tool_call_envelope_ends_with_the_result_event`: one accepted envelope with tools ends normally on the result event (the gap noted before).
  - `test_a_repeated_answer_ends_the_call_at_the_first` (no tools) is unchanged and still kills at the second `message_start`.
- Mutation: with the rule removed, `test_a_repeated_tool_call_envelope_is_not_ended_early` fails (`assert 9 == 18`, the call killed at the repeat); restored from a `cp` backup, `cmp` identical.

## Known leftovers, not fixed here (for the planner's record)

1. The usage estimate of a call ended at the stage limit during a repeat counts only the copy being written, so it reads low.
2. The assess-phase test in `tests/test_llm_phases.py` covers the disclosure, not the stream.
