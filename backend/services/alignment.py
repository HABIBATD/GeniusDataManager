"""
Alignment and filtering engine for GeniusDataManager.
Transforms raw DataFrames according to user-configured schemas, type coercions,
filter rules, and computed column derivations.
"""
import logging
import re
import uuid
from typing import Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from dateutil import parser as date_parser

from models.schemas import (
    AlignmentConfig,
    AlignmentResult,
    CoercionError,
    FieldMapping,
    FilterRule,
)
from services.schema_detection import json_safe_value

logger = logging.getLogger("genius.alignment")


def coerce_value(val: Any, target_type: str) -> Tuple[Any, Optional[str]]:
    """
    Coerce a single value to the target type.
    Returns (coerced_value, error_message_if_any).
    """
    if pd.isna(val) or val is None or val == "":
        return None, None

    target_type = target_type.lower()
    val_str = str(val).strip()

    try:
        if target_type == "int":
            # Remove currency/commas/spaces
            cleaned = re.sub(r"[\$,€£¥%\s,]", "", val_str)
            float_val = float(cleaned)
            return int(round(float_val)), None

        elif target_type in ("float", "currency"):
            cleaned = re.sub(r"[\$,€£¥%\s,]", "", val_str)
            return float(cleaned), None

        elif target_type == "string":
            return str(val), None

        elif target_type == "datetime":
            dt = date_parser.parse(val_str)
            return dt.strftime("%Y-%m-%d %H:%M:%S") if (dt.hour or dt.minute or dt.second) else dt.strftime("%Y-%m-%d"), None

        elif target_type == "boolean":
            lower_v = val_str.lower()
            if lower_v in ("true", "1", "yes", "y", "t"):
                return True, None
            if lower_v in ("false", "0", "no", "n", "f"):
                return False, None
            return None, f"Cannot convert '{val_str}' to boolean"

        else:
            return val, None

    except Exception as exc:
        return None, str(exc)


def apply_type_coercions(df: pd.DataFrame, mappings: List[FieldMapping]) -> Tuple[pd.DataFrame, List[CoercionError]]:
    """
    Apply target type coercions to dataframe columns, tracking any conversion errors gracefully.
    """
    coercion_errors: List[CoercionError] = []
    df_out = df.copy()

    for m in mappings:
        if not m.keep:
            continue
        col = m.target_field
        if col not in df_out.columns or not m.target_type:
            continue

        target_t = m.target_type.lower()
        new_col_vals = []

        for idx, val in enumerate(df_out[col]):
            coerced, err = coerce_value(val, target_t)
            if err:
                coercion_errors.append(
                    CoercionError(
                        column=col,
                        row_index=idx,
                        raw_value=str(val),
                        target_type=target_t,
                        error_message=err,
                    )
                )
                new_col_vals.append(None)
            else:
                new_col_vals.append(coerced)

        df_out[col] = new_col_vals

        # If int or float, convert pandas dtype with nullable support
        if target_t == "int":
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").astype("Int64")
        elif target_t in ("float", "currency"):
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").astype("Float64")
        elif target_t == "datetime":
            df_out[col] = pd.to_datetime(df_out[col], errors="coerce")

    return df_out, coercion_errors


def apply_filter_rule(df: pd.DataFrame, rule: FilterRule) -> pd.DataFrame:
    """
    Apply a single filter rule to the dataframe.
    """
    col = rule.column
    if col not in df.columns:
        logger.warning(f"Filter column '{col}' not found in dataframe. Skipping rule.")
        return df

    op = rule.operator.lower()
    val = rule.value

    if op == "not_null":
        return df[df[col].notna() & (df[col] != "")]

    if op == "equals":
        if isinstance(val, str):
            mask = df[col].astype(str).str.strip().str.lower() == str(val).strip().lower()
        else:
            mask = df[col] == val
        return df[mask]

    if op == "not_equals":
        if isinstance(val, str):
            mask = df[col].astype(str).str.strip().str.lower() != str(val).strip().lower()
        else:
            mask = df[col] != val
        return df[mask]

    if op == "contains":
        mask = df[col].astype(str).str.contains(str(val), case=False, na=False)
        return df[mask]

    if op == "range":
        # val can be [min, max] or a dict or string 'min..max'
        min_v, max_v = None, None
        if isinstance(val, (list, tuple)) and len(val) == 2:
            min_v, max_v = val[0], val[1]
        elif isinstance(val, dict):
            min_v, max_v = val.get("min"), val.get("max")
        elif isinstance(val, str) and ".." in val:
            parts = val.split("..")
            min_v, max_v = parts[0].strip(), parts[1].strip()

        mask = pd.Series(True, index=df.index)
        col_series = df[col]

        # Numeric range
        if pd.api.types.is_numeric_dtype(col_series):
            if min_v is not None and str(min_v).strip() != "":
                mask = mask & (col_series >= float(min_v))
            if max_v is not None and str(max_v).strip() != "":
                mask = mask & (col_series <= float(max_v))
        # Datetime range
        elif pd.api.types.is_datetime64_any_dtype(col_series):
            if min_v is not None and str(min_v).strip() != "":
                mask = mask & (col_series >= pd.to_datetime(min_v))
            if max_v is not None and str(max_v).strip() != "":
                mask = mask & (col_series <= pd.to_datetime(max_v))
        else:
            # String comparison
            if min_v is not None and str(min_v).strip() != "":
                mask = mask & (col_series.astype(str) >= str(min_v))
            if max_v is not None and str(max_v).strip() != "":
                mask = mask & (col_series.astype(str) <= str(max_v))

        return df[mask]

    if op == "in_list":
        if isinstance(val, str):
            allowed = [x.strip() for x in val.split(",") if x.strip()]
        elif isinstance(val, list):
            allowed = [x for x in val]
        else:
            allowed = [val]
        # Match case-insensitively if strings
        str_allowed = {str(x).strip().lower() for x in allowed}
        mask = df[col].astype(str).str.strip().str.lower().isin(str_allowed)
        return df[mask]

    return df


