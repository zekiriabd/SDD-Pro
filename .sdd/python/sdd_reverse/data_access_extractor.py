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

from sdd_reverse.scan_legacy import decode_text, normalize_bytes, read_text_normalized as _read_text

DATA_ACCESS_SCHEMA_VERSION = 1

# Languages whose source can embed inline SQL strings.
# Audit 2026-06-11 M14 : ajout Delphi (.pas), Classic ASP (.asp), VB6
# (.bas/.frm/.cls) — l'extraction SQL par regex sur strings fonctionne sur
# tout texte ; sans ces extensions, ces legacy produisaient un dataAccess
# vide en silence (reproduction du bug C7 corrigé pour VB.NET).
_CODE_EXTENSIONS = frozenset({
    ".cs", ".vb", ".java", ".php", ".jsp",
    ".pas", ".asp", ".bas", ".frm", ".cls",
})
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

# --- M1 (audit 2026-08-29) : dynamic-SQL signal on the CODE stream -----------
# `code_unit_complexity._has_dynamic_sql` has read a `dynamicSql` key on every
# query / proc-call since the complexity router shipped, but nothing on the code
# side ever wrote one — the key only existed on the DB-reverse side. The signal
# was therefore dead: a unit whose SQL is assembled at runtime (the single
# strongest reason to spend an Opus on it, because its behaviour is NOT
# statically observable) was routed exactly like a unit of parameterized
# literals.
#
# Definition kept deliberately consistent with the DB side
# (`sql_body_analyzer._DYNAMIC_RE`) so "dynamic" means the same thing in both
# streams, plus the two idioms that only exist in application code:
#   1. an execution marker inside the SQL text — sp_executesql / EXEC( / EXECUTE
#      IMMEDIATE / PREPARE  (shared with the DB side)
#   2. the SQL text carries an interpolation placeholder — String.Format `{0}`,
#      C# `$"{x}"`, f-string `{x}`, JSP/EL `${x}`, MyBatis `#{x}`, PHP `$var`
#   3. the literal is concatenated with a NON-literal expression — `"… WHERE id="
#      + userId`, `'…' . $where`, `"…" & sVar`. Literal-to-literal concatenation
#      is NOT dynamic: `_merge_concatenated_literals` has already folded those
#      into one static string.
# `@p` / `:p` bind parameters are the opposite of dynamic and never match.
_DYNAMIC_EXEC_RE = re.compile(
    r"\bsp_executesql\b|\bEXEC(?:UTE)?\s*\(|\bEXECUTE\s+IMMEDIATE\b|\bPREPARE\b",
    re.IGNORECASE,
)
_INTERPOLATION_RE = re.compile(
    r"\{\s*\w+\s*\}"        # {0} / {name} — String.Format, f-string, .format()
    r"|\$\{\s*\w+\s*\}"     # ${name} — JSP/EL, shell, template literals
    r"|#\{\s*\w+\s*\}"      # #{name} — MyBatis, Ruby
    r"|\$\w+"               # $var — PHP double-quoted interpolation
)
# Gap between a literal's closing quote and the next token, when that token is
# an expression rather than another string literal.
_CONCAT_WITH_EXPR_RE = re.compile(r"^[\s_]*[+&.][\s_]*(?![\"'])[\w$@(]")


def _is_dynamic_sql_text(sql: str) -> bool:
    """Literal-level dynamic-SQL signals (execution marker OR interpolation)."""
    return bool(_DYNAMIC_EXEC_RE.search(sql) or _INTERPOLATION_RE.search(sql))


def _concatenated_with_expression(text: str, literal_end: int) -> bool:
    """True when the literal ending at `literal_end` is glued to an expression."""
    gap = text[literal_end + 1: literal_end + 40]
    return bool(_CONCAT_WITH_EXPR_RE.match(gap))


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
    #: M1 (audit 2026-08-29) — SQL assembled at runtime (see _is_dynamic_sql_text).
    dynamic_sql: bool = False

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
            # Read by code_unit_complexity._has_dynamic_sql (model routing).
            "dynamicSql": self.dynamic_sql,
        }


