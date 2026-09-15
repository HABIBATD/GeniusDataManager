"""
Upload Router for GeniusDataManager.
POST /api/upload
"""
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile

from models.schemas import UploadResponse
from services.parsing import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    parse_uploaded_file,
)
from services.storage import storage

logger = logging.getLogger("genius.router.upload")
router = APIRouter(prefix="/api", tags=["Upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Accepts multipart file upload, validates extension & size limit,
    extracts sheet names if Excel, stores raw content, and returns file_id.
    """
    filename = file.filename or "unknown.csv"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / (1024*1024):.1f} MB). Maximum allowed is {MAX_FILE_SIZE / (1024*1024):.0f} MB.",
        )

    file_id = str(uuid.uuid4())
    logger.info(f"Received upload: '{filename}' ({len(content):,} bytes) -> file_id: {file_id}")

    # Parse and cache default dataframe
    try:
        df, sheet_names = parse_uploaded_file(content, filename)
    except Exception as exc:
        logger.exception(f"Parsing failed for '{filename}'")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(exc)}")

    # Store raw bytes and parsed dataframe
    storage.store_raw_file(file_id, filename, content, sheet_names)
    storage.store_dataframe(file_id, df)

    default_sheet = sheet_names[0] if sheet_names else None

    return UploadResponse(
        file_id=file_id,
        filename=filename,
        sheet_names=sheet_names,
        default_sheet=default_sheet,
        message=f"File '{filename}' uploaded and parsed successfully ({len(df):,} rows).",
    )
