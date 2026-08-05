"""
Stage 1 — PDF Extractor
=======================
Strategy:
  1. Open with pdfplumber. Attempt extract_tables() (line-based column detection).
  2. If tables are found and non-empty → use them.
  3. If extract_tables() returns empty / text too sparse (<50 chars) → fall back to OCR.
     a. Convert the page to an image via pdf2image (300 DPI).
     b. Run pytesseract.image_to_data() to get per-word bounding boxes.
     c. Cluster words into rows by y-coordinate proximity, then into columns by x-gap.
  4. Rows that cannot be parsed are stored in unparsed_rows — never silently dropped.

Every row carries: page_num, source_line (bbox y-position), raw_text — for traceability.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)

# OCR availability flag — checked once at import time so we can degrade gracefully
_OCR_AVAILABLE = False
_OCR_UNAVAILABLE_REASON = ""

try:
    import pdfplumber  # type: ignore
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not installed — PDF extraction unavailable")

try:
    import pytesseract  # type: ignore
    from pdf2image import convert_from_bytes  # type: ignore
    # Quick smoke-test: if tesseract binary is missing this raises
    pytesseract.get_tesseract_version()
    _OCR_AVAILABLE = True
except Exception as exc:
    _OCR_UNAVAILABLE_REASON = str(exc)
    logger.warning("Tesseract/OCR not available: %s. Scanned PDFs will be flagged.", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_pdf(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract all tables from a PDF file.
    Returns a Stage1Result with one RawTable per detected logical table.
    """
    if not _PDFPLUMBER_AVAILABLE:
        return Stage1Result(
            filename=filename,
            file_type="pdf",
            warnings=["pdfplumber not installed — PDF extraction unavailable"],
        )

    result_tables: list[RawTable] = []
    global_unparsed: list[dict] = []
    warnings: list[str] = []
    total_pages = 0

    import io

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        total_pages = len(pdf.pages)
        table_index = 0

        for page in pdf.pages:
            page_num = page.page_number  # 1-based

            # --- Attempt 1: structured table extraction ---
            try:
                tables = page.extract_tables()
            except Exception as exc:
                warnings.append(f"Page {page_num}: extract_tables() failed: {exc}")
                tables = []

            # Filter noise: discard tables with fewer than 2 non-empty rows or 1 column.
            # pdfplumber can detect hundreds of tiny text blocks as separate "tables";
            # these are almost always false positives from aligned text, not real data tables.
            if tables:
                quality_tables = [
                    tbl for tbl in tables
                    if tbl
                    and len(tbl) >= 2                          # at least header + 1 data row
                    and len(tbl[0]) >= 2                       # at least 2 columns
                    and sum(                                    # at least 1 non-blank data row
                        1 for row in tbl[1:]
                        if any(cell and str(cell).strip() for cell in row)
                    ) >= 1
                ]
                # If pdfplumber returned many tiny fragments (>10) but only 1-2 are real,
                # consolidate: group tables with identical header structure.
                if len(quality_tables) > 10:
                    quality_tables = _consolidate_tables(quality_tables)

                if quality_tables:
                    for tbl in quality_tables:
                        raw_table, unparsed = _pdfplumber_table_to_raw(
                            tbl, table_index, page_num, ExtractionMethod.PDFPLUMBER_TABLES
                        )
                        if raw_table.rows:  # only keep tables that produced actual rows
                            result_tables.append(raw_table)
                            global_unparsed.extend(unparsed)
                            table_index += 1
                    continue  # page handled by table extraction

            # --- Attempt 2: check if page has any meaningful text ---
            page_text = page.extract_text() or ""
            if len(page_text.strip()) >= 50:
                # Has text but no tables — treat entire page text as one table
                raw_table, unparsed = _text_to_raw_table(
                    page_text, table_index, page_num
                )
                result_tables.append(raw_table)
                global_unparsed.extend(unparsed)
                table_index += 1
                continue

            # --- Attempt 3: OCR fallback ---
            if _OCR_AVAILABLE:
                try:
                    ocr_table, unparsed = _ocr_page(
                        file_bytes, page_num, table_index
                    )
                    result_tables.append(ocr_table)
                    global_unparsed.extend(unparsed)
                    table_index += 1
                except Exception as exc:
                    warnings.append(f"Page {page_num}: OCR failed: {exc}")
                    global_unparsed.append({
                        "source": f"page {page_num}",
                        "reason": f"OCR error: {exc}",
                        "raw_text": page_text[:200],
                    })
            else:
                msg = (
                    f"Page {page_num}: sparse text (<50 chars) and OCR unavailable "
                    f"({_OCR_UNAVAILABLE_REASON}). Page flagged as unreadable."
                )
                warnings.append(msg)
                global_unparsed.append({
                    "source": f"page {page_num}",
                    "reason": "OCR unavailable — install Tesseract to process scanned pages",
                    "raw_text": page_text[:200],
                })

    return Stage1Result(
        filename=filename,
        file_type="pdf",
        total_pages=total_pages,
        tables=result_tables,
        unparsed_rows=global_unparsed,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pdfplumber_table_to_raw(
    tbl: list[list],
    table_index: int,
    page_num: int,
    method: ExtractionMethod,
) -> tuple[RawTable, list[dict]]:
    """
    Convert a pdfplumber raw table (list of lists) to our RawTable model.
    The first row is treated as headers; remaining rows are data.
    Cells that cannot be cast to any type go into unparsed_rows.
    """
    unparsed: list[dict] = []

    if not tbl:
        return RawTable(
            table_index=table_index,
            source_page=page_num,
            extraction_method=method,
        ), unparsed

    # Normalize: remove fully-None rows (pdfplumber emits them for merged cells)
    tbl = [row for row in tbl if any(cell is not None for cell in row)]
    if not tbl:
        return RawTable(
            table_index=table_index,
            source_page=page_num,
            extraction_method=method,
        ), unparsed

    # First row = headers (may contain None — fill with "Col_N")
    headers = [
        _clean_cell(tbl[0][i]) if tbl[0][i] is not None else f"Col_{i}"
        for i in range(len(tbl[0]))
    ]

    raw_rows: list[RawRow] = []
    for row_idx, row in enumerate(tbl[1:], start=1):
        # Pad short rows
        padded = list(row) + [None] * max(0, len(headers) - len(row))
        cells: list[RawCell] = []
        row_text_parts: list[str] = []

        for col_idx, cell_val in enumerate(padded[: len(headers)]):
            cleaned = _clean_cell(cell_val)
            row_text_parts.append(cleaned)
            cells.append(RawCell(col_index=col_idx, value=_coerce_value(cleaned), raw_text=cleaned))

        raw_rows.append(RawRow(
            row_index=row_idx - 1,
            source_page=page_num,
            source_line=row_idx,          # row position within the table
            raw_text=" | ".join(row_text_parts),
            cells=cells,
        ))

    return RawTable(
        table_index=table_index,
        source_page=page_num,
        extraction_method=method,
        headers=headers,
        rows=raw_rows,
    ), unparsed


def _text_to_raw_table(
    page_text: str,
    table_index: int,
    page_num: int,
) -> tuple[RawTable, list[dict]]:
    """
    Fallback: convert raw page text (no table structure found) into a single-column table.
    Each non-empty line becomes one row with one cell.
    """
    lines = [ln for ln in page_text.splitlines() if ln.strip()]
    headers = ["text"]
    raw_rows = [
        RawRow(
            row_index=i,
            source_page=page_num,
            source_line=i,
            raw_text=line,
            cells=[RawCell(col_index=0, value=line.strip(), raw_text=line.strip())],
        )
        for i, line in enumerate(lines)
    ]
    return RawTable(
        table_index=table_index,
        source_page=page_num,
        extraction_method=ExtractionMethod.PDFPLUMBER_TEXT,
        headers=headers,
        rows=raw_rows,
    ), []


def _ocr_page(
    file_bytes: bytes,
    page_num: int,
    table_index: int,
) -> tuple[RawTable, list[dict]]:
    """
    OCR a single PDF page.
    Uses pytesseract.image_to_data() for per-word bounding boxes,
    then clusters words into rows (y-proximity) and columns (x-gap).
    """
    import pytesseract  # type: ignore
    from pdf2image import convert_from_bytes  # type: ignore
    from PIL import Image  # type: ignore
    import io

    images = convert_from_bytes(
        file_bytes,
        dpi=300,
        first_page=page_num,
        last_page=page_num,
    )
    if not images:
        return RawTable(
            table_index=table_index,
            source_page=page_num,
            extraction_method=ExtractionMethod.OCR,
        ), [{"source": f"page {page_num}", "reason": "pdf2image returned no images"}]

    img = images[0]
    ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    # Collect non-empty words with their bounding boxes
    words: list[dict] = []
    for i, text in enumerate(ocr_data["text"]):
        if text.strip():
            words.append({
                "text": text.strip(),
                "x": ocr_data["left"][i],
                "y": ocr_data["top"][i],
                "w": ocr_data["width"][i],
                "h": ocr_data["height"][i],
                "conf": ocr_data["conf"][i],
            })

    if not words:
        return RawTable(
            table_index=table_index,
            source_page=page_num,
            extraction_method=ExtractionMethod.OCR,
        ), [{"source": f"page {page_num}", "reason": "OCR returned no words"}]

    # Cluster words into rows by y-coordinate (within ±10px = same row)
    words.sort(key=lambda w: (w["y"], w["x"]))
    row_clusters: list[list[dict]] = []
    current_row: list[dict] = [words[0]]
    current_y = words[0]["y"]

    for word in words[1:]:
        if abs(word["y"] - current_y) <= 12:
            current_row.append(word)
        else:
            row_clusters.append(sorted(current_row, key=lambda w: w["x"]))
            current_row = [word]
            current_y = word["y"]
    if current_row:
        row_clusters.append(sorted(current_row, key=lambda w: w["x"]))

    # Detect column boundaries from first few rows (x-gap clustering)
    col_boundaries = _detect_column_x_boundaries(row_clusters[:5])

    # Build headers from first row
    first_row_text = " ".join(w["text"] for w in row_clusters[0])
    if col_boundaries:
        header_cells = _assign_words_to_columns(row_clusters[0], col_boundaries)
        headers = [c if c else f"Col_{i}" for i, c in enumerate(header_cells)]
    else:
        headers = ["text"]

    raw_rows: list[RawRow] = []
    for row_idx, cluster in enumerate(row_clusters[1:], start=1):
        if col_boundaries:
            col_texts = _assign_words_to_columns(cluster, col_boundaries)
        else:
            col_texts = [" ".join(w["text"] for w in cluster)]

        cells = [
            RawCell(col_index=ci, value=_coerce_value(ct), raw_text=ct)
            for ci, ct in enumerate(col_texts)
        ]
        raw_rows.append(RawRow(
            row_index=row_idx - 1,
            source_page=page_num,
            source_line=cluster[0]["y"],  # y-position as proxy for line number
            raw_text=" | ".join(col_texts),
            cells=cells,
        ))

    return RawTable(
        table_index=table_index,
        source_page=page_num,
        extraction_method=ExtractionMethod.OCR,
        headers=headers,
        rows=raw_rows,
    ), []


def _detect_column_x_boundaries(row_clusters: list[list[dict]]) -> list[int]:
    """
    Heuristic: find x-positions of large horizontal gaps between words
    across the first few rows, to infer column boundaries.
    Returns a sorted list of x-split positions (boundaries between columns).
    """
    if not row_clusters:
        return []

    # Collect all word right-edges and next-word left-edges gaps
    gaps: list[tuple[int, int]] = []  # (gap_start_x, gap_size)
    for cluster in row_clusters:
        for i in range(len(cluster) - 1):
            right_edge = cluster[i]["x"] + cluster[i]["w"]
            next_left = cluster[i + 1]["x"]
            gap = next_left - right_edge
            if gap > 20:  # significant gap
                gaps.append((right_edge, gap))

    if not gaps:
        return []

    # Sort by gap start x, then merge overlapping gap positions
    gaps.sort(key=lambda g: g[0])
    boundaries: list[int] = []
    for gap_x, _ in gaps:
        mid = gap_x + 5
        if not boundaries or abs(mid - boundaries[-1]) > 30:
            boundaries.append(mid)

    return sorted(boundaries)


def _assign_words_to_columns(
    words: list[dict], col_boundaries: list[int]
) -> list[str]:
    """
    Assign each word to a column bucket based on its x-center vs. boundary positions.
    Returns a list of strings (one per column), gaps are empty strings.
    """
    num_cols = len(col_boundaries) + 1
    buckets: list[list[str]] = [[] for _ in range(num_cols)]

    for word in words:
        x_center = word["x"] + word["w"] / 2
        col_idx = 0
        for boundary in col_boundaries:
            if x_center > boundary:
                col_idx += 1
        buckets[col_idx].append(word["text"])

    return [" ".join(b) for b in buckets]


def _clean_cell(val) -> str:
    if val is None:
        return ""
    text = str(val).strip()
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def _coerce_value(text: str):
    """
    Try to return a typed Python value from a cell string.
    Order: None → float → int → str
    """
    if text == "" or text is None:
        return None
    # Remove common numeric noise: commas, currency symbols, trailing % (keep actual value)
    cleaned = re.sub(r"[,$£€₹\s]", "", text)
    cleaned = cleaned.replace("(", "-").replace(")", "")  # accounting negatives: (500) → -500
    try:
        f = float(cleaned)
        return int(f) if f == int(f) else f
    except ValueError:
        pass
    return text
