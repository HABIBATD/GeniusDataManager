"""
Pydantic v2 schemas for GeniusDataManager.
"""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ColumnSchema(BaseModel):
    name: str = Field(..., description="Original column name")
    dtype: str = Field(..., description="Inferred dtype: 'int' | 'float' | 'string' | 'datetime' | 'boolean'")
    semantic_label: Optional[str] = Field(None, description="Best-guess semantic label (e.g. 'date', 'currency', 'product', 'id', 'category', 'quantity')")
    null_pct: float = Field(..., description="Percentage of null/missing values (0-100)")
    unique_count: int = Field(..., description="Count of distinct non-null values")
    sample_values: List[Any] = Field(default_factory=list, description="Sample non-null values")
    min_val: Optional[Any] = Field(None, description="Minimum value if numeric or datetime")
    max_val: Optional[Any] = Field(None, description="Maximum value if numeric or datetime")


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    sheet_names: Optional[List[str]] = None
    default_sheet: Optional[str] = None
    message: str = "File uploaded successfully."


class SchemaResponse(BaseModel):
    file_id: str
    filename: str
    sheet_name: Optional[str] = None
    columns: List[ColumnSchema]
    row_count: int
    column_count: int
    preview: List[Dict[str, Any]]


class FieldMapping(BaseModel):
    source_column: str
    target_field: str
    target_type: Optional[str] = Field(None, description="'int' | 'float' | 'string' | 'datetime' | 'boolean' | 'currency'")
    keep: bool = Field(True, description="Whether to include this column in aligned dataset")


class FilterRule(BaseModel):
    column: str
    operator: str = Field(..., description="'equals' | 'not_equals' | 'contains' | 'range' | 'in_list' | 'not_null'")
    value: Any = Field(..., description="Filter value or [min, max] list for range")


class ComputedColumn(BaseModel):
    name: str
    expression: str = Field(..., description="Expression e.g. 'quantity * unit_price'")


class AlignmentConfig(BaseModel):
    file_id: str
    sheet_name: Optional[str] = None
    mappings: List[FieldMapping]
    filters: List[FilterRule] = Field(default_factory=list)
    computed_columns: List[ComputedColumn] = Field(default_factory=list)


class CoercionError(BaseModel):
    column: str
    row_index: int
    raw_value: Any
    target_type: str
    error_message: str


class AlignmentResult(BaseModel):
    aligned_id: str
    total_rows_source: int
    total_rows_aligned: int
    filtered_out_rows: int
    coercion_errors_count: int
    coercion_error_samples: List[CoercionError] = Field(default_factory=list)
    columns: List[str]
    aligned_preview: List[Dict[str, Any]]


class AnalysisRequest(BaseModel):
    aligned_id: str
    analysis_type: str = Field(
        ...,
        description="'sales_analysis' | 'trend_analysis' | 'comparison' | 'summary_stats' | 'outlier_detection'"
    )
    comparison_type: Optional[str] = Field(
        None,
        description="'period_over_period' | 'category_comparison' | 'before_after' | 'none'"
    )
    target_columns: List[str] = Field(default_factory=list, description="Primary metric or feature columns")
    category_columns: List[str] = Field(default_factory=list, description="Categorical grouping columns")
    date_column: Optional[str] = Field(None, description="Date/timestamp column for time series")
    options: Dict[str, Any] = Field(default_factory=dict, description="Strategy-specific options")


class KPICard(BaseModel):
    label: str
    value: Union[str, int, float]
    formatted: str
    change_pct: Optional[float] = None
    subtext: Optional[str] = None


class ChartSeries(BaseModel):
    name: str
    data: List[Any]
    type: Optional[str] = None  # bar, line, etc.


class ChartData(BaseModel):
    chart_type: str = Field("bar", description="'bar' | 'line' | 'pie' | 'doughnut' | 'scatter'")
    title: str
    labels: List[str] = Field(default_factory=list)
    series: List[ChartSeries] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    result_id: str
    analysis_type: str
    summary: str
    detailed_findings: List[str] = Field(default_factory=list)
    kpis: List[KPICard] = Field(default_factory=list)
    charts: List[ChartData] = Field(default_factory=list)
    table_data: Optional[List[Dict[str, Any]]] = None
    table_columns: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str
