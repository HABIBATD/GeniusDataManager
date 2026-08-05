"""
Stage 2 — Master Profiler
===========================
Orchestrates all Stage 2 sub-modules and produces the final Stage2Result.

Also handles pre-existing computed column validation:
  - Detects columns whose header suggests they are pre-computed totals
    (headers containing Total/Sum/YTD/H1/H2/etc.).
  - For each detected computed column, recomputes the sum from DETAIL rows only
    (excluding SUBTOTAL/GRAND_TOTAL rows to avoid double-counting).
  - Compares the source file's value against the recomputed value.
  - CRITICAL RULE: Every comparison states explicitly which value comes from where.
    This rule exists because the original bug in this project came from comparing
    two derived sums against each other without clearly documenting their origins,
    causing 181 false "validation failures."

Grain detection (what does one row represent?):
  - Heuristic: look at the first identifier/category column. If unique values = total rows,
    grain is "one row = one [first column header] record."
  - If time structure detected, grain is "one row = one [category] per [period]."
"""

import re
import statistics
from typing import Any, Optional

from models.intermediate import (
    Anomaly,
    ColumnProfile,
    ColumnType,
    ComputedColumnMismatch,
    RawRow,
    RawTable,
    RowRole,
    Stage1Result,
    Stage2Result,
    TableProfile,
)
from stage2_profiling.type_inferrer import infer_column_type
from stage2_profiling.hierarchy_detector import assign_row_roles, has_hierarchy
from stage2_profiling.time_detector import detect_time_structure
from stage2_profiling.anomaly_detector import detect_anomalies

# Pattern for computed column header detection
_COMPUTED_HEADER_PATTERN = re.compile(
    r"""(
      \btotal[s]?\b |
      \bsubtotal[s]?\b |
      \bsum\b |
      \bYTD\b |
      \bH1\b | \bH2\b |   # half-year
      \bFull[\s]?Year\b |
      \bAnnual\b |
      \bGrand\b |
      合計 | 总计 | 總計 | 합계
    )""",
    re.IGNORECASE | re.VERBOSE | re.UNICODE,
)


def profile_stage1_result(s1: Stage1Result) -> Stage2Result:
    """
    Run Stage 2 profiling on the complete Stage 1 result.
    Returns a Stage2Result with per-table profiles and a human-readable summary.
    """
    table_profiles: list[TableProfile] = []
    total_detail_rows = 0
    total_anomalies = 0
    total_mismatches = 0
    all_category_values: set[str] = set()
    warnings: list[str] = list(s1.warnings)

    for raw_table in s1.tables:
        tp = _profile_table(raw_table, warnings)
        table_profiles.append(tp)
        total_detail_rows += tp.detail_row_count
        total_anomalies += len(tp.anomalies)
        total_mismatches += len(tp.computed_column_mismatches)

        # Collect category values for grand totals
        for cp in tp.column_profiles:
            if cp.inferred_type == ColumnType.CATEGORY:
                for row in raw_table.rows:
                    if cp.col_index < len(row.cells):
                        v = row.cells[cp.col_index].value
                        if v and str(v).strip():
                            all_category_values.add(str(v).strip())

    summary = _build_human_summary(
        s1=s1,
        table_profiles=table_profiles,
        total_detail_rows=total_detail_rows,
        total_categories=len(all_category_values),
        total_anomalies=total_anomalies,
        total_mismatches=total_mismatches,
    )

    return Stage2Result(
        table_profiles=table_profiles,
        total_tables=len(table_profiles),
        total_detail_rows=total_detail_rows,
        total_categories=len(all_category_values),
        total_anomalies=total_anomalies,
        total_mismatches=total_mismatches,
        human_summary=summary,
        warnings=warnings,
    )


