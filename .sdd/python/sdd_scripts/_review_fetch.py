"""Internal helpers for sdd_review.py — DB fetch + deduplication (M2 split v7.0.0).

Extracted from sdd_review.py to keep the orchestrator <300L. Public API
(Finding, _normalize_path, deduplicate_findings, fetch_findings,
run_quality_scan, SEVERITY_*) is re-exported from sdd_review.py for
backward-compat with tests (test_sdd_review_dedup.py).

v7.0.0-alpha (audit MAJ-15, 2026-06-04) — the `_` prefix on this file
and `_review_report.py` is **intentional** (PEP 8 module-private
convention). Renaming to a `sdd_lib/review/` sub-package would be
cosmetic: zero behavior gain, ~10 caller updates, ~30min of test
realignment. Decision : keep as-is.
"""
from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect  # noqa: E402


# Severity ordering — same as accessibility-auditor / security-reviewer.
SEVERITY_ORDER = ("info", "minor", "moderate", "serious", "critical", "blocker")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# Map quality_scan severities → unified ordering
QUALITY_SEV_MAP = {
    "error":    "serious",
    "warning":  "moderate",
    "info":     "info",
    "blocker":  "blocker",
    "critical": "critical",
    "major":    "serious",
    "minor":    "minor",
}


@dataclass
class Finding:
    source: str           # "quality" | "code-review" | "security" | "a11y" | "perf" | "spec"
    issue_class: str      # [CLASS] préfixe, ex. REVIEW_*, SEC_*, A11Y_*
    severity: str         # normalisé sur SEVERITY_ORDER
    rule: str | None
    file_path: str | None
    line: int | None
    message: str | None
    owner: str = "unknown"


def run_quality_scan(feat_n: int) -> tuple[bool, str]:
    """Re-run quality_scan.py for the given FEAT. Returns (ok, stdout-tail)."""
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "quality_scan.py"),
        "--feat-number", str(feat_n),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (>120s)"
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return proc.returncode == 0, "\n".join(tail[-6:])