def _iter_string_literals(text: str, *, include_single_quotes: bool = False):
    """Yield (content, start_offset, end_offset) for string literals.

    Handles regular ``"..."`` (with ``\\"`` escapes), C# verbatim ``@"..."``
    (with ``""`` escapes) and — when ``include_single_quotes`` (audit M3,
    PHP/JSP dominant channel) — ``'...'`` literals with ``\\'`` escapes.
    ``end_offset`` is the index of the closing quote (exclusive of content).
    """
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"' or (include_single_quotes and c == "'"):
            quote = c
            verbatim = quote == '"' and i > 0 and text[i - 1] == "@"
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
                    if cj == quote:
                        break
                    if cj == "\n":
                        break
                    buf.append(cj)
                    j += 1
            yield "".join(buf), start, j
            i = j + 1
            continue
        i += 1


# --- M2 (audit 2026-06-10) : literal concatenation merge ---------------------
# Legacy SQL is frequently split across several literals :
#     "SELECT x FROM " + "T1 WHERE y = @p"          (C#/Java +)
#     "SELECT … " & _                                (VB & with line continuation)
#     'SELECT … ' . $where                           (PHP .)
#     sb.Append("SELECT …"); sb.Append(" FROM T")    (StringBuilder chain)
#     sql += " AND z = 1";                           (compound append)
# Before this fix only the first fragment was seen → the FROM clause (and thus
# tables[]) was silently lost.
_CONCAT_GAP_RES = (
    # operator join : + & . with optional VB `_` continuation + C# @ verbatim prefix
    re.compile(r"^[\s_]*[+&.][\s_]*@?$"),
    # StringBuilder chain : ");  sb.Append("   /  ).AppendLine(@"
    re.compile(r"^\s*\)?\s*;?\s*[\w.]*\.Append(?:Line|Format)?\s*\(\s*@?$",
               re.IGNORECASE),
    # compound append statement : ";  sql += "  /  ; $sql .= '
    re.compile(r"^\s*;?\s*\$?\w+\s*(?:\+=|\.=|&=)\s*@?$"),
)


def _merge_concatenated_literals(
    literals: list[tuple[str, int, int]], text: str,
) -> list[tuple[str, int, int]]:
    """Merge adjacent literals whose inter-gap looks like a concatenation."""
    if not literals:
        return []
    merged: list[tuple[str, int, int]] = [literals[0]]
    for content, start, end in literals[1:]:
        prev_content, prev_start, prev_end = merged[-1]
        gap = text[prev_end + 1: start - 1]
        if len(gap) <= 120 and any(p.match(gap) for p in _CONCAT_GAP_RES):
            merged[-1] = (prev_content + content, prev_start, end)
        else:
            merged.append((content, start, end))
    return merged


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_sql_from_text(
    text: str, source: str = "", *, include_single_quotes: bool = False,
) -> list[Query]:
    """Extract inline SQL queries from a source file's text.

    Literals split by concatenation (+ / & / . / StringBuilder.Append chains)
    are merged first (M2) so multi-fragment queries keep their FROM clause.
    ``include_single_quotes`` enables '…' literals (M3 — PHP/JSP).
    """
    out: list[Query] = []
    literals = list(_iter_string_literals(text, include_single_quotes=include_single_quotes))
    for content, off, end in _merge_concatenated_literals(literals, text):
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
            dynamic_sql=(
                _is_dynamic_sql_text(content)
                or _concatenated_with_expression(text, end)
            ),
        ))
    return out


# M1 : the proc-name literal may be BEFORE or AFTER the marker — the most
# common ADO.NET ordering is `cmd.CommandType = CommandType.StoredProcedure;
# cmd.CommandText = "sp_X";` (name AFTER). Search both directions, nearest wins.
_PROC_NAME_WINDOW = 800

