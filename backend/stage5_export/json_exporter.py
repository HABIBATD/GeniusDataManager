"""
Stage 5 — JSON Exporter
=========================
Exports the complete pipeline result as clean, structured, and composable JSON.
Includes:
  - Global metadata & composition summary
  - Extracted tables with typed cell objects and column definitions
  - Profiling metrics, anomalies, and validation results
"""

import json
import logging
from typing import Any

from models.intermediate import PipelineResult

logger = logging.getLogger(__name__)


def export_json(result: PipelineResult) -> bytes:
    """
    Build and return a JSON file as bytes from the PipelineResult.
    """
    data: dict[str, Any] = {
        "task_id": result.task_id,
        "filename": result.filename,
        "status": result.status,
    }

    if result.stage2 and result.stage2.composition:
        data["composition"] = result.stage2.composition.model_dump()

    if result.stage1:
        tables_data = []
        for tbl in result.stage1.tables:
            # Build list of row dictionaries for easy consumer integration
            rows_as_dicts = []
            for r in tbl.rows:
                row_dict = {}
                for cell in r.cells:
                    if cell.col_index < len(tbl.headers):
                        h = tbl.headers[cell.col_index]
                        row_dict[h] = cell.value
                rows_as_dicts.append(row_dict)

            tables_data.append({
                "table_index": tbl.table_index,
                "sheet_name": tbl.source_sheet or f"Table {tbl.table_index + 1}",
                "source_page": tbl.source_page,
                "headers": tbl.headers,
                "row_count": len(tbl.rows),
                "records": rows_as_dicts,
            })
        data["tables"] = tables_data

    if result.stage2:
        profiles_data = []
        for tp in result.stage2.table_profiles:
            profiles_data.append({
                "table_index": tp.table_index,
                "grain_description": tp.grain_description,
                "columns": [cp.model_dump() for cp in tp.column_profiles],
                "anomalies": [a.model_dump() for a in tp.anomalies],
                "mismatches": [m.model_dump() for m in tp.computed_column_mismatches],
            })
        data["profiles"] = profiles_data

    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return json_str.encode("utf-8")