def apply_computed_columns(df: pd.DataFrame, config: AlignmentConfig) -> pd.DataFrame:
    """
    Extensibility hook: compute derived columns (e.g. revenue = quantity * unit_price).
    Safely evaluates simple arithmetic on numeric columns.
    """
    df_out = df.copy()
    for comp in config.computed_columns:
        expr = comp.expression.strip()
        # Parse basic multiplications, additions, subtractions, divisions between columns
        match = re.match(r"^\s*([a-zA-Z0-9_]+)\s*([\*\+\-\/])\s*([a-zA-Z0-9_]+)\s*$", expr)
        if match:
            col1, op, col2 = match.groups()
            if col1 in df_out.columns and col2 in df_out.columns:
                s1 = pd.to_numeric(df_out[col1], errors="coerce")
                s2 = pd.to_numeric(df_out[col2], errors="coerce")
                if op == "*":
                    df_out[comp.name] = s1 * s2
                elif op == "+":
                    df_out[comp.name] = s1 + s2
                elif op == "-":
                    df_out[comp.name] = s1 - s2
                elif op == "/":
                    df_out[comp.name] = s1 / s2.replace(0, np.nan)
    return df_out


def align_dataframe(df_source: pd.DataFrame, config: AlignmentConfig) -> Tuple[pd.DataFrame, AlignmentResult]:
    """
    Executes mapping, renaming, filtering, type coercion, and derivation.
    Returns (aligned_df, AlignmentResult).
    """
    total_source_rows = len(df_source)

    # 1. Column Selection & Renaming
    keep_mappings = [m for m in config.mappings if m.keep]
    rename_dict = {m.source_column: m.target_field for m in keep_mappings if m.source_column in df_source.columns}
    source_keep_cols = [m.source_column for m in keep_mappings if m.source_column in df_source.columns]

    if not source_keep_cols:
        # Fallback to all source columns if user didn't specify any
        df_aligned = df_source.copy()
    else:
        df_aligned = df_source[source_keep_cols].copy()
        df_aligned = df_aligned.rename(columns=rename_dict)

    # 2. Apply Type Coercions & track errors
    df_aligned, coercion_errors = apply_type_coercions(df_aligned, keep_mappings)

    # 3. Apply Filters
    rows_before_filter = len(df_aligned)
    for rule in config.filters:
        df_aligned = apply_filter_rule(df_aligned, rule)
    filtered_out_rows = rows_before_filter - len(df_aligned)

    # 4. Apply Computed Columns
    if config.computed_columns:
        df_aligned = apply_computed_columns(df_aligned, config)

    df_aligned = df_aligned.reset_index(drop=True)
    aligned_id = str(uuid.uuid4())

    # Build preview rows (JSON serializable)
    preview_records: List[dict] = []
    for _, row in df_aligned.head(20).iterrows():
        rec = {col: json_safe_value(val) for col, val in row.items()}
        preview_records.append(rec)

    result = AlignmentResult(
        aligned_id=aligned_id,
        total_rows_source=total_source_rows,
        total_rows_aligned=len(df_aligned),
        filtered_out_rows=filtered_out_rows,
        coercion_errors_count=len(coercion_errors),
        coercion_error_samples=coercion_errors[:10],
        columns=list(df_aligned.columns),
        aligned_preview=preview_records,
    )

    return df_aligned, result
