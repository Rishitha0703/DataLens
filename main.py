"""
main.py
-------
FastAPI entrypoint for DataLens.
Starts the server, registers routers, mounts static assets, and serves
the interactive dataset analytics & AI dashboard web app.

Run with:
    python main.py
or
    uvicorn main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ai_insights import is_gemini_configured
from upload import router as upload_router
from validators import ALLOWED_EXTENSIONS, MAX_FILE_MB

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="DataLens",
    description="Automated Dataset Profiler, Plotly Visualization Engine & Gemini AI Insights",
    version="1.0.0",
)

# CORS middleware for open local collaboration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the file upload and analysis router
app.include_router(upload_router)

# Mount current directory as static files to serve dashboard.js, report.html, etc.
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "DataLens", "version": "1.0.0"}


@app.get("/api/config", tags=["system"])
def get_config() -> dict[str, object]:
    """Return runtime configuration and capability flags."""
    return {
        "gemini_configured": is_gemini_configured(),
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        "max_file_mb": MAX_FILE_MB,
        "default_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    }


@app.get("/", response_class=HTMLResponse, tags=["ui"])
def serve_index() -> HTMLResponse:
    """Serve the primary interactive DataLens web application."""
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h3>index.html not found</h3>", status_code=404)

    template = index_path.read_text(encoding="utf-8")
    gemini_ready = is_gemini_configured()
    badge_color = "#0f766e" if gemini_ready else "#b45309"
    badge_text = "Gemini AI Connected" if gemini_ready else "Gemini Key Not Set (Using Rule-based AI Fallback)"

    rendered = (
        template.replace("__BADGE_COLOR__", badge_color)
        .replace("__BADGE_TEXT__", badge_text)
        .replace("__MAX_FILE_MB__", str(MAX_FILE_MB))
    )
    return HTMLResponse(content=rendered)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
