# Offline checks for the design-review agent and its evaluation harness. No key, no network (ADR-008).
#
#   make smoke   under a minute: the end-to-end selftest plus the config, prompt-lock, CLI and leakage checks.
#                Run it on a fresh clone and after every live change (docs/DEMO_DAY_RUNBOOK.md §1 and §4,
#                robustness DEMO-13).
#   make test    ruff and the whole offline test suite (about a minute).
#
# The interpreter is the repository's virtualenv when it exists, else python3 on PATH. To use another one:
#   make smoke PYTHON=/path/to/python
# First-time setup: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

VENV ?= .venv
PYTHON ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

# The tests a live change can break: config files and their pinned lines, profiles, the prompt lock, the spec
# models, stop rules and the orchestrator, the CLI (run, --k, --profile, coverage, selftest) and the leakage gate.
SMOKE_TESTS = tests/test_config.py tests/test_config_layout.py tests/test_config_profiles.py tests/test_prompts.py \
              tests/test_models.py tests/test_orchestrator.py tests/test_selftest_cli.py tests/test_cli_kruns.py \
              tests/test_cli_coverage.py tests/test_runtime_leakage.py tests/test_not_assessed_verdict.py \
              tests/test_skeleton_imports.py

.PHONY: help smoke test lint check-env

help:
	@echo "make smoke   offline check in under a minute (selftest + config, prompt-lock, CLI and leakage tests)"
	@echo "make test    ruff + the whole offline test suite"
	@echo "interpreter: $(PYTHON)  (override with PYTHON=...)"

check-env:
	@$(PYTHON) -c "import sit_review_agent, sit_eval, pytest" 2>/dev/null || { \
	  echo "error: $(PYTHON) cannot import the project or pytest."; \
	  echo "       Set it up once: python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\""; exit 2; }

smoke: check-env
	$(PYTHON) -m sit_review_agent selftest
	$(PYTHON) -m pytest -q $(SMOKE_TESTS)

lint: check-env
	$(PYTHON) -m ruff check agent harness tests

test: lint
	$(PYTHON) -m pytest -q