def _profile_table(raw_table: RawTable, warnings: list[str]) -> TableProfile:
    rows = raw_table.rows
    headers = raw_table.headers
    num_cols = len(headers)

    if not rows:
        return TableProfile(
            table_index=raw_table.table_index,
            source_page=raw_table.source_page,
            source_sheet=raw_table.source_sheet,
            total_rows=0,
            detail_row_count=0,
            subtotal_row_count=0,
            section_header_count=0,
            grain_description="Empty table — no rows to profile.",
            row_roles=[],
        )

    # --- Step 1: Detect time structure from headers ---
    time_struct = detect_time_structure(headers)
    time_period_col_indices: set[int] = set(time_struct.get("time_period_col_indices", []))
    parsed_periods: dict = time_struct.get("parsed_periods", {})

    # --- Step 2: Infer column types ---
    col_profiles: list[ColumnProfile] = []
    for ci, header in enumerate(headers):
        col_values = [
            row.cells[ci].value if ci < len(row.cells) else None
            for row in rows
        ]
        is_time_period = ci in time_period_col_indices
        inferred_type, confidence, evidence = infer_column_type(
            col_index=ci,
            header=header,
            values=col_values,
            is_time_period_header=is_time_period,
        )
        non_null_vals = [v for v in col_values if v is not None and str(v).strip()]
        unique_vals = set(str(v).strip().lower() for v in non_null_vals)
        sample = [str(v) for v in non_null_vals[:5]]

        is_computed = bool(_COMPUTED_HEADER_PATTERN.search(header))

        period_info = parsed_periods.get(ci, {})
        col_profiles.append(ColumnProfile(
            col_index=ci,
            header=header,
            inferred_type=inferred_type,
            type_confidence=confidence,
            type_evidence=evidence,
            null_count=len(col_values) - len(non_null_vals),
            unique_count=len(unique_vals),
            sample_values=sample,
            is_computed_column=is_computed,
            period_label=period_info.get("label"),
            period_order=period_info.get("period_order"),
        ))

    # --- Step 3: Assign row roles ---
    row_roles = assign_row_roles(rows, num_cols)

    detail_rows = [r for r, role in zip(rows, row_roles) if role == RowRole.DETAIL]
    subtotal_rows = [r for r, role in zip(rows, row_roles) if role == RowRole.SUBTOTAL]
    grand_total_rows = [r for r, role in zip(rows, row_roles) if role == RowRole.GRAND_TOTAL]
    section_header_rows = [r for r, role in zip(rows, row_roles) if role == RowRole.SECTION_HEADER]

    # --- Step 4: Validate computed columns ---
    mismatches = _validate_computed_columns(
        rows=rows,
        row_roles=row_roles,
        col_profiles=col_profiles,
        time_period_col_indices=time_period_col_indices,
    )

    # --- Step 5: Detect anomalies ---
    # Update col_profiles with null_count so anomaly_detector can use it
    for cp in col_profiles:
        cp.null_count = sum(
            1 for row in rows
            if cp.col_index >= len(row.cells) or row.cells[cp.col_index].value is None
            or str(row.cells[cp.col_index].value).strip() == ""
        )

    anomalies = detect_anomalies(rows, row_roles, col_profiles)

    # --- Step 6: Grain detection ---
    grain = _infer_grain(
        detail_rows=detail_rows,
        col_profiles=col_profiles,
        time_struct=time_struct,
    )

    return TableProfile(
        table_index=raw_table.table_index,
        source_page=raw_table.source_page,
        source_sheet=raw_table.source_sheet,
        total_rows=len(rows),
        detail_row_count=len(detail_rows),
        subtotal_row_count=len(subtotal_rows) + len(grand_total_rows),
        section_header_count=len(section_header_rows),
        column_profiles=col_profiles,
        time_structure=time_struct if time_struct["has_time_structure"] else None,
        grain_description=grain,
        has_hierarchy=has_hierarchy(row_roles),
        row_roles=row_roles,
        computed_column_mismatches=mismatches,
        anomalies=anomalies,
    )


