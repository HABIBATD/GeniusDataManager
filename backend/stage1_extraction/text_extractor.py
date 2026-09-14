"""
Stage 1 — Universal Text & Delimited Extractor
================================================
Handles:
  - Tab-separated (TSV), Pipe-separated (|), Semicolon-separated (;)
  - Markdown tables (| Col 1 | Col 2 |)
  - Key-Value configurations (key = value or key: value)
  - Server logs (timestamps, log levels, logger, message)
  - Unstructured plain text (line/paragraph records with metrics)
"""

import csv
import io
import logging
import re
from typing import Any, Optional

import chardet

from models.intermediate import (
    ExtractionMethod,
    RawCell,
    RawRow,
    RawTable,
    Stage1Result,
)

logger = logging.getLogger(__name__)

# Regex for common server log formats (e.g. 2026-09-14 12:00:00 [INFO] module: message)
_LOG_LINE_REGEX = re.compile(
    r"""^
    (?P<timestamp>\d{4}[-/]\d{2}[-/]\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?
    \s*
    (?:\[?(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\]?)?
    \s*
    (?:\[?(?P<logger>[\w\.\-]+)\]?:?)?
    \s*
    (?P<message>.*)
    $""",
    re.IGNORECASE | re.VERBOSE,
)


def extract_text(file_bytes: bytes, filename: str) -> Stage1Result:
    """
    Extract structured data from text, log, TSV, markdown, or config files.
    """
    warnings: list[str] = []
    unparsed: list[dict] = []

    # Detect encoding
    detected = chardet.detect(file_bytes)
    encoding = detected.get("encoding") or "utf-8"
    try:
        text = file_bytes.decode(encoding, errors="replace")
    except Exception:
        text = file_bytes.decode("utf-8", errors="replace")
        warnings.append("Decoded using UTF-8 fallback with replacement characters.")

    lines = [line for line in text.splitlines()]
    non_empty_lines = [l for l in lines if l.strip()]

    if not non_empty_lines:
        return Stage1Result(
            filename=filename,
            file_type="text",
            warnings=["File contains no text."],
        )

    # 1. Check for Markdown table
    md_table = _try_parse_markdown_table(non_empty_lines, filename)
    if md_table:
        return Stage1Result(
            filename=filename,
            file_type="text",
            tables=[md_table],
            warnings=warnings,
        )

    # 2. Check for standard delimited data (TSV, Pipe, Semicolon, Comma)
    delim_table = _try_parse_delimited(non_empty_lines, filename)
    if delim_table:
        return Stage1Result(
            filename=filename,
            file_type="text",
            tables=[delim_table],
            warnings=warnings,
        )

    # 3. Check for Server Log patterns
    log_table = _try_parse_log_file(non_empty_lines, filename)
    if log_table:
        return Stage1Result(
            filename=filename,
            file_type="text",
            tables=[log_table],
            warnings=warnings,
        )

    # 4. Check for Key-Value / INI / Conf format
    kv_table = _try_parse_key_value(non_empty_lines, filename)
    if kv_table:
        return Stage1Result(
            filename=filename,
            file_type="text",
            tables=[kv_table],
            warnings=warnings,
        )

    # 5. Fallback: Unstructured Text Line Analyzer
    unstructured_table = _parse_unstructured_text(lines, filename)
    return Stage1Result(
        filename=filename,
        file_type="text",
        tables=[unstructured_table],
        warnings=warnings + ["Processed unstructured text by parsing line records and text metrics."],
    )


def _try_parse_markdown_table(lines: list[str], filename: str) -> Optional[RawTable]:
    """Detects and parses Markdown-style tables (| Col 1 | Col 2 |)."""
    table_lines: list[list[str]] = []
    has_separator = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            parts = [c.strip() for c in stripped[1:-1].split("|")]
            # Check if separator line (e.g. |---|---|)
            if all(re.match(r"^:?-+:?$", p) for p in parts if p):
                has_separator = True
                continue
            table_lines.append(parts)

    if has_separator and len(table_lines) >= 2:
        headers = [h if h else f"Col_{i}" for i, h in enumerate(table_lines[0])]
        num_cols = len(headers)
        rows: list[RawRow] = []

        for row_idx, r in enumerate(table_lines[1:]):
            padded = (r + [""] * num_cols)[:num_cols]
            cells = [
                RawCell(col_index=ci, value=_coerce_val(val), raw_text=val)
                for ci, val in enumerate(padded)
            ]
            rows.append(RawRow(
                row_index=row_idx,
                source_line=row_idx + 2,
                raw_text=" | ".join(padded),
                cells=cells,
            ))

        return RawTable(
            table_index=0,
            source_sheet="Markdown Table",
            extraction_method=ExtractionMethod.TEXT_MARKDOWN,
            headers=headers,
            rows=rows,
        )
    return None


