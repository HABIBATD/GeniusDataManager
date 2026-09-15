"""
Sales Analysis Strategy for GeniusDataManager.
Computes totals, averages, product/category breakdowns, period-over-period growth rates,
and plain-language insights.
"""
import uuid
from typing import Optional
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


class SalesAnalysis(BaseAnalysis):
    @property
    def name(self) -> str:
        return "sales_analysis"

    def analyze(self, df: pd.DataFrame, request: AnalysisRequest) -> AnalysisResult:
        if df.empty:
            return AnalysisResult(
                result_id=str(uuid.uuid4()),
                analysis_type=self.name,
                summary="The dataset is empty. No sales analysis could be performed.",
                detailed_findings=["No records matched your selection or filters."],
                kpis=[],
                charts=[],
            )

        df_work = df.copy()

        # 1. Identify or synthesize the revenue metric
        revenue_col = None
        # Check target_columns first
        for col in request.target_columns:
            if col in df_work.columns and pd.api.types.is_numeric_dtype(df_work[col]):
                revenue_col = col
                break

        # If not specified, look for revenue, sales, amount, total, price
        if not revenue_col:
            for col in df_work.columns:
                lower = col.lower()
                if any(k in lower for k in ["revenue", "sales", "total_price", "amount", "total"]):
                    if pd.api.types.is_numeric_dtype(df_work[col]):
                        revenue_col = col
                        break

        # Check if we can compute revenue = quantity * unit_price
        qty_col = None
        price_col = None
        for col in df_work.columns:
            c_low = col.lower()
            if any(k in c_low for k in ["qty", "quantity", "units"]) and pd.api.types.is_numeric_dtype(df_work[col]):
                qty_col = col
            elif any(k in c_low for k in ["unit_price", "price", "rate", "cost"]) and pd.api.types.is_numeric_dtype(df_work[col]):
                price_col = col

        if not revenue_col and qty_col and price_col:
            df_work["calculated_revenue"] = df_work[qty_col] * df_work[price_col]
            revenue_col = "calculated_revenue"

        # If still no numeric revenue column, pick the first numeric column
        if not revenue_col:
            num_cols = [c for c in df_work.columns if pd.api.types.is_numeric_dtype(df_work[c])]
            if num_cols:
                revenue_col = num_cols[0]
            else:
                raise ValueError("Sales analysis requires at least one numeric metric column (e.g. revenue, price, quantity).")

        # 2. Identify Category / Product column
        cat_col = None
        if request.category_columns:
            for c in request.category_columns:
                if c in df_work.columns:
                    cat_col = c
                    break
        if not cat_col:
            for col in df_work.columns:
                c_low = col.lower()
                if any(k in c_low for k in ["product", "item", "category", "sku", "region", "channel"]):
                    cat_col = col
                    break

        # 3. Identify Date column
        date_col = request.date_column
        if not date_col or date_col not in df_work.columns:
            for col in df_work.columns:
                if pd.api.types.is_datetime64_any_dtype(df_work[col]) or any(k in col.lower() for k in ["date", "time", "period", "day", "month"]):
                    date_col = col
                    break

        # Calculate Core Metrics
        total_rev = float(df_work[revenue_col].sum(skipna=True))
        avg_rev = float(df_work[revenue_col].mean(skipna=True))
        total_orders = len(df_work)
        total_units = int(df_work[qty_col].sum(skipna=True)) if qty_col else total_orders

        kpis: list[KPICard] = [
            KPICard(
                label="Total Revenue",
                value=round(total_rev, 2),
                formatted=f"${total_rev:,.2f}" if total_rev >= 0 else f"-${abs(total_rev):,.2f}",
                subtext="Total across all matching records",
            ),
            KPICard(
                label="Average Order Value",
                value=round(avg_rev, 2),
                formatted=f"${avg_rev:,.2f}",
                subtext="Average revenue per transaction",
            ),
            KPICard(
                label="Total Volume",
                value=total_units,
                formatted=f"{total_units:,} units" if qty_col else f"{total_orders:,} orders",
                subtext=f"{total_orders:,} total transactions",
            ),
        ]

        detailed_findings = []
        charts: list[ChartData] = []
        growth_rate = None
        top_cat_name = "N/A"
        top_cat_share = 0.0

        # 4. Category breakdown
        if cat_col and cat_col in df_work.columns:
            cat_group = df_work.groupby(cat_col)[revenue_col].sum().sort_values(ascending=False)
            top_n = cat_group.head(8)
            if not top_n.empty and total_rev > 0:
                top_cat_name = str(top_n.index[0])
                top_cat_rev = float(top_n.iloc[0])
                top_cat_share = round((top_cat_rev / total_rev) * 100, 1)
                kpis.append(
                    KPICard(
                        label=f"Top {cat_col.title()}",
                        value=top_cat_name,
                        formatted=top_cat_name,
                        subtext=f"${top_cat_rev:,.2f} ({top_cat_share}% share)",
                    )
                )
                detailed_findings.append(
                    f"Top-performing {cat_col} is '{top_cat_name}', generating ${top_cat_rev:,.2f} ({top_cat_share}% of total sales)."
                )

            # Category bar chart
            charts.append(
                ChartData(
                    chart_type="bar",
                    title=f"Revenue by {cat_col.title()}",
                    labels=[str(x) for x in top_n.index],
                    series=[
                        ChartSeries(
                            name="Revenue",
                            data=[round(float(v), 2) for v in top_n.values],
                            type="bar",
                        )
                    ],
                )
            )

        # 5. Time series & Growth Rate (if date column exists)
        if date_col and date_col in df_work.columns:
            try:
                date_s = pd.to_datetime(df_work[date_col], errors="coerce")
                valid_date_mask = date_s.notna()
                if valid_date_mask.sum() > 1:
                    df_time = df_work[valid_date_mask].copy()
                    df_time["_period"] = date_s[valid_date_mask].dt.to_period("M").astype(str)
                    period_rev = df_time.groupby("_period")[revenue_col].sum().sort_index()

                    if len(period_rev) > 1:
                        # Compute latest period vs previous period growth
                        prev_val = float(period_rev.iloc[-2])
                        last_val = float(period_rev.iloc[-1])
                        if prev_val > 0:
                            growth_rate = round(((last_val - prev_val) / prev_val) * 100, 1)
                            direction = "grew" if growth_rate >= 0 else "declined"
                            kpis[0].change_pct = growth_rate
                            detailed_findings.append(
                                f"Period-over-period revenue {direction} by {abs(growth_rate)}% in the latest period."
                            )

                    charts.append(
                        ChartData(
                            chart_type="line",
                            title=f"Monthly Revenue Trend ({date_col})",
                            labels=list(period_rev.index),
                            series=[
                                ChartSeries(
                                    name="Monthly Revenue",
                                    data=[round(float(v), 2) for v in period_rev.values],
                                    type="line",
                                )
                            ],
                        )
                    )
            except Exception:
                pass

        # Build Plain-Language Summary
        summary_parts = [f"Total revenue generated is ${total_rev:,.2f} across {total_orders:,} transactions."]
        if growth_rate is not None:
            direction = "grew" if growth_rate >= 0 else "declined"
            summary_parts.append(f"Revenue {direction} {abs(growth_rate)}% month-over-month")
            if top_cat_name != "N/A":
                summary_parts[-1] += f", driven mainly by {top_cat_name}."
            else:
                summary_parts[-1] += "."
        elif top_cat_name != "N/A":
            summary_parts.append(f"Leading performer is {top_cat_name} ({top_cat_share}% of total volume).")

        summary = " ".join(summary_parts)

        # Prepare underlying table data for export / review
        preview_cols = [c for c in df_work.columns if not c.startswith("_")][:15]
        table_records = []
        for _, row in df_work.head(100).iterrows():
            table_records.append({c: json_safe_value(row[c]) for c in preview_cols})

        return AnalysisResult(
            result_id=str(uuid.uuid4()),
            analysis_type=self.name,
            summary=summary,
            detailed_findings=detailed_findings,
            kpis=kpis,
            charts=charts,
            table_data=table_records,
            table_columns=preview_cols,
            metadata={"revenue_column": revenue_col, "category_column": cat_col, "date_column": date_col},
        )
