"""
Outlier Detection Strategy for GeniusDataManager.
Detects statistical anomalies using IQR (Interquartile Range) or Z-score methods.
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


class OutlierDetectionAnalysis(BaseAnalysis):
    @property
    def name(self) -> str:
        return "outlier_detection"

    def analyze(self, df: pd.DataFrame, request: AnalysisRequest) -> AnalysisResult:
        if df.empty:
            return AnalysisResult(
                result_id=str(uuid.uuid4()),
                analysis_type=self.name,
                summary="Dataset is empty.",
                detailed_findings=[],
                kpis=[],
                charts=[],
            )

        # 1. Identify target numeric column
        target_col = None
        for col in request.target_columns:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                target_col = col
                break
        if not target_col:
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    target_col = col
                    break

        if not target_col:
            raise ValueError("Outlier detection requires at least one numeric column.")

        method = request.options.get("method", "iqr").lower()
        s = df[target_col].dropna()
        total_valid = len(s)

        if total_valid < 4:
            raise ValueError("Outlier detection requires at least 4 valid numeric values.")

        outlier_mask = pd.Series(False, index=df.index)
        lower_bound = 0.0
        upper_bound = 0.0

        if method == "zscore":
            z_thresh = float(request.options.get("threshold", 3.0))
            mean_v = float(s.mean())
            std_v = float(s.std()) if s.std() > 0 else 1.0
            z_scores = (df[target_col] - mean_v).abs() / std_v
            outlier_mask = z_scores > z_thresh
            lower_bound = round(mean_v - (z_thresh * std_v), 2)
            upper_bound = round(mean_v + (z_thresh * std_v), 2)
            method_desc = f"Z-score threshold ±{z_thresh}"
        else:
            # IQR method default (1.5x IQR)
            multiplier = float(request.options.get("multiplier", 1.5))
            q25 = float(s.quantile(0.25))
            q75 = float(s.quantile(0.75))
            iqr = q75 - q25
            lower_bound = round(q25 - (multiplier * iqr), 2)
            upper_bound = round(q75 + (multiplier * iqr), 2)
            outlier_mask = (df[target_col] < lower_bound) | (df[target_col] > upper_bound)
            method_desc = f"Tukey's IQR ({multiplier}x)"

        outlier_count = int(outlier_mask.sum())
        outlier_pct = round((outlier_count / total_valid * 100), 2) if total_valid > 0 else 0.0

        kpis = [
            KPICard(
                label="Outliers Detected",
                value=outlier_count,
                formatted=f"{outlier_count:,} anomalies",
                subtext=f"{outlier_pct}% of {total_valid:,} rows",
            ),
            KPICard(
                label="Normal Lower Bound",
                value=lower_bound,
                formatted=f"{lower_bound:,.2f}",
                subtext="Values below this are flagged low",
            ),
            KPICard(
                label="Normal Upper Bound",
                value=upper_bound,
                formatted=f"{upper_bound:,.2f}",
                subtext="Values above this are flagged high",
            ),
            KPICard(
                label="Detection Method",
                value=method.upper(),
                formatted=method_desc,
                subtext=f"Feature: {target_col}",
            ),
        ]

        summary = f"Detected {outlier_count:,} statistical outlier(s) ({outlier_pct}%) in '{target_col}' using {method_desc}. Normal boundary is [{lower_bound:,.2f} to {upper_bound:,.2f}]."

        detailed_findings = [
            f"Evaluated {total_valid:,} non-null values for column '{target_col}'.",
            f"Expected normal range: {lower_bound:,.2f} to {upper_bound:,.2f}.",
            f"{outlier_count} record(s) exceed these boundaries.",
        ]

        # Extract outlier rows for preview table
        outlier_df = df[outlier_mask].copy()
        preview_cols = [c for c in df.columns if not c.startswith("_")][:10]
        table_records = []
        for _, row in outlier_df.head(50).iterrows():
            rec = {c: json_safe_value(row[c]) for c in preview_cols}
            rec["_outlier_value"] = json_safe_value(row[target_col])
            table_records.append(rec)

        # Build chart: Normal vs Outlier counts or sample points
        charts = [
            ChartData(
                chart_type="doughnut",
                title=f"Outlier Proportion ({target_col})",
                labels=["Normal Data", "Outliers"],
                series=[
                    ChartSeries(
                        name="Count",
                        data=[total_valid - outlier_count, outlier_count],
                        type="doughnut",
                    )
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
            table_data=table_records,
            table_columns=preview_cols + ["_outlier_value"],
            metadata={"column": target_col, "lower_bound": lower_bound, "upper_bound": upper_bound, "outlier_count": outlier_count},
        )
