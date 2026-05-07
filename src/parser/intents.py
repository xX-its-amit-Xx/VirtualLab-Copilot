"""Pydantic data models describing a parsed natural-language query.

These types are the contract between the parser, the cohort engine, and
the API. They are intentionally JSON-serializable so they can be shown
in the UI as a 'query plan' and audited.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    """High-level intent of the user's question."""

    DESCRIBE_COHORT = "describe_cohort"
    COMPARE_GROUPS = "compare_groups"
    SURVIVAL_ANALYSIS = "survival_analysis"
    MUTATION_FREQUENCY = "mutation_frequency"
    EXPRESSION_ANALYSIS = "expression_analysis"


Operator = Literal["=", "!=", ">", ">=", "<", "<=", "in", "contains"]


class CohortFilter(BaseModel):
    """A single SQL-translatable predicate."""

    table: Literal["patients", "genomics", "transcriptomics", "clinical_labs"]
    column: str
    operator: Operator
    value: str | int | float | list[str] | list[int] | list[float]
    rationale: str = Field(
        default="",
        description="Free-text explanation of why this filter was extracted.",
    )


class Comparison(BaseModel):
    """Describes a two-group comparison (e.g. responders vs non-responders)."""

    column: str
    group_a: str
    group_b: str
    metric: Literal[
        "progression_free_survival_months",
        "overall_survival_months",
        "response_rate",
        "expression",
    ] = "progression_free_survival_months"


class ParsedQuery(BaseModel):
    """Structured representation of a natural-language research question."""

    raw_question: str
    intent: QueryIntent
    filters: list[CohortFilter] = Field(default_factory=list)
    comparison: Comparison | None = None
    target_gene: str | None = None
    notes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def to_sql(self) -> tuple[str, list]:
        """Compile the parsed filters into a SQL string + parameters.

        Returns SQL that selects ``patients.patient_id`` for every patient
        matching every filter. Genomics and transcriptomics filters are
        translated into EXISTS subqueries so a patient with at least one
        matching mutation/expression row qualifies.
        """
        params: list = []
        joins: list[str] = []
        wheres: list[str] = []

        for f in self.filters:
            if f.table == "patients":
                wheres.append(_render_predicate("p", f, params))
            elif f.table == "clinical_labs":
                if "JOIN clinical_labs c" not in " ".join(joins):
                    joins.append("LEFT JOIN clinical_labs c ON c.patient_id = p.patient_id")
                wheres.append(_render_predicate("c", f, params))
            elif f.table == "genomics":
                clause, sub_params = _render_exists("genomics", "g", f)
                wheres.append(clause)
                params.extend(sub_params)
            elif f.table == "transcriptomics":
                clause, sub_params = _render_exists("transcriptomics", "t", f)
                wheres.append(clause)
                params.extend(sub_params)

        sql = "SELECT p.patient_id FROM patients p"
        if joins:
            sql += " " + " ".join(joins)
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        return sql, params


# ---------------------------------------------------------------------------


def _render_predicate(alias: str, f: CohortFilter, params: list) -> str:
    """Render a single predicate against an aliased table."""
    col = f"{alias}.{f.column}"
    if f.operator == "in":
        values = list(f.value) if isinstance(f.value, list) else [f.value]
        placeholders = ",".join(["?"] * len(values))
        params.extend(values)
        return f"{col} IN ({placeholders})"
    if f.operator == "contains":
        params.append(f"%{f.value}%")
        return f"{col} LIKE ?"
    params.append(f.value)
    return f"{col} {f.operator} ?"


def _render_exists(table: str, alias: str, f: CohortFilter) -> tuple[str, list]:
    """Render an EXISTS subquery for one-to-many tables."""
    sub_params: list = []
    pred = _render_predicate(alias, f, sub_params)
    sql = (
        f"EXISTS (SELECT 1 FROM {table} {alias} "
        f"WHERE {alias}.patient_id = p.patient_id AND {pred})"
    )
    return sql, sub_params
