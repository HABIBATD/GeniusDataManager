"""
Stage 5 — CSV Exporter
========================
Produces a flat CSV containing only the DETAIL rows from all tables
merged into a single file.

Each row gets additional columns:
  _table_index   — which source table it came from
  _source_page   — PDF page (if applicable)
  _source_sheet  — XLSX sheet name (if applicable)
  _row_role      — always "detail" (only detail rows exported)
"""

import csv
import io

from models.intermediate import PipelineResult, RowRole


def export_csv(result: PipelineResult) -> bytes:
    """
    Build and return a flat UTF-8 CSV (with BOM for Excel compatibility) as bytes.
    """
    buf = io.StringIO()

    if not result.stage1 or not result.stage1.tables:
        buf.write("# No tables extracted.\n")
        return buf.getvalue().encode("utf-8-sig")

    # Determine row roles per table from stage2 (fall back to all DETAIL if unavailable)
    role_map: dict[int, list[RowRole]] = {}
    if result.stage2:
        for tp in result.stage2.table_profiles:
            role_map[tp.table_index] = tp.row_roles

    # Collect all headers (prefix with table index if multiple tables to avoid collision)
    multi_table = len(result.stage1.tables) > 1

    # We write a single unified CSV. When multiple tables share the same headers, rows merge
    # cleanly. When headers differ, missing columns are left blank.
    all_headers_ordered: list[str] = []
    seen_headers: set[str] = set()
    per_table_headers: dict[int, list[str]] = {}

    for raw_table in result.stage1.tables:
        hdrs = raw_table.headers
        per_table_headers[raw_table.table_index] = hdrs
        for h in hdrs:
            if h not in seen_headers:
                all_headers_ordered.append(h)
                seen_headers.add(h)

    # Meta columns
    meta_cols = ["_table_index", "_source_sheet", "_source_page", "_row_index"]
    full_headers = meta_cols + all_headers_ordered

    writer = csv.DictWriter(buf, fieldnames=full_headers, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()

    for raw_table in result.stage1.tables:
        roles = role_map.get(raw_table.table_index, [RowRole.DETAIL] * len(raw_table.rows))
        hdrs = per_table_headers[raw_table.table_index]

        for raw_row, role in zip(raw_table.rows, roles):
            if role != RowRole.DETAIL:
                continue  # flat CSV = detail rows only

            row_dict: dict[str, object] = {
                "_table_index":  raw_table.table_index,
                "_source_sheet": raw_table.source_sheet or "",
                "_source_page":  raw_table.source_page or "",
                "_row_index":    raw_row.row_index,
            }
            for ci, hdr in enumerate(hdrs):
                val = raw_row.cells[ci].value if ci < len(raw_row.cells) else None
                row_dict[hdr] = val if val is not None else ""

            writer.writerow(row_dict)

    # Return UTF-8 with BOM (Excel-friendly)
    return buf.getvalue().encode("utf-8-sig")
