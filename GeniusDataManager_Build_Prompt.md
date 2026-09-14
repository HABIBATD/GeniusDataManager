# GeniusDataManager — Full Build Specification & Prompt

Use this document as a prompt for an AI coding assistant (Claude Code, Cursor, etc.) to scaffold and build the application end-to-end. It's written to be pasted in as-is.

---

## 1. Project Summary

Build **GeniusDataManager**, a full-stack web application that lets a non-technical user upload a raw data file (CSV, Excel, or JSON), have the system **automatically detect its structure** (columns, data types, row counts, semantic meaning), and then let the user **configure** — through a guided UI, not code — exactly how that data should be interpreted, aligned to a target schema, filtered, compared, and analyzed (e.g. sales analysis, period comparison, trend detection). The system then produces an aligned dataset plus an analysis result the user can view and export.

The backend entrypoint already exists (`start.py`) and runs:
```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
from a `backend/` directory. Build `backend/main.py` and supporting modules to match this, and scaffold a frontend that talks to it.

---

## 2. Core User Flow

1. **Upload** — user uploads one file (`.csv`, `.xlsx`, `.xls`, `.json`).
2. **Auto-Detection** — system parses the file and returns:
   - Column names, inferred dtypes (string/number/date/boolean/currency/category)
   - Row count, missing-value % per column, sample preview (first ~20 rows)
   - A best-guess "semantic label" per column (e.g. "looks like a date", "looks like a price", "looks like a product/SKU name", "looks like a customer identifier")
3. **User Configuration (guided UI)** — user selects:
   - Which columns to keep / rename / map to target field names
   - Row filters (date ranges, value thresholds, category filters)
   - Comparison type: `period_over_period`, `category_comparison`, `before_after`, `none`
   - Analysis type: `sales_analysis`, `trend_analysis`, `summary_stats`, `outlier_detection`, `custom_aggregation`
4. **Processing** — backend aligns the raw data to the user's target schema, applies filters/type coercion, and runs the selected analysis.
5. **Results** — user sees an aligned data table, relevant chart(s), a plain-language summary of findings, and can export the result as CSV/XLSX/JSON.

---

## 3. Functional Modules to Build

### 3.1 Upload & Parsing
- Accept multipart file upload, validate extension + size limit (default cap: 50MB, configurable).
- Parse with `pandas` (`read_csv`, `read_excel`, `read_json`); handle multiple sheets in Excel (return sheet list, let user pick one).
- Store the parsed file temporarily (disk or in-memory cache) keyed by a generated `file_id`.

### 3.2 Schema Detection Engine
- Infer dtype per column (int, float, string, datetime, boolean).
- Compute per-column stats: null %, unique count, min/max (numeric/date), example values.
- Heuristic semantic tagging using column name patterns + value sniffing (e.g. column named "date"/"created_at" + parseable datetime → `date`; values with currency symbols or column name containing "price"/"amount"/"revenue" → `currency`).
- Return a `ColumnSchema[]` the frontend can render as an editable table.

### 3.3 Field Mapping / Alignment Engine
- Accept a user-defined mapping: `{ source_column: target_field_name }`, plus target type coercions.
- Apply renames, type casting (with graceful error collection for rows that fail to coerce — don't silently drop data), and column reordering.
- Support dropping unselected columns and adding computed/derived columns later (extensibility hook).

### 3.4 Filtering
- Support filter rules: `equals`, `contains`, `range` (numeric/date), `in_list`, `not_null`.
- Filters combine with AND logic (v1); design the schema so OR/grouping can be added later.

### 3.5 Analysis Engine (pluggable)
Design this as a strategy/plugin pattern so new analysis types can be added without touching core code:
- `sales_analysis`: totals, averages, top-N by category, growth rate if a date column exists.
- `trend_analysis`: time-bucketed aggregation (daily/weekly/monthly) with simple trend direction.
- `comparison`: compare two segments (e.g. two date ranges, or two category values) on chosen metric columns.
- `summary_stats`: standard descriptive stats per numeric column.
- `outlier_detection`: IQR or z-score based flagging on chosen numeric columns.

### 3.6 Export
- Export aligned data and/or analysis results as CSV, XLSX, or JSON via a download endpoint.

---

## 4. Suggested API Design

```
POST   /api/upload                 -> { file_id, sheet_names? }
GET    /api/schema/{file_id}       -> { columns: ColumnSchema[], row_count, preview: rows[] }
POST   /api/align                  -> body: AlignmentConfig -> { aligned_preview, aligned_id }
POST   /api/analyze                -> body: AnalysisRequest -> { result_id, summary, chart_data }
GET    /api/export/{result_id}?format=csv|xlsx|json -> file download
GET    /api/health                 -> { status: "ok" }
```

### Core data models (pydantic)
```python
class ColumnSchema(BaseModel):
    name: str
    dtype: str            # "int" | "float" | "string" | "datetime" | "boolean"
    semantic_label: str | None
    null_pct: float
    unique_count: int
    sample_values: list

