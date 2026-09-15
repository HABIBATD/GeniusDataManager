"""
Health Check Router for GeniusDataManager.
GET /api/health
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "GeniusDataManager API",
        "version": "2.1.0",
    }
