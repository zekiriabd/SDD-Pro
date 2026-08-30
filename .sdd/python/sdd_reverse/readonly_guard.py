"""readonly_guard.py — Hard read-only barrier for DB stored-procedure reverse.

The db-reverse adapter connects to a LIVE database. The single non-negotiable
contract is: **it never modifies anything**. This module is the mechanical
enforcement of that contract (invariant `reverse-db-readonly`,
`rules/reverse-engineering.md §6` class `[REVERSE_DB_READONLY_VIOLATION]`).

Every SQL statement the adapter is about to send to the server passes through
one of TWO guards, and nothing reaches a cursor without passing one of them:

  - `assert_readonly()` — for every catalog QUERY. Accepted ONLY if it is a pure
    read: it must start with `SELECT` (or `WITH ... SELECT`) and must contain no
    DDL/DML token. There is no code path in the adapter that issues
    `DROP`/`DELETE`/`ALTER`/`EXEC`/etc.
  - `assert_session_pragma()` — for the handful of *session pragmas* the adapter
    issues right after connecting to harden the session itself
    (`SET TRANSACTION ...`). These are not SELECTs, so they can never pass
    `assert_readonly`; before the audit of 2026-08-25 (finding N1) they were sent
    with no guard at all, which made this module's own contract false. They are
    now matched against a CLOSED whitelist (`_SESSION_PRAGMAS`): a pragma that is
    not literally one of them is refused like any mutation.

The two guards are disjoint on purpose — widening `assert_readonly` to tolerate
`SET` would have opened it to `SET @sql = ...` and friends.

NOTE (smoke/test design): this module necessarily *names* the forbidden tokens
in its blocklist. The `reverse_smoke` read-only check
(`check_dialect_queries_readonly`, registry name
`reverse-db-readonly-dialect-queries`) therefore validates the **dialect query
constants** via `is_readonly()` (they must pass), NOT a blind grep for the words
(which would false-positive on this blocklist and on the body analyzer, which
legitimately matches `INSERT`/`UPDATE` as analysis regex). The pytest suite
covers the same ground from the other side — `tests/test_reverse_db_dialects.py`
and `tests/test_sdd_reverse_proc.py`, the enforcers named by
`INVARIANTS.reverse.yml:reverse-db-readonly-proc`.

(Audit 2026-08-29, m4: this paragraph described the smoke check for months
before one existed. It exists now.)

Public API:
    is_readonly(sql) -> bool
    assert_readonly(sql) -> None            # raises ReadOnlyViolation
    is_allowed_session_pragma(sql) -> bool
    assert_session_pragma(sql) -> None      # raises ReadOnlyViolation
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


# --------------------------------------------------------------------------- #
# Session pragmas (N1, audit 2026-08-25)
# --------------------------------------------------------------------------- #

# CLOSED whitelist. Each entry is a session-hardening statement the adapter may
# issue immediately after connecting; none of them reads or writes user data.
#
# SQL Server keeps READ UNCOMMITTED deliberately: an introspection run must never
# take shared locks on a production catalog and block the application. Dirty
# reads of catalog metadata are harmless (a routine being altered mid-scan is
# reported by `modified` anyway); blocking a live app is not. The trade-off is
# recorded here rather than silently changed.
_SESSION_PRAGMAS = frozenset({
    "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED",   # SQL Server
    "SET TRANSACTION READ ONLY",                          # Oracle
    "SET SESSION TRANSACTION READ ONLY",                  # MySQL / MariaDB
    "SET TRANSACTION ISOLATION LEVEL READ COMMITTED",     # generic fallback
})

_WS_RE = re.compile(r"\s+")


def _normalise_pragma(sql: str) -> str:
    return _WS_RE.sub(" ", _strip_comments(sql or "").strip().rstrip(";")).upper()


def is_allowed_session_pragma(sql: str) -> bool:
    """True iff `sql` is exactly one whitelisted session-hardening pragma."""
    return _normalise_pragma(sql) in _SESSION_PRAGMAS


def assert_session_pragma(sql: str) -> None:
    """Raise `ReadOnlyViolation` unless `sql` is a whitelisted session pragma."""
    if not is_allowed_session_pragma(sql):
        raise ReadOnlyViolation(
            f"{ERROR_CLASS} refused non-whitelisted session pragma: "
            f"{(sql or '').strip()[:120]!r}"
        )
