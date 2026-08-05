"""
Stage 1 — CSV Extractor
========================
Strategy:
  1. Auto-detect encoding with chardet.
  2. Auto-detect delimiter with csv.Sniffer.
  3. Identify header row (first non-empty, non-comment row).
  4. Preserve original file row number for every data row (traceability).
  5. Rows that fail to parse → unparsed_rows (never silently dropped).
"""

import csv
import io
import logging
import re
from typing import Any

import chardet  # type: ignore

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_csv(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract data from a CSV file.
    Returns a Stage1Result with a single RawTable.
    """
    warnings: list[str] = []
    unparsed: list[dict] = []

    # --- Step 1: Detect encoding ---
    detected = chardet.detect(file_bytes)
    encoding = detected.get("encoding") or "utf-8"
    confidence = detected.get("confidence", 0.0)
    if confidence < 0.7:
        warnings.append(
            f"Encoding detection confidence is low ({confidence:.0%}). "
            f"Guessed '{encoding}'. If the data looks garbled, the file may use a different encoding."
        )

    try:
        text = file_bytes.decode(encoding, errors="replace")
    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="csv",
            warnings=[f"Could not decode file with encoding '{encoding}': {exc}"],
        )

    # --- Step 2: Detect delimiter ---
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
        warnings.append("Could not auto-detect delimiter; defaulting to comma.")

    # --- Step 3: Parse rows ---
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    raw_rows_all: list[list[str]] = []
    for row in reader:
        raw_rows_all.append(row)

    if not raw_rows_all:
        return Stage1Result(
            filename=filename,
            file_type="csv",
            warnings=["File appears empty."],
        )

    # --- Step 4: Identify header row (skip fully blank leading rows) ---
    header_file_line = 0
    for i, row in enumerate(raw_rows_all):
        if any(cell.strip() for cell in row):
            header_file_line = i
            break

    headers_raw = raw_rows_all[header_file_line]
    headers = [
        cell.strip() if cell.strip() else f"Col_{ci}"
        for ci, cell in enumerate(headers_raw)
    ]
    num_cols = len(headers)

    # --- Step 5: Build RawRows from data rows ---
    raw_rows: list[RawRow] = []
    row_index = 0

    for file_line, row in enumerate(raw_rows_all[header_file_line + 1:], start=header_file_line + 1):
        # Skip completely empty rows silently (visual spacers)
        if not any(cell.strip() for cell in row):
            continue

        # Pad or truncate to match header width
        padded = list(row) + [""] * max(0, num_cols - len(row))
        padded = padded[:num_cols]

        try:
            cells: list[RawCell] = []
            for ci, raw_val in enumerate(padded):
                cleaned = raw_val.strip()
                cells.append(RawCell(
                    col_index=ci,
                    value=_coerce_value(cleaned),
                    raw_text=cleaned,
                ))
            raw_rows.append(RawRow(
                row_index=row_index,
                source_page=None,
                source_line=file_line + 1,  # 1-based file line number
                raw_text=delimiter.join(row),
                cells=cells,
            ))
            row_index += 1
        except Exception as exc:
            unparsed.append({
                "source": f"file line {file_line + 1}",
                "reason": str(exc),
                "raw_text": delimiter.join(row)[:300],
            })

    table = RawTable(
        table_index=0,
        source_page=None,
        source_sheet=None,
        extraction_method=ExtractionMethod.PANDAS_CSV,
        headers=headers,
        rows=raw_rows,
        unparsed_rows=unparsed,
    )

    return Stage1Result(
        filename=filename,
        file_type="csv",
        total_pages=None,
        tables=[table],
        unparsed_rows=unparsed,
        warnings=warnings,
    )


def _coerce_value(text: str) -> Any:
    if text == "":
        return None
    cleaned = re.sub(r"[,$£€₹\s]", "", text)
    cleaned = cleaned.replace("(", "-").replace(")", "")
    try:
        f = float(cleaned)
        return int(f) if f == int(f) else f
    except ValueError:
        pass
    return text
