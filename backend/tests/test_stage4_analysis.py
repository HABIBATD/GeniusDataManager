"""
Unit tests for Stage 4 Analysis Module.
========================================
Tests all 5 analysis strategies (Sales, Trend, Comparison, Summary Stats, Outlier Detection),
custom AnalysisValidationError assertions on unsuitable data, and pluggable strategy registry.
"""
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import numpy as np
import pandas as pd

from stage4_analysis import (
    AnalysisValidationError,
    BaseAnalysis,
    ComparisonAnalysis,
    OutlierDetectionAnalysis,
    SalesAnalysis,
    SummaryStatsAnalysis,
    TrendAnalysis,
    get_strategy,
    list_strategies,
    register_strategy,
)
from models.schemas import AnalysisRequest


class TestStage4Analysis(unittest.TestCase):
    def setUp(self):
        # Synthetic sales & transactional dataset
        self.df_sales = pd.DataFrame({
            "order_date": pd.to_datetime([
                "2026-01-05", "2026-01-15", "2026-02-10",
                "2026-02-20", "2026-03-01", "2026-03-15",
            ]),
            "product": ["Laptop", "Mouse", "Laptop", "Mouse", "Keyboard", "Laptop"],
            "region": ["North", "North", "South", "North", "South", "North"],
            "quantity": [5, 20, 8, 25, 10, 12],
            "unit_price": [1200.0, 25.0, 1200.0, 25.0, 80.0, 1200.0],
            "revenue": [6000.0, 500.0, 9600.0, 625.0, 800.0, 14400.0],
        })

        # Dataset with clear outliers
        self.df_outliers = pd.DataFrame({
            "response_time": [10.2, 10.5, 9.8, 10.1, 10.4, 9.9, 10.3, 10.0, 500.0, -100.0]
        })

        # Pure text dataset without any numeric columns
        self.df_text = pd.DataFrame({
            "name": ["Alice", "Bob", "Charlie"],
            "city": ["New York", "London", "Tokyo"],
        })

    # ------------------------------------------------------------------------
    # 1. Sales Analysis Tests
    # ------------------------------------------------------------------------
    def test_sales_analysis_run_dict(self):
        strat = get_strategy("sales_analysis")
        res = strat.run(self.df_sales, {
            "target_columns": ["revenue"],
            "category_columns": ["product"],
            "date_column": "order_date",
        })

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis_type"], "sales_analysis")
        self.assertIn("Laptop", res["summary"])
        self.assertGreater(len(res["kpis"]), 0)
        self.assertGreater(len(res["charts"]), 0)
        self.assertEqual(res["charts"][0]["chart_type"], "bar")
        self.assertIsInstance(res["table_data"], list)

    def test_sales_analysis_pydantic_adapter(self):
        strat = get_strategy("sales_analysis")
        req = AnalysisRequest(
            aligned_id="aligned_001",
            analysis_type="sales_analysis",
            target_columns=["revenue"],
            category_columns=["product"],
            date_column="order_date",
        )
        res = strat.analyze(self.df_sales, req)
        self.assertEqual(res.analysis_type, "sales_analysis")
        self.assertGreater(len(res.kpis), 0)
        self.assertTrue(any("Total" in k.label for k in res.kpis))

    def test_sales_analysis_validation_error_no_numeric(self):
        strat = get_strategy("sales_analysis")
        with self.assertRaises(AnalysisValidationError) as ctx:
            strat.run(self.df_text)
        self.assertIn("numeric column", str(ctx.exception).lower())

    def test_sales_analysis_validation_error_empty_dataframe(self):
        strat = get_strategy("sales_analysis")
        with self.assertRaises(AnalysisValidationError):
            strat.run(pd.DataFrame())

    # ------------------------------------------------------------------------
    # 2. Trend Analysis Tests
    # ------------------------------------------------------------------------
    def test_trend_analysis_monthly_bucket(self):
        strat = get_strategy("trend_analysis")
        res = strat.run(self.df_sales, {
            "target_columns": ["revenue"],
            "date_column": "order_date",
            "bucket": "M",
        })

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis_type"], "trend_analysis")
        self.assertIn("trend", res["summary"].lower())
        self.assertEqual(res["charts"][0]["chart_type"], "line")
        self.assertIn("slope_pct", res["metadata"])

    def test_trend_analysis_validation_error_no_date(self):
        strat = get_strategy("trend_analysis")
        df_no_date = pd.DataFrame({"value": [10, 20, 30], "label": ["A", "B", "C"]})
        with self.assertRaises(AnalysisValidationError) as ctx:
            strat.run(df_no_date)
        self.assertIn("date", str(ctx.exception).lower())

    def test_trend_analysis_validation_error_no_numeric(self):
        strat = get_strategy("trend_analysis")
        df_dates_only = pd.DataFrame({
            "order_date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "text": ["A", "B"],
        })
        with self.assertRaises(AnalysisValidationError) as ctx:
            strat.run(df_dates_only)
        self.assertIn("numeric", str(ctx.exception).lower())

    # ------------------------------------------------------------------------
    # 3. Comparison Analysis Tests
    # ------------------------------------------------------------------------
    def test_comparison_analysis_category(self):
        strat = get_strategy("comparison")
        res = strat.run(self.df_sales, {
            "target_columns": ["revenue"],
            "category_columns": ["region"],
            "comparison_type": "category_comparison",
        })

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis_type"], "comparison")
        self.assertIn("North", res["summary"])
        self.assertGreater(len(res["kpis"]), 0)
        self.assertEqual(res["charts"][0]["chart_type"], "bar")

    def test_comparison_analysis_validation_error_no_numeric(self):
        strat = get_strategy("comparison")
        with self.assertRaises(AnalysisValidationError) as ctx:
            strat.run(self.df_text)
        self.assertIn("numeric", str(ctx.exception).lower())

    # ------------------------------------------------------------------------
    # 4. Summary Statistics Tests
    # ------------------------------------------------------------------------
    def test_summary_stats_run(self):
        strat = get_strategy("summary_stats")
        res = strat.run(self.df_sales, {
            "target_columns": ["revenue", "quantity"],
        })

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis_type"], "summary_stats")
        self.assertIn("Mean", res["summary"])
        self.assertGreaterEqual(len(res["table_data"]), 2)
        # Check table columns
        self.assertIn("Mean", res["table_columns"])
        self.assertIn("StdDev", res["table_columns"])

    def test_summary_stats_validation_error_no_numeric(self):
        strat = get_strategy("summary_stats")
        with self.assertRaises(AnalysisValidationError) as ctx:
            strat.run(self.df_text)
        self.assertIn("numeric", str(ctx.exception).lower())

    # ------------------------------------------------------------------------
    # 5. Outlier Detection Tests
    # ------------------------------------------------------------------------
    def test_outlier_detection_iqr(self):
        strat = get_strategy("outlier_detection")
        res = strat.run(self.df_outliers, {
            "target_columns": ["response_time"],
            "method": "iqr",
            "multiplier": 1.5,
        })

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["analysis_type"], "outlier_detection")
        self.assertGreaterEqual(res["metadata"]["outlier_count"], 2)  # 500.0 and -100.0
        self.assertEqual(res["charts"][0]["chart_type"], "pie")

    def test_outlier_detection_zscore(self):
        strat = get_strategy("outlier_detection")
        res = strat.run(self.df_outliers, {
            "target_columns": ["response_time"],
            "method": "zscore",
            "z_threshold": 2.0,
        })

        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["metadata"]["outlier_count"], 1)

    def test_outlier_detection_insufficient_rows(self):
        strat = get_strategy("outlier_detection")
        df_tiny = pd.DataFrame({"val": [1.0, 2.0]})
        with self.assertRaises(AnalysisValidationError) as ctx:
            strat.run(df_tiny)
        self.assertIn("at least 4", str(ctx.exception).lower())

    # ------------------------------------------------------------------------
    # 6. Strategy Registry Tests
    # ------------------------------------------------------------------------
    def test_strategy_registry_listing(self):
        strategies = list_strategies()
        self.assertIn("sales_analysis", strategies)
        self.assertIn("trend_analysis", strategies)
        self.assertIn("comparison", strategies)
        self.assertIn("summary_stats", strategies)
        self.assertIn("outlier_detection", strategies)

    def test_custom_pluggable_strategy(self):
        class CustomStrategy(BaseAnalysis):
            @property
            def name(self) -> str:
                return "custom_metric"

            def run(self, df: pd.DataFrame, options=None):
                return {"status": "success", "analysis_type": "custom_metric", "summary": "Custom OK"}

        register_strategy(CustomStrategy())
        self.assertIn("custom_metric", list_strategies())
        instance = get_strategy("custom_metric")
        self.assertEqual(instance.name, "custom_metric")
        res = instance.run(self.df_sales)
        self.assertEqual(res["summary"], "Custom OK")


if __name__ == "__main__":
    unittest.main()
