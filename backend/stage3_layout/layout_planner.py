"""
Stage 3 — Layout Planner (Rule-Based)
=======================================
Consumes a Stage2Result and produces a LayoutPlan that tells the frontend
*what to render and how* — without any hard-coded templates.

Rules are deterministic and inspectable. Each ChartSpec records *why* it
was chosen via the `notes` field, so the decision is always auditable.

Rule priority order (applied per table):
  1. Time structure detected  → line/area chart (y = all numeric/currency non-computed cols)
  2. Hierarchy detected       → drilldown table (in addition to any chart)
  3. Single numeric col, categorical → horizontal bar chart
  4. Multiple numeric cols, no time  → grouped bar chart
  5. Computed column mismatches > 0  → mismatch panel (chart_type="mismatch")
  6. Anomalies > 0                   → anomaly panel  (chart_type="anomaly")
  7. Always                          → KPI summary strip (chart_type="kpi")
"""

from __future__ import annotations

import re
from models.intermediate import (
    ColumnType,
    ChartSpec,
    LayoutPlan,
    RowRole,
    Stage2Result,
    TableProfile,
)


def plan_layout(stage2: Stage2Result, task_id: str) -> LayoutPlan:
    """
    Run the Stage 3 rules engine over all table profiles.
    Returns a LayoutPlan describing how to visualise the data.
    """
    charts: list[ChartSpec] = []
    drilldown_indices: list[int] = []
    highlight_mismatches = False
    highlight_anomalies = False
    layout_notes_parts: list[str] = []
    chart_counter = 0

    # --- KPI summary (always first) ---
    charts.append(ChartSpec(
        chart_id="kpi_strip",
        chart_type="kpi",
        title="Data Summary",
        table_index=-1,           # -1 = applies to whole pipeline result
        notes="KPI strip is always shown regardless of data shape.",
    ))
    layout_notes_parts.append("KPI strip always rendered.")

    for tp in stage2.table_profiles:
        tid = tp.table_index
        col_profiles = tp.column_profiles

        # Identify column categories
        numeric_cols = [
            cp.header for cp in col_profiles
            if cp.inferred_type in (ColumnType.NUMERIC, ColumnType.CURRENCY)
            and not cp.is_computed_column
        ]
        time_period_cols = [
            cp.header for cp in col_profiles
            if cp.inferred_type == ColumnType.TIME_PERIOD
            and not cp.is_computed_column
        ]
        category_cols = [
            cp.header for cp in col_profiles
            if cp.inferred_type in (ColumnType.CATEGORY, ColumnType.IDENTIFIER)
        ]
        # Primary x-axis category column
        x_col = category_cols[0] if category_cols else (col_profiles[0].header if col_profiles else None)

        # --- Rule 1: Time structure → line chart ---
        if tp.time_structure and time_period_cols:
            # y = all numeric non-computed cols (they are the values in the period columns)
            # In a time-period layout, the period headers ARE the y-series columns
            y_cols = time_period_cols
            charts.append(ChartSpec(
                chart_id=f"chart_{chart_counter}_line",
                chart_type="line",
                title=f"Table {tid + 1} — Time Series" + (f" ({tp.source_sheet})" if tp.source_sheet else ""),
                table_index=tid,
                x_col=x_col,
                y_cols=y_cols,
                row_filter="detail",
                notes=(
                    f"Time structure detected: {tp.time_structure.get('period_type')} "
                    f"from {tp.time_structure.get('start')} to {tp.time_structure.get('end')} "
                    f"({tp.time_structure.get('count')} periods). Rule 1: time → line chart."
                ),
            ))
            layout_notes_parts.append(
                f"Table {tid + 1}: time structure → line chart over {len(y_cols)} period columns."
            )
            chart_counter += 1

        # --- Rule 2: Hierarchy → drilldown table ---
        if tp.has_hierarchy:
            drilldown_indices.append(tid)
            layout_notes_parts.append(
                f"Table {tid + 1}: hierarchy detected → drilldown table added."
            )

        # --- Rule 3 & 4: No time structure → bar charts ---
        if not tp.time_structure:
            if len(numeric_cols) == 1:
                # Single numeric → horizontal bar
                charts.append(ChartSpec(
                    chart_id=f"chart_{chart_counter}_bar_h",
                    chart_type="bar_horizontal",
                    title=f"Table {tid + 1} — {numeric_cols[0]}",
                    table_index=tid,
                    x_col=x_col,
                    y_cols=[numeric_cols[0]],
                    row_filter="detail",
                    notes=(
                        f"No time structure, single numeric column '{numeric_cols[0]}'. "
                        f"Rule 3: horizontal bar for category vs. single metric."
                    ),
                ))
                layout_notes_parts.append(
                    f"Table {tid + 1}: single numeric col → horizontal bar chart."
                )
                chart_counter += 1
            elif len(numeric_cols) >= 2:
                # Multiple numeric → grouped bar (limit to 6 series for readability)
                y_cols_limited = numeric_cols[:6]
                charts.append(ChartSpec(
                    chart_id=f"chart_{chart_counter}_grouped_bar",
                    chart_type="grouped_bar",
                    title=f"Table {tid + 1} — Multi-Metric Comparison",
                    table_index=tid,
                    x_col=x_col,
                    y_cols=y_cols_limited,
                    row_filter="detail",
                    notes=(
                        f"No time structure, {len(numeric_cols)} numeric columns. "
                        f"Rule 4: grouped bar for multi-metric comparison "
                        f"(showing first {len(y_cols_limited)} series)."
                    ),
                ))
                layout_notes_parts.append(
                    f"Table {tid + 1}: {len(numeric_cols)} numeric cols → grouped bar."
                )
                chart_counter += 1

        # --- Always add a drilldown table if no hierarchy was found ---
        if not tp.has_hierarchy and tid not in drilldown_indices:
            drilldown_indices.append(tid)

        # --- Rule 5: Mismatches ---
        if tp.computed_column_mismatches:
            highlight_mismatches = True
            charts.append(ChartSpec(
                chart_id=f"chart_{chart_counter}_mismatch",
                chart_type="mismatch",
                title=f"Table {tid + 1} — Computed Column Mismatches",
                table_index=tid,
                notes=(
                    f"{len(tp.computed_column_mismatches)} computed column mismatch(es) detected. "
                    f"Rule 5: show mismatch detail panel."
                ),
            ))
            layout_notes_parts.append(
                f"Table {tid + 1}: {len(tp.computed_column_mismatches)} mismatches → mismatch panel."
            )
            chart_counter += 1

        # --- Rule 6: Anomalies ---
        if tp.anomalies:
            highlight_anomalies = True
            charts.append(ChartSpec(
                chart_id=f"chart_{chart_counter}_anomaly",
                chart_type="anomaly",
                title=f"Table {tid + 1} — Anomalies",
                table_index=tid,
                notes=(
                    f"{len(tp.anomalies)} anomaly/anomalies detected. "
                    f"Rule 6: show anomaly detail panel."
                ),
            ))
            layout_notes_parts.append(
                f"Table {tid + 1}: {len(tp.anomalies)} anomalies → anomaly panel."
            )
            chart_counter += 1

    return LayoutPlan(
        task_id=task_id,
        charts=charts,
        drilldown_table_indices=drilldown_indices,
        highlight_mismatches=highlight_mismatches,
        highlight_anomalies=highlight_anomalies,
        layout_notes=" | ".join(layout_notes_parts) or "No renderable data found.",
    )
