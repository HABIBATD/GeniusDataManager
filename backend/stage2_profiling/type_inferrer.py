"""
Stage 2 — Column Type Inferrer
================================
Infers column type from VALUES, not header text.
Header text is used only as weak supplementary evidence and is labeled as such in output.

Type priority (first matching rule wins):
  1. time_period   — header parses as a date/period expression (detected separately by time_detector)
  2. date          — ≥60% of non-null values parse as dates
  3. currency      — ≥80% parse as float, magnitudes suggest financial values,
                     AND (currency symbol in header OR currency symbol in any value)
  4. percentage    — ≥80% parse as float, values in [−1, 1] OR raw text contains "%"
  5. numeric       — ≥80% parse as float/int (not currency/percentage)
  6. identifier    — unique_count / non_null_count > 0.85 (very high cardinality)
  7. category      — unique_count / non_null_count ≤ 0.20 (low cardinality, string)
  8. free_text     — fallback

Judgment call thresholds (documented explicitly):
  - 80% numeric threshold: industry standard for "mostly numeric" columns
  - 60% date threshold: slightly more lenient because date columns often have blank cells
  - 0.85 cardinality for identifier: typical for ID/code columns
  - 0.20 cardinality for category: typical for label columns (e.g. department, category name)
"""

import re
import unicodedata
from typing import Any

from models.intermediate import ColumnType, RawTable

# Currency symbols used for evidence (NOT hardcoded to specific currency — any triggers this)
_CURRENCY_SYMBOL_PATTERN = re.compile(r"[$£€₹¥₩₦₴₱฿]")
_DATE_PATTERNS = [
    # ISO 8601: 2025-07-01
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    # DD/MM/YYYY or MM/DD/YYYY
    re.compile(r"^\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}$"),
    # Month Year: "Jul 2025", "July 2025", "Jul-2025", "Jul-25"
    re.compile(
        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-](\d{2,4})$",
        re.IGNORECASE,
    ),
    # Quarter: "Q1 2025", "Q1FY26", "Q1 FY26"
    re.compile(r"^Q[1-4]\s*(FY)?\d{2,4}$", re.IGNORECASE),
    # Half-year: "H1 2025", "H2FY26"
    re.compile(r"^H[12]\s*(FY)?\d{2,4}$", re.IGNORECASE),
    # Year only: "2025"
    re.compile(r"^\d{4}$"),
    # Month/Year short: "07/2025", "2025/07"
    re.compile(r"^\d{1,2}/\d{4}$"),
]


