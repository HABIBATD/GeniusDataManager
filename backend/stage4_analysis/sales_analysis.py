"""
Stage 4 — Sales Analysis Strategy.
=================================
Computes sales totals, averages, top-N products/categories breakdowns,
period-over-period growth rates, and plain-language executive findings.
"""
import uuid
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from stage4_analysis.base import AnalysisValidationError, BaseAnalysis


def _json_safe(val: Any) -> Any:
    """Convert NaN/Inf/numpy types to JSON-safe primitives."""
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


class SalesAnalysis(BaseAnalysis):
    """
    Analyzes sales/revenue metrics across dimensions, categories, and time periods.
    """

    @property
    def name(self) -> str:
        return "sales_analysis"

    def run(self, df: pd.DataFrame, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        result_id = str(uuid.uuid4())

        if df is None or df.empty:
            raise AnalysisValidationError("Sales analysis requires a non-empty dataset.")

        df_work = df.copy()

        # 1. Identify or calculate Revenue / Metric column
        revenue_col = None
        target_columns = options.get("target_columns", [])
        for col in target_columns:
            if col in df_work.columns and pd.api.types.is_numeric_dtype(df_work[col]):
                revenue_col = col
                break

        # If not specified in targets, look for common revenue column names
        if not revenue_col:
            for col in df_work.columns:
                lower = col.lower()
                if any(k in lower for k in ["revenue", "sales", "total_price", "amount", "total"]):
                    if pd.api.types.is_numeric_dtype(df_work[col]):
                        revenue_col = col
                        break

        # Check if revenue can be synthesized from qty * unit_price
        if not revenue_col:
            qty_col = None
            price_col = None
            for col in df_work.columns:
                c_low = col.lower()
                if any(k in c_low for k in ["qty", "quantity", "units"]) and pd.api.types.is_numeric_dtype(df_work[col]):
                    qty_col = col
                elif any(k in c_low for k in ["unit_price", "price", "rate", "cost"]) and pd.api.types.is_numeric_dtype(df_work[col]):
                    price_col = col

            if qty_col and price_col:
                df_work["calculated_revenue"] = df_work[qty_col] * df_work[price_col]
                revenue_col = "calculated_revenue"

        # Fallback to any numeric column
        if not revenue_col:
            for col in df_work.columns:
                if pd.api.types.is_numeric_dtype(df_work[col]):
                    revenue_col = col
                    break

        if not revenue_col:
            raise AnalysisValidationError(
                "Sales analysis requires at least one numeric column (e.g. 'revenue', 'sales', 'amount', or 'price')."
            )

        # 2. Identify Category column
        cat_col = None
        category_columns = options.get("category_columns", [])
        for col in category_columns:
            if col in df_work.columns:
                cat_col = col
                break

        if not cat_col:
            for col in df_work.columns:
                c_low = col.lower()
                if any(k in c_low for k in ["product", "category", "item", "segment", "region", "department", "channel"]):
                    cat_col = col
                    break

        if not cat_col:
            for col in df_work.columns:
                if col != revenue_col and not pd.api.types.is_numeric_dtype(df_work[col]):
                    cat_col = col
                    break

        # 3. Identify Date column
        date_col = options.get("date_column")
        if not date_col or date_col not in df_work.columns:
            for col in df_work.columns:
                if pd.api.types.is_datetime64_any_dtype(df_work[col]) or any(k in col.lower() for k in ["date", "time", "order_date", "day"]):
                    date_col = col
                    break

        # 4. Calculate Core Metrics
        total_revenue = float(df_work[revenue_col].sum())
        avg_revenue = float(df_work[revenue_col].mean())
        total_orders = len(df_work)
        kpis = [
            {
                "label": f"Total {revenue_col.replace('_', ' ').title()}",
                "value": round(total_revenue, 2),
                "formatted": f"${total_revenue:,.2f}" if "price" in revenue_col or "rev" in revenue_col or "sales" in revenue_col else f"{total_revenue:,.2f}",
                "subtext": f"Across {total_orders:,} total records",
            },
            {
                "label": f"Average {revenue_col.replace('_', ' ').title()}",
                "value": round(avg_revenue, 2),
                "formatted": f"${avg_revenue:,.2f}" if "price" in revenue_col or "rev" in revenue_col or "sales" in revenue_col else f"{avg_revenue:,.2f}",
                "subtext": "Per transaction / line item",
            },
            {
                "label": "Total Record Count",
                "value": total_orders,
                "formatted": f"{total_orders:,}",
                "subtext": "Volume analyzed",
            },
        ]

        charts = []
        findings = []
        summary_text = f"Total revenue across {total_orders:,} records is {kpis[0]['formatted']}, averaging {kpis[1]['formatted']} per entry."

        # 5. Top-N Category Breakdown
        top_category_name = None
        if cat_col:
            cat_group = (
                df_work.groupby(cat_col)[revenue_col]
                .sum()
                .reset_index()
                .sort_values(by=revenue_col, ascending=False)
            )
            top_n = cat_group.head(10)
            labels = [str(x) for x in top_n[cat_col].tolist()]
            values = [round(float(v), 2) for v in top_n[revenue_col].tolist()]

            charts.append({
                "chart_type": "bar",
                "title": f"Top {len(top_n)} {cat_col.replace('_', ' ').title()} by {revenue_col.replace('_', ' ').title()}",
                "labels": labels,
                "series": [{"name": revenue_col.title(), "data": values, "type": "bar"}],
                "options": {"horizontal": False},
            })

            if len(cat_group) > 0:
                top_category_name = str(cat_group.iloc[0][cat_col])
                top_cat_rev = float(cat_group.iloc[0][revenue_col])
                pct_share = (top_cat_rev / total_revenue * 100) if total_revenue > 0 else 0
                kpis.append({
                    "label": f"Top {cat_col.title()}",
                    "value": top_category_name,
                    "formatted": f"{top_category_name} ({pct_share:.1f}%)",
                    "subtext": f"${top_cat_rev:,.2f} total revenue",
                })
                findings.append(
                    f"'{top_category_name}' is the top performing {cat_col}, contributing ${top_cat_rev:,.2f} ({pct_share:.1f}% of total {revenue_col})."
                )
                summary_text += f" The leading {cat_col} was '{top_category_name}', generating {pct_share:.1f}% of overall revenue."

        # 6. Time-based Growth & Trends
        if date_col:
            try:
                df_work["_dt"] = pd.to_datetime(df_work[date_col], errors="coerce")
                df_time = df_work.dropna(subset=["_dt"]).sort_values("_dt")
                if not df_time.empty:
                    df_time["_period"] = df_time["_dt"].dt.to_period("M").astype(str)
                    time_group = df_time.groupby("_period")[revenue_col].sum().reset_index()
                    t_labels = time_group["_period"].tolist()
                    t_vals = [round(float(v), 2) for v in time_group[revenue_col].tolist()]

                    charts.append({
                        "chart_type": "line",
                        "title": f"{revenue_col.replace('_', ' ').title()} Monthly Trend",
                        "labels": t_labels,
                        "series": [{"name": "Monthly Total", "data": t_vals, "type": "line"}],
                        "options": {},
                    })

                    if len(t_vals) >= 2:
                        first_val = t_vals[0]
                        last_val = t_vals[-1]
                        growth = ((last_val - first_val) / first_val * 100) if first_val > 0 else 0
                        kpis.append({
                            "label": "Period Growth",
                            "value": round(growth, 1),
                            "formatted": f"{growth:+.1f}%",
                            "change_pct": round(growth, 1),
                            "subtext": f"From {t_labels[0]} to {t_labels[-1]}",
                        })
                        findings.append(
                            f"Performance grew by {growth:+.1f}% between {t_labels[0]} and {t_labels[-1]}."
                        )
            except Exception:
                pass

        table_preview = df_work.head(20).to_dict(orient="records")
        safe_preview = [{k: _json_safe(v) for k, v in row.items() if not str(k).startswith("_")} for row in table_preview]

        return {
            "result_id": result_id,
            "analysis_type": self.name,
            "status": "success",
            "summary": summary_text,
            "detailed_findings": findings,
            "kpis": kpis,
            "charts": charts,
            "table_data": safe_preview,
            "table_columns": [c for c in df_work.columns if not c.startswith("_")],
            "metadata": {
                "revenue_column": revenue_col,
                "category_column": cat_col,
                "date_column": date_col,
                "row_count": total_orders,
            },
        }
