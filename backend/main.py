"""
GeniusDataManager — FastAPI Application Entrypoint
=================================================
Runs via start.py:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import logging
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import services & strategies (triggers strategy registrations)
import services.analysis  # noqa: F401

# Import API Routers
from routers import align, analyze, export, health, schema, upload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("genius")

app = FastAPI(
    title="GeniusDataManager API",
    description="Intelligent schema detection, user-guided data alignment, and pluggable analysis.",
    version="2.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handlers returning structured { "error": str, "detail": str }
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    detail_msg = "; ".join([f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in errors])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "ValidationError", "detail": detail_msg},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "InternalServerError", "detail": str(exc)},
    )


# Include API Routers
app.include_router(upload.router)
app.include_router(schema.router)
app.include_router(align.router)
app.include_router(analyze.router)
app.include_router(export.router)
app.include_router(health.router)


@app.get("/health")
async def root_health():
    """Direct root health check endpoint."""
    return {"status": "ok", "version": "2.1.0"}


# Mount Frontend static files
frontend_dir = backend_dir.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Mounted frontend static directory from: {frontend_dir}")
