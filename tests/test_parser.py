"""Parser unit tests."""
from __future__ import annotations

import pytest

from src.parser import parse_query
from src.parser.intents import QueryIntent


def test_iss_stage_and_therapy_extracted():
    parsed = parse_query(
        "Show patients with ISS stage III treated with proteasome inhibitors"
    )
    cols = {(f.column, f.value) for f in parsed.filters}
    assert ("ISS_stage", "III") in cols
    assert ("therapy_class", "Proteasome Inhibitor") in cols
    assert parsed.intent == QueryIntent.DESCRIBE_COHORT
    assert parsed.confidence > 0.5


def test_responder_comparison_detected():
    parsed = parse_query("Compare PFS for responders vs non-responders")
    assert parsed.comparison is not None
    assert parsed.comparison.group_a == "Responder"
    assert parsed.comparison.group_b == "Non-Responder"
    assert parsed.intent in {QueryIntent.COMPARE_GROUPS, QueryIntent.SURVIVAL_ANALYSIS}


def test_mutation_and_lab_filters():
    parsed = parse_query(
        "Find patients with TP53 mutations and high beta-2 microglobulin"
    )
    cols = [(f.table, f.column, f.operator) for f in parsed.filters]
    assert ("genomics", "mutation_gene", "=") in cols
    assert any(c[1] == "beta2_microglobulin" and c[2] in (">=", ">") for c in cols)
    assert parsed.target_gene == "TP53"


def test_age_over_filter():
    parsed = parse_query("Most common mutations in patients over 70")
    age_filters = [f for f in parsed.filters if f.column == "age"]
    assert len(age_filters) == 1
    assert age_filters[0].operator == ">="
    assert age_filters[0].value == 70


def test_to_sql_compiles_with_genomics_exists():
    parsed = parse_query("Find patients with TP53 mutations")
    sql, params = parsed.to_sql()
    assert sql.startswith("SELECT p.patient_id FROM patients p")
    assert "EXISTS" in sql
    assert "TP53" in params


def test_describe_cohort_default_for_vague_question():
    parsed = parse_query("Tell me about the patients")
    assert parsed.intent == QueryIntent.DESCRIBE_COHORT
    assert parsed.notes  # falls back with a note


@pytest.mark.parametrize(
    "q,expected_value",
    [
        ("Patients with ISS stage I", "I"),
        ("ISS Stage 2 patients", "II"),
        ("stage III myeloma", "III"),
    ],
)
def test_iss_stage_variants(q, expected_value):
    parsed = parse_query(q)
    iss = [f for f in parsed.filters if f.column == "ISS_stage"]
    assert len(iss) == 1
    assert iss[0].value == expected_value
