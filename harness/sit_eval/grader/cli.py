"""``sit-eval grade`` sub-commands. Owned by the grader workstream; mounted by ``sit_eval.cli``."""

import typer

app = typer.Typer(help="Lecturer grader (research/grading/grader_prompt.md).", no_args_is_help=True)
