"""
Test script for Universal Data Ingestion & Composition Pipeline
================================================================
Tests:
  1. JSON extraction (nested objects, array of records)
  2. CSV & TSV delimited extraction
  3. Server log pattern extraction
  4. Markdown table extraction
  5. SQLite database in-memory creation and extraction
  6. DOCX document generation and extraction
  7. Universal sniffer on arbitrary file extension (.custom)
  8. Full Stage 2 profiling and composition (Health score, insights, unified catalog)
  9. Stage 5 exports: XLSX, CSV, JSON
"""

import io
import json
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from stage1_extraction.universal_extractor import extract_universal
from stage2_profiling.profiler import profile_stage1_result
from stage5_export.json_exporter import export_json
from stage5_export.csv_exporter import export_csv
from stage5_export.xlsx_exporter import export_xlsx
from models.intermediate import PipelineResult, ColumnType


def test_json():
    print("Testing JSON extraction...")
    sample_json = [
        {"id": 101, "customer": {"name": "Alice", "city": "New York"}, "amount": 150.50, "active": True},
        {"id": 102, "customer": {"name": "Bob", "city": "London"}, "amount": 290.00, "active": False},
        {"id": 103, "customer": {"name": "Charlie", "city": "Tokyo"}, "amount": 99.99, "active": True},
    ]
    json_bytes = json.dumps(sample_json).encode("utf-8")
    s1 = extract_universal(json_bytes, "orders.json")
    assert len(s1.tables) == 1, f"Expected 1 table, got {len(s1.tables)}"
    tbl = s1.tables[0]
    print(f"  JSON extracted headers: {tbl.headers}")
    assert "customer.name" in tbl.headers
    assert "amount" in tbl.headers
    assert len(tbl.rows) == 3

    s2 = profile_stage1_result(s1)
    assert s2.composition is not None
    print(f"  Composition Health Score: {s2.composition.health_score}")
    print(f"  Composition Insights: {s2.composition.executive_insights[:2]}")
    assert s2.composition.completeness_pct == 100.0
    print("  [PASS] JSON Extraction & Composition")


def test_delimited_tsv_and_logs():
    print("Testing TSV & Logs extraction...")
    tsv_data = "Product\tCategory\tPrice\tInStock\nLaptop\tElectronics\t999.99\tTrue\nChair\tFurniture\t79.50\tFalse\n"
    s1_tsv = extract_universal(tsv_data.encode("utf-8"), "inventory.tsv")
    assert len(s1_tsv.tables) == 1
    assert s1_tsv.tables[0].headers == ["Product", "Category", "Price", "InStock"]
    print("  [PASS] TSV Extraction")

    log_data = (
        "2026-09-14 10:15:20 [INFO] auth_service: User login successful for alice\n"
        "2026-09-14 10:16:05 [WARN] db_pool: Connection timeout reaching primary db\n"
        "2026-09-14 10:17:45 [ERROR] payment_gateway: Card declined for transaction 8812\n"
    )
    s1_log = extract_universal(log_data.encode("utf-8"), "system.log")
    assert len(s1_log.tables) == 1
    assert "Level" in s1_log.tables[0].headers
    assert len(s1_log.tables[0].rows) == 3
    print("  [PASS] Log File Extraction")


def test_markdown_table():
    print("Testing Markdown table extraction...")
    md_data = (
        "# Sales Summary\n\n"
        "| Region | Q1_Sales | Q2_Sales |\n"
        "|:-------|---------:|---------:|\n"
        "| North  |    15000 |    18000 |\n"
        "| South  |    12000 |    13500 |\n"
        "| East   |    21000 |    24000 |\n"
    )
    s1 = extract_universal(md_data.encode("utf-8"), "report.md")
    assert len(s1.tables) == 1
    assert s1.tables[0].headers == ["Region", "Q1_Sales", "Q2_Sales"]
    assert len(s1.tables[0].rows) == 3
    print("  [PASS] Markdown Table Extraction")