class FieldMapping(BaseModel):
    source_column: str
    target_field: str
    target_type: str | None

class FilterRule(BaseModel):
    column: str
    operator: str          # "equals" | "contains" | "range" | "in_list" | "not_null"
    value: Any

class AlignmentConfig(BaseModel):
    file_id: str
    mappings: list[FieldMapping]
    filters: list[FilterRule] = []

class AnalysisRequest(BaseModel):
    aligned_id: str
    analysis_type: str     # "sales_analysis" | "trend_analysis" | "comparison" | "summary_stats" | "outlier_detection"
    comparison_type: str | None
    target_columns: list[str]
    options: dict = {}
```

---

## 5. Recommended Tech Stack

- **Backend**: FastAPI + Pydantic v2 + `pandas` + `openpyxl` (Excel support) — matches the existing `uvicorn main:app` entrypoint.
- **Frontend**: React + Vite + TailwindCSS, with a step-by-step wizard UI (Upload → Review Schema → Configure Mapping/Filters → Choose Analysis → Results). Use `recharts` for charts and a table library (or a simple custom table) for the data grid.
- **Storage**: Start with local temp files / in-memory dict keyed by UUID for `file_id`/`aligned_id`/`result_id`; design the storage layer behind an interface so it can later swap to S3 or a database without touching business logic.
- **CORS**: enable for the frontend's dev origin.

Suggested backend structure:
```
backend/
  main.py                # FastAPI app, routers included here
  routers/
    upload.py
    schema.py
    align.py
    analyze.py
    export.py
  services/
    parsing.py           # file parsing
    schema_detection.py  # dtype + semantic inference
    alignment.py         # mapping + filtering
    analysis/
      base.py            # strategy interface
      sales_analysis.py
      trend_analysis.py
      comparison.py
      summary_stats.py
      outlier_detection.py
    storage.py            # abstracted temp storage
  models/
    schemas.py            # pydantic models above
```

---

## 6. Non-Functional Requirements

- Handle reasonably large files without loading everything into memory blindly — use chunked reads for very large CSVs where feasible.
- Every endpoint returns structured error responses (`{ "error": str, "detail": str }`) with proper HTTP status codes — never a bare 500 with no message.
- Log key operations (upload received, alignment applied, analysis run) with enough context to debug a failed run.
- Input validation: reject unsupported file types and oversized files with a clear message before attempting to parse.

---

## 7. Edge Cases to Handle Explicitly

- Excel files with multiple sheets, or a sheet with merged header cells.
- Columns with mixed types (e.g. mostly numbers with a few text entries).
- Duplicate column names in the source file.
- Fully empty columns or rows.
- Non-English / non-ASCII column names and values.
- Dates in ambiguous formats (DD/MM/YYYY vs MM/DD/YYYY) — surface this as a question to the user rather than guessing silently when confidence is low.
- User selects an analysis type that needs a column type the data doesn't have (e.g. sales analysis with no numeric column) — return a clear validation error, not a stack trace.

---

## 8. Deliverables to Ask the AI Coding Tool For

1. Working `backend/main.py` + full router/service structure above, runnable via the existing `start.py`.
2. A `frontend/` scaffold implementing the wizard flow described in Section 2.
3. One or two sample fixture files (small CSV with sales-like data) for manual testing.
4. A `README.md` explaining setup, running the backend and frontend, and the API contract.
5. Basic tests for the schema detection and alignment logic (these are the highest-risk correctness areas).

---

## 9. Example End-to-End Scenario (for the AI to validate its build against)

A user uploads a CSV with columns `Order Date, Product, Qty, Unit Price, Region`. The system detects `Order Date` as a date, `Unit Price` as currency, `Qty` as integer, `Region`/`Product` as categorical strings. The user maps these to `date, product, quantity, unit_price, region`, filters to `region = "West"`, and selects `sales_analysis` with `comparison_type = period_over_period`. The result should show total and average revenue (`quantity * unit_price`), a month-over-month trend chart, and a plain-language summary like "Revenue grew 12% month-over-month, driven mainly by Product X."
