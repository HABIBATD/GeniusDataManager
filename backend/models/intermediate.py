"""
Pydantic models for the GeniusDataManager intermediate pipeline data structures.

Every stage reads/writes these models — they are the contracts between stages.
Nothing in the pipeline uses raw dicts; all inter-stage data passes through here.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1 — Extraction primitives
# ---------------------------------------------------------------------------

class ExtractionMethod(str, Enum):
    PDFPLUMBER_TABLES = "pdfplumber_tables"
    PDFPLUMBER_TEXT   = "pdfplumber_text"
    OCR               = "ocr"
    OCR_UNAVAILABLE   = "ocr_unavailable"
    PANDAS_CSV        = "pandas_csv"
    OPENPYXL_XLSX     = "openpyxl_xlsx"
    JSON_FLATTEN      = "json_flatten"
    TEXT_DELIMITED    = "text_delimited"
    TEXT_LOG          = "text_log"
    TEXT_MARKDOWN     = "text_markdown"
    TEXT_KEY_VALUE    = "text_key_value"
    TEXT_UNSTRUCTURED = "text_unstructured"
    DOCX_TABLE        = "docx_table"
    PPTX_TABLE        = "pptx_table"
    SQLITE_TABLE      = "sqlite_table"
    XML_HTML_TABLE    = "xml_html_table"
    ARCHIVE_CONTAINED = "archive_contained"
    IMAGE_OCR         = "image_ocr"
    UNIVERSAL_SNIFFER = "universal_sniffer"


class RawCell(BaseModel):
    """One cell with its raw text value and optional bounding-box info."""
    col_index: int
    value: Any                              # str, int, float, or None
    raw_text: str = ""
    bbox: Optional[tuple[float, float, float, float]] = None  # (x0, top, x1, bottom)


class RawRow(BaseModel):
    """One extracted row with provenance metadata."""
    row_index: int                          # 0-based within its table
    source_page: Optional[int] = None      # PDF page number (1-based), None for CSV/XLSX
    source_line: Optional[int] = None      # File line / XLSX row number
    raw_text: str = ""                     # Full concatenated raw text of the row
    cells: list[RawCell] = Field(default_factory=list)


class RawTable(BaseModel):
    """One logical table extracted from a page or sheet."""
    table_index: int
    source_page: Optional[int] = None
    source_sheet: Optional[str] = None
    extraction_method: ExtractionMethod
    headers: list[str] = Field(default_factory=list)
    rows: list[RawRow] = Field(default_factory=list)
    unparsed_rows: list[dict] = Field(default_factory=list)  # rows that failed parsing


class Stage1Result(BaseModel):
    """Complete output of Stage 1 extraction."""
    filename: str
    file_type: str                          # "pdf" | "csv" | "xlsx"
    total_pages: Optional[int] = None
    tables: list[RawTable] = Field(default_factory=list)
    unparsed_rows: list[dict] = Field(default_factory=list)  # global unparsed
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 2 — Data Profile primitives
# ---------------------------------------------------------------------------

class ColumnType(str, Enum):
    IDENTIFIER  = "identifier"
    CATEGORY    = "category"
    DATE        = "date"
    CURRENCY    = "currency"
    PERCENTAGE  = "percentage"
    NUMERIC     = "numeric"
    BOOLEAN     = "boolean"
    COMPLEX     = "complex"
    FREE_TEXT   = "free_text"
    TIME_PERIOD = "time_period"   # column header represents a time period


class RowRole(str, Enum):
    DETAIL         = "detail"
    SUBTOTAL       = "subtotal"
    GRAND_TOTAL    = "grand_total"
    SECTION_HEADER = "section_header"
    UNKNOWN        = "unknown"


class ColumnProfile(BaseModel):
    """Profile of a single column."""
    col_index: int
    header: str
    inferred_type: ColumnType
    type_confidence: float              # 0.0–1.0
    type_evidence: str                  # human-readable reason for the inference
    null_count: int = 0
    unique_count: int = 0
    sample_values: list[Any] = Field(default_factory=list)
    is_computed_column: bool = False    # True if header suggests it's a pre-existing total/sum
    # For time_period columns only:
    period_label: Optional[str] = None  # Parsed label e.g. "2025-07"
    period_order: Optional[int] = None  # Sort order among time-period columns


class ComputedColumnMismatch(BaseModel):
    """A single mismatch between source file's computed column and our recomputed value."""
    row_index: int
    row_description: str                    # e.g. "Salaries" from first identifier column
    column_header: str
    source_value: Optional[float]
    recomputed_value: Optional[float]
    delta: Optional[float]
    # Explicit statement of what was summed to produce recomputed_value:
    recomputed_from: str                    # e.g. "SUM of detail rows for columns [Jul 2025..Dec 2025]"
    source_page: Optional[int] = None
    source_line: Optional[int] = None


