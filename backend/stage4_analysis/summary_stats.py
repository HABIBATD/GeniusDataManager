"""
Stage 4 — Summary Statistics Strategy.
=====================================
Computes standard descriptive statistics (count, mean, median, standard deviation,
min, max, IQR, skewness) across all selected numeric features.
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


class SummaryStatsAnalysis(BaseAnalysis):
    """
    Computes comprehensive univariate statistical summaries on numeric features.
    """

    @property
    def name(self) -> str:
        return "summary_stats"

    def run(self, df: pd.DataFrame, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        result_id = str(uuid.uuid4())

        if df is None or df.empty:
            raise AnalysisValidationError("Summary statistics requires a non-empty dataset.")

        target_cols = [
            c for c in options.get("target_columns", [])
            if c in df.columns and pd.api.types.is_numeric_dtype(df[c])
        ]
        if not target_cols:
            target_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        if not target_cols:
            raise AnalysisValidationError("Summary statistics requires at least one numeric column in the dataset.")

        primary_col = target_cols[0]
        s = df[primary_col].dropna()
        count = len(s)

        if count == 0:
            raise AnalysisValidationError(f"Column '{primary_col}' contains only null values.")

        mean_val = float(s.mean())
        median_val = float(s.median())
        std_val = float(s.std()) if count > 1 else 0.0
        min_val = float(s.min())
        max_val = float(s.max())
        q25 = float(s.quantile(0.25))
        q75 = float(s.quantile(0.75))
        iqr = q75 - q25
        skew_val = float(s.skew()) if count > 2 else 0.0

        skew_desc = "Symmetric" if abs(skew_val) < 0.5 else ("Right-skewed (positive)" if skew_val > 0 else "Left-skewed (negative)")

        kpis = [
            {
                "label": f"Mean ({primary_col})",
                "value": round(mean_val, 2),
                "formatted": f"{mean_val:,.2f}",
                "subtext": f"Median: {median_val:,.2f}",
            },
            {
                "label": "Std Deviation",
                "value": round(std_val, 2),
                "formatted": f"±{std_val:,.2f}",
                "subtext": f"Spread / volatility across {count:,} values",
            },
            {
                "label": "Min / Max Range",
                "value": round(max_val - min_val, 2),
                "formatted": f"[{min_val:,.2f} – {max_val:,.2f}]",
                "subtext": f"IQR: {iqr:,.2f} (Q1={q25:,.2f}, Q3={q75:,.2f})",
            },
            {
                "label": "Distribution Shape",
                "value": skew_desc,
                "formatted": skew_desc,
                "subtext": f"Skewness score: {skew_val:+.2f}",
            },
        ]

        findings = [
            f"Analyzed {len(target_cols)} numeric column(s) across {len(df):,} records.",
            f"Primary metric '{primary_col}': Mean={mean_val:,.2f}, Median={median_val:,.2f}, StdDev=±{std_val:,.2f}.",
            f"Range extends from {min_val:,.2f} to {max_val:,.2f} with a distribution described as {skew_desc.lower()}.",
        ]

        # Multi-column statistical overview table
        table_rows = []
        for col in target_cols:
            col_s = df[col].dropna()
            c_count = len(col_s)
            c_mean = float(col_s.mean()) if c_count > 0 else 0.0
            c_med = float(col_s.median()) if c_count > 0 else 0.0
            c_std = float(col_s.std()) if c_count > 1 else 0.0
            c_min = float(col_s.min()) if c_count > 0 else 0.0
            c_max = float(col_s.max()) if c_count > 0 else 0.0
            table_rows.append({
                "Column": col,
                "Count": c_count,
                "Mean": round(c_mean, 2),
                "Median": round(c_med, 2),
                "StdDev": round(c_std, 2),
                "Min": round(c_min, 2),
                "Max": round(c_max, 2),
            })

        # Chart: Distribution bins for primary column
        charts = []
        if count >= 4:
            bins = min(10, count)
            counts, bin_edges = np.histogram(s, bins=bins)
            bin_labels = [f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}" for i in range(len(counts))]
            charts.append({
                "chart_type": "bar",
                "title": f"Frequency Distribution ({primary_col})",
                "labels": bin_labels,
                "series": [{"name": "Count", "data": [int(c) for c in counts], "type": "bar"}],
                "options": {},
            })

        summary_text = (
            f"Computed summary statistics for {len(target_cols)} column(s). '{primary_col}': Mean is "
            f"{mean_val:,.2f} (median: {median_val:,.2f}) with standard deviation ±{std_val:,.2f}."
        )

        return {
            "result_id": result_id,
            "analysis_type": self.name,
            "status": "success",
            "summary": summary_text,
            "detailed_findings": findings,
            "kpis": kpis,
            "charts": charts,
            "table_data": table_rows,
            "table_columns": ["Column", "Count", "Mean", "Median", "StdDev", "Min", "Max"],
            "metadata": {
                "target_columns": target_cols,
                "primary_column": primary_col,
                "skewness": round(skew_val, 3),
                "total_rows": len(df),
            },
        }
