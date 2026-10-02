"""``sit-eval`` command line. Owned by the matcher workstream."""

import typer

from sit_eval.grader.cli import app as grade_app

app = typer.Typer(help="SIT evaluation harness.", no_args_is_help=True)
app.add_typer(grade_app, name="grade")


def main() -> None:
    app()
