"""
Stage 5 — XLSX Exporter
=========================
Produces a workbook where:
  - Each detected RawTable becomes its own sheet.
  - Headers are bold, frozen on row 1.
  - Detail rows are written first, then subtotal rows (highlighted blue/grey),
    then grand_total rows (highlighted darker).
  - Columns flagged as computed (is_computed_column=True) get =SUM() Excel
    formulas instead of raw values — so the recipient can verify totals in Excel.
  - Anomaly cells are highlighted red.
  - Mismatch cells are highlighted amber.
"""

import io
from typing import Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from models.intermediate import (
    Anomaly,
    ColumnType,
    ComputedColumnMismatch,
    PipelineResult,
    RowRole,
    Stage2Result,
    TableProfile,
)


# ── Colour palette ────────────────────────────────────────────────────────────
_CLR_HEADER_BG     = "1A1A2E"   # dark navy
_CLR_HEADER_FG     = "FFFFFF"
_CLR_SUBTOTAL_BG   = "D6E4F0"
_CLR_GRANDTOTAL_BG = "AED6F1"
_CLR_COMPUTED_BG   = "FFF9C4"   # pale yellow — computed col cells
_CLR_MISMATCH_BG   = "FFCC80"   # amber — mismatch cells
_CLR_ANOMALY_BG    = "FFCDD2"   # light red — anomaly cells
_CLR_ODD_ROW       = "F8F9FA"
_CLR_EVEN_ROW      = "FFFFFF"

