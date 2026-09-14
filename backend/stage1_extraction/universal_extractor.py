"""
Stage 1 — Universal Master Extractor
======================================
Intelligent routing engine for ANY incoming file.
Dispatches based on extension and magic bytes to specialized extractors:
  - PDF: Native text, borderless tables, OCR fallback
  - Spreadsheets: XLSX, XLS
  - Delimited & Text: CSV, TSV, TXT, LOG, Markdown, Configs, SQL, MD
  - Hierarchical / Data: JSON, JSONL, NDJSON, GeoJSON, XML, HTML
  - Office Documents: Word DOCX, PowerPoint PPTX
  - Databases: SQLite (.db, .sqlite, .sqlite3)
  - Archives: ZIP (recursively unpacks and extracts all contained data)
  - Media: PNG, JPG, JPEG, WEBP, BMP, TIFF (OCR + metadata)
  - Universal Sniffer Fallback: Inspects arbitrary files, never fails!
"""

import io
import logging
import re
from pathlib import Path
from typing import Any

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)
from stage1_extraction.pdf_extractor import extract_pdf
from stage1_extraction.csv_extractor import extract_csv
from stage1_extraction.xlsx_extractor import extract_xlsx
from stage1_extraction.json_extractor import extract_json
from stage1_extraction.text_extractor import extract_text
from stage1_extraction.docx_extractor import extract_docx
from stage1_extraction.pptx_extractor import extract_pptx
from stage1_extraction.sqlite_extractor import extract_sqlite
from stage1_extraction.xml_html_extractor import extract_xml_html
from stage1_extraction.image_extractor import extract_image
from stage1_extraction.archive_extractor import extract_archive

logger = logging.getLogger(__name__)


