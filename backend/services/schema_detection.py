"""
Schema detection and semantic inference engine for GeniusDataManager.
Analyzes DataFrames to infer technical dtypes, statistical metrics, and semantic tags.
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from dateutil import parser as date_parser

from models.schemas import ColumnSchema, SchemaResponse


def is_convertible_to_datetime(series: pd.Series, sample_size: int = 50) -> bool:
    """
    Check if a series of strings or objects can reasonably be parsed as datetimes.
    """
    valid_samples = series.dropna().head(sample_size)
    if len(valid_samples) == 0:
        return False

    success_count = 0
    for val in valid_samples:
        val_str = str(val).strip()
        # Exclude purely short numbers (like '1', '25', '2023' alone) unless clearly formatted
        if len(val_str) < 6:
            continue
        try:
            date_parser.parse(val_str, fuzzy=False)
            success_count += 1
        except (ValueError, OverflowError, TypeError):
            continue

    return (success_count / len(valid_samples)) >= 0.75


def is_convertible_to_numeric(series: pd.Series, sample_size: int = 50) -> Tuple[bool, str]:
    """
    Check if an object series contains numeric values (e.g. formatted with currency symbols or commas).
    Returns (is_numeric, 'int' | 'float').
    """
    valid_samples = series.dropna().head(sample_size)
    if len(valid_samples) == 0:
        return False, "string"

    has_float = False
    success_count = 0
    clean_regex = re.compile(r"[\$,€£¥%\s,]")

    for val in valid_samples:
        cleaned = clean_regex.sub("", str(val).strip())
        if not cleaned:
            continue
        try:
            num = float(cleaned)
            success_count += 1
            if "." in cleaned or not num.is_integer():
                has_float = True
        except ValueError:
            continue

    if (success_count / len(valid_samples)) >= 0.8:
        return True, "float" if has_float else "int"
    return False, "string"


def infer_column_dtype(series: pd.Series) -> str:
    """
    Infer canonical dtype: 'int' | 'float' | 'string' | 'datetime' | 'boolean'
    """
    # 1. Native boolean
    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    # 2. Native datetime
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    # 3. Native integer
    if pd.api.types.is_integer_dtype(series):
        return "int"

    # 4. Native float
    if pd.api.types.is_float_dtype(series):
        # Check if all non-null floats are actually whole numbers
        non_null = series.dropna()
        if len(non_null) > 0 and (non_null % 1 == 0).all():
            return "int"
        return "float"

    # 5. Object or string checks
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        non_null = series.dropna()
        if len(non_null) == 0:
            return "string"

        # Check boolean strings
        bool_set = {"true", "false", "yes", "no", "y", "n", "t", "f", "1", "0"}
        lower_vals = [str(x).strip().lower() for x in non_null.head(30)]
        if len(lower_vals) > 0 and all(x in bool_set for x in lower_vals):
            # If all are 1 and 0, could be int or bool, if names or others suggest
            if set(lower_vals).issubset({"true", "false", "yes", "no"}):
                return "boolean"

        # Check numeric with symbols
        is_num, num_type = is_convertible_to_numeric(series)
        if is_num:
            return num_type

        # Check datetime strings
        if is_convertible_to_datetime(series):
            return "datetime"

    return "string"


def sniff_semantic_label(col_name: str, dtype: str, series: pd.Series) -> str:
    """
    Determine a best-guess semantic label based on column name and sample values:
    'date' | 'currency' | 'quantity' | 'id' | 'percentage' | 'geo' | 'category' | 'name' | 'status' | 'text'
    """
    name_clean = col_name.strip().lower()
    non_null = series.dropna()
    total_valid = len(non_null)

    # 1. Date / Time
    if dtype == "datetime" or any(k in name_clean for k in ["date", "time", "timestamp", "created_at", "updated_at", "day", "month", "year", "quarter"]):
        return "date"

    # 2. Currency / Revenue / Price / Amount
    currency_keywords = ["price", "amount", "revenue", "cost", "salary", "fee", "balance", "budget", "total", "subtotal", "tax", "discount"]
    if any(k in name_clean for k in currency_keywords):
        return "currency"
    # Check for currency symbols in sample string values
    if dtype in ("string", "float", "int") and total_valid > 0:
        sample_strs = [str(x) for x in non_null.head(20)]
        if any(any(sym in s for sym in ["$", "€", "£", "¥"]) for s in sample_strs):
            return "currency"

    # 3. Percentage / Rate / Ratio
    pct_keywords = ["pct", "percent", "percentage", "rate", "ratio", "margin", "growth"]
    if any(k in name_clean for k in pct_keywords):
        return "percentage"
    if dtype in ("string", "float") and total_valid > 0:
        if any("%" in str(x) for x in non_null.head(20)):
            return "percentage"

    # 4. Quantity / Count / Units
    qty_keywords = ["qty", "quantity", "units", "count", "volume", "num_", "number_of"]
    if dtype == "int" and any(k in name_clean for k in qty_keywords):
        return "quantity"

    # 5. Identifier / Code / SKU
    id_keywords = ["id", "sku", "code", "uuid", "guid", "key", "number", "no", "reference", "ref"]
    if any(name_clean == k or name_clean.endswith(f"_{k}") or name_clean.startswith(f"{k}_") for k in id_keywords):
        return "id"

    # 6. Geography / Region
    geo_keywords = ["region", "country", "state", "city", "zip", "postal", "province", "territory", "address"]
    if any(k in name_clean for k in geo_keywords):
        return "geo"

    # 7. Status / State / Stage
    if any(k in name_clean for k in ["status", "state", "stage", "flag", "active"]):
        return "status"

    # 8. Person / Product / Entity Name
    name_keywords = ["product", "item", "customer", "client", "employee", "vendor", "user", "name", "title"]
    if any(k in name_clean for k in name_keywords):
        return "name"

    # 9. Low cardinality category
    if dtype == "string" and total_valid > 0:
        unique_ratio = series.nunique() / total_valid
        if unique_ratio <= 0.2 or series.nunique() <= 15:
            return "category"

    # Defaults based on dtype
    if dtype in ("int", "float"):
        return "numeric"
    if dtype == "boolean":
        return "boolean"

    return "text"


def json_safe_value(val: Any) -> Any:
    """
    Ensure value is JSON serializable (converts NaNs, NaTs, Timestamps, numpy types).
    """
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    return str(val)


def analyze_column(col_name: str, series: pd.Series) -> ColumnSchema:
    """
    Compute comprehensive column schema including dtype, stats, and semantic label.
    """
    total_len = len(series)
    null_count = int(series.isna().sum())
    null_pct = round((null_count / total_len * 100.0) if total_len > 0 else 0.0, 2)
    unique_count = int(series.nunique(dropna=True))

    # Sample non-null values
    non_null_series = series.dropna()
    samples = [json_safe_value(x) for x in non_null_series.head(5).tolist()]

    # Infer dtype
    inferred_dtype = infer_column_dtype(series)

    # Min/Max computation
    min_val = None
    max_val = None
    if inferred_dtype in ("int", "float"):
        try:
            numeric_series = pd.to_numeric(
                non_null_series.astype(str).str.replace(r"[\$,€£¥%\s,]", "", regex=True),
                errors="coerce"
            ).dropna()
            if not numeric_series.empty:
                min_val = json_safe_value(numeric_series.min())
                max_val = json_safe_value(numeric_series.max())
        except Exception:
            pass
    elif inferred_dtype == "datetime":
        try:
            date_series = pd.to_datetime(non_null_series, errors="coerce").dropna()
            if not date_series.empty:
                min_val = str(date_series.min())
                max_val = str(date_series.max())
        except Exception:
            pass

    # Semantic label
    semantic_label = sniff_semantic_label(col_name, inferred_dtype, series)

    return ColumnSchema(
        name=col_name,
        dtype=inferred_dtype,
        semantic_label=semantic_label,
        null_pct=null_pct,
        unique_count=unique_count,
        sample_values=samples,
        min_val=min_val,
        max_val=max_val,
    )


def detect_schema(df: pd.DataFrame, file_id: str, filename: str, sheet_name: Optional[str] = None, preview_limit: int = 20) -> SchemaResponse:
    """
    Run full schema detection across all columns of a dataframe.
    """
    column_schemas = [analyze_column(col, df[col]) for col in df.columns]

    # Generate preview rows (JSON safe)
    preview_df = df.head(preview_limit)
    preview_records: List[Dict[str, Any]] = []
    for _, row in preview_df.iterrows():
        record = {col: json_safe_value(val) for col, val in row.items()}
        preview_records.append(record)

    return SchemaResponse(
        file_id=file_id,
        filename=filename,
        sheet_name=sheet_name,
        columns=column_schemas,
        row_count=len(df),
        column_count=len(df.columns),
        preview=preview_records,
    )
