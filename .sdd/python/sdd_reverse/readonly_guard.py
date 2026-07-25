"""readonly_guard.py — Hard read-only barrier for DB stored-procedure reverse.

The proc-reverse adapter connects to a LIVE database. The single non-negotiable
contract is: **it never modifies anything**. This module is the mechanical
enforcement of that contract (invariant `reverse-db-readonly`,
`rules/reverse-engineering.md §6` class `[REVERSE_DB_READONLY_VIOLATION]`).

Every SQL statement the adapter is about to send to the server passes through
`assert_readonly()`. A statement is accepted ONLY if it is a pure read against
catalog metadata: it must start with `SELECT` (or `WITH ... SELECT`) and must
contain no DDL/DML token. Anything else raises `ReadOnlyViolation` — there is no
code path in the adapter that issues `DROP`/`DELETE`/`ALTER`/`EXEC`/etc.

NOTE (smoke/test design): this module necessarily *names* the forbidden tokens
in its blocklist. The `reverse_smoke` read-only check therefore validates the
**dialect query constants** via `is_readonly()` (they must pass), NOT a blind
grep for the words (which would false-positive on this blocklist and on the
body analyzer, which legitimately matches `INSERT`/`UPDATE` as analysis regex).

Public API:
    is_readonly(sql) -> bool
    assert_readonly(sql) -> None            # raises ReadOnlyViolation
    class ReadOnlyViolation(Exception)       # .error_class = "[REVERSE_DB_READONLY_VIOLATION]"
"""

from __future__ import annotations

import re

ERROR_CLASS = "[REVERSE_DB_READONLY_VIOLATION]"

# Any of these tokens, as a standalone word, disqualifies a statement. Covers
# T-SQL, PL/pgSQL, PL/SQL, MySQL/MariaDB and DB2 mutating verbs + procedure
# execution (we read definitions, we never RUN procedures).
_FORBIDDEN_TOKENS = (
    "INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE", "UPSERT",
    "DROP", "CREATE", "ALTER", "RENAME",
    "GRANT", "REVOKE", "DENY",
    "EXEC", "EXECUTE", "CALL", "PERFORM",
    "INTO",          # SELECT ... INTO #tmp materialises a table — forbidden
    "BACKUP", "RESTORE", "DBCC", "SHUTDOWN", "RECONFIGURE",
    "BEGIN", "COMMIT", "ROLLBACK",   # no write transactions whatsoever
    "SP_EXECUTESQL", "XP_CMDSHELL", "OPENROWSET", "OPENQUERY",
)
_FORBIDDEN_RE = re.compile(
    r"\b(?:" + "|".join(_FORBIDDEN_TOKENS) + r")\b", re.IGNORECASE
)

# A read statement must begin with SELECT, or a CTE that resolves to SELECT.
_READ_START_RE = re.compile(r"^\s*(?:WITH\b[\s\S]+?\bSELECT|SELECT)\b", re.IGNORECASE)

# Strip line/block comments so a `-- DELETE` comment never trips the guard,
# and a hidden `/* */ DROP` can never sneak past the start check.
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")


class ReadOnlyViolation(Exception):
    """Raised when a non-read-only statement is about to be executed."""

    error_class = ERROR_CLASS


def _strip_comments(sql: str) -> str:
    return _BLOCK_COMMENT_RE.sub(" ", _LINE_COMMENT_RE.sub(" ", sql))


def is_readonly(sql: str) -> bool:
    """True iff `sql` is a pure catalog read (starts with SELECT/WITH, no DDL/DML).

    Multiple statements (`;`-separated) are rejected — the adapter issues one
    statement at a time, so a batch is always suspicious.
    """
    if not sql or not sql.strip():
        return False
    clean = _strip_comments(sql).strip().rstrip(";")
    if ";" in clean:                      # no statement batching
        return False
    if not _READ_START_RE.match(clean):
        return False
    return _FORBIDDEN_RE.search(clean) is None


def assert_readonly(sql: str) -> None:
    """Raise `ReadOnlyViolation` unless `sql` is a pure catalog read."""
    if not is_readonly(sql):
        raise ReadOnlyViolation(
            f"{ERROR_CLASS} refused non-read-only statement: "
            f"{sql.strip()[:120]!r}"
        )
