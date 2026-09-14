"""
Stage 1 — Archive (.zip) Extractor
====================================
Recursively unpacks ZIP archives in memory, identifies contained data files,
extracts all tables from each file, and composes them into a unified Stage1Result.
"""

import io
import logging
import zipfile
from pathlib import Path

from models.intermediate import (
    ExtractionMethod,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_archive(file_bytes: bytes, filename: str, universal_extractor_func) -> Stage1Result:
    """
    Unpack ZIP archive and run universal extraction on all contained data files.
    """
    warnings: list[str] = []
    unparsed: list[dict] = []
    all_tables: list[RawTable] = []

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            namelist = [n for n in zf.namelist() if not n.startswith("__MACOSX") and not n.endswith("/")]
            if not namelist:
                return Stage1Result(
                    filename=filename,
                    file_type="zip",
                    warnings=["Archive is empty."],
                )

            table_counter = 0
            for inner_name in namelist:
                inner_path = Path(inner_name)
                # Skip hidden files
                if inner_path.name.startswith("."):
                    continue

                try:
                    inner_bytes = zf.read(inner_name)
                    if not inner_bytes:
                        continue

                    # Extract sub-result using universal extractor
                    sub_result = universal_extractor_func(inner_bytes, inner_path.name)
                    warnings.extend([f"[{inner_path.name}] {w}" for w in sub_result.warnings])
                    unparsed.extend(sub_result.unparsed_rows)

                    for tbl in sub_result.tables:
                        # Prepend inner filename to source sheet
                        orig_sheet = tbl.source_sheet or f"Table {tbl.table_index + 1}"
                        combined_sheet = f"{inner_path.name} - {orig_sheet}"
                        tbl.source_sheet = combined_sheet[:60]
                        tbl.table_index = table_counter
                        all_tables.append(tbl)
                        table_counter += 1

                except Exception as exc:
                    warnings.append(f"Failed extracting '{inner_name}': {exc}")

    except Exception as exc:
        return Stage1Result(
            filename=filename,
            file_type="zip",
            warnings=[f"Failed to open ZIP archive: {exc}"],
        )

    if not all_tables:
        warnings.append("No tabular or structured data files found inside ZIP archive.")

    return Stage1Result(
        filename=filename,
        file_type="zip",
        tables=all_tables,
        unparsed_rows=unparsed,
        warnings=warnings,
    )
