"""
Base strategy interface and registry alias for GeniusDataManager analysis engine.
Delegates to stage4_analysis.base.
"""
from stage4_analysis.base import (
    AnalysisValidationError,
    BaseAnalysis,
    clear_strategies,
    get_strategy,
    list_strategies,
    register_strategy,
)

__all__ = [
    "AnalysisValidationError",
    "BaseAnalysis",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "clear_strategies",
]
