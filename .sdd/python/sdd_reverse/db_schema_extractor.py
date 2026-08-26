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
reverse extraction ladder (3a reverse-tech-analyst) will degrade entities to
`confidence: medium` (per §9.2 design doc).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import ScanResult, decode_text, normalize_bytes, read_text_normalized as _read_text

DB_SCHEMA_VERSION = 1


# === SQL DDL parsing ===

# Match `CREATE TABLE name (` — body extracted via balanced-paren scan (see _find_table_body).
# Audit 2026-06-11 (B4) : l'ancien header ne matchait que les identifiants nus
# ou [bracketés] préfixés `dbo.` — les backticks MySQL (`` `users` ``), les
# identifiants double-quotés PostgreSQL, `IF NOT EXISTS` et les schémas
# non-dbo n'étaient pas parsés alors que _detect_db_type prétend reconnaître
# MySQL/PostgreSQL.
_RE_CREATE_TABLE_HEADER = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:[\[`\"]?\w+[\]`\"]?\s*\.\s*)?"          # optional schema prefix (dbo., `db`., "sch".)
    r"[\[`\"]?(\w+)[\]`\"]?\s*\(",
    re.IGNORECASE,
)

# B4 — vues et triggers : extraction des NOMS uniquement (leur corps n'est pas
# analysé — la logique métier qu'ils portent reste invisible à l'escalier,
# signalé via parseWarnings ; cf. KNOWN-LIMITATIONS « angles morts runtime »).
_RE_CREATE_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?VIEW\s+"
    r"(?:[\[`\"]?\w+[\]`\"]?\s*\.\s*)?[\[`\"]?(\w+)[\]`\"]?",
    re.IGNORECASE,
)
_RE_CREATE_TRIGGER = re.compile(
    r"CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?TRIGGER\s+"
    r"(?:[\[`\"]?\w+[\]`\"]?\s*\.\s*)?[\[`\"]?(\w+)[\]`\"]?",
    re.IGNORECASE,
)

