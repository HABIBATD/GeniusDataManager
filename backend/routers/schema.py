"""
Schema Router for GeniusDataManager.
GET /api/schema/{file_id}
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db import get_db
from db_models import UploadedFile
from models.schemas import SchemaResponse
from services.parsing import parse_uploaded_file
from services.schema_detection import detect_schema
from services.storage import storage

logger = logging.getLogger("genius.router.schema")
router = APIRouter(prefix="/api", tags=["Schema"])


@router.get("/schema/{file_id}", response_model=SchemaResponse)
async def get_schema(
    file_id: str,
    sheet: Optional[str] = Query(None, description="Sheet name for Excel workbooks"),
    db: Session = Depends(get_db),
):
    """
    Returns column names, inferred dtypes, statistical metrics, semantic labels,
    and a preview of raw rows for the specified file.
    """
    record = db.query(UploadedFile).filter_by(id=file_id).first()

    raw_item = storage.get_raw_file(file_id)
    if not raw_item and not record:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    filename = raw_item[0] if raw_item else (record.filename or "unknown.csv")
    content = raw_item[1] if raw_item else None

    # If sheet is requested and differs from default cached sheet
    cache_key = f"{file_id}_{sheet}" if sheet else file_id
    df = storage.get_dataframe(cache_key)

    if df is None:
        # Fallback to base file dataframe
        df = storage.get_dataframe(file_id)

    if df is None and content:
        try:
            df, _ = parse_uploaded_file(content, filename, sheet_name=sheet)
            storage.store_dataframe(cache_key, df)
        except Exception as exc:
            logger.exception(f"Failed to parse sheet '{sheet}' for file '{filename}'")
            raise HTTPException(status_code=400, detail=f"Failed to parse sheet '{sheet}': {str(exc)}")

    if df is None:
        raise HTTPException(status_code=404, detail=f"Data for file ID '{file_id}' could not be loaded.")

    try:
        response = detect_schema(df, file_id=file_id, filename=filename, sheet_name=sheet)
        if record:
            try:
                record.schema_json = response.model_dump()
                db.commit()
            except Exception as e:
                logger.warning(f"Could not persist schema_json to DB: {e}")
        return response
    except Exception as exc:
        logger.exception(f"Schema detection failed for file_id: {file_id}")
        raise HTTPException(status_code=500, detail=f"Schema detection error: {str(exc)}")

