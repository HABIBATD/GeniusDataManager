"""
End-to-End API Integration test validating the Section 9 scenario.
"""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from main import app


class TestEndToEndApiFlow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.csv_path = Path("fixtures/sample_sales.csv")
        self.assertTrue(self.csv_path.exists(), "sample_sales.csv fixture must exist")

    def test_section_9_full_workflow(self):
        # 1. POST /api/upload
        with open(self.csv_path, "rb") as f:
            upload_res = self.client.post(
                "/api/upload",
                files={"file": ("sample_sales.csv", f, "text/csv")},
            )
        self.assertEqual(upload_res.status_code, 200)
        upload_data = upload_res.json()
        file_id = upload_data["file_id"]
        self.assertIsNotNone(file_id)

        # 2. GET /api/schema/{file_id}
        schema_res = self.client.get(f"/api/schema/{file_id}")
        self.assertEqual(schema_res.status_code, 200)
        schema_data = schema_res.json()
        self.assertEqual(schema_data["file_id"], file_id)
        self.assertGreaterEqual(schema_data["row_count"], 15)

        # Verify inferred dtypes
        col_map = {c["name"]: c for c in schema_data["columns"]}
        self.assertEqual(col_map["Order Date"]["dtype"], "datetime")
        self.assertEqual(col_map["Order Date"]["semantic_label"], "date")
        self.assertEqual(col_map["Qty"]["dtype"], "int")
        self.assertEqual(col_map["Unit Price"]["semantic_label"], "currency")

        # 3. POST /api/align with mappings and filter: region = "West"
        align_payload = {
            "file_id": file_id,
            "mappings": [
                {"source_column": "Order Date", "target_field": "date", "target_type": "datetime", "keep": True},
                {"source_column": "Product", "target_field": "product", "target_type": "string", "keep": True},
                {"source_column": "Qty", "target_field": "quantity", "target_type": "int", "keep": True},
                {"source_column": "Unit Price", "target_field": "unit_price", "target_type": "float", "keep": True},
                {"source_column": "Region", "target_field": "region", "target_type": "string", "keep": True},
            ],
            "filters": [
                {"column": "region", "operator": "equals", "value": "West"}
            ],
            "computed_columns": [
                {"name": "revenue", "expression": "quantity * unit_price"}
            ]
        }

        align_res = self.client.post("/api/align", json=align_payload)
        self.assertEqual(align_res.status_code, 200)
        align_data = align_res.json()
        aligned_id = align_data["aligned_id"]
        self.assertIsNotNone(aligned_id)
        self.assertGreater(align_data["total_rows_aligned"], 0)
        self.assertLess(align_data["total_rows_aligned"], align_data["total_rows_source"])

        # 4. POST /api/analyze with sales_analysis and period_over_period
        analyze_payload = {
            "aligned_id": aligned_id,
            "analysis_type": "sales_analysis",
            "comparison_type": "period_over_period",
            "target_columns": ["revenue"],
            "category_columns": ["product"],
            "date_column": "date",
        }

        analyze_res = self.client.post("/api/analyze", json=analyze_payload)
        self.assertEqual(analyze_res.status_code, 200)
        analyze_data = analyze_res.json()
        result_id = analyze_data["result_id"]
        self.assertIsNotNone(result_id)
        self.assertIn("revenue", analyze_data["summary"].lower())
        self.assertGreaterEqual(len(analyze_data["kpis"]), 3)
        self.assertGreaterEqual(len(analyze_data["charts"]), 1)

        # 5. GET /api/export/{result_id}?format=csv
        export_csv_res = self.client.get(f"/api/export/{result_id}?format=csv")
        self.assertEqual(export_csv_res.status_code, 200)
        self.assertIn("text/csv", export_csv_res.headers["content-type"])
        self.assertIn("Laptop Pro", export_csv_res.text)

        # 6. GET /api/export/{result_id}?format=json
        export_json_res = self.client.get(f"/api/export/{result_id}?format=json")
        self.assertEqual(export_json_res.status_code, 200)
        self.assertIn("application/json", export_json_res.headers["content-type"])

        # 7. GET /api/export/{result_id}?format=xlsx
        export_xlsx_res = self.client.get(f"/api/export/{result_id}?format=xlsx")
        self.assertEqual(export_xlsx_res.status_code, 200)
        self.assertIn("openxmlformats", export_xlsx_res.headers["content-type"])
        self.assertGreater(len(export_xlsx_res.content), 1000)


if __name__ == "__main__":
    unittest.main()
