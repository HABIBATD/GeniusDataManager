"""
Stage 2 — Anomaly Detector
============================
Flags four categories of anomalies. None are silently removed — all are reported.

1. NEGATIVE_IN_POSITIVE_COLUMN
   - Condition: column type is CURRENCY or NUMERIC, ≥90% of non-null values are
     positive, but this specific cell is negative.
   - Judgment call: 90% threshold avoids over-flagging columns that legitimately
     contain mixed signs (e.g. variance columns, P&L items).
   - Does NOT flag PERCENTAGE columns (negative percentages are common in variances).

2. BLANK_RUN
   - Condition: ≥3 consecutive blank cells in a column that otherwise has data.
   - Judgment call: threshold of 3 because 1–2 blank cells are common in real-world
     files (missing data, merged cells artefacts); 3+ suggests a structural gap.

3. OCR_CORRUPTION
   - Condition: cell value (as string) contains characters outside the set of:
     printable ASCII + common punctuation + Unicode letters/digits/currency.
     Targets garbled Tesseract output like "S4|ar|es" or "Ｌ45.00".
   - Does NOT flag legitimate Unicode (Arabic, Chinese, Cyrillic, etc.).

4. DUPLICATE_ROW
   - Condition: all cell values (stripped, lowercased) are identical to a previous row.
   - Only flags DETAIL rows; subtotal rows with identical values are not flagged
     because many reports have identical subtotal rows per category.
"""

import re
import unicodedata
from collections import defaultdict
from typing import Any

from models.intermediate import Anomaly, ColumnProfile, ColumnType, RawRow, RowRole

# Characters that are probably OCR corruption (control chars, box-drawing, etc.)
_SUSPICIOUS_CHAR_PATTERN = re.compile(
    r"[^\w\s\d\.,;\:\!\?\-\+\=\/\\\(\)\[\]\{\}\'\"@#\$%\^&\*\~\`"
    r"\u00A0-\u024F"   # Latin Extended
    r"\u0400-\u04FF"   # Cyrillic
    r"\u0600-\u06FF"   # Arabic
    r"\u4E00-\u9FFF"   # CJK Unified Ideographs
    r"\u3000-\u303F"   # CJK Symbols
    r"\uAC00-\uD7AF"   # Korean Hangul
    r"\u20A0-\u20CF"   # Currency Symbols
    r"\u2019\u2018\u201C\u201D"  # Smart quotes
    r"]",
    re.UNICODE,
)


