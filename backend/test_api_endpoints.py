"""
Test End-to-End API Endpoints
"""
import requests
import json

BASE = "http://127.0.0.1:8000"

# 1. Health check
resp = requests.get(f"{BASE}/health")
assert resp.status_code == 200, f"Health check failed: {resp.text}"
print("Health check: OK")

# 2. Upload JSON file
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
upload_resp = requests.post(f"{BASE}/upload", files=files)
assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
data = upload_resp.json()
task_id = data["task_id"]
print(f"Upload successful. Task ID: {task_id}")
assert data["status"] == "complete"
assert data["stage2"]["composition"] is not None
print(f"Health Score: {data['stage2']['composition']['health_score']}")

# 3. Layout planning
layout_resp = requests.post(f"{BASE}/layout", json={"task_id": task_id})
assert layout_resp.status_code == 200, f"Layout failed: {layout_resp.text}"
layout_data = layout_resp.json()
print(f"Layout planned: {len(layout_data['charts'])} chart(s)")

# 4. Exports: JSON, XLSX, CSV
json_export = requests.get(f"{BASE}/export/{task_id}/json")
assert json_export.status_code == 200, f"JSON export failed: {json_export.text}"
assert len(json_export.content) > 0
print(f"JSON export: {len(json_export.content)} bytes")

xlsx_export = requests.get(f"{BASE}/export/{task_id}/xlsx")
assert xlsx_export.status_code == 200, f"XLSX export failed: {xlsx_export.text}"
print(f"XLSX export: {len(xlsx_export.content)} bytes")

csv_export = requests.get(f"{BASE}/export/{task_id}/csv")
assert csv_export.status_code == 200, f"CSV export failed: {csv_export.text}"
print(f"CSV export: {len(csv_export.content)} bytes")

# 5. Upload an unknown arbitrary extension file (.custom)
custom_data = "Server;Region;Ping_ms;Active\nAlpha;US-East;18.5;True\nBeta;EU-West;24.2;True\nGamma;AP-South;65.0;False\n"
custom_files = {
    "file": ("cluster_nodes.custom", custom_data.encode("utf-8"), "application/octet-stream")
}
custom_resp = requests.post(f"{BASE}/upload", files=custom_files)
assert custom_resp.status_code == 200, f"Custom file upload failed: {custom_resp.text}"
custom_data_res = custom_resp.json()
assert custom_data_res["status"] == "complete"
print("Custom arbitrary extension upload: SUCCESS (universal sniffer worked!)")

print("\nALL API ENDPOINTS TESTED AND VERIFIED SUCCESSFULLY!")
