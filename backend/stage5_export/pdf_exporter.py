"""
Stage 5 — PDF Exporter
========================
Produces a structured PDF report using ReportLab (already in requirements).

Report structure:
  Page 1: Cover — filename, status, summary stats
  Per-table section:
    - Table info (source page/sheet, row counts, grain description)
    - Column profiles table
    - Time structure (if detected)
    - Anomalies list
    - Computed column mismatches table
  Final page: Warnings
"""

import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

from models.intermediate import PipelineResult, TableProfile, RowRole


# ── Colour palette ────────────────────────────────────────────────────────────
_NAVY    = colors.HexColor("#1A1A2E")
_ACCENT  = colors.HexColor("#7C3AED")
_SUCCESS = colors.HexColor("#10B981")
_WARNING = colors.HexColor("#F59E0B")
_DANGER  = colors.HexColor("#EF4444")
_MUTED   = colors.HexColor("#6B7280")
_LIGHT   = colors.HexColor("#F3F4F6")
_WHITE   = colors.white


def export_pdf(result: PipelineResult) -> bytes:
    """Build and return a PDF report as bytes."""
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        title=f"GeniusDataManager — {result.filename}",
        author="GeniusDataManager",
    )

    W, H = A4
    inner_w = W - 40 * mm

    # ── Page templates ────────────────────────────────────────────────────────
    def _header_footer(canvas, doc):
        canvas.saveState()
        # Header bar
        canvas.setFillColor(_NAVY)
        canvas.rect(0, H - 18 * mm, W, 18 * mm, fill=1, stroke=0)
        canvas.setFillColor(_WHITE)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(20 * mm, H - 12 * mm, "GeniusDataManager — Data Profile Report")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(W - 20 * mm, H - 12 * mm, result.filename[:60])
        # Footer
        canvas.setFillColor(_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(20 * mm, 10 * mm,
                          f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Task: {result.task_id[:24]}…")
        canvas.drawRightString(W - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    frame = Frame(20 * mm, 20 * mm, inner_w, H - 45 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_header_footer)])

    styles = getSampleStyleSheet()
    story = []

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph(
        f"<font color='#{_NAVY.hexval()[2:]}' size='24'><b>Data Profile Report</b></font>",
        ParagraphStyle("cover_title", fontSize=24, textColor=_NAVY, spaceAfter=8, alignment=TA_CENTER),
    ))
    story.append(Paragraph(
        result.filename,
        ParagraphStyle("cover_file", fontSize=13, textColor=_MUTED, spaceAfter=30, alignment=TA_CENTER),
    ))

    # Summary stats table
    s2 = result.stage2
    stats = [
        ["Status",   result.status.upper()],
        ["Tables",   str(s2.total_tables) if s2 else "—"],
        ["Detail Rows", str(s2.total_detail_rows) if s2 else "—"],
        ["Categories", str(s2.total_categories) if s2 else "—"],
        ["Anomalies", str(s2.total_anomalies) if s2 else "—"],
        ["Mismatches", str(s2.total_mismatches) if s2 else "—"],
    ]
    stats_tbl = Table(stats, colWidths=[inner_w * 0.4, inner_w * 0.6])
    stats_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _LIGHT),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",   (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_WHITE, _LIGHT]),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(stats_tbl)
    story.append(Spacer(1, 12))

    # Human summary
    if s2 and s2.human_summary:
        story.append(Paragraph("AI Summary", _h3_style()))
        story.append(Paragraph(
            s2.human_summary.replace("\n", "<br/>"),
            ParagraphStyle("summary", fontSize=8, textColor=_MUTED,
                           backColor=colors.HexColor("#F8F9FA"),
                           borderPad=8, borderRadius=4, spaceAfter=12,
                           leftIndent=8, rightIndent=8, leading=13),
        ))

    story.append(PageBreak())

    # ── Per-table sections ────────────────────────────────────────────────────
    if result.stage1 and result.stage2:
        tp_map = {tp.table_index: tp for tp in result.stage2.table_profiles}
        for raw_table in result.stage1.tables:
            tp = tp_map.get(raw_table.table_index)
            _add_table_section(story, raw_table, tp, inner_w)

    # ── Warnings ─────────────────────────────────────────────────────────────
    warnings = []
    if result.stage1:
        warnings.extend(result.stage1.warnings)
    if result.stage2:
        warnings.extend(result.stage2.warnings)
    if warnings:
        story.append(Paragraph("⚠ Warnings", _h2_style()))
        for w in warnings:
            story.append(Paragraph(f"• {w}", _body_style()))

    doc.build(story)
    return buf.getvalue()


