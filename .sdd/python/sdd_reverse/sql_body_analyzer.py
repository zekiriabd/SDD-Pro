"""sql_body_analyzer.py — Deterministic signal extraction from a routine body.

Dialect-AGNOSTIC (T-SQL, PL/pgSQL, PL/SQL, MySQL/PSM, SQL PL). Given the text of
one stored procedure / function, extract the structural signals that a faithful
reverse needs, each anchored to a body line number so the LLM analyst and the
FEAT can carry `<!-- evidence: <snapshot>.sql:Lstart-Lend -->`:

  - params           : declared parameters (name, type, output)
  - tables_read      : FROM / JOIN targets
  - tables_written   : INSERT / UPDATE / DELETE / MERGE targets (data effects)
  - branches         : count of IF / CASE WHEN / WHILE (business-rule density)
  - raises           : RAISERROR / THROW / RAISE / SIGNAL (preconditions → AC-neg)
  - has_transaction  : explicit transaction control
  - has_try_catch    : structured error handling
  - dynamic_sql      : sp_executesql / EXEC(...) / EXECUTE IMMEDIATE / PREPARE
  - calls            : EXEC / CALL / PERFORM of other routines (dependency edges)
  - calls_inferred   : invocations written WITHOUT a call keyword — PL/SQL
                       `pkg.proc(...)`, scalar functions inside an expression
                       (`SELECT dbo.fnVat(x)`, `v := fn_rate(1)`). Heuristic, so
                       it lives in its OWN field: consumers resolve it against
                       the catalog and DROP what does not resolve, instead of
                       reporting phantom unresolved callees (see below).
  - cursors          : DECLARE ... CURSOR
  - temp_tables      : #temp / temporary tables

IMPORTANT: this module *reads* SQL text — it matches `INSERT`/`UPDATE` etc. as
**analysis patterns**, it never executes anything. The read-only guard
(`readonly_guard`) governs SQL *sent to the server*; the two are orthogonal.

`confidence_signal(...)` proposes a per-routine downgrade: a body dominated by
dynamic SQL is not statically understandable → cap to `medium` (bias toward
not-verified). The absolute cap per language stays in `language_signatures.yml`.

Public API:
    analyze_routine(name, body) -> dict
    confidence_signal(signals, lang_cap) -> str
"""

from __future__ import annotations

import re
from typing import Any

# Reuse the proven proc-param regex from the static extractor for parity.
from sdd_reverse.data_access_extractor import _PROC_PARAM_RE  # noqa: PLC2701

SCHEMA_VERSION = 1

# Object reference, capturing the FULL qualified name as written (D1, audit
# 2026-08-25). The previous pattern captured only the LAST identifier, which
# collapsed `sales.Orders` and `dbo.Orders` into one node and — on a 3-part name
# like `LinkedDb.dbo.Orders` — captured the SCHEMA instead of the table.
# Up to 3 parts (server/db . schema . object); brackets, backticks and double
# quotes are stripped by `_norm_obj`. Qualification is preserved as written: a
# schema is never invented.
_OBJ = r"((?:[\[`\"]?\w+[\]`\"]?\s*\.\s*){0,2}[\[`\"]?\w+[\]`\"]?)"
# Anchor closing an `_OBJ` capture. It asserts "the identifier ends HERE" without
# constraining what follows, so the regex engine never backtracks INSIDE the
# identifier to satisfy it (C1, audit 2026-08-29 — see `_CALL_RE`).
_OBJ_END = r"(?![\w.])"

_WRITE_RES = {
    "INSERT": re.compile(r"\bINSERT\s+INTO\s+" + _OBJ, re.IGNORECASE),
    "UPDATE": re.compile(r"\bUPDATE\s+(?!STATISTICS\b)" + _OBJ, re.IGNORECASE),
    "DELETE": re.compile(r"\bDELETE\s+(?:FROM\s+)?" + _OBJ, re.IGNORECASE),
    "MERGE":  re.compile(r"\bMERGE\s+(?:INTO\s+)?" + _OBJ, re.IGNORECASE),
}
_READ_RE = re.compile(r"\b(?:FROM|JOIN)\s+" + _OBJ, re.IGNORECASE)

