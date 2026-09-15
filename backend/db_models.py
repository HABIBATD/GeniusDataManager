"""
SQLAlchemy ORM Models for persistent database storage in GeniusDataManager.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, LargeBinary, String, Text, JSON
from db import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=True)
    filepath = Column(String, nullable=True)          # raw file stays on disk, path stored here
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    schema_json = Column(JSON, nullable=True)

    @property
    def file_id(self):
        return self.id

    @file_id.setter
    def file_id(self, val):
        self.id = val


class AlignmentResult(Base):
    __tablename__ = "alignment_results"

    id = Column(String, primary_key=True, index=True)
    file_id = Column(String, nullable=True)
    mapping_json = Column(JSON, nullable=True)
    filters_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(String, primary_key=True, index=True)
    aligned_id = Column(String, nullable=True)
    analysis_type = Column(String, nullable=True)
    result_json = Column(JSON, nullable=True)
    export_dataframe_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def result_id(self):
        return self.id

    @result_id.setter
    def result_id(self, val):
        self.id = val


# Legacy / direct storage models for binary cache & dataframes
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


# Alias for AnalysisResultModel
AnalysisResultModel = AnalysisResult
