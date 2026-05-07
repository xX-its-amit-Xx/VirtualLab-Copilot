# VirtualLab-Copilot

> **AI-assisted translational genomics research copilot — prototype.**
> Ask plain-English questions about a synthetic multiple-myeloma cohort and get back a structured query plan, SQL, cohort summaries, multi-omic visualizations, and an AI-style analytical report.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/api-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/ui-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](#testing)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> ⚠️ **All data is synthetic.** No real patient records are used. Nothing in this repo is clinical advice or a regulated medical device.

---

## What it does

VirtualLab-Copilot is a small, end-to-end demo of how a research engineer might build a **natural-language cohort discovery layer** on top of a translational-genomics data commons (think Gen3 / AWS HealthOmics). It packages:

1. **Synthetic data generation** — patients, mutations, bulk RNA-seq, clinical labs, with biology-flavored distributions (ISS stage drives β2-microglobulin, responders get a survival benefit, etc.).
2. **Natural-language parser** — turns a question like *"Find patients with TP53 mutations and high beta-2 microglobulin"* into a typed `ParsedQuery` (intent, filters, comparison, target gene, confidence).
3. **Cohort engine** — compiles the parsed query into SQL, runs it against a SQLite database, and returns a `CohortResult` bundle (size, demographics, clinical summary, mutation frequency, expression summary, group comparison).
4. **Visualizations** — Kaplan-Meier-like PFS curve, response distribution, mutation frequency bar, age-by-stage histogram, gene-expression boxplot.
5. **AI-style narrative summary** — deterministic template that produces a headline + key findings + caveats + suggested next analyses, structured so it can be swapped for an LLM-backed summarizer.
6. **FastAPI backend** with `/query`, `/schema`, `/example-questions`, `/health`.
7. **Streamlit frontend** that ties it all together with example-question buttons, a query plan viewer, plots, and a provenance panel.

### Example questions

| Question | What the parser does |
| --- | --- |
| *Show patients with ISS stage III treated with proteasome inhibitors* | Two patient-level filters → `ISS_stage='III' AND therapy_class='Proteasome Inhibitor'` |
| *Compare PFS for responders vs non-responders* | `Comparison(group_a='Responder', group_b='Non-Responder', metric='progression_free_survival_months')` → side-by-side KM curves |
| *Find patients with TP53 mutations and high beta-2 microglobulin* | `EXISTS` subquery on `genomics` + threshold filter on `clinical_labs` |
| *Show MYC expression in patients on anti-CD38 therapy* | Therapy filter + transcriptomics summary scoped to MYC |
| *What are the most common mutations in older patients (over 70)?* | `age >= 70` filter + ranked mutation frequency |

---

## Architecture

```
┌────────────────┐    POST /query    ┌───────────────────────────┐
│  Streamlit UI  │ ────────────────▶ │       FastAPI API         │
│  (frontend)    │ ◀──────────────── │  /query /schema /health   │
└────────────────┘   ParsedQuery +   └─────────────┬─────────────┘
        ▲             CohortResult +               │
        │             AI-style summary             ▼
        │                                ┌──────────────────┐
        │                                │ Parser (rules) ──┼── future: LLM/RAG adapter
        │                                ├──────────────────┤
        │                                │ Cohort service   │
        │                                ├──────────────────┤
        │                                │ Stats / Summary  │
        │                                ├──────────────────┤
        │                                │ SQLite database  │ ◀── Synthetic data generator
        └────────────── plots ──────────▶│ (4 tables)       │
                                         └──────────────────┘
```

```
src/
├── data/           # Synthetic dataset generator
├── database/       # SQLite schema + thin repository
├── parser/         # NL → ParsedQuery (rule-based, LLM-pluggable)
├── analysis/       # Cohort service, stats, AI-style summary
├── visualization/  # Plotly figure builders
├── api/            # FastAPI app
└── frontend/       # Streamlit app
```

---

## Quickstart

### Local (no Docker)

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Seed the synthetic database (idempotent)
python scripts/seed_db.py            # use --force to reseed

# 3. Run tests
pytest -ra

# 4. Start the API and the UI (in two terminals)
uvicorn src.api.main:app --reload --port 8000
streamlit run src/frontend/app.py --server.port 8501
```

Then open:

- API docs: http://localhost:8000/docs
- Streamlit UI: http://localhost:8501

### Docker

```bash
docker compose up --build
# API at  http://localhost:8000
# UI  at  http://localhost:8501
```

The compose file ships two services backed by the same image — one running uvicorn, one running streamlit — sharing a named volume for the SQLite database.

---

## API reference

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness + seed status. |
| `GET` | `/schema` | Table-by-table schema with descriptions and row counts. |
| `GET` | `/example-questions` | Curated example questions, used by the UI. |
| `POST` | `/query` | Body `{"question": "..."}` → parsed query, SQL, cohort summary, AI-style report, provenance. |

`POST /query` response (abridged):

```jsonc
{
  "parsed_query": {
    "intent": "describe_cohort",
    "filters": [{ "table": "patients", "column": "ISS_stage", "operator": "=", "value": "III" }],
    "confidence": 0.65
  },
  "sql": "SELECT p.patient_id FROM patients p WHERE p.ISS_stage = ?",
  "sql_params": ["III"],
  "cohort_size": 117,
  "demographics": { "age_median": 67.0, "sex_distribution": { "Male": 64, "Female": 53 }, ... },
  "clinical_summary": { "pfs_median_months": 17.4, "response_rate": 0.61, ... },
  "mutation_frequency": [{ "mutation_gene": "KRAS", "n_patients": 22, "frequency": 0.188 }, ...],
  "summary": {
    "headline": "Identified a synthetic cohort of **117 patients** ISS stage III.",
    "findings": ["Median age was 67 years (IQR 60-74). ..."],
    "caveats": ["All values are synthetic ..."],
    "next_steps": ["Stratify by ... ", "..."]
  },
  "provenance": { "data_source": "synthetic-multiple-myeloma-v1", "generator_seed": 42, ... }
}
```

---

## Data model

| Table | Grain | Key columns |
| --- | --- | --- |
| `patients` | one row per patient | `patient_id`, `age`, `sex`, `race_ethnicity`, `diagnosis_date`, `ISS_stage`, `treatment_line`, `therapy_class`, `response`, `progression_free_survival_months`, `overall_survival_months` |
| `genomics` | one row per (patient, mutated gene) | `patient_id`, `mutation_gene`, `mutation_type`, `variant_allele_frequency` |
| `transcriptomics` | one row per (patient, gene) | `patient_id`, `gene`, `expression_value` (log2-TPM-like) |
| `clinical_labs` | one row per patient | `patient_id`, `albumin`, `beta2_microglobulin`, `hemoglobin`, `creatinine`, `calcium` |

The generator is deterministic given a seed (`VLC_RANDOM_SEED`) and uses biology-flavored conditional distributions (e.g. ISS-III patients have higher β2-microglobulin and worse PFS; responders get a survival bump). It is **not** trained on or derived from any real cohort.

---

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VLC_DB_PATH` | `./data/virtuallab.db` | SQLite database path |
| `VLC_RANDOM_SEED` | `42` | Generator seed (deterministic) |
| `VLC_NUM_PATIENTS` | `400` | Cohort size to generate |
| `VLC_API_BASE_URL` | `http://localhost:8000` | URL the Streamlit app calls |
| `VLC_API_HOST` / `VLC_API_PORT` | `0.0.0.0` / `8000` | uvicorn bind |
| `VLC_LLM_PROVIDER` | *(empty)* | Reserved for the future LLM adapter |

---

## Testing

```bash
pytest -ra
```

The suite covers the parser (intent, filters, SQL compilation), the cohort service (filtering correctness, comparison block), and the API (health, schema, query endpoint, validation). It uses an isolated temp database so it never touches your dev data.

---

## Limitations

- Survival curves are **uncensored** and computed via a simplified KM-style step function. Replace with `lifelines` for any serious analysis.
- The parser is **rule-based**; it will miss synonyms outside its lexicon. The `parse_query()` entry point is built so an LLM/RAG adapter can replace it without changing the API contract.
- Statistical summaries are descriptive only — no multiple-testing correction, no covariate adjustment, no propensity matching.
- The dataset is synthetic and small (default 400 patients); summary statistics are illustrative, not generalizable.
- No authentication / authorization. Production deployments on a Gen3-style commons must layer on identity (e.g. Fence, Cognito), audit logging, and row-level access controls.

---

## Future work

- **LLM/RAG adapter for the parser.** Drop a `src/parser/llm_adapter.py` that produces a `ParsedQuery` from natural language with a retrieval step over the schema, dictionary entries, and a few-shot example bank. The `parse_query()` dispatcher is already wired to use it when `VLC_LLM_PROVIDER` is set.
- **Gen3 / AWS integration.** Swap the SQLite repository for a Gen3 PFB / Guppy-backed adapter or an AWS HealthOmics + Athena query engine. Keep `Database` as the single seam.
- **Authentication.** Plug a Fence/Cognito JWT validator into the FastAPI dependency tree and enforce per-cohort access in the cohort service.
- **Censored survival.** Add a `event_observed` column and switch the KM helper to `lifelines.KaplanMeierFitter`.
- **Multi-omic joins.** Today the prototype models bulk RNA-seq and somatic mutations; extend with cytogenetics (e.g. t(4;14), del(17p)), single-cell metadata, and proteomics.
- **Provenance / lineage.** Emit a structured provenance record per query (parser version, seed, table snapshots) into a dedicated table for reproducibility.
- **Caching & async.** Cache parsed queries and paginate large cohorts; move heavy aggregations to background tasks.

---

## Why this exists

This repo is a portfolio demonstration aimed at AI Research Engineering Intern roles working on translational-genomics data commons. It tries to show, end-to-end on synthetic data:

- A clean **boundary between rule-based and LLM-backed components** so the team can iterate on the smart layer without touching analytics.
- Honest treatment of **clinical-data realities** — provenance, disclaimers, censoring caveats, and a data model that resembles what an MM cohort actually looks like.
- A working **multi-omic cohort discovery loop**: NL → SQL → tables → plots → narrative.
- Production-shaped scaffolding (typed APIs, tests, Docker, settings, `Makefile`) without overengineering the core science.

---

## Screenshots

> Screenshots / GIFs go here once the UI has been captured.

- `docs/screenshots/streamlit-overview.png` — landing page with example questions
- `docs/screenshots/query-plan.png` — parsed intent + generated SQL
- `docs/screenshots/survival-curve.png` — Kaplan-Meier-style PFS by responder status
- `docs/screenshots/mutation-frequency.png` — top mutated genes for a cohort

---

## License

MIT — see [LICENSE](LICENSE).
