"""
Stage 4 — Analysis Engine: Base Strategy Interface and Registry.
================================================================
Defines the standard abstract base class and registry for pluggable analysis algorithms.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
import pandas as pd

from models.schemas import AnalysisRequest, AnalysisResult, ChartData, KPICard


class AnalysisValidationError(ValueError):
    """
    Raised when an analysis strategy cannot be executed on the input DataFrame
    due to missing required columns, wrong data types, or insufficient rows.
    """
    pass


class BaseAnalysis(ABC):
    """
    Abstract base class for all Stage 4 data analysis strategies.
    Any new analysis type can implement this interface and be registered dynamically.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name identifier (e.g. 'sales_analysis')."""
        pass

    @abstractmethod
    def run(self, df: pd.DataFrame, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute analysis on the DataFrame with optional parameters dictionary.
        Returns a serializable dictionary containing summary, kpis, charts, and findings.
        Raises AnalysisValidationError if input data is unsuitable.
        """
        pass

    def analyze(self, df: pd.DataFrame, request: AnalysisRequest) -> AnalysisResult:
        """
        Adapter method for FastAPI endpoints accepting AnalysisRequest and returning AnalysisResult.
        """
        options = {
            "target_columns": request.target_columns,
            "category_columns": request.category_columns,
            "date_column": request.date_column,
            "comparison_type": request.comparison_type,
            **(request.options or {}),
        }
        res_dict = self.run(df, options)

        # Convert KPI dicts to KPICard models
        kpis = [
            KPICard(**k) if isinstance(k, dict) else k
            for k in res_dict.get("kpis", [])
        ]
        # Convert Chart dicts to ChartData models
        charts = [
            ChartData(**c) if isinstance(c, dict) else c
            for c in res_dict.get("charts", [])
        ]

        return AnalysisResult(
            result_id=res_dict.get("result_id", ""),
            analysis_type=res_dict.get("analysis_type", self.name),
            summary=res_dict.get("summary", ""),
            detailed_findings=res_dict.get("detailed_findings", []),
            kpis=kpis,
            charts=charts,
            table_data=res_dict.get("table_data"),
            table_columns=res_dict.get("table_columns"),
            metadata=res_dict.get("metadata", {}),
        )


_STRATEGY_REGISTRY: Dict[str, BaseAnalysis] = {}


def register_strategy(strategy: BaseAnalysis) -> None:
    """Register an analysis strategy instance."""
    _STRATEGY_REGISTRY[strategy.name] = strategy


def get_strategy(name: str) -> BaseAnalysis:
    """Retrieve an analysis strategy by name or raise ValueError."""
    if name not in _STRATEGY_REGISTRY:
        available = list(_STRATEGY_REGISTRY.keys())
        raise ValueError(f"Analysis type '{name}' is not registered. Available strategies: {available}")
    return _STRATEGY_REGISTRY[name]


def list_strategies() -> List[str]:
    """Return all registered strategy names."""
    return list(_STRATEGY_REGISTRY.keys())


def clear_strategies() -> None:
    """Clear all registered strategies (primarily for testing)."""
    _STRATEGY_REGISTRY.clear()


__all__ = [
    "AnalysisValidationError",
    "BaseAnalysis",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "clear_strategies",
]
