"""scan_snapshot_secrets.py — Scan .sys/proc-snapshot/ for hardcoded secrets.

Searches SQL snapshot files for patterns that look like hardcoded passwords,
connection strings or API keys and emits [REVERSE_SECRETS_DETECTED] findings.
This is informational/WARN — it never modifies the snapshot files. The Tech
Lead is expected to:
  1. Revoke any exposed credential immediately.
  2. Add the snapshot directory to .gitignore (printed as a recommended action).
  3. Re-provision the secret via a vault / environment variable.

CLI:
    python scan_snapshot_secrets.py --project NounouJob [--workspace workspace]
                                     [--json] [--exit-on-found]

Exit codes: 0 clean · 1 secrets found (only when --exit-on-found) · 2 IO error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --- Detection patterns (conservative: aim for near-zero false negatives) ----
# Each entry: (name, compiled_regex).  The regex must NOT capture the actual
# secret value to avoid leaking it into log files — it only identifies the LINE.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # SQL Server connection strings embedded in SQL bodies
    ("conn-string-password",
     re.compile(r"(?:Password|Pwd)\s*=\s*[^;'\s]{3,}", re.IGNORECASE)),
    # Explicit password assignment patterns: @pwd = 'value', Password = 'value'
    ("password-literal",
     re.compile(r"\b(?:password|passwd|pwd|secret)\b\s*[=:]\s*N?'[^']{3,}'",
                re.IGNORECASE)),
    # Connection string with User ID (always a secret context)
    ("connection-string-userid",
     re.compile(r"User\s+ID\s*=\s*\w+\s*;", re.IGNORECASE)),
    # API / auth key patterns (long alphanumeric tokens)
    ("api-key-literal",
     re.compile(r"\b(?:api[_-]?key|auth[_-]?token|access[_-]?key)\b\s*[=:]\s*N?'[A-Za-z0-9+/]{20,}'",
                re.IGNORECASE)),
    # Hardcoded SMTP credentials
    ("smtp-credential",
     re.compile(r"\b(?:smtp[._-]?(?:user|pass|password)|mail[._-]?password)\b\s*[=:]\s*N?'[^']{3,}'",
                re.IGNORECASE)),
    # Private key header (PEM / PFX embedded as base64 string in SQL)
    ("private-key-header",
     re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE)),
]


def scan_file(path: Path) -> list[dict]:
    """Return one finding per secret line in the file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        # Skip pure comment lines — secret in a comment is still a secret,
        # but we want to surface it with a note.
        is_comment = line.lstrip().startswith("--")
        for name, rx in _PATTERNS:
            if rx.search(line):
                findings.append({
                    "file": str(path),
                    "line": i,
                    "pattern": name,
                    "inComment": is_comment,
                    # Emit the line NUMBER and pattern only — never the value.
                    "excerpt": f"line {i}: {name} pattern matched",
                })
                break  # one finding per line is enough
    return findings


def scan_project(project: str, ws: Path) -> dict:
    snapshot_dir = ws / "old" / project / ".sys" / "proc-snapshot"
    if not snapshot_dir.is_dir():
        return {"ok": True, "skipped": True, "reason": f"{snapshot_dir} not found"}

    all_findings: list[dict] = []
    scanned = 0
    for sql_file in sorted(snapshot_dir.glob("*.sql")):
        findings = scan_file(sql_file)
        all_findings.extend(findings)
        scanned += 1

    gitignore_paths = [
        f".sys/proc-snapshot/",
        f".sys/schema-snapshot/",
        f".sys/db-context.json",
        f".sys/db-introspection.json",
    ]
    return {
        "ok": True,
        "project": project,
        "snapshotDir": str(snapshot_dir),
        "scanned": scanned,
        "findings": all_findings,
        "count": len(all_findings),
        "gitignoreRecommended": gitignore_paths,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan SQL snapshots for hardcoded secrets.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--exit-on-found", action="store_true",
                    help="exit 1 if any secret pattern is found (for CI use)")
    args = ap.parse_args(argv)

    result = scan_project(args.project, Path(args.workspace))

    if result.get("skipped"):
        print(f"[REVERSE] scan_snapshot_secrets: {result['reason']} — ignoré. (100%)")
        return 0

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if (args.exit_on_found and result["count"]) else 0

    if result["count"] == 0:
        print(f"[REVERSE] scan_snapshot_secrets: {result['scanned']} fichier(s) analysé(s) "
              f"— aucun secret détecté. (100%)")
    else:
        print(
            f"🔴 [REVERSE/WARN] scan_snapshot_secrets — "
            f"[REVERSE_SECRETS_DETECTED] {result['count']} pattern(s) dans "
            f"{result['scanned']} fichier(s) :",
            file=sys.stderr,
        )
        for f in result["findings"][:10]:
            note = " (dans commentaire)" if f["inComment"] else ""
            print(f"  {f['file']}:{f['line']} — {f['pattern']}{note}", file=sys.stderr)
        if len(result["findings"]) > 10:
            print(f"  … et {len(result['findings']) - 10} autre(s). (--json pour la liste complète)",
                  file=sys.stderr)
        print("\nFIX: révoquer les credentials exposés. Ajouter à .gitignore :", file=sys.stderr)
        for g in result["gitignoreRecommended"]:
            print(f"  {g}", file=sys.stderr)

    return 1 if (args.exit_on_found and result["count"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
