#!/usr/bin/env python3
"""SDD_Pro statusline — executive view of the active pipeline run.

Reads `workspace/output/db/console.db` (table `runs`, optionally `run_phases`
and `events`) and emits a single-line summary suitable for Claude Code's
`statusLine` setting :

    [DEV-BACKEND] 48% · FEAT 1-Auth · US 1-2 · 12:34 elapsed

When no run is active (status != 'running' across all rows), falls back
to a quiet idle string :

    [SDD] idle · last: /sdd-full FEAT 1-Auth · 🟢 GREEN · 2h ago

When the DB is absent or unreadable, emits a neutral marker without
breaking the harness :

    [SDD] no run

Designed to be CHEAP : single SQLite SELECT, no agent invocation, no LLM.
Latency target < 30 ms.

Invocation contract (Claude Code statusLine):
    The harness invokes `command` periodically. stdout (last line) is
    displayed. stderr is ignored. Exit code is ignored.

Usage:
    python -m sdd_admin.statusline                  # default
    python -m sdd_admin.statusline --db <path>      # override DB path
    python -m sdd_admin.statusline --no-emoji       # ASCII only
    python -m sdd_admin.statusline --debug          # verbose to stderr

Configuration (statusLine in .claude/settings.json) :
    {
      "statusLine": {
        "type": "command",
        "command": "python -m sdd_admin.statusline",
        "padding": 0
      }
    }

Phase → label/progress mapping aligned with rules/output-protocol.md §3-§4.
"""
from __future__ import annotations

from sdd_lib.exit_codes import SUCCESS  # noqa: E402

import argparse
import os
import pathlib
import sqlite3
import sys
import time
from datetime import datetime, timezone


# Phase name → (canonical [AGENT] label, progress %)
# Aligned with rules/output-protocol.md §4 (midpoint of each range)
PHASE_TO_LABEL = {
    # /feat-generate
    "1-FEAT-GENERATE":        ("ANALYSIS",    3),
    "1.5-ELICITOR":           ("ELICITOR",    7),
    # /us-generate (PO agent)
    "2-PO":                   ("PO",         10),
    "2-US-GENERATE":          ("PO",         10),
    # /feat-validate
    "2.6-FEAT-VALIDATE":      ("VALIDATE",   14),
    # /dev-plan
    "2.7-DEV-PLAN":           ("PLAN",       18),
    "3-PLAN":                 ("PLAN",       18),
    # /arch-init (arch + DB scaffolding)
    "3-ARCH":                 ("ARCH",       27),
    "4-ARCH":                 ("ARCH",       27),
    # /dev-run dev-backend
    "5-DEV-BACKEND":          ("DEV-BACKEND", 45),
    "5-BACKEND":              ("DEV-BACKEND", 45),
    "5-CODE":                 ("DEV-BACKEND", 45),
    # API Gate
    "5.5-API-GATE":           ("QA",         62),
    "5-API-GATE":             ("QA",         62),
    # /dev-run dev-frontend
    "6-DEV-FRONTEND":         ("DEV-FRONTEND", 72),
    "6-FRONTEND":             ("DEV-FRONTEND", 72),
    # /qa-generate
    "7-QA":                   ("QA",         83),
    "7-QA-GENERATE":          ("QA",         83),
    # /sdd-review aggregation (code-reviewer, spec-compliance)
    "8-REVIEW":               ("REVIEW",     91),
    "8-CODE-REVIEW":          ("REVIEW",     91),
    "8-SPEC-COMPLIANCE":      ("REVIEW",     91),
    # security-reviewer
    "9-SECURITY":             ("SECURITY",   95),
    "9-SECURITY-REVIEW":      ("SECURITY",   95),
    # arch-reviewer + consolidated verdict
    "10-ARCH-REVIEW":         ("REVIEW",     98),
    "10-REVIEW-CONSOLIDATED": ("REVIEW",     98),
    # Terminal
    "DONE":                   ("DONE",      100),
    "100-DONE":               ("DONE",      100),
}


# Verdict → emoji
STATUS_EMOJI = {
    "running":   "⏳",
    "success":   "🟢",
    "partial":   "🟡",
    "failed":    "🔴",
    "cancelled": "⊘",
    "pass":      "🟢",
    "warn":      "🟡",
    "fail":      "🔴",
    "skip":      "⊘",
}


