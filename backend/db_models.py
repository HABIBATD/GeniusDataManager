"""
SQLAlchemy ORM Models for persistent database storage in GeniusDataManager.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, LargeBinary, String, Text
from database import Base


class RawFileModel(Base):
    __tablename__ = "raw_files"

    file_id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    sheet_names_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DataFrameModel(Base):
    __tablename__ = "dataframes"

    key = Column(String, primary_key=True, index=True)
    dataframe_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisResultModel(Base):
    __tablename__ = "analysis_results"

    result_id = Column(String, primary_key=True, index=True)
    analysis_type = Column(String, nullable=False)
    result_json = Column(Text, nullable=False)
    export_dataframe_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
