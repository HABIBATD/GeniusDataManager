"""
Schema Router for GeniusDataManager.
GET /api/schema/{file_id}
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

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
):
    """
    Returns column names, inferred dtypes, statistical metrics, semantic labels,
    and a preview of raw rows for the specified file.
    """
    raw_item = storage.get_raw_file(file_id)
    if not raw_item:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    filename, content, sheet_names = raw_item

    # If sheet is requested and differs from default cached sheet
    cache_key = f"{file_id}_{sheet}" if sheet else file_id
    df = storage.get_dataframe(cache_key)

    if df is None:
        try:
            df, _ = parse_uploaded_file(content, filename, sheet_name=sheet)
            storage.store_dataframe(cache_key, df)
        except Exception as exc:
            logger.exception(f"Failed to parse sheet '{sheet}' for file '{filename}'")
            raise HTTPException(status_code=400, detail=f"Failed to parse sheet '{sheet}': {str(exc)}")

    try:
        response = detect_schema(df, file_id=file_id, filename=filename, sheet_name=sheet)
        return response
    except Exception as exc:
        logger.exception(f"Schema detection failed for file_id: {file_id}")
        raise HTTPException(status_code=500, detail=f"Schema detection error: {str(exc)}")
