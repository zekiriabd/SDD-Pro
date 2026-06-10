r"""data_access_extractor.py — Extract code-level data access from legacy (L1).

Closes three 0%-coverage gaps that made reverse migration infidelity guaranteed:
    1. inline SQL embedded in application code (SqlCommand / CommandText / Dapper)
    2. stored-procedure CALL sites (CommandType.StoredProcedure / EXEC sp_xxx)
    3. stored-procedure DEFINITIONS in .sql files (CREATE PROCEDURE + parameters)

Each extracted item carries `file:line` evidence so it can be attached to the
owning functional unit (via the file→unit map) and surfaced as a Business Rule
or Data-Access deliverable in the FEAT. Connection strings live in
`config_extractor.py`; DB table DDL lives in `db_schema_extractor.py`.

Public API:
    extract_data_access(project_root, scan_result) -> dict   # data-access.json
    extract_sql_from_text(text) -> list[Query]               # reusable, testable
    parse_stored_procedure_defs(text, source) -> list[dict]  # .sql CREATE PROC

Scope L1: C#/VB (.cs/.vb), Java (.java), PHP (.php) for inline SQL, and any
`sql` family file for procedure DDL. Best-effort regex — anti-hallucination:
only what is literally present in the source is reported.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import normalize_bytes

DATA_ACCESS_SCHEMA_VERSION = 1

# Languages whose source can embed inline SQL strings.
_CODE_EXTENSIONS = frozenset({".cs", ".vb", ".java", ".php", ".jsp"})
_SQL_FAMILY_EXTENSIONS = frozenset({".sql"})

_SQL_VERBS = ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "WITH", "EXEC", "EXECUTE")
_SQL_START_RE = re.compile(r"^\s*(" + "|".join(_SQL_VERBS) + r")\b", re.IGNORECASE)

# Table references inside a SQL query.
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?",
    re.IGNORECASE,
)
# Parameter tokens (@p in T-SQL, :p in JPA/Oracle, ? positional ignored).
_PARAM_RE = re.compile(r"[@:](\w+)")

# CommandType.StoredProcedure marker.
_STORED_PROC_MARKER_RE = re.compile(r"CommandType\.StoredProcedure", re.IGNORECASE)
# EXEC sp_name  /  EXECUTE dbo.MyProc
_EXEC_RE = re.compile(
    r"\bEXEC(?:UTE)?\s+(?:@\w+\s*=\s*)?(?:\[?dbo\]?\.)?\[?(\w+)\]?",
    re.IGNORECASE,
)

# Parameter add patterns (ADO.NET).
_PARAM_ADD_RE = re.compile(
    r"(?:AddWithValue|Parameters\.Add|new\s+SqlParameter|new\s+OracleParameter|"
    r"new\s+MySqlParameter|new\s+NpgsqlParameter)\s*\(\s*[\"'](@?:?\w+)[\"']",
    re.IGNORECASE,
)

# CREATE PROCEDURE header (T-SQL / common dialects).
_CREATE_PROC_RE = re.compile(
    r"CREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?",
    re.IGNORECASE,
)
# A single proc parameter declaration: @name type [= default] [OUTPUT]
_PROC_PARAM_RE = re.compile(
    r"@(\w+)\s+([A-Za-z][\w]*(?:\s*\([^)]*\))?)(\s+OUT(?:PUT)?)?",
    re.IGNORECASE,
)


@dataclass
class Query:
    verb: str
    sql: str
    tables: list[str] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    file: str = ""
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        # Truncate long SQL in the artefact to keep it readable; full text stays
        # reachable via file:line evidence.
        sql = self.sql.strip()
        if len(sql) > 400:
            sql = sql[:400] + " …"
        return {
            "verb": self.verb.upper(),
            "sql": sql,
            "tables": sorted(set(self.tables)),
            "params": sorted(set(self.params)),
            "file": self.file,
            "line": self.line,
        }


def _iter_string_literals(text: str):
    """Yield (content, start_offset) for C#/Java/PHP string literals.

    Handles regular ``"..."`` (with ``\\"`` escapes) and C# verbatim ``@"..."``
    (with ``""`` escapes). Offsets are into `text` for line computation.
    """
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            verbatim = i > 0 and text[i - 1] == "@"
            start = i + 1
            j = start
            buf: list[str] = []
            while j < n:
                cj = text[j]
                if verbatim:
                    if cj == '"':
                        if j + 1 < n and text[j + 1] == '"':
                            buf.append('"')
                            j += 2
                            continue
                        break
                    buf.append(cj)
                    j += 1
                else:
                    if cj == "\\" and j + 1 < n:
                        buf.append(text[j + 1])
                        j += 2
                        continue
                    if cj == '"':
                        break
                    if cj == "\n":
                        break
                    buf.append(cj)
                    j += 1
            yield "".join(buf), start
            i = j + 1
            continue
        i += 1


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_sql_from_text(text: str, source: str = "") -> list[Query]:
    """Extract inline SQL queries from a source file's text."""
    out: list[Query] = []
    for content, off in _iter_string_literals(text):
        if not _SQL_START_RE.match(content):
            continue
        verb_m = _SQL_START_RE.match(content)
        verb = verb_m.group(1) if verb_m else "SQL"
        tables = _TABLE_RE.findall(content)
        params = [p for p in _PARAM_RE.findall(content)]
        out.append(Query(
            verb=verb,
            sql=content,
            tables=tables,
            params=params,
            file=source,
            line=_line_at(text, off),
        ))
    return out


def _extract_proc_calls(text: str, source: str) -> list[dict[str, Any]]:
    """Detect stored-procedure call sites (CommandType.StoredProcedure / EXEC)."""
    calls: list[dict[str, Any]] = []
    # 1. ADO.NET CommandType.StoredProcedure — the proc name is the nearest
    #    preceding string literal that looks like a bare identifier.
    literals = list(_iter_string_literals(text))
    for m in _STORED_PROC_MARKER_RE.finditer(text):
        marker_off = m.start()
        name = None
        name_off = 0
        for content, off in literals:
            if off < marker_off and re.fullmatch(r"(?:dbo\.)?\w+", content.strip()):
                name = content.strip()
                name_off = off
        if name:
            # Parameters declared near the call site.
            window = text[max(0, name_off - 50): marker_off + 600]
            params = sorted(set(_PARAM_ADD_RE.findall(window)))
            calls.append({
                "name": name,
                "params": params,
                "file": source,
                "line": _line_at(text, marker_off),
                "via": "CommandType.StoredProcedure",
            })
    # 2. EXEC sp_xxx inside SQL strings or .sql files.
    for content, off in literals:
        for em in _EXEC_RE.finditer(content):
            calls.append({
                "name": em.group(1),
                "params": sorted(set(_PARAM_RE.findall(content))),
                "file": source,
                "line": _line_at(text, off),
                "via": "EXEC",
            })
    return calls


def parse_stored_procedure_defs(text: str, source: str) -> list[dict[str, Any]]:
    """Parse CREATE PROCEDURE definitions (name + typed parameters) from SQL."""
    defs: list[dict[str, Any]] = []
    for m in _CREATE_PROC_RE.finditer(text):
        name = m.group(1)
        start = m.end()
        # Parameter block = text up to the first AS / BEGIN keyword.
        tail = text[start:start + 2000]
        as_idx = re.search(r"\bAS\b|\bBEGIN\b", tail, re.IGNORECASE)
        param_blob = tail[: as_idx.start()] if as_idx else tail
        params = [
            {
                "name": "@" + pm.group(1),
                "type": pm.group(2).strip(),
                "output": bool(pm.group(3)),
            }
            for pm in _PROC_PARAM_RE.finditer(param_blob)
        ]
        line = _line_at(text, m.start())
        defs.append({
            "name": name,
            "params": params,
            "file": source,
            "line": line,
        })
    return defs


def _read_text(path: Path) -> str:
    try:
        return normalize_bytes(path.read_bytes()).decode("utf-8", errors="replace")
    except OSError:
        return ""


def extract_data_access(project_root: str | Path, scan_result: Any) -> dict[str, Any]:
    """Extract inline SQL + stored proc calls + proc DDL across the project."""
    root = Path(project_root).resolve()
    queries: list[dict[str, Any]] = []
    proc_calls: list[dict[str, Any]] = []
    proc_defs: list[dict[str, Any]] = []

    seen: set[str] = set()
    for lm in getattr(scan_result, "languages", []):
        for f in lm.files:
            key = str(f)
            if key in seen:
                continue
            ext = f.suffix.lower()
            rel = f.relative_to(root).as_posix()
            if ext in _CODE_EXTENSIONS:
                seen.add(key)
                text = _read_text(f)
                queries.extend(q.to_dict() for q in extract_sql_from_text(text, rel))
                proc_calls.extend(_extract_proc_calls(text, rel))
            elif ext in _SQL_FAMILY_EXTENSIONS or lm.family == "sql":
                seen.add(key)
                text = _read_text(f)
                proc_defs.extend(parse_stored_procedure_defs(text, rel))
                # EXEC calls inside .sql scripts too
                for em in _EXEC_RE.finditer(text):
                    proc_calls.append({
                        "name": em.group(1),
                        "params": [],
                        "file": rel,
                        "line": _line_at(text, em.start()),
                        "via": "EXEC",
                    })

    return {
        "schemaVersion": DATA_ACCESS_SCHEMA_VERSION,
        "project": root.name,
        "extractDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "queries": queries,
        "storedProcedureCalls": proc_calls,
        "storedProcedureDefs": proc_defs,
        "summary": {
            "queriesCount": len(queries),
            "procCallsCount": len(proc_calls),
            "procDefsCount": len(proc_defs),
        },
    }
