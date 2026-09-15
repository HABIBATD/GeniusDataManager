"""
Alignment Router for GeniusDataManager.
POST /api/align
"""
import logging
from fastapi import APIRouter, HTTPException

from models.schemas import AlignmentConfig, AlignmentResult
from services.alignment import align_dataframe
from services.storage import storage

logger = logging.getLogger("genius.router.align")
router = APIRouter(prefix="/api", tags=["Alignment"])


@router.post("/align", response_model=AlignmentResult)
async def align_data(config: AlignmentConfig):
    """
    Applies user-configured column mapping, renaming, type coercion, and filters.
    Stores the aligned DataFrame and returns aligned preview and metrics.
    """
    cache_key = f"{config.file_id}_{config.sheet_name}" if config.sheet_name else config.file_id
    df_source = storage.get_dataframe(cache_key)

    if df_source is None:
        # Fallback to base file_id
        df_source = storage.get_dataframe(config.file_id)

    if df_source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source data for file_id '{config.file_id}' not found. Please upload the file first.",
        )

    try:
        df_aligned, result = align_dataframe(df_source, config)
    except Exception as exc:
        logger.exception("Alignment failed")
        raise HTTPException(status_code=422, detail=f"Alignment error: {str(exc)}")

    # Store aligned dataframe
    storage.store_dataframe(result.aligned_id, df_aligned)
    logger.info(
        f"Alignment complete: aligned_id={result.aligned_id}, "
        f"{result.total_rows_aligned:,}/{result.total_rows_source:,} rows kept."
    )

    return result
