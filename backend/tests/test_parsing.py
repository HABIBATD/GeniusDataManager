"""
Unit tests for file parsing service.
"""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from services.parsing import (
    clean_dataframe,
    detect_excel_sheets,
    parse_csv,
    parse_excel,
    parse_json,
    parse_uploaded_file,
    sanitize_column_names,
)


class TestParsingService(unittest.TestCase):
    def test_sanitize_column_names_deduplication(self):
        raw_cols = ["date", "sales", "date", "sales", "", "Unnamed: 5"]
        sanitized = sanitize_column_names(raw_cols)
        self.assertEqual(sanitized[0], "date")
        self.assertEqual(sanitized[1], "sales")
        self.assertEqual(sanitized[2], "date_1")
        self.assertEqual(sanitized[3], "sales_1")
        self.assertEqual(sanitized[4], "column_5")
        self.assertEqual(sanitized[5], "column_6")

    def test_parse_csv(self):
        csv_content = b"Item,Qty,Price\nWidget A,10,$15.50\nWidget B,20,$25.00\n"
        df = parse_csv(csv_content)
        self.assertEqual(len(df), 2)
        self.assertListEqual(list(df.columns), ["Item", "Qty", "Price"])

    def test_parse_json(self):
        json_content = b'[{"user": "Alice", "score": 95}, {"user": "Bob", "score": 88}]'
        df = parse_json(json_content)
        self.assertEqual(len(df), 2)
        self.assertIn("user", df.columns)
        self.assertIn("score", df.columns)

    def test_parse_excel_multi_sheet(self):
        excel_path = Path("fixtures/sample_quarterly.xlsx")
        if not excel_path.exists():
            self.skipTest("sample_quarterly.xlsx not found")

        content = excel_path.read_bytes()
        sheets = detect_excel_sheets(content)
        self.assertIn("Q1_Sales", sheets)
        self.assertIn("Q2_Sales", sheets)

        df_q1, _ = parse_uploaded_file(content, "sample.xlsx", sheet_name="Q1_Sales")
        self.assertEqual(len(df_q1), 5)
        self.assertIn("Revenue", df_q1.columns)

        df_q2, _ = parse_uploaded_file(content, "sample.xlsx", sheet_name="Q2_Sales")
        self.assertEqual(len(df_q2), 5)
        self.assertEqual(df_q2.iloc[0]["Revenue"], 61000)


if __name__ == "__main__":
    unittest.main()
