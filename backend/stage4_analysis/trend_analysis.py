"""
Stage 4 — Trend Analysis Strategy.
=================================
Performs time-bucketed aggregation (daily/weekly/monthly/quarterly),
computes trend slope, direction, moving averages, and growth percentages.
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


class TrendAnalysis(BaseAnalysis):
    """
    Performs time-series aggregation and trend direction analysis on numeric columns.
    """

    @property
    def name(self) -> str:
        return "trend_analysis"

    def run(self, df: pd.DataFrame, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        result_id = str(uuid.uuid4())

        if df is None or df.empty:
            raise AnalysisValidationError("Trend analysis requires a non-empty dataset.")

        df_work = df.copy()

        # 1. Identify Date Column
        date_col = options.get("date_column")
        if not date_col or date_col not in df_work.columns:
            for col in df_work.columns:
                if pd.api.types.is_datetime64_any_dtype(df_work[col]) or any(
                    k in col.lower() for k in ["date", "time", "day", "month", "created", "period"]
                ):
                    date_col = col
                    break

        if not date_col:
            raise AnalysisValidationError(
                "Trend analysis requires a valid date or timestamp column (e.g., 'date', 'created_at')."
            )

        # 2. Identify Metric Column
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
            raise AnalysisValidationError(
                "Trend analysis requires at least one numeric metric column to measure trends."
            )

        # 3. Parse Dates and Filter Invalid
        df_work["_dt"] = pd.to_datetime(df_work[date_col], errors="coerce")
        df_valid = df_work.dropna(subset=["_dt"]).sort_values("_dt")

        if df_valid.empty:
            raise AnalysisValidationError(
                f"Could not parse valid datetime values from column '{date_col}'."
            )

        # 4. Determine Bucket Frequency
        bucket = options.get("bucket", "M").upper()
        if bucket not in ("D", "W", "M", "Q", "Y"):
            bucket = "M"

        bucket_names = {"D": "Daily", "W": "Weekly", "M": "Monthly", "Q": "Quarterly", "Y": "Yearly"}
        bucket_label = bucket_names.get(bucket, "Monthly")

        df_valid["_period"] = df_valid["_dt"].dt.to_period(bucket).astype(str)
        agg_df = (
            df_valid.groupby("_period")[metric_col]
            .agg(["sum", "mean", "count"])
            .reset_index()
            .rename(columns={"sum": "total", "mean": "average", "count": "records"})
        )

        labels = agg_df["_period"].tolist()
        totals = [round(float(v), 2) for v in agg_df["total"].tolist()]
        averages = [round(float(v), 2) for v in agg_df["average"].tolist()]

        # 5. Trend Direction & Slope
        direction = "Neutral / Stable"
        slope_pct = 0.0
        findings = []

        if len(totals) >= 2:
            x = np.arange(len(totals))
            y = np.array(totals)
            # Linear regression fit
            slope, intercept = np.polyfit(x, y, 1)
            mean_y = np.mean(y) if np.mean(y) != 0 else 1.0
            slope_pct = round(float((slope / mean_y) * 100), 1)

            if slope_pct > 3.0:
                direction = "Upward / Growth"
            elif slope_pct < -3.0:
                direction = "Downward / Decline"
            else:
                direction = "Stable"

            growth_overall = ((totals[-1] - totals[0]) / totals[0] * 100) if totals[0] > 0 else 0
            findings.append(
                f"The overall {bucket_label.lower()} trend is {direction} with an average rate of {slope_pct:+.1f}% per period."
            )
            findings.append(
                f"First period ({labels[0]}): {totals[0]:,}; Most recent period ({labels[-1]}): {totals[-1]:,} (Net change: {growth_overall:+.1f}%)."
            )
            summary_text = (
                f"{metric_col.replace('_', ' ').title()} exhibits an {direction.lower()} trend across {len(labels)} "
                f"{bucket_label.lower()} periods ({labels[0]} to {labels[-1]}), with a net change of {growth_overall:+.1f}%."
            )
        else:
            summary_text = f"Only one {bucket_label.lower()} period ({labels[0]}) is present in the dataset."
            findings.append("Insufficient distinct periods to calculate trend slope.")

        kpis = [
            {
                "label": "Trend Direction",
                "value": direction,
                "formatted": direction,
                "subtext": f"{bucket_label} slope: {slope_pct:+.1f}%/period",
            },
            {
                "label": f"Peak {bucket_label} {metric_col.title()}",
                "value": max(totals) if totals else 0,
                "formatted": f"{max(totals):,.2f}" if totals else "0",
                "subtext": f"Recorded in {labels[int(np.argmax(totals))]}" if totals else "",
            },
            {
                "label": f"Lowest {bucket_label} {metric_col.title()}",
                "value": min(totals) if totals else 0,
                "formatted": f"{min(totals):,.2f}" if totals else "0",
                "subtext": f"Recorded in {labels[int(np.argmin(totals))]}" if totals else "",
            },
        ]

        charts = [
            {
                "chart_type": "line",
                "title": f"{bucket_label} Trend: {metric_col.replace('_', ' ').title()}",
                "labels": labels,
                "series": [
                    {"name": f"Total {metric_col.title()}", "data": totals, "type": "line"},
                    {"name": f"Average {metric_col.title()}", "data": averages, "type": "line"},
                ],
                "options": {},
            }
        ]

        table_data = [
            {
                "Period": row["_period"],
                f"Total_{metric_col}": _json_safe(row["total"]),
                f"Average_{metric_col}": _json_safe(row["average"]),
                "Records": int(row["records"]),
            }
            for _, row in agg_df.iterrows()
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
                "date_column": date_col,
                "metric_column": metric_col,
                "bucket": bucket,
                "slope_pct": slope_pct,
                "period_count": len(labels),
            },
        }
