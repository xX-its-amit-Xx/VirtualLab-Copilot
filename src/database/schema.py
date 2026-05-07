"""SQL schema definitions for the synthetic research database."""
from __future__ import annotations

SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY,
        age INTEGER NOT NULL,
        sex TEXT NOT NULL,
        race_ethnicity TEXT NOT NULL,
        diagnosis_date TEXT NOT NULL,
        ISS_stage TEXT NOT NULL,
        treatment_line INTEGER NOT NULL,
        therapy_class TEXT NOT NULL,
        response TEXT NOT NULL,
        progression_free_survival_months REAL NOT NULL,
        overall_survival_months REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS genomics (
        patient_id TEXT NOT NULL,
        mutation_gene TEXT NOT NULL,
        mutation_type TEXT NOT NULL,
        variant_allele_frequency REAL NOT NULL,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transcriptomics (
        patient_id TEXT NOT NULL,
        gene TEXT NOT NULL,
        expression_value REAL NOT NULL,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clinical_labs (
        patient_id TEXT PRIMARY KEY,
        albumin REAL NOT NULL,
        beta2_microglobulin REAL NOT NULL,
        hemoglobin REAL NOT NULL,
        creatinine REAL NOT NULL,
        calcium REAL NOT NULL,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_genomics_gene ON genomics(mutation_gene)",
    "CREATE INDEX IF NOT EXISTS idx_genomics_patient ON genomics(patient_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_gene ON transcriptomics(gene)",
    "CREATE INDEX IF NOT EXISTS idx_tx_patient ON transcriptomics(patient_id)",
]


TABLE_DESCRIPTIONS: dict[str, str] = {
    "patients": (
        "One row per synthetic patient. Carries demographics, ISS stage, "
        "treatment line/class, response category, and survival outcomes "
        "(PFS and OS in months)."
    ),
    "genomics": (
        "Long-format mutation calls. One row per (patient, mutated gene) "
        "with mutation type and variant allele frequency."
    ),
    "transcriptomics": (
        "Long-format bulk RNA-seq panel. One row per (patient, gene) on a "
        "log2(TPM+1)-like scale. Synthetic, not real expression data."
    ),
    "clinical_labs": (
        "Standard clinical chemistry at diagnosis: albumin, beta-2 "
        "microglobulin, hemoglobin, creatinine, calcium."
    ),
}
