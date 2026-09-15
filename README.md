# GeniusDataManager

**GeniusDataManager** is a full-stack web application that allows non-technical users to upload raw data files (`.csv`, `.xlsx`, `.xls`, `.json`), automatically detect column structures and semantic types, configure guided field mappings and filter rules, run pluggable analysis strategies (sales, trend, comparison, summary statistics, outlier detection), and view interactive visualizations and executive summaries.

---

## Key Features

1. **Multi-Format Upload & Extraction**:
   - Supports CSV, TSV, Excel (`.xlsx`, `.xls`), and JSON.
   - Multi-sheet Excel workbook detection with sheet selection.
   - Automatic encoding detection (`UTF-8`, `Latin-1`, `cp1252`) via `chardet`.

2. **Automatic Schema & Semantic Detection**:
   - Infers technical dtypes (`int`, `float`, `string`, `datetime`, `boolean`).
   - Statistical profiling (null %, unique counts, min/max values).
   - Heuristic semantic tagging (`date`, `currency`, `quantity`, `id`, `category`, `geo`, `name`, `percentage`, `status`).

3. **User-Guided Alignment & Filtering Engine**:
   - Interactive column mapping, renaming, and type coercion.
   - Graceful type coercion error collection — malformed cells are logged without silently dropping data.
   - Flexible filter rule builder (`equals`, `not_equals`, `contains`, `range`, `in_list`, `not_null`) with AND logic.
   - Extensibility hook for computed/derived fields (e.g., `revenue = quantity * unit_price`).

4. **Pluggable Analysis Engine**:
   - Strategy design pattern allowing seamless addition of custom analysis algorithms behind a unified `BaseAnalysis` interface.
   - Built-in strategies:
     - `sales_analysis`: Revenue totals, average order value, top-N category breakdown, MoM growth rate.
     - `trend_analysis`: Daily/weekly/monthly time-bucketed aggregation with linear trend direction (`Upward`, `Downward`, `Stable`).
     - `comparison`: Compare segments (period-over-period or category vs category) with delta percentages.
     - `summary_stats`: Mean, median, standard deviation, quartiles, IQR, frequency distribution.
     - `outlier_detection`: Tukey's 1.5x IQR or Z-score statistical anomaly detection.

5. **Visual Dashboard & Executive Summaries**:
   - Plain-language executive summary highlighting key findings.
   - KPI cards with growth badges and context.
   - Dynamic interactive charts (Bar, Line, Doughnut) powered by Chart.js.
   - Tabular aligned data grid.

6. **Multi-Format Export Engine**:
   - Stream download as flat CSV, formatted multi-sheet Excel (`.xlsx`), or structured JSON.

---

## Project Structure

```
GeniusDataManager/
├── backend/
│   ├── main.py                  # FastAPI app entrypoint & static frontend mounting
│   ├── models/
│   │   └── schemas.py           # Pydantic v2 schemas for all payloads
│   ├── services/
│   │   ├── storage.py           # In-memory / abstracted temporary storage
│   │   ├── parsing.py           # Multi-format parsing & sheet extraction
│   │   ├── schema_detection.py  # Dtype inference & semantic tagging
│   │   ├── alignment.py         # Mapping, coercion, filtering & derivations
│   │   └── analysis/
│   │       ├── base.py          # Abstract BaseAnalysis strategy interface
│   │       ├── sales_analysis.py
│   │       ├── trend_analysis.py
│   │       ├── comparison.py
│   │       ├── summary_stats.py
│   │       └── outlier_detection.py
│   ├── routers/
│   │   ├── upload.py            # POST /api/upload
│   │   ├── schema.py            # GET /api/schema/{file_id}
│   │   ├── align.py             # POST /api/align
│   │   ├── analyze.py           # POST /api/analyze
│   │   ├── export.py            # GET /api/export/{result_id}
│   │   └── health.py            # GET /api/health
│   └── tests/
│       ├── test_parsing.py
│       ├── test_schema_detection.py
│       ├── test_alignment.py
│       ├── test_analysis.py
│       └── test_api_flow.py
├── frontend/
│   ├── index.html               # 5-step guided wizard interface
│   ├── css/
│   │   └── styles.css           # Glassmorphism dark theme & UI design system
│   └── js/
│       ├── app.js               # State machine & wizard controller
│       ├── api.js               # API client
│       └── ui_components.js     # Dynamic DOM components & Chart.js renderer
├── fixtures/
│   ├── sample_sales.csv         # Standard sales dataset fixture
│   ├── sample_quarterly.xlsx    # Multi-sheet Excel workbook fixture
│   └── sample_customers.json    # SaaS customer dataset fixture
├── start.py                     # Single entrypoint script to run application
└── README.md
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- Dependencies installed: `fastapi`, `uvicorn`, `pandas`, `openpyxl`, `chardet`, `pydantic`, `python-dateutil`

### Run the Application

Run from the root directory:
```bash
python start.py
```

This starts the backend FastAPI server and serves the full frontend web interface at:
**`http://localhost:8000`**

