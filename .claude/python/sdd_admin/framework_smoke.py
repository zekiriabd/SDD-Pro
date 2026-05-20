#!/usr/bin/env python3
"""SDD_Pro framework smoke test.

Validates SDD_Pro internal coherence WITHOUT running a pipeline.

Checks:
1. Expected agents/*.md exist with valid frontmatter
2. Expected rules/*.md exist
3. Expected templates/* exist
4. Expected scripts (Python and/or PowerShell) exist
5. Expected commands/*.md exist
6. No Inline Rules drift (delegates to validate_inline_rules.py)
7. CLAUDE.md cites principal commands
8. docs/{architecture,workflow,conventions}.md exist

Usage:
    python framework_smoke.py
    python framework_smoke.py --json
    python framework_smoke.py --strict   (exit 1 on FAIL)

Migrated from .claude/scripts/framework-smoke.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402


CACHE_TTL_SECONDS = 300


def _cache_path(claude_root: Path) -> Path:
    return claude_root / ".cache" / "framework-smoke.json"


def _fingerprint(claude_root: Path) -> str:
    """SHA1 fingerprint of (path, mtime_ns) for all framework files.

    Stable across runs when nothing changed — change in any file flips it.
    Cheap: pure stat() calls, no file reads.
    """
    h = hashlib.sha1()
    roots = (
        claude_root / "agents",
        claude_root / "rules",
        claude_root / "commands",
        claude_root / "docs",
        claude_root / "templates",
        claude_root / "python" / "sdd_scripts",
        claude_root / "python" / "sdd_admin",
        claude_root / "python" / "sdd_hooks",
        claude_root / "stacks",
    )
    entries: list[tuple[str, int]] = []
    for r in roots:
        if not r.is_dir():
            continue
        for f in r.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".py", ".json", ".html", ".yml"):
                try:
                    entries.append((str(f.relative_to(claude_root)).replace("\\", "/"), f.stat().st_mtime_ns))
                except OSError:
                    pass
    for p in ("CLAUDE.md", "loader.yml", "settings.json", "WORKING-AGREEMENT.md"):
        f = claude_root / p
        if f.is_file():
            try:
                entries.append((p, f.stat().st_mtime_ns))
            except OSError:
                pass
    entries.sort()
    for path, mtime in entries:
        h.update(f"{path}:{mtime}\n".encode("utf-8"))
    return h.hexdigest()


def _try_fast_path(claude_root: Path) -> bool:
    """Return True if cache is fresh AND fingerprint matches → skip full smoke."""
    cache_file = _cache_path(claude_root)
    if not cache_file.is_file():
        return False
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("status") != "ok":
        return False
    age = time.time() - data.get("timestamp", 0)
    if age > CACHE_TTL_SECONDS:
        return False
    return data.get("fingerprint") == _fingerprint(claude_root)


def _write_cache(claude_root: Path, status: str) -> None:
    cache_file = _cache_path(claude_root)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "timestamp": time.time(),
        "fingerprint": _fingerprint(claude_root) if status == "ok" else "",
    }
    try:
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


EXPECTED_AGENTS = (
    # Cœur (4)
    "po", "arch", "dev-backend", "dev-frontend",
    # Variants strict v6.2 — REMOVED v7.0.0 (governance-major-prompts-trim)
    # Support (3)
    "elicitor", "qa", "constitutioner",
    # Rendering (1) — REMOVED v7.0.0 (governance-major-auditors-trim)
    # → replaced by sdd_scripts/index_adrs.py (0 token, deterministic)
    # Auditors v6.3+ (4 after v7.0.0 trim)
    # accessibility-auditor + performance-auditor REMOVED v7.0.0
    # → axe-core + Lighthouse CI
    "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer",
)

EXPECTED_RULES = (
    "us-granularity", "constitution", "file-ownership",
    "qa-coverage", "stack-completeness",
    "backend-first", "error-classification", "source-first",
    "dev-shared",
    # Ajoutées v6.9.0 (consolidation patterns inlinés)
    "cors", "ui-tokens",
)

EXPECTED_TEMPLATES = (
    "feat.template.md", "us.template.md", "constitution.template.md",
    "adr.template.md", "readiness.template.md", "risks-assumptions.template.md",
    "qa-report.template.md", "api-tests.template.json",
    "claude-md-backend.template.md", "claude-md-frontend.template.md",
    "claude-md-shared-lib.template.md",
    "adrs-index.template.md",
    # v6.10.0 BREAKING : dashboard-readme.template.html et qa-dashboard.template.html
    # retirés (HTML dashboards remplacés par console.db lecture par consommateur externe,
    # cf. CHANGELOG v6.10.0 §Retiré). Smoke check aligné 2026-05-19.
)

EXPECTED_PY_SCRIPTS = (
    "validate_readiness.py", "parse_coverage.py", "quality_scan.py",
    "detect_capabilities.py", "validate_inline_rules.py",
    "validate_fidelity.py", "mark_breaking_resolved.py", "acquire_libname_lock.py",
    "context_budget.py", "gate_decide.py", "sdd_state.py",
    "compact_front_plans.py", "preflight.py", "validate_semantic.py",
    "detect_arch_shortcircuit.py",
    # v6.8 — US schema v2 toolkit
    "set_us_status.py", "compute_us_complexity.py",
    "migrate_us_v1_to_v2.py", "validate_us_deps.py",
)

EXPECTED_ADMIN_SCRIPTS = (
    "framework_smoke.py", "measure_batch.py", "init_status_json.py",
    "sync_stack_md.py", "validate_libs_catalog.py",
)

EXPECTED_COMMANDS = (
    "feat-generate", "feat-deepen", "feat-validate", "us-generate", "arch-init",
    "dev-plan", "dev-backend", "dev-frontend", "dev-run", "sdd-full",
    "qa-generate", "sdd-status", "doc-refresh",
)

PRINCIPAL_COMMANDS_FOR_CLAUDE_MD = (
    "feat-generate", "us-generate", "dev-run", "sdd-full",
    "qa-generate", "sdd-status",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument(
        "--silent-on-pass",
        action="store_true",
        help="No stdout output if all checks pass (suitable for Stop hook).",
    )
    return p.parse_args()


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, status: str, message: str) -> None:
        self.items.append({"name": name, "status": status, "message": message})

    def count(self, status: str) -> int:
        return sum(1 for c in self.items if c["status"] == status)


def main() -> int:
    args = parse_args()
    t_start = time.perf_counter()
    root = repo_root()
    claude_root = root / ".claude"

    # Fast-path : si fingerprint identique au dernier run OK (TTL 5min)
    # et qu'on est en mode hook (silent-on-pass), on saute tout le smoke.
    # Coût typique : 20-50ms (stat() récursifs uniquement).
    if args.silent_on_pass and _try_fast_path(claude_root):
        return 0

    checks = Checks()

    # 1. Agents
    agents_dir = claude_root / "agents"
    for a in EXPECTED_AGENTS:
        f = agents_dir / f"{a}.md"
        if not f.is_file():
            checks.add(f"agent-{a}", "FAIL", f"Missing: {f}")
            continue
        content = f.read_text(encoding="utf-8-sig", errors="replace")  # strip BOM
        if not re.search(rf"(?ms)^---\s*\r?\n.*?name:\s*{re.escape(a)}\s*\r?$", content):
            checks.add(f"agent-{a}", "WARN", "Frontmatter name field missing or wrong")
        else:
            checks.add(f"agent-{a}", "OK", f"agents/{a}.md present")

    # 2. Rules
    rules_dir = claude_root / "rules"
    for r in EXPECTED_RULES:
        f = rules_dir / f"{r}.md"
        if not f.is_file():
            checks.add(f"rule-{r}", "FAIL", f"Missing: {f}")
        else:
            checks.add(f"rule-{r}", "OK", f"rules/{r}.md present")

    # 3. Templates
    templates_dir = claude_root / "templates"
    for t in EXPECTED_TEMPLATES:
        f = templates_dir / t
        if not f.is_file():
            checks.add(f"template-{t}", "FAIL", f"Missing: {f}")
        else:
            checks.add(f"template-{t}", "OK", f"templates/{t} present")

    # 4. Python scripts (pipeline)
    py_dir = claude_root / "python" / "sdd_scripts"
    for s in EXPECTED_PY_SCRIPTS:
        f = py_dir / s
        if not f.is_file():
            checks.add(f"py-script-{s}", "WARN", f"Missing Python migration: {f}")
        else:
            checks.add(f"py-script-{s}", "OK", f"python/sdd_scripts/{s} present")

    # 4.b Python admin scripts (Tech Lead opt-in, depuis 2026-05-13)
    admin_dir = claude_root / "python" / "sdd_admin"
    for s in EXPECTED_ADMIN_SCRIPTS:
        f = admin_dir / s
        if not f.is_file():
            checks.add(f"py-admin-{s}", "WARN", f"Missing admin script: {f}")
        else:
            checks.add(f"py-admin-{s}", "OK", f"python/sdd_admin/{s} present")

    # 5. Commands
    commands_dir = claude_root / "commands"
    for c in EXPECTED_COMMANDS:
        f = commands_dir / f"{c}.md"
        if not f.is_file():
            checks.add(f"command-{c}", "FAIL", f"Missing: {f}")
        else:
            checks.add(f"command-{c}", "OK", f"commands/{c}.md present")

    # 6. Inline Rules drift
    drift_script = py_dir / "validate_inline_rules.py"
    if drift_script.is_file():
        try:
            result = subprocess.run(
                [sys.executable, str(drift_script), "--json"],
                capture_output=True, text=True, check=False,
            )
            drift = json.loads(result.stdout) if result.stdout.strip() else {}
            summary = drift.get("summary", {})
            d_count = int(summary.get("drift_suspected", 0))
            m_count = int(summary.get("missing_rule", 0))
            ok_count = int(summary.get("ok", 0))
            if d_count > 0:
                checks.add("inline-rules-drift", "WARN", f"{d_count} drift suspected")
            elif m_count > 0:
                checks.add("inline-rules-drift", "FAIL", f"{m_count} missing rules")
            else:
                checks.add("inline-rules-drift", "OK", f"{ok_count} refs coherent, 0 drift")
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            checks.add("inline-rules-drift", "WARN", "Could not parse drift detector output")

    # 7. CLAUDE.md cites principal commands
    claude_md = claude_root / "CLAUDE.md"
    if claude_md.is_file():
        cm = claude_md.read_text(encoding="utf-8", errors="replace")
        missing = [c for c in PRINCIPAL_COMMANDS_FOR_CLAUDE_MD if f"/{c}" not in cm]
        if missing:
            checks.add(
                "claude-md-commands",
                "WARN",
                f"Commands not cited in CLAUDE.md: {', '.join(missing)}",
            )
        else:
            checks.add("claude-md-commands", "OK", "Principal commands referenced in CLAUDE.md")

    # 8. docs/
    docs_dir = claude_root / "docs"
    for d in ("architecture.md", "workflow.md", "conventions.md"):
        f = docs_dir / d
        if not f.is_file():
            checks.add(f"docs-{d}", "WARN", f"Missing: docs/{d}")
        else:
            checks.add(f"docs-{d}", "OK", f"docs/{d} present")

    # 9. Parallélisme dev-run preservé (anti-régression risque #4)
    dev_run = claude_root / "commands" / "dev-run.md"
    if dev_run.is_file():
        dr = dev_run.read_text(encoding="utf-8", errors="replace").lower()
        # Pattern : la commande doit déclarer son invocation Agent parallèle
        if "parall" in dr and "agent" in dr and "dev-backend" in dr and "dev-frontend" in dr:
            checks.add("parallel-orchestration", "OK", "dev-run.md déclare l'invocation Agent parallèle dev-*")
        else:
            checks.add(
                "parallel-orchestration", "WARN",
                "dev-run.md ne mentionne plus 'parallèle' + 'Agent' + 'dev-backend/dev-frontend' (orchestration dégradée ?)",
            )

    # 9.bis Libs catalogs schema validation (anti-régression drift JSON silencieux)
    try:
        from sdd_admin.validate_libs_catalog import validate_catalog  # noqa: E402

        stacks_dir = claude_root / "stacks"
        # Skip _drafts/ subtree — those are quarantined stacks
        # (fullstack/mobiles/ddd/microservice) not part of the active surface.
        catalogs = (
            sorted(p for p in stacks_dir.rglob("*.libs.json")
                   if "_drafts" not in p.parts)
            if stacks_dir.is_dir() else []
        )
        cat_errors = 0
        for f in catalogs:
            _, errs, _ = validate_catalog(f, root)
            cat_errors += len(errs)
        if cat_errors == 0:
            checks.add("libs-catalogs-schema", "OK",
                       f"{len(catalogs)} .libs.json valid (schema + versionRef + capability)")
        else:
            checks.add("libs-catalogs-schema", "FAIL",
                       f"{cat_errors} schema error(s) in stacks/**/*.libs.json — run validate_libs_catalog.py")
    except ImportError:
        checks.add("libs-catalogs-schema", "WARN", "validate_libs_catalog module not importable")

    # 10. Console lock cross-langage symétrique (anti-régression risque #2)
    node_lock = root / "workspace" / "console" / "lib" / "atomic-write.js"
    py_lock = claude_root / "python" / "sdd_scripts" / "gate_decide.py"
    if node_lock.is_file() and py_lock.is_file():
        node_src = node_lock.read_text(encoding="utf-8", errors="replace")
        py_src = py_lock.read_text(encoding="utf-8", errors="replace")
        # Les deux doivent partager le même nom de lock et la TTL 10s
        symmetric = ".status.lock" in node_src and ".status.lock" in py_src \
            and "10_000" in node_src and "10000" in py_src
        if symmetric:
            checks.add("console-lock-symmetry", "OK", "Console lock Node <-> Python symetrique (.status.lock + TTL 10s)")
        else:
            checks.add(
                "console-lock-symmetry", "WARN",
                "Implémentations console lock Node et Python ont divergé (lock path ou TTL)",
            )

    # 12. v6.8 — US schema v2 coherence (Metadata + 7 statuses + Dependencies doc)
    us_tpl = templates_dir / "us.template.md"
    if us_tpl.is_file():
        tpl = us_tpl.read_text(encoding="utf-8", errors="replace")
        has_metadata = "## Metadata" in tpl and "```json" in tpl
        has_status_doc = all(s in tpl for s in
                             ("Ready", "InProgress", "Review", "Deferred", "Cancelled"))
        if has_metadata and has_status_doc:
            checks.add("us-template-v2", "OK",
                       "us.template.md v6.8: Metadata + 7-status doc present")
        else:
            missing_bits = []
            if not has_metadata:
                missing_bits.append("Metadata section")
            if not has_status_doc:
                missing_bits.append("7-status doc")
            checks.add("us-template-v2", "WARN",
                       f"us.template.md v6.8 incomplete: missing {', '.join(missing_bits)}")

    # 13. v6.8 — Error classification taxonomy includes US_STATUS_* and US_DEPS_*
    err_class = rules_dir / "error-classification.md"
    if err_class.is_file():
        ec = err_class.read_text(encoding="utf-8", errors="replace")
        v68_classes = ("[US_STATUS_INVALID]", "[US_STATUS_TRANSITION_INVALID]",
                       "[US_DEPS_CYCLE]", "[US_DEPS_MISSING]", "[US_NOT_FOUND]")
        missing_classes = [c for c in v68_classes if c not in ec]
        if not missing_classes:
            checks.add("error-classes-v6.8", "OK",
                       "error-classification.md v6.8 classes present")
        else:
            checks.add("error-classes-v6.8", "WARN",
                       f"Missing classes: {', '.join(missing_classes)}")

    # 14. v6.8 — dev-run.md STEP 2.bis (deps validation gate)
    if dev_run.is_file():
        dr_content = dev_run.read_text(encoding="utf-8", errors="replace")
        has_step_2bis = "STEP 2.bis" in dr_content and "validate_us_deps.py" in dr_content
        if has_step_2bis:
            checks.add("dev-run-deps-gate", "OK",
                       "dev-run.md STEP 2.bis (US deps gate) wired")
        else:
            checks.add("dev-run-deps-gate", "WARN",
                       "dev-run.md missing STEP 2.bis or validate_us_deps.py invocation")

    # 11. Self-timing (anti-régression risque #1 : smoke doit rester rapide au hook Stop)
    elapsed_ms = (time.perf_counter() - t_start) * 1000
    if elapsed_ms < 200:
        checks.add("smoke-timing", "OK", f"smoke completed in {elapsed_ms:.0f}ms (< 200ms threshold)")
    elif elapsed_ms < 500:
        checks.add("smoke-timing", "WARN", f"smoke took {elapsed_ms:.0f}ms (> 200ms — hook Stop perçu)")
    else:
        checks.add("smoke-timing", "FAIL", f"smoke took {elapsed_ms:.0f}ms (> 500ms — hook Stop trop lent)")

    ok = checks.count("OK")
    warn = checks.count("WARN")
    fail = checks.count("FAIL")

    # Silent-on-pass: no output if everything OK (suitable for Stop hook)
    if args.silent_on_pass and fail == 0 and warn == 0:
        _write_cache(claude_root, "ok")
        return 0

    if args.json:
        result = {
            "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary":    {"total": len(checks.items), "ok": ok, "warn": warn, "fail": fail},
            "checks":     checks.items,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print()
        print("=== SDD_Pro Framework Smoke Test ===")
        print()
        fails = [c for c in checks.items if c["status"] == "FAIL"]
        warns = [c for c in checks.items if c["status"] == "WARN"]
        if fails:
            print(f"[FAIL] {len(fails)} error(s):")
            for c in fails:
                print(f"  {c['name']:<32}  {c['message']}")
            print()
        if warns:
            print(f"[WARN] {len(warns)} warning(s):")
            for c in warns:
                print(f"  {c['name']:<32}  {c['message']}")
            print()
        if not fails and not warns:
            print(f"[OK] All checks pass ({ok} / {len(checks.items)})")
        print()
        print(f"Summary: OK={ok}  WARN={warn}  FAIL={fail}  total={len(checks.items)}")

    if (args.strict and fail > 0) or fail > 0:
        _write_cache(claude_root, "fail")
        return 1
    _write_cache(claude_root, "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
