"""Plotly figure builders.

Each builder returns a ``plotly.graph_objects.Figure``. The builders are
written to be safe for empty cohorts — they return a placeholder figure
with an explanatory annotation rather than raising.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ..analysis.cohort import CohortResult, attach_responder_label
from ..analysis.stats import kaplan_meier_like
from ..database import Database


def _placeholder(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 14},
            }
        ],
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig


# ---------------------------------------------------------------------------


def build_survival_figure(result: CohortResult) -> go.Figure:
    """Kaplan-Meier-style PFS curve. Splits by responder if comparing."""
    if result.cohort_size == 0 or result.patients.empty:
        return _placeholder("Progression-Free Survival", "No patients in cohort.")

    df = attach_responder_label(result.patients)
    fig = go.Figure()
    if result.comparison and result.comparison.get("column") == "responder_label":
        for label, color in [("Responder", "#2ca02c"), ("Non-Responder", "#d62728")]:
            sub = df[df["responder_label"] == label]
            if sub.empty:
                continue
            curve = kaplan_meier_like(sub["progression_free_survival_months"])
            fig.add_trace(
                go.Scatter(
                    x=curve["time"],
                    y=curve["survival"],
                    mode="lines",
                    line={"shape": "hv", "color": color, "width": 2.5},
                    name=f"{label} (n={len(sub)})",
                )
            )
    else:
        curve = kaplan_meier_like(df["progression_free_survival_months"])
        fig.add_trace(
            go.Scatter(
                x=curve["time"],
                y=curve["survival"],
                mode="lines",
                line={"shape": "hv", "color": "#1f77b4", "width": 2.5},
                name=f"Cohort (n={result.cohort_size})",
            )
        )
    fig.update_layout(
        title="Progression-Free Survival (synthetic)",
        xaxis_title="Months",
        yaxis_title="Survival probability",
        yaxis={"range": [0, 1.02]},
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def build_response_rate_figure(result: CohortResult) -> go.Figure:
    if result.cohort_size == 0:
        return _placeholder("Response Distribution", "No patients in cohort.")
    counts = (
        result.patients["response"]
        .value_counts()
        .reindex(
            [
                "Complete Response",
                "Very Good Partial Response",
                "Partial Response",
                "Stable Disease",
                "Progressive Disease",
            ],
            fill_value=0,
        )
    )
    fig = px.bar(
        x=counts.index,
        y=counts.values,
        labels={"x": "Response category", "y": "Patients"},
        color=counts.index,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        title="Response Distribution",
        showlegend=False,
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def build_mutation_frequency_figure(result: CohortResult, top_n: int = 12) -> go.Figure:
    df = result.mutation_frequency
    if df.empty:
        return _placeholder("Mutation Frequency", "No mutations in cohort.")
    df = df.head(top_n).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=df["frequency"],
            y=df["mutation_gene"],
            orientation="h",
            marker={"color": "#9467bd"},
            text=[f"{f * 100:.0f}%" for f in df["frequency"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"Top {top_n} Mutated Genes (cohort)",
        xaxis_title="Fraction of patients",
        yaxis_title="Gene",
        margin={"l": 60, "r": 30, "t": 50, "b": 40},
    )
    return fig


def build_demographics_figure(result: CohortResult) -> go.Figure:
    if result.cohort_size == 0:
        return _placeholder("Demographics", "No patients in cohort.")
    df = result.patients
    fig = px.histogram(
        df,
        x="age",
        color="ISS_stage",
        nbins=20,
        barmode="overlay",
        opacity=0.65,
        category_orders={"ISS_stage": ["I", "II", "III"]},
        color_discrete_sequence=px.colors.qualitative.Vivid,
    )
    fig.update_layout(
        title="Age distribution by ISS stage",
        xaxis_title="Age (years)",
        yaxis_title="Patients",
        legend_title_text="ISS stage",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def build_expression_boxplot(
    result: CohortResult, db: Database, gene: str | None = None
) -> go.Figure:
    """Boxplot of expression for a target gene, split by responder status."""
    target_gene = gene or result.parsed_query.target_gene
    if not target_gene or result.cohort_size == 0:
        return _placeholder(
            "Gene Expression",
            "No target gene selected. Mention a gene (e.g. MYC) in your question.",
        )
    placeholders = ",".join(["?"] * result.cohort_size)
    pids = result.patients["patient_id"].tolist()
    expr = db.read_sql(
        f"""
        SELECT t.patient_id, t.expression_value, p.response
        FROM transcriptomics t
        JOIN patients p ON p.patient_id = t.patient_id
        WHERE t.patient_id IN ({placeholders}) AND t.gene = ?
        """,
        tuple([*pids, target_gene]),
    )
    if expr.empty:
        return _placeholder(
            f"{target_gene} Expression",
            "No transcriptomics rows found for this gene/cohort.",
        )
    expr = expr.assign(
        responder_label=expr["response"].map(
            {
                "Complete Response": "Responder",
                "Very Good Partial Response": "Responder",
                "Partial Response": "Responder",
                "Stable Disease": "Non-Responder",
                "Progressive Disease": "Non-Responder",
            }
        )
    )
    fig = px.box(
        expr,
        x="responder_label",
        y="expression_value",
        points="outliers",
        color="responder_label",
        color_discrete_map={"Responder": "#2ca02c", "Non-Responder": "#d62728"},
    )
    fig.update_layout(
        title=f"{target_gene} expression — responders vs non-responders",
        xaxis_title="",
        yaxis_title="Expression (log2-TPM-like, synthetic)",
        showlegend=False,
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


__all__ = [
    "build_survival_figure",
    "build_response_rate_figure",
    "build_mutation_frequency_figure",
    "build_demographics_figure",
    "build_expression_boxplot",
]


# Re-export a tiny helper so consumers can build a DataFrame from the
# expression summary without re-querying.
def expression_summary_to_df(result: CohortResult) -> pd.DataFrame:
    return result.expression_summary.copy()