_BRANCH_RE = re.compile(r"\b(?:IF|CASE|WHILE|ELSIF|ELSEIF)\b", re.IGNORECASE)
_RAISE_RE = re.compile(r"\b(?:RAISERROR|THROW|RAISE|SIGNAL)\b", re.IGNORECASE)
_TXN_RE = re.compile(
    r"\b(?:BEGIN\s+TRAN(?:SACTION)?|COMMIT(?:\s+TRAN(?:SACTION)?)?|"
    r"ROLLBACK|START\s+TRANSACTION)\b",
    re.IGNORECASE,
)
_TRY_RE = re.compile(r"\bBEGIN\s+TRY\b|\bEXCEPTION\s+WHEN\b|\bEXCEPTION\b", re.IGNORECASE)
_DYNAMIC_RE = re.compile(
    r"\bsp_executesql\b|\bEXEC(?:UTE)?\s*\(|\bEXECUTE\s+IMMEDIATE\b|\bPREPARE\b"
    # PL/pgSQL builds its dynamic statement with `EXECUTE format(...)`; the
    # keyword alone is a proc call in T-SQL, so the `format(` is what tells them
    # apart. Without this the plpgsql idiom was neither dynamic nor a call.
    r"|\bEXECUTE\s+format\s*\(",
    re.IGNORECASE,
)
# EXEC/CALL/PERFORM of a NAMED routine (not EXEC( dynamic ) — that's _DYNAMIC_RE).
# `EXECUTE AS` is a SECURITY CONTEXT clause, not a call: `WITH EXECUTE AS 'dbo'`
# and `execute as caller;` both extracted a phantom callee named "AS".
# Observed on a real base (2026-08-27): the 7 SSMS diagram procedures each
# reported an unresolved callee `AS`, which downgraded their confidence and
# routed them to an LLM for nothing.
#
# C1 (audit 2026-08-29) — the trailing anchor used to be `(?!\s*\()`, a *content*
# constraint meant to keep `EXEC(@sql)` out of the call list. Because it can be
# satisfied by ending the identifier one character early, the engine backtracked
# INSIDE the name to make it true: `CALL spB(1,2)` yielded the callee `sp`,
# `PERFORM fnB(1)` yielded `fn`, and `EXEC dbo.usp_Child(1)` yielded
# `dbo.usp_Chil`. A caller and its callee then landed in the SAME wave, which is
# precisely what wave planning exists to prevent. The dynamic-SQL case is now a
# SEPARATE discriminator: `_DYNAMIC_RE` keys on `EXEC(`, and the mandatory `\s+`
# below means `EXEC(@sql)` cannot match this pattern in the first place.
#
# Reserved words that can follow the keyword without being a callee. Kept to a
# tiny, dialect-reserved set on purpose: unlike the inferred scan below, an
# explicit `EXEC <name>` is an unambiguous call, and filtering it against a broad
# built-in list would silently drop user routines that happen to share a name.
_CALL_STOPWORD = r"(?:AS|IMMEDIATE|FORMAT|STATEMENT)\b"
_CALL_RE = re.compile(
    r"\b(?:EXEC(?:UTE)?|CALL|PERFORM)\s+(?!" + _CALL_STOPWORD + r")"
    r"(?:@\w+\s*=\s*)?" + _OBJ + _OBJ_END,
    re.IGNORECASE,
)
# Invocation WITHOUT a call keyword: `<name>(` in statement or expression
# position. PL/SQL has no `EXEC` inside a body (`pkg_util.do_thing(1);` IS the
# call), and every dialect invokes a scalar function inside an expression
# (`SELECT dbo.fnCalcVat(Amount)`, `v := fn_rate(1)`). Neither was extracted at
# all before C1.
#
# The lookbehind stops the match from starting inside a longer identifier or on a
# variable (`@fn(`). This scan is HEURISTIC — `INSERT INTO dbo.T (a,b)` looks
# exactly like a call — so its output goes to `callsInferred`, never to `calls`:
# consumers resolve it against the real object set and drop what does not match,
# so a false positive costs nothing while a real edge is recovered.
_INVOKE_RE = re.compile(r"(?<![\w.@])" + _OBJ + r"\s*\(", re.IGNORECASE)
_CURSOR_RE = re.compile(r"\bDECLARE\s+\w+\s+(?:INSENSITIVE\s+|SCROLL\s+)*CURSOR\b", re.IGNORECASE)
_TEMP_RE = re.compile(r"#\w+|\bCREATE\s+(?:GLOBAL\s+)?TEMP(?:ORARY)?\s+TABLE\b", re.IGNORECASE)

