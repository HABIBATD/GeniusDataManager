"""
Test End-to-End API Endpoints with FastAPI TestClient
=====================================================
"""
import json
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app


class TestApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_02_upload_json_file(self):
        sample_json = [
            {"department": "Engineering", "team": "Backend", "budget": 120000, "headcount": 8},
            {"department": "Engineering", "team": "Frontend", "budget": 95000, "headcount": 6},
            {"department": "Marketing", "team": "Growth", "budget": 65000, "headcount": 4},
            {"department": "Marketing", "team": "Brand", "budget": 45000, "headcount": 3},
            {"department": "Sales", "team": "Enterprise", "budget": 180000, "headcount": 10},
        ]
        files = {
            "file": ("department_data.json", json.dumps(sample_json).encode("utf-8"), "application/json")
        }
        upload_resp = self.client.post("/api/upload", files=files)
        self.assertEqual(upload_resp.status_code, 200)
        data = upload_resp.json()
        self.assertIn("file_id", data)
        self.assertEqual(data["filename"], "department_data.json")

    def test_03_custom_extension_upload(self):
        custom_data = "Server;Region;Ping_ms;Active\nAlpha;US-East;18.5;True\nBeta;EU-West;24.2;True\nGamma;AP-South;65.0;False\n"
        custom_files = {
            "file": ("cluster_nodes.custom", custom_data.encode("utf-8"), "text/plain")
        }
        # When .custom is uploaded, check upload API validation
        # Allowed extensions in services/parsing are .csv, .tsv, .xlsx, .xls, .json, etc.
        # Check standard upload behavior
        pass


if __name__ == "__main__":
    unittest.main()
