"""
Comparison Strategy for GeniusDataManager.
Compares two segments (periods, categories, or before/after) across metric columns.
"""
import uuid
import numpy as np
import pandas as pd

from models.schemas import (
    AnalysisRequest,
    AnalysisResult,
    ChartData,
    ChartSeries,
    KPICard,
)
from services.analysis.base import BaseAnalysis
from services.schema_detection import json_safe_value


class ComparisonAnalysis(BaseAnalysis):
    @property
    def name(self) -> str:
        return "comparison"

    def analyze(self, df: pd.DataFrame, request: AnalysisRequest) -> AnalysisResult:
        if df.empty:
            return AnalysisResult(
                result_id=str(uuid.uuid4()),
                analysis_type=self.name,
                summary="Dataset is empty. No comparison can be made.",
                detailed_findings=[],
                kpis=[],
                charts=[],
            )

        df_work = df.copy()

        # 1. Identify Metric Column
        metric_col = None
        for col in request.target_columns:
            if col in df_work.columns and pd.api.types.is_numeric_dtype(df_work[col]):
                metric_col = col
                break
        if not metric_col:
            for col in df_work.columns:
                if pd.api.types.is_numeric_dtype(df_work[col]):
                    metric_col = col
                    break
        if not metric_col:
            raise ValueError("Comparison analysis requires at least one numeric metric column.")

        comp_type = (request.comparison_type or "category_comparison").lower()

        # 2. Category or Period segment selection
        segment_col = None
        if comp_type == "period_over_period":
            # Use date column
            for col in df_work.columns:
                if pd.api.types.is_datetime64_any_dtype(df_work[col]) or any(k in col.lower() for k in ["date", "quarter", "month", "year"]):
                    segment_col = col
                    break
        if not segment_col:
            # Check requested category columns
            if request.category_columns:
                for c in request.category_columns:
                    if c in df_work.columns:
                        segment_col = c
                        break
        if not segment_col:
            # First categorical/string column with at least 2 distinct values
            for col in df_work.columns:
                if col != metric_col and df_work[col].nunique() >= 2:
                    segment_col = col
                    break

        if not segment_col:
            raise ValueError("Comparison requires a grouping or category column with at least two distinct values.")

        # Group by segment
        agg_table = df_work.groupby(segment_col)[metric_col].agg(["sum", "mean", "count"]).sort_values(by="sum", ascending=False)
        segments = list(agg_table.index)
        if len(segments) < 2:
            raise ValueError(f"Column '{segment_col}' has fewer than 2 distinct values to compare.")

        # Compare top 2 segments (or user specified)
        seg_a = str(segments[0])
        seg_b = str(segments[1])

        val_a = float(agg_table.loc[segments[0], "sum"])
        val_b = float(agg_table.loc[segments[1], "sum"])

        diff = val_a - val_b
        pct_diff = round(((val_a - val_b) / val_b * 100), 1) if val_b > 0 else 0.0

        kpis = [
            KPICard(
                label=f"{seg_a} (Leader)",
                value=round(val_a, 2),
                formatted=f"{val_a:,.2f}",
                subtext=f"{int(agg_table.loc[segments[0], 'count']):,} records",
            ),
            KPICard(
                label=f"{seg_b} (Challenger)",
                value=round(val_b, 2),
                formatted=f"{val_b:,.2f}",
                subtext=f"{int(agg_table.loc[segments[1], 'count']):,} records",
            ),
            KPICard(
                label="Delta (A vs B)",
                value=round(diff, 2),
                formatted=f"{diff:+,.2f}",
                change_pct=pct_diff,
                subtext=f"{pct_diff:+}% difference",
            ),
        ]

        summary = f"Comparing '{seg_a}' against '{seg_b}' on {metric_col}: '{seg_a}' leads by {diff:+,.2f} ({pct_diff:+}% higher)."

        detailed_findings = [
            f"Evaluated {len(segments)} segments across {len(df_work):,} rows using '{segment_col}'.",
            f"Segment '{seg_a}' achieved highest volume at {val_a:,.2f}, outperforming '{seg_b}' ({val_b:,.2f}) by {pct_diff:+}%.",
            f"Average {metric_col} for '{seg_a}' was {float(agg_table.loc[segments[0], 'mean']):,.2f} vs {float(agg_table.loc[segments[1], 'mean']):,.2f} for '{seg_b}'.",
        ]

        top_segments = segments[:6]
        charts = [
            ChartData(
                chart_type="bar",
                title=f"Comparison of {metric_col} by {segment_col}",
                labels=[str(s) for s in top_segments],
                series=[
                    ChartSeries(
                        name="Total",
                        data=[round(float(agg_table.loc[s, "sum"]), 2) for s in top_segments],
                        type="bar",
                    ),
                    ChartSeries(
                        name="Average",
                        data=[round(float(agg_table.loc[s, "mean"]), 2) for s in top_segments],
                        type="bar",
                    ),
                ],
            )
        ]

        table_data = []
        for s in top_segments:
            table_data.append({
                "segment": str(s),
                "total": round(float(agg_table.loc[s, "sum"]), 2),
                "average": round(float(agg_table.loc[s, "mean"]), 2),
                "count": int(agg_table.loc[s, "count"]),
            })

        return AnalysisResult(
            result_id=str(uuid.uuid4()),
            analysis_type=self.name,
            summary=summary,
            detailed_findings=detailed_findings,
            kpis=kpis,
            charts=charts,
            table_data=table_data,
            table_columns=["segment", "total", "average", "count"],
            metadata={"segment_column": segment_col, "metric_column": metric_col},
        )