def infer_column_type(
    col_index: int,
    header: str,
    values: list[Any],
    is_time_period_header: bool = False,
) -> tuple[ColumnType, float, str]:
    """
    Infer the type of a column from its values.

    Args:
        col_index:            0-based column index
        header:               Column header string (used as weak evidence only)
        values:               All cell values for this column (may include None)
        is_time_period_header: True if the time_detector already marked this header as a period

    Returns:
        (ColumnType, confidence: 0.0–1.0, evidence_string)
    """

    # --- Rule 0: Pre-flagged by time detector ---
    if is_time_period_header:
        return (
            ColumnType.TIME_PERIOD,
            1.0,
            f"Header '{header}' was parsed as a calendar time period by the time detector.",
        )

    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    total = len(non_null)

    if total == 0:
        return (
            ColumnType.FREE_TEXT,
            0.5,
            "Column has no non-null values — defaulting to free_text.",
        )

    # Precompute characteristics
    numeric_vals = _try_parse_numeric(non_null)
    numeric_count = sum(1 for v in numeric_vals if v is not None)
    numeric_ratio = numeric_count / total

    raw_texts = [str(v) for v in non_null]
    pct_texts = [t for t in raw_texts if "%" in t]
    currency_in_values = any(_CURRENCY_SYMBOL_PATTERN.search(t) for t in raw_texts)
    currency_in_header = bool(_CURRENCY_SYMBOL_PATTERN.search(header))

    date_count = sum(1 for t in raw_texts if _is_date_like(t))
    date_ratio = date_count / total

    unique_vals = set(str(v).strip().lower() for v in non_null)
    unique_ratio = len(unique_vals) / total

    # --- Rule 0b: Boolean ---
    bool_count = sum(
        1 for v in non_null
        if isinstance(v, bool) or str(v).strip().lower() in ("true", "false", "yes", "no", "t", "f")
    )
    if bool_count / total >= 0.85:
        return (
            ColumnType.BOOLEAN,
            bool_count / total,
            f"{bool_count}/{total} values ({bool_count/total:.0%}) are boolean (true/false/yes/no). Rule: ≥85% → ColumnType.BOOLEAN.",
        )

    # --- Rule 0c: Complex / JSON ---
    complex_count = sum(
        1 for v in non_null
        if isinstance(v, (dict, list)) or (isinstance(v, str) and v.strip()[:1] in ("{", "[") and v.strip()[-1:] in ("}", "]"))
    )
    if complex_count / total >= 0.50:
        return (
            ColumnType.COMPLEX,
            complex_count / total,
            f"{complex_count}/{total} values contain structured JSON/dict/list objects. Rule: ≥50% → ColumnType.COMPLEX.",
        )

    # --- Rule 1: Date ---
    if date_ratio >= 0.60:
        return (
            ColumnType.DATE,
            date_ratio,
            (
                f"Judgment call (threshold: 60%): {date_count}/{total} values "
                f"({date_ratio:.0%}) parse as dates. "
                f"Rule: ≥60% date-like values → ColumnType.DATE."
            ),
        )

    # --- Rule 2: Percentage ---
    if numeric_ratio >= 0.80 and (
        len(pct_texts) / total >= 0.40
        or (
            numeric_count > 0
            and all(
                v is not None and -1.5 <= v <= 1.5
                for v in numeric_vals
                if v is not None
            )
        )
    ):
        evidence = (
            f"Judgment call (threshold: 80% numeric, 40% '%' symbol or all values in [−1.5, 1.5]): "
            f"{numeric_count}/{total} values are numeric. "
            f"{len(pct_texts)} contain '%'. "
            f"Rule: ≥80% numeric AND (≥40% contain '%' OR all values in [−1.5,1.5]) → ColumnType.PERCENTAGE."
        )
        return (ColumnType.PERCENTAGE, numeric_ratio, evidence)

    # --- Rule 3: Currency ---
    if numeric_ratio >= 0.80 and (currency_in_values or currency_in_header):
        evidence = (
            f"Judgment call (threshold: 80% numeric + currency symbol): "
            f"{numeric_count}/{total} values are numeric. "
            f"Currency symbol found: {'in values' if currency_in_values else 'in header only'}. "
            f"Rule: ≥80% numeric AND currency symbol present → ColumnType.CURRENCY."
        )
        return (ColumnType.CURRENCY, numeric_ratio, evidence)

    # --- Rule 4: Numeric (general) ---
    if numeric_ratio >= 0.80:
        evidence = (
            f"Judgment call (threshold: 80%): {numeric_count}/{total} values "
            f"({numeric_ratio:.0%}) parse as numbers. No currency/percentage signals found. "
            f"Rule: ≥80% numeric, no other signals → ColumnType.NUMERIC."
        )
        return (ColumnType.NUMERIC, numeric_ratio, evidence)

    # --- Rule 5: Identifier (high cardinality) ---
    if unique_ratio > 0.85:
        evidence = (
            f"Judgment call (threshold: unique/total > 0.85): "
            f"{len(unique_vals)} unique values out of {total} non-null ({unique_ratio:.0%}). "
            f"Rule: very high cardinality, string-like → ColumnType.IDENTIFIER."
        )
        return (ColumnType.IDENTIFIER, 0.75, evidence)

    # --- Rule 6: Category (low cardinality) ---
    if unique_ratio <= 0.20 and total >= 3:
        evidence = (
            f"Judgment call (threshold: unique/total ≤ 0.20): "
            f"{len(unique_vals)} unique values out of {total} non-null ({unique_ratio:.0%}). "
            f"Rule: low cardinality, string-like → ColumnType.CATEGORY."
        )
        return (ColumnType.CATEGORY, 0.75, evidence)

    # --- Rule 7: Free text (fallback) ---
    return (
        ColumnType.FREE_TEXT,
        0.5,
        (
            f"No rule matched: numeric_ratio={numeric_ratio:.0%}, "
            f"date_ratio={date_ratio:.0%}, unique_ratio={unique_ratio:.0%}. "
            f"Defaulting to ColumnType.FREE_TEXT."
        ),
    )


def _try_parse_numeric(values: list[Any]) -> list[float | None]:
    """
    Try to parse each value as float.
    Strips common numeric noise: commas, currency symbols, parenthetical negatives.
    Returns a parallel list (None where parsing fails).
    """
    result: list[float | None] = []
    for v in values:
        text = str(v).strip()
        cleaned = re.sub(r"[,$£€₹¥₩₦₴₱฿\s]", "", text)
        cleaned = cleaned.replace("(", "-").replace(")", "")
        cleaned = cleaned.rstrip("%")
        try:
            result.append(float(cleaned))
        except ValueError:
            result.append(None)
    return result


def _is_date_like(text: str) -> bool:
    """Return True if text matches any known date/period pattern."""
    text = text.strip()
    for pat in _DATE_PATTERNS:
        if pat.match(text):
            return True
    # Try python-dateutil as a secondary check for edge cases
    try:
        from dateutil import parser as duparser  # type: ignore
        duparser.parse(text, fuzzy=False)
        # Only accept if it looks unambiguous (has a digit and a letter separator or slash)
        if re.search(r"[\d]", text) and len(text) > 4:
            return True
    except Exception:
        pass
    return False
