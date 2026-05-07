"""Pydantic request/response models for the public API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class HealthResponse(BaseModel):
    status: str
    seeded: bool
    n_patients: int
    db_path: str


class SchemaResponse(BaseModel):
    tables: dict[str, dict[str, Any]]
    notes: str


class ExampleQuestion(BaseModel):
    text: str
    intent: str
    description: str


class ExampleQuestionsResponse(BaseModel):
    examples: list[ExampleQuestion]


class QueryResponse(BaseModel):
    parsed_query: dict[str, Any]
    sql: str
    sql_params: list[Any]
    cohort_size: int
    demographics: dict[str, Any]
    clinical_summary: dict[str, Any]
    mutation_frequency: list[dict[str, Any]]
    expression_summary: list[dict[str, Any]]
    comparison: dict[str, Any] | None
    summary: dict[str, Any]
    provenance: dict[str, Any]
