"""
analytics.py
------------
Statistical analysis of a cleaned DataFrame.

Covers:
  * DataFrame operations (select, group, describe, value_counts, corr)
  * Mean, median, mode, standard deviation (+ quartiles, skew, outliers)
  * Frequency distributions (histogram bins for numbers, value counts for categories)
  * Correlation matrix and strongest pairs

`analyze()` returns one JSON-serialisable dict. The report (Plotly.js) and the
future AI step both consume that same dict.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from preprocessing import detect_missing, identify_column_types

MAX_HIST_BINS = 40


# --------------------------------------------------------------------------- #
# JSON safety: numpy / pandas types -> plain Python, NaN -> None
# --------------------------------------------------------------------------- #
def to_native(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_native(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [to_native(v) for v in obj.tolist()]
    if obj is pd.NaT or obj is None:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if math.isfinite(obj) else None
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    return obj


# --------------------------------------------------------------------------- #
# Numeric columns
# --------------------------------------------------------------------------- #
def _numeric_summary(series: pd.Series) -> dict[str, Any] | None:
    s = series.dropna().astype(float)
    if s.empty:
        return None

    q1, median, q3 = s.quantile([0.25, 0.5, 0.75]).tolist()
    iqr = q3 - q1
    low_fence, high_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inliers = s[(s >= low_fence) & (s <= high_fence)]

    # Mode: only meaningful when some value actually repeats
    counts = s.value_counts()
    modes = counts[counts == counts.iloc[0]].index.sort_values().tolist()[:3] if counts.iloc[0] > 1 else []

    # Frequency distribution as histogram bins
    edges = np.histogram_bin_edges(s, bins="auto")
    if len(edges) - 1 > MAX_HIST_BINS:
        edges = np.histogram_bin_edges(s, bins=MAX_HIST_BINS)
    hist_counts, edges = np.histogram(s, bins=edges)

    return {
        "count": int(s.size),
        "mean": s.mean(),
        "median": median,
        "mode": modes,
        "std": s.std(ddof=1) if s.size > 1 else None,  # sample standard deviation
        "variance": s.var(ddof=1) if s.size > 1 else None,
        "min": s.min(),
        "q1": q1,
        "q3": q3,
        "max": s.max(),
        "skew": s.skew() if s.size > 2 else None,
        "kurtosis": s.kurt() if s.size > 3 else None,
        "outlier_count": int(s.size - inliers.size),
        "whisker_low": inliers.min() if not inliers.empty else s.min(),
        "whisker_high": inliers.max() if not inliers.empty else s.max(),
        "histogram": {"counts": hist_counts.tolist(), "edges": edges.tolist()},
    }


# --------------------------------------------------------------------------- #
# Categorical columns
# --------------------------------------------------------------------------- #
def _categorical_summary(series: pd.Series, top_n: int) -> dict[str, Any]:
    s = series.dropna().astype(str)
    total = int(s.size)
    counts = s.value_counts()
    unique = int(counts.size)

    top = counts.head(top_n)
    frequency = [
        {"value": str(v), "count": int(c), "pct": round(c / total * 100, 2)} for v, c in top.items()
    ]
    other = int(counts.iloc[top_n:].sum()) if unique > top_n else 0

    modes = counts[counts == counts.iloc[0]].index.tolist()[:3] if total else []

    return {
        "count": total,
        "unique": unique,
        "mode": modes,
        "top_frequency": frequency,
        "other_count": other,
        # Looks like an ID / free text: a frequency chart would not be useful
        "likely_identifier": bool(total > 20 and unique / total > 0.9),
    }


# --------------------------------------------------------------------------- #
# Datetime columns
# --------------------------------------------------------------------------- #
def _datetime_summary(series: pd.Series) -> dict[str, Any] | None:
    s = series.dropna()
    if s.empty:
        return None
    return {
        "count": int(s.size),
        "min": s.min(),
        "max": s.max(),
        "span_days": int((s.max() - s.min()).days),
    }


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #
def _correlation(df: pd.DataFrame, numeric_cols: list[str], top_pairs: int = 10) -> dict[str, Any]:
    # Constant columns have no defined correlation, so leave them out
    usable = [c for c in numeric_cols if df[c].nunique(dropna=True) > 1]
    if len(usable) < 2:
        return {"columns": usable, "matrix": [], "top_pairs": []}

    corr = df[usable].corr(method="pearson")

    pairs = []
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            r = corr.loc[a, b]
            if pd.notna(r):
                pairs.append({"a": a, "b": b, "r": float(r)})
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)

    for p in pairs:
        strength = abs(p["r"])
        p["strength"] = (
            "very strong" if strength >= 0.8 else
            "strong" if strength >= 0.6 else
            "moderate" if strength >= 0.4 else
            "weak"
        )
        p["direction"] = "positive" if p["r"] > 0 else "negative"

    return {"columns": usable, "matrix": corr.values.tolist(), "top_pairs": pairs[:top_pairs]}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def analyze(df: pd.DataFrame, cleaning_log: dict[str, Any] | None = None, top_n: int = 10) -> dict[str, Any]:
    """Run the full analysis on a *cleaned* DataFrame."""
    cleaning_log = cleaning_log or {}
    types = identify_column_types(df)

    numeric_stats = {}
    for col in types["numerical"]:
        summary = _numeric_summary(df[col])
        if summary:
            numeric_stats[col] = summary

    categorical_stats = {col: _categorical_summary(df[col], top_n) for col in types["categorical"]}

    datetime_stats = {}
    for col in types["datetime"]:
        summary = _datetime_summary(df[col])
        if summary:
            datetime_stats[col] = summary

    analysis = {
        "overview": {
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "numerical_columns": len(types["numerical"]),
            "categorical_columns": len(types["categorical"]),
            "datetime_columns": len(types["datetime"]),
            "memory_kb": round(float(df.memory_usage(deep=True).sum()) / 1024, 1),
            "original_rows": (cleaning_log.get("original_shape") or [df.shape[0]])[0],
            "original_columns": (cleaning_log.get("original_shape") or [0, df.shape[1]])[1],
        },
        "column_types": types,
        "data_quality": {
            "missing_before_cleaning": cleaning_log.get("missing_before", []),
            "missing_after_cleaning": detect_missing(df).to_dict(orient="records"),
            "duplicates_found": cleaning_log.get("duplicates_found", 0),
            "duplicates_removed": cleaning_log.get("duplicates_removed", 0),
            "dropped_columns": cleaning_log.get("dropped_columns", []),
            "imputed": cleaning_log.get("imputed", []),
            "converted_types": cleaning_log.get("converted_types", {}),
            "renamed_columns": cleaning_log.get("renamed_columns", {}),
        },
        "numeric_stats": numeric_stats,
        "categorical_stats": categorical_stats,
        "datetime_stats": datetime_stats,
        "correlation": _correlation(df, types["numerical"]),
    }
    return to_native(analysis)