_FILL = lambda hex_: PatternFill("solid", fgColor=hex_)
_THIN = Side(style="thin", color="CCCCCC")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def export_xlsx(result: PipelineResult) -> bytes:
    """
    Build and return a .xlsx file as bytes from the PipelineResult.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove the default empty sheet

    if not result.stage1 or not result.stage1.tables:
        ws = wb.create_sheet("No Data")
        ws["A1"] = "No tables were extracted from this file."
        return _workbook_bytes(wb)

    stage2 = result.stage2
    table_profiles: dict[int, TableProfile] = {}
    if stage2:
        for tp in stage2.table_profiles:
            table_profiles[tp.table_index] = tp

    for raw_table in result.stage1.tables:
        tp = table_profiles.get(raw_table.table_index)
        sheet_name = _make_sheet_name(raw_table, wb)
        ws = wb.create_sheet(sheet_name)

        headers = raw_table.headers
        num_cols = len(headers)

        # Determine row roles
        row_roles: list[RowRole] = []
        if tp and tp.row_roles:
            row_roles = tp.row_roles
        else:
            row_roles = [RowRole.DETAIL] * len(raw_table.rows)

        # Computed column indices
        computed_col_indices: set[int] = set()
        if tp:
            for cp in tp.column_profiles:
                if cp.is_computed_column:
                    computed_col_indices.add(cp.col_index)

        # Build anomaly/mismatch cell lookup {(row_0based, col_0based) -> "anomaly"|"mismatch"}
        flagged: dict[tuple[int, int], str] = {}
        if tp:
            for a in tp.anomalies:
                if a.row_index is not None and a.col_index is not None:
                    flagged[(a.row_index, a.col_index)] = "anomaly"
            for m in tp.computed_column_mismatches:
                # find the column index matching the mismatch header
                mismatch_col = next(
                    (cp.col_index for cp in (tp.column_profiles or []) if cp.header == m.column_header),
                    None,
                )
                if mismatch_col is not None:
                    flagged[(m.row_index, mismatch_col)] = "mismatch"

        # ── Write header row ─────────────────────────────────────────
        for ci, hdr in enumerate(headers):
            cell = ws.cell(row=1, column=ci + 1, value=hdr)
            cell.font = Font(bold=True, color=_CLR_HEADER_FG, name="Calibri", size=10)
            cell.fill = _FILL(_CLR_HEADER_BG)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = _BORDER

        ws.row_dimensions[1].height = 28
        ws.freeze_panes = "A2"

        # ── Write data rows ─────────────────────────────────────────
        excel_row = 2
        for row_0based, (raw_row, role) in enumerate(zip(raw_table.rows, row_roles)):
            # Determine row fill
            if role == RowRole.GRAND_TOTAL:
                row_fill = _FILL(_CLR_GRANDTOTAL_BG)
                row_bold = True
            elif role in (RowRole.SUBTOTAL,):
                row_fill = _FILL(_CLR_SUBTOTAL_BG)
                row_bold = True
            elif role == RowRole.SECTION_HEADER:
                row_fill = _FILL(_CLR_SUBTOTAL_BG)
                row_bold = True
            elif excel_row % 2 == 0:
                row_fill = _FILL(_CLR_ODD_ROW)
                row_bold = False
            else:
                row_fill = _FILL(_CLR_EVEN_ROW)
                row_bold = False

            for ci in range(num_cols):
                raw_val = raw_row.cells[ci].value if ci < len(raw_row.cells) else None
                cell = ws.cell(row=excel_row, column=ci + 1)

                # For computed columns in DETAIL rows, write =SUM() formula
                if ci in computed_col_indices and role == RowRole.DETAIL:
                    # Find the addend column indices (non-computed numeric/currency)
                    addend_cols = []
                    if tp:
                        addend_cols = [
                            cp.col_index for cp in tp.column_profiles
                            if cp.col_index not in computed_col_indices
                            and cp.inferred_type in (ColumnType.NUMERIC, ColumnType.CURRENCY, ColumnType.TIME_PERIOD)
                        ]
                    if addend_cols:
                        col_refs = "+".join(
                            f"{get_column_letter(ac + 1)}{excel_row}"
                            for ac in addend_cols
                        )
                        cell.value = f"={col_refs}"
                        cell.fill = _FILL(_CLR_COMPUTED_BG)
                    else:
                        cell.value = raw_val
                        cell.fill = row_fill
                else:
                    cell.value = raw_val
                    # Override fill for flagged cells
                    flag = flagged.get((row_0based, ci))
                    if flag == "anomaly":
                        cell.fill = _FILL(_CLR_ANOMALY_BG)
                    elif flag == "mismatch":
                        cell.fill = _FILL(_CLR_MISMATCH_BG)
                    else:
                        cell.fill = row_fill

                cell.font = Font(bold=row_bold, name="Calibri", size=10)
                cell.border = _BORDER
                cell.alignment = Alignment(vertical="center")

            excel_row += 1

        # ── Column widths (auto-fit estimate) ─────────────────────
        for ci, hdr in enumerate(headers):
            max_len = max(len(str(hdr)), 8)
            for raw_row in raw_table.rows:
                if ci < len(raw_row.cells):
                    v = raw_row.cells[ci].value
                    max_len = max(max_len, min(len(str(v or "")), 40))
            ws.column_dimensions[get_column_letter(ci + 1)].width = max_len + 2

    # ── Legend sheet ─────────────────────────────────────────────
    _add_legend_sheet(wb, result)

    return _workbook_bytes(wb)


def _add_legend_sheet(wb: openpyxl.Workbook, result: PipelineResult) -> None:
    ws = wb.create_sheet("📋 Legend")
    items = [
        ("Colour Legend", ""),
        ("Dark navy header", _CLR_HEADER_BG),
        ("Computed column cell (=SUM formula written)", _CLR_COMPUTED_BG),
        ("Subtotal / Section header row", _CLR_SUBTOTAL_BG),
        ("Grand Total row", _CLR_GRANDTOTAL_BG),
        ("Anomaly cell", _CLR_ANOMALY_BG),
        ("Computed column mismatch cell", _CLR_MISMATCH_BG),
        ("", ""),
        ("File", result.filename),
        ("Status", result.status),
        ("Task ID", result.task_id),
    ]
    for r, (label, note) in enumerate(items, 1):
        ws.cell(r, 1, label).font = Font(bold=(r == 1), name="Calibri")
        if note and len(note) == 6 and all(c in "0123456789ABCDEF" for c in note):
            ws.cell(r, 2).fill = _FILL(note)
            ws.cell(r, 2, " ").font = Font(name="Calibri")
        elif note:
            ws.cell(r, 2, note).font = Font(name="Calibri")
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 20


def _make_sheet_name(raw_table, wb: openpyxl.Workbook) -> str:
    """Create a valid, unique Excel sheet name."""
    base = raw_table.source_sheet or f"Table {raw_table.table_index + 1}"
    # Excel sheet names max 31 chars, no invalid chars
    name = re.sub(r"[\\/*?\[\]:]", "_", base)[:31]
    existing = {s.title for s in wb.worksheets}
    if name not in existing:
        return name
    for i in range(2, 99):
        candidate = f"{name[:27]}_{i}"
        if candidate not in existing:
            return candidate
    return f"Sheet_{raw_table.table_index}"


def _workbook_bytes(wb: openpyxl.Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


import re  # noqa: E402 (placed at bottom to keep top of file readable)