# db-reverse-tsql.md §2.1 — MERGE branch: WHEN NOT MATCHED BY SOURCE THEN DELETE
# is a CONDITIONAL MASS DELETION, the most dangerous MERGE branch and the one most
# likely to be demoted to "plumbing" by a reader who only sees the MERGE keyword.
_MERGE_DELETE_RE = re.compile(
    r"\bWHEN\s+NOT\s+MATCHED\s+BY\s+SOURCE\s+THEN\s+DELETE\b", re.IGNORECASE
)
# db-reverse-tsql.md §2.2 — OUTPUT without INTO returns a result set to the caller;
# that is part of the CONTRACT, not plumbing. OUTPUT…INTO @t is plumbing (stays in
# the proc).
# Two-pass detection: (1) any OUTPUT keyword exists, AND (2) no OUTPUT…INTO pattern.
# We cannot use a simple negative lookahead because INSERTED/DELETED pseudo-tables
# follow OUTPUT directly ("OUTPUT inserted.Col") and "inserted" contains "INSERT",
# which would accidentally suppress the match.
_HAS_OUTPUT_RE = re.compile(r"\bOUTPUT\b", re.IGNORECASE)
_OUTPUT_INTO_RE = re.compile(r"\bOUTPUT\b.+?\bINTO\b", re.IGNORECASE | re.DOTALL)

# Comment strip so commented-out SQL does not inflate the signals.
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
# Single-quoted SQL string literal (with '' escape). Universal across dialects.
# Double-quoted text is left intact — it is an *identifier* in standard SQL /
# T-SQL / Oracle / PostgreSQL, not a string, so masking it would eat table names.
_STRING_RE = re.compile(r"'(?:[^']|'')*'")

# Leaf names that are never a real table: Oracle's `dual`, and the trigger
# pseudo-tables (`inserted`/`deleted` on SQL Server, `new`/`old` elsewhere) —
# counting them as tables polluted the dependency graph with phantom nodes.
_NOISE_TABLES = frozenset({"dual", "inserted", "deleted"})

# System routines that are NOT business dependencies (N3, audit 2026-08-25).
# `EXEC sp_executesql @sql` used to land in `callsProcs`, adding a phantom node
# to the dependency graph and to cohesion clustering. Matched on the LEAF name.
# Deliberately explicit rather than a blanket `sp_*`: legacy shops do ship user
# procedures named `sp_Something`, and dropping those would lose real edges.
_SYSTEM_ROUTINES = frozenset({
    "sp_executesql", "sp_execute", "sp_prepare", "sp_unprepare", "sp_cursoropen",
    "sp_helptext", "sp_rename", "sp_getapplock", "sp_releaseapplock",
    "sp_send_dbmail", "sp_addextendedproperty", "sp_sqlexec",
    "dbms_output", "dbms_sql", "dbms_lob", "dbms_utility",
})
_SYSTEM_ROUTINE_PREFIXES = ("xp_",)      # extended procedures are always system