def _validate_computed_columns(
    rows: list[RawRow],
    row_roles: list[RowRole],
    col_profiles: list[ColumnProfile],
    time_period_col_indices: set[int],
) -> list[ComputedColumnMismatch]:
    """
    For each row that is NOT a subtotal/grand_total, check if computed columns
    match the sum of their constituent detail columns.

    CRITICAL DOCUMENTATION (to avoid the previous double-counting bug):
      - source_value: the value stored in the computed column cell of this specific row
        (taken directly from Stage 1 extraction, NOT recomputed).
      - recomputed_value: the sum of all TIME_PERIOD or NUMERIC columns in the SAME row
        that are NOT themselves computed columns.
      - These are two different things: one comes from the source file, one is our calculation.
      - We compare source_value (from source file) vs recomputed_value (our sum of detail cols).
    """
    mismatches: list[ComputedColumnMismatch] = []

    computed_cols = [cp for cp in col_profiles if cp.is_computed_column]
    if not computed_cols:
        return mismatches

    # Determine which columns to SUM (source for recomputation):
    # - Time period columns (if present) are the primary addends
    # - Otherwise, use non-computed numeric/currency columns
    if time_period_col_indices:
        addend_col_indices = [
            ci for ci in time_period_col_indices
            if not col_profiles[ci].is_computed_column
            and col_profiles[ci].inferred_type in (
                ColumnType.NUMERIC, ColumnType.CURRENCY, ColumnType.TIME_PERIOD
            )
        ]
        recomputed_from_label = (
            f"SUM of time-period columns: "
            f"{[col_profiles[ci].header for ci in addend_col_indices]}"
        )
    else:
        addend_col_indices = [
            cp.col_index for cp in col_profiles
            if not cp.is_computed_column
            and cp.inferred_type in (ColumnType.NUMERIC, ColumnType.CURRENCY)
        ]
        recomputed_from_label = (
            f"SUM of non-computed numeric/currency columns: "
            f"{[col_profiles[ci].header for ci in addend_col_indices]}"
        )

    if not addend_col_indices:
        return mismatches

    # First identifier or category column is used as the row description
    desc_col = next(
        (cp.col_index for cp in col_profiles if cp.inferred_type in (ColumnType.IDENTIFIER, ColumnType.CATEGORY)),
        0,
    )

    for row, role in zip(rows, row_roles):
        # Only validate DETAIL rows (subtotals are already aggregated — comparing them
        # against a re-sum of their own children would require grouping, handled separately)
        if role != RowRole.DETAIL:
            continue

        row_desc = ""
        if desc_col < len(row.cells):
            row_desc = str(row.cells[desc_col].value or "")

        for comp_cp in computed_cols:
            ci = comp_cp.col_index
            if ci >= len(row.cells):
                continue
            source_val = row.cells[ci].value
            if not isinstance(source_val, (int, float)):
                continue

            # Recompute: SUM of addend columns in this same row
            recomputed = 0.0
            for aci in addend_col_indices:
                if aci < len(row.cells):
                    v = row.cells[aci].value
                    if isinstance(v, (int, float)):
                        recomputed += float(v)

            delta = float(source_val) - recomputed
            # Only flag if difference is not negligible (rounding threshold: 0.01)
            if abs(delta) > 0.01:
                mismatches.append(ComputedColumnMismatch(
                    row_index=row.row_index,
                    row_description=row_desc,
                    column_header=comp_cp.header,
                    source_value=float(source_val),
                    recomputed_value=recomputed,
                    delta=delta,
                    recomputed_from=recomputed_from_label,
                    source_page=row.source_page,
                    source_line=row.source_line,
                ))

    return mismatches


