"""Lecturer grader (research/grading/grader_prompt.md). Owned by the grader workstream.

``grade_review`` grades one structured Review against the canonical page text of its document:
Pass A (finding level, shuffled), harness verification, Pass B (holistic), aggregation in code
(GR §4, prereg ``grader``), optional key-aware diagnostic. ``run_meta_validation`` runs GR §8.
"""

from sit_eval.grader.costs import Budget, BudgetExceeded
from sit_eval.grader.pipeline import GraderError, GradeResult, grade_review, grade_review_async, plan_grade
from sit_eval.grader.projection import GraderInputError, project_review
from sit_eval.grader.validation import run_meta_validation, run_meta_validation_async

__all__ = ["Budget", "BudgetExceeded", "GradeResult", "GraderError", "GraderInputError", "grade_review",
           "grade_review_async", "plan_grade", "project_review", "run_meta_validation", "run_meta_validation_async"]