# Leaf names that may sit immediately before a `(` without being a routine call.
# Consulted ONLY by the inferred-invocation scan (`_INVOKE_RE`), never by the
# explicit `EXEC/CALL/PERFORM` scan — see `_CALL_STOPWORD` for why.
# Three groups: SQL statement/clause keywords, declared type names, and the
# built-in function libraries of the four supported engines.
_NOT_A_CALL = frozenset(w.lower() for w in (
    # --- statement / clause keywords -------------------------------------- #
    "select", "insert", "update", "delete", "merge", "from", "where", "into",
    "values", "set", "declare", "begin", "end", "as", "is", "if", "elsif",
    "elseif", "else", "then", "case", "when", "while", "loop", "for", "do",
    "and", "or", "not", "in", "exists", "between", "like", "any", "all", "some",
    "on", "using", "join", "inner", "left", "right", "full", "outer", "cross",
    "apply", "union", "intersect", "except", "group", "order", "by", "having",
    "with", "over", "partition", "top", "distinct", "output", "returns",
    "return", "returning", "limit", "offset", "fetch", "open", "close", "next",
    "deallocate", "cursor", "table", "view", "trigger", "procedure", "proc",
    "function", "package", "index", "constraint", "primary", "key", "foreign",
    "references", "unique", "check", "default", "identity", "computed",
    "create", "alter", "drop", "truncate", "grant", "revoke", "exec", "execute",
    "call", "perform", "raise", "raiserror", "throw", "signal", "print",
    "commit", "rollback", "save", "tran", "transaction", "goto", "break",
    "continue", "exception", "when_others", "others", "null", "add", "column",
    "type", "row", "rows", "only", "nowait", "readonly", "out", "inout",
    # --- declared type names (a `varchar(50)` is not a call) --------------- #
    "char", "nchar", "varchar", "nvarchar", "varchar2", "nvarchar2", "text",
    "ntext", "binary", "varbinary", "blob", "clob", "nclob", "raw", "long",
    "decimal", "numeric", "number", "float", "real", "double", "int", "integer",
    "bigint", "smallint", "tinyint", "bit", "boolean", "money", "smallmoney",
    "datetime", "datetime2", "smalldatetime", "datetimeoffset", "timestamp",
    "time", "date", "interval", "uniqueidentifier", "uuid", "xml", "json",
    "jsonb", "sql_variant", "hierarchyid", "geography", "geometry", "enum",
    # --- built-in functions (T-SQL / PL-pgSQL / PL-SQL / MySQL) ------------ #
    "count", "sum", "avg", "min", "max", "abs", "round", "floor", "ceiling",
    "ceil", "power", "sqrt", "exp", "log", "log10", "sign", "mod", "rand",
    "random", "isnull", "ifnull", "nullif", "coalesce", "nvl", "nvl2", "decode",
    "iif", "choose", "greatest", "least", "len", "length", "datalength",
    "substring", "substr", "left", "right", "charindex", "patindex", "instr",
    "position", "replace", "stuff", "reverse", "upper", "lower", "ltrim",
    "rtrim", "trim", "lpad", "rpad", "space", "replicate", "concat",
    "concat_ws", "string_agg", "group_concat", "listagg", "split_part",
    "format", "cast", "convert", "try_cast", "try_convert", "try_parse",
    "parse", "to_char", "to_date", "to_number", "to_timestamp", "str_to_date",
    "date_format", "getdate", "getutcdate", "sysdatetime", "sysutcdatetime",
    "systimestamp", "sysdate", "now", "curdate", "curtime", "current_date",
    "current_time", "current_timestamp", "localtimestamp", "dateadd",
    "datediff", "datepart", "datename", "date_add", "date_sub", "date_trunc",
    "trunc", "extract", "age", "year", "month", "day", "hour", "minute",
    "second", "week", "quarter", "dayofweek", "last_day", "eomonth",
    "row_number", "rank", "dense_rank", "ntile", "lag", "lead", "first_value",
    "last_value", "cume_dist", "percent_rank", "newid", "newsequentialid",
    "uuid_generate_v4", "gen_random_uuid", "scope_identity", "ident_current",
    "identity_insert", "object_id", "object_name", "object_definition",
    "schema_name", "schema_id", "db_name", "db_id", "type_name", "col_name",
    "columnproperty", "objectproperty", "serverproperty", "has_perms_by_name",
    "suser_sname", "suser_name", "user_name", "current_user", "session_user",
    "system_user", "host_name", "app_name", "original_login",
    "error_message", "error_number", "error_severity", "error_state",
    "error_line", "error_procedure", "sqlerrm", "sqlcode", "raise_application_error",
    "checksum", "binary_checksum", "hashbytes", "md5", "sha2", "crc32",
    "json_value", "json_query", "json_modify", "json_extract", "openjson",
    "openquery", "openrowset", "opendatasource", "containstable", "freetexttable",
    "isnumeric", "isdate", "try_convert_json", "nextval", "currval", "setval",
    "generate_series", "unnest", "array_agg", "string_to_array", "array_to_string",
    "regexp_replace", "regexp_substr", "regexp_like", "regexp_instr", "regexp_count",
    "grouping", "grouping_id", "rollup", "cube", "sets",
))