def _infer_grain(
    detail_rows: list[RawRow],
    col_profiles: list[ColumnProfile],
    time_struct: dict,
) -> str:
    """
    Produce a human-readable description of what one row represents.
    This is a heuristic; it is displayed in the profile for user review.
    """
    if not detail_rows:
        return "No detail rows to determine grain."

    # Find the primary identifier/category column
    id_cols = [cp for cp in col_profiles if cp.inferred_type == ColumnType.IDENTIFIER]
    cat_cols = [cp for cp in col_profiles if cp.inferred_type == ColumnType.CATEGORY]
    primary_col = (id_cols + cat_cols + col_profiles)[0] if col_profiles else None

    has_time = time_struct.get("has_time_structure", False)
    period_type = time_struct.get("period_type", "")
    period_count = time_struct.get("count", 0)

    if primary_col and has_time:
        return (
            f"One row = one '{primary_col.header}' record. "
            f"Numeric values span {period_count} {period_type} period columns "
            f"({time_struct.get('start')} – {time_struct.get('end')}). "
            f"[Heuristic — please verify]"
        )

    if primary_col:
        n_unique = primary_col.unique_count
        n_rows = len(detail_rows)
        if n_unique == n_rows:
            return (
                f"One row = one unique '{primary_col.header}' record "
                f"({n_rows} distinct values). [Heuristic — please verify]"
            )
        else:
            return (
                f"One row represents a '{primary_col.header}' entry "
                f"({n_unique} unique values across {n_rows} rows — "
                f"some values appear multiple times). [Heuristic — please verify]"
            )

    return f"Could not determine grain automatically. {len(detail_rows)} detail rows total. [Manual review needed]"


def _build_human_summary(
    s1: Stage1Result,
    table_profiles: list[TableProfile],
    total_detail_rows: int,
    total_categories: int,
    total_anomalies: int,
    total_mismatches: int,
) -> str:
    """Build the human-readable data profile summary shown in the UI."""
    lines: list[str] = []
    lines.append(f"📄 File: {s1.filename} ({s1.file_type.upper()})")
    lines.append(f"📊 Found {len(table_profiles)} table(s) with {total_detail_rows} detail rows and {total_categories} unique category values.")

    for tp in table_profiles:
        sheet_info = f" (sheet: '{tp.source_sheet}')" if tp.source_sheet else ""
        page_info = f" (page {tp.source_page})" if tp.source_page else ""
        lines.append(
            f"  • Table {tp.table_index + 1}{sheet_info}{page_info}: "
            f"{tp.detail_row_count} detail rows, "
            f"{tp.subtotal_row_count} subtotal/grand-total rows, "
            f"{tp.section_header_count} section headers."
        )
        if tp.time_structure:
            ts = tp.time_structure
            lines.append(
                f"    ⏱ Time structure: {ts['period_type']} columns "
                f"from {ts['start']} to {ts['end']} ({ts['count']} periods)."
            )
        if tp.has_hierarchy:
            lines.append("    🏗 Hierarchy detected: category/subtotal structure present.")
        lines.append(f"    📐 Grain: {tp.grain_description}")

        if tp.computed_column_mismatches:
            lines.append(
                f"    ⚠️  {len(tp.computed_column_mismatches)} mismatch(es) between source file's "
                f"computed columns and recomputed values:"
            )
            for m in tp.computed_column_mismatches[:5]:  # show first 5
                lines.append(
                    f"       • Row '{m.row_description}', column '{m.column_header}': "
                    f"source={m.source_value:,.2f}, recomputed={m.recomputed_value:,.2f}, "
                    f"delta={m.delta:+,.2f}. "
                    f"[Recomputed from: {m.recomputed_from}]"
                )
            if len(tp.computed_column_mismatches) > 5:
                lines.append(f"       ... and {len(tp.computed_column_mismatches) - 5} more (see full profile JSON).")

        if tp.anomalies:
            by_type: dict[str, int] = {}
            for a in tp.anomalies:
                by_type[a.anomaly_type] = by_type.get(a.anomaly_type, 0) + 1
            anomaly_summary = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in by_type.items())
            lines.append(f"    🔍 Anomalies: {anomaly_summary}.")

    if s1.unparsed_rows:
        lines.append(f"  ⛔ {len(s1.unparsed_rows)} row(s) could not be parsed — see 'Unparsed Rows' section.")

    if total_mismatches == 0 and total_anomalies == 0:
        lines.append("  ✅ No computed column mismatches or anomalies detected.")

    return "\n".join(lines)
