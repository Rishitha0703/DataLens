"""
upload.py
---------
FastAPI router and processing pipeline for receiving, validating, cleaning,
and analyzing uploaded dataset files (CSV, TSV, Excel).

Pipeline:
  1. Receive uploaded file safely via FastAPI `UploadFile`.
  2. Validate file integrity & size with `validators.validate_upload()`.
  3. Load into DataFrame with `preprocessing.load_dataset()`.
  4. Validate parsed DataFrame with `validators.validate_dataframe()`.
  5. Clean data with `preprocessing.clean_dataset()`.
  6. Compute statistical metrics with `analytics.analyze()`.
  7. Generate Gemini AI insights with `ai_insights.generate_insights()`.
  8. Return complete analysis payload (and optional HTML report export).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse

import pandas as pd
from ai_insights import generate_insights, is_gemini_configured
from analytics import analyze
from preprocessing import clean_dataset, load_dataset
from validators import (
    OPENXML_EXTENSIONS,
    ValidationError,
    safe_filename,
    validate_dataframe,
    validate_upload,
)

router = APIRouter(prefix="/api", tags=["upload"])

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def process_dataset(
    file_path: Path,
    original_filename: str,
    sheet_name: str | int = 0,
    drop_duplicates: bool = True,
    impute: bool = True,
    enable_ai: bool = True,
    gemini_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Run full validation, cleaning, statistical analysis, and AI interpretation on a file path.
    """
    # Stage 1: Validate file format & safety
    file_val = validate_upload(file_path, sheet_name=sheet_name)
    if not file_val.ok:
        raise ValidationError(file_val.errors)

    resolved_sheet = file_val.resolved_sheet if file_val.resolved_sheet is not None else sheet_name

    # Stage 2: Load dataset
    try:
        df = load_dataset(file_path, sheet_name=resolved_sheet)
    except Exception as exc:
        raise ValidationError([f"Failed to load dataset: {str(exc)}"])

    # Stage 3: Validate parsed table
    df_val = validate_dataframe(df)
    if not df_val.ok:
        raise ValidationError(df_val.errors)

    combined_warnings = file_val.warnings + df_val.warnings

    # Stage 4: Clean dataset
    cleaning_result = clean_dataset(
        df=df,
        drop_duplicates=drop_duplicates,
        impute=impute,
    )

    # Stage 5: Analyze
    analysis_data = analyze(
        df=cleaning_result.df,
        cleaning_log=cleaning_result.log,
    )
    analysis_data["title"] = f"Analysis of {original_filename}"

    # Stage 6: AI Insights via Gemini
    insights_text = None
    if enable_ai:
        try:
            insights_text = generate_insights(
                analysis=analysis_data,
                api_key=gemini_api_key,
                dataset_name=original_filename,
            )
        except Exception as exc:
            insights_text = f"Notice: AI insights could not be generated ({str(exc)})."

    analysis_data["insights"] = insights_text

    return {
        "success": True,
        "filename": original_filename,
        "warnings": combined_warnings,
        "analysis": analysis_data,
        "gemini_active": is_gemini_configured(gemini_api_key) if enable_ai else False,
    }


