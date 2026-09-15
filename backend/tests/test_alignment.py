"""
Unit tests for data alignment, filtering, type coercion, and error collection.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from models.schemas import AlignmentConfig, ComputedColumn, FieldMapping, FilterRule
from services.alignment import align_dataframe, apply_filter_rule


class TestAlignment(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "Order Date": ["2026-01-05", "2026-01-12", "2026-01-18", "2026-02-02"],
            "Product": ["Laptop Pro", "Wireless Mouse", "Monitor 4K", "Laptop Pro"],
            "Qty": ["5", "25", "invalid_num", "7"],
            "Unit Price": ["$1200.00", "$25.50", "$350.00", "$1200.00"],
            "Region": ["West", "West", "East", "West"],
            "Internal_Notes": ["note1", "note2", "note3", "note4"],
        })

    def test_mapping_renaming_and_dropping(self):
        config = AlignmentConfig(
            file_id="test_file",
            mappings=[
                FieldMapping(source_column="Order Date", target_field="date", target_type="datetime", keep=True),
                FieldMapping(source_column="Product", target_field="product", target_type="string", keep=True),
                FieldMapping(source_column="Qty", target_field="quantity", target_type="int", keep=True),
                FieldMapping(source_column="Unit Price", target_field="price", target_type="float", keep=True),
                FieldMapping(source_column="Region", target_field="region", target_type="string", keep=True),
                FieldMapping(source_column="Internal_Notes", target_field="notes", target_type="string", keep=False),
            ],
            filters=[],
        )

        aligned_df, res = align_dataframe(self.df, config)
        self.assertNotIn("notes", aligned_df.columns)
        self.assertNotIn("Internal_Notes", aligned_df.columns)
        self.assertIn("date", aligned_df.columns)
        self.assertIn("quantity", aligned_df.columns)
        self.assertIn("price", aligned_df.columns)

        # Verify coercion error collected gracefully for 'invalid_num'
        self.assertEqual(res.coercion_errors_count, 1)
        self.assertEqual(res.coercion_error_samples[0].column, "quantity")
        self.assertEqual(res.coercion_error_samples[0].raw_value, "invalid_num")

        # Row with invalid_num is preserved, value set to NA
        self.assertEqual(len(aligned_df), 4)
        self.assertTrue(pd.isna(aligned_df.iloc[2]["quantity"]))

    def test_filter_rules_equals_and_range(self):
        # Filter equals
        rule_eq = FilterRule(column="Region", operator="equals", value="West")
        df_filtered = apply_filter_rule(self.df, rule_eq)
        self.assertEqual(len(df_filtered), 3)

        # Filter range on numeric
        df_num = pd.DataFrame({"val": [10, 25, 50, 75, 100]})
        rule_range = FilterRule(column="val", operator="range", value=[20, 80])
        df_range = apply_filter_rule(df_num, rule_range)
        self.assertEqual(len(df_range), 3)
        self.assertListEqual(list(df_range["val"]), [25, 50, 75])

    def test_computed_column(self):
        config = AlignmentConfig(
            file_id="test_file",
            mappings=[
                FieldMapping(source_column="Qty", target_field="quantity", target_type="float", keep=True),
                FieldMapping(source_column="Unit Price", target_field="price", target_type="float", keep=True),
            ],
            filters=[],
            computed_columns=[
                ComputedColumn(name="total_revenue", expression="quantity * price")
            ],
        )
        df_simple = pd.DataFrame({
            "Qty": [2, 5],
            "Unit Price": [100.0, 20.0],
        })
        aligned_df, _ = align_dataframe(df_simple, config)
        self.assertIn("total_revenue", aligned_df.columns)
        self.assertEqual(aligned_df.iloc[0]["total_revenue"], 200.0)
        self.assertEqual(aligned_df.iloc[1]["total_revenue"], 100.0)


if __name__ == "__main__":
    unittest.main()
