"""
Stage 1 — XML & HTML Extractor
================================
Extracts:
  - All HTML <table> elements with <th>/<td> tags using BeautifulSoup.
  - Repeating XML elements (<record>, <item>, <entry>, etc.) into columns.
  - XML attributes and child tags as column headers.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from bs4 import BeautifulSoup
import chardet

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_xml_html(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract tables and structured data from HTML or XML files.
    """
    warnings: list[str] = []
    tables: list[RawTable] = []

    # Decode text
    detected = chardet.detect(file_bytes)
    encoding = detected.get("encoding") or "utf-8"
    try:
        text = file_bytes.decode(encoding, errors="replace")
    except Exception:
        text = file_bytes.decode("utf-8", errors="replace")
        warnings.append("Decoded using UTF-8 fallback with replacement characters.")

    is_xml = filename.lower().endswith(".xml")

    # 1. Try HTML Table extraction first (works on both HTML and XML with table tags)
    html_tables = _extract_html_tables(text)
    if html_tables:
        return Stage1Result(
            filename=filename,
            file_type="html" if not is_xml else "xml",
            tables=html_tables,
            warnings=warnings,
        )

    # 2. Try XML Record-based extraction if is_xml or contains XML declaration
    if is_xml or text.strip().startswith("<?xml"):
        xml_table = _extract_xml_records(text, filename)
        if xml_table:
            return Stage1Result(
                filename=filename,
                file_type="xml",
                tables=[xml_table],
                warnings=warnings,
            )

    # 3. Fallback: Extract list items / paragraphs from HTML
    soup = BeautifulSoup(text, "html.parser")
    # Remove script and style
    for s in soup(["script", "style"]):
        s.decompose()

    items = [li.get_text(strip=True) for li in soup.find_all(["li", "p"]) if li.get_text(strip=True)]
    if items:
        rows = [
            RawRow(
                row_index=idx,
                source_line=idx + 1,
                raw_text=it,
                cells=[
                    RawCell(col_index=0, value=idx + 1, raw_text=str(idx + 1)),
                    RawCell(col_index=1, value=it, raw_text=it),
                    RawCell(col_index=2, value=len(it.split()), raw_text=str(len(it.split()))),
                ],
            )
            for idx, it in enumerate(items[:5000])
        ]
        tables.append(RawTable(
            table_index=0,
            source_sheet="Extracted Content",
            extraction_method=ExtractionMethod.XML_HTML_TABLE,
            headers=["Item_No", "Content", "Word_Count"],
            rows=rows,
        ))
        warnings.append("No explicit tables found; extracted document paragraphs and list items.")

    return Stage1Result(
        filename=filename,
        file_type="html" if not is_xml else "xml",
        tables=tables,
        warnings=warnings,
    )


def _extract_html_tables(html_text: str) -> list[RawTable]:
    """Extracts all <table> elements with rows and cells."""
    soup = BeautifulSoup(html_text, "html.parser")
    tables_found = soup.find_all("table")
    raw_tables: list[RawTable] = []

    for t_idx, tbl in enumerate(tables_found):
        rows_data: list[list[str]] = []

        for tr in tbl.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if any(c for c in cells):
                rows_data.append(cells)

        if not rows_data:
            continue

        headers = [h if h else f"Col_{i}" for i, h in enumerate(rows_data[0])]
        num_cols = len(headers)

        rows: list[RawRow] = []
        for ri, r in enumerate(rows_data[1:]):
            padded = (r + [""] * num_cols)[:num_cols]
            cells = [
                RawCell(col_index=ci, value=_coerce_val(val), raw_text=val)
                for ci, val in enumerate(padded)
            ]
            rows.append(RawRow(
                row_index=ri,
                source_line=ri + 2,
                raw_text=" | ".join(padded),
                cells=cells,
            ))

        caption = tbl.find("caption")
        sheet_name = caption.get_text(strip=True) if caption else f"Table {t_idx + 1}"

        raw_tables.append(RawTable(
            table_index=t_idx,
            source_sheet=sheet_name[:30],
            extraction_method=ExtractionMethod.XML_HTML_TABLE,
            headers=headers,
            rows=rows,
        ))

    return raw_tables


def _extract_xml_records(xml_text: str, filename: str) -> Any:
    """Detects repeating XML tags and extracts child elements and attributes as columns."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    # Find the most frequent repeating tag name among all descendants
    tag_counts: dict[str, int] = {}
    for elem in root.iter():
        if elem != root:
            tag_counts[elem.tag] = tag_counts.get(elem.tag, 0) + 1

    if not tag_counts:
        return None

    # Pick the repeating tag with max count (at least 2 occurrences)
    candidates = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    best_tag, count = candidates[0]
    if count < 2:
        return None

    records: list[dict] = []
    for elem in root.iter(best_tag):
        rec: dict = {}
        # Add XML attributes
        for k, v in elem.attrib.items():
            rec[f"@{k}"] = v
        # Add child tag values
        for child in elem:
            child_tag = child.tag.split("}")[-1]  # remove namespace
            child_val = child.text.strip() if child.text else ""
            rec[child_tag] = child_val
        if not rec and elem.text and elem.text.strip():
            rec["Value"] = elem.text.strip()
        if rec:
            records.append(rec)

    if not records:
        return None

    # Union of headers
    seen_headers: set[str] = set()
    headers: list[str] = []
    for r in records:
        for k in r.keys():
            if k not in seen_headers:
                seen_headers.add(k)
                headers.append(k)

    num_cols = len(headers)
    rows: list[RawRow] = []
    for ri, r in enumerate(records):
        cells = []
        raw_vals = []
        for ci, h in enumerate(headers):
            val = r.get(h)
            raw_str = "" if val is None else str(val)
            raw_vals.append(raw_str)
            cells.append(RawCell(col_index=ci, value=_coerce_val(raw_str), raw_text=raw_str))
        rows.append(RawRow(
            row_index=ri,
            source_line=ri + 1,
            raw_text=" | ".join(raw_vals),
            cells=cells,
        ))

    tag_name_clean = best_tag.split("}")[-1]
    return RawTable(
        table_index=0,
        source_sheet=f"{tag_name_clean} records",
        extraction_method=ExtractionMethod.XML_HTML_TABLE,
        headers=headers,
        rows=rows,
    )


def _coerce_val(text: str) -> Any:
    if text == "":
        return None
    lower = text.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    cleaned = re.sub(r"[,$£€₹\s]", "", text).replace("(", "-").replace(")", "")
    try:
        f = float(cleaned)
        return int(f) if f == int(f) else f
    except ValueError:
        return text