@router.post("/upload")
async def handle_file_upload(
    file: UploadFile = File(..., description="CSV or Excel file to analyze"),
    sheet_name: str = Form("0", description="Sheet name or 0-indexed number for Excel workbooks"),
    drop_duplicates: bool = Form(True, description="Whether to drop duplicate rows"),
    impute: bool = Form(True, description="Whether to impute missing values"),
    enable_ai: bool = Form(True, description="Whether to generate Gemini AI insights"),
    gemini_api_key: str | None = Form(None, description="Optional per-request Gemini API key"),
) -> dict[str, Any]:
    """
    Primary upload endpoint: receives files, validates, cleans, calculates statistics,
    and returns full analysis with Gemini AI insights.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": ["No file was provided."]},
        )

    clean_name = safe_filename(file.filename)

    # Save to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(clean_name).suffix) as tmp_file:
        temp_path = Path(tmp_file.name)
        try:
            shutil.copyfileobj(file.file, tmp_file)
        finally:
            file.file.close()

    try:
        result = process_dataset(
            file_path=temp_path,
            original_filename=clean_name,
            sheet_name=sheet_name,
            drop_duplicates=drop_duplicates,
            impute=impute,
            enable_ai=enable_ai,
            gemini_api_key=gemini_api_key,
        )
        return result

    except ValidationError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": val_err.errors},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"errors": [f"An unexpected error occurred during processing: {str(exc)}"]},
        )
    finally:
        # Clean up temporary upload file
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@router.post("/inspect-sheets")
async def inspect_workbook_sheets(file: UploadFile = File(...)) -> dict[str, Any]:
    """Inspect an uploaded Excel file and return available sheet names for the UI dropdown."""
    clean_name = safe_filename(file.filename or "file")
    ext = Path(clean_name).suffix.lower()

    if ext not in OPENXML_EXTENSIONS and ext != ".xls":
        return {"is_excel": False, "sheets": [], "default": None}

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_path = Path(tmp_file.name)
        try:
            shutil.copyfileobj(file.file, tmp_file)
        finally:
            file.file.close()

    try:
        excel = pd.ExcelFile(tmp_path)
        sheet_names = excel.sheet_names
        return {
            "is_excel": True,
            "sheets": sheet_names,
            "default": sheet_names[0] if sheet_names else None,
            "count": len(sheet_names),
        }
    except Exception as exc:
        return {
            "is_excel": True,
            "sheets": [],
            "error": str(exc),
            "default": None,
        }
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


@router.get("/sample-data")
def get_sample_analysis(sample_type: str = "health", enable_ai: bool = True) -> dict[str, Any]:
    """
    Return a pre-computed or generated sample dataset analysis
    for quick demonstration and testing of the dashboard.
    Supports 'health' (Excel with 'Form responses 1') and 'ecommerce' (CSV).
    """
    import numpy as np
    import pandas as pd

    if sample_type == "health":
        sample_file = BASE_DIR / "sample_health_campaign.xlsx"
        if not sample_file.exists():
            np.random.seed(101)
            n = 280
            ages = np.random.randint(21, 78, size=n)
            systolic = np.round(110 + (ages - 20) * 0.45 + np.random.normal(0, 12, size=n), 1)
            cholesterol = np.round(175 + (ages - 20) * 0.65 + np.random.normal(0, 22, size=n), 1)
            bmi = np.round(np.random.normal(26.4, 4.2, size=n), 1)

            risk_cats = []
            for s, c, b in zip(systolic, cholesterol, bmi):
                if s > 140 or c > 235 or b > 31:
                    risk_cats.append("High Risk")
                elif s > 125 or c > 205 or b > 27:
                    risk_cats.append("Moderate Risk")
                else:
                    risk_cats.append("Low Risk")

            responses = np.random.choice(
                ["Attended Workshop", "Received Consultation", "Completed Digital Survey", "Declined Follow-up"],
                size=n,
                p=[0.38, 0.28, 0.24, 0.10],
            )
            dates = pd.date_range("2024-03-01", periods=n, freq="D").strftime("%Y-%m-%d")

            df = pd.DataFrame({
                "Participant ID": [f"MED-{i+1001}" for i in range(n)],
                "Age": ages,
                "Systolic BP": systolic,
                "Cholesterol (mg/dL)": cholesterol,
                "BMI": bmi,
                "Risk Category": risk_cats,
                "Campaign Outcome": responses,
                "Screening Date": dates,
                "Notes": [None] * n,
            })
            # Realistic data quality features
            df.loc[12:19, "Cholesterol (mg/dL)"] = np.nan
            df.loc[30:35, "BMI"] = np.nan
            df = pd.concat([df, df.iloc[:8]], ignore_index=True)

            with pd.ExcelWriter(sample_file, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Form responses 1", index=False)

        return process_dataset(
            file_path=sample_file,
            original_filename="Health Awareness Campaign (Responses).xlsx",
            sheet_name="Form responses 1",
            drop_duplicates=True,
            impute=True,
            enable_ai=enable_ai,
        )

    # Default ecommerce CSV
    sample_file = BASE_DIR / "sample.csv"
    if not sample_file.exists():
        np.random.seed(42)
        n = 300
        ages = np.random.randint(18, 70, size=n)
        incomes = np.round(np.random.normal(52000, 14000, size=n) + (ages - 18) * 120, 2)
        spends = np.round(incomes * 0.05 + np.random.normal(200, 80, size=n), 2)
        regions = np.random.choice(["North", "South", "East", "West"], size=n, p=[0.25, 0.25, 0.3, 0.2])
        dates = pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d")

        df = pd.DataFrame({
            "Customer ID": [f"C{i:04d}" for i in range(n)],
            "Age": ages,
            "Income": incomes,
            "Spend": spends,
            "Region": regions,
            "Signup": dates,
            "Notes": [None] * n,
        })
        df.loc[5:15, "Income"] = np.nan
        df.loc[20:25, "Region"] = np.nan
        df = pd.concat([df, df.iloc[:10]], ignore_index=True)
        df.to_csv(sample_file, index=False)

    return process_dataset(
        file_path=sample_file,
        original_filename="sample.csv",
        sheet_name=0,
        drop_duplicates=True,
        impute=True,
        enable_ai=enable_ai,
    )


@router.post("/export-report")
async def export_html_report(payload: dict[str, Any]) -> HTMLResponse:
    """
    Generate and return a standalone, self-contained HTML report with Plotly.js charts.
    """
    analysis_data = payload.get("analysis")
    if not analysis_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must include 'analysis' object.",
        )

    report_template_path = BASE_DIR / "report.html"
    if not report_template_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report template file not found.",
        )

    template_content = report_template_path.read_text(encoding="utf-8")
    json_str = json.dumps(analysis_data, ensure_ascii=False)

    # Replace the embedded <script type="application/json" id="data"> content
    import re
    updated_html = re.sub(
        r'<script type="application/json" id="data">.*?</script>',
        f'<script type="application/json" id="data">{json_str}</script>',
        template_content,
        flags=re.DOTALL,
    )

    # Also update the title tag
    title = analysis_data.get("title", "DataLens Analysis Report")
    updated_html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", updated_html)

    return HTMLResponse(
        content=updated_html,
        headers={"Content-Disposition": f'attachment; filename="datalens_report.html"'},
    )
