"""Schema slicing — extract a per-US subset of `workspace/output/db/schema.json`.

Levier 4 (audit 2026-06-08) : QA Phase 5 reads the full schema.json
(50-200 KB on real projects) for fixture setup. Most US touch 1-3 tables
out of 30-200. Slicing the schema to the entities referenced by an US
+ their FK transitive closure cuts the volatile/semi payload substantially
without losing correctness (FK contracts preserved).

Public API:
    extract_entity_names_from_us(us_text) -> set[str]
    extract_slice(schema, entity_names, include_referenced=True) -> dict
    slice_for_us(schema_path, us_path) -> tuple[dict, set[str]]

The CLI lives in `sdd_scripts.generate_schema_slice`.

Fallback semantics:
    Empty entity_names → returns the *full schema* (slice doesn't drop data
    silently). Callers that need an explicit "0 entities → skip slice file"
    behavior check the second tuple element (empty set) and act accordingly.
"""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any


_WORD_BOUNDARY_CHARS = re.compile(r"\w")


def extract_entity_names_from_us(us_text: str, candidate_names: set[str]) -> set[str]:
    """Find table names that appear in US text (case-insensitive, word boundary).

    Args:
        us_text: full US markdown
        candidate_names: set of table names from schema.json (the only valid hits)

    Returns:
        subset of candidate_names that appear at least once in us_text

    The match is case-insensitive and requires word boundaries so that
    `Bebe` matches `bebe` but not `BebeRdv` (which is a separate table
    that we'd want to match separately if it's named in the US).
    """
    if not us_text or not candidate_names:
        return set()
    lower_text = us_text.lower()
    hits: set[str] = set()
    for name in candidate_names:
        pattern = re.compile(rf"\b{re.escape(name.lower())}\b")
        if pattern.search(lower_text):
            hits.add(name)
    return hits


def _build_fk_graph(schema: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build forward + reverse FK adjacency from schema['tables'].

    Returns:
        (outgoing, incoming) — outgoing[T] = tables T points TO via FK;
        incoming[T] = tables that point TO T.
    """
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}
    tables = schema.get("tables", []) or []
    for tbl in tables:
        name = tbl.get("name")
        if not isinstance(name, str):
            continue
        outgoing.setdefault(name, set())
        incoming.setdefault(name, set())
    for tbl in tables:
        src = tbl.get("name")
        if not isinstance(src, str):
            continue
        for fk in tbl.get("foreign_keys", []) or []:
            ref = fk.get("ref_table")
            if isinstance(ref, str) and ref in outgoing:
                outgoing[src].add(ref)
                incoming[ref].add(src)
    return outgoing, incoming


def extract_slice(schema: dict[str, Any], entity_names: set[str],
                  include_referenced: bool = True) -> dict[str, Any]:
    """Return a slice of `schema` containing only the requested tables
    and (optionally) the tables they reference via FK (transitive).

    Args:
        schema: full schema dict (must have a 'tables' list)
        entity_names: table names to seed the slice
        include_referenced: also include tables reached via outgoing FK
                            (transitive). True by default — guarantees that
                            DTOs and fixtures see foreign-key contracts.

    Returns:
        New schema dict with the same top-level fields and a filtered
        `tables` list. Empty `entity_names` → returns the *full* schema
        unchanged (callers that need a "skip slice file" behavior check
        for emptiness before calling).
    """
    if not entity_names:
        return schema

    tables_by_name = {t["name"]: t for t in schema.get("tables", []) if "name" in t}
    if not entity_names & tables_by_name.keys():
        # No requested entity exists in the schema — fall back to full schema
        return schema

    keep: set[str] = set(entity_names) & tables_by_name.keys()
    if include_referenced:
        outgoing, _ = _build_fk_graph(schema)
        queue = deque(keep)
        while queue:
            current = queue.popleft()
            for target in outgoing.get(current, set()):
                if target not in keep:
                    keep.add(target)
                    queue.append(target)

    sliced_tables = [tables_by_name[n] for n in tables_by_name if n in keep]
    return {
        **{k: v for k, v in schema.items() if k != "tables"},
        "tables": sliced_tables,
        "_slice_metadata": {
            "seed_entities": sorted(entity_names & tables_by_name.keys()),
            "transitive_entities": sorted(keep - (entity_names & tables_by_name.keys())),
            "total_tables_in_slice": len(sliced_tables),
            "total_tables_in_source": len(tables_by_name),
        },
    }


def slice_for_us(schema_path: Path, us_path: Path,
                 include_referenced: bool = True
                 ) -> tuple[dict[str, Any], set[str]]:
    """Convenience: read schema + US from disk and return the slice.

    Returns:
        (sliced_schema, matched_entities). If matched_entities is empty,
        sliced_schema equals the full schema (no useful slice possible).

    Raises:
        FileNotFoundError: schema or US missing
        ValueError: schema.json malformed
    """
    if not schema_path.is_file():
        raise FileNotFoundError(f"schema.json not found: {schema_path}")
    if not us_path.is_file():
        raise FileNotFoundError(f"US not found: {us_path}")

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"schema.json is not valid JSON: {e}") from e

    if not isinstance(schema, dict) or "tables" not in schema:
        raise ValueError("schema.json missing 'tables' field")

    us_text = us_path.read_text(encoding="utf-8-sig")
    candidate_names = {t["name"] for t in schema["tables"] if "name" in t}
    matched = extract_entity_names_from_us(us_text, candidate_names)
    sliced = extract_slice(schema, matched, include_referenced=include_referenced)
    return sliced, matched
