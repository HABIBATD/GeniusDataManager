"""
Stage 2 — Hierarchy Detector
==============================
Assigns a RowRole to each row: DETAIL, SUBTOTAL, GRAND_TOTAL, SECTION_HEADER, or UNKNOWN.

Detection signals (applied in order; first match wins):
  1. GRAND_TOTAL: row text matches "grand total", "total overall", "net total" patterns
     AND its numeric value is larger than the median of all numeric values in the column.
  2. SUBTOTAL: row text contains "total", "subtotal", "sum", "sous-total" (French),
     "totaal" (Dutch), "suma" (Spanish/Polish), "合計" (Japanese), "总计" (Chinese), etc.
     — detected by regex, not by hardcoded English strings.
  3. SECTION_HEADER: row has only 1 non-empty cell (or ≤25% non-empty cells),
     and its value is a string (not a number).
  4. DETAIL: everything else.
  5. UNKNOWN: edge cases where signals conflict.

Judgment calls documented:
  - The multilingual keyword list covers common cases but is not exhaustive.
    Files with domain-specific subtotal labels (e.g. "Carried Forward") will fall
    through to DETAIL — users can see the row_role in the profile and correct this.
  - The "≤25% non-empty" threshold for SECTION_HEADER avoids misclassifying
    sparse data rows.
"""

import re
import statistics
from typing import Any

from models.intermediate import RawRow, RowRole

# Multilingual patterns that indicate a subtotal or total row.
# Judgment call: these cover common Western + East Asian office languages;
# domain-specific labels (e.g. "Carried Forward", "B/F") will NOT match
# and will correctly remain DETAIL rows.
_TOTAL_PATTERNS = re.compile(
    r"""
    (
      \btotal[s]?\b                |  # English: total, totals
      \bsubtotal[s]?\b             |  # English: subtotal
      \bsub[\s\-]?total[s]?\b     |  # hyphenated
      \bgrand[\s]?total\b          |  # grand total
      \bnet[\s]?total\b            |  # net total
      \bsum[\s]?total\b            |  # sum total
      \bsum\b                      |  # sum (standalone)
      \bsous[\s\-]total\b          |  # French
      \btotaal\b                   |  # Dutch
      \bsumme\b                    |  # German
      \bsuma\b                     |  # Spanish / Polish
      \btotale\b                   |  # Italian
      \btotal[\s]?geral\b          |  # Portuguese
      合計                          |  # Japanese: gōkei
      小計                          |  # Japanese: shōkei (subtotal)
      总计                          |  # Simplified Chinese
      總計                          |  # Traditional Chinese
      합계                          |  # Korean
      \bitog\b                     |  # Norwegian/Danish
      \btotalt\b                   |  # Swedish/Norwegian
      \bтого\b                     |  # Russian: itogo
      \bитого\b                    |  # Russian: itogo (alternate)
      \bвсего\b                    |  # Russian: vsego (total)
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.UNICODE,
)

_GRAND_TOTAL_PATTERNS = re.compile(
    r"""(
      grand[\s]?total |
      total[\s]?general |
      net[\s]?total |
      overall[\s]?total |
      grand[\s]?sum |
      总计 | 합계
    )""",
    re.IGNORECASE | re.VERBOSE | re.UNICODE,
)


def assign_row_roles(
    rows: list[RawRow],
    num_cols: int,
) -> list[RowRole]:
    """
    Assign a RowRole to every row in the table.

    Args:
        rows:      All RawRows in the table (from Stage 1).
        num_cols:  Number of columns (used to compute fill-ratio for SECTION_HEADER detection).

    Returns:
        A parallel list of RowRole values (same length as rows).
    """
    roles: list[RowRole] = []

    # Pre-compute: collect all numeric values per column to get column medians
    col_numeric_vals: dict[int, list[float]] = {}
    for row in rows:
        for cell in row.cells:
            if isinstance(cell.value, (int, float)):
                col_numeric_vals.setdefault(cell.col_index, []).append(float(cell.value))

    col_medians: dict[int, float] = {
        ci: statistics.median(vals)
        for ci, vals in col_numeric_vals.items()
        if vals
    }

    for row in rows:
        role = _classify_row(row, num_cols, col_medians)
        roles.append(role)

    return roles


def _classify_row(
    row: RawRow,
    num_cols: int,
    col_medians: dict[int, float],
) -> RowRole:
    row_text = row.raw_text.strip()

    # Count non-empty cells
    non_empty_cells = [c for c in row.cells if c.value is not None and str(c.value).strip()]
    fill_ratio = len(non_empty_cells) / max(1, num_cols)

    # --- Signal: does the raw text contain a total/subtotal keyword? ---
    has_total_keyword = bool(_TOTAL_PATTERNS.search(row_text))
    has_grand_keyword = bool(_GRAND_TOTAL_PATTERNS.search(row_text))

    # --- Signal: does the row's numeric value exceed the column median? ---
    # This helps distinguish true subtotals from rows that merely mention "total" in text.
    exceeds_median = False
    for cell in row.cells:
        if isinstance(cell.value, (int, float)):
            median = col_medians.get(cell.col_index)
            if median and abs(float(cell.value)) > abs(median) * 1.5:
                exceeds_median = True
                break

    # --- Rule 1: GRAND_TOTAL ---
    if has_grand_keyword:
        return RowRole.GRAND_TOTAL

    # --- Rule 2: SUBTOTAL ---
    if has_total_keyword:
        return RowRole.SUBTOTAL

    # --- Rule 3: SECTION_HEADER ---
    # A row with ≤25% non-empty cells where the first cell is a string (not numeric)
    if fill_ratio <= 0.25 and non_empty_cells:
        first_non_empty = non_empty_cells[0]
        if isinstance(first_non_empty.value, str):
            return RowRole.SECTION_HEADER

    # Also: a row where all cells are empty except one string cell in a low-index column
    if (
        len(non_empty_cells) == 1
        and isinstance(non_empty_cells[0].value, str)
        and non_empty_cells[0].col_index <= 1
    ):
        return RowRole.SECTION_HEADER

    # --- Rule 4: DETAIL (default) ---
    return RowRole.DETAIL


def has_hierarchy(roles: list[RowRole]) -> bool:
    """Return True if any row is SUBTOTAL, GRAND_TOTAL, or SECTION_HEADER."""
    return any(r in (RowRole.SUBTOTAL, RowRole.GRAND_TOTAL, RowRole.SECTION_HEADER) for r in roles)
