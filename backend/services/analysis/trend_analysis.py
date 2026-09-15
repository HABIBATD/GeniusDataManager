"""
Trend Analysis Strategy for GeniusDataManager.
Performs time-bucketed aggregation (daily/weekly/monthly/quarterly) and trend direction detection.
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


class TrendAnalysis(BaseAnalysis):
    @property
    def name(self) -> str:
        return "trend_analysis"

    def analyze(self, df: pd.DataFrame, request: AnalysisRequest) -> AnalysisResult:
        if df.empty:
            return AnalysisResult(
                result_id=str(uuid.uuid4()),
                analysis_type=self.name,
                summary="No records to analyze for trends.",
                detailed_findings=[],
                kpis=[],
                charts=[],
            )

        df_work = df.copy()

        # 1. Identify Date Column
        date_col = request.date_column
        if not date_col or date_col not in df_work.columns:
            for col in df_work.columns:
                if pd.api.types.is_datetime64_any_dtype(df_work[col]) or any(k in col.lower() for k in ["date", "time", "day", "month", "created", "period"]):
                    date_col = col
                    break

        if not date_col:
            raise ValueError("Trend analysis requires a valid date or timestamp column.")

        # 2. Identify Metric Column
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
            raise ValueError("Trend analysis requires at least one numeric metric column.")

        # Parse dates
        dt_series = pd.to_datetime(df_work[date_col], errors="coerce")
        valid_mask = dt_series.notna() & df_work[metric_col].notna()
        df_valid = df_work[valid_mask].copy()
        df_valid["_dt"] = dt_series[valid_mask]

        if len(df_valid) < 2:
            raise ValueError("Trend analysis requires at least 2 valid timestamped rows.")

        # Determine grouping bucket: 'D' (daily), 'W' (weekly), 'M' (monthly), 'Q' (quarterly)
        bucket = request.options.get("bucket", "M").upper()
        if bucket not in ("D", "W", "M", "Q"):
            bucket = "M"

        df_valid = df_valid.sort_values("_dt")
        span_days = (df_valid["_dt"].max() - df_valid["_dt"].min()).days
        # Auto adjust bucket if span is very short or very long
        if span_days <= 14:
            bucket = "D"
        elif span_days <= 60:
            bucket = "W"

        df_valid["_period"] = df_valid["_dt"].dt.to_period(bucket).astype(str)
        grouped = df_valid.groupby("_period")[metric_col].agg(["sum", "mean", "count"]).sort_index()

        periods = list(grouped.index)
        sums = [round(float(v), 2) for v in grouped["sum"]]
        means = [round(float(v), 2) for v in grouped["mean"]]

        # Calculate Trend Slope and Direction
        x = np.arange(len(sums))
        slope = float(np.polyfit(x, sums, 1)[0]) if len(sums) > 1 else 0.0

        if slope > 0.05 * (np.mean(sums) if np.mean(sums) > 0 else 1):
            direction = "Upward"
            trend_icon = "📈"
        elif slope < -0.05 * (np.mean(sums) if np.mean(sums) > 0 else 1):
            direction = "Downward"
            trend_icon = "📉"
        else:
            direction = "Stable"
            trend_icon = "⚖️"

        # First vs Last Period Change
        first_val = sums[0]
        last_val = sums[-1]
        overall_change_pct = round(((last_val - first_val) / first_val * 100), 1) if first_val > 0 else 0.0

        kpis = [
            KPICard(
                label=f"Overall Trend ({metric_col})",
                value=direction,
                formatted=f"{trend_icon} {direction}",
                subtext=f"Linear slope: {slope:+.2f} per {bucket} period",
            ),
            KPICard(
                label="Latest Period Total",
                value=last_val,
                formatted=f"{last_val:,.2f}",
                change_pct=overall_change_pct,
                subtext=f"Period: {periods[-1]}",
            ),
            KPICard(
                label="Period Average",
                value=round(float(np.mean(sums)), 2),
                formatted=f"{float(np.mean(sums)):,.2f}",
                subtext=f"Across {len(periods)} periods ({bucket})",
            ),
        ]

        detailed_findings = [
            f"Analyzed {len(df_valid):,} records across {len(periods)} time periods ({periods[0]} to {periods[-1]}).",
            f"The primary metric '{metric_col}' shows an overall {direction.lower()} movement with an aggregate change of {overall_change_pct:+}% from inception to the latest period.",
            f"Peak value was {max(sums):,.2f} recorded in period {periods[sums.index(max(sums))]}.",
        ]

        summary = f"Detected an {direction.lower()} trend in {metric_col} over {len(periods)} periods. Overall performance changed by {overall_change_pct:+}% ({first_val:,.2f} to {last_val:,.2f})."

        charts = [
            ChartData(
                chart_type="line",
                title=f"{metric_col} Over Time ({bucket}-Bucketed)",
                labels=periods,
                series=[
                    ChartSeries(name=f"Total {metric_col}", data=sums, type="line"),
                    ChartSeries(name=f"Average {metric_col}", data=means, type="line"),
                ],
            )
        ]

        return AnalysisResult(
            result_id=str(uuid.uuid4()),
            analysis_type=self.name,
            summary=summary,
            detailed_findings=detailed_findings,
            kpis=kpis,
            charts=charts,
            table_data=[{"period": p, "total": s, "average": m} for p, s, m in zip(periods, sums, means)],
            table_columns=["period", "total", "average"],
            metadata={"metric": metric_col, "date_column": date_col, "bucket": bucket, "slope": slope},
        )