# Where a routine BODY starts, after its `CREATE …` header. The header's own
# parameter list (`CREATE PROCEDURE dbo.spA(@a int)`) looks exactly like an
# invocation of `dbo.spA`, and taking it as one would mark every routine in the
# database self-recursive. Genuine self-recursion inside the body still matches.
_CREATE_HEADER_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?"
    r"(?:PROCEDURE|PROC|FUNCTION|VIEW|TRIGGER|PACKAGE(?:\s+BODY)?)\b",
    re.IGNORECASE,
)
_BODY_START_RE = re.compile(r"\b(?:AS|IS|BEGIN|RETURN)\b", re.IGNORECASE)


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _blank_match_keep_lines(m: "re.Match") -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def _strip_comments_keep_lines(text: str) -> str:
    """Blank out comments but preserve newlines so line numbers stay accurate."""
    return _BLOCK_COMMENT_RE.sub(_blank_match_keep_lines,
                                 _LINE_COMMENT_RE.sub(_blank_match_keep_lines, text))


def _blank_string_literals(text: str) -> str:
    """Blank the CONTENT of single-quoted string literals (P1/DB2 fidelity fix).

    Prevents SQL built dynamically inside a string (``SET @sql = 'INSERT INTO
    Orders ...'``) or SQL keywords inside an error message (``'DELETE interdit'``)
    from being mistaken for a real static write/read/call. The dynamic-SQL flag
    still fires (it keys on ``sp_executesql`` / ``EXEC(`` / ``EXECUTE IMMEDIATE``
    — code that lives OUTSIDE the quotes), so confidence is still downgraded.
    Quotes and newlines are preserved so line numbers stay accurate.
    """
    def _b(m: "re.Match") -> str:
        inner = re.sub(r"[^\n]", " ", m.group(0)[1:-1])
        return "'" + inner + "'"
    return _STRING_RE.sub(_b, text)


def _params_from_header(body: str) -> list[dict[str, Any]]:
    """Extract typed parameters from the CREATE PROC/FUNCTION header block."""
    head_m = re.search(r"\b(?:AS|BEGIN|RETURNS)\b", body, re.IGNORECASE)
    header = body[: head_m.start()] if head_m else body[:2000]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pm in _PROC_PARAM_RE.finditer(header):
        name = "@" + pm.group(1)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "type": pm.group(2).strip(), "output": bool(pm.group(3))})
    return out


_QUOTE_CHARS = str.maketrans("", "", '[]`"')


