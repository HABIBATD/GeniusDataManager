"""
Stage 1 — Image & Scanned Document Extractor
==============================================
Extracts:
  - OCR text and detected tables from PNG, JPG, JPEG, WEBP, BMP, TIFF.
  - Image properties and structural metadata.
Uses Pillow and pytesseract (with graceful fallback if tesseract binary is uninstalled).
"""

import io
import logging
from typing import Any

from PIL import Image

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_image(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract data from images using Pillow and optional OCR.
    """
    warnings: list[str] = []
    tables: list[RawTable] = []

    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
        img_format = img.format or "UNKNOWN"
        mode = img.mode
    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="image",
            warnings=[f"Failed to decode image: {exc}"],
        )

    # 1. Try OCR via pytesseract
    ocr_lines: list[str] = []
    try:
        import pytesseract
        ocr_text = pytesseract.image_to_string(img)
        if ocr_text.strip():
            ocr_lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    except Exception as ocr_err:
        warnings.append(f"OCR note: {ocr_err}")

    if ocr_lines:
        # Check if lines have multiple columns (separated by multiple spaces or tabs)
        rows_data: list[list[str]] = []
        for line in ocr_lines:
            parts = [p.strip() for p in line.split("  ") if p.strip()]
            if not parts:
                parts = [line]
            rows_data.append(parts)

        # Common column width
        col_lens = [len(r) for r in rows_data]
        max_cols = max(col_lens) if col_lens else 1

        headers = [f"Col_{i + 1}" for i in range(max_cols)]
        if rows_data:
            headers = [h if h else f"Col_{i + 1}" for i, h in enumerate(rows_data[0])]

        rows: list[RawRow] = []
        for ri, r in enumerate(rows_data[1:] if len(rows_data) > 1 else rows_data):
            padded = (r + [""] * len(headers))[:len(headers)]
            cells = [
                RawCell(col_index=ci, value=val, raw_text=val)
                for ci, val in enumerate(padded)
            ]
            rows.append(RawRow(
                row_index=ri,
                source_line=ri + 1,
                raw_text=" | ".join(padded),
                cells=cells,
            ))

        tables.append(RawTable(
            table_index=0,
            source_sheet="OCR Extracted Text",
            extraction_method=ExtractionMethod.IMAGE_OCR,
            headers=headers,
            rows=rows,
        ))
    else:
        # Structured metadata table
        headers = ["Property", "Value"]
        meta_items = [
            ("Filename", filename),
            ("Format", img_format),
            ("Dimensions", f"{width} × {height} px"),
            ("Color Mode", mode),
            ("Size (KB)", f"{len(file_bytes) / 1024:.1f} KB"),
        ]
        rows = [
            RawRow(
                row_index=idx,
                source_line=idx + 1,
                raw_text=f"{k}: {v}",
                cells=[
                    RawCell(col_index=0, value=k, raw_text=k),
                    RawCell(col_index=1, value=v, raw_text=v),
                ],
            )
            for idx, (k, v) in enumerate(meta_items)
        ]
        tables.append(RawTable(
            table_index=0,
            source_sheet="Image Metadata",
            extraction_method=ExtractionMethod.IMAGE_OCR,
            headers=headers,
            rows=rows,
        ))
        warnings.append("No text could be extracted via OCR; extracted image metadata properties.")

    return Stage1Result(
        filename=filename,
        file_type="image",
        tables=tables,
        warnings=warnings,
    )
