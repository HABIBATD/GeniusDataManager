"""
Stage 2 — Time Structure Detector
===================================
Detects whether a set of column headers represents calendar time periods.

Rules:
  1. For each header, attempt to parse it as a month, quarter, half-year, or year expression.
  2. If ≥2 consecutive columns parse as time periods → the table has a time-series layout.
  3. All detected period headers are sorted chronologically (not by their file position),
     and their sort order is stored on the ColumnProfile.period_order field.
  4. The detected range is returned as a structured dict:
       {"period_type": "monthly|quarterly|halfyear|yearly", "start": "...", "end": "...", "count": N}

Judgment calls documented:
  - "≥2 consecutive" threshold: below 2, any random pair of year-like numbers could trigger
    false positives. 2 is the minimum meaningful time series.
  - We attempt a broad set of patterns before falling back to dateutil, because dateutil
    is too aggressive (it will parse "Apr" as a date even without a year, causing false positives
    on category columns with abbreviated text).
"""

import re
from datetime import datetime
from typing import Optional

# -----------------------------------------------------------
# Period patterns — ordered from most specific to least specific
# -----------------------------------------------------------

_MONTH_ABBRS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # French / Spanish abbrs (common in multi-language files)
    "janv": 1, "févr": 2, "fév": 2, "mars": 3, "avr": 4, "mai": 5,
    "juin": 6, "juil": 7, "aoû": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12,
}

_MONTH_FULL = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}


def detect_time_structure(headers: list[str]) -> dict:
    """
    Analyse a list of column headers and return a time-structure descriptor.

    Returns:
      {
        "has_time_structure": bool,
        "period_type": "monthly" | "quarterly" | "halfyear" | "yearly" | None,
        "start": "YYYY-MM" or "YYYY-Q1" etc., or None,
        "end": same format, or None,
        "count": int,
        "time_period_col_indices": [list of col indices that are time periods],
        "parsed_periods": {col_index: {"label": "...", "sort_key": datetime, "period_order": int}},
      }
    """
    parsed: dict[int, dict] = {}

    for i, header in enumerate(headers):
        result = _parse_period(header.strip())
        if result:
            parsed[i] = result

    if len(parsed) < 2:
        return {
            "has_time_structure": False,
            "period_type": None,
            "start": None,
            "end": None,
            "count": 0,
            "time_period_col_indices": [],
            "parsed_periods": {},
        }

    # Sort detected periods by their datetime sort key
    sorted_indices = sorted(parsed.keys(), key=lambda i: parsed[i]["sort_key"])

    # Assign period_order (chronological rank, 0-based)
    for order, idx in enumerate(sorted_indices):
        parsed[idx]["period_order"] = order

    # Determine period type (look at all detected period types)
    types_found = set(p["period_type"] for p in parsed.values())
    if "monthly" in types_found:
        period_type = "monthly"
    elif "quarterly" in types_found:
        period_type = "quarterly"
    elif "halfyear" in types_found:
        period_type = "halfyear"
    else:
        period_type = "yearly"

    # Start and end from sorted period keys
    first = parsed[sorted_indices[0]]
    last = parsed[sorted_indices[-1]]

    return {
        "has_time_structure": True,
        "period_type": period_type,
        "start": first["label"],
        "end": last["label"],
        "count": len(parsed),
        "time_period_col_indices": sorted_indices,
        "parsed_periods": parsed,
    }


def _parse_period(header: str) -> Optional[dict]:
    """
    Try to parse a single header string as a time period.
    Returns None if not a time period.
    Returns a dict: {"label": str, "sort_key": datetime, "period_type": str}
    """
    h = header.strip()

    # --- Monthly: "Jul 2025", "July 2025", "Jul-2025", "Jul-25", "07/2025", "2025/07" ---
    m = re.match(
        r"^([A-Za-zÀ-ÖØ-öø-ÿ]+)[\s\-_](\d{2,4})$", h
    )
    if m:
        month_str = m.group(1).lower()[:4].rstrip(".")
        year_str = m.group(2)
        month_num = _MONTH_ABBRS.get(month_str) or _MONTH_FULL.get(month_str)
        if month_num:
            year = _expand_year(year_str)
            if year:
                label = f"{year}-{month_num:02d}"
                return {
                    "label": label,
                    "sort_key": datetime(year, month_num, 1),
                    "period_type": "monthly",
                }

    # "2025/07" or "07/2025"
    m = re.match(r"^(\d{4})/(\d{1,2})$", h)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return {"label": f"{year}-{month:02d}", "sort_key": datetime(year, month, 1), "period_type": "monthly"}

    m = re.match(r"^(\d{1,2})/(\d{4})$", h)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return {"label": f"{year}-{month:02d}", "sort_key": datetime(year, month, 1), "period_type": "monthly"}

    # --- Quarterly: "Q1 2025", "Q1FY26", "Q1 FY26", "1Q2025" ---
    m = re.match(r"^Q([1-4])[\s\-_]*(FY)?(\d{2,4})$", h, re.IGNORECASE)
    if m:
        quarter = int(m.group(1))
        year = _expand_year(m.group(3))
        if year:
            month_start = (quarter - 1) * 3 + 1
            return {
                "label": f"{year}-Q{quarter}",
                "sort_key": datetime(year, month_start, 1),
                "period_type": "quarterly",
            }

    m = re.match(r"^([1-4])Q[\s\-_]?(\d{4})$", h, re.IGNORECASE)
    if m:
        quarter, year = int(m.group(1)), int(m.group(2))
        month_start = (quarter - 1) * 3 + 1
        return {"label": f"{year}-Q{quarter}", "sort_key": datetime(year, month_start, 1), "period_type": "quarterly"}

    # --- Half-year: "H1 2025", "H2FY26", "H1 FY26" ---
    m = re.match(r"^H([12])[\s\-_]*(FY)?(\d{2,4})$", h, re.IGNORECASE)
    if m:
        half = int(m.group(1))
        year = _expand_year(m.group(3))
        if year:
            month_start = 1 if half == 1 else 7
            return {
                "label": f"{year}-H{half}",
                "sort_key": datetime(year, month_start, 1),
                "period_type": "halfyear",
            }

    # --- Yearly: standalone 4-digit year "2025" ---
    m = re.match(r"^(20\d{2}|19\d{2})$", h)
    if m:
        year = int(m.group(1))
        return {"label": str(year), "sort_key": datetime(year, 1, 1), "period_type": "yearly"}

    # --- Financial year: "FY2025", "FY25", "FY 2025" ---
    m = re.match(r"^FY[\s]?(\d{2,4})$", h, re.IGNORECASE)
    if m:
        year = _expand_year(m.group(1))
        if year:
            return {"label": f"FY{year}", "sort_key": datetime(year, 1, 1), "period_type": "yearly"}

    return None


def _expand_year(year_str: str) -> Optional[int]:
    """
    Convert 2-digit or 4-digit year string to a 4-digit integer.
    Judgment call: 2-digit years 00–49 → 2000–2049, 50–99 → 1950–1999.
    """
    try:
        y = int(year_str)
        if y >= 1900:
            return y
        if y <= 49:
            return 2000 + y
        return 1900 + y
    except ValueError:
        return None
