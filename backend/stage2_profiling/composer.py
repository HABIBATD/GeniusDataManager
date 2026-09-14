"""
Stage 2 — Genius Data Composition Engine
==========================================
Analyzes the extracted tables as a cohesive data model:
  - Calculates Data Quality & Health Score (0–100)
  - Evaluates Completeness Percentage across all cells
  - Detects Cross-Table Relationships & Foreign Key candidates
  - Determines if tables can be consolidated / unioned
  - Produces a Unified Column Catalog & Executive Insights
"""

import logging
from typing import Any

from models.intermediate import (
    ColumnType,
    CompositionSummary,
    RawTable,
    Stage1Result,
    TableProfile,
)

logger = logging.getLogger(__name__)


def compose_dataset(s1: Stage1Result, table_profiles: list[TableProfile]) -> CompositionSummary:
    """
    Synthesize all table profiles into a comprehensive dataset composition.
    """
    total_cells = 0
    null_cells = 0
    total_records = 0
    total_anomalies = 0
    total_mismatches = 0
    unparsed_count = len(s1.unparsed_rows)

    all_cols: dict[str, dict[str, Any]] = {}
    table_headers_map: dict[int, set[str]] = {}

    for tp in table_profiles:
        raw_table = s1.tables[tp.table_index] if tp.table_index < len(s1.tables) else None
        num_rows = len(raw_table.rows) if raw_table else tp.total_rows
        total_records += num_rows
        total_anomalies += len(tp.anomalies)
        total_mismatches += len(tp.computed_column_mismatches)

        headers_set: set[str] = set()
        for cp in tp.column_profiles:
            clean_header = cp.header.strip()
            headers_set.add(clean_header.lower())

            col_total = num_rows
            col_nulls = cp.null_count
            total_cells += col_total
            null_cells += col_nulls

            if clean_header not in all_cols:
                all_cols[clean_header] = {
                    "header": clean_header,
                    "inferred_type": cp.inferred_type.value,
                    "confidence": cp.type_confidence,
                    "sample_values": cp.sample_values,
                    "unique_count": cp.unique_count,
                    "null_count": col_nulls,
                    "total_count": col_total,
                    "tables": [tp.source_sheet or f"Table {tp.table_index + 1}"],
                }
            else:
                all_cols[clean_header]["total_count"] += col_total
                all_cols[clean_header]["null_count"] += col_nulls
                all_cols[clean_header]["tables"].append(tp.source_sheet or f"Table {tp.table_index + 1}")
                if cp.sample_values and not all_cols[clean_header]["sample_values"]:
                    all_cols[clean_header]["sample_values"] = cp.sample_values

        table_headers_map[tp.table_index] = headers_set

    # 1. Completeness percentage
    if total_cells > 0:
        completeness_pct = round(((total_cells - null_cells) / total_cells) * 100.0, 1)
    else:
        completeness_pct = 100.0

    # 2. Data Health Score (0 - 100)
    health = 100.0
    # Penalty for nulls
    null_ratio = (null_cells / total_cells) if total_cells > 0 else 0.0
    health -= null_ratio * 25.0
    # Penalty for anomalies
    health -= min(25.0, total_anomalies * 2.5)
    # Penalty for mismatches
    health -= min(25.0, total_mismatches * 4.0)
    # Penalty for unparsed rows
    health -= min(15.0, unparsed_count * 2.0)
    health_score = round(max(0.0, min(100.0, health)), 1)

    # 3. Detect Cross-Table Relationships & Union capability
    can_unify = False
    relationships: list[dict] = []

    if len(table_profiles) > 1:
        # Check union: do all tables share at least 70% columns?
        t0_headers = table_headers_map.get(0, set())
        if t0_headers:
            union_possible = True
            for tidx in range(1, len(table_profiles)):
                th = table_headers_map.get(tidx, set())
                intersection = t0_headers.intersection(th)
                overlap_ratio = len(intersection) / max(1, len(t0_headers))
                if overlap_ratio < 0.7:
                    union_possible = False
                    break
            can_unify = union_possible

        # Identify candidate foreign keys
        key_patterns = {"id", "key", "code", "uuid", "num", "no", "sku", "email", "account"}
        for i in range(len(table_profiles)):
            for j in range(i + 1, len(table_profiles)):
                common = table_headers_map.get(i, set()).intersection(table_headers_map.get(j, set()))
                for c in common:
                    if any(kp in c for kp in key_patterns) or len(common) <= 3:
                        t1_name = table_profiles[i].source_sheet or f"Table {i + 1}"
                        t2_name = table_profiles[j].source_sheet or f"Table {j + 1}"
                        relationships.append({
                            "table_a": t1_name,
                            "table_b": t2_name,
                            "matching_column": c,
                            "type": "shared_key",
                        })

    # 4. Generate Executive Insights
    insights: list[str] = []
    insights.append(
        f"Extracted {len(table_profiles)} table(s) encompassing {total_records:,} total records "
        f"and {len(all_cols)} unique features."
    )

    if health_score >= 90:
        insights.append(f"High data integrity ({health_score}/100 Health Score) with {completeness_pct}% cell completeness.")
    elif health_score >= 70:
        insights.append(f"Moderate data integrity ({health_score}/100 Health Score). {completeness_pct}% complete.")
    else:
        insights.append(f"Data quality alert ({health_score}/100 Health Score): detected anomalies or null distributions.")

    # Find dominant types
    numeric_count = sum(1 for c in all_cols.values() if c["inferred_type"] in ("numeric", "currency", "percentage"))
    cat_count = sum(1 for c in all_cols.values() if c["inferred_type"] in ("category", "identifier"))
    date_count = sum(1 for c in all_cols.values() if c["inferred_type"] in ("date", "time_period"))

    insights.append(
        f"Schema distribution: {numeric_count} quantitative metrics, {cat_count} categorical/identity fields, "
        f"and {date_count} temporal dimension(s)."
    )

    if total_anomalies > 0:
        insights.append(f"Detected {total_anomalies} data anomalies requiring review.")
    else:
        insights.append("Zero value anomalies detected across all rows.")

    if can_unify:
        insights.append("Extracted tables share identical or overlapping schemas and can be unified into a consolidated master view.")

    if relationships:
        insights.append(f"Identified {len(relationships)} potential relational join key(s) connecting tables.")

    # Unified columns list sorted by frequency
    unified_columns_list = list(all_cols.values())
    unified_columns_list.sort(key=lambda x: x["total_count"], reverse=True)

    return CompositionSummary(
        health_score=health_score,
        completeness_pct=completeness_pct,
        total_records=total_records,
        total_features=len(all_cols),
        executive_insights=insights,
        unified_columns=unified_columns_list,
        can_unify=can_unify,
        table_relationships=relationships[:10],
    )
