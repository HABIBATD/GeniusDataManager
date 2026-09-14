"""
Stage 1 — SQLite Database Extractor
=====================================
Extracts:
  - All tables and views from SQLite databases (.db, .sqlite, .sqlite3).
  - Column names and types via PRAGMA table_info.
  - Rows with type preservation.
Uses Python's built-in sqlite3 — zero external dependencies.
"""

import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_sqlite(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract all tables and views from an SQLite database file.
    """
    warnings: list[str] = []
    tables: list[RawTable] = []

    # Write temporarily to load with sqlite3
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Find all user tables and views
        cursor.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        entities = cursor.fetchall()

        if not entities:
            return Stage1Result(
                filename=filename,
                file_type="sqlite",
                warnings=["No user tables or views found in SQLite database."],
            )

        table_index = 0
        for ent in entities:
            tname = ent["name"]
            ttype = ent["type"]

            try:
                # Column info
                cursor.execute(f"PRAGMA table_info(`{tname}`)")
                col_info = cursor.fetchall()
                headers = [col["name"] for col in col_info] if col_info else []

                # Data rows
                cursor.execute(f"SELECT * FROM `{tname}` LIMIT 10000")
                db_rows = cursor.fetchall()

                if not headers and db_rows:
                    headers = list(db_rows[0].keys())

                if not headers:
                    headers = ["No_Columns"]

                raw_rows: list[RawRow] = []
                for ri, row in enumerate(db_rows):
                    cells: list[RawCell] = []
                    raw_vals: list[str] = []
                    for ci, h in enumerate(headers):
                        val = row[h] if h in row.keys() else None
                        raw_str = "" if val is None else str(val)
                        raw_vals.append(raw_str)
                        cells.append(RawCell(
                            col_index=ci,
                            value=val,
                            raw_text=raw_str,
                        ))
                    raw_rows.append(RawRow(
                        row_index=ri,
                        source_line=ri + 1,
                        raw_text=" | ".join(raw_vals),
                        cells=cells,
                    ))

                tables.append(RawTable(
                    table_index=table_index,
                    source_sheet=f"{tname} ({ttype})",
                    extraction_method=ExtractionMethod.SQLITE_TABLE,
                    headers=headers,
                    rows=raw_rows,
                ))
                table_index += 1
            except Exception as row_exc:
                warnings.append(f"Failed extracting table '{tname}': {row_exc}")

        conn.close()
    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="sqlite",
            warnings=[f"SQLite database error: {exc}"],
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return Stage1Result(
        filename=filename,
        file_type="sqlite",
        tables=tables,
        warnings=warnings,
    )
