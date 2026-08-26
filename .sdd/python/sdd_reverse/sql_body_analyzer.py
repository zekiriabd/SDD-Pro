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
    r"\bsp_executesql\b|\bEXEC(?:UTE)?\s*\(|\bEXECUTE\s+IMMEDIATE\b|\bPREPARE\b",
    re.IGNORECASE,
)
# EXEC/CALL/PERFORM of a NAMED routine (not EXEC( dynamic ) — that's _DYNAMIC_RE).
_CALL_RE = re.compile(
    r"\b(?:EXEC(?:UTE)?|CALL|PERFORM)\s+(?:@\w+\s*=\s*)?" + _OBJ + r"(?!\s*\()",
    re.IGNORECASE,
)
_CURSOR_RE = re.compile(r"\bDECLARE\s+\w+\s+(?:INSENSITIVE\s+|SCROLL\s+)*CURSOR\b", re.IGNORECASE)
_TEMP_RE = re.compile(r"#\w+|\bCREATE\s+(?:GLOBAL\s+)?TEMP(?:ORARY)?\s+TABLE\b", re.IGNORECASE)

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
    raises = sorted({m.group(0).upper() for m in _RAISE_RE.finditer(clean)})

    return {
        "schemaVersion": SCHEMA_VERSION,
        "name": name,
        "lineCount": body.count("\n") + 1 if body else 0,
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
        "cursors": len(_CURSOR_RE.findall(clean)),
        "tempTables": bool(_TEMP_RE.search(clean)),
        "isReadOnly": not tables_written and not write_kinds,
    }


# Volume above which a body cannot be faithfully summarised by a fixed template,
# even with no branching (M2, audit 2026-08-25): a long linear ETL is exactly the
# case the old rubric mis-routed to "simple".
SIMPLE_MAX_LINES = 80
# A contract this wide is a capability, not a CRUD accessor.
SIMPLE_MAX_PARAMS = 4


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
