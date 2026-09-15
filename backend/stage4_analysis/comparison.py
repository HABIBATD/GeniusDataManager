"""
Stage 4 — Comparison Analysis Strategy.
=======================================
Compares performance across two or more segments (categories, customer tiers,
regions, or time periods) evaluating metric variance and percentage differentials.
"""
import uuid
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from stage4_analysis.base import AnalysisValidationError, BaseAnalysis


def _json_safe(val: Any) -> Any:
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.isoformat()
    return str(val)


class ComparisonAnalysis(BaseAnalysis):
    """
    Compares segments, periods, or categories on selected numeric metrics.
    """

    @property
    def name(self) -> str:
        return "comparison"

    def run(self, df: pd.DataFrame, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        result_id = str(uuid.uuid4())

        if df is None or df.empty:
            raise AnalysisValidationError("Comparison analysis requires a non-empty dataset.")

        df_work = df.copy()

        # 1. Identify Metric Column
        metric_col = None
        target_columns = options.get("target_columns", [])
        for col in target_columns:
            if col in df_work.columns and pd.api.types.is_numeric_dtype(df_work[col]):
                metric_col = col
                break

        if not metric_col:
            for col in df_work.columns:
                if pd.api.types.is_numeric_dtype(df_work[col]):
                    metric_col = col
                    break

        if not metric_col:
            raise AnalysisValidationError("Comparison analysis requires at least one numeric metric column.")

        # 2. Identify Segment / Dimension Column
        segment_col = None
        comp_type = (options.get("comparison_type") or "category_comparison").lower()
        category_columns = options.get("category_columns", [])

        if comp_type == "period_over_period":
            for col in df_work.columns:
                if pd.api.types.is_datetime64_any_dtype(df_work[col]) or any(
                    k in col.lower() for k in ["date", "quarter", "month", "year"]
                ):
                    segment_col = col
                    break

        if not segment_col and category_columns:
            for col in category_columns:
                if col in df_work.columns and col != metric_col:
                    segment_col = col
                    break

        if not segment_col:
            for col in df_work.columns:
                if col != metric_col and not pd.api.types.is_numeric_dtype(df_work[col]):
                    segment_col = col
                    break

        if not segment_col:
            for col in df_work.columns:
                if col != metric_col:
                    segment_col = col
                    break

        if not segment_col:
            raise AnalysisValidationError("Comparison analysis requires at least one dimension or category column.")

        # 3. Aggregate by segment
        seg_df = (
            df_work.groupby(segment_col)[metric_col]
            .agg(["sum", "mean", "count"])
            .reset_index()
            .rename(columns={"sum": "total", "mean": "average", "count": "records"})
            .sort_values(by="total", ascending=False)
        )

        if seg_df.empty or len(seg_df) < 1:
            raise AnalysisValidationError(f"No valid segments found in column '{segment_col}'.")

        labels = [str(x) for x in seg_df[segment_col].tolist()]
        totals = [round(float(v), 2) for v in seg_df["total"].tolist()]
        averages = [round(float(v), 2) for v in seg_df["average"].tolist()]

        findings = []
        leader = labels[0]
        leader_total = totals[0]
        runner_up = labels[1] if len(labels) > 1 else None
        runner_up_total = totals[1] if len(labels) > 1 else None

        kpis = [
            {
                "label": f"Top Segment ({segment_col.title()})",
                "value": leader,
                "formatted": f"{leader} (${leader_total:,.2f})",
                "subtext": f"{(leader_total / sum(totals) * 100):.1f}% of total metric volume",
            }
        ]

        if runner_up and runner_up_total:
            variance = leader_total - runner_up_total
            variance_pct = ((leader_total - runner_up_total) / runner_up_total * 100) if runner_up_total > 0 else 0
            kpis.append({
                "label": "Top Variance (1st vs 2nd)",
                "value": round(variance, 2),
                "formatted": f"+${variance:,.2f} (+{variance_pct:.1f}%)",
                "subtext": f"{leader} leads {runner_up}",
            })
            findings.append(
                f"'{leader}' outperformed '{runner_up}' by ${variance:,.2f} ({variance_pct:+.1f}%)."
            )

        kpis.append({
            "label": "Total Segments Analyzed",
            "value": len(labels),
            "formatted": str(len(labels)),
            "subtext": f"Across {len(df_work):,} records",
        })

        summary_text = (
            f"Compared {len(labels)} '{segment_col}' segments across {len(df_work):,} records. "
            f"'{leader}' leads with ${leader_total:,.2f} ({round(leader_total / sum(totals) * 100, 1)}% share)."
        )

        charts = [
            {
                "chart_type": "bar",
                "title": f"{segment_col.title()} Comparison by {metric_col.title()}",
                "labels": labels[:10],
                "series": [
                    {"name": f"Total {metric_col.title()}", "data": totals[:10], "type": "bar"},
                    {"name": f"Average {metric_col.title()}", "data": averages[:10], "type": "line"},
                ],
                "options": {},
            }
        ]

        table_data = [
            {
                segment_col: str(row[segment_col]),
                f"Total_{metric_col}": _json_safe(row["total"]),
                f"Average_{metric_col}": _json_safe(row["average"]),
                "Records": int(row["records"]),
            }
            for _, row in seg_df.iterrows()
        ]

        return {
            "result_id": result_id,
            "analysis_type": self.name,
            "status": "success",
            "summary": summary_text,
            "detailed_findings": findings,
            "kpis": kpis,
            "charts": charts,
            "table_data": table_data,
            "table_columns": list(table_data[0].keys()) if table_data else [],
            "metadata": {
                "segment_column": segment_col,
                "metric_column": metric_col,
                "comparison_type": comp_type,
                "segment_count": len(labels),
            },
        }
