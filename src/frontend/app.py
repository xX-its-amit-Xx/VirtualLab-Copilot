"""Streamlit UI for VirtualLab-Copilot.

Run with:
    streamlit run src/frontend/app.py

The app talks to the FastAPI backend over HTTP for the parsed query and
cohort summary, but builds plots locally using the analysis + visualization
modules so we keep figures interactive without round-tripping JSON for
plotly traces.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.analysis import CohortService, generate_summary
from src.config import get_settings
from src.database import ensure_database
from src.parser import parse_query
from src.visualization import (
    build_demographics_figure,
    build_expression_boxplot,
    build_mutation_frequency_figure,
    build_response_rate_figure,
    build_survival_figure,
)

st.set_page_config(
    page_title="VirtualLab-Copilot",
    page_icon=":dna:",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Seeding synthetic database...")
def _bootstrap():
    """Ensure the database exists and is seeded; return a (db, service) pair."""
    db = ensure_database()
    return db, CohortService(db)


def _api_base_url() -> str:
    return os.environ.get("VLC_API_BASE_URL", get_settings().api_base_url)


def _try_remote_health() -> dict[str, Any] | None:
    try:
        r = requests.get(f"{_api_base_url()}/health", timeout=2)
        if r.ok:
            return r.json()
    except requests.RequestException:
        return None
    return None


def _example_questions(local_only: bool = False) -> list[dict[str, str]]:
    if not local_only:
        try:
            r = requests.get(f"{_api_base_url()}/example-questions", timeout=2)
            if r.ok:
                return r.json().get("examples", [])
        except requests.RequestException:
            pass
    return [
        {"text": "Show patients with ISS stage III treated with proteasome inhibitors"},
        {"text": "Compare PFS for responders vs non-responders"},
        {"text": "Find patients with TP53 mutations and high beta-2 microglobulin"},
        {"text": "Show MYC expression in patients on anti-CD38 therapy"},
        {"text": "What are the most common mutations in older patients (over 70)?"},
        {"text": "Compare survival between stage I and stage III myeloma"},
    ]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


db, service = _bootstrap()
settings = get_settings()
remote = _try_remote_health()

with st.sidebar:
    st.title("VirtualLab-Copilot")
    st.caption(
        "Prototype AI-assisted research copilot for translational genomics. "
        "All data is **fully synthetic**."
    )
    st.markdown("---")
    st.subheader("Status")
    if remote:
        st.success(
            f"API live · {remote['n_patients']} patients\n\n`{remote['db_path']}`"
        )
    else:
        st.info(
            "Running in local mode (FastAPI not reachable). "
            "All analysis runs in-process."
        )
    with st.expander("Database provenance"):
        st.write(
            {
                "data_source": "synthetic-multiple-myeloma-v1",
                "seed": settings.random_seed,
                "n_patients_configured": settings.num_patients,
                "db_path": str(settings.db_path),
            }
        )
    st.markdown("---")
    st.subheader("Try an example")
    examples = _example_questions(local_only=remote is None)
    for ex in examples:
        if st.button(ex["text"], use_container_width=True, key=f"ex-{ex['text']}"):
            st.session_state["question"] = ex["text"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


st.title(":dna: VirtualLab-Copilot")
st.markdown(
    "Ask a research question in plain English. The copilot turns it into a "
    "structured query, runs it against a synthetic multiple-myeloma database, "
    "and returns cohort summaries, visualizations, and an AI-style report."
)
st.warning(
    "**Demo data only.** All patients, mutations, and expression values "
    "shown here are synthetic. This tool is not for clinical use.",
    icon="⚠️",
)

if "question" not in st.session_state:
    st.session_state["question"] = (
        "Show patients with ISS stage III treated with proteasome inhibitors"
    )

question = st.text_input(
    "Research question",
    key="question",
    help="Tip: mention ISS stage, therapy class, mutated genes, or labs.",
)
run = st.button("Run query", type="primary")


def _execute(q: str):
    parsed = parse_query(q)
    result = service.run(parsed)
    summary = generate_summary(result)
    return parsed, result, summary


if run or "_last_q" not in st.session_state:
    st.session_state["_last_q"] = question

with st.spinner("Parsing question and running cohort discovery..."):
    parsed, result, summary = _execute(st.session_state["_last_q"])

# -- Top metrics row --------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Cohort size", result.cohort_size)
c2.metric(
    "Median age",
    result.demographics.get("age_median", "—") if result.cohort_size else "—",
)
rr = result.clinical_summary.get("response_rate") if result.cohort_size else None
c3.metric("Response rate", f"{rr * 100:.1f}%" if rr is not None else "—")
c4.metric(
    "Median PFS (mo)",
    result.clinical_summary.get("pfs_median_months", "—") if result.cohort_size else "—",
)
c5.metric(
    "Median OS (mo)",
    result.clinical_summary.get("os_median_months", "—") if result.cohort_size else "—",
)

# -- AI-style summary -------------------------------------------------------

st.markdown("### AI-style analytical summary")
st.markdown(f"**{summary['headline']}**")
if summary.get("findings"):
    st.markdown("**Key findings**")
    for f in summary["findings"]:
        st.markdown(f"- {f}")
if summary.get("caveats"):
    with st.expander("Caveats"):
        for c in summary["caveats"]:
            st.markdown(f"- {c}")
if summary.get("next_steps"):
    with st.expander("Suggested next analyses"):
        for s in summary["next_steps"]:
            st.markdown(f"- {s}")

# -- Query plan -------------------------------------------------------------

st.markdown("### Generated query plan")
plan_col, sql_col = st.columns(2)
with plan_col:
    st.markdown("**Parsed intent**")
    st.json(
        {
            "intent": parsed.intent.value,
            "confidence": parsed.confidence,
            "filters": [f.model_dump() for f in parsed.filters],
            "comparison": parsed.comparison.model_dump() if parsed.comparison else None,
            "target_gene": parsed.target_gene,
            "notes": parsed.notes,
        }
    )
with sql_col:
    st.markdown("**SQL executed**")
    st.code(result.sql, language="sql")
    st.caption(f"params = {result.sql_params}")

# -- Plots ------------------------------------------------------------------

st.markdown("### Visualizations")
tab_surv, tab_resp, tab_mut, tab_demo, tab_expr = st.tabs(
    [
        "Survival (PFS)",
        "Response distribution",
        "Mutation frequency",
        "Demographics",
        "Gene expression",
    ]
)

with tab_surv:
    st.plotly_chart(build_survival_figure(result), use_container_width=True)
with tab_resp:
    st.plotly_chart(build_response_rate_figure(result), use_container_width=True)
with tab_mut:
    st.plotly_chart(build_mutation_frequency_figure(result), use_container_width=True)
with tab_demo:
    st.plotly_chart(build_demographics_figure(result), use_container_width=True)
with tab_expr:
    gene_choice = st.selectbox(
        "Gene",
        options=sorted(result.expression_summary["gene"].unique()) if not result.expression_summary.empty else [],
        index=0 if not result.expression_summary.empty else None,
        help="Choose a gene to see its expression split by responder status.",
    )
    if gene_choice:
        st.plotly_chart(
            build_expression_boxplot(result, db, gene=gene_choice),
            use_container_width=True,
        )

# -- Cohort table & provenance ---------------------------------------------

st.markdown("### Cohort details")
left, right = st.columns([2, 1])
with left:
    if result.cohort_size:
        st.dataframe(
            result.patients.head(50),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Showing first 50 of {result.cohort_size} patients.")
    else:
        st.info("No patients matched the parsed query.")
with right:
    st.markdown("**Mutation frequency**")
    if result.mutation_frequency.empty:
        st.write("—")
    else:
        st.dataframe(
            result.mutation_frequency.head(15),
            use_container_width=True,
            hide_index=True,
        )

st.markdown("### Data provenance")
st.json(
    {
        "data_source": "synthetic-multiple-myeloma-v1",
        "generator_seed": settings.random_seed,
        "n_patients_configured": settings.num_patients,
        "db_path": str(settings.db_path),
        "disclaimer": (
            "Fully synthetic. Not derived from any real patient cohort. "
            "Not for clinical use."
        ),
    }
)
