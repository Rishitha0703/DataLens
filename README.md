# DataLens 📊

**DataLens** is an automated dataset profiler, statistical analytics engine, interactive Plotly visualization dashboard, and Google Gemini AI insights generator.

---

## 🚀 Quick Start

### 1. Configure Gemini AI (Optional but Recommended)
Copy `.env.example` to `.env` and insert your Gemini API Key:
```bash
copy .env.example .env
```
Inside `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```
*(If no API key is set, DataLens automatically provides an automated rule-based analytical summary as a fallback.)*

### 2. Start the FastAPI Server
Run from the project folder:
```bash
python main.py
```
or with Uvicorn:
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Open the Interactive Web App
Open your browser and navigate to:
```
http://127.0.0.1:8000
```
- Drag and drop any **CSV**, **TSV**, or **Excel** (`.xlsx`, `.xls`) file.
- Or click **"Try Sample Data"** to immediately test with a generated customer dataset.
- Export standalone HTML reports or raw JSON analysis results with one click.

---

## 📁 Architecture & File Overview

| File | Description |
| :--- | :--- |
| [`main.py`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/main.py) | **Starts FastAPI server**, configures CORS, mounts static assets, serves the interactive single-page web app at `/`, and handles health/config endpoints. |
| [`upload.py`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/upload.py) | **FastAPI Router for file uploads** (`POST /api/upload`), handles file intake, coordinates validation, dataset loading, cleaning, statistical profiling, and report export. |
| [`ai_insights.py`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/ai_insights.py) | **Connects with Google Gemini** (`google-genai` SDK), parses dataset profile summaries, generates structured multi-section executive reports, and provides heuristic fallbacks. |
| [`dashboard.js`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/dashboard.js) | **Plotly.js visual representation engine**: renders KPI tiles, missing data bars, cleaning logs, summary tables, dual histogram/box plots, correlation heatmaps, categorical charts, and Markdown-styled AI insights. |
| [`preprocessing.py`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/preprocessing.py) | Reads CSV/TSV/Excel, standardizes missing placeholders, infers datatypes, drops duplicates, drops sparse columns, and performs median/mode imputation. |
| [`analytics.py`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/analytics.py) | Calculates comprehensive descriptive statistics (mean, median, mode, std, skew, kurtosis, IQR whiskers, outliers, histograms, value counts, and Pearson correlations). |
| [`validators.py`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/validators.py) | File integrity, size, magic bytes verification, zip bomb defense, sheet validation, and DataFrame quality guards. |
| [`report.html`](file:///c:/Users/bindu/OneDrive/Desktop/DataLens/report.html) | Standalone exportable HTML report template that renders interactive Plotly visualizations offline. |

---

## 🔌 API Endpoints Reference

- **`GET /`**: Interactive DataLens web application UI with drag-and-drop file upload.
- **`POST /api/upload`**: Primary file upload endpoint.
  - Accepts `multipart/form-data` with fields:
    - `file` (File, required)
    - `sheet_name` (string or integer, default `"0"`)
    - `drop_duplicates` (boolean, default `true`)
    - `impute` (boolean, default `true`)
    - `enable_ai` (boolean, default `true`)
    - `gemini_api_key` (string, optional override)
  - Returns complete analysis JSON with computed statistics and AI insights.
- **`GET /api/sample-data`**: Generates and analyzes a synthetic customer dataset.
- **`POST /api/export-report`**: Generates a downloadable standalone HTML report.
- **`GET /health`**: Health check probe (`{"status": "ok"}`).
- **`GET /api/config`**: Runtime configuration and supported extensions.
