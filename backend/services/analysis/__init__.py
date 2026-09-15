"""
Analysis package initialization.
Registers all built-in analysis strategies with the strategy registry.
"""
from services.analysis.base import (
    BaseAnalysis,
    get_strategy,
    list_strategies,
    register_strategy,
)
from services.analysis.sales_analysis import SalesAnalysis
from services.analysis.trend_analysis import TrendAnalysis
from services.analysis.comparison import ComparisonAnalysis
from services.analysis.summary_stats import SummaryStatsAnalysis
from services.analysis.outlier_detection import OutlierDetectionAnalysis

# Register default strategies
register_strategy(SalesAnalysis())
register_strategy(TrendAnalysis())
register_strategy(ComparisonAnalysis())
register_strategy(SummaryStatsAnalysis())
register_strategy(OutlierDetectionAnalysis())

__all__ = [
    "BaseAnalysis",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "SalesAnalysis",
    "TrendAnalysis",
    "ComparisonAnalysis",
    "SummaryStatsAnalysis",
    "OutlierDetectionAnalysis",
]