def extract_universal(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Master universal extractor. Automatically routes any file to the appropriate
    specialized extraction engine or intelligent sniffer.
    """
    if not file_bytes:
        return Stage1Result(
            filename=filename,
            file_type="empty",
            warnings=["Uploaded file is empty (0 bytes)."],
        )

    ext = Path(filename).suffix.lower()
    magic = file_bytes[:16]

    # --- 1. Check Magic Signatures (takes precedence if extension is misleading) ---
    if magic.startswith(b"%PDF"):
        return extract_pdf(file_bytes, filename)

    if magic.startswith(b"SQLite format 3"):
        return extract_sqlite(file_bytes, filename)

    if magic.startswith(b"\x89PNG\r\n\x1a\n") or magic.startswith(b"\xff\xd8\xff") or magic.startswith(b"RIFF"):
        return extract_image(file_bytes, filename)

    # --- 2. Extension-based routing ---
    if ext == ".pdf":
        return extract_pdf(file_bytes, filename)

    if ext in (".xlsx", ".xls"):
        return extract_xlsx(file_bytes, filename)

    if ext == ".csv":
        return extract_csv(file_bytes, filename)

    if ext in (".json", ".jsonl", ".ndjson", ".geojson"):
        return extract_json(file_bytes, filename)

    if ext == ".docx":
        return extract_docx(file_bytes, filename)

    if ext == ".pptx":
        return extract_pptx(file_bytes, filename)

    if ext in (".db", ".sqlite", ".sqlite3"):
        return extract_sqlite(file_bytes, filename)

    if ext in (".xml", ".html", ".htm"):
        return extract_xml_html(file_bytes, filename)

    if ext == ".zip":
        return extract_archive(file_bytes, filename, extract_universal)

    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
        return extract_image(file_bytes, filename)

    if ext in (".txt", ".tsv", ".tab", ".log", ".dat", ".env", ".ini", ".conf", ".sql", ".md", ".yaml", ".yml"):
        return extract_text(file_bytes, filename)

    # ZIP container check (DOCX and PPTX are ZIPs too, but if extension is missing/unknown)
    if magic.startswith(b"PK\x03\x04"):
        # Check if it contains word/document.xml
        try:
            import zipfile
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                names = zf.namelist()
                if "word/document.xml" in names:
                    return extract_docx(file_bytes, filename)
                if "ppt/presentation.xml" in names:
                    return extract_pptx(file_bytes, filename)
                if "xl/workbook.xml" in names:
                    return extract_xlsx(file_bytes, filename)
                return extract_archive(file_bytes, filename, extract_universal)
        except Exception:
            pass

    # --- 3. Intelligent Sniffer Fallback for Unknown / Arbitrary Files ---
    logger.info("Running universal sniffer fallback on unknown file: %s", filename)
    return _sniff_and_extract(file_bytes, filename)


def _sniff_and_extract(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Intelligently analyzes arbitrary file bytes:
      - Tests if decodable text:
        * If starts with '{' or '[' -> JSON
        * If starts with '<' -> XML / HTML
        * Otherwise -> Text / Delimited
      - If raw binary -> Extracts printable strings & byte frequency profile.
    """
    # Try decoding as text
    text: str | None = None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is not None:
        stripped = text.strip()
        # Is it JSON?
        if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            res = extract_json(file_bytes, filename)
            res.warnings.append("Auto-detected as JSON data by universal sniffer.")
            return res

        # Is it XML / HTML?
        if stripped.startswith("<") and stripped.endswith(">"):
            res = extract_xml_html(file_bytes, filename)
            res.warnings.append("Auto-detected as XML/HTML by universal sniffer.")
            return res

        # Standard text / delimited
        res = extract_text(file_bytes, filename)
        res.warnings.append("Auto-detected as structured text by universal sniffer.")
        return res

    # Pure binary fallback
    return _extract_binary_profile(file_bytes, filename)


def _extract_binary_profile(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    For completely unparseable binary files, extracts printable string tokens
    and binary profile segments into a structured table.
    """
    # Extract ASCII strings of length >= 4
    pattern = re.compile(rb"[\x20-\x7E]{4,}")
    matches = pattern.findall(file_bytes)
    extracted_strings = [m.decode("ascii", errors="ignore") for m in matches[:1000]]

    rows: list[RawRow] = []
    if extracted_strings:
        headers = ["Index", "Extracted_Token", "Length", "Category"]
        for ri, s in enumerate(extracted_strings):
            cat = "Path/URL" if ("/" in s or "\\" in s) else ("Identifier" if re.match(r"^\w+$", s) else "Text")
            cells = [
                RawCell(col_index=0, value=ri + 1, raw_text=str(ri + 1)),
                RawCell(col_index=1, value=s, raw_text=s),
                RawCell(col_index=2, value=len(s), raw_text=str(len(s))),
                RawCell(col_index=3, value=cat, raw_text=cat),
            ]
            rows.append(RawRow(
                row_index=ri,
                source_line=ri + 1,
                raw_text=f"{ri + 1}: {s}",
                cells=cells,
            ))
    else:
        headers = ["Offset_Hex", "Byte_Count", "Hex_Snippet"]
        chunk_size = 32
        for ci in range(0, min(len(file_bytes), 3200), chunk_size):
            chunk = file_bytes[ci:ci + chunk_size]
            hex_str = " ".join(f"{b:02X}" for b in chunk)
            cells = [
                RawCell(col_index=0, value=f"0x{ci:06X}", raw_text=f"0x{ci:06X}"),
                RawCell(col_index=1, value=len(chunk), raw_text=str(len(chunk))),
                RawCell(col_index=2, value=hex_str, raw_text=hex_str),
            ]
            rows.append(RawRow(
                row_index=len(rows),
                source_line=len(rows) + 1,
                raw_text=hex_str,
                cells=cells,
            ))

    table = RawTable(
        table_index=0,
        source_sheet="Binary Profile",
        extraction_method=ExtractionMethod.UNIVERSAL_SNIFFER,
        headers=headers,
        rows=rows,
    )

    return Stage1Result(
        filename=filename,
        file_type="binary",
        tables=[table],
        warnings=["Processed unrecognized binary file using string extraction and byte profiling."],
    )
