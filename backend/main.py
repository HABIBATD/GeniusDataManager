"""
GeniusDataManager — FastAPI Backend
=====================================
Phase A+B endpoints:

  POST /upload
    - Accepts multipart file (PDF, CSV, XLSX).
    - Runs Stage 1 (extraction) + Stage 2 (profiling) synchronously.
    - Returns the full PipelineResult (Stage 1 + Stage 2 JSON).

  GET /profile/{task_id}
    - Returns a previously processed PipelineResult by task_id.

  POST /layout
    - Body: {"task_id": "..."}
    - Runs Stage 3 (layout planning rules engine) on the stored Stage 2 profile.
    - Returns a LayoutPlan specifying charts + panels for the dashboard.

  GET /export/{task_id}/xlsx
  GET /export/{task_id}/pdf
  GET /export/{task_id}/csv
    - Stage 5 exports. Streams the file as a download.

  GET /health
    - Health check.

  GET /tasks
    - Lists all processed tasks (debugging).
"""

import io
import logging
import os
import sys
import uuid
from pathlib import Path

# Add the backend directory to the Python path so sub-packages work
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from models.intermediate import LayoutPlan, PipelineResult, Stage1Result, Stage2Result
from stage1_extraction.universal_extractor import extract_universal
from stage2_profiling.profiler import profile_stage1_result
from stage3_layout.layout_planner import plan_layout
from stage5_export.xlsx_exporter import export_xlsx
from stage5_export.pdf_exporter import export_pdf
from stage5_export.csv_exporter import export_csv
from stage5_export.json_exporter import export_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("genius")

app = FastAPI(
    title="GeniusDataManager API",
    description="Automatic data profiling and report generation from PDF, CSV, and XLSX files.",
    version="2.0.0-phase-b",
)

# Allow the frontend (served from the same server or localhost dev) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task store (Phase A: simple dict; Phase B: replace with Redis/DB)
_task_store: dict[str, PipelineResult] = {}

# Maximum upload size: 100 MB
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # some browsers send this for xlsx
    "text/plain",                # some browsers send this for csv
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0-phase-b"}


@app.post("/upload", response_model=PipelineResult)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file and run Stage 1 (extraction) + Stage 2 (profiling).
    Returns the full pipeline result including the data profile.
    """
    task_id = str(uuid.uuid4())

    # --- Validation ---
    filename = file.filename or "unknown"

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(file_bytes) / 1_048_576:.1f} MB). Maximum is 100 MB.",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info("Processing file: %s (%d bytes)", filename, len(file_bytes))

    # --- Stage 1: Universal Extraction ---
    try:
        stage1: Stage1Result = extract_universal(file_bytes, filename)
    except Exception as exc:
        logger.exception("Stage 1 extraction failed for %s", filename)
        result = PipelineResult(
            task_id=task_id,
            filename=filename,
            status="error",
            error=f"Stage 1 extraction error: {exc}",
        )
        _task_store[task_id] = result
        return result

    logger.info(
        "Stage 1 complete: %d table(s), %d unparsed rows, %d warnings",
        len(stage1.tables),
        len(stage1.unparsed_rows),
        len(stage1.warnings),
    )

    # --- Stage 2: Profiling ---
    try:
        stage2: Stage2Result = profile_stage1_result(stage1)
    except Exception as exc:
        logger.exception("Stage 2 profiling failed for %s", filename)
        result = PipelineResult(
            task_id=task_id,
            filename=filename,
            status="error",
            error=f"Stage 2 profiling error: {exc}",
            stage1=stage1,
        )
        _task_store[task_id] = result
        return result

    logger.info(
        "Stage 2 complete: %d anomalies, %d mismatches",
        stage2.total_anomalies,
        stage2.total_mismatches,
    )

    result = PipelineResult(
        task_id=task_id,
        filename=filename,
        status="complete",
        stage1=stage1,
        stage2=stage2,
    )
    _task_store[task_id] = result
    return result


@app.get("/profile/{task_id}", response_model=PipelineResult)
async def get_profile(task_id: str):
    """Retrieve a previously processed pipeline result by task_id."""
    result = _task_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return result


@app.get("/tasks")
async def list_tasks():
    """List all processed task IDs (for debugging)."""
    return {
        "tasks": [
            {
                "task_id": tid,
                "filename": r.filename,
                "status": r.status,
                "tables": len(r.stage1.tables) if r.stage1 else 0,
            }
            for tid, r in _task_store.items()
        ]
    }


# ---------------------------------------------------------------------------
# Stage 3 — Layout Planning
# ---------------------------------------------------------------------------

@app.post("/layout", response_model=LayoutPlan)
async def get_layout(request: Request):
    """
    Run Stage 3 (layout planning) on a previously processed pipeline result.
    Body: {"task_id": "<uuid>"}
    Returns a LayoutPlan describing what charts and panels to render.
    """
    body = await request.json()
    task_id = body.get("task_id", "")
    result = _task_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    if not result.stage2:
        raise HTTPException(
            status_code=422,
            detail="Stage 2 profiling result is missing — cannot plan layout.",
        )
    try:
        layout = plan_layout(result.stage2, task_id)
    except Exception as exc:
        logger.exception("Stage 3 layout planning failed for task %s", task_id)
        raise HTTPException(status_code=500, detail=f"Stage 3 error: {exc}")

    logger.info(
        "Stage 3 complete: %d chart(s), %d drilldown table(s)",
        len(layout.charts),
        len(layout.drilldown_table_indices),
    )
    return layout


# ---------------------------------------------------------------------------
# Stage 5 — Export
# ---------------------------------------------------------------------------

_EXPORT_FORMATS = {"xlsx", "pdf", "csv", "json"}

@app.get("/export/{task_id}/{fmt}")
async def export_file(task_id: str, fmt: str):
    """
    Stage 5: Export the pipeline result as XLSX, PDF, CSV, or JSON.
    Streams the file as a download attachment.
    """
    if fmt not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown format '{fmt}'. Supported: xlsx, pdf, csv, json.",
        )
    result = _task_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    safe_name = result.filename.rsplit(".", 1)[0][:40].replace(" ", "_")

    try:
        if fmt == "xlsx":
            data = export_xlsx(result)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"{safe_name}_genius_export.xlsx"
        elif fmt == "pdf":
            data = export_pdf(result)
            media_type = "application/pdf"
            filename = f"{safe_name}_genius_report.pdf"
        elif fmt == "json":
            data = export_json(result)
            media_type = "application/json; charset=utf-8"
            filename = f"{safe_name}_genius_data.json"
        else:  # csv
            data = export_csv(result)
            media_type = "text/csv; charset=utf-8"
            filename = f"{safe_name}_genius_flat.csv"
    except Exception as exc:
        logger.exception("Stage 5 export (%s) failed for task %s", fmt, task_id)
        raise HTTPException(status_code=500, detail=f"Export error: {exc}")

    logger.info("Stage 5 export %s for task %s: %d bytes", fmt, task_id, len(data))
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Serve frontend static files
# ---------------------------------------------------------------------------

frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
