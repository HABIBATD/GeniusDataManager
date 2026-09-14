"""
Stage 1 — PowerPoint (.pptx) Extractor
========================================
Extracts:
  - Tables from all slides using python-pptx.
  - Slide titles, bullet points, and shape text as structured records.
"""

import io
import logging
import re
from typing import Any

from pptx import Presentation

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_pptx(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract tables and structured slide text from a PPTX file.
    """
    warnings: list[str] = []
    tables: list[RawTable] = []

    try:
        prs = Presentation(io.BytesIO(file_bytes))
    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="pptx",
            warnings=[f"Failed to load PowerPoint presentation: {exc}"],
        )

    table_index = 0
    all_slide_text: list[dict] = []

    for slide_idx, slide in enumerate(prs.slides, start=1):
        # 1. Search for table shapes
        for shape in slide.shapes:
            if shape.has_table:
                table_shape = shape.table
                rows_data: list[list[str]] = []
                for row in table_shape.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    if any(c for c in row_cells):
                        rows_data.append(row_cells)

                if rows_data:
                    headers = [h if h else f"Col_{ci}" for ci, h in enumerate(rows_data[0])]
                    num_cols = len(headers)
                    raw_rows: list[RawRow] = []

                    for ri, r in enumerate(rows_data[1:]):
                        padded = (r + [""] * num_cols)[:num_cols]
                        cells = [
                            RawCell(col_index=ci, value=_coerce_val(val), raw_text=val)
                            for ci, val in enumerate(padded)
                        ]
                        raw_rows.append(RawRow(
                            row_index=ri,
                            source_page=slide_idx,
                            source_line=ri + 1,
                            raw_text=" | ".join(padded),
                            cells=cells,
                        ))

                    tables.append(RawTable(
                        table_index=table_index,
                        source_page=slide_idx,
                        source_sheet=f"Slide {slide_idx} Table {table_index + 1}",
                        extraction_method=ExtractionMethod.PPTX_TABLE,
                        headers=headers,
                        rows=raw_rows,
                    ))
                    table_index += 1

            elif shape.has_text_frame:
                txt = shape.text_frame.text.strip()
                if txt:
                    shape_name = shape.name or "Text"
                    all_slide_text.append({
                        "Slide": slide_idx,
                        "Shape_Type": shape_name,
                        "Content": txt,
                        "Word_Count": len(txt.split()),
                    })

    # If no tables found, produce a structured table of slide texts
    if not tables and all_slide_text:
        headers = ["Slide", "Shape_Type", "Content", "Word_Count"]
        rows: list[RawRow] = []
        for ri, item in enumerate(all_slide_text):
            cells = [
                RawCell(col_index=0, value=item["Slide"], raw_text=str(item["Slide"])),
                RawCell(col_index=1, value=item["Shape_Type"], raw_text=item["Shape_Type"]),
                RawCell(col_index=2, value=item["Content"], raw_text=item["Content"]),
                RawCell(col_index=3, value=item["Word_Count"], raw_text=str(item["Word_Count"])),
            ]
            rows.append(RawRow(
                row_index=ri,
                source_page=item["Slide"],
                source_line=ri + 1,
                raw_text=f"Slide {item['Slide']}: {item['Content']}",
                cells=cells,
            ))

        tables.append(RawTable(
            table_index=0,
            source_sheet="Slide Contents",
            extraction_method=ExtractionMethod.PPTX_TABLE,
            headers=headers,
            rows=rows,
        ))
        warnings.append("No embedded tables found in PPTX; extracted slide texts as structured records.")

    return Stage1Result(
        filename=filename,
        file_type="pptx",
        total_pages=len(prs.slides),
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