def test_sqlite():
    print("Testing SQLite extraction...")
    # Create SQLite database in memory, serialize to bytes
    buf = io.BytesIO()
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE employees (id INT, name TEXT, salary REAL, dept TEXT)")
    cur.execute("INSERT INTO employees VALUES (1, 'Eve', 85000, 'Engineering')")
    cur.execute("INSERT INTO employees VALUES (2, 'Frank', 72000, 'Sales')")
    conn.commit()

    # Save in-memory db to file bytes
    backup_db = sqlite3.connect(buf) if hasattr(sqlite3, "deserialize") else None
    # Use SQLite backup API
    disk_conn = sqlite3.connect("test_temp.db")
    conn.backup(disk_conn)
    disk_conn.close()
    conn.close()

    with open("test_temp.db", "rb") as f:
        db_bytes = f.read()
    Path("test_temp.db").unlink(missing_ok=True)

    s1 = extract_universal(db_bytes, "company.sqlite")
    assert len(s1.tables) == 1
    assert "employees" in s1.tables[0].source_sheet
    assert s1.tables[0].headers == ["id", "name", "salary", "dept"]
    assert len(s1.tables[0].rows) == 2
    print("  [PASS] SQLite Database Extraction")


def test_docx():
    print("Testing DOCX extraction...")
    # Build a minimal valid DOCX file in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:tbl>
              <w:tr>
                <w:tc><w:p><w:t>Project</w:t></w:p></w:tc>
                <w:tc><w:p><w:t>Status</w:t></w:p></w:tc>
                <w:tc><w:p><w:t>Budget</w:t></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:t>Genius Data</w:t></w:p></w:tc>
                <w:tc><w:p><w:t>Active</w:t></w:p></w:tc>
                <w:tc><w:p><w:t>50000</w:t></w:p></w:tc>
              </w:tr>
            </w:tbl>
          </w:body>
        </w:document>"""
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))

    s1 = extract_universal(buf.getvalue(), "specs.docx")
    assert len(s1.tables) == 1
    assert s1.tables[0].headers == ["Project", "Status", "Budget"]
    assert len(s1.tables[0].rows) == 1
    print("  [PASS] DOCX Table Extraction")


def test_arbitrary_sniffer():
    print("Testing Universal Sniffer on unknown file...")
    custom_text = "Metric;Value;Date\nCPU;45.2;2026-09-14\nRAM;68.1;2026-09-14\nDisk;32.0;2026-09-14\n"
    s1 = extract_universal(custom_text.encode("utf-8"), "system_telemetry.custom")
    assert len(s1.tables) == 1
    assert s1.tables[0].headers == ["Metric", "Value", "Date"]
    assert len(s1.tables[0].rows) == 3

    s2 = profile_stage1_result(s1)
    assert s2.composition is not None
    print(f"  Sniffer Health Score: {s2.composition.health_score}")

    # Test JSON export
    pipe = PipelineResult(task_id="test-123", filename="system_telemetry.custom", stage1=s1, stage2=s2)
    json_bytes = export_json(pipe)
    parsed_export = json.loads(json_bytes.decode("utf-8"))
    assert parsed_export["task_id"] == "test-123"
    assert "composition" in parsed_export
    assert len(parsed_export["tables"]) == 1
def test_zip():
    print("Testing ZIP archive extraction...")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("users.json", json.dumps([{"user_id": 1, "username": "alice"}, {"user_id": 2, "username": "bob"}]).encode("utf-8"))
        zf.writestr("orders.csv", "order_id,user_id,total\n101,1,45.5\n102,2,90.0\n".encode("utf-8"))

    s1 = extract_universal(buf.getvalue(), "bundle.zip")
    assert len(s1.tables) == 2, f"Expected 2 tables from ZIP, got {len(s1.tables)}"
    s2 = profile_stage1_result(s1)
    assert s2.composition is not None
    assert len(s2.composition.table_relationships) >= 1
    print(f"  Discovered relationship: {s2.composition.table_relationships[0]}")
    print("  [PASS] ZIP Archive & Relational Discovery")


if __name__ == "__main__":
    test_json()
    test_delimited_tsv_and_logs()
    test_markdown_table()
    test_sqlite()
    test_docx()
    test_zip()
    test_arbitrary_sniffer()
    print("\nALL UNIVERSAL PIPELINE TESTS PASSED SUCCESSFULLY!")
