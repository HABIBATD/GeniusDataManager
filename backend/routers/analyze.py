"""
Analysis Router for GeniusDataManager.
POST /api/analyze
"""
import logging
from fastapi import APIRouter, HTTPException

from models.schemas import AnalysisRequest, AnalysisResult
from stage4_analysis import AnalysisValidationError, get_strategy, list_strategies
from services.storage import storage

logger = logging.getLogger("genius.router.analyze")
router = APIRouter(prefix="/api", tags=["Analysis"])


@router.post("/analyze", response_model=AnalysisResult)
async def run_analysis(request: AnalysisRequest):
    """
    Executes a pluggable Stage 4 analysis strategy on an aligned dataset.
    Returns plain-language summary, KPI cards, and chart datasets.
    """
    df = storage.get_dataframe(request.aligned_id)
    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aligned dataset '{request.aligned_id}' not found. Please run alignment first.",
        )

    try:
        strategy = get_strategy(request.analysis_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{str(exc)}. Available analysis types: {list_strategies()}",
        )

    try:
        result = strategy.analyze(df, request)
    except AnalysisValidationError as val_err:
        logger.warning(f"Validation error in Stage 4 analysis: {val_err}")
        raise HTTPException(status_code=422, detail=str(val_err))
    except ValueError as val_err:
        logger.warning(f"Value error in analysis: {val_err}")
        raise HTTPException(status_code=422, detail=str(val_err))
    except Exception as exc:
        logger.exception(f"Analysis failed for '{request.analysis_type}'")
        raise HTTPException(status_code=500, detail=f"Analysis calculation error: {str(exc)}")

    # Store analysis result and underlying dataframe for export
    storage.store_analysis_result(result.result_id, result, df)
    logger.info(f"Stage 4 analysis '{request.analysis_type}' completed: result_id={result.result_id}")

    return result