---

## Running Automated Tests

Run the full backend test suite covering schema detection, alignment logic, analysis strategies, and end-to-end API flows:

```bash
python -m unittest discover -s backend/tests -p "test_*.py" -v
```

---

## REST API Contract

### 1. Upload File
`POST /api/upload`
- **Body**: Multipart file form data (`file`)
- **Response**:
  ```json
  {
    "file_id": "82511093-d430-491e-9aaf-343dde5c80b8",
    "filename": "sample_sales.csv",
    "sheet_names": null,
    "default_sheet": null,
    "message": "File 'sample_sales.csv' uploaded and parsed successfully (19 rows)."
  }
  ```

### 2. Get Schema & Profile
`GET /api/schema/{file_id}?sheet={sheet_name}`
- **Response**:
  ```json
  {
    "file_id": "82511093-d430-491e-9aaf-343dde5c80b8",
    "filename": "sample_sales.csv",
    "columns": [
      {
        "name": "Order Date",
        "dtype": "datetime",
        "semantic_label": "date",
        "null_pct": 0.0,
        "unique_count": 19,
        "sample_values": ["2026-01-05", "2026-01-12"]
      }
    ],
    "row_count": 19,
    "column_count": 5,
    "preview": [...]
  }
  ```

### 3. Align Dataset
`POST /api/align`
- **Body**: `AlignmentConfig`
  ```json
  {
    "file_id": "82511093-d430-491e-9aaf-343dde5c80b8",
    "mappings": [
      {"source_column": "Order Date", "target_field": "date", "target_type": "datetime", "keep": true},
      {"source_column": "Unit Price", "target_field": "unit_price", "target_type": "float", "keep": true},
      {"source_column": "Qty", "target_field": "quantity", "target_type": "int", "keep": true},
      {"source_column": "Region", "target_field": "region", "target_type": "string", "keep": true}
    ],
    "filters": [
      {"column": "region", "operator": "equals", "value": "West"}
    ],
    "computed_columns": [
      {"name": "revenue", "expression": "quantity * unit_price"}
    ]
  }
  ```
- **Response**:
  ```json
  {
    "aligned_id": "0c78452c-97d4-427a-bbac-79d6a1ed0459",
    "total_rows_source": 19,
    "total_rows_aligned": 14,
    "filtered_out_rows": 5,
    "coercion_errors_count": 0,
    "columns": ["date", "unit_price", "quantity", "region", "revenue"],
    "aligned_preview": [...]
  }
  ```

### 4. Run Analysis Strategy
`POST /api/analyze`
- **Body**: `AnalysisRequest`
  ```json
  {
    "aligned_id": "0c78452c-97d4-427a-bbac-79d6a1ed0459",
    "analysis_type": "sales_analysis",
    "comparison_type": "period_over_period",
    "target_columns": ["revenue"],
    "category_columns": ["product"],
    "date_column": "date"
  }
  ```
- **Response**: `AnalysisResult` containing plain-language summary, KPI cards, Chart.js datasets, and table preview.

### 5. Export Results
`GET /api/export/{result_id}?format=csv|xlsx|json`
- **Response**: File download stream (`text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, or `application/json`).
