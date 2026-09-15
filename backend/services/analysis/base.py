"""
Base strategy interface and registry for GeniusDataManager analysis engine.
"""
from abc import ABC, abstractmethod
from typing import Dict, Type
import pandas as pd

from models.schemas import AnalysisRequest, AnalysisResult


class BaseAnalysis(ABC):
    """
    Abstract strategy class for pluggable data analysis algorithms.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name identifier (e.g. 'sales_analysis')."""
        pass

    @abstractmethod
    def analyze(self, df: pd.DataFrame, request: AnalysisRequest) -> AnalysisResult:
        """
        Execute analysis on the aligned DataFrame and return an AnalysisResult
        with plain-language summary, KPI cards, and charts.
        """
        pass


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


def list_strategies() -> list[str]:
    """Return all registered strategy names."""
    return list(_STRATEGY_REGISTRY.keys())
