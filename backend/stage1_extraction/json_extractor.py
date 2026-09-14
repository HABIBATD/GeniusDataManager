"""
Stage 1 — Universal JSON Extractor
====================================
Handles:
  - JSON arrays of objects: [{"colA": 1, "colB": 2}, ...]
  - JSON dictionaries of arrays (e.g. {"users": [...], "orders": [...]}) -> multiple RawTables
  - Single JSON objects: {"key1": "val1", ...} -> key-value or 1-row table
  - Nested objects flattened with dot-notation (e.g. "address.city")
  - JSONL / NDJSON (newline-delimited JSON)
  - GeoJSON FeatureCollections -> properties + geometry coordinates
"""

import json
import logging
from typing import Any

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)


def extract_json(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract structured data from JSON or JSONL files.
    Returns a Stage1Result with one or more RawTables.
    """
    warnings: list[str] = []
    unparsed: list[dict] = []
    tables: list[RawTable] = []

    # Decode text
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = file_bytes.decode("utf-8", errors="replace")
        warnings.append("Decoded JSON with replacement characters due to encoding issues.")

    text_stripped = text.strip()
    if not text_stripped:
        return Stage1Result(
            filename=filename,
            file_type="json",
            warnings=["Uploaded JSON file is empty."],
        )

    # Check for JSONL (multiple lines, each a JSON object)
    is_jsonl = filename.lower().endswith((".jsonl", ".ndjson"))
    if not is_jsonl and "\n" in text_stripped and not (text_stripped.startswith("[") or text_stripped.startswith("{")):
        is_jsonl = True

    parsed_obj: Any = None
    if is_jsonl:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        records = []
        for line_num, line in enumerate(lines, 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as err:
                unparsed.append({
                    "source": f"line {line_num}",
                    "reason": f"Invalid JSONL line: {err}",
                    "raw_text": line[:200],
                })
        parsed_obj = records
    else:
        try:
            parsed_obj = json.loads(text_stripped)
        except json.JSONDecodeError:
            # Fallback attempt: maybe JSONL without extension
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            records = []
            valid_count = 0
            for line_num, line in enumerate(lines, 1):
                try:
                    records.append(json.loads(line))
                    valid_count += 1
                except Exception:
                    pass
            if valid_count > 0:
                parsed_obj = records
                warnings.append("File parsed as JSONL (newline-delimited JSON).")
            else:
                return Stage1Result(
                    filename=filename,
                    file_type="json",
                    warnings=["Failed to parse file as valid JSON or JSONL."],
                    unparsed_rows=[{"source": filename, "reason": "Malformed JSON syntax", "raw_text": text[:300]}],
                )

    # Process parsed data into RawTables
    if isinstance(parsed_obj, list):
        # Array of objects / values
        table = _records_to_table(parsed_obj, table_index=0, sheet_name="Data", unparsed=unparsed)
        tables.append(table)
    elif isinstance(parsed_obj, dict):
        # Check GeoJSON
        if parsed_obj.get("type") == "FeatureCollection" and isinstance(parsed_obj.get("features"), list):
            records = []
            for f in parsed_obj["features"]:
                props = f.get("properties", {}) or {}
                if "geometry" in f and f["geometry"]:
                    props["_geometry_type"] = f["geometry"].get("type")
                    coords = f["geometry"].get("coordinates")
                    if coords:
                        props["_coordinates"] = str(coords)
                records.append(props)
            table = _records_to_table(records, table_index=0, sheet_name="GeoJSON Features", unparsed=unparsed)
            tables.append(table)
        else:
            # Check if dict contains multiple list collections (e.g. {"users": [...], "sales": [...]})
            list_keys = [k for k, v in parsed_obj.items() if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict)]
            if list_keys:
                table_idx = 0
                for k in list_keys:
                    sub_table = _records_to_table(parsed_obj[k], table_index=table_idx, sheet_name=str(k), unparsed=unparsed)
                    tables.append(sub_table)
                    table_idx += 1
                # Non-list metadata items as metadata table
                meta_keys = {k: v for k, v in parsed_obj.items() if k not in list_keys}
                if meta_keys:
                    meta_table = _records_to_table([meta_keys], table_index=table_idx, sheet_name="Metadata", unparsed=unparsed)
                    tables.append(meta_table)
            else:
                # Single root object or flat dictionary
                # Treat as 1-row table or key-value table
                flattened = _flatten_dict(parsed_obj)
                table = _records_to_table([flattened], table_index=0, sheet_name="Root", unparsed=unparsed)
                tables.append(table)
    else:
        # Primitive value (e.g. 123 or "abc")
        table = RawTable(
            table_index=0,
            source_sheet="Value",
            extraction_method=ExtractionMethod.JSON_FLATTEN,
            headers=["Value"],
            rows=[RawRow(row_index=0, raw_text=str(parsed_obj), cells=[RawCell(col_index=0, value=parsed_obj, raw_text=str(parsed_obj))])],
        )
        tables.append(table)

    return Stage1Result(
        filename=filename,
        file_type="json",
        total_pages=None,
        tables=tables,
        unparsed_rows=unparsed,
        warnings=warnings,
    )


def _flatten_dict(d: dict, prefix: str = "", max_depth: int = 4, depth: int = 0) -> dict:
    """Recursively flattens a nested dictionary using dot-notation."""
    items: dict = {}
    for k, v in d.items():
        new_key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and depth < max_depth:
            items.update(_flatten_dict(v, new_key, max_depth, depth + 1))
        elif isinstance(v, list):
            # Check if list of primitives
            if all(isinstance(x, (str, int, float, bool)) or x is None for x in v):
                items[new_key] = ", ".join(str(x) for x in v)
            else:
                items[new_key] = json.dumps(v, ensure_ascii=False)
        else:
            items[new_key] = v
    return items


def _records_to_table(records: list[Any], table_index: int, sheet_name: str, unparsed: list[dict]) -> RawTable:
    """Converts a list of dicts/records into a RawTable with consistent headers."""
    if not records:
        return RawTable(
            table_index=table_index,
            source_sheet=sheet_name,
            extraction_method=ExtractionMethod.JSON_FLATTEN,
            headers=["Empty"],
            rows=[],
        )

    # Flatten each record if dict
    flattened_records: list[dict] = []
    for i, r in enumerate(records):
        if isinstance(r, dict):
            flattened_records.append(_flatten_dict(r))
        elif isinstance(r, (list, tuple)):
            flattened_records.append({f"Col_{ci}": val for ci, val in enumerate(r)})
        else:
            flattened_records.append({"Value": r})

    # Collect union of all headers preserving order of appearance
    seen_headers: set[str] = set()
    headers: list[str] = []
    for r in flattened_records:
        for k in r.keys():
            clean_k = str(k).strip() or "Unnamed"
            if clean_k not in seen_headers:
                seen_headers.add(clean_k)
                headers.append(clean_k)

    if not headers:
        headers = ["Value"]

    # Build RawRows
    rows: list[RawRow] = []
    for row_idx, r in enumerate(flattened_records):
        cells: list[RawCell] = []
        raw_parts: list[str] = []
        for col_idx, h in enumerate(headers):
            val = r.get(h)
            raw_str = "" if val is None else str(val)
            raw_parts.append(raw_str)
            cells.append(RawCell(
                col_index=col_idx,
                value=val,
                raw_text=raw_str,
            ))
        rows.append(RawRow(
            row_index=row_idx,
            source_line=row_idx + 1,
            raw_text=" | ".join(raw_parts),
            cells=cells,
        ))

    return RawTable(
        table_index=table_index,
        source_sheet=sheet_name,
        extraction_method=ExtractionMethod.JSON_FLATTEN,
        headers=headers,
        rows=rows,
    )
