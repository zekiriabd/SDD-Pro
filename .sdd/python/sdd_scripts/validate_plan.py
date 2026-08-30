#!/usr/bin/env python3
"""SDD_Pro Plan validator — From-Plan Strict gate (v6.2).

Validates `workspace/plans/{n}-{m}-{Name}.{back|front}.md` files
for structure, coherence, and staleness vs source US.

Validation (single layer — strict mode retired, audit M5 2026-08-29):

  - YAML frontmatter parseable
  - Mandatory fields present: `us`, `family`
  - `## Files` section with entries
  - Each file entry has: `path`, `operation` (create|augment), `layer`,
    `covers_acs`
  - `augment` operations have both `preserves:` and `adds:` keys
  - `us-hash` matches the current US SHA256 (if `--us-path`) → `[PLAN_STALE]`
  - `## ACs Coverage Summary` covers every AC-N declared in the US
    → `[PLAN_AC_COVERAGE_GAP]`
  - informational: `plan-schema-version`, `## Inline Digest` presence,
    `claude-md-hash` drift (warnings only, never exit codes)

Usage:
    validate_plan.py --plan-path PATH [--us-path PATH] [--claude-md-path PATH]
                     [--json]

Output (default): human-readable summary on stdout.
Output (`--json`): single line of structured JSON on stdout.

Exit codes:
    0 = plan valide (voir `warnings[]` pour les signaux non bloquants :
        digest absent, fraîcheur invérifiable, couverture AC absente)
    2 = plan is invalid / corrupted / stale
        → callers must STOP + ERROR [PLAN_INVALID] or [PLAN_STALE]

    Exit 1 (`[PLAN_NOT_STRICT_READY]`) est RETIRÉ — audit M5 2026-08-29. Il
    n'était produit que par `validate_strict()`, gate des agents
    `dev-*-strict` supprimés en v7.0.0, donc inatteignable dans toutes les
    invocations documentées (aucune ne passait `--strict`). Le flag
    `--strict` reste accepté en no-op pour ne pas casser un script ancien.

Conventions (cf. `.sdd/python/README.md`):
- Python 3.10+ stdlib only (no external deps)
- Deterministic (0 token LLM)
- Cross-platform paths (use sdd_lib.paths.normalize)
- Canonical ERROR format on stderr via sdd_lib.stderr.error_block

Related:
- `@.claude/archive/v7-design-superseded/DESIGN-FROMPLAN-STRICT.md` (design)
- `@.sdd/rules/build-and-loop.md §7` (plan structure spec)
- `@.sdd/rules/error-classification.md` (PLAN_* codes)
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.markdown_io import (  # noqa: E402
    parse_frontmatter,
    section_body_stripped as extract_section_body,
)
from sdd_lib.paths import normalize  # noqa: E402
from sdd_lib.stderr import error_block  # noqa: E402


#: Retired with strict mode (audit M5, 2026-08-29) — kept as a named constant
#: because `## Inline Digest`-bearing plans are still called "v2" in the docs.
SCHEMA_VERSION_V2 = 2
ERR_CLASSES = {
    "PLAN_NOT_FOUND": 2,
    "PLAN_UNREADABLE": 2,
    "PLAN_NO_FRONTMATTER": 2,
    "PLAN_FRONTMATTER_INVALID": 2,
    "PLAN_MISSING_REQUIRED_FIELD": 2,
    "PLAN_FILES_SECTION_MISSING": 2,
    "PLAN_FILE_ENTRY_INVALID": 2,
    "PLAN_AUGMENT_CONTRACT_MISSING": 2,
    "PLAN_AC_COVERAGE_GAP": 2,
    "PLAN_STALE": 2,
    # `PLAN_NOT_STRICT_READY` (exit 1) retired — audit M5, 2026-08-29.
    # Exit 1 is no longer reachable: strict mode gated the `dev-*-strict`
    # agents deleted in v7.0.0, so the only code path that produced it was
    # unreachable in every documented invocation.
}


@dataclass
class FileEntry:
    path: str
    operation: str  # 'create' | 'augment'
    layer: str
    covers_acs: list[str] = field(default_factory=list)
    preserves: list[str] = field(default_factory=list)
    adds: list[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class PlanReport:
    plan_path: str
    us_path: str | None
    strict_mode: bool
    result: str = "unknown"  # 'ready' | 'not_strict_ready' | 'invalid'
    exit_code: int = 0
    schema_version: int = 1
    frontmatter: dict[str, str] = field(default_factory=dict)
    files: list[FileEntry] = field(default_factory=list)
    us_hash_match: bool | None = None
    claude_md_hash_match: bool | None = None
    inline_digest_present: bool = False
    ac_coverage: dict[str, list[str]] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "plan_path": self.plan_path,
            "us_path": self.us_path,
            "strict_mode": self.strict_mode,
            "result": self.result,
            "exit_code": self.exit_code,
            "schema_version": self.schema_version,
            "frontmatter": self.frontmatter,
            "files_count": len(self.files),
            "us_hash_match": self.us_hash_match,
            "claude_md_hash_match": self.claude_md_hash_match,
            "inline_digest_present": self.inline_digest_present,
            "ac_coverage_acs": sorted(self.ac_coverage.keys()),
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def add_error(self, code: str, hint: str) -> None:
        self.errors.append({"code": code, "hint": hint})
        candidate = ERR_CLASSES.get(code, 2)
        if candidate > self.exit_code:
            self.exit_code = candidate

    def add_warning(self, code: str, hint: str) -> None:
        self.warnings.append({"code": code, "hint": hint})


# Frontmatter / section parsing now delegated to sdd_lib.markdown_io
# (v7.0.0-alpha, audit CRIT-3 — SSoT consolidation).
_FILE_ENTRY_PATH_RE = re.compile(r"^-\s*path\s*:\s*(.+?)\s*$", re.MULTILINE)
_FILE_ENTRY_FIELD_RE = re.compile(r"^\s+([a-zA-Z_]+)\s*:\s*(.+?)\s*$")
_LIST_INLINE_RE = re.compile(r"^\s*\[\s*(.*?)\s*\]\s*$")
_SECTION_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_AC_REF_RE = re.compile(r"\bAC(?:-UI)?-\d+\b")


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate a SDD_Pro plan file for structure + strict-readiness.",
    )
    p.add_argument("--plan-path", required=True, help="Path to .back.md or .front.md plan")
    p.add_argument("--us-path", default=None, help="Path to source US (for us-hash check)")
    p.add_argument("--claude-md-path", default=None, help="Path to project CLAUDE.md (for hash check)")
    p.add_argument(
        "--strict", action="store_true",
        help="RETIRÉ (audit M5, 2026-08-29) — no-op accepté pour "
             "backward-compat. Le mode strict gatait les agents dev-*-strict, "
             "supprimés en v7.0.0 ; ses checks utiles sont désormais always-on.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON output on stdout")
    p.add_argument("--workspace-root", default=None, help="Override repo root (testing)")
    return p.parse_args()


def parse_inline_list(raw: str) -> list[str]:
    """Parse `[a, b, c]` or `a, b, c` or `a` into a list of trimmed strings."""
    s = raw.strip()
    m = _LIST_INLINE_RE.match(s)
    if m:
        s = m.group(1)
    if not s:
        return []
    return [tok.strip().strip('"').strip("'") for tok in s.split(",") if tok.strip()]


def parse_files_section(body: str) -> list[FileEntry]:
    """Parse `## Files` section into a list of FileEntry.

    Format expected:
        - path: src/foo.cs
          operation: create
          layer: Service
          covers_acs: [AC-1, AC-2]

        - path: src/bar.cs
          operation: augment
          layer: Service
          preserves: [AuthService.ExistingMethod]
          adds: [AuthService.NewMethod]
          covers_acs: [AC-3]
    """
    section = extract_section_body(body, "Files")
    if section is None:
        return []

    entries: list[FileEntry] = []
    lines = section.splitlines()
    current: FileEntry | None = None
    for idx, line in enumerate(lines, start=1):
        path_match = _FILE_ENTRY_PATH_RE.match(line.lstrip())
        if path_match:
            if current is not None:
                entries.append(current)
            current = FileEntry(
                path=path_match.group(1).strip(),
                operation="",
                layer="",
                line_number=idx,
            )
            continue
        if current is None:
            continue
        field_match = _FILE_ENTRY_FIELD_RE.match(line)
        if not field_match:
            continue
        key, raw_value = field_match.group(1), field_match.group(2)
        if key == "operation":
            current.operation = raw_value.strip()
        elif key == "layer":
            current.layer = raw_value.strip()
        elif key == "covers_acs":
            current.covers_acs = parse_inline_list(raw_value)
        elif key == "preserves":
            current.preserves = parse_inline_list(raw_value)
        elif key == "adds":
            current.adds = parse_inline_list(raw_value)
    if current is not None:
        entries.append(current)
    return entries


def parse_ac_coverage(body: str) -> dict[str, list[str]]:
    """Parse `## ACs Coverage Summary` markdown table into AC -> [files]."""
    section = extract_section_body(body, "ACs Coverage Summary")
    if section is None:
        return {}
    coverage: dict[str, list[str]] = {}
    for line in section.splitlines():
        if not line.strip() or line.lstrip().startswith("|--"):
            continue
        if not line.lstrip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 2:
            continue
        ac, files_str = parts[0], parts[1]
        if not _AC_REF_RE.match(ac):
            continue
        files = [f.strip() for f in files_str.split(",") if f.strip()]
        coverage[ac] = files
    return coverage


def extract_us_acs(us_text: str) -> list[str]:
    """Extract AC-N (and AC-UI-N) identifiers from an US file."""
    section = extract_section_body(us_text, "Acceptance Criteria")
    if section is None:
        # Try alternate heading
        section = extract_section_body(us_text, "Acceptance Criteria (Backend)")
    if section is None:
        return []
    return sorted(set(_AC_REF_RE.findall(section)))


def validate_structural(body: str, report: PlanReport) -> None:
    """Apply structural validations (exit 2 if any fail)."""
    required = ("us", "family")
    for key in required:
        if key not in report.frontmatter:
            report.add_error(
                "PLAN_MISSING_REQUIRED_FIELD",
                f"frontmatter field `{key}` absent",
            )

    files = parse_files_section(body)
    report.files = files
    if not files:
        report.add_error(
            "PLAN_FILES_SECTION_MISSING",
            "section `## Files` absente ou vide",
        )
        return

    for entry in files:
        if not entry.path:
            report.add_error(
                "PLAN_FILE_ENTRY_INVALID",
                f"file entry line {entry.line_number}: path manquant",
            )
        if entry.operation not in ("create", "augment"):
            report.add_error(
                "PLAN_FILE_ENTRY_INVALID",
                f"{entry.path}: operation manquante ou invalide (attendu: create|augment)",
            )
        if not entry.layer:
            report.add_error(
                "PLAN_FILE_ENTRY_INVALID",
                f"{entry.path}: layer manquant",
            )
        if not entry.covers_acs:
            report.add_error(
                "PLAN_FILE_ENTRY_INVALID",
                f"{entry.path}: covers_acs manquant ou vide",
            )
        if entry.operation == "augment":
            if not entry.preserves and not entry.adds:
                report.add_error(
                    "PLAN_AUGMENT_CONTRACT_MISSING",
                    f"{entry.path}: operation=augment requiert preserves: et/ou adds:",
                )


def validate_staleness(report: PlanReport, us_path: Path | None) -> None:
    """Always-applied staleness gate: a plan whose declared `us-hash` no longer
    matches its source US is STALE (exit 2 → `[PLAN_STALE]`), regardless of
    `--strict`.

    Audit fix 2026-06-12 (M3) — this check previously lived only inside
    `validate_strict()` (run `if args.strict`), but `/dev-run` STEP 6.0.bis
    invokes the validator WITHOUT `--strict` and its action table expects exit 2
    on stale. Result: a plan edited after its US changed silently passed exit 0
    and dev-* materialized against a stale plan. Backward-compatible: a v1 plan
    with no `us-hash` field simply skips the check (no false positive).
    """
    us_hash_decl = report.frontmatter.get("us-hash", "")
    if not us_hash_decl:
        report.add_warning(
            "PLAN_STALENESS_UNVERIFIABLE",
            "frontmatter `us-hash` absent (plan v1 legacy) — la fraîcheur du "
            "plan vis-à-vis de son US ne peut PAS être vérifiée ; "
            "régénérer via /dev-plan pour obtenir un plan v2 hashé",
        )
        report.us_hash_match = None
        return
    # Audit M6 (2026-08-29) — staleness-UNKNOWN must never look identical to
    # staleness-confirmed-fresh. The pre-fix code returned bare on a missing
    # US path, so a caller reading `exit 0` could not distinguish "the plan
    # is provably in sync" from "nobody could check". Both branches below now
    # leave a visible trace in the report (and on stderr via _emit_output),
    # while staying non-blocking: an unverifiable plan is a warning, only a
    # *proven* mismatch is `[PLAN_STALE]` (exit 2).
    if us_path is None:
        report.add_warning(
            "PLAN_STALENESS_UNVERIFIABLE",
            "aucun --us-path fourni — us-hash déclaré mais non comparé "
            "(fraîcheur du plan INCONNUE, pas 'fraîche')",
        )
        report.us_hash_match = None
        return
    if not us_path.is_file():
        report.add_warning(
            "PLAN_STALENESS_UNVERIFIABLE",
            f"US source introuvable ({normalize(us_path)}) — us-hash déclaré "
            f"mais non comparé (fraîcheur du plan INCONNUE, pas 'fraîche')",
        )
        report.us_hash_match = None
        return
    try:
        us_content = us_path.read_text(encoding="utf-8")
    except OSError as e:
        report.add_warning("PLAN_US_READ_FAILED", f"lecture US impossible : {e}")
        report.us_hash_match = None
        return
    actual = sha256_hex(us_content)
    declared = us_hash_decl.replace("sha256:", "").strip()
    report.us_hash_match = (actual == declared)
    if not report.us_hash_match:
        report.add_error(
            "PLAN_STALE",
            f"us-hash mismatch (plan: {declared[:12]}..., US: {actual[:12]}...) "
            "— regenerer via /dev-plan",
        )


def validate_metadata(body: str, report: PlanReport,
                      claude_md_path: Path | None) -> None:
    """Always-applied metadata pass (schema version, digest, CLAUDE.md drift).

    Audit M5 (2026-08-29) — replaces the retired ``validate_strict()``.

    The strict layer gated the removed ``dev-*-strict`` agent variants
    (v7.0.0, ADR ``governance-major-auditors-trim``). Once those agents were
    deleted, `--strict` became a documented no-op and exit code 1
    (``[PLAN_NOT_STRICT_READY]``) was unreachable in **every** documented
    invocation — while `dev-plan.md` still published an exit-1 row. Rather
    than resurrect strict mode, the layer is retired: the checks that still
    carry information (schema version, digest presence, CLAUDE.md drift)
    become always-on and purely *informational*; the ones that only existed
    to decide strict routing are gone.
    """
    schema_str = report.frontmatter.get("plan-schema-version", "1")
    try:
        report.schema_version = int(schema_str)
    except ValueError:
        report.add_error(
            "PLAN_FRONTMATTER_INVALID",
            f"plan-schema-version doit etre un entier (recu: {schema_str})",
        )
        return

    digest = extract_section_body(body, "Inline Digest")
    report.inline_digest_present = bool(digest and digest.strip())
    if not report.inline_digest_present:
        report.add_warning(
            "PLAN_DIGEST_ABSENT",
            "section `## Inline Digest` absente (plan v1 legacy — utilisable)",
        )

    claude_md_hash_decl = report.frontmatter.get("claude-md-hash", "")
    if claude_md_hash_decl and claude_md_path is not None and claude_md_path.is_file():
        try:
            cm_content = claude_md_path.read_text(encoding="utf-8")
        except OSError as e:
            report.add_warning(
                "PLAN_CLAUDE_MD_READ_FAILED",
                f"lecture CLAUDE.md impossible : {e}",
            )
        else:
            actual = sha256_hex(cm_content)
            declared = claude_md_hash_decl.replace("sha256:", "").strip()
            report.claude_md_hash_match = (actual == declared)
            if not report.claude_md_hash_match:
                report.add_warning(
                    "PLAN_CLAUDE_MD_DRIFT",
                    "claude-md-hash mismatch (non-bloquant, plan reste utilisable)",
                )


def validate_ac_coverage(body: str, report: PlanReport, us_path: Path | None) -> None:
    """Always-applied AC coverage gate → `[PLAN_AC_COVERAGE_GAP]` (exit 2).

    Audit M5 (2026-08-29) — this check used to run only under `--strict`,
    which no documented caller passes, so `[PLAN_AC_COVERAGE_GAP]` had no
    reachable emitter. `dev-plan.md` STEP 4.7 already *describes* AC coverage
    as part of the standard post-generation validation; this aligns the code
    with the documented contract.

    Deliberately narrower than the old strict variant: a plan with **no**
    `## ACs Coverage Summary` at all is a WARNING (that section was a
    strict-readiness requirement, not a correctness one). Only a coverage
    summary that *omits ACs declared in the US* is an error — that is a real
    traceability hole.
    """
    report.ac_coverage = parse_ac_coverage(body)
    if not report.ac_coverage:
        report.add_warning(
            "PLAN_AC_COVERAGE_ABSENT",
            "section `## ACs Coverage Summary` absente ou vide "
            "(traçabilité AC non vérifiable pour ce plan)",
        )
        return
    if us_path is None or not us_path.is_file():
        return
    try:
        us_acs = set(extract_us_acs(us_path.read_text(encoding="utf-8")))
    except OSError:
        return
    missing = us_acs - set(report.ac_coverage.keys())
    if missing:
        report.add_error(
            "PLAN_AC_COVERAGE_GAP",
            f"ACs presents dans l'US mais absents du plan: {sorted(missing)}",
        )


def determine_result(report: PlanReport) -> None:
    """Set report.result based on exit_code.

    Audit M5 — the `not_strict_ready` result (exit 1) is retired along with
    strict mode. Only `valid` (0) and `invalid` (2) remain.
    """
    report.result = "invalid" if report.exit_code == 2 else "valid"


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan_path).resolve()
    us_path = Path(args.us_path).resolve() if args.us_path else None
    claude_md_path = Path(args.claude_md_path).resolve() if args.claude_md_path else None

    report = PlanReport(
        plan_path=normalize(plan_path),
        us_path=normalize(us_path) if us_path else None,
        strict_mode=args.strict,
    )

    if not plan_path.is_file():
        report.add_error("PLAN_NOT_FOUND", f"plan introuvable: {plan_path}")
        determine_result(report)
        _emit_output(report, args.json)
        return report.exit_code

    try:
        plan_content = plan_path.read_text(encoding="utf-8")
    except OSError as e:
        report.add_error("PLAN_UNREADABLE", f"lecture impossible: {e}")
        determine_result(report)
        _emit_output(report, args.json)
        return report.exit_code

    parsed = parse_frontmatter(plan_content)
    if parsed is None:
        report.add_error(
            "PLAN_NO_FRONTMATTER",
            "frontmatter YAML `---` ... `---` absent en tete de fichier",
        )
        determine_result(report)
        _emit_output(report, args.json)
        return report.exit_code

    report.frontmatter, body = parsed

    validate_structural(body, report)

    # Always-on staleness gate (audit fix M3 2026-06-12) — independent of
    # --strict, so /dev-run (which calls without --strict) catches stale plans.
    if report.exit_code < 2:
        validate_staleness(report, us_path)

    # Audit M5 (2026-08-29) — ex-strict checks, now always-on. `--strict` is
    # a retired no-op kept only so an old script does not crash on it.
    if report.exit_code < 2:
        validate_metadata(body, report, claude_md_path)
    if report.exit_code < 2:
        validate_ac_coverage(body, report, us_path)

    determine_result(report)
    _emit_output(report, args.json)
    return report.exit_code


def _emit_output(report: PlanReport, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_json(), separators=(",", ":")))
        return

    # Human-readable summary on stdout
    status_symbol = {"valid": "OK", "invalid": "FAIL"}
    sym = status_symbol.get(report.result, "?")
    print(f"[{sym}] plan={report.plan_path} schema-version={report.schema_version} "
          f"files={len(report.files)} result={report.result}")

    if report.errors:
        # Surface first error in canonical 3-line ERROR/CAUSE/FIX on stderr
        first = report.errors[0]
        error_block(
            error_line=f"validate_plan {report.plan_path}",
            cause=f"[{first['code']}] {first['hint']}",
            fix=("regenerer via /dev-plan {n}" if first['code'].startswith("PLAN_")
                 else "verifier la coherence du plan"),
        )
        # All errors logged as JSON on stderr for callers
        for err in report.errors[1:]:
            print(f"  ERR: [{err['code']}] {err['hint']}", file=sys.stderr)

    for warn in report.warnings:
        print(f"  WARN: [{warn['code']}] {warn['hint']}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