def run_pattern_scan(feat_n: int) -> tuple[bool, str]:
    """Re-run the deterministic pattern scan for a FEAT. Returns (ok, stdout-tail).

    Audit 2026-08-28, corrections #2 and #6. This is the CALLER that
    `security_patterns.yaml` and `code_review_patterns.yaml` never had: 467
    lines of regex covering 16 error classes sat in the repo with no runtime
    consumer, while the detection was delegated to an LLM reading their prose
    twin. Wiring it here — Python calling Python, inside the aggregator that
    already refreshes `quality_scan` — means it runs whether or not an agent
    remembers to, which is the whole point.

    `--no-fail` is deliberate: exit 4 (verdict RED) is NOT a scan failure, and
    /sdd-review owns the consolidated verdict. Letting a RED propagate as a
    subprocess error here would make the aggregator report an infra problem
    where there is a security finding.
    """
    cmd = [
        sys.executable, "-m", "sdd_scripts.scan_patterns",
        "--feat-number", str(feat_n), "--no-fail",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (>180s)"
    except OSError as exc:
        return False, f"OSError: {exc}"
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return proc.returncode == 0, "\n".join(tail[-6:])


def _norm_sev(s: str | None, src: str) -> str:
    if not s:
        return "info"
    s = s.strip().lower()
    if src == "quality":
        return QUALITY_SEV_MAP.get(s, "info")
    return s if s in SEVERITY_RANK else "info"


def _select_with_detector(conn, select: str, tail: str, params: tuple):
    """Exécute `select` en ajoutant la colonne `detector` si elle existe.

    Le schéma v8 l'ajoute (audit 2026-08-28). Une base restée en v7 — lue par
    du code v8 sans être passée par `ensure_initialized` — n'a pas la colonne :
    on retombe sur la requête d'origine, et `_is_agent_row` traite l'absence
    de `detector` comme `'agent'`, ce qui reproduit exactement le comportement
    antérieur. Une régression de télémétrie ne doit pas casser une lecture.
    """
    try:
        return list(conn.execute(f"{select}, detector {tail}", params))
    except sqlite3.OperationalError:
        return list(conn.execute(f"{select} {tail}", params))


def _is_agent_row(row) -> bool:
    """Un finding prouve-t-il qu'un AGENT a tourné ?

    Les findings déterministes (`detector='deterministic'`) alimentent le
    verdict mais ne valent PAS preuve d'exécution de l'agent : sinon
    `--ensure-scans` cesserait de détecter un reviewer LLM absent.

    `qa_code_review` distingue en plus deux producteurs agent
    (`agent:code-review` / `agent:arch-review`, cf. `ingest_agent_report.
    ingest_code_review`) pour que leurs replace respectifs ne s'écrasent
    plus — les deux valeurs restent des preuves d'exécution agent.
    """
    try:
        det = row["detector"]
    except (KeyError, IndexError, TypeError):
        return True
    return det in (None, "", "agent") or (isinstance(det, str) and det.startswith("agent:"))


def fetch_findings(feat_n: int) -> tuple[list[Finding], list[str]]:
    """Pull all auditor findings for `feat_n` from console.db.

    Returns (findings, missing_sources). `missing_sources` is the list of
    auditor tables where 0 rows exist for this feat — informational, used
    by the Markdown report.
    """
    findings: list[Finding] = []
    sources_present: set[str] = set()

    with connect() as conn:
        # v7.0.0 P0 C3 fix : presence is determined by auditor_runs (one row
        # per invocation, regardless of findings count). Counting rows in the
        # per-finding tables produced false-positive [REVIEW_SOURCES_MISSING]
        # on clean scans (0 findings = no row inserted). The findings loops
        # below still add to sources_present opportunistically — that path
        # remains correct for any auditor that produced ≥ 1 finding even if
        # it forgot to call record_auditor_run() (forward-compat).
        try:
            for row in conn.execute(
                "SELECT DISTINCT auditor FROM auditor_runs WHERE feat_n=?", (feat_n,)
            ):
                sources_present.add(row[0])
        except sqlite3.OperationalError:
            # Table not yet created (DB pre-migration). Fall back to legacy
            # inference from findings rows only — same behavior as v6.x.
            pass

        conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}

        # qa_quality (deterministic scan)
        for row in conn.execute(
            "SELECT severity, issue_class, rule, file_path, line, message "
            "FROM qa_quality WHERE feat_n=?", (feat_n,)
        ):
            sources_present.add("quality")
            findings.append(Finding(
                source="quality",
                issue_class=row["issue_class"] or row["rule"] or "QUALITY",
                severity=_norm_sev(row["severity"], "quality"),
                rule=row["rule"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_code_review (LLM) — split by issue_class prefix:
        #   ARCH_* → source "arch" (emitted by arch-reviewer)
        #   *      → source "code-review" (emitted by code-reviewer)
        for row in _select_with_detector(
            conn, "SELECT severity, issue_class, file_path, line, message",
            "FROM qa_code_review WHERE feat_n=?", (feat_n,)
        ):
            cls = (row["issue_class"] or "").strip()
            is_arch = cls.startswith("ARCH_") or cls.startswith("[ARCH_")
            src = "arch" if is_arch else "code-review"
            if _is_agent_row(row):
                sources_present.add(src)
            findings.append(Finding(
                source=src,
                issue_class=cls or "REVIEW",
                severity=_norm_sev(row["severity"], src),
                rule=None,
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_security
        for row in _select_with_detector(
            conn, "SELECT severity, issue_class, file_path, line, message, mode, owasp, cwe",
            "FROM qa_security WHERE feat_n=? AND (mode IS NULL OR mode='scan')", (feat_n,)
        ):
            if _is_agent_row(row):
                sources_present.add("security")
            findings.append(Finding(
                source="security",
                issue_class=row["issue_class"],
                severity=_norm_sev(row["severity"], "security"),
                rule=row["owasp"] or row["cwe"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_a11y
        for row in conn.execute(
            "SELECT severity, issue_class, file_path, line, message, wcag "
            "FROM qa_a11y WHERE feat_n=?", (feat_n,)
        ):
            sources_present.add("a11y")
            findings.append(Finding(
                source="a11y",
                issue_class=row["issue_class"],
                severity=_norm_sev(row["severity"], "a11y"),
                rule=row["wcag"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_performance
        for row in conn.execute(
            "SELECT severity, issue_class, file_path, line, message, metric "
            "FROM qa_performance WHERE feat_n=?", (feat_n,)
        ):
            sources_present.add("perf")
            findings.append(Finding(
                source="perf",
                issue_class=row["issue_class"],
                severity=_norm_sev(row["severity"], "perf"),
                rule=row["metric"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_spec_compliance
        for row in conn.execute(
            "SELECT severity, us_id, ac_id, verdict, evidence_file, evidence_line, message "
            "FROM qa_spec_compliance WHERE feat_n=? AND verdict != 'verified'", (feat_n,)
        ):
            sources_present.add("spec")
            findings.append(Finding(
                source="spec",
                issue_class=f"SPEC_{(row['verdict'] or 'not_verified').upper()}",
                severity=_norm_sev(row["severity"], "spec"),
                rule=f"{row['us_id']}/{row['ac_id']}",
                file_path=row["evidence_file"],
                line=row["evidence_line"],
                message=row["message"],
            ))

    all_sources = {"quality", "code-review", "security", "a11y", "perf", "spec", "arch"}
    missing = sorted(all_sources - sources_present)
    return findings, missing


#: Leading `./`, repeated. A prefix strip — NOT `lstrip("./")`, which strips a
#: character set and eats any leading dot (audit M12, 2026-08-29).
_LEADING_DOT_SLASH_RE = re.compile(r"^(?:\./)+")

#: Repo prefixes stripped so paths from different auditor scopes converge.
#: Order matters — longest first.
_PATH_PREFIXES: tuple[str, ...] = (
    "workspace/src/",
    "workspace/",
    "src/",
)


def _segment_prefix_index(s: str, prefix: str) -> int | None:
    """Index of `prefix` in `s` where it starts a path SEGMENT, else None.

    Audit M12 — a plain `s.find("src/")` matches mid-segment, so
    `mysrc/Auth.cs` normalized to the same key as `src/Auth.cs` and one of
    the two findings was silently dropped by the dedup pass.
    """
    start = 0
    while True:
        idx = s.find(prefix, start)
        if idx < 0:
            return None
        if idx == 0 or s[idx - 1] == "/":
            return idx
        start = idx + 1


def _normalize_path(p: str | None) -> str:
    """v7.0.0 audit §6.R3 — normalize finding file paths for cross-source dedup.

    Auditors emit paths in different formats :
      - `code-reviewer` may emit `workspace/src/X/Auth.cs` (full repo-relative)
      - `security-reviewer` may emit `src/X/Auth.cs` (project-relative)
      - `arch-reviewer` may emit `X/Auth.cs` (module-relative)
      - Some use backslashes on Windows, others forward slashes

    Without normalization, `(file_path, line)` keys diverge → dedup rate
    silently → verdict consolidated inflated. This function returns a
    canonical form : lowercased, forward-slashes, leading-stripped of
    common prefixes (`workspace/`, `./`, project root segments).

    Idempotent. Empty input → empty string.
    """
    if not p:
        return ""
    # Normalize separators + strip redundant slashes.
    #
    # Audit M12 (2026-08-29) — the leading `./` strip used to be
    # `s.lstrip("./")`, which removes a *character set*, not a prefix: every
    # leading `.` and `/` in any order disappears. `.sdd/x` became `sdd/x`
    # and, worse, any path whose first characters are dots/slashes lost them
    # silently. Combined with the substring `find()` below (kept: it is what
    # lets an absolute path converge with a relative one), unrelated files
    # collided on the same dedup key and the lower-severity finding was
    # dropped without trace. `^(\./)+` strips exactly what was intended.
    s = _LEADING_DOT_SLASH_RE.sub("", p.replace("\\", "/")).lower()
    while "//" in s:
        s = s.replace("//", "/")
    # Strip well-known repo prefixes so paths from different scopes converge.
    #
    # Audit M12 — anchored on a SEGMENT boundary. `find("src/")` matched
    # mid-segment, so `mysrc/Auth.cs` was treated as `src/Auth.cs`: two
    # unrelated files, one dedup key, one finding silently discarded. The
    # prefix must start the string or follow a `/`.
    for prefix in _PATH_PREFIXES:
        idx = _segment_prefix_index(s, prefix)
        if idx is not None:
            # Keep everything from the first match of the prefix forward
            # (this handles both absolute paths and relative ones uniformly)
            s = s[idx + len(prefix):]
            break
    return s.strip("/")


def deduplicate_findings(findings: list[Finding]) -> tuple[list[Finding], int]:
    """v7.0.0 audit §6.10 + R3 fix 2026-05-20 — cross-source dedup on
    (normalized_path, line, canonical_class).

    Auditors overlap on a few well-known classes :
      - `[REVIEW_SECRETS_HARDCODED]` (code-reviewer) ≈ `[SEC_SECRET_HARDCODED]` (security)
      - `[LAYER_VIOLATION]` (code-reviewer §5.2) ≈ `[ARCH_LAYER_BYPASS]` (arch-reviewer §5.2)
      - `[REVIEW_ANTI_PATTERN_N_PLUS_ONE]` (code-reviewer) ≈ `[PERF_N_PLUS_ONE_RISK]` (legacy)

    Without dedup, the same file:line gets counted twice in the consolidated
    report, inflating the verdict severity. This function groups by
    (normalized_path, line, canonical_class) — keeps the finding with the
    HIGHEST severity (most specific), drops duplicates.

    R3 fix : key uses `_normalize_path(file_path)` instead of raw file_path,
    so reviewers emitting paths at different prefixes (full repo-relative
    vs project-relative vs module-relative) still get deduplicated.

    Returns (deduplicated_findings, suppressed_count).
    """
    # Canonical class mapping — maps overlapping classes to a single key
    CANONICAL_CLASS = {
        # secrets hardcoded duo
        "REVIEW_SECRETS_HARDCODED": "SECRET_HARDCODED",
        "SEC_SECRET_HARDCODED":      "SECRET_HARDCODED",
        # layer violation duo
        "LAYER_VIOLATION":      "LAYER_VIOLATION_GROUP",
        "ARCH_LAYER_BYPASS":    "LAYER_VIOLATION_GROUP",
        "ARCH_PATTERN_VIOLATION": "LAYER_VIOLATION_GROUP",
        # N+1 query duo
        "REVIEW_ANTI_PATTERN_N_PLUS_ONE": "N_PLUS_ONE_GROUP",
        "PERF_N_PLUS_ONE_RISK":           "N_PLUS_ONE_GROUP",
    }

    def canonical_key(f: Finding) -> tuple:
        # Group key : normalized file + line + canonical class
        cls = f.issue_class or ""
        canonical = CANONICAL_CLASS.get(cls.strip("[]"), cls)
        return (_normalize_path(f.file_path), f.line or 0, canonical)

    groups: dict[tuple, list[Finding]] = {}
    for f in findings:
        groups.setdefault(canonical_key(f), []).append(f)

    deduped: list[Finding] = []
    suppressed = 0
    for key, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        # Keep the highest-severity, then alphabetical source for determinism
        group.sort(
            key=lambda f: (-SEVERITY_RANK.get(f.severity, 0), f.source),
        )
        deduped.append(group[0])
        suppressed += len(group) - 1

    return deduped, suppressed
