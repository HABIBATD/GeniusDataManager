"""
Stage 1 — Word Document (.docx) Extractor
===========================================
Extracts:
  - All embedded tables (<w:tbl>) with their column headers and cell values.
  - Document outline / structured paragraphs if no tables are present or as additional context.
Uses standard library zipfile and xml.etree.ElementTree — zero external dependencies.
"""

import io
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)

# Word XML namespaces
_NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


def extract_docx(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract tables and structured content from a DOCX file.
    """
    warnings: list[str] = []
    tables: list[RawTable] = []

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            if "word/document.xml" not in zf.namelist():
                return Stage1Result(
                    filename=filename,
                    file_type="docx",
                    warnings=["Invalid DOCX file: word/document.xml not found."],
                )
            doc_xml = zf.read("word/document.xml")
    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="docx",
            warnings=[f"Failed to read DOCX archive: {exc}"],
        )

    try:
        root = ET.fromstring(doc_xml)
    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="docx",
            warnings=[f"Failed to parse DOCX XML: {exc}"],
        )

    # 1. Search for all <w:tbl> elements
    xml_tables = root.findall(".//w:tbl", _NAMESPACES)
    table_index = 0

    for tbl_idx, tbl_elem in enumerate(xml_tables):
        rows_data: list[list[str]] = []
        for tr in tbl_elem.findall("./w:tr", _NAMESPACES):
            row_cells: list[str] = []
            for tc in tr.findall("./w:tc", _NAMESPACES):
                # Extract all text within the cell
                cell_text = "".join(
                    t.text or "" for t in tc.findall(".//w:t", _NAMESPACES)
                ).strip()
                row_cells.append(cell_text)
            if any(c for c in row_cells):
                rows_data.append(row_cells)

        if not rows_data:
            continue

        # Header row is the first row
        header_raw = rows_data[0]
        headers = [
            h if h else f"Col_{ci}"
            for ci, h in enumerate(header_raw)
        ]
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

        tables.append(RawTable(
            table_index=table_index,
            source_sheet=f"Table {table_index + 1}",
            extraction_method=ExtractionMethod.DOCX_TABLE,
            headers=headers,
            rows=rows,
        ))
        table_index += 1

    # 2. If no tables found, extract document paragraphs as a structured table
    if not tables:
        para_rows: list[RawRow] = []
        p_elements = root.findall(".//w:p", _NAMESPACES)
        for pi, p in enumerate(p_elements):
            text = "".join(t.text or "" for t in p.findall(".//w:t", _NAMESPACES)).strip()
            if not text:
                continue
            words = len(text.split())
            cells = [
                RawCell(col_index=0, value=len(para_rows) + 1, raw_text=str(len(para_rows) + 1)),
                RawCell(col_index=1, value=text, raw_text=text),
                RawCell(col_index=2, value=words, raw_text=str(words)),
            ]
            para_rows.append(RawRow(
                row_index=len(para_rows),
                source_line=pi + 1,
                raw_text=text,
                cells=cells,
            ))

        if para_rows:
            tables.append(RawTable(
                table_index=0,
                source_sheet="Document Content",
                extraction_method=ExtractionMethod.DOCX_TABLE,
                headers=["Paragraph_No", "Content", "Word_Count"],
                rows=para_rows,
            ))
            warnings.append("No embedded tables detected; extracted document paragraphs as structured records.")

    return Stage1Result(
        filename=filename,
        file_type="docx",
        tables=tables,
        warnings=warnings,
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
