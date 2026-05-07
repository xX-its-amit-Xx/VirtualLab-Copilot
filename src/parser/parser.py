"""Rule-based natural-language → ``ParsedQuery`` translator.

The parser is deliberately heuristic. It is *good enough* to demonstrate
cohort discovery on synthetic data, but more importantly the public
entry point :func:`parse_query` provides a stable seam for plugging in
an LLM or RAG-backed parser later. To do so, set ``VLC_LLM_PROVIDER``
and implement ``llm_adapter.parse(question)`` returning a ParsedQuery.
"""
from __future__ import annotations

import re

from ..config import get_settings
from .intents import CohortFilter, Comparison, ParsedQuery, QueryIntent
from .rules import (
    AGE_OVER_PATTERN,
    AGE_UNDER_PATTERN,
    GENE_PATTERN,
    INTENT_KEYWORDS,
    ISS_PATTERN,
    LAB_KEYWORDS,
    LAB_THRESHOLDS,
    RESPONDER_KEYWORDS,
    ROMAN_TO_STAGE,
    THERAPY_SYNONYMS,
)


class RuleBasedParser:
    """Heuristic parser that extracts intent, filters, and comparisons."""

    def parse(self, question: str) -> ParsedQuery:
        q = question.strip()
        ql = q.lower()

        intent = self._detect_intent(ql)
        filters: list[CohortFilter] = []
        notes: list[str] = []
        confidence = 0.4  # baseline

        # ISS stage --------------------------------------------------------
        m = ISS_PATTERN.search(ql)
        if m:
            stage = ROMAN_TO_STAGE.get(m.group(1).lower())
            if stage:
                filters.append(
                    CohortFilter(
                        table="patients",
                        column="ISS_stage",
                        operator="=",
                        value=stage,
                        rationale=f"Detected ISS stage '{stage}' in question.",
                    )
                )
                confidence += 0.15

        # Therapy class ---------------------------------------------------
        for synonym, canonical in THERAPY_SYNONYMS.items():
            if synonym in ql:
                if not any(
                    f.column == "therapy_class" and f.value == canonical for f in filters
                ):
                    filters.append(
                        CohortFilter(
                            table="patients",
                            column="therapy_class",
                            operator="=",
                            value=canonical,
                            rationale=f"Therapy synonym '{synonym}' → '{canonical}'.",
                        )
                    )
                    confidence += 0.1
                break  # one therapy filter is plenty

        # Age -------------------------------------------------------------
        if (m := AGE_OVER_PATTERN.search(ql)):
            filters.append(
                CohortFilter(
                    table="patients",
                    column="age",
                    operator=">=",
                    value=int(m.group(1)),
                    rationale=f"'over {m.group(1)}' → age >= {m.group(1)}.",
                )
            )
            confidence += 0.05
        elif (m := AGE_UNDER_PATTERN.search(ql)):
            filters.append(
                CohortFilter(
                    table="patients",
                    column="age",
                    operator="<=",
                    value=int(m.group(1)),
                    rationale=f"'under {m.group(1)}' → age <= {m.group(1)}.",
                )
            )
            confidence += 0.05

        # Gene mutations --------------------------------------------------
        target_gene: str | None = None
        for gene in GENE_PATTERN.findall(question):
            target_gene = target_gene or gene
            if "mutation" in ql or "mutated" in ql or intent == QueryIntent.MUTATION_FREQUENCY:
                filters.append(
                    CohortFilter(
                        table="genomics",
                        column="mutation_gene",
                        operator="=",
                        value=gene,
                        rationale=f"Mutation in {gene} requested.",
                    )
                )
                confidence += 0.1

        # Clinical labs (e.g. "high beta-2 microglobulin") ----------------
        for keyword, col in LAB_KEYWORDS.items():
            if keyword in ql:
                low_max, high_min = LAB_THRESHOLDS[col]
                if re.search(rf"high\s+{re.escape(keyword)}", ql) or re.search(
                    rf"elevated\s+{re.escape(keyword)}", ql
                ):
                    filters.append(
                        CohortFilter(
                            table="clinical_labs",
                            column=col,
                            operator=">=",
                            value=high_min,
                            rationale=f"'high {keyword}' → {col} >= {high_min}.",
                        )
                    )
                    confidence += 0.1
                elif re.search(rf"low\s+{re.escape(keyword)}", ql):
                    filters.append(
                        CohortFilter(
                            table="clinical_labs",
                            column=col,
                            operator="<=",
                            value=low_max,
                            rationale=f"'low {keyword}' → {col} <= {low_max}.",
                        )
                    )
                    confidence += 0.1

        # Comparison detection -------------------------------------------
        comparison = self._detect_comparison(ql)
        if comparison is not None:
            confidence += 0.1

        confidence = min(confidence, 0.95)

        if not filters and intent == QueryIntent.DESCRIBE_COHORT:
            notes.append(
                "No specific filters detected. Falling back to cohort-wide "
                "summary across the full synthetic dataset."
            )

        return ParsedQuery(
            raw_question=q,
            intent=intent,
            filters=filters,
            comparison=comparison,
            target_gene=target_gene,
            notes=notes,
            confidence=round(confidence, 2),
        )

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _detect_intent(ql: str) -> QueryIntent:
        for intent_str, kws in INTENT_KEYWORDS.items():
            if any(kw in ql for kw in kws):
                return QueryIntent(intent_str)
        return QueryIntent.DESCRIBE_COHORT

    @staticmethod
    def _detect_comparison(ql: str) -> Comparison | None:
        # Responders vs non-responders
        if any(kw in ql for kw in ["responders", "responder"]) and (
            "non-responder" in ql
            or "non responders" in ql
            or "non-responders" in ql
            or "nonresponder" in ql
            or "vs" in ql
        ):
            return Comparison(
                column="responder_label",
                group_a="Responder",
                group_b="Non-Responder",
                metric="progression_free_survival_months",
            )
        # Sex comparisons
        if "male" in ql and "female" in ql:
            return Comparison(
                column="sex",
                group_a="Male",
                group_b="Female",
                metric="progression_free_survival_months",
            )
        # ISS stage comparisons
        if "stage i" in ql and "stage iii" in ql:
            return Comparison(
                column="ISS_stage",
                group_a="I",
                group_b="III",
                metric="overall_survival_months",
            )
        return None


# Public API -----------------------------------------------------------------


def parse_query(question: str) -> ParsedQuery:
    """Parse a natural-language question into a structured ``ParsedQuery``.

    If ``VLC_LLM_PROVIDER`` is configured, this dispatches to a future
    LLM/RAG adapter. Otherwise it uses the rule-based parser.
    """
    settings = get_settings()
    if settings.llm_provider:
        try:
            from . import llm_adapter  # type: ignore[attr-defined]

            return llm_adapter.parse(question)  # pragma: no cover
        except Exception:
            # Adapter not yet implemented — fall back to rules.
            pass
    return RuleBasedParser().parse(question)
