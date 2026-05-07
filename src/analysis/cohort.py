"""Cohort discovery: turn a ``ParsedQuery`` into materialized result tables.

The :class:`CohortService` is the single place where parsed intents are
applied to the database. It returns a :class:`CohortResult` bundle that
the API and Streamlit frontend both consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..database import Database
from ..parser import ParsedQuery
from ..parser.rules import RESPONDER_KEYWORDS


RESPONDER_MAP = {
    "Complete Response": "Responder",
    "Very Good Partial Response": "Responder",
    "Partial Response": "Responder",
    "Stable Disease": "Non-Responder",
    "Progressive Disease": "Non-Responder",
}


@dataclass
class CohortResult:
    """Bundle of analytical artifacts for a single user query."""

    parsed_query: ParsedQuery
    sql: str
    sql_params: list
    cohort_size: int
    patients: pd.DataFrame
    demographics: dict[str, Any]
    clinical_summary: dict[str, Any]
    mutation_frequency: pd.DataFrame
    expression_summary: pd.DataFrame
    comparison: dict[str, Any] | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parsed_query": self.parsed_query.model_dump(),
            "sql": self.sql,
            "sql_params": self.sql_params,
            "cohort_size": self.cohort_size,
            "patients": self.patients.to_dict(orient="records"),
            "demographics": self.demographics,
            "clinical_summary": self.clinical_summary,
            "mutation_frequency": self.mutation_frequency.to_dict(orient="records"),
            "expression_summary": self.expression_summary.to_dict(orient="records"),
            "comparison": self.comparison,
        }


class CohortService:
    """Apply a parsed query against the database and aggregate results."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- entry point ------------------------------------------------------

    def run(self, parsed: ParsedQuery) -> CohortResult:
        sql, params = parsed.to_sql()
        ids_df = self.db.read_sql(sql, tuple(params))
        patient_ids: list[str] = ids_df["patient_id"].tolist()

        if not patient_ids:
            empty = pd.DataFrame()
            return CohortResult(
                parsed_query=parsed,
                sql=sql,
                sql_params=params,
                cohort_size=0,
                patients=empty,
                demographics={},
                clinical_summary={},
                mutation_frequency=empty,
                expression_summary=empty,
                comparison=None,
            )

        patients = self._fetch_patients(patient_ids)
        labs = self._fetch_labs(patient_ids)
        merged = patients.merge(labs, on="patient_id", how="left")

        demographics = self._summarize_demographics(merged)
        clinical_summary = self._summarize_clinical(merged)
        mutation_freq = self._mutation_frequency(patient_ids)
        expression_summary = self._expression_summary(patient_ids, parsed.target_gene)
        comparison = self._comparison(merged, parsed)

        return CohortResult(
            parsed_query=parsed,
            sql=sql,
            sql_params=params,
            cohort_size=len(patient_ids),
            patients=merged,
            demographics=demographics,
            clinical_summary=clinical_summary,
            mutation_frequency=mutation_freq,
            expression_summary=expression_summary,
            comparison=comparison,
        )

    # -- fetchers ---------------------------------------------------------

    def _fetch_patients(self, patient_ids: list[str]) -> pd.DataFrame:
        placeholders = ",".join(["?"] * len(patient_ids))
        return self.db.read_sql(
            f"SELECT * FROM patients WHERE patient_id IN ({placeholders})",
            tuple(patient_ids),
        )

    def _fetch_labs(self, patient_ids: list[str]) -> pd.DataFrame:
        placeholders = ",".join(["?"] * len(patient_ids))
        return self.db.read_sql(
            f"SELECT * FROM clinical_labs WHERE patient_id IN ({placeholders})",
            tuple(patient_ids),
        )

    # -- summaries --------------------------------------------------------

    @staticmethod
    def _summarize_demographics(df: pd.DataFrame) -> dict[str, Any]:
        return {
            "n": int(len(df)),
            "age_mean": round(float(df["age"].mean()), 1),
            "age_median": float(df["age"].median()),
            "age_iqr": [
                float(df["age"].quantile(0.25)),
                float(df["age"].quantile(0.75)),
            ],
            "sex_distribution": df["sex"].value_counts().to_dict(),
            "race_distribution": df["race_ethnicity"].value_counts().to_dict(),
            "iss_distribution": df["ISS_stage"].value_counts().to_dict(),
            "therapy_distribution": df["therapy_class"].value_counts().to_dict(),
            "response_distribution": df["response"].value_counts().to_dict(),
        }

    @staticmethod
    def _summarize_clinical(df: pd.DataFrame) -> dict[str, Any]:
        cols = ["albumin", "beta2_microglobulin", "hemoglobin", "creatinine", "calcium"]
        out: dict[str, Any] = {}
        for c in cols:
            if c in df.columns and df[c].notna().any():
                out[c] = {
                    "mean": round(float(df[c].mean()), 2),
                    "median": round(float(df[c].median()), 2),
                    "std": round(float(df[c].std(ddof=1) or 0.0), 2),
                }
        out["pfs_median_months"] = round(
            float(df["progression_free_survival_months"].median()), 1
        )
        out["os_median_months"] = round(
            float(df["overall_survival_months"].median()), 1
        )
        out["response_rate"] = round(
            float(df["response"].map(RESPONDER_MAP).eq("Responder").mean()), 3
        )
        return out

    def _mutation_frequency(self, patient_ids: list[str]) -> pd.DataFrame:
        placeholders = ",".join(["?"] * len(patient_ids))
        df = self.db.read_sql(
            f"""
            SELECT mutation_gene, COUNT(DISTINCT patient_id) AS n_patients
            FROM genomics
            WHERE patient_id IN ({placeholders})
            GROUP BY mutation_gene
            ORDER BY n_patients DESC
            """,
            tuple(patient_ids),
        )
        n = len(patient_ids)
        if not df.empty:
            df["frequency"] = (df["n_patients"] / n).round(3)
        return df

    def _expression_summary(
        self, patient_ids: list[str], target_gene: str | None
    ) -> pd.DataFrame:
        placeholders = ",".join(["?"] * len(patient_ids))
        gene_clause = ""
        params: list[Any] = list(patient_ids)
        if target_gene:
            gene_clause = " AND gene = ?"
            params.append(target_gene)
        df = self.db.read_sql(
            f"""
            SELECT gene,
                   AVG(expression_value) AS mean_expression,
                   COUNT(*) AS n
            FROM transcriptomics
            WHERE patient_id IN ({placeholders}){gene_clause}
            GROUP BY gene
            ORDER BY mean_expression DESC
            """,
            tuple(params),
        )
        if not df.empty:
            df["mean_expression"] = df["mean_expression"].round(3)
        return df

    @staticmethod
    def _comparison(df: pd.DataFrame, parsed: ParsedQuery) -> dict[str, Any] | None:
        comp = parsed.comparison
        if comp is None or df.empty:
            return None
        df = df.copy()
        if comp.column == "responder_label":
            df["responder_label"] = df["response"].map(RESPONDER_MAP)
            col = "responder_label"
        else:
            col = comp.column
        if col not in df.columns:
            return None
        groups = {}
        for label in (comp.group_a, comp.group_b):
            sub = df[df[col] == label]
            if sub.empty:
                continue
            groups[label] = {
                "n": int(len(sub)),
                "pfs_median": round(
                    float(sub["progression_free_survival_months"].median()), 1
                ),
                "os_median": round(
                    float(sub["overall_survival_months"].median()), 1
                ),
                "response_rate": round(
                    float(
                        sub["response"].map(RESPONDER_MAP).eq("Responder").mean()
                    ),
                    3,
                ),
            }
        return {
            "column": col,
            "metric": comp.metric,
            "groups": groups,
        }


# Convenience for the visualization layer ------------------------------------


def attach_responder_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["responder_label"] = df["response"].map(RESPONDER_MAP)
    return df


__all__ = ["CohortResult", "CohortService", "attach_responder_label", "RESPONDER_MAP"]
# RESPONDER_KEYWORDS is re-exported for completeness.
_ = RESPONDER_KEYWORDS  # silence unused import in some linters
