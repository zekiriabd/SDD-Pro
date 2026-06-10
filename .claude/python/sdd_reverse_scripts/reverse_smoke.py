"""reverse_smoke.py — Enforcer for INVARIANTS.reverse.yml (ADV-7).

Per design doc §15.1. Runs deterministic checks against the reverse workflow
invariants. NOT plugged into framework_smoke.py (D4 isolation strict) —
the Tech Lead runs this manually OR via CI when the reverse workflow is in
use.

Invocation:
    python -m sdd_reverse_scripts.reverse_smoke [--json]

Exit codes:
    0  all invariants OK (warnings tolerated)
    1  ≥ 1 invariant violated (hard fail)

Output format mirrors framework_smoke.py for visual consistency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class CheckResult:
    name: str
    status: str   # OK | WARN | FAIL
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def check_isolation_no_cross_imports() -> CheckResult:
    """sdd_reverse/* MUST NOT import from sdd_lib, sdd_scripts, sdd_admin, sdd_hooks."""
    sdd_reverse = REPO_ROOT / ".claude" / "python" / "sdd_reverse"
    bad_patterns = [
        re.compile(r"^\s*from\s+sdd_lib\b"),
        re.compile(r"^\s*import\s+sdd_lib\b"),
        re.compile(r"^\s*from\s+sdd_scripts\b"),
        re.compile(r"^\s*import\s+sdd_scripts\b"),
        re.compile(r"^\s*from\s+sdd_admin\b"),
        re.compile(r"^\s*import\s+sdd_admin\b"),
        re.compile(r"^\s*from\s+sdd_hooks\b"),
        re.compile(r"^\s*import\s+sdd_hooks\b"),
    ]
    violations: list[str] = []
    for p in sdd_reverse.rglob("*.py"):
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            for pat in bad_patterns:
                if pat.match(line):
                    violations.append(f"{p.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}")
    if violations:
        return CheckResult(
            "reverse-isolation-no-cross-imports", "FAIL",
            f"{len(violations)} cross-import(s) detected (D4 violation)",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-isolation-no-cross-imports", "OK")


def check_loader_autonomous() -> CheckResult:
    """loader.reverse.yml referenced ONLY by reverse commands/skill, NEVER by loader.yml."""
    loader_yml = REPO_ROOT / ".claude" / "loader.yml"
    if loader_yml.is_file():
        try:
            content = loader_yml.read_text(encoding="utf-8")
            if "loader.reverse.yml" in content or "loader.reverse" in content:
                return CheckResult(
                    "reverse-loader-autonomous", "FAIL",
                    "loader.yml references loader.reverse.yml (D4 violation)",
                )
        except OSError:
            pass
    return CheckResult("reverse-loader-autonomous", "OK")


def check_inventory_schema_v1() -> CheckResult:
    """All inventory.json under workspace/old/*/.sys/ MUST be schemaVersion==1 with required keys."""
    workspace_old = REPO_ROOT / "workspace" / "old"
    if not workspace_old.is_dir():
        return CheckResult("reverse-inventory-schema-v1", "OK", "(no workspace/old/ found)")
    violations: list[str] = []
    for inv in workspace_old.rglob(".sys/inventory.json"):
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            violations.append(f"{inv.relative_to(REPO_ROOT)}: unparseable")
            continue
        rel = str(inv.relative_to(REPO_ROOT))
        if data.get("schemaVersion") != 1:
            violations.append(f"{rel}: schemaVersion != 1")
        if "_allocatedNames" not in data:
            violations.append(f"{rel}: _allocatedNames missing (ADV-23)")
        if "_featAllocations" not in data:
            violations.append(f"{rel}: _featAllocations missing (ADV-23)")
    if violations:
        return CheckResult(
            "reverse-inventory-schema-v1", "WARN",
            f"{len(violations)} inventory issue(s) — refresh recommended",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-inventory-schema-v1", "OK")


def check_db_schema_enrichment_separate() -> CheckResult:
    """Verify db-schema.enrichment.json exists separately when audit ran (no merge directly into base)."""
    workspace_old = REPO_ROOT / "workspace" / "old"
    if not workspace_old.is_dir():
        return CheckResult("reverse-db-schema-enrichment-separate", "OK", "(no workspace/old/ found)")
    issues: list[str] = []
    for tech_audit in workspace_old.rglob(".sys/tech-audit.md"):
        sys_dir = tech_audit.parent
        enrich = sys_dir / "db-schema.enrichment.json"
        base = sys_dir / "db-schema.json"
        if tech_audit.is_file() and not enrich.is_file() and base.is_file():
            # Audit ran but no enrichment.json → could mean nothing to enrich (acceptable)
            # OR auditor wrote to base directly (violation).
            # Best-effort: WARN to flag for review.
            issues.append(f"{tech_audit.parent.relative_to(REPO_ROOT)}: audit ran but no enrichment.json — review")
    if issues:
        return CheckResult(
            "reverse-db-schema-enrichment-separate", "WARN",
            f"{len(issues)} project(s) need review",
            {"projects": issues[:5]},
        )
    return CheckResult("reverse-db-schema-enrichment-separate", "OK")


def check_template_isolated() -> CheckResult:
    """feat.reverse.template.md must exist in sdd_reverse/, not be a symlink to .claude/templates/."""
    template = REPO_ROOT / ".claude" / "python" / "sdd_reverse" / "feat.reverse.template.md"
    if not template.is_file():
        return CheckResult(
            "reverse-template-isolated", "FAIL",
            "feat.reverse.template.md missing — ADV-9 violation (no fallback inline allowed)",
        )
    if template.is_symlink():
        return CheckResult(
            "reverse-template-isolated", "FAIL",
            "feat.reverse.template.md is a symlink — ADV-9 requires a deliberate local copy",
        )
    return CheckResult("reverse-template-isolated", "OK")


def check_helper_parity_drift() -> CheckResult:
    """Compare sdd_lib/atomic_write.py + file_locks.py hashes to snapshots (informational WARN)."""
    snap_path = REPO_ROOT / ".claude" / "python" / "sdd_reverse" / "_parity_snapshots.json"
    if not snap_path.is_file():
        return CheckResult("helper-parity-drift", "WARN", "_parity_snapshots.json absent")
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult("helper-parity-drift", "WARN", f"snapshots unreadable: {e}")
    drifts: list[str] = []
    for rel_path, snap_hash in (snap.get("snapshots") or {}).items():
        target = REPO_ROOT / ".claude" / "python" / rel_path
        if not target.is_file():
            drifts.append(f"{rel_path}: file missing (was present at snapshot time)")
            continue
        current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if snap_hash and current_hash != snap_hash:
            drifts.append(f"{rel_path}: hash changed (snap={snap_hash[:12]}... current={current_hash[:12]}...)")
    if drifts:
        return CheckResult(
            "helper-parity-drift", "WARN",
            f"{len(drifts)} helper(s) drifted upstream — review local copies",
            {"drifts": drifts},
        )
    return CheckResult("helper-parity-drift", "OK")


# ---------------------------------------------------------------------------
# P1.6 closure — direct checks for invariants previously delegated to
# validate_reverse_feat.py. Smoke now enforces them STANDALONE so a missing
# /sdd-reverse run doesn't silently mask malformed FEATs already committed.
# ---------------------------------------------------------------------------

_REVERSE_FEAT_FRONTMATTER_CONFIDENCE = re.compile(
    r"^---\s*$.*?^confidence:\s*(\S+)\s*$.*?^---\s*$",
    re.MULTILINE | re.DOTALL,
)
_REVERSE_GATE_COMMENT = re.compile(
    r"<!--\s*REVERSE-GATE:\s*confidence=(\w+)\s*(?:;\s*allow-sdd-full=(\w+))?\s*-->",
)
_REVERSE_FEAT_GENERATED_BY = re.compile(
    r"^generated-by:\s*sdd-reverse\b", re.MULTILINE,
)
_VALID_CONFIDENCE = {"high", "medium", "low"}
# Section headings in a FEAT that introduce items requiring an evidence comment
_EVIDENCE_REQUIRED_HEADINGS = (
    "## Functional Needs",
    "## Functional Deliverables",
    "## Business Rules",
    "## Acceptance Criteria",
)
_EVIDENCE_COMMENT_RE = re.compile(r"<!--\s*evidence:\s*[^>]+-->")
_ITEM_ID_RE = re.compile(r"^\s*-?\s*\*?\*?(SFD|FD|BR|AC)-\d+", re.MULTILINE)


def _iter_reverse_feats() -> list[Path]:
    """Return FEAT files under workspace/input/feats/ that look reverse-generated."""
    feats_dir = REPO_ROOT / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        return []
    out: list[Path] = []
    for f in feats_dir.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _REVERSE_FEAT_GENERATED_BY.search(text):
            out.append(f)
    return out


def check_reverse_evidence_required() -> CheckResult:
    """INVARIANT #3 reverse-evidence-required — every SFD/FD/BR/AC item in a
    reverse FEAT must carry an `<!-- evidence: ... -->` comment nearby.

    Heuristic: for each section heading in `_EVIDENCE_REQUIRED_HEADINGS`,
    count the number of item IDs vs the number of evidence comments in
    the same section. Mismatch → WARN with file pointer.
    """
    feats = _iter_reverse_feats()
    if not feats:
        return CheckResult(
            "reverse-evidence-required", "OK",
            "(no reverse-generated FEATs found)",
        )
    issues: list[str] = []
    for f in feats:
        text = f.read_text(encoding="utf-8", errors="replace")
        # Slice the text by section
        sections: list[tuple[str, str]] = []
        current_heading: str | None = None
        current_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("## "):
                if current_heading is not None:
                    sections.append((current_heading, "\n".join(current_lines)))
                current_heading = line.strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_heading is not None:
            sections.append((current_heading, "\n".join(current_lines)))

        for heading, body in sections:
            if heading not in _EVIDENCE_REQUIRED_HEADINGS:
                continue
            items = _ITEM_ID_RE.findall(body)
            evidence_count = len(_EVIDENCE_COMMENT_RE.findall(body))
            if items and evidence_count < len(items):
                issues.append(
                    f"{f.relative_to(REPO_ROOT)} [{heading}]: "
                    f"{len(items)} items, {evidence_count} evidence comments"
                )
    if issues:
        return CheckResult(
            "reverse-evidence-required", "WARN",
            f"{len(issues)} section(s) missing evidence",
            {"issues": issues[:10]},
        )
    return CheckResult("reverse-evidence-required", "OK")


def check_reverse_confidence_enum_strict() -> CheckResult:
    """INVARIANT #4 reverse-confidence-enum-strict — confidence values in
    frontmatter AND in inline `<!-- confidence: X -->` comments must be one
    of {high, medium, low} (lowercase, no quotes). Any other value = FAIL.
    """
    feats = _iter_reverse_feats()
    if not feats:
        return CheckResult(
            "reverse-confidence-enum-strict", "OK",
            "(no reverse-generated FEATs found)",
        )
    violations: list[str] = []
    inline_re = re.compile(r"<!--\s*confidence:\s*(\S+?)\s*-->")
    for f in feats:
        text = f.read_text(encoding="utf-8", errors="replace")
        # Frontmatter
        m = _REVERSE_FEAT_FRONTMATTER_CONFIDENCE.search(text)
        if m:
            val = m.group(1).strip().strip('"').strip("'").lower()
            if val not in _VALID_CONFIDENCE:
                violations.append(
                    f"{f.relative_to(REPO_ROOT)} frontmatter: confidence={val!r}"
                )
        else:
            violations.append(
                f"{f.relative_to(REPO_ROOT)}: frontmatter.confidence missing"
            )
        # Inline comments
        for inline_m in inline_re.finditer(text):
            val = inline_m.group(1).strip('"').strip("'").lower()
            if val not in _VALID_CONFIDENCE:
                violations.append(
                    f"{f.relative_to(REPO_ROOT)} inline comment: confidence={val!r}"
                )
    if violations:
        return CheckResult(
            "reverse-confidence-enum-strict", "FAIL",
            f"{len(violations)} invalid confidence value(s)",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-confidence-enum-strict", "OK")


def check_reverse_gate_comment_sync() -> CheckResult:
    """INVARIANT #5 reverse-gate-comment-sync — the
    `<!-- REVERSE-GATE: confidence=X ... -->` comment must match
    `frontmatter.confidence`. Desync = REVERSE_GATE_DRIFT (ADV-22).
    """
    feats = _iter_reverse_feats()
    if not feats:
        return CheckResult(
            "reverse-gate-comment-sync", "OK",
            "(no reverse-generated FEATs found)",
        )
    drifts: list[str] = []
    for f in feats:
        text = f.read_text(encoding="utf-8", errors="replace")
        fm_m = _REVERSE_FEAT_FRONTMATTER_CONFIDENCE.search(text)
        gate_m = _REVERSE_GATE_COMMENT.search(text)
        if fm_m is None or gate_m is None:
            # Missing either → reported by other checks (evidence/enum)
            continue
        fm_val = fm_m.group(1).strip().strip('"').strip("'").lower()
        gate_val = gate_m.group(1).strip().lower()
        if fm_val != gate_val:
            drifts.append(
                f"{f.relative_to(REPO_ROOT)}: frontmatter={fm_val!r} ≠ gate={gate_val!r}"
            )
    if drifts:
        return CheckResult(
            "reverse-gate-comment-sync", "FAIL",
            f"{len(drifts)} FEAT(s) with frontmatter/gate drift (ADV-22)",
            {"drifts": drifts[:10]},
        )
    return CheckResult("reverse-gate-comment-sync", "OK")


def check_validator_parity_drift() -> CheckResult:
    """DRIFT CHECK #1 validator-parity-drift — verify that
    `validate_reverse_feat.py` declares the required `REQUIRED_SECTIONS`
    constants and a `validate_reverse_feat` entry point (sanity guard
    against accidental deletion / refactor that would silently disable
    enforcement of invariants #3-#5).
    """
    validator = REPO_ROOT / ".claude" / "python" / "sdd_reverse_scripts" / "validate_reverse_feat.py"
    if not validator.is_file():
        return CheckResult(
            "validator-parity-drift", "FAIL",
            "validate_reverse_feat.py missing — invariants #3-#5 lose their direct enforcer",
        )
    src = validator.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    # Sanity markers (presence-only, not semantic equivalence)
    for marker in (
        "REQUIRED_SECTIONS",
        "REQUIRED_FRONTMATTER_KEYS_REVERSE",
        "REVERSE-GATE",
        "evidence",
    ):
        if marker not in src:
            missing.append(marker)
    if missing:
        return CheckResult(
            "validator-parity-drift", "WARN",
            f"validate_reverse_feat.py lacks expected markers: {missing}",
        )
    return CheckResult("validator-parity-drift", "OK")


def check_lock_format() -> CheckResult:
    """If .alloc.lock exists, validate its JSON shape (informational)."""
    lock = REPO_ROOT / "workspace" / "input" / "feats" / ".alloc.lock"
    if not lock.is_file():
        return CheckResult("reverse-lock-format-valid", "OK", "(no active lock)")
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CheckResult(
            "reverse-lock-format-valid", "WARN",
            ".alloc.lock present but unparseable (will be overwritten as stale on next acquire)",
        )
    required = {"agent_id", "pid", "ts_unix", "host"}
    missing = required - set(data.keys())
    if missing:
        return CheckResult(
            "reverse-lock-format-valid", "FAIL",
            f".alloc.lock missing required keys: {sorted(missing)}",
        )
    return CheckResult("reverse-lock-format-valid", "OK")


_ALL_CHECKS = [
    check_isolation_no_cross_imports,
    check_loader_autonomous,
    check_inventory_schema_v1,
    check_db_schema_enrichment_separate,
    check_template_isolated,
    check_helper_parity_drift,
    check_lock_format,
    # P1.6 closure (2026-06-10) — direct enforcement of invariants
    # previously delegated to validate_reverse_feat.py
    check_reverse_evidence_required,
    check_reverse_confidence_enum_strict,
    check_reverse_gate_comment_sync,
    check_validator_parity_drift,
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reverse_smoke",
        description="Enforcer for INVARIANTS.reverse.yml (ADV-7 closure).",
    )
    parser.add_argument("--json", action="store_true", help="Emit report as JSON")
    args = parser.parse_args(argv)

    results = [check() for check in _ALL_CHECKS]
    ok_count = sum(1 for r in results if r.status == "OK")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    if args.json:
        print(json.dumps({
            "ok": fail_count == 0,
            "summary": {"OK": ok_count, "WARN": warn_count, "FAIL": fail_count, "total": len(results)},
            "checks": [
                {"name": r.name, "status": r.status, "message": r.message, "details": r.details}
                for r in results
            ],
        }, ensure_ascii=False))
    else:
        print("=== Reverse Engineering Invariants Smoke ===")
        for r in results:
            # ASCII icons (Windows cp1252 console compatibility)
            icon = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(r.status, "[??]")
            line = f"  {icon} {r.name}"
            if r.message:
                line += f" — {r.message}"
            print(line)
            for k, v in r.details.items():
                if isinstance(v, list):
                    for item in v[:5]:
                        print(f"        • {item}")
        print()
        print(f"Summary: OK={ok_count}  WARN={warn_count}  FAIL={fail_count}  total={len(results)}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