def _norm_obj(raw: str) -> str:
    """Normalise a captured object reference to `schema.name` as WRITTEN.

    Strips brackets/backticks/quotes and whitespace around the dots. A name
    written unqualified stays unqualified — the analyzer never invents a default
    schema, because guessing `dbo.` would create a false identity between
    `Orders` and `dbo.Orders` on engines where the caller's default schema
    differs.
    """
    parts = [p.strip().translate(_QUOTE_CHARS).strip()
             for p in (raw or "").split(".")]
    return ".".join(p for p in parts if p)


def object_leaf(name: str) -> str:
    """Last segment of a (possibly qualified) object name — `dbo.T` → `T`."""
    return (name or "").rsplit(".", 1)[-1]


def _is_system_routine(name: str) -> bool:
    leaf = object_leaf(name).lower()
    return leaf in _SYSTEM_ROUTINES or leaf.startswith(_SYSTEM_ROUTINE_PREFIXES)


def _collect_objects(
    rx: re.Pattern, text: str, *, drop_system_routines: bool = False,
) -> list[str]:
    """Collect normalised object references, de-duplicated case-insensitively.

    De-duplication is on the qualified, lower-cased form: `dbo.Orders` and
    `sales.Orders` are two distinct objects (that was D1), while `DBO.Orders`
    and `dbo.orders` are one.
    """
    found: list[str] = []
    seen: set[str] = set()
    for m in rx.finditer(text):
        name = _norm_obj(m.group(1))
        if not name or object_leaf(name).lower() in _NOISE_TABLES:
            continue
        if drop_system_routines and _is_system_routine(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
    return found


def _body_region(text: str) -> str:
    """The routine body with its `CREATE …` header removed (see `_CREATE_HEADER_RE`).

    Returns the text unchanged when there is no header — MySQL's
    `ROUTINE_DEFINITION` ships the `BEGIN … END` block alone, and a hand-built
    fragment has none either.
    """
    m = _CREATE_HEADER_RE.search(text)
    if not m:
        return text
    m2 = _BODY_START_RE.search(text, m.end())
    return text[m2.end():] if m2 else text[m.end():]


def _collect_inferred_calls(clean: str, explicit: list[str]) -> list[str]:
    """Invocations written without a call keyword, minus keywords and built-ins.

    Deliberately permissive on the regex and strict on the filter: what survives
    is a *candidate* edge, resolved against the real catalog by the consumer
    (`db_wave_planner.resolve_calls`, `sql_dependency_graph`), which drops
    anything that does not name a known object. A leftover false positive
    therefore never produces a phantom node or an unresolved-callee report.
    """
    already = {n.lower() for n in explicit}
    found: list[str] = []
    seen: set[str] = set()
    for m in _INVOKE_RE.finditer(_body_region(clean)):
        name = _norm_obj(m.group(1))
        leaf = object_leaf(name).lower()
        if not name or leaf in _NOT_A_CALL or leaf in _NOISE_TABLES:
            continue
        if _is_system_routine(name):
            continue
        key = name.lower()
        if key in seen or key in already:
            continue
        seen.add(key)
        found.append(name)
    return found


def analyze_routine(name: str, body: str) -> dict[str, Any]:
    """Extract deterministic signals from one routine body. 0 token."""
    body = body or ""
    # Strip comments THEN blank string-literal content: a static-signal scan must
    # not see SQL that lives inside comments or inside dynamic-SQL / message
    # strings (P1/DB2 fidelity). Dynamic-SQL detection still fires on the code
    # keywords outside the quotes.
    clean = _blank_string_literals(_strip_comments_keep_lines(body))

    tables_written: list[str] = []
    write_kinds: dict[str, list[str]] = {}
    for kind, rx in _WRITE_RES.items():
        objs = _collect_objects(rx, clean)
        if objs:
            write_kinds[kind] = objs
        for o in objs:
            if o not in tables_written:
                tables_written.append(o)

    written_lc = {t.lower() for t in tables_written}
    tables_read = [t for t in _collect_objects(_READ_RE, clean) if t.lower() not in written_lc]

    calls = _collect_objects(_CALL_RE, clean, drop_system_routines=True)
    calls_inferred = _collect_inferred_calls(clean, calls)
    raises = sorted({m.group(0).upper() for m in _RAISE_RE.finditer(clean)})

    # db-reverse-tsql.md §2.1: MERGE with WHEN NOT MATCHED BY SOURCE THEN DELETE is
    # a conditional mass deletion — a distinct, high-severity write kind.
    merge_delete = bool(_MERGE_DELETE_RE.search(clean))
    if merge_delete and "MERGE" in write_kinds:
        write_kinds["MERGE_DELETE"] = write_kinds.get("MERGE", [])

    # db-reverse-tsql.md §2.2: OUTPUT without INTO returns a result set — contract.
    output_contract = bool(_HAS_OUTPUT_RE.search(clean)) and not bool(_OUTPUT_INTO_RE.search(clean))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "name": name,
        # `count(NL) + 1` overcounts by one whenever the body ends with a
        # newline — which SQL Server bodies do. Observed on a real base
        # (2026-08-27): 90 evidence ranges pointed one line PAST end-of-file,
        # so the anti-hallucination contract could not be resolved on disk.
        # `splitlines()` is correct for trailing NL, CRLF and empty bodies.
        "lineCount": len(body.splitlines()),
        "params": _params_from_header(body),
        "tablesRead": tables_read,
        "tablesWritten": tables_written,
        "writeKinds": write_kinds,
        "branches": len(_BRANCH_RE.findall(clean)),
        "raises": raises,
        "hasTransaction": bool(_TXN_RE.search(clean)),
        "hasTryCatch": bool(_TRY_RE.search(clean)),
        "dynamicSql": bool(_DYNAMIC_RE.search(clean)),
        "calls": calls,
        # Heuristic sibling of `calls` — resolve-or-drop, never "unresolved".
        "callsInferred": calls_inferred,
        "cursors": len(_CURSOR_RE.findall(clean)),
        "tempTables": bool(_TEMP_RE.search(clean)),
        "isReadOnly": not tables_written and not write_kinds,
        # Extended signals (db-reverse-tsql.md §2.1-§2.2)
        "mergeDeleteBySource": merge_delete,
        "outputContract": output_contract,
    }


