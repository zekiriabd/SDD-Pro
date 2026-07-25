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

_OBJ = r"(?:\[?\w+\]?\.)?\[?(\w+)\]?"   # optional schema-qualified, bracketed

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

_NOISE_TABLES = frozenset({"dual"})


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


def _collect_objects(rx: re.Pattern, text: str) -> list[str]:
    found: list[str] = []
    for m in rx.finditer(text):
        name = m.group(1)
        if name and name.lower() not in _NOISE_TABLES and name not in found:
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

    calls = _collect_objects(_CALL_RE, clean)
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


def proc_complexity(rec: dict[str, Any]) -> str:
    """Route a procedure to deterministic vs LLM analysis (token efficiency).

    "simple"  → pure CRUD/SELECT, statically trivial : no control-flow branches,
                no dynamic SQL, no raised errors, no cursors. The US can be
                generated deterministically (0 token) — an LLM adds nothing.
    "complex" → real business logic worth understanding (branches, dynamic SQL,
                raised preconditions, cursors) → spawn the LLM analyst.

    Encrypted routines (body unavailable) route to "simple": no model can read
    them, so we emit a deterministic low-confidence US with a banner.
    """
    if rec.get("encrypted"):
        return "simple"
    if rec.get("branches", 0) > 0:
        return "complex"
    if rec.get("dynamicSql"):
        return "complex"
    if rec.get("raises"):
        return "complex"
    if rec.get("cursors", 0):
        return "complex"
    return "simple"


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
