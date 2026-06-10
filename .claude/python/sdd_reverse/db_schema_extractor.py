r"""db_schema_extractor.py — Extract basic DB schema from legacy (D7).

Per design doc §4.2 + §5.2 — produces db-schema.json with `completeness: "basic"`.

Supported sources (best-effort regex):
    - SQL DDL files (.sql) — CREATE TABLE / ALTER TABLE
    - EF Code-First (C# DbSet<T> + class definitions)
    - Hibernate/JPA annotations (Java @Entity)
    - Doctrine annotations (PHP @ORM\Entity)
    - Manual ADO.NET / JDBC parameter usage

Public API:
    extract_db_schema(project_root, scan_result) -> dict

If no schema source is found → returns minimal `{entities: []}` and the
agent reverse-functional-extractor will degrade entities to `confidence: medium`
(per §9.2 design doc).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import ScanResult, normalize_bytes

DB_SCHEMA_VERSION = 1


# === SQL DDL parsing ===

# Match `CREATE TABLE name (` — body extracted via balanced-paren scan (see _find_table_body).
_RE_CREATE_TABLE_HEADER = re.compile(
    r"CREATE\s+TABLE\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?\s*\(",
    re.IGNORECASE,
)

# Column line: name TYPE[(args)] [NOT NULL|NULL] [IDENTITY(...)] [PRIMARY KEY] [DEFAULT ...]
_RE_COLUMN = re.compile(
    r"^\s*\[?(\w+)\]?\s+"                                       # 1: name
    r"([A-Za-z][A-Za-z0-9]*(?:\s*\([^)]+\))?)"                  # 2: type (possibly with parens like NVARCHAR(50))
    r"(.*)$",                                                    # 3: trailing modifiers
    re.IGNORECASE,
)
_RE_FK = re.compile(
    r"(?:CONSTRAINT\s+\[?(\w+)\]?\s+)?FOREIGN\s+KEY\s*\(\[?(\w+)\]?\)\s+REFERENCES\s+\[?(\w+)\]?\s*\(\[?(\w+)\]?\)",
    re.IGNORECASE,
)


def _find_table_body(content: str, open_paren_idx: int) -> tuple[str, int] | None:
    """Find the body between balanced parens starting at `open_paren_idx`.

    Returns (body_string, end_idx) or None if unmatched.
    """
    depth = 0
    i = open_paren_idx
    n = len(content)
    while i < n:
        c = content[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return content[open_paren_idx + 1: i], i
        i += 1
    return None

# === EF / JPA / Doctrine entity detection ===

_RE_EF_DBSET = re.compile(r"DbSet<(\w+)>\s+\w+\s*[{;]", re.IGNORECASE)
_RE_EF_CLASS = re.compile(r"public\s+(?:partial\s+)?class\s+(\w+)\s*[:{]")
_RE_JPA_ENTITY = re.compile(r"@Entity\b[\s\S]{0,200}?public\s+class\s+(\w+)")
_RE_DOCTRINE_ENTITY = re.compile(r"@ORM\\Entity\b[\s\S]{0,500}?class\s+(\w+)")


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return normalize_bytes(raw).decode("utf-8", errors="replace")


def _split_top_level_commas(body: str) -> list[str]:
    """Split `body` on commas at paren-depth 0 (top-level only)."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for c in body:
        if c == "(":
            depth += 1
            buf.append(c)
        elif c == ")":
            depth -= 1
            buf.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_sql_ddl(content: str, source_file: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (entities, relations)."""
    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    for m in _RE_CREATE_TABLE_HEADER.finditer(content):
        table_name = m.group(1)
        # m.end() points just after the opening "("
        open_idx = m.end() - 1
        result = _find_table_body(content, open_idx)
        if result is None:
            continue
        body, close_idx = result

        start_line = content[: m.start()].count("\n") + 1
        end_line = content[: close_idx].count("\n") + 1
        evidence = f"{source_file}:{start_line}-{end_line}"

        fields: list[dict[str, Any]] = []
        for raw_col in _split_top_level_commas(body):
            col_text = raw_col.strip()
            upper = col_text.upper()
            if not col_text:
                continue
            if upper.startswith(("CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY", "INDEX", "UNIQUE")):
                continue
            cm = _RE_COLUMN.match(col_text)
            if not cm:
                continue
            field_name = cm.group(1)
            field_type = (cm.group(2) or "").strip()
            modifiers = (cm.group(3) or "").upper()
            is_pk = "PRIMARY KEY" in modifiers
            identity = "IDENTITY" in modifiers
            is_not_null = "NOT NULL" in modifiers or is_pk
            # Extract DEFAULT clause if any
            default: str | None = None
            dm = re.search(r"DEFAULT\s+([^\s,]+(?:\([^)]*\))?)", modifiers, re.IGNORECASE)
            if dm:
                default = dm.group(1).strip()
            fields.append({
                "name": field_name,
                "type": field_type,
                "primaryKey": is_pk,
                "identity": identity,
                "nullable": not is_not_null,
                "default": default,
            })

        # Foreign keys in body
        for fk in _RE_FK.finditer(body):
            from_field = fk.group(2)
            to_table = fk.group(3)
            to_field = fk.group(4)
            relations.append({
                "name": fk.group(1) or f"FK_{table_name}_{from_field}",
                "from": {"entity": table_name, "field": from_field},
                "to": {"entity": to_table, "field": to_field},
                "type": "many-to-one",
                "evidence": evidence,
            })

        entities.append({
            "name": table_name,
            "table": table_name,
            "evidence": [evidence],
            "fields": fields,
        })

    return entities, relations


def _detect_orm_entities(content: str, source_file: str) -> list[dict[str, Any]]:
    """Detect entity names from ORM annotations (no field extraction here)."""
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name: str, line: int) -> None:
        if name in seen:
            return
        seen.add(name)
        entities.append({
            "name": name,
            "table": name,
            "evidence": [f"{source_file}:{line}"],
            "fields": [],
        })

    for m in _RE_EF_DBSET.finditer(content):
        _add(m.group(1), content[: m.start()].count("\n") + 1)
    for m in _RE_JPA_ENTITY.finditer(content):
        _add(m.group(1), content[: m.start()].count("\n") + 1)
    for m in _RE_DOCTRINE_ENTITY.finditer(content):
        _add(m.group(1), content[: m.start()].count("\n") + 1)

    return entities


def _detect_db_type(scan_result: ScanResult, content_samples: list[str]) -> str:
    """Guess database type from content samples."""
    blob = "\n".join(content_samples).lower()
    if "nvarchar" in blob or "uniqueidentifier" in blob or "[dbo]" in blob:
        return "SqlServer"
    if "auto_increment" in blob or "engine=innodb" in blob:
        return "MySQL"
    if "serial primary key" in blob or "::text" in blob:
        return "PostgreSQL"
    if ".sqlite" in blob or "autoincrement" in blob:
        return "SQLite"
    return "Unknown"


def extract_db_schema(
    project_root: str | Path,
    scan_result: ScanResult,
) -> dict[str, Any]:
    """Extract a basic DB schema.

    Returns a dict matching design doc §5.2.
    """
    root = Path(project_root).resolve()
    all_entities: dict[str, dict[str, Any]] = {}
    all_relations: list[dict[str, Any]] = []
    sources: list[str] = []
    content_samples: list[str] = []

    # Pass 1: SQL DDL files (most authoritative)
    for lm in scan_result.languages:
        if lm.id != "tsql" and lm.family != "sql":
            continue
        for f in lm.files:
            content = _read_text(f)
            content_samples.append(content[:500])
            rel = str(f.relative_to(root).as_posix())
            sources.append(rel)
            ents, rels = _parse_sql_ddl(content, rel)
            for e in ents:
                if e["name"] not in all_entities:
                    all_entities[e["name"]] = e
                else:
                    # Merge evidence
                    all_entities[e["name"]]["evidence"].extend(e["evidence"])
            all_relations.extend(rels)

    # Pass 2: ORM annotations (fallback / complement)
    for lm in scan_result.languages:
        if lm.family not in {"dotnet", "java", "php"}:
            continue
        for f in lm.files:
            content = _read_text(f)
            content_samples.append(content[:300])
            rel = str(f.relative_to(root).as_posix())
            ents = _detect_orm_entities(content, rel)
            if ents:
                sources.append(rel)
            for e in ents:
                if e["name"] not in all_entities:
                    all_entities[e["name"]] = e
                else:
                    all_entities[e["name"]]["evidence"].extend(e["evidence"])

    db_type = _detect_db_type(scan_result, content_samples)

    return {
        "schemaVersion": DB_SCHEMA_VERSION,
        "project": root.name,
        "extractDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": " + ".join(sorted(set(sources))) if sources else "(no schema source found)",
        "completeness": "basic",
        "databaseType": db_type,
        "entities": list(all_entities.values()),
        "relations": all_relations,
        "indexes": [],
        "missingPartsHint": [] if all_entities else [
            "No DB schema detected. Phase 3 entities will be degraded to confidence: medium (§9.2)."
        ],
    }
