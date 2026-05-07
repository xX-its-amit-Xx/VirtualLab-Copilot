"""FastAPI endpoint smoke tests using the Starlette TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["seeded"] is True
    assert body["n_patients"] > 0


def test_schema_lists_all_tables(client):
    r = client.get("/schema")
    assert r.status_code == 200
    body = r.json()
    assert set(body["tables"].keys()) == {
        "patients",
        "genomics",
        "transcriptomics",
        "clinical_labs",
    }
    for t in body["tables"].values():
        assert t["row_count"] > 0
        assert t["columns"]


def test_example_questions_nonempty(client):
    r = client.get("/example-questions")
    assert r.status_code == 200
    body = r.json()
    assert len(body["examples"]) >= 3


def test_query_endpoint_returns_summary(client):
    r = client.post(
        "/query",
        json={"question": "Show patients with ISS stage II"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cohort_size"] > 0
    assert "headline" in body["summary"]
    assert body["sql"].startswith("SELECT p.patient_id")
    assert body["provenance"]["data_source"].startswith("synthetic")


def test_query_validation_rejects_empty(client):
    r = client.post("/query", json={"question": ""})
    assert r.status_code == 422
