"""Synthetic multiple-myeloma dataset generator.

The data produced here is **fully synthetic**. Distributions are loosely
informed by published multiple-myeloma cohort statistics (e.g. CoMMpass,
Kumar et al. 2017) but no real patient records are used. Output is
deterministic when a random seed is provided.

Tables generated
----------------
patients          : demographics, disease stage, treatment, outcomes
genomics          : per-patient mutations (gene, type, VAF)
transcriptomics   : per-patient bulk RNA-seq expression for a gene panel
clinical_labs     : standard clinical chemistry at diagnosis
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

# Reference vocabularies -----------------------------------------------------

SEXES = ["Male", "Female"]
RACE_ETHNICITY = [
    "White (non-Hispanic)",
    "Black or African American",
    "Hispanic or Latino",
    "Asian",
    "Other / Unknown",
]
ISS_STAGES = ["I", "II", "III"]
TREATMENT_LINES = [1, 2, 3, 4]
THERAPY_CLASSES = [
    "Proteasome Inhibitor",
    "Immunomodulatory Drug",
    "Anti-CD38 Antibody",
    "Autologous Stem Cell Transplant",
    "BCMA-targeted",
    "Combination Triplet",
]
RESPONSE_CATEGORIES = [
    "Complete Response",
    "Very Good Partial Response",
    "Partial Response",
    "Stable Disease",
    "Progressive Disease",
]
RESPONDER_LABELS = {
    "Complete Response": "Responder",
    "Very Good Partial Response": "Responder",
    "Partial Response": "Responder",
    "Stable Disease": "Non-Responder",
    "Progressive Disease": "Non-Responder",
}

# Genes commonly altered or expressed in multiple myeloma. Used for both
# the genomics table (mutation calls) and the transcriptomics table
# (synthetic bulk expression values, log2(TPM+1)-like scale).
MYELOMA_GENES = [
    "TP53",
    "KRAS",
    "NRAS",
    "BRAF",
    "FAM46C",
    "DIS3",
    "TRAF3",
    "CYLD",
    "MYC",
    "FGFR3",
    "CCND1",
    "MAF",
    "NSD2",
    "ATM",
    "RB1",
    "IRF4",
    "XBP1",
    "BCMA",
    "CD38",
    "SLAMF7",
]
MUTATION_TYPES = ["Missense", "Nonsense", "Frameshift", "Splice", "Copy Number Gain", "Copy Number Loss"]


# ---------------------------------------------------------------------------


@dataclass
class SyntheticDataset:
    """In-memory bundle of generated tables."""

    patients: pd.DataFrame
    genomics: pd.DataFrame
    transcriptomics: pd.DataFrame
    clinical_labs: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "patients": self.patients,
            "genomics": self.genomics,
            "transcriptomics": self.transcriptomics,
            "clinical_labs": self.clinical_labs,
        }


def _patient_ids(n: int) -> list[str]:
    return [f"MM-{i:05d}" for i in range(1, n + 1)]


def _generate_patients(rng: np.random.Generator, n: int) -> pd.DataFrame:
    ids = _patient_ids(n)
    age = np.clip(rng.normal(loc=66, scale=10, size=n), 30, 92).round().astype(int)
    sex = rng.choice(SEXES, size=n, p=[0.55, 0.45])
    race = rng.choice(
        RACE_ETHNICITY,
        size=n,
        p=[0.62, 0.18, 0.10, 0.06, 0.04],
    )
    # ISS stage skewed somewhat toward II/III as is typical for symptomatic MM.
    iss = rng.choice(ISS_STAGES, size=n, p=[0.30, 0.40, 0.30])
    line = rng.choice(TREATMENT_LINES, size=n, p=[0.55, 0.25, 0.13, 0.07])
    therapy = rng.choice(THERAPY_CLASSES, size=n)

    # Outcomes loosely conditioned on stage so cohorts behave intuitively.
    response = []
    pfs = np.empty(n, dtype=float)
    os_months = np.empty(n, dtype=float)
    for i, stage in enumerate(iss):
        if stage == "I":
            r = rng.choice(RESPONSE_CATEGORIES, p=[0.30, 0.30, 0.25, 0.10, 0.05])
            base_pfs = rng.normal(40, 10)
            base_os = rng.normal(80, 15)
        elif stage == "II":
            r = rng.choice(RESPONSE_CATEGORIES, p=[0.18, 0.27, 0.30, 0.15, 0.10])
            base_pfs = rng.normal(28, 9)
            base_os = rng.normal(60, 14)
        else:  # III
            r = rng.choice(RESPONSE_CATEGORIES, p=[0.10, 0.20, 0.30, 0.20, 0.20])
            base_pfs = rng.normal(18, 8)
            base_os = rng.normal(42, 13)
        # Responders get a survival benefit; non-responders are penalized.
        if RESPONDER_LABELS[r] == "Responder":
            base_pfs += rng.normal(6, 2)
            base_os += rng.normal(10, 3)
        else:
            base_pfs -= rng.normal(4, 2)
            base_os -= rng.normal(8, 3)
        response.append(r)
        pfs[i] = max(1.0, base_pfs)
        os_months[i] = max(pfs[i] + 1.0, base_os)

    # Diagnosis dates spread over the last ~5 years.
    today = date(2025, 1, 1)
    days_back = rng.integers(low=30, high=365 * 5, size=n)
    diagnosis_date = [today - timedelta(days=int(d)) for d in days_back]

    return pd.DataFrame(
        {
            "patient_id": ids,
            "age": age,
            "sex": sex,
            "race_ethnicity": race,
            "diagnosis_date": diagnosis_date,
            "ISS_stage": iss,
            "treatment_line": line,
            "therapy_class": therapy,
            "response": response,
            "progression_free_survival_months": pfs.round(2),
            "overall_survival_months": os_months.round(2),
        }
    )


def _generate_genomics(rng: np.random.Generator, patient_ids: list[str]) -> pd.DataFrame:
    """One row per (patient, mutated gene). 0-6 mutations per patient."""
    rows = []
    # Per-gene background mutation prevalence (loosely realistic).
    gene_freq = {
        "TP53": 0.10,
        "KRAS": 0.20,
        "NRAS": 0.18,
        "BRAF": 0.06,
        "FAM46C": 0.10,
        "DIS3": 0.10,
        "TRAF3": 0.08,
        "CYLD": 0.05,
        "MYC": 0.12,
        "FGFR3": 0.10,
        "CCND1": 0.15,
        "MAF": 0.05,
        "NSD2": 0.10,
        "ATM": 0.07,
        "RB1": 0.06,
    }
    for pid in patient_ids:
        for gene, p in gene_freq.items():
            if rng.random() < p:
                mtype = rng.choice(MUTATION_TYPES, p=[0.45, 0.10, 0.12, 0.08, 0.13, 0.12])
                vaf = float(np.clip(rng.beta(2, 5), 0.02, 0.98))
                rows.append(
                    {
                        "patient_id": pid,
                        "mutation_gene": gene,
                        "mutation_type": str(mtype),
                        "variant_allele_frequency": round(vaf, 3),
                    }
                )
    return pd.DataFrame(rows)


def _generate_transcriptomics(
    rng: np.random.Generator, patient_ids: list[str]
) -> pd.DataFrame:
    """Per-patient log2(TPM+1)-like values for the myeloma gene panel."""
    rows = []
    for pid in patient_ids:
        for gene in MYELOMA_GENES:
            # Mean expression depends on gene; biology-flavored but synthetic.
            mu = {
                "MYC": 8.5,
                "BCMA": 7.0,
                "CD38": 9.2,
                "SLAMF7": 7.8,
                "IRF4": 8.0,
                "XBP1": 8.2,
            }.get(gene, 5.5)
            value = float(np.clip(rng.normal(mu, 1.2), 0.0, 14.0))
            rows.append(
                {
                    "patient_id": pid,
                    "gene": gene,
                    "expression_value": round(value, 3),
                }
            )
    return pd.DataFrame(rows)


def _generate_clinical_labs(
    rng: np.random.Generator, patients: pd.DataFrame
) -> pd.DataFrame:
    """Generate clinical labs correlated with ISS stage."""
    rows = []
    for _, row in patients.iterrows():
        stage = row["ISS_stage"]
        # ISS uses albumin & beta-2 microglobulin so distributions reflect that.
        if stage == "I":
            albumin = rng.normal(4.0, 0.3)
            b2m = rng.normal(2.8, 0.5)
        elif stage == "II":
            albumin = rng.normal(3.6, 0.4)
            b2m = rng.normal(4.0, 0.8)
        else:
            albumin = rng.normal(3.1, 0.4)
            b2m = rng.normal(7.5, 2.0)
        hemoglobin = rng.normal(11.0, 1.5)
        creatinine = rng.normal(1.2, 0.5)
        calcium = rng.normal(9.6, 0.7)
        rows.append(
            {
                "patient_id": row["patient_id"],
                "albumin": round(float(np.clip(albumin, 1.5, 5.5)), 2),
                "beta2_microglobulin": round(float(np.clip(b2m, 0.5, 25.0)), 2),
                "hemoglobin": round(float(np.clip(hemoglobin, 5.0, 17.0)), 2),
                "creatinine": round(float(np.clip(creatinine, 0.4, 8.0)), 2),
                "calcium": round(float(np.clip(calcium, 7.0, 14.0)), 2),
            }
        )
    return pd.DataFrame(rows)


def generate_dataset(num_patients: int = 400, seed: int = 42) -> SyntheticDataset:
    """Generate a fully-synthetic multiple-myeloma research dataset.

    Parameters
    ----------
    num_patients:
        Number of synthetic patients to generate.
    seed:
        Seed for the numpy random generator. Same seed -> identical data.
    """
    rng = np.random.default_rng(seed)
    patients = _generate_patients(rng, num_patients)
    pids = patients["patient_id"].tolist()
    genomics = _generate_genomics(rng, pids)
    transcriptomics = _generate_transcriptomics(rng, pids)
    clinical_labs = _generate_clinical_labs(rng, patients)
    return SyntheticDataset(
        patients=patients,
        genomics=genomics,
        transcriptomics=transcriptomics,
        clinical_labs=clinical_labs,
    )
