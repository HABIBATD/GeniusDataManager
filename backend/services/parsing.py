"""
Parsing service for GeniusDataManager.
Handles ingestion and dataframe extraction from CSV, Excel (XLSX/XLS), and JSON files,
including multi-sheet detection, encoding sniffing, and column sanitization.
"""
import io
import json
import logging
from typing import List, Optional, Tuple
import chardet
import openpyxl
import pandas as pd

logger = logging.getLogger("genius.parsing")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB default cap
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json"}


def sanitize_column_names(columns: List[str]) -> List[str]:
    """
    Ensure column names are non-empty strings and deduplicate any duplicates by appending _1, _2, etc.
    """
    clean_cols = []
    counts: dict[str, int] = {}
    for idx, col in enumerate(columns):
        c_str = str(col).strip() if col is not None else ""
        if not c_str or c_str.lower().startswith("unnamed:"):
            c_str = f"column_{idx + 1}"
        if c_str in counts:
            counts[c_str] += 1
            dedup_name = f"{c_str}_{counts[c_str]}"
            clean_cols.append(dedup_name)
        else:
            counts[c_str] = 0
            clean_cols.append(c_str)
    return clean_cols


def detect_excel_sheets(content: bytes) -> List[str]:
    """
    Extract sheet names from an Excel file without loading all sheet contents into memory.
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets = wb.sheetnames
        wb.close()
        return sheets
    except Exception as exc:
        logger.warning(f"openpyxl failed to read sheet names: {exc}. Trying pandas ExcelFile.")
        try:
            xl = pd.ExcelFile(io.BytesIO(content))
            return xl.sheet_names
        except Exception as e:
            logger.error(f"Failed to extract sheet names: {e}")
            return ["Sheet1"]


def parse_csv(content: bytes) -> pd.DataFrame:
    """
    Parse CSV or TSV bytes with encoding detection and delimiter sniffing.
    """
    # Detect encoding
    detected = chardet.detect(content[:100000])
    encoding = detected.get("encoding") or "utf-8"
    if encoding.lower() in ("ascii", "windows-1252", "iso-8859-1"):
        encoding = "latin-1"

    # Try utf-8 first, fallback to detected
    buffer = io.BytesIO(content)
    try:
        df = pd.read_csv(buffer, encoding="utf-8", sep=None, engine="python")
    except Exception:
        buffer.seek(0)
        try:
            df = pd.read_csv(buffer, encoding=encoding, sep=None, engine="python")
        except Exception:
            buffer.seek(0)
            # fallback to comma delimiter
            df = pd.read_csv(buffer, encoding="latin-1", on_bad_lines="skip")

    # Sanitize dataframe
    df = clean_dataframe(df)
    return df


def parse_excel(content: bytes, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Parse an Excel workbook sheet into a clean pandas DataFrame.
    """
    buffer = io.BytesIO(content)
    target_sheet = sheet_name if sheet_name else 0
    try:
        df = pd.read_excel(buffer, sheet_name=target_sheet, engine="openpyxl")
    except Exception as exc:
        logger.warning(f"openpyxl read_excel failed: {exc}. Trying default engine.")
        buffer.seek(0)
        df = pd.read_excel(buffer, sheet_name=target_sheet)

    df = clean_dataframe(df)
    return df


def parse_json(content: bytes) -> pd.DataFrame:
    """
    Parse JSON bytes into a pandas DataFrame.
    Supports list of records, dict with 'data'/'records' key, or line-delimited JSON.
    """
    # Detect text encoding
    text = None
    for enc in ["utf-8", "latin-1"]:
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = content.decode("utf-8", errors="replace")

    text = text.strip()
    # Try standard JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            df = pd.json_normalize(parsed)
        elif isinstance(parsed, dict):
            # Check for common container keys
            for key in ["data", "records", "items", "rows", "results"]:
                if key in parsed and isinstance(parsed[key], list):
                    df = pd.json_normalize(parsed[key])
                    break
            else:
                # Single record or dict of columns
                df = pd.DataFrame([parsed])
        else:
            df = pd.DataFrame()
    except json.JSONDecodeError:
        # Try JSON lines
        buffer = io.StringIO(text)
        df = pd.read_json(buffer, lines=True)

    df = clean_dataframe(df)
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean columns and remove completely empty rows/columns.
    """
    if df.empty:
        return df

    # Drop completely empty rows and columns
    df = df.dropna(how="all", axis=0).reset_index(drop=True)
    df = df.dropna(how="all", axis=1)

    # Sanitize and deduplicate column names
    clean_cols = sanitize_column_names([str(c) for c in df.columns])
    df.columns = clean_cols
    return df


def parse_uploaded_file(content: bytes, filename: str, sheet_name: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[List[str]]]:
    """
    Dispatcher to parse any supported uploaded file content.
    Returns (DataFrame, sheet_names_if_excel).
    """
    lower_name = filename.lower()
    sheet_names = None

    if lower_name.endswith((".xlsx", ".xls")):
        sheet_names = detect_excel_sheets(content)
        selected_sheet = sheet_name or (sheet_names[0] if sheet_names else None)
        df = parse_excel(content, sheet_name=selected_sheet)
    elif lower_name.endswith((".csv", ".tsv", ".txt")):
        df = parse_csv(content)
    elif lower_name.endswith((".json", ".jsonl")):
        df = parse_json(content)
    else:
        # Attempt CSV parse as generic fallback
        try:
            df = parse_csv(content)
        except Exception:
            raise ValueError(f"Unsupported file format for '{filename}'. Allowed: CSV, XLSX, XLS, JSON.")

    return df, sheet_names