def _try_parse_delimited(lines: list[str], filename: str) -> Optional[RawTable]:
    """Sniffs and parses delimited files (TSV, pipe, semicolon, comma)."""
    sample_text = "\n".join(lines[:50])
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters="\t|;,")
        delimiter = dialect.delimiter
    except Exception:
        # Check tab specifically
        tab_counts = [l.count("\t") for l in lines[:10]]
        pipe_counts = [l.count("|") for l in lines[:10]]
        if max(tab_counts) >= 1 and min(tab_counts) == max(tab_counts):
            delimiter = "\t"
        elif max(pipe_counts) >= 1 and min(pipe_counts) == max(pipe_counts):
            delimiter = "|"
        else:
            return None

    reader = csv.reader(lines, delimiter=delimiter)
    all_rows = list(reader)
    if not all_rows or len(all_rows[0]) <= 1:
        return None

    # Check consistency: at least 70% of rows must have similar number of columns
    col_counts = [len(r) for r in all_rows]
    most_common_cols = max(set(col_counts), key=col_counts.count)
    if most_common_cols <= 1 or (col_counts.count(most_common_cols) / len(col_counts)) < 0.6:
        return None

    # First row is header
    header_raw = all_rows[0]
    headers = [h.strip() if h.strip() else f"Col_{i}" for i, h in enumerate(header_raw)]
    num_cols = len(headers)

    rows: list[RawRow] = []
    for row_idx, r in enumerate(all_rows[1:]):
        if not any(cell.strip() for cell in r):
            continue
        padded = (r + [""] * num_cols)[:num_cols]
        cells = [
            RawCell(col_index=ci, value=_coerce_val(val.strip()), raw_text=val.strip())
            for ci, val in enumerate(padded)
        ]
        rows.append(RawRow(
            row_index=len(rows),
            source_line=row_idx + 2,
            raw_text=delimiter.join(padded),
            cells=cells,
        ))

    return RawTable(
        table_index=0,
        source_sheet="Delimited Data",
        extraction_method=ExtractionMethod.TEXT_DELIMITED,
        headers=headers,
        rows=rows,
    )


def _try_parse_log_file(lines: list[str], filename: str) -> Optional[RawTable]:
    """Detects server logs and parses into Timestamp, Level, Logger, and Message columns."""
    matches = 0
    parsed_records = []

    for idx, line in enumerate(lines[:100]):
        stripped = line.strip()
        m = _LOG_LINE_REGEX.match(stripped)
        if m and (m.group("timestamp") or m.group("level")):
            matches += 1

    # Check if lines match log pattern
    is_log_file = filename.lower().endswith(".log")
    min_matches = 1 if is_log_file else 2
    if matches >= min_matches and (matches / max(1, min(len(lines), 100))) >= 0.30:
        headers = ["Timestamp", "Level", "Module", "Message"]
        rows: list[RawRow] = []

        for row_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            m = _LOG_LINE_REGEX.match(stripped)
            if m and (m.group("timestamp") or m.group("level")):
                ts = m.group("timestamp") or ""
                lvl = (m.group("level") or "INFO").upper()
                mod = m.group("logger") or ""
                msg = m.group("message") or ""
            else:
                ts, lvl, mod, msg = "", "INFO", "", stripped

            cells = [
                RawCell(col_index=0, value=ts or None, raw_text=ts),
                RawCell(col_index=1, value=lvl, raw_text=lvl),
                RawCell(col_index=2, value=mod or None, raw_text=mod),
                RawCell(col_index=3, value=msg, raw_text=msg),
            ]
            rows.append(RawRow(
                row_index=len(rows),
                source_line=row_idx + 1,
                raw_text=stripped,
                cells=cells,
            ))

        return RawTable(
            table_index=0,
            source_sheet="Server Logs",
            extraction_method=ExtractionMethod.TEXT_LOG,
            headers=headers,
            rows=rows,
        )
    return None


def _try_parse_key_value(lines: list[str], filename: str) -> Optional[RawTable]:
    """Detects key-value configurations (e.g. key=val, key: val)."""
    kv_pairs: list[tuple[str, str, int]] = []
    kv_pattern = re.compile(r"^([\w\.\-]+)\s*[:=]\s*(.*)$")

    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", ";", "--")):
            continue
        m = kv_pattern.match(stripped)
        if m:
            kv_pairs.append((m.group(1).strip(), m.group(2).strip(), line_idx + 1))

    if len(kv_pairs) >= 3 and len(kv_pairs) >= (len(lines) * 0.3):
        headers = ["Key", "Value"]
        rows: list[RawRow] = []
        for idx, (k, v, orig_line) in enumerate(kv_pairs):
            cells = [
                RawCell(col_index=0, value=k, raw_text=k),
                RawCell(col_index=1, value=_coerce_val(v), raw_text=v),
            ]
            rows.append(RawRow(
                row_index=idx,
                source_line=orig_line,
                raw_text=f"{k} = {v}",
                cells=cells,
            ))

        return RawTable(
            table_index=0,
            source_sheet="Key-Value Config",
            extraction_method=ExtractionMethod.TEXT_KEY_VALUE,
            headers=headers,
            rows=rows,
        )
    return None


def _parse_unstructured_text(lines: list[str], filename: str) -> RawTable:
    """Parses arbitrary text into structured rows with analytical metrics."""
    headers = ["Line_Number", "Content", "Word_Count", "Char_Count"]
    rows: list[RawRow] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        words = len(stripped.split())
        chars = len(stripped)
        cells = [
            RawCell(col_index=0, value=idx + 1, raw_text=str(idx + 1)),
            RawCell(col_index=1, value=stripped, raw_text=stripped),
            RawCell(col_index=2, value=words, raw_text=str(words)),
            RawCell(col_index=3, value=chars, raw_text=str(chars)),
        ]
        rows.append(RawRow(
            row_index=len(rows),
            source_line=idx + 1,
            raw_text=stripped,
            cells=cells,
        ))

    return RawTable(
        table_index=0,
        source_sheet="Text Content",
        extraction_method=ExtractionMethod.TEXT_UNSTRUCTURED,
        headers=headers,
        rows=rows,
    )


def _coerce_val(text: str) -> Any:
    """Converts numeric/boolean strings to numbers/booleans where applicable."""
    if text == "":
        return None
    lower = text.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    cleaned = re.sub(r"[,$£€₹\s]", "", text).replace("(", "-").replace(")", "")
    try:
        f = float(cleaned)
        return int(f) if f == int(f) else f
    except ValueError:
        return text