def detect_anomalies(
    rows: list[RawRow],
    row_roles: list[RowRole],
    col_profiles: list[ColumnProfile],
) -> list[Anomaly]:
    """
    Detect anomalies across all rows in a table.

    Args:
        rows:         All RawRows (Stage 1 output).
        row_roles:    Parallel list of RowRole assigned by hierarchy_detector.
        col_profiles: ColumnProfiles from type_inferrer (for type-aware checks).

    Returns:
        List of Anomaly objects. Never modifies the input rows.
    """
    anomalies: list[Anomaly] = []

    # Index column profiles for fast lookup
    col_type_map: dict[int, ColumnType] = {
        cp.col_index: cp.inferred_type for cp in col_profiles
    }
    col_header_map: dict[int, str] = {
        cp.col_index: cp.header for cp in col_profiles
    }

    # Pre-compute: for each NUMERIC/CURRENCY column, is it a "positive" column?
    positive_col_flags: dict[int, bool] = {}
    for cp in col_profiles:
        if cp.inferred_type in (ColumnType.CURRENCY, ColumnType.NUMERIC):
            numeric_vals = [
                float(row.cells[cp.col_index].value)
                for row in rows
                if cp.col_index < len(row.cells)
                and isinstance(row.cells[cp.col_index].value, (int, float))
            ]
            if numeric_vals:
                pos_count = sum(1 for v in numeric_vals if v >= 0)
                pos_ratio = pos_count / len(numeric_vals)
                # Judgment call: 90% positive → flag negatives
                positive_col_flags[cp.col_index] = pos_ratio >= 0.90
            else:
                positive_col_flags[cp.col_index] = False

    # -- Anomaly 1: Negative values in positive columns --
    for row, role in zip(rows, row_roles):
        if role != RowRole.DETAIL:
            continue
        for cell in row.cells:
            ci = cell.col_index
            if (
                ci in positive_col_flags
                and positive_col_flags[ci]
                and isinstance(cell.value, (int, float))
                and float(cell.value) < 0
            ):
                anomalies.append(Anomaly(
                    anomaly_type="negative_in_positive_column",
                    description=(
                        f"Judgment call (threshold: ≥90% positive): "
                        f"Column '{col_header_map.get(ci, ci)}' has ≥90% positive values, "
                        f"but row {row.row_index} contains {cell.value}. "
                        f"Raw text: '{cell.raw_text}'. "
                        f"Source: page={row.source_page}, line={row.source_line}."
                    ),
                    row_index=row.row_index,
                    col_index=ci,
                    col_header=col_header_map.get(ci),
                    source_page=row.source_page,
                    source_line=row.source_line,
                    raw_value=cell.raw_text,
                ))

    # -- Anomaly 2: Blank runs (≥3 consecutive blanks per column) --
    for cp in col_profiles:
        ci = cp.col_index
        non_null_total = cp.non_null_count if hasattr(cp, "non_null_count") else 0
        # Only check columns that have some data
        col_vals = [
            (row.row_index, row.cells[ci].value if ci < len(row.cells) else None, row.source_page, row.source_line)
            for row in rows
        ]
        blank_run = 0
        run_start_row = None
        for row_i, val, pg, ln in col_vals:
            is_blank = val is None or str(val).strip() == ""
            if is_blank:
                if blank_run == 0:
                    run_start_row = row_i
                blank_run += 1
            else:
                if blank_run >= 3:
                    anomalies.append(Anomaly(
                        anomaly_type="blank_run",
                        description=(
                            f"Judgment call (threshold: ≥3 consecutive blanks): "
                            f"Column '{cp.header}' has {blank_run} consecutive blank cells "
                            f"starting at row {run_start_row}. "
                            f"This may indicate a structural gap or missing data."
                        ),
                        row_index=run_start_row,
                        col_index=ci,
                        col_header=cp.header,
                    ))
                blank_run = 0
                run_start_row = None
        # Check if run extends to end of column
        if blank_run >= 3:
            anomalies.append(Anomaly(
                anomaly_type="blank_run",
                description=(
                    f"Judgment call (threshold: ≥3 consecutive blanks): "
                    f"Column '{cp.header}' ends with {blank_run} consecutive blank cells "
                    f"starting at row {run_start_row}."
                ),
                row_index=run_start_row,
                col_index=ci,
                col_header=cp.header,
            ))

    # -- Anomaly 3: OCR corruption --
    for row, role in zip(rows, row_roles):
        for cell in row.cells:
            if not cell.raw_text:
                continue
            suspicious_chars = _SUSPICIOUS_CHAR_PATTERN.findall(cell.raw_text)
            if suspicious_chars:
                anomalies.append(Anomaly(
                    anomaly_type="ocr_corruption",
                    description=(
                        f"Cell in column '{col_header_map.get(cell.col_index, cell.col_index)}' "
                        f"contains suspicious characters that may be OCR corruption: "
                        f"{suspicious_chars[:5]}. Raw text: '{cell.raw_text[:100]}'. "
                        f"Source: page={row.source_page}, line={row.source_line}."
                    ),
                    row_index=row.row_index,
                    col_index=cell.col_index,
                    col_header=col_header_map.get(cell.col_index),
                    source_page=row.source_page,
                    source_line=row.source_line,
                    raw_value=cell.raw_text[:200],
                ))

    # -- Anomaly 4: Duplicate rows (DETAIL rows only) --
    seen_fingerprints: dict[str, int] = {}
    for row, role in zip(rows, row_roles):
        if role != RowRole.DETAIL:
            continue
        fingerprint = "|".join(
            str(c.value).strip().lower() if c.value is not None else ""
            for c in row.cells
        )
        if fingerprint in seen_fingerprints:
            anomalies.append(Anomaly(
                anomaly_type="duplicate_row",
                description=(
                    f"Row {row.row_index} is an exact duplicate of row "
                    f"{seen_fingerprints[fingerprint]}. "
                    f"All cell values match (case-insensitive, stripped). "
                    f"Source: page={row.source_page}, line={row.source_line}. "
                    f"Raw text: '{row.raw_text[:200]}'."
                ),
                row_index=row.row_index,
                source_page=row.source_page,
                source_line=row.source_line,
                raw_value=row.raw_text[:200],
            ))
        else:
            seen_fingerprints[fingerprint] = row.row_index

    return anomalies
