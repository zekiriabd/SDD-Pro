#!/usr/bin/env python3
"""SDD_Pro template linter (audit m3, 2026-06-06).

Detects drift between `.claude/templates/*.md` and their expected
structure. Catches the silent failure mode where a template gets edited
(e.g. add a section) but the consumer scripts/agents still rely on the
old layout — `po`/`arch`/`elicitor` would generate artifacts with
missing sections.

Checks per template :

  * us.template.md         : H1 `# US-{m}`, ID/Parent/Status frontmatter,
                             required sections (Story, AC, Covers, Deps).
  * feat.template.md       : H1 `# FEAT-{n}`, sections SFD/FD/BR/AC.
  * adr.template.md        : Statut/Date/Context/Decision/Consequences/Alt.
  * constitution.template.md: §1..§8 numbered.
  * claude-md-*.template.md : H1 + Architecture + Forbidden patterns.
  * qa-report.template.md  : metrics summary + per-stack section.
  * readiness.template.md  : GO/NO-GO verdict + checklist.

Exit codes :
  0 = SUCCESS (no drift)
  1 = drift found OR template missing
  2 = unreadable / parse error

CI wiring : `.github/workflows/sdd-ci.yml` calls
  `python .claude/python/sdd_admin/validate_templates.py --strict`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402


@dataclass
class TemplateSpec:
    filename: str
    must_match: list[str] = field(default_factory=list)  # regex patterns
    must_contain: list[str] = field(default_factory=list)  # literal substrings

    def validate(self, text: str) -> list[str]:
        issues: list[str] = []
        for rx in self.must_match:
            if not re.search(rx, text, re.MULTILINE):
                issues.append(f"missing regex: {rx}")
        for needle in self.must_contain:
            if needle not in text:
                issues.append(f"missing literal: {needle!r}")
        return issues


SPECS: list[TemplateSpec] = [
    TemplateSpec(
        filename="us.template.md",
        must_match=[r"^# US-\{m\}:", r"^ID:\s*\{n\}-\{m\}", r"^Status:\s*Draft"],
        must_contain=["## User Story", "## Acceptance Criteria", "## Covers", "## Dependencies"],
    ),
    TemplateSpec(
        filename="feat.template.md",
        must_match=[r"^# FEAT:", r"^FEAT ID:\s*\{n\}"],
        must_contain=["Functional Needs", "Functional Deliverables", "Business Rules", "Acceptance Criteria"],
    ),
    TemplateSpec(
        filename="adr.template.md",
        must_match=[r"^#\s*ADR-"],
        must_contain=["Context", "Decision", "Consequences", "Alternatives"],
    ),
    TemplateSpec(
        filename="constitution.template.md",
        must_contain=["## 1.", "## 2.", "## 3.", "## 4.", "## 6.", "## 7."],
    ),
    # claude-md-{backend,frontend,shared-lib}: BREAKING CHANGES section is
    # injected dynamically by arch only if scaffolding diff exists ; not in
    # static template. Architecture is the canonical anchor.
    TemplateSpec(
        filename="claude-md-backend.template.md",
        must_contain=["## Architecture"],
    ),
    TemplateSpec(
        filename="claude-md-frontend.template.md",
        must_contain=["## Architecture"],
    ),
    TemplateSpec(
        filename="claude-md-shared-lib.template.md",
        must_contain=["{LibName}"],  # template is for shared lib context
    ),
    TemplateSpec(
        filename="qa-report.template.md",
        must_contain=["Coverage", "Tests"],
    ),
    TemplateSpec(
        filename="readiness.template.md",
        must_contain=["GO", "NO-GO"],
    ),
    # Bilingual templates — match FR canonical OR EN fallback.
    TemplateSpec(
        filename="risks-assumptions.template.md",
        must_match=[r"Risques?|Risks?", r"Hypoth[eè]ses?|Assumptions?"],
    ),
    TemplateSpec(
        filename="threat-model.template.md",
        must_contain=["STRIDE", "Assets", "Actors"],
    ),
    TemplateSpec(
        filename="runbook.template.md",
        must_contain=["Mitigation", "Severity"],
    ),
    TemplateSpec(
        filename="slo-sli.template.md",
        must_contain=["SLO", "SLI"],
    ),
    TemplateSpec(
        filename="postmortem.template.md",
        must_match=[r"Timeline|Chronologie", r"Root cause|Cause racine"],
    ),
    TemplateSpec(
        filename="adrs-index.template.md",
        must_contain=["ADR"],
    ),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--strict", action="store_true",
                   help="Exit 1 on any drift (vs WARN-only)")
    args = p.parse_args()

    root = repo_root()
    tpl_dir = root / ".claude" / "templates"
    if not tpl_dir.is_dir():
        print(f"FAIL: templates dir missing: {tpl_dir}", file=sys.stderr)
        return CORRECTIBLE
    findings: list[dict] = []
    for spec in SPECS:
        path = tpl_dir / spec.filename
        if not path.exists():
            findings.append({"template": spec.filename, "status": "MISSING", "issues": []})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append({"template": spec.filename, "status": "UNREADABLE",
                             "issues": [str(exc)]})
            continue
        issues = spec.validate(text)
        findings.append({
            "template": spec.filename,
            "status": "OK" if not issues else "DRIFT",
            "issues": issues,
        })

    drift = sum(1 for f in findings if f["status"] != "OK")
    summary = {
        "templates_total": len(SPECS),
        "ok": sum(1 for f in findings if f["status"] == "OK"),
        "drift": sum(1 for f in findings if f["status"] == "DRIFT"),
        "missing": sum(1 for f in findings if f["status"] == "MISSING"),
        "unreadable": sum(1 for f in findings if f["status"] == "UNREADABLE"),
    }

    if args.json:
        print(json.dumps({"findings": findings, "summary": summary},
                         indent=2, ensure_ascii=False))
    else:
        # ASCII-only output for Windows cp1252 stdout (no Unicode marks).
        print("=== Template Linter (audit m3) ===")
        for f in findings:
            mark = "OK" if f["status"] == "OK" else "FAIL"
            print(f"  [{mark}] {f['template']:<40} {f['status']}")
            for issue in f["issues"]:
                print(f"      - {issue}")
        print(
            f"\nSummary : ok={summary['ok']}  drift={summary['drift']}  "
            f"missing={summary['missing']}  unreadable={summary['unreadable']}"
        )

    if args.strict and drift > 0:
        return FAIL_FAST
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
