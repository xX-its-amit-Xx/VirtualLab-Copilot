"""Cohort service / filtering tests."""
from __future__ import annotations

from src.analysis import generate_summary
from src.parser import parse_query


def test_cohort_size_consistent_with_filters(cohort_service, db):
    parsed = parse_query("Show patients with ISS stage III")
    result = cohort_service.run(parsed)
    assert result.cohort_size > 0
    # Every returned patient should actually be ISS III.
    assert (result.patients["ISS_stage"] == "III").all()


def test_cohort_zero_for_impossible_filter(cohort_service):
    parsed = parse_query("ISS stage III treated with proteasome inhibitors")
    # Manually narrow to an impossible age constraint.
    from src.parser.intents import CohortFilter

    parsed.filters.append(
        CohortFilter(
            table="patients",
            column="age",
            operator=">=",
            value=200,
            rationale="impossible age",
        )
    )
    result = cohort_service.run(parsed)
    assert result.cohort_size == 0
    summary = generate_summary(result)
    assert summary["headline"].startswith("No patients")


def test_genomics_filter_returns_only_mutated_patients(cohort_service, db):
    parsed = parse_query("Find patients with TP53 mutations")
    result = cohort_service.run(parsed)
    if result.cohort_size == 0:
        return  # Possible but unlikely with seed=7 / n=120
    pids = result.patients["patient_id"].tolist()
    placeholders = ",".join(["?"] * len(pids))
    mutated = db.read_sql(
        f"SELECT DISTINCT patient_id FROM genomics WHERE mutation_gene='TP53' "
        f"AND patient_id IN ({placeholders})",
        tuple(pids),
    )
    assert len(mutated) == len(pids)


def test_summary_contains_key_numbers(cohort_service):
    parsed = parse_query("Show patients with ISS stage II")
    result = cohort_service.run(parsed)
    summary = generate_summary(result)
    keys = summary["key_numbers"]
    assert keys["cohort_size"] == result.cohort_size
    assert keys["median_age"] is not None
    assert "disclaimer" in summary


def test_comparison_block_populated_when_responder_compare(cohort_service):
    parsed = parse_query("Compare PFS for responders vs non-responders")
    result = cohort_service.run(parsed)
    assert result.comparison is not None
    assert "Responder" in result.comparison["groups"]