_ASCII_FALLBACK = {
    "🟢": "[OK]",
    "🟡": "[WARN]",
    "🔴": "[FAIL]",
    "⊘":  "[SKIP]",
    "⏳": "[..]",
    "✓":  "ok",
    "·":  "-",
}


def _to_ascii(line: str) -> str:
    for em, repl in _ASCII_FALLBACK.items():
        line = line.replace(em, repl)
    return line


def emit(line: str, no_emoji: bool = False) -> None:
    """Single stdout line. Falls back to ASCII when stdout encoding rejects emoji.

    Windows default cp1252 console raises UnicodeEncodeError on emoji
    chars (🟢/🟡/🔴/⊘/⏳). Try utf-8 reconfigure first ; if it still
    fails on write, retry with ASCII placeholders ([OK]/[WARN]/...).
    """
    if no_emoji:
        line = _to_ascii(line)
    try:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        print(line.strip(), flush=True)
    except UnicodeEncodeError:
        print(_to_ascii(line).strip(), flush=True)


def find_repo_root(start: pathlib.Path) -> pathlib.Path | None:
    """Walk up from `start` until a strict SDD_Pro repo root is found.

    Delegates to `sdd_lib.paths.repo_root()` which uses the canonical
    strict check (`.claude/agents/` + `.claude/commands/` + `workspace/`
    triple-marker) — post-mortem 2026-05-21 a démontré que le check
    unique `(p / ".claude").is_dir()` est insuffisant et peut résoudre
    sur un sous-dossier d'archive.

    `start` est conservé en argument pour backward-compat de l'API
    (ignoré désormais — `repo_root()` walk depuis CWD avec fallback
    via $SDD_REPO_ROOT et __file__).
    """
    from sdd_lib.paths import repo_root
    _ = start  # backward-compat: argument no longer used
    try:
        return repo_root()
    except Exception:
        return None


def resolve_db_path(arg: str | None) -> pathlib.Path | None:
    """Resolve console.db path. Priority: --db > env > repo root."""
    if arg:
        p = pathlib.Path(arg)
        return p if p.is_file() else None
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        candidate = pathlib.Path(env) / "workspace" / "output" / "db" / "console.db"
        if candidate.is_file():
            return candidate
    root = find_repo_root(pathlib.Path.cwd())
    if root:
        candidate = root / "workspace" / "output" / "db" / "console.db"
        if candidate.is_file():
            return candidate
    return None


def elapsed(iso: str | None) -> str:
    """Human-readable elapsed time since ISO timestamp."""
    if not iso:
        return ""
    try:
        ts = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 0:
            return ""
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m{secs % 60:02d}s"
        if secs < 86400:
            return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
        return f"{secs // 86400}d"
    except (ValueError, TypeError):
        return ""


