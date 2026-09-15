"""
Analysis package initialization.
Re-exports from Stage 4 analysis engine for backward compatibility.
"""
from stage4_analysis import (
    AnalysisValidationError,
    BaseAnalysis,
    ComparisonAnalysis,
    OutlierDetectionAnalysis,
    SalesAnalysis,
    SummaryStatsAnalysis,
    TrendAnalysis,
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
    "SalesAnalysis",
    "TrendAnalysis",
    "ComparisonAnalysis",
    "SummaryStatsAnalysis",
    "OutlierDetectionAnalysis",
]
