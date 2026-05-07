"""Lightweight statistical helpers used by the visualization layer.

We deliberately avoid pulling in ``lifelines`` so the prototype stays
small. The Kaplan-Meier-like estimator below treats every event as
observed (no censoring) and is intended for visual storytelling on
synthetic data, NOT for clinical inference.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def kaplan_meier_like(
    durations: np.ndarray | pd.Series, events: np.ndarray | pd.Series | None = None
) -> pd.DataFrame:
    """Compute a step survival function S(t) on synthetic durations.

    If ``events`` is None, every duration is treated as an event (i.e. no
    right-censoring). This is appropriate for the synthetic dataset where
    all patients have observed PFS/OS.

    Returns a DataFrame with columns: ``time``, ``at_risk``, ``events``,
    ``survival``.
    """
    times = np.asarray(durations, dtype=float)
    if events is None:
        events_arr = np.ones_like(times, dtype=int)
    else:
        events_arr = np.asarray(events, dtype=int)

    order = np.argsort(times)
    times_sorted = times[order]
    events_sorted = events_arr[order]

    rows = []
    n_at_risk = len(times_sorted)
    survival = 1.0
    rows.append({"time": 0.0, "at_risk": n_at_risk, "events": 0, "survival": 1.0})

    unique_times = np.unique(times_sorted)
    for t in unique_times:
        mask = times_sorted == t
        d = int(events_sorted[mask].sum())
        if n_at_risk <= 0:
            break
        if d > 0:
            survival *= 1.0 - d / n_at_risk
        rows.append(
            {
                "time": float(t),
                "at_risk": int(n_at_risk),
                "events": d,
                "survival": float(survival),
            }
        )
        n_at_risk -= int(mask.sum())

    return pd.DataFrame(rows)


def proportion_difference_p_value(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-proportion z-test; returns a two-sided p-value.

    Used for response-rate comparisons in the AI-style summary. Falls back
    to 1.0 (no signal) if either sample is empty.
    """
    if n1 == 0 or n2 == 0:
        return 1.0
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    # Two-sided p-value via standard normal CDF approximation.
    from math import erf, sqrt

    p = 2.0 * (1.0 - 0.5 * (1.0 + erf(abs(z) / sqrt(2))))
    return float(p)
