"""
Stage 4 — Outlier Detection Strategy.
====================================
Detects statistical anomalies and extreme values in numeric features using
IQR (Interquartile Range) fencing or Z-score standard deviation thresholds.
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


class OutlierDetectionAnalysis(BaseAnalysis):
    """
    Identifies outliers and extreme values using IQR or Z-score statistical tests.
    """

    @property
    def name(self) -> str:
        return "outlier_detection"

    def run(self, df: pd.DataFrame, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        result_id = str(uuid.uuid4())

        if df is None or df.empty:
            raise AnalysisValidationError("Outlier detection requires a non-empty dataset.")

        # 1. Identify target numeric column
        target_col = None
        target_columns = options.get("target_columns", [])
        for col in target_columns:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                target_col = col
                break

        if not target_col:
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    target_col = col
                    break

        if not target_col:
            raise AnalysisValidationError("Outlier detection requires at least one numeric column.")

        s = df[target_col].dropna()
        total_valid = len(s)

        if total_valid < 4:
            raise AnalysisValidationError(
                f"Outlier detection requires at least 4 non-null numeric values in column '{target_col}' (found {total_valid})."
            )

        method = options.get("method", "iqr").lower()
        multiplier = float(options.get("multiplier", 1.5))
        z_threshold = float(options.get("z_threshold", 2.5))

        outlier_mask = pd.Series(False, index=df.index)
        lower_bound = 0.0
        upper_bound = 0.0

        if method == "zscore":
            mean_val = float(s.mean())
            std_val = float(s.std())
            if std_val > 0:
                z_scores = (df[target_col] - mean_val) / std_val
                outlier_mask = z_scores.abs() > z_threshold
                lower_bound = mean_val - z_threshold * std_val
                upper_bound = mean_val + z_threshold * std_val
        else:
            # Default: IQR fencing
            method = "iqr"
            q25 = float(s.quantile(0.25))
            q75 = float(s.quantile(0.75))
            iqr = q75 - q25
            lower_bound = q25 - (multiplier * iqr)
            upper_bound = q75 + (multiplier * iqr)
            outlier_mask = (df[target_col] < lower_bound) | (df[target_col] > upper_bound)

        outlier_count = int(outlier_mask.sum())
        outlier_pct = round((outlier_count / len(df)) * 100, 2)
        normal_count = len(df) - outlier_count

        kpis = [
            {
                "label": "Outliers Detected",
                "value": outlier_count,
                "formatted": f"{outlier_count} records ({outlier_pct:.1f}%)",
                "subtext": f"Using {method.upper()} test (bounds: [{lower_bound:,.2f} – {upper_bound:,.2f}])",
            },
            {
                "label": "Normal Records",
                "value": normal_count,
                "formatted": f"{normal_count:,} records",
                "subtext": f"{(100 - outlier_pct):.1f}% within expected bounds",
            },
            {
                "label": f"Normal Expected Range",
                "value": round(upper_bound - lower_bound, 2),
                "formatted": f"[{lower_bound:,.2f} to {upper_bound:,.2f}]",
                "subtext": f"Lower: {lower_bound:,.2f} | Upper: {upper_bound:,.2f}",
            },
        ]

        findings = [
            f"Evaluated column '{target_col}' using {method.upper()} outlier testing across {len(df):,} rows.",
            f"Identified {outlier_count} anomaly record(s) ({outlier_pct:.1f}% of dataset) falling outside bounds [{lower_bound:,.2f}, {upper_bound:,.2f}].",
        ]

        if outlier_count > 0:
            outlier_rows = df[outlier_mask]
            extreme_val = outlier_rows[target_col].max() if (outlier_rows[target_col].max() > upper_bound) else outlier_rows[target_col].min()
            findings.append(f"Most extreme outlier detected was value {extreme_val:,.2f}.")
            summary_text = (
                f"Detected {outlier_count} statistical outlier(s) ({outlier_pct:.1f}% of data) in column '{target_col}' "
                f"using {method.upper()} thresholding. Expected normal range is [{lower_bound:,.2f}, {upper_bound:,.2f}]."
            )
        else:
            summary_text = (
                f"No statistical outliers detected in '{target_col}' using {method.upper()} thresholding. "
                f"All {len(df):,} records sit cleanly within normal expected range [{lower_bound:,.2f}, {upper_bound:,.2f}]."
            )

        charts = [
            {
                "chart_type": "pie",
                "title": f"Outlier Distribution ({target_col})",
                "labels": ["Normal Records", "Flagged Outliers"],
                "series": [{"name": "Record Count", "data": [normal_count, outlier_count], "type": "pie"}],
                "options": {},
            }
        ]

        # Extract outlier sample rows
        df_flagged = df.copy()
        df_flagged["_is_outlier"] = outlier_mask
        outliers_subset = df_flagged[df_flagged["_is_outlier"]].head(25)
        table_data = [
            {k: _json_safe(v) for k, v in row.items()}
            for row in outliers_subset.to_dict(orient="records")
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
            "table_columns": list(table_data[0].keys()) if table_data else list(df.columns) + ["_is_outlier"],
            "metadata": {
                "target_column": target_col,
                "method": method,
                "lower_bound": round(lower_bound, 4),
                "upper_bound": round(upper_bound, 4),
                "outlier_count": outlier_count,
                "outlier_pct": outlier_pct,
            },
        }