def _extract_proc_calls(text: str, source: str) -> list[dict[str, Any]]:
    """Detect stored-procedure call sites (CommandType.StoredProcedure / EXEC)."""
    calls: list[dict[str, Any]] = []
    literals = list(_iter_string_literals(text))
    for m in _STORED_PROC_MARKER_RE.finditer(text):
        marker_off = m.start()
        name = None
        name_off = 0
        best_dist: int | None = None
        for content, off, _end in literals:
            dist = abs(off - marker_off)
            if dist > _PROC_NAME_WINDOW:
                continue
            stripped = content.strip()
            if re.fullmatch(r"(?:\[?dbo\]?\.)?\[?\w+\]?", stripped) and len(stripped) >= 3:
                if best_dist is None or dist < best_dist:
                    name = stripped.strip("[]").removeprefix("dbo.").strip("[]")
                    name_off = off
                    best_dist = dist
        if name:
            # Parameters declared near the call site.
            lo = max(0, min(name_off, marker_off) - 50)
            hi = max(name_off, marker_off) + 600
            window = text[lo:hi]
            params = sorted(set(_PARAM_ADD_RE.findall(window)))
            calls.append({
                "name": name,
                "params": params,
                "file": source,
                "line": _line_at(text, marker_off),
                "via": "CommandType.StoredProcedure",
                # A name found as a plain literal IS the static case; it only
                # turns dynamic when the surrounding window builds it (M1).
                "dynamicSql": _is_dynamic_sql_text(window),
            })
    # 2. EXEC sp_xxx inside SQL strings or .sql files.
    for content, off, end in literals:
        for em in _EXEC_RE.finditer(content):
            calls.append({
                "name": em.group(1),
                "params": sorted(set(_PARAM_RE.findall(content))),
                "file": source,
                "line": _line_at(text, off),
                "via": "EXEC",
                "dynamicSql": (
                    _is_dynamic_sql_text(content)
                    or _concatenated_with_expression(text, end)
                ),
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


# _read_text centralise dans scan_legacy (audit 2026-06-11 B5 — cap 5 Mo).


# M3 : languages whose string literals are dominantly single-quoted.
_SINGLE_QUOTE_EXTENSIONS = frozenset({".php", ".jsp"})

# M4 : declarative SQL in markup — <asp:SqlDataSource SelectCommand="…">.
_MARKUP_SQL_EXTENSIONS = frozenset({".aspx", ".ascx"})
_MARKUP_SQL_RE = re.compile(
    r"(?:Select|Insert|Update|Delete)Command\s*=\s*\"([^\"]+)\"", re.IGNORECASE,
)
# M4 : Typed DataSets / TableAdapters — queries live in <CommandText> of .xsd.
_XSD_COMMAND_RE = re.compile(r"<CommandText>([\s\S]*?)</CommandText>", re.IGNORECASE)


def _query_from_sql(sql: str, rel: str, line: int) -> Query | None:
    sql = sql.strip()
    vm = _SQL_START_RE.match(sql)
    if not vm:
        return None
    return Query(
        verb=vm.group(1),
        sql=sql,
        tables=_TABLE_RE.findall(sql),
        params=_PARAM_RE.findall(sql),
        file=rel,
        line=line,
        # Declarative markup / .xsd command text has no surrounding code to
        # concatenate with — only the literal-level signals apply (M1).
        dynamic_sql=_is_dynamic_sql_text(sql),
    )


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
                queries.extend(q.to_dict() for q in extract_sql_from_text(
                    text, rel,
                    include_single_quotes=(ext in _SINGLE_QUOTE_EXTENSIONS),
                ))
                proc_calls.extend(_extract_proc_calls(text, rel))
            elif ext in _MARKUP_SQL_EXTENSIONS:
                # M4 : SqlDataSource declarative commands in WebForms markup.
                seen.add(key)
                text = _read_text(f)
                for mm in _MARKUP_SQL_RE.finditer(text):
                    q = _query_from_sql(mm.group(1), rel, _line_at(text, mm.start()))
                    if q:
                        queries.append(q.to_dict())
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
                        # A .sql script is static text — the only dynamic form
                        # here is an explicit sp_executesql / EXEC( … ) marker.
                        "dynamicSql": _is_dynamic_sql_text(
                            text[max(0, em.start() - 200): em.end() + 200]),
                    })

    # M4 : Typed DataSets (.xsd) hold TableAdapter queries — not part of any
    # language's file_extensions, so walk them explicitly (bounded).
    for xsd in root.rglob("*.xsd"):
        if any(part in {"bin", "obj", "packages", "node_modules", ".git"} for part in xsd.parts):
            continue
        rel = xsd.relative_to(root).as_posix()
        text = _read_text(xsd)
        for mm in _XSD_COMMAND_RE.finditer(text):
            q = _query_from_sql(mm.group(1), rel, _line_at(text, mm.start()))
            if q:
                queries.append(q.to_dict())

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