# Column line: name TYPE[(args)] [NOT NULL|NULL] [IDENTITY(...)] [PRIMARY KEY] [DEFAULT ...]
# Audit 2026-06-10 C8 : the type may itself be bracketed (`[Id] [int]
# IDENTITY(1,1)` — DEFAULT scripting format of SSMS). The previous regex
# required the type to start with a letter, so EVERY column of an SSMS-scripted
# DDL was silently dropped (fields: [] without any WARN).
_RE_COLUMN = re.compile(
    r"^\s*\[?(\w+)\]?\s+"                                       # 1: name
    r"(\[?[A-Za-z][A-Za-z0-9_]*\]?(?:\s*\([^)]+\))?)"           # 2: type, optionally [bracketed], with optional (args)
    r"(.*)$",                                                    # 3: trailing modifiers
    re.IGNORECASE,
)
_RE_FK = re.compile(
    r"(?:CONSTRAINT\s+\[?(\w+)\]?\s+)?FOREIGN\s+KEY\s*\(\[?(\w+)\]?\)\s+"
    r"REFERENCES\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?\s*\(\[?(\w+)\]?\)",
    re.IGNORECASE,
)
# C8 : FKs scripted as `ALTER TABLE [dbo].[X] [WITH CHECK] ADD CONSTRAINT …
# FOREIGN KEY … REFERENCES …` (the SSMS default) were never parsed despite the
# docstring claiming ALTER TABLE support — file-level second pass.
_RE_ALTER_FK = re.compile(
    r"ALTER\s+TABLE\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?\s+"
    r"(?:WITH\s+(?:NO)?CHECK\s+)?ADD\s+"
    r"(?:CONSTRAINT\s+\[?(\w+)\]?\s+)?FOREIGN\s+KEY\s*\(\[?(\w+)\]?\)\s*"
    r"REFERENCES\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?\s*\(\[?(\w+)\]?\)",
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

# L1: auto/full property within a C#/Java class body → entity field name + type.
_RE_CLASS_HEADER = re.compile(r"\b(?:public|internal)?\s*(?:partial\s+)?class\s+(\w+)")
_RE_AUTO_PROP = re.compile(
    r"public\s+(?:virtual\s+|override\s+|required\s+)?"
    r"([\w<>\[\],\.\?]+)\s+(\w+)\s*\{\s*get",
)


def _class_property_registry(content: str) -> dict[str, list[dict[str, Any]]]:
    """Map className → [{name, type}] of its auto/full properties (coarse, L1).

    Splits the file on `class X` headers and parses public properties in each
    span. Sufficient to fill ORM entity fields that DDL parsing cannot see
    (EF Code-First / JPA POCOs). Best-effort — anti-hallucination preserved
    (only properties literally declared are reported).
    """
    registry: dict[str, list[dict[str, Any]]] = {}
    headers = list(_RE_CLASS_HEADER.finditer(content))
    for i, hm in enumerate(headers):
        cname = hm.group(1)
        start = hm.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        span = content[start:end]
        fields: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pm in _RE_AUTO_PROP.finditer(span):
            ptype, pname = pm.group(1).strip(), pm.group(2).strip()
            if pname in seen or pname in {"get", "set"}:
                continue
            seen.add(pname)
            fields.append({
                "name": pname,
                "type": ptype,
                "primaryKey": pname.lower() in ("id", cname.lower() + "id"),
                "identity": False,
                "nullable": ptype.endswith("?"),
                "default": None,
            })
        if fields:
            registry[cname] = fields
    return registry


# _read_text centralise dans scan_legacy (audit 2026-06-11 B5 — cap 5 Mo).


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


def _parse_sql_ddl(
    content: str, source_file: str,
    parse_warnings: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (entities, relations). Unparseable column lines are logged into
    `parse_warnings` (C8 — silent drops made SSMS DDL vanish without trace)."""
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
                if parse_warnings is not None:
                    parse_warnings.append(
                        f"{source_file} table {table_name}: column line not "
                        f"parsed: {col_text[:80]!r}"
                    )
                continue
            field_name = cm.group(1)
            # Drop SSMS brackets around the type name: `[nvarchar](100)` → `nvarchar(100)`
            field_type = re.sub(r"[\[\]]", "", (cm.group(2) or "")).strip()
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

    # C8 : file-level pass — FKs added via ALTER TABLE … ADD CONSTRAINT.
    for fk in _RE_ALTER_FK.finditer(content):
        table_name = fk.group(1)
        from_field = fk.group(3)
        line = content[: fk.start()].count("\n") + 1
        relations.append({
            "name": fk.group(2) or f"FK_{table_name}_{from_field}",
            "from": {"entity": table_name, "field": from_field},
            "to": {"entity": fk.group(4), "field": fk.group(5)},
            "type": "many-to-one",
            "evidence": f"{source_file}:{line}",
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
    all_views: list[dict[str, Any]] = []
    all_triggers: list[dict[str, Any]] = []
    sources: list[str] = []
    content_samples: list[str] = []
    parse_warnings: list[str] = []   # C8 — surfaced, never silent

    # Pass 1: SQL DDL files (most authoritative)
    #
    # Files are deduplicated ACROSS language buckets before parsing (audit F-05,
    # 2026-08-25). A `.sql` file can be listed under several SQL dialects when
    # their evidence patterns overlap; iterating the buckets then re-parsed the
    # same file once per dialect, and `seen_vt` — being reset inside the file
    # loop — could not catch it: every view, trigger and parseWarning was
    # emitted once per dialect. `scan_legacy._resolve_exclusive_groups` now makes
    # the dialects exclusive upstream; this set keeps the extractor correct on
    # its own regardless of how the buckets are populated.
    sql_files: list[Path] = []
    seen_sql: set[Path] = set()
    for lm in scan_result.languages:
        if lm.id != "tsql" and lm.family != "sql":
            continue
        for f in lm.files:
            try:
                key = f.resolve()
            except OSError:
                key = f
            if key in seen_sql:
                continue
            seen_sql.add(key)
            sql_files.append(f)

    for f in sql_files:
        content = _read_text(f)
        content_samples.append(content[:500])
        rel = str(f.relative_to(root).as_posix())
        sources.append(rel)
        # B4 — noms de vues/triggers (corps NON analysé, signalé).
        seen_vt: set[str] = set()
        for vm in _RE_CREATE_VIEW.finditer(content):
            name = vm.group(1)
            if ("v", name) in seen_vt:
                continue
            seen_vt.add(("v", name))
            line = content[: vm.start()].count("\n") + 1
            all_views.append({"name": name, "evidence": f"{rel}:{line}"})
        for tm in _RE_CREATE_TRIGGER.finditer(content):
            name = tm.group(1)
            if ("t", name) in seen_vt:
                continue
            seen_vt.add(("t", name))
            line = content[: tm.start()].count("\n") + 1
            all_triggers.append({"name": name, "evidence": f"{rel}:{line}"})
        if seen_vt:
            parse_warnings.append(
                f"{rel}: {len(seen_vt)} view(s)/trigger(s) detected — names "
                "only, their body logic is NOT analyzed (blind spot for the "
                "extraction ladder, review manually)"
            )
        ents, rels = _parse_sql_ddl(content, rel, parse_warnings)
        for e in ents:
            if e["name"] not in all_entities:
                all_entities[e["name"]] = e
            else:
                # Merge evidence
                all_entities[e["name"]]["evidence"].extend(e["evidence"])
        all_relations.extend(rels)

    # Pass 2: ORM annotations (fallback / complement) + class property registry.
    prop_registry: dict[str, list[dict[str, Any]]] = {}
    for lm in scan_result.languages:
        if lm.family not in {"dotnet", "java", "php"}:
            continue
        for f in lm.files:
            content = _read_text(f)
            content_samples.append(content[:300])
            rel = str(f.relative_to(root).as_posix())
            # L1: harvest class properties across all OO files for ORM field fill.
            for cname, fields in _class_property_registry(content).items():
                prop_registry.setdefault(cname, fields)
            ents = _detect_orm_entities(content, rel)
            if ents:
                sources.append(rel)
            for e in ents:
                if e["name"] not in all_entities:
                    all_entities[e["name"]] = e
                else:
                    all_entities[e["name"]]["evidence"].extend(e["evidence"])

    # L1: fill empty ORM entity fields from the property registry (EF Code-First
    # / JPA POCOs whose columns DDL parsing cannot see).
    for ent in all_entities.values():
        if not ent.get("fields") and ent["name"] in prop_registry:
            ent["fields"] = prop_registry[ent["name"]]

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
        "views": all_views,         # B4 — noms seuls, corps non analysé
        "triggers": all_triggers,   # B4 — noms seuls, corps non analysé
        "indexes": [],
        "parseWarnings": parse_warnings[:50],   # C8 — unparsed column lines
        "missingPartsHint": [] if all_entities else [
            "No DB schema detected. Phase 3 entities will be degraded to confidence: medium (§9.2)."
        ],
    }
