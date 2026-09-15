"""
Unit tests for analysis strategies: sales, trend, comparison, summary stats, outlier detection.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from models.schemas import AnalysisRequest
from services.analysis import get_strategy


class TestAnalysisStrategies(unittest.TestCase):
    def setUp(self):
        self.df_sales = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-05", "2026-01-15", "2026-02-10", "2026-02-20", "2026-03-01", "2026-03-15"]),
            "product": ["Laptop", "Mouse", "Laptop", "Mouse", "Keyboard", "Laptop"],
            "quantity": [5, 20, 8, 25, 10, 12],
            "price": [1200.0, 25.0, 1200.0, 25.0, 80.0, 1200.0],
            "revenue": [6000.0, 500.0, 9600.0, 625.0, 800.0, 14400.0],
            "region": ["West", "West", "East", "West", "Central", "West"],
        })

    def test_sales_analysis(self):
        strat = get_strategy("sales_analysis")
        req = AnalysisRequest(
            aligned_id="test_aligned",
            analysis_type="sales_analysis",
            target_columns=["revenue"],
            category_columns=["product"],
            date_column="date",
        )
        res = strat.analyze(self.df_sales, req)
        self.assertEqual(res.analysis_type, "sales_analysis")
        self.assertGreater(len(res.kpis), 0)
        self.assertIn("Laptop", res.summary)
        self.assertGreater(len(res.charts), 0)

    def test_trend_analysis(self):
        strat = get_strategy("trend_analysis")
        req = AnalysisRequest(
            aligned_id="test_aligned",
            analysis_type="trend_analysis",
            target_columns=["revenue"],
            date_column="date",
            options={"bucket": "M"},
        )
        res = strat.analyze(self.df_sales, req)
        self.assertEqual(res.analysis_type, "trend_analysis")
        self.assertIn("trend", res.summary.lower())
        self.assertEqual(res.charts[0].chart_type, "line")

    def test_comparison_analysis(self):
        strat = get_strategy("comparison")
        req = AnalysisRequest(
            aligned_id="test_aligned",
            analysis_type="comparison",
            comparison_type="category_comparison",
            target_columns=["revenue"],
            category_columns=["region"],
        )
        res = strat.analyze(self.df_sales, req)
        self.assertEqual(res.analysis_type, "comparison")
        self.assertIn("West", res.summary)

    def test_summary_stats(self):
        strat = get_strategy("summary_stats")
        req = AnalysisRequest(
            aligned_id="test_aligned",
            analysis_type="summary_stats",
            target_columns=["revenue", "quantity"],
        )
        res = strat.analyze(self.df_sales, req)
        self.assertEqual(res.analysis_type, "summary_stats")
        self.assertIn("Mean", res.summary)

    def test_outlier_detection(self):
        df_outliers = pd.DataFrame({
            "score": [10.0, 11.0, 10.5, 9.8, 10.2, 10.1, 10.4, 9.9, 100.0]  # 100.0 is an outlier
        })
        strat = get_strategy("outlier_detection")
        req = AnalysisRequest(
            aligned_id="test_aligned",
            analysis_type="outlier_detection",
            target_columns=["score"],
            options={"method": "iqr", "multiplier": 1.5},
        )
        res = strat.analyze(df_outliers, req)
        self.assertEqual(res.analysis_type, "outlier_detection")
        self.assertGreaterEqual(res.metadata["outlier_count"], 1)


if __name__ == "__main__":
    unittest.main()