class Anomaly(BaseModel):
    """A single detected anomaly."""
    anomaly_type: str       # "negative_in_positive_column" | "blank_run" | "ocr_corruption" | "duplicate_row"
    description: str
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    col_header: Optional[str] = None
    source_page: Optional[int] = None
    source_line: Optional[int] = None
    raw_value: Optional[str] = None


class TableProfile(BaseModel):
    """Profile of one extracted table."""
    table_index: int
    source_page: Optional[int] = None
    source_sheet: Optional[str] = None
    total_rows: int
    detail_row_count: int
    subtotal_row_count: int
    section_header_count: int
    column_profiles: list[ColumnProfile] = Field(default_factory=list)
    time_structure: Optional[dict] = None   # {"period_type": "monthly", "start": "2025-07", "end": "2026-06", "count": 12}
    grain_description: str = ""             # e.g. "one row = one GL account per month"
    has_hierarchy: bool = False
    # Row-level role assignments (parallel to RawTable.rows)
    row_roles: list[RowRole] = Field(default_factory=list)
    computed_column_mismatches: list[ComputedColumnMismatch] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)


class CompositionSummary(BaseModel):
    """Genius data composition metrics across all extracted tables."""
    health_score: float = 100.0          # 0-100 overall data quality score
    completeness_pct: float = 100.0      # % non-null cells across dataset
    total_records: int = 0
    total_features: int = 0
    executive_insights: list[str] = Field(default_factory=list)
    unified_columns: list[dict] = Field(default_factory=list)
    can_unify: bool = False
    table_relationships: list[dict] = Field(default_factory=list)


class Stage2Result(BaseModel):
    """Complete output of Stage 2 profiling."""
    table_profiles: list[TableProfile] = Field(default_factory=list)
    total_tables: int = 0
    total_detail_rows: int = 0
    total_categories: int = 0
    total_anomalies: int = 0
    total_mismatches: int = 0
    human_summary: str = ""             # The short human-readable summary shown in the UI
    warnings: list[str] = Field(default_factory=list)
    composition: Optional[CompositionSummary] = None


# ---------------------------------------------------------------------------
# Stage 3 — Layout Plan primitives
# ---------------------------------------------------------------------------

class ChartSpec(BaseModel):
    """Specification for a single chart or panel in the dashboard."""
    chart_id: str                       # unique id, e.g. "chart_0_line"
    chart_type: str                     # "line" | "bar" | "area" | "bar_horizontal" | "grouped_bar" | "kpi" | "table" | "mismatch" | "anomaly"
    title: str
    table_index: int                    # which RawTable / TableProfile this draws from
    x_col: Optional[str] = None        # header name for x-axis / category axis
    y_cols: list[str] = Field(default_factory=list)  # header names for value series
    row_filter: str = "detail"          # "detail" | "subtotal" | "all"
    notes: str = ""                     # human-readable rationale for this choice


class LayoutPlan(BaseModel):
    """Complete layout plan produced by Stage 3 rules engine."""
    task_id: str
    charts: list[ChartSpec] = Field(default_factory=list)
    drilldown_table_indices: list[int] = Field(default_factory=list)  # table indices rendered as expandable drilldown tables
    highlight_mismatches: bool = False
    highlight_anomalies: bool = False
    layout_notes: str = ""              # overall rationale for the chosen layout


# ---------------------------------------------------------------------------
# Stage 4 — Analysis Result primitives
# ---------------------------------------------------------------------------

class Stage4Result(BaseModel):
    """Output of Stage 4 Analysis."""
    result_id: str
    analysis_type: str
    summary: str
    detailed_findings: list[str] = Field(default_factory=list)
    kpis: list[dict] = Field(default_factory=list)
    charts: list[dict] = Field(default_factory=list)
    table_data: Optional[list[dict]] = None
    table_columns: Optional[list[str]] = None
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline envelope — wraps stage outputs for the API response
# ---------------------------------------------------------------------------

class PipelineResult(BaseModel):
    task_id: str
    filename: str
    status: str = "complete"            # "processing" | "complete" | "error"
    error: Optional[str] = None
    stage1: Optional[Stage1Result] = None
    stage2: Optional[Stage2Result] = None
    stage3: Optional[LayoutPlan] = None
    stage4: Optional[Stage4Result] = None
