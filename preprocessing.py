"""
preprocessing.py
----------------
Loads a dataset (CSV / Excel) and cleans it.

Covers:
  * Reading CSV and Excel with Pandas
  * Identifying numerical and categorical columns
  * Missing value detection
  * Duplicate detection
  * Cleaning: tidy names, fix types, drop duplicates, handle missing values

Everything the cleaner does is written to a `log` dict, so the analytics
module, the report and (later) the AI step can all see what was changed.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}

# Text values that really mean "missing"
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "nil", "-", "--", "?", "missing"}


# --------------------------------------------------------------------------- #
# 1. Loading
# --------------------------------------------------------------------------- #
def load_dataset(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    """Read a CSV/TSV or Excel file into a DataFrame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()

    if ext in CSV_EXTENSIONS:
        sep = "\t" if ext == ".tsv" else None  # None -> let pandas sniff the delimiter
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(path, sep=sep, engine="python", encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Could not decode {path.name} with utf-8 or latin-1.")

    if ext in EXCEL_EXTENSIONS:
        # needs `openpyxl` for .xlsx/.xlsm and `xlrd` for .xls
        return pd.read_excel(path, sheet_name=sheet_name)

    raise ValueError(
        f"Unsupported file type '{ext}'. Use one of: "
        f"{sorted(CSV_EXTENSIONS | EXCEL_EXTENSIONS)}"
    )


# --------------------------------------------------------------------------- #
# 2. Inspection helpers (these don't change the data)
# --------------------------------------------------------------------------- #
def identify_column_types(df: pd.DataFrame) -> dict[str, list[str]]:
    """Split columns into numerical, categorical and datetime."""
    numeric = df.select_dtypes(include="number").columns.tolist()
    datetime = df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    categorical = [c for c in df.columns if c not in numeric and c not in datetime]
    return {"numerical": numeric, "categorical": categorical, "datetime": datetime}


def detect_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Missing-value count and percentage for every column (sorted, worst first)."""
    count = df.isna().sum()
    pct = (count / len(df) * 100).round(2) if len(df) else count * 0.0
    out = pd.DataFrame({"column": df.columns, "missing": count.values, "missing_pct": pct.values})
    return out.sort_values("missing", ascending=False).reset_index(drop=True)


def detect_duplicates(df: pd.DataFrame) -> dict[str, Any]:
    """Count fully duplicated rows (every occurrence after the first)."""
    mask = df.duplicated(keep="first")
    return {
        "count": int(mask.sum()),
        "pct": round(float(mask.mean() * 100), 2) if len(df) else 0.0,
        "row_indices": df.index[mask].tolist()[:100],  # preview only
    }


# --------------------------------------------------------------------------- #
# 3. Cleaning
# --------------------------------------------------------------------------- #
@dataclass
class CleaningResult:
    df: pd.DataFrame
    log: dict[str, Any]


def _tidy_column_names(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Strip spaces, collapse whitespace and make names unique."""
    renamed: dict[str, str] = {}
    seen: dict[str, int] = {}
    new_cols = []
    for col in df.columns:
        name = re.sub(r"\s+", " ", str(col)).strip() or "unnamed"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        if name != col:
            renamed[str(col)] = name
        new_cols.append(name)
    df = df.copy()
    df.columns = new_cols
    return df, renamed


def _standardise_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Trim text and turn placeholders like 'N/A' or '' into real NaN."""
    df = df.copy()
    for col in df.select_dtypes(include=["object", "string"]).columns:
        s = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        is_token = s.map(lambda v: isinstance(v, str) and v.lower() in MISSING_TOKENS)
        df[col] = s.mask(is_token, np.nan)
    return df


def _infer_types(df: pd.DataFrame, threshold: float = 0.9) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Text columns that are really numbers or dates get converted.
    A column is converted when at least `threshold` of its non-null values parse.
    """
    df = df.copy()
    converted: dict[str, str] = {}

    for col in df.select_dtypes(include=["object", "string"]).columns:
        s = df[col]
        non_null = s.dropna()
        if non_null.empty:
            continue
        as_text = non_null.astype(str)

        # numeric? (handles "1,200", "$45", "12%")
        stripped = as_text.str.replace(r"[,$€£₹%\s]", "", regex=True)
        parsed = pd.to_numeric(stripped, errors="coerce")
        if parsed.notna().mean() >= threshold:
            df[col] = pd.to_numeric(
                s.astype("string").str.replace(r"[,$€£₹%\s]", "", regex=True), errors="coerce"
            ).astype(float)
            converted[col] = "numeric"
            continue

        # datetime? only try when most values contain a digit (avoids "May" -> date)
        if as_text.str.contains(r"\d").mean() >= threshold:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    dt = pd.to_datetime(s, errors="coerce", format="mixed")
                except (TypeError, ValueError):  # older pandas
                    dt = pd.to_datetime(s, errors="coerce")
            if dt.notna().sum() / len(non_null) >= threshold:
                df[col] = dt
                converted[col] = "datetime"

    return df, converted


def clean_dataset(
    df: pd.DataFrame,
    drop_duplicates: bool = True,
    missing_col_threshold: float = 0.6,
    impute: bool = True,
) -> CleaningResult:
    """
    Run the full cleaning pipeline and return the cleaned frame plus a log.

    Steps
    -----
    1. Tidy column names
    2. Trim text, convert 'N/A'-style placeholders to NaN
    3. Convert text columns that are really numbers / dates
    4. Record missing values and duplicates (before touching them)
    5. Drop empty rows and duplicate rows
    6. Drop columns that are mostly empty (> missing_col_threshold)
    7. Impute: median for numbers, mode for categories (dates left as-is)
    """
    log: dict[str, Any] = {"original_shape": list(df.shape)}

    df, renamed = _tidy_column_names(df)
    log["renamed_columns"] = renamed

    df = _standardise_missing(df)
    df, converted = _infer_types(df)
    log["converted_types"] = converted

    # ---- detection (before any removal) ----
    log["column_types_before"] = identify_column_types(df)
    log["missing_before"] = detect_missing(df).to_dict(orient="records")
    dup_info = detect_duplicates(df)
    log["duplicates_found"] = dup_info["count"]

    # ---- rows ----
    before = len(df)
    df = df.dropna(how="all")
    log["empty_rows_removed"] = before - len(df)

    if drop_duplicates:
        before = len(df)
        df = df.drop_duplicates(keep="first")
        log["duplicates_removed"] = before - len(df)
    else:
        log["duplicates_removed"] = 0
    df = df.reset_index(drop=True)

    # ---- columns ----
    if len(df):
        sparse = [c for c in df.columns if df[c].isna().mean() > missing_col_threshold]
    else:
        sparse = []
    df = df.drop(columns=sparse)
    log["dropped_columns"] = sparse

    # ---- imputation ----
    imputed: list[dict[str, Any]] = []
    if impute:
        types = identify_column_types(df)
        for col in types["numerical"]:
            n_missing = int(df[col].isna().sum())
            if n_missing:
                fill = df[col].median()
                df[col] = df[col].fillna(fill)
                imputed.append({"column": col, "strategy": "median", "value": float(fill), "count": n_missing})
        for col in types["categorical"]:
            n_missing = int(df[col].isna().sum())
            if n_missing:
                modes = df[col].mode()
                fill = modes.iloc[0] if not modes.empty else "Unknown"
                df[col] = df[col].fillna(fill)
                imputed.append({"column": col, "strategy": "mode", "value": str(fill), "count": n_missing})
    log["imputed"] = imputed

    log["final_shape"] = list(df.shape)
    return CleaningResult(df=df, log=log)