def _add_table_section(story, raw_table, tp, inner_w):
    sheet_info = f" — Sheet: {raw_table.source_sheet}" if raw_table.source_sheet else ""
    page_info  = f" — Page {raw_table.source_page}"   if raw_table.source_page  else ""
    story.append(Paragraph(
        f"Table {raw_table.table_index + 1}{sheet_info}{page_info}",
        _h2_style(),
    ))

    if tp:
        # Basic stats row
        meta = [
            ["Detail rows", str(tp.detail_row_count)],
            ["Subtotal/Grand-total rows", str(tp.subtotal_row_count)],
            ["Section headers", str(tp.section_header_count)],
            ["Hierarchy detected", "Yes" if tp.has_hierarchy else "No"],
        ]
        if tp.time_structure:
            ts = tp.time_structure
            meta.append(["Time structure",
                          f"{ts.get('period_type')}, {ts.get('start')} → {ts.get('end')} ({ts.get('count')} periods)"])
        meta_tbl = Table(meta, colWidths=[inner_w * 0.45, inner_w * 0.55])
        meta_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_WHITE, _LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(meta_tbl)
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Grain:</b> {tp.grain_description}", _small_style()))
        story.append(Spacer(1, 10))

        # Column profiles table
        story.append(Paragraph("Column Profiles", _h3_style()))
        col_data = [["#", "Header", "Type", "Confidence", "Nulls", "Computed?"]]
        for cp in tp.column_profiles:
            col_data.append([
                str(cp.col_index),
                cp.header[:30],
                cp.inferred_type,
                f"{int(cp.type_confidence * 100)}%",
                str(cp.null_count),
                "⚠ Yes" if cp.is_computed_column else "—",
            ])
        col_tbl = Table(col_data, colWidths=[
            inner_w * 0.05, inner_w * 0.28, inner_w * 0.16,
            inner_w * 0.12, inner_w * 0.08, inner_w * 0.10,
        ])
        col_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR",  (0, 0), (-1, 0), _WHITE),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (3, 1), (4, -1), "CENTER"),
        ]))
        story.append(col_tbl)
        story.append(Spacer(1, 10))

        # Anomalies
        if tp.anomalies:
            story.append(Paragraph(f"🔍 Anomalies ({len(tp.anomalies)})", _h3_style()))
            anom_data = [["Type", "Description", "Row", "Col"]]
            for a in tp.anomalies[:20]:
                anom_data.append([
                    a.anomaly_type.replace("_", " "),
                    a.description[:60],
                    str(a.row_index) if a.row_index is not None else "—",
                    a.col_header or "—",
                ])
            anom_tbl = Table(anom_data, colWidths=[
                inner_w * 0.22, inner_w * 0.50, inner_w * 0.12, inner_w * 0.16,
            ])
            anom_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EF4444")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), _WHITE),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, colors.HexColor("#FEF2F2")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#FECACA")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(anom_tbl)
            if len(tp.anomalies) > 20:
                story.append(Paragraph(f"… and {len(tp.anomalies) - 20} more (see JSON export).", _small_style()))
            story.append(Spacer(1, 10))

        # Mismatches
        if tp.computed_column_mismatches:
            story.append(Paragraph(f"⚠ Computed Column Mismatches ({len(tp.computed_column_mismatches)})", _h3_style()))
            mism_data = [["Row", "Column", "Source Value", "Recomputed", "Delta"]]
            for m in tp.computed_column_mismatches[:20]:
                mism_data.append([
                    m.row_description[:24],
                    m.column_header[:20],
                    f"{m.source_value:,.2f}" if m.source_value is not None else "—",
                    f"{m.recomputed_value:,.2f}" if m.recomputed_value is not None else "—",
                    f"{m.delta:+,.2f}" if m.delta is not None else "—",
                ])
            mism_tbl = Table(mism_data, colWidths=[
                inner_w * 0.22, inner_w * 0.22, inner_w * 0.18, inner_w * 0.18, inner_w * 0.20,
            ])
            mism_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F59E0B")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), _WHITE),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, colors.HexColor("#FFFBEB")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#FDE68A")),
                ("ALIGN",      (2, 1), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(mism_tbl)
            if len(tp.computed_column_mismatches) > 20:
                story.append(Paragraph(f"… and {len(tp.computed_column_mismatches) - 20} more.", _small_style()))
            story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB"), spaceAfter=16))


# ── Style helpers ─────────────────────────────────────────────────────────────

def _h2_style():
    return ParagraphStyle(
        "h2", fontSize=13, fontName="Helvetica-Bold",
        textColor=_NAVY, spaceBefore=16, spaceAfter=8,
    )

def _h3_style():
    return ParagraphStyle(
        "h3", fontSize=10, fontName="Helvetica-Bold",
        textColor=_ACCENT, spaceBefore=10, spaceAfter=6,
    )

def _body_style():
    return ParagraphStyle(
        "body", fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#374151"), spaceAfter=4, leading=14,
    )

def _small_style():
    return ParagraphStyle(
        "small", fontSize=8, fontName="Helvetica",
        textColor=_MUTED, spaceAfter=4, leading=12,
    )
