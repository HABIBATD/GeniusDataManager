"""
Storage service for GeniusDataManager.
Provides abstract StorageBackend and SQLiteStorage for persistent DB storage
using SQLAlchemy (geniusdata.db), with in-memory caching.
"""
import io
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
import pandas as pd

from db import Base, SessionLocal, engine
from db_models import AnalysisResultModel, DataFrameModel, RawFileModel, UploadedFile
from models.schemas import AnalysisResult

logger = logging.getLogger("genius.storage")

# Create database tables if they do not exist
try:
    Base.metadata.create_all(bind=engine)
except Exception as exc:
    logger.error(f"Failed to initialize database tables: {exc}")


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


class SQLiteStorage(StorageBackend):
    def __init__(self):
        # In-memory LRU/fast cache
        self._raw_cache: Dict[str, Tuple[str, bytes, Optional[list[str]]]] = {}
        self._df_cache: Dict[str, pd.DataFrame] = {}
        self._analysis_cache: Dict[str, Tuple[AnalysisResult, Optional[pd.DataFrame]]] = {}

    def store_raw_file(self, file_id: str, filename: str, content: bytes, sheet_names: Optional[list[str]] = None) -> None:
        self._raw_cache[file_id] = (filename, content, sheet_names)

        db = SessionLocal()
        try:
            sheets_json = json.dumps(sheet_names) if sheet_names else None
            record = RawFileModel(
                file_id=file_id,
                filename=filename,
                content=content,
                sheet_names_json=sheets_json,
            )
            db.merge(record)

            uploaded_file = UploadedFile(
                id=file_id,
                filename=filename,
            )
            db.merge(uploaded_file)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to persist raw file {file_id} to DB: {exc}")
        finally:
            db.close()

    def get_raw_file(self, file_id: str) -> Optional[Tuple[str, bytes, Optional[list[str]]]]:
        if file_id in self._raw_cache:
            return self._raw_cache[file_id]

        db = SessionLocal()
        try:
            record = db.query(RawFileModel).filter(RawFileModel.file_id == file_id).first()
            if record:
                sheets = json.loads(record.sheet_names_json) if record.sheet_names_json else None
                item = (record.filename, record.content, sheets)
                self._raw_cache[file_id] = item
                return item
        except Exception as exc:
            logger.error(f"Failed to query raw file {file_id} from DB: {exc}")
        finally:
            db.close()
        return None

    def store_dataframe(self, key: str, df: pd.DataFrame) -> None:
        self._df_cache[key] = df.copy()

        db = SessionLocal()
        try:
            df_json = df.to_json(orient="split", date_format="iso")
            record = DataFrameModel(key=key, dataframe_json=df_json)
            db.merge(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to persist dataframe {key} to DB: {exc}")
        finally:
            db.close()

    def get_dataframe(self, key: str) -> Optional[pd.DataFrame]:
        if key in self._df_cache:
            return self._df_cache[key].copy()

        db = SessionLocal()
        try:
            record = db.query(DataFrameModel).filter(DataFrameModel.key == key).first()
            if record:
                df = pd.read_json(io.StringIO(record.dataframe_json), orient="split")
                self._df_cache[key] = df.copy()
                return df
        except Exception as exc:
            logger.error(f"Failed to query dataframe {key} from DB: {exc}")
        finally:
            db.close()
        return None

    def store_analysis_result(self, result_id: str, result: AnalysisResult, export_df: Optional[pd.DataFrame] = None) -> None:
        self._analysis_cache[result_id] = (result, export_df.copy() if export_df is not None else None)

        db = SessionLocal()
        try:
            res_json = result.model_dump_json()
            export_json = export_df.to_json(orient="split", date_format="iso") if export_df is not None else None
            record = AnalysisResultModel(
                id=result_id,
                analysis_type=result.analysis_type,
                result_json=res_json,
                export_dataframe_json=export_json,
            )
            db.merge(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to persist analysis result {result_id} to DB: {exc}")
        finally:
            db.close()

    def get_analysis_result(self, result_id: str) -> Optional[Tuple[AnalysisResult, Optional[pd.DataFrame]]]:
        if result_id in self._analysis_cache:
            res, df = self._analysis_cache[result_id]
            return (res, df.copy() if df is not None else None)

        db = SessionLocal()
        try:
            record = db.query(AnalysisResultModel).filter(AnalysisResultModel.id == result_id).first()
            if record:
                res_data = record.result_json
                if isinstance(res_data, str):
                    result = AnalysisResult.model_validate_json(res_data)
                elif isinstance(res_data, dict):
                    result = AnalysisResult.model_validate(res_data)
                else:
                    result = AnalysisResult.model_validate_json(str(res_data))
                export_df = pd.read_json(io.StringIO(record.export_dataframe_json), orient="split") if record.export_dataframe_json else None
                item = (result, export_df)
                self._analysis_cache[result_id] = item
                return (result, export_df.copy() if export_df is not None else None)
        except Exception as exc:
            logger.error(f"Failed to query analysis result {result_id} from DB: {exc}")
        finally:
            db.close()
        return None


# Default singleton instance for the app
storage = SQLiteStorage()
