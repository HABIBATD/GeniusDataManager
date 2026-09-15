"""
Summary Statistics Strategy for GeniusDataManager.
Computes standard descriptive statistics (mean, median, std dev, quartiles, skewness) per numeric column.
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


class SummaryStatsAnalysis(BaseAnalysis):
    @property
    def name(self) -> str:
        return "summary_stats"

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

        # Select numeric columns
        target_cols = [c for c in request.target_columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        if not target_cols:
            target_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        if not target_cols:
            raise ValueError("Summary statistics requires at least one numeric column.")

        primary_col = target_cols[0]
        s = df[primary_col].dropna()

        count = len(s)
        mean_val = float(s.mean()) if count > 0 else 0.0
        median_val = float(s.median()) if count > 0 else 0.0
        std_val = float(s.std()) if count > 1 else 0.0
        min_val = float(s.min()) if count > 0 else 0.0
        max_val = float(s.max()) if count > 0 else 0.0
        q25 = float(s.quantile(0.25)) if count > 0 else 0.0
        q75 = float(s.quantile(0.75)) if count > 0 else 0.0
        iqr = q75 - q25

        kpis = [
            KPICard(
                label=f"Mean ({primary_col})",
                value=round(mean_val, 2),
                formatted=f"{mean_val:,.2f}",
                subtext=f"Std Dev: {std_val:,.2f}",
            ),
            KPICard(
                label=f"Median ({primary_col})",
                value=round(median_val, 2),
                formatted=f"{median_val:,.2f}",
                subtext=f"IQR: {iqr:,.2f}",
            ),
            KPICard(
                label=f"Range (Min - Max)",
                value=round(max_val - min_val, 2),
                formatted=f"{min_val:,.2f} to {max_val:,.2f}",
                subtext=f"Spread: {max_val - min_val:,.2f}",
            ),
            KPICard(
                label="Sample Count",
                value=count,
                formatted=f"{count:,} rows",
                subtext=f"{len(df) - count} null values",
            ),
        ]

        summary = f"Summary stats for '{primary_col}': Mean is {mean_val:,.2f} with median {median_val:,.2f} (std dev: {std_val:,.2f}, range: {min_val:,.2f} - {max_val:,.2f})."

        detailed_findings = [
            f"Evaluated {count:,} non-null values for primary feature '{primary_col}'.",
            f"25th percentile (Q1): {q25:,.2f} | 75th percentile (Q3): {q75:,.2f} | Interquartile Range: {iqr:,.2f}.",
            f"Distribution spread ratio (StdDev / Mean): {(std_val / mean_val if mean_val != 0 else 0):.2f}.",
        ]

        # Detailed stats table across all numeric columns
        table_data = []
        for col in target_cols[:10]:
            cs = df[col].dropna()
            if len(cs) > 0:
                table_data.append({
                    "column": col,
                    "count": len(cs),
                    "mean": round(float(cs.mean()), 2),
                    "median": round(float(cs.median()), 2),
                    "std": round(float(cs.std()), 2) if len(cs) > 1 else 0.0,
                    "min": round(float(cs.min()), 2),
                    "max": round(float(cs.max()), 2),
                    "q25": round(float(cs.quantile(0.25)), 2),
                    "q75": round(float(cs.quantile(0.75)), 2),
                })

        # Histogram or Quantile Chart for primary column
        hist_counts, bin_edges = np.histogram(s, bins=min(10, max(3, count // 2)))
        bin_labels = [f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}" for i in range(len(hist_counts))]

        charts = [
            ChartData(
                chart_type="bar",
                title=f"Frequency Distribution ({primary_col})",
                labels=bin_labels,
                series=[
                    ChartSeries(
                        name="Frequency",
                        data=[int(c) for c in hist_counts],
                        type="bar",
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
            table_data=table_data,
            table_columns=["column", "count", "mean", "median", "std", "min", "max", "q25", "q75"],
            metadata={"analyzed_columns": target_cols},
        )
