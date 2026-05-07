"""FastAPI application factory and route definitions."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..analysis import CohortService, generate_summary
from ..config import get_settings
from ..database import Database, ensure_database
from ..database.schema import TABLE_DESCRIPTIONS
from ..parser import parse_query
from .schemas import (
    ExampleQuestion,
    ExampleQuestionsResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
)

logger = logging.getLogger("virtuallab.api")


EXAMPLE_QUESTIONS: list[ExampleQuestion] = [
    ExampleQuestion(
        text="Show patients with ISS stage III treated with proteasome inhibitors",
        intent="describe_cohort",
        description="Filter by ISS stage and therapy class.",
    ),
    ExampleQuestion(
        text="Compare PFS for responders vs non-responders",
        intent="compare_groups",
        description="Two-group survival comparison on PFS.",
    ),
    ExampleQuestion(
        text="Find patients with TP53 mutations and high beta-2 microglobulin",
        intent="describe_cohort",
        description="Genomic + clinical-lab combined filter.",
    ),
    ExampleQuestion(
        text="Show MYC expression in patients on anti-CD38 therapy",
        intent="expression_analysis",
        description="Transcriptomics view scoped by therapy class.",
    ),
    ExampleQuestion(
        text="What are the most common mutations in older patients (over 70)?",
        intent="mutation_frequency",
        description="Demographic-scoped mutation prevalence.",
    ),
    ExampleQuestion(
        text="Compare survival between stage I and stage III myeloma",
        intent="compare_groups",
        description="Stage-stratified Kaplan-Meier mockup.",
    ),
]


# ---------------------------------------------------------------------------


def _build_schema_response(db: Database) -> SchemaResponse:
    tables: dict[str, dict[str, Any]] = {}
    with db.connect() as conn:
        cur = conn.cursor()
        for name in TABLE_DESCRIPTIONS:
            cur.execute(f"PRAGMA table_info({name})")
            cols = [
                {"name": row["name"], "type": row["type"], "notnull": bool(row["notnull"])}
                for row in cur.fetchall()
            ]
            cur.execute(f"SELECT COUNT(*) AS n FROM {name}")
            count = cur.fetchone()["n"]
            tables[name] = {
                "description": TABLE_DESCRIPTIONS[name],
                "columns": cols,
                "row_count": int(count),
            }
    return SchemaResponse(
        tables=tables,
        notes=(
            "All tables are populated with synthetic data. The schema is "
            "deliberately denormalized for analytical queries — no PHI is "
            "stored or accepted."
        ),
    )


def _provenance(db: Database) -> dict[str, Any]:
    settings = get_settings()
    return {
        "data_source": "synthetic-multiple-myeloma-v1",
        "generator_seed": settings.random_seed,
        "n_patients_configured": settings.num_patients,
        "db_path": str(settings.db_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Fully synthetic data. Not derived from any real patient cohort."
        ),
    }


# ---------------------------------------------------------------------------


def get_db() -> Database:
    return ensure_database()


def create_app() -> FastAPI:
    app = FastAPI(
        title="VirtualLab-Copilot API",
        description=(
            "Natural-language cohort discovery over a synthetic translational-"
            "genomics multiple-myeloma dataset. Prototype for AI-assisted "
            "research engineering on biomedical data commons."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health(db: Database = Depends(get_db)) -> HealthResponse:
        seeded = db.is_seeded()
        n = 0
        if seeded:
            row = db.read_sql("SELECT COUNT(*) AS n FROM patients")
            n = int(row.iloc[0]["n"])
        return HealthResponse(
            status="ok",
            seeded=seeded,
            n_patients=n,
            db_path=str(get_settings().db_path),
        )

    @app.get("/schema", response_model=SchemaResponse)
    def schema(db: Database = Depends(get_db)) -> SchemaResponse:
        return _build_schema_response(db)

    @app.get("/example-questions", response_model=ExampleQuestionsResponse)
    def example_questions() -> ExampleQuestionsResponse:
        return ExampleQuestionsResponse(examples=EXAMPLE_QUESTIONS)

    @app.post("/query", response_model=QueryResponse)
    def query(req: QueryRequest, db: Database = Depends(get_db)) -> QueryResponse:
        try:
            parsed = parse_query(req.question)
            result = CohortService(db).run(parsed)
            summary = generate_summary(result)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("query failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return QueryResponse(
            parsed_query=parsed.model_dump(),
            sql=result.sql,
            sql_params=result.sql_params,
            cohort_size=result.cohort_size,
            demographics=result.demographics,
            clinical_summary=result.clinical_summary,
            mutation_frequency=result.mutation_frequency.to_dict(orient="records"),
            expression_summary=result.expression_summary.to_dict(orient="records"),
            comparison=result.comparison,
            summary=summary,
            provenance=_provenance(db),
        )

    return app


app = create_app()
