"""Lexicons and regex patterns used by the rule-based parser.

These tables are intentionally explicit rather than learned. A future
LLM/RAG adapter can ignore them and produce a ``ParsedQuery`` directly.
"""
from __future__ import annotations

import re
from typing import Final

# Therapy-class synonyms (lowercase keys -> canonical value used in DB).
THERAPY_SYNONYMS: Final[dict[str, str]] = {
    "proteasome inhibitor": "Proteasome Inhibitor",
    "proteasome inhibitors": "Proteasome Inhibitor",
    "bortezomib": "Proteasome Inhibitor",
    "carfilzomib": "Proteasome Inhibitor",
    "ixazomib": "Proteasome Inhibitor",
    "imid": "Immunomodulatory Drug",
    "imids": "Immunomodulatory Drug",
    "immunomodulatory": "Immunomodulatory Drug",
    "lenalidomide": "Immunomodulatory Drug",
    "pomalidomide": "Immunomodulatory Drug",
    "thalidomide": "Immunomodulatory Drug",
    "anti-cd38": "Anti-CD38 Antibody",
    "cd38": "Anti-CD38 Antibody",
    "daratumumab": "Anti-CD38 Antibody",
    "isatuximab": "Anti-CD38 Antibody",
    "transplant": "Autologous Stem Cell Transplant",
    "asct": "Autologous Stem Cell Transplant",
    "autologous": "Autologous Stem Cell Transplant",
    "bcma": "BCMA-targeted",
    "car-t": "BCMA-targeted",
    "ide-cel": "BCMA-targeted",
    "cilta-cel": "BCMA-targeted",
    "triplet": "Combination Triplet",
    "combination": "Combination Triplet",
}

ISS_PATTERN: Final[re.Pattern] = re.compile(
    r"\b(?:iss|stage)\s*(?:stage\s*)?(i{1,3}|1|2|3)\b", re.IGNORECASE
)
ROMAN_TO_STAGE: Final[dict[str, str]] = {
    "i": "I",
    "1": "I",
    "ii": "II",
    "2": "II",
    "iii": "III",
    "3": "III",
}

# Genes — the parser picks these up as uppercase tokens.
GENE_PATTERN: Final[re.Pattern] = re.compile(
    r"\b("
    r"TP53|KRAS|NRAS|BRAF|FAM46C|DIS3|TRAF3|CYLD|MYC|FGFR3|"
    r"CCND1|MAF|NSD2|ATM|RB1|IRF4|XBP1|BCMA|CD38|SLAMF7"
    r")\b"
)

LAB_KEYWORDS: Final[dict[str, str]] = {
    "beta-2 microglobulin": "beta2_microglobulin",
    "beta 2 microglobulin": "beta2_microglobulin",
    "beta2 microglobulin": "beta2_microglobulin",
    "b2m": "beta2_microglobulin",
    "albumin": "albumin",
    "hemoglobin": "hemoglobin",
    "creatinine": "creatinine",
    "calcium": "calcium",
}

# 'high'/'low' thresholds for labs (synthetic — clinically reasonable-ish).
LAB_THRESHOLDS: Final[dict[str, tuple[float, float]]] = {
    "beta2_microglobulin": (3.5, 5.5),  # (low_max, high_min)
    "albumin": (3.5, 4.0),
    "hemoglobin": (10.0, 12.0),
    "creatinine": (1.0, 1.5),
    "calcium": (8.5, 10.5),
}

AGE_PATTERN: Final[re.Pattern] = re.compile(
    r"\b(?:age|aged)\s*(?:over|under|>=|<=|>|<|above|below)?\s*(\d{2})\b",
    re.IGNORECASE,
)
AGE_OVER_PATTERN: Final[re.Pattern] = re.compile(
    r"\b(?:over|older than|>\s*=?|above)\s*(\d{2})\b", re.IGNORECASE
)
AGE_UNDER_PATTERN: Final[re.Pattern] = re.compile(
    r"\b(?:under|younger than|<\s*=?|below)\s*(\d{2})\b", re.IGNORECASE
)

RESPONDER_KEYWORDS: Final[dict[str, list[str]]] = {
    "Responder": [
        "complete response",
        "very good partial response",
        "partial response",
        "responder",
        "responders",
    ],
    "Non-Responder": [
        "stable disease",
        "progressive disease",
        "non-responder",
        "non responders",
        "non-responders",
        "nonresponder",
    ],
}

INTENT_KEYWORDS: Final[dict[str, list[str]]] = {
    "compare_groups": ["compare", "vs", "versus", "between"],
    "survival_analysis": [
        "survival",
        "kaplan",
        "kaplan-meier",
        "pfs",
        "progression-free",
        "overall survival",
        "os ",
    ],
    "mutation_frequency": [
        "mutation frequency",
        "mutated",
        "mutation rate",
        "most mutated",
        "common mutations",
    ],
    "expression_analysis": [
        "expression",
        "rna-seq",
        "transcriptomic",
        "expressed",
        "boxplot",
    ],
}
