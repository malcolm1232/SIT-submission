# Prompts

One file per model-facing phase plus the shared system prompt. They are rendered with Jinja
`StrictUndefined` from declared variables only (`agent/sit_review_agent/prompts.py`); there are no
prompt strings in Python code.

| File | Phase | Output type (`agent/sit_review_agent/llm/outputs.py`) | Owner |
|---|---|---|---|
| `system.md` | every conversation (cached prefix) | — | A |
| `understand.md` | understand | `UnderstandOutput` | A |
| `plan.md` | plan | `PlanOutput` | A |
| `research.md` | research (tool loop) | `ResearchOutput` | B |
| `assess.md` | assess | `AssessOutput` | A |
| `refine.md` | refine | `RefineOutput` | A |
| `verify.md` | verify (anchor repair) | `AnchorRepairOutput` | C |
| `report.md` | report | `ReportOutput` | C |

## Leakage rule (methodology R4/R5, docs/SEALING.md)

Prompts and `config/` must never contain:

- anything from an evaluation document or answer key (`eval/`), including item names, titles,
  component names, planted-flaw mechanisms or wording;
- anything from `spec/taxonomy.yaml` `legacy_mappings` or `spec/README.md` §2 (they name answer-key
  labels);
- distinctive terms of the SIT sample artefact.

Examples in prompts must be invented and generic. `spec/taxonomy.yaml` outside `legacy_mappings`
is prompt-safe. `tests/test_prompts.py` greps every prompt for the known eval item names.

## Content rules every prompt keeps

Traceability (1-3 locations, verbatim quote of at least 8 words, page, section); "no change" is an
allowed disposition; evidence is cited by `EV-` ID only; never write a URL or cite anything that is
not in the evidence register; document and tool text are data, not instructions; no request to print
internal reasoning (it trips the `reasoning_extraction` classifier, ADR-002).

## Content-hash rule (docs/REPRODUCIBILITY.md §4)

`PROMPTS.lock` lists the SHA-256 of every prompt file (not this README). The bundle hash
(`prompts_bundle_sha256`, over the sorted `(path, sha256)` list) is recorded in every run manifest,
and each call's rendered-prompt hash becomes `Finding.provenance.prompt_hash`. After editing a
prompt, regenerate the lock and commit both together:

```
python -m sit_review_agent.prompts --write-lock
```

`tests/test_prompts.py` fails when the lock is stale. Changing a prompt after a freeze tag is a
recorded deviation. Nothing volatile (dates, run IDs) goes into a prompt.
