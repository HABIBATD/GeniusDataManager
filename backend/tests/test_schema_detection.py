"""
Unit tests for schema detection and semantic tagging engine.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from services.schema_detection import (
    analyze_column,
    detect_schema,
    infer_column_dtype,
    sniff_semantic_label,
)


class TestSchemaDetection(unittest.TestCase):
    def test_infer_dtype_and_semantic_date(self):
        s = pd.Series(["2026-01-01", "2026-02-15", "2026-03-20", "2026-04-10"])
        dtype = infer_column_dtype(s)
        self.assertEqual(dtype, "datetime")
        label = sniff_semantic_label("order_date", dtype, s)
        self.assertEqual(label, "date")

    def test_infer_dtype_and_semantic_currency(self):
        s = pd.Series(["$120.50", "$45.00", "$99.99", "$1,250.00"])
        dtype = infer_column_dtype(s)
        self.assertEqual(dtype, "float")
        label = sniff_semantic_label("unit_price", dtype, s)
        self.assertEqual(label, "currency")

    def test_infer_dtype_and_semantic_quantity(self):
        s = pd.Series([10, 25, 4, 100])
        dtype = infer_column_dtype(s)
        self.assertEqual(dtype, "int")
        label = sniff_semantic_label("qty", dtype, s)
        self.assertEqual(label, "quantity")

    def test_infer_dtype_and_semantic_id(self):
        s = pd.Series(["SKU-001", "SKU-002", "SKU-003", "SKU-004"])
        dtype = infer_column_dtype(s)
        self.assertEqual(dtype, "string")
        label = sniff_semantic_label("product_sku", dtype, s)
        self.assertEqual(label, "id")

    def test_detect_schema_full_dataframe(self):
        df = pd.DataFrame({
            "Order Date": ["2026-01-05", "2026-01-12", "2026-01-18"],
            "Product": ["Laptop", "Mouse", "Keyboard"],
            "Qty": [5, 25, 12],
            "Unit Price": ["$1200.00", "$25.50", "$85.00"],
            "Region": ["West", "West", "East"],
        })
        res = detect_schema(df, file_id="test_1", filename="sales.csv")
        self.assertEqual(res.row_count, 3)
        self.assertEqual(res.column_count, 5)

        col_dict = {c.name: c for c in res.columns}
        self.assertEqual(col_dict["Order Date"].dtype, "datetime")
        self.assertEqual(col_dict["Order Date"].semantic_label, "date")
        self.assertEqual(col_dict["Qty"].dtype, "int")
        self.assertEqual(col_dict["Qty"].semantic_label, "quantity")
        self.assertEqual(col_dict["Unit Price"].semantic_label, "currency")
        self.assertEqual(col_dict["Region"].semantic_label, "geo")


if __name__ == "__main__":
    unittest.main()
