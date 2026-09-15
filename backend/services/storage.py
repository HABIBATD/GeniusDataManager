"""
Storage service for GeniusDataManager.
Provides abstract StorageBackend and InMemoryStorage for caching raw files,
dataframes, and analysis results.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
import pandas as pd

from models.schemas import AnalysisResult


class StorageBackend(ABC):
    @abstractmethod
    def store_raw_file(self, file_id: str, filename: str, content: bytes, sheet_names: Optional[list[str]] = None) -> None:
        pass

    @abstractmethod
    def get_raw_file(self, file_id: str) -> Optional[Tuple[str, bytes, Optional[list[str]]]]:
        pass

    @abstractmethod
    def store_dataframe(self, key: str, df: pd.DataFrame) -> None:
        pass

    @abstractmethod
    def get_dataframe(self, key: str) -> Optional[pd.DataFrame]:
        pass

    @abstractmethod
    def store_analysis_result(self, result_id: str, result: AnalysisResult, export_df: Optional[pd.DataFrame] = None) -> None:
        pass

    @abstractmethod
    def get_analysis_result(self, result_id: str) -> Optional[Tuple[AnalysisResult, Optional[pd.DataFrame]]]:
        pass


class InMemoryStorage(StorageBackend):
    def __init__(self):
        self._raw_files: Dict[str, Tuple[str, bytes, Optional[list[str]]]] = {}
        self._dataframes: Dict[str, pd.DataFrame] = {}
        self._analysis_results: Dict[str, Tuple[AnalysisResult, Optional[pd.DataFrame]]] = {}

    def store_raw_file(self, file_id: str, filename: str, content: bytes, sheet_names: Optional[list[str]] = None) -> None:
        self._raw_files[file_id] = (filename, content, sheet_names)

    def get_raw_file(self, file_id: str) -> Optional[Tuple[str, bytes, Optional[list[str]]]]:
        return self._raw_files.get(file_id)

    def store_dataframe(self, key: str, df: pd.DataFrame) -> None:
        # Store a copy to prevent mutation
        self._dataframes[key] = df.copy()

    def get_dataframe(self, key: str) -> Optional[pd.DataFrame]:
        df = self._dataframes.get(key)
        return df.copy() if df is not None else None

    def store_analysis_result(self, result_id: str, result: AnalysisResult, export_df: Optional[pd.DataFrame] = None) -> None:
        self._analysis_results[result_id] = (result, export_df.copy() if export_df is not None else None)

    def get_analysis_result(self, result_id: str) -> Optional[Tuple[AnalysisResult, Optional[pd.DataFrame]]]:
        item = self._analysis_results.get(result_id)
        if item is None:
            return None
        res, df = item
        return (res, df.copy() if df is not None else None)


# Default singleton instance for the app
storage = InMemoryStorage()
