"""
Stage 4 — Analysis Module Initialization.
========================================
Registers all built-in analysis strategies:
- SalesAnalysis
- TrendAnalysis
- ComparisonAnalysis
- SummaryStatsAnalysis
- OutlierDetectionAnalysis
"""
from stage4_analysis.base import (
    AnalysisValidationError,
    BaseAnalysis,
    clear_strategies,
    get_strategy,
    list_strategies,
    register_strategy,
)
from stage4_analysis.sales_analysis import SalesAnalysis
from stage4_analysis.trend_analysis import TrendAnalysis
from stage4_analysis.comparison import ComparisonAnalysis
from stage4_analysis.summary_stats import SummaryStatsAnalysis
from stage4_analysis.outlier_detection import OutlierDetectionAnalysis

# Register default built-in strategies
register_strategy(SalesAnalysis())
register_strategy(TrendAnalysis())
register_strategy(ComparisonAnalysis())
register_strategy(SummaryStatsAnalysis())
register_strategy(OutlierDetectionAnalysis())

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
