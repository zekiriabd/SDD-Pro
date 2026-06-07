#!/usr/bin/env python3
"""SDD_Pro: detect drift between inline rules in agents/*.md and rule files.

For each agent containing a `## Inline Rules` section, extracts referenced
rule names (via "substance de X.md" backticks or "@.claude/rules/X.md") and checks
the rule file mtime vs agent mtime. If the rule was modified AFTER the agent,
the agent's inline copy may be stale.

Usage:
    python validate_inline_rules.py            # human report
    python validate_inline_rules.py --json     # JSON output (CI)
    python validate_inline_rules.py --strict   # exit 1 if drift detected

Migrated from .claude/scripts/validate-inline-rules.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


SUBSTANCE_RE = re.compile(r"substance de\s*`([a-zA-Z0-9_-]+)\.md")
AT_RULE_RE = re.compile(r"@\.claude/rules/([a-zA-Z0-9_-]+)\.md")
INLINE_RULES_SECTION_RE = re.compile(r"(?ms)^## Inline Rules")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    return p.parse_args()


def mtime_utc(p: Path) -> datetime:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    args = parse_args()
    root = repo_root()
    agents_dir = root / ".claude" / "agents"
    rules_dir = root / ".claude" / "rules"

    if not agents_dir.is_dir():
        warn(f"Agents dir not found: {agents_dir}")
        return FAIL_FAST
    if not rules_dir.is_dir():
        warn(f"Rules dir not found: {rules_dir}")
        return FAIL_FAST
    agents = sorted(agents_dir.glob("*.md"))
    rules = sorted(rules_dir.glob("*.md"))
    rules_by_name = {r.stem: r for r in rules}

    findings: list[dict] = []

    for agent in agents:
        try:
            content = agent.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not INLINE_RULES_SECTION_RE.search(content):
            continue

        agent_mtime = mtime_utc(agent)
        refs: list[str] = []
        for m in SUBSTANCE_RE.finditer(content):
            refs.append(m.group(1))
        for m in AT_RULE_RE.finditer(content):
            refs.append(m.group(1))
        referenced = sorted(set(refs))

        for rule_name in referenced:
            if rule_name not in rules_by_name:
                findings.append({
                    "agent":       agent.name,
                    "rule":        f"{rule_name}.md",
                    "status":      "MISSING_RULE",
                    "rule_mtime":  None,
                    "agent_mtime": iso(agent_mtime),
                    "delta_days":  None,
                    "message":     "Agent reference une rule inexistante",
                })
                continue

            rule_file = rules_by_name[rule_name]
            rule_mtime = mtime_utc(rule_file)
            # Audit Sprint 3-5 (2026-06-07) : seuil bumped 0d → 1d.
            # Same-day edits (Tech Lead refresh stylistique cross-files,
            # rewrites de compression sans changement sémantique des
            # @-references) génèrent des faux positifs systématiques.
            # 1 jour reste suffisant pour catcher un vrai drift (refactor
            # rule load-bearing — l'agent doit être re-relu sous 24h).
            delta_days = (rule_mtime - agent_mtime).total_seconds() / 86400
            if delta_days > 1.0:
                delta = round(delta_days, 1)
                findings.append({
                    "agent":       agent.name,
                    "rule":        f"{rule_name}.md",
                    "status":      "DRIFT_SUSPECTED",
                    "rule_mtime":  iso(rule_mtime),
                    "agent_mtime": iso(agent_mtime),
                    "delta_days":  delta,
                    "message":     f"Rule modifiee {delta} jours apres l'agent : verifier que les Inline Rules de l'agent sont a jour",
                })
            else:
                findings.append({
                    "agent":       agent.name,
                    "rule":        f"{rule_name}.md",
                    "status":      "OK",
                    "rule_mtime":  iso(rule_mtime),
                    "agent_mtime": iso(agent_mtime),
                    "delta_days":  None,
                    "message":     "OK",
                })

    counts = {
        "ok":              sum(1 for f in findings if f["status"] == "OK"),
        "drift_suspected": sum(1 for f in findings if f["status"] == "DRIFT_SUSPECTED"),
        "missing_rule":    sum(1 for f in findings if f["status"] == "MISSING_RULE"),
    }

    if args.json:
        print(json.dumps({
            "scanned_at":   iso(datetime.now(timezone.utc)),
            "agents_count": len(agents),
            "rules_count":  len(rules),
            "findings":     findings,
            "summary":      counts,
        }, indent=2, ensure_ascii=False))
    else:
        print()
        print("=== Inline Rules Drift Detection ===")
        print(f"Agents scannes  : {len(agents)}")
        print(f"Rules disponibles : {len(rules)}")
        print()

        if counts["missing_rule"]:
            print("[MISSING_RULE] Agent reference une rule introuvable :")
            for f in findings:
                if f["status"] == "MISSING_RULE":
                    print(f"  {f['agent']:<24}  {f['rule']:<32}  {f['message']}")
            print()

        if counts["drift_suspected"]:
            print("[DRIFT_SUSPECTED] Rule modifiee apres l'agent qui l'inline :")
            for f in findings:
                if f["status"] == "DRIFT_SUSPECTED":
                    print(
                        f"  {f['agent']:<24}  {f['rule']:<32}  "
                        f"delta={f['delta_days']}d  rule={f['rule_mtime']}"
                    )
            print("Action recommandee : relire l'agent et verifier les Inline Rules.")
            print()

        if counts["ok"]:
            print(f"[OK] {counts['ok']} references coherentes (rule plus ancienne que l'agent).")

        print()
        print(f"Resume : OK={counts['ok']}  DRIFT={counts['drift_suspected']}  MISSING={counts['missing_rule']}")

    if args.strict and any(f["status"] != "OK" for f in findings):
        return FAIL_FAST
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