# Volume above which a body cannot be faithfully summarised by a fixed template,
# even with no branching (M2, audit 2026-08-25): a long linear ETL is exactly the
# case the old rubric mis-routed to "simple".
SIMPLE_MAX_LINES = 80
# A contract this wide is a capability, not a CRUD accessor.
SIMPLE_MAX_PARAMS = 4
# Above this many distinct callers, an object is load-bearing for the database:
# its meaning propagates everywhere, so it is worth an LLM read even when its
# own body is trivial.
FANIN_CRITICAL = 3


def complexity_reasons(rec: dict[str, Any]) -> list[str]:
    """Why a routine is complex — empty list means genuinely trivial.

    Returned as data (not just a verdict) so the orchestrator, the US banner and
    the audit log can all state WHY an LLM was or was not spent on this object.
    """
    reasons: list[str] = []
    if rec.get("branches", 0) > 0:
        reasons.append(f"branches={rec['branches']}")
    if rec.get("dynamicSql"):
        reasons.append("dynamic-sql")
    if rec.get("raises"):
        reasons.append("raises=" + ",".join(rec.get("raises") or []))
    if rec.get("cursors", 0):
        reasons.append(f"cursors={rec['cursors']}")

    # --- M2 additions: volume and data-effect breadth, not just control flow ---
    lines = rec.get("lineCount") or 0
    if lines > SIMPLE_MAX_LINES:
        reasons.append(f"lines={lines}>{SIMPLE_MAX_LINES}")
    written = rec.get("tablesWritten") or []
    if len(written) >= 2:
        reasons.append(f"writes={len(written)}-tables")
    elif written and rec.get("hasTransaction"):
        # An explicit transaction around a write encodes an all-or-nothing
        # business invariant — that belongs in an AC, not in a template.
        reasons.append("transactional-write")
    params = rec.get("params") or []
    if len(params) >= SIMPLE_MAX_PARAMS:
        reasons.append(f"params={len(params)}")

    # --- Graph signals (audit 2026-08-26): composition is complexity ---------
    # The rubric used to weigh only what a body does BY ITSELF. An orchestrator
    # of forty branchless lines that delegates its whole business rule to six
    # other procedures was therefore "simple": it got a template User Story, no
    # LLM, and — nothing having downgraded it — sailed through the REVERSE-GATE
    # with a `high` confidence it had not earned. Delegation is not simplicity.
    calls = rec.get("callsProcs") or []
    if calls:
        reasons.append(f"calls={len(calls)}")
    unresolved = rec.get("unresolvedCallees") or []
    if unresolved:
        reasons.append("unresolved-callees=" + ",".join(sorted(unresolved)[:3]))
    if rec.get("recursive"):
        reasons.append("recursive")
    if (rec.get("fanIn") or 0) >= FANIN_CRITICAL:
        # Not complex in itself, but critical by usage: getting it wrong is
        # wrong in every caller at once.
        reasons.append(f"fan-in={rec['fanIn']}")
    return reasons


