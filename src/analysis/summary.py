"""AI-style narrative summary of a CohortResult.

This module produces a human-readable report. It is *not* an LLM call —
it's a deterministic template informed by the cohort statistics. The
shape of the output (headline / findings / caveats / next steps) was
chosen so a future LLM-backed summarizer can be slotted in with the same
contract.
"""
from __future__ import annotations

from typing import Any

from .cohort import CohortResult


DISCLAIMER = (
    "All data shown here is **fully synthetic** and generated for "
    "demonstration of cohort-discovery tooling. Nothing in this report "
    "constitutes clinical advice."
)


def generate_summary(result: CohortResult) -> dict[str, Any]:
    """Return a structured summary suitable for both API and UI display."""
    if result.cohort_size == 0:
        return {
            "headline": "No patients matched your query.",
            "findings": [],
            "caveats": [
                "The parser may have over-constrained the cohort. "
                "Try removing one filter or broadening a value (e.g. ISS "
                "stage II OR III)."
            ],
            "next_steps": [
                "Re-run with a single filter to verify each predicate.",
                "Check the SQL plan in the UI to confirm the parser's "
                "interpretation matches your intent.",
            ],
            "disclaimer": DISCLAIMER,
        }

    parsed = result.parsed_query
    demo = result.demographics
    clinical = result.clinical_summary

    headline = _build_headline(result)
    findings = _build_findings(result)
    caveats = _build_caveats(result)
    next_steps = _build_next_steps(result)

    return {
        "headline": headline,
        "findings": findings,
        "caveats": caveats,
        "next_steps": next_steps,
        "parsed_intent": parsed.intent.value,
        "filters_applied": [f.model_dump() for f in parsed.filters],
        "key_numbers": {
            "cohort_size": result.cohort_size,
            "median_age": demo.get("age_median"),
            "response_rate": clinical.get("response_rate"),
            "median_pfs_months": clinical.get("pfs_median_months"),
            "median_os_months": clinical.get("os_median_months"),
        },
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------


def _build_headline(result: CohortResult) -> str:
    n = result.cohort_size
    parsed = result.parsed_query
    bits = [f"Identified a synthetic cohort of **{n} patients**"]
    filter_phrases = []
    for f in parsed.filters:
        if f.column == "ISS_stage":
            filter_phrases.append(f"ISS stage {f.value}")
        elif f.column == "therapy_class":
            filter_phrases.append(f"on {f.value}")
        elif f.column == "mutation_gene":
            filter_phrases.append(f"with {f.value} mutations")
        elif f.column == "age" and f.operator == ">=":
            filter_phrases.append(f"aged ≥{f.value}")
        elif f.column == "age" and f.operator == "<=":
            filter_phrases.append(f"aged ≤{f.value}")
        elif f.column.startswith("beta2") or f.column in {
            "albumin",
            "hemoglobin",
            "creatinine",
            "calcium",
        }:
            qualifier = "elevated" if f.operator in {">", ">="} else "low"
            filter_phrases.append(f"with {qualifier} {f.column.replace('_', ' ')}")
    if filter_phrases:
        bits.append(", ".join(filter_phrases))
    return " ".join(bits) + "."


def _build_findings(result: CohortResult) -> list[str]:
    findings: list[str] = []
    demo = result.demographics
    clinical = result.clinical_summary

    findings.append(
        f"Median age was {demo.get('age_median')} years (IQR "
        f"{demo.get('age_iqr', [0, 0])[0]:.0f}-{demo.get('age_iqr', [0, 0])[1]:.0f}). "
        f"Sex distribution: "
        + ", ".join(f"{k} = {v}" for k, v in demo.get("sex_distribution", {}).items())
        + "."
    )

    findings.append(
        f"Overall response rate was {clinical.get('response_rate', 0) * 100:.1f}%, "
        f"with median PFS of {clinical.get('pfs_median_months')} months and "
        f"median OS of {clinical.get('os_median_months')} months."
    )

    if not result.mutation_frequency.empty:
        top = result.mutation_frequency.head(3)
        top_bits = ", ".join(
            f"{row['mutation_gene']} ({row['frequency'] * 100:.0f}%)"
            for _, row in top.iterrows()
        )
        findings.append(f"Top mutated genes in this cohort: {top_bits}.")

    comp = result.comparison
    if comp:
        groups = comp.get("groups", {})
        if len(groups) == 2:
            (a_name, a), (b_name, b) = list(groups.items())
            findings.append(
                f"Group comparison ({a_name} vs {b_name}): "
                f"median PFS {a['pfs_median']} vs {b['pfs_median']} months; "
                f"response rate {a['response_rate'] * 100:.0f}% vs {b['response_rate'] * 100:.0f}%."
            )

    if not result.expression_summary.empty and result.parsed_query.target_gene:
        gene_row = result.expression_summary[
            result.expression_summary["gene"] == result.parsed_query.target_gene
        ]
        if not gene_row.empty:
            value = float(gene_row.iloc[0]["mean_expression"])
            findings.append(
                f"Mean {result.parsed_query.target_gene} expression in this "
                f"cohort: {value:.2f} (log2-TPM-like, synthetic)."
            )

    return findings


def _build_caveats(result: CohortResult) -> list[str]:
    caveats = [
        "All values are synthetic and generated to be plausible-looking, "
        "not clinically meaningful.",
        "Survival curves are uncensored; in real translational analyses, "
        "censoring and follow-up time must be modeled (e.g. lifelines).",
    ]
    if result.cohort_size < 30:
        caveats.append(
            f"Cohort size is small (n={result.cohort_size}); summary "
            "statistics will be unstable."
        )
    if result.parsed_query.confidence < 0.5:
        caveats.append(
            "Parser confidence is low — the structured filters may not "
            "fully capture the original question. Inspect the query plan."
        )
    return caveats


def _build_next_steps(result: CohortResult) -> list[str]:
    parsed = result.parsed_query
    steps: list[str] = []
    if parsed.target_gene:
        steps.append(
            f"Stratify by {parsed.target_gene} expression quartiles and "
            "recompute PFS to look for a dose-response effect."
        )
    if parsed.comparison is None and result.cohort_size > 50:
        steps.append(
            "Pick a comparator group (e.g. responders vs non-responders) "
            "and run a head-to-head Kaplan-Meier analysis."
        )
    if not result.mutation_frequency.empty:
        top_gene = result.mutation_frequency.iloc[0]["mutation_gene"]
        steps.append(
            f"Drill into {top_gene}-mutant patients and check whether "
            "VAF correlates with treatment response."
        )
    steps.append(
        "Once happy with the cohort definition, export to an analyst "
        "notebook (e.g. Gen3 workspace, AWS HealthOmics) for deeper modeling."
    )
    return steps