def query_active_run(conn: sqlite3.Connection) -> dict | None:
    """Return latest run with status='running', or None."""
    cur = conn.execute(
        """
        SELECT run_id, command, feat_n, feat_name, started_at,
               status, current_phase, tags_json
        FROM runs
        WHERE status = 'running'
        ORDER BY started_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = ("run_id", "command", "feat_n", "feat_name",
            "started_at", "status", "current_phase", "tags_json")
    return dict(zip(keys, row))


def query_last_finished_run(conn: sqlite3.Connection) -> dict | None:
    """Return most recent finished run (not 'running')."""
    cur = conn.execute(
        """
        SELECT run_id, command, feat_n, feat_name, started_at,
               ended_at, status, current_phase
        FROM runs
        WHERE status != 'running'
        ORDER BY COALESCE(ended_at, started_at) DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = ("run_id", "command", "feat_n", "feat_name",
            "started_at", "ended_at", "status", "current_phase")
    return dict(zip(keys, row))


def query_running_us(conn: sqlite3.Connection, run_id: str) -> str | None:
    """From events table, extract latest US id in flight for this run."""
    try:
        cur = conn.execute(
            """
            SELECT us_id FROM events
            WHERE run_id = ? AND us_id IS NOT NULL
            ORDER BY ts DESC
            LIMIT 1
            """,
            (run_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def build_active_line(run: dict, us_id: str | None) -> str:
    """Format the chat statusline for an active run."""
    phase = (run.get("current_phase") or "").strip().upper()
    label, pct = PHASE_TO_LABEL.get(phase, ("SDD", 0))
    feat_n = run.get("feat_n")
    feat_name = run.get("feat_name") or "?"
    parts = [f"[{label}] {pct}%"]
    if feat_n is not None:
        parts.append(f"FEAT {feat_n}-{feat_name}")
    if us_id:
        parts.append(f"US {us_id}")
    eta = elapsed(run.get("started_at"))
    if eta:
        parts.append(f"{eta} elapsed")
    return " · ".join(parts)


def build_idle_line(last: dict | None) -> str:
    """Format the chat statusline when no run is active."""
    if last is None:
        return "[SDD] idle"
    status = (last.get("status") or "").lower()
    emoji = STATUS_EMOJI.get(status, "·")
    cmd = last.get("command") or "?"
    feat_n = last.get("feat_n")
    feat_name = last.get("feat_name") or ""
    parts = [f"[SDD] idle"]
    when = elapsed(last.get("ended_at") or last.get("started_at"))
    if cmd != "?":
        feat_str = f" FEAT {feat_n}-{feat_name}" if feat_n is not None else ""
        parts.append(f"last: {cmd}{feat_str}")
    parts.append(f"{emoji} {status}" if status else "")
    if when:
        parts.append(f"{when} ago")
    return " · ".join(p for p in parts if p)


#: TTL cache for statusline output (audit m6, 2026-06-06).
#: The harness may invoke statusline on every keystroke ; with a typing
#: speed of 5-10 char/sec each invocation triggers ~5 SQLite opens/sec
#: which is wasteful on Windows (file open syscalls are 10-50× slower
#: than POSIX). 750ms TTL gives perceived freshness while cutting ~80 %
#: of I/O on a typing-heavy session.
_STATUSLINE_TTL_MS = 750


def _cache_path() -> pathlib.Path | None:
    """Resolve the statusline cache file path or None on failure."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not root:
        for parent in [pathlib.Path.cwd()] + list(pathlib.Path.cwd().parents):
            if (parent / ".claude").is_dir():
                root = str(parent)
                break
    if not root:
        return None
    return pathlib.Path(root) / "workspace" / "output" / ".sys" / ".cache" / "statusline.txt"


def _try_serve_from_cache(no_emoji: bool) -> bool:
    """Emit last cached output if mtime is within TTL ; return True if served."""
    cache = _cache_path()
    if cache is None or not cache.exists():
        return False
    try:
        age_ms = (time.time() - cache.stat().st_mtime) * 1000.0
        if age_ms > _STATUSLINE_TTL_MS:
            return False
        text = cache.read_text(encoding="utf-8").rstrip("\n")
        if not text:
            return False
        emit(text, no_emoji=no_emoji)
        return True
    except OSError:
        return False


def _write_cache(line: str) -> None:
    """Persist line to cache (best-effort, never raises)."""
    cache = _cache_path()
    if cache is None:
        return
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(line + "\n", encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="sdd_admin.statusline")
    parser.add_argument("--db", help="Override console.db path")
    parser.add_argument("--no-emoji", action="store_true",
                        help="ASCII output (no emoji)")
    parser.add_argument("--debug", action="store_true",
                        help="Print debug info to stderr")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip TTL cache (debug)")
    args = parser.parse_args()

    # TTL cache short-circuit (audit m6) — skip SQLite open entirely on
    # rapid successive invocations.
    if not args.no_cache and _try_serve_from_cache(args.no_emoji):
        return SUCCESS

    db_path = resolve_db_path(args.db)
    if db_path is None:
        line = "[SDD] no run"
        emit(line, no_emoji=args.no_emoji)
        _write_cache(line)
        if args.debug:
            print("statusline: console.db not found", file=sys.stderr)
        return SUCCESS
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)
    except sqlite3.Error as exc:
        line = "[SDD] db unreachable"
        emit(line, no_emoji=args.no_emoji)
        _write_cache(line)
        if args.debug:
            print(f"statusline: sqlite3 connect failed: {exc}", file=sys.stderr)
        return SUCCESS
    try:
        active = query_active_run(conn)
        if active:
            us_id = query_running_us(conn, active["run_id"])
            line = build_active_line(active, us_id)
        else:
            last = query_last_finished_run(conn)
            line = build_idle_line(last)
        emit(line, no_emoji=args.no_emoji)
        _write_cache(line)
    except sqlite3.Error as exc:
        line = "[SDD] db error"
        emit(line, no_emoji=args.no_emoji)
        _write_cache(line)
        if args.debug:
            print(f"statusline: query failed: {exc}", file=sys.stderr)
    finally:
        conn.close()

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