def proc_complexity(rec: dict[str, Any]) -> str:
    """Route a SQL object to deterministic vs LLM analysis (token efficiency).

    "simple"  → statically trivial AND small: a short, single-effect CRUD/SELECT
                with no control flow. A fixed template can describe it honestly,
                so an LLM adds nothing and costs tokens.
    "complex" → real business logic worth understanding — branches, dynamic SQL,
                raised preconditions, cursors, volume, multi-table writes,
                transactional invariants, or a wide parameter contract.
                → spawn the LLM analyst.

    Encrypted routines (body unavailable) route to "simple": no model can read
    them, so we emit a deterministic low-confidence US with a banner.

    Audit 2026-08-25 (M2): the rubric used to look at control flow ONLY. A
    500-line branchless procedure writing twelve tables inside a transaction was
    classified "simple", got a tautological template US, and — because nothing
    downgraded its confidence — sailed through the REVERSE-GATE with no human
    review. Volume and data-effect breadth are now first-class signals.
    """
    if rec.get("encrypted"):
        return "simple"
    return "complex" if complexity_reasons(rec) else "simple"


def confidence_signal(signals: dict[str, Any], lang_cap: str) -> str:
    """Effective per-routine confidence: cap, downgraded if not statically clear.

    Dynamic SQL means the real behaviour is not visible in the text → never
    `high`. Encrypted bodies (no signals at all) → `low`.
    """
    order = {"low": 0, "medium": 1, "high": 2}
    cap = lang_cap if lang_cap in order else "low"
    eff = cap
    if signals.get("dynamicSql"):
        eff = "medium" if order[eff] > order["medium"] else eff
    if signals.get("lineCount", 0) == 0:           # encrypted / empty
        eff = "low"
    return eff


def confidence_with_graph(base: str, metrics: dict[str, Any] | None) -> str:
    """Lower a routine's confidence for what its call graph hides from it.

    Two situations make a body an incomplete account of its own behaviour, and
    neither is visible in the text alone:

      * an **unresolved callee** — a linked server, a cross-database call, a
        dropped object, or a bare name that matches two schemas. The analyst
        cannot read what that call does, so the User Story cannot be `high`.
      * **recursion** — a self-recursive routine or a mutually recursive pair.
        Termination and accumulated effect are not statically readable.

    Applied on top of `confidence_signal`, never above it: this function only
    ever lowers. Confidence stays min-monotone up the ladder, which is what
    makes the REVERSE-GATE honest about composed behaviour.
    """
    order = {"low": 0, "medium": 1, "high": 2}
    eff = base if base in order else "low"
    if not metrics:
        return eff
    if metrics.get("unresolvedCallees") or metrics.get("recursive"):
        eff = "medium" if order[eff] > order["medium"] else eff
    return eff
