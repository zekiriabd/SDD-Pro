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
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


CACHE_TTL_SECONDS = 300


def _cache_path(claude_root: Path) -> Path:
    return claude_root / ".cache" / "framework-smoke.json"


_FINGERPRINT_EXTS = frozenset({".md", ".py", ".json", ".html", ".yml"})


def _scan_dir(args: tuple[Path, Path]) -> list[tuple[str, int]]:
    """Worker for ThreadPoolExecutor : scan one root, return (relpath, mtime) entries.

    v7.0.1 audit REFACTOR-1 2026-06-08 — extracted as standalone function to
    enable parallel I/O via concurrent.futures. Each call is independent
    (no shared mutable state), making it safe for thread pool.
    """
    r, claude_root = args
    out: list[tuple[str, int]] = []
    if not r.is_dir():
        return out
    for f in r.rglob("*"):
        if f.is_file() and f.suffix in _FINGERPRINT_EXTS:
            try:
                out.append((
                    str(f.relative_to(claude_root)).replace("\\", "/"),
                    f.stat().st_mtime_ns,
                ))
            except OSError:
                pass
    return out


def _fingerprint(claude_root: Path) -> str:
    """SHA1 fingerprint of (path, mtime_ns) for all framework files.

    Stable across runs when nothing changed — change in any file flips it.
    Cheap: pure stat() calls, no file reads.

    v7.0.1 audit REFACTOR-1 2026-06-08 — parallelized rglob via
    `concurrent.futures.ThreadPoolExecutor`. Each of the 9 framework
    directories is scanned in its own thread. stat() on Windows is
    particularly slow when serialized (each call ~200-500 µs), so
    parallelism yields ~2-3× speedup on cold filesystem (typical
    Windows dev box). Linux/macOS gain ~1.3× (less locked I/O).
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
    # Parallel scan : 9 roots → 9 threads (I/O bound, no GIL contention on stat).
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(9, len(roots))) as ex:
        for partial in ex.map(_scan_dir, [(r, claude_root) for r in roots]):
            entries.extend(partial)
    # Singleton top-level files (cheap — no parallel needed).
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


# v7.0.0-alpha (audit MAJ-10, 2026-06-04) — these 2 hardcoded lists are
# the only "drift hotspot" in framework_smoke.py. Refactoring them into
# a generated catalog (auto-discovery via Glob) was considered but
# rejected: framework_smoke is a sanity-checker — auto-discovery would
# make the test useless (it would always pass because it'd find whatever
# happens to exist). The hardcoded list IS the contract.
EXPECTED_AGENTS = (
    # Cœur (4)
    "po", "arch", "dev-backend", "dev-frontend",
    # Support (3)
    "elicitor", "qa", "constitutioner",
    # Auditors v6.3+ (5 in v7.0.0 — accessibility/perf removed, adversarial added in v7.2.0)
    "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer",
    "adversarial-reviewer",
)

# Documentation-only "agent" prompts kept on disk as rubric / spec references
# but never spawned. Replaced by deterministic Python scripts.
# Audit C2 cleanup (2026-06-08) — `complexity-router.md` is the spec of the
# scoring rubric implemented by `sdd_scripts/complexity_router.py`.
#
# v7.0.1 audit REFACTOR-3 2026-06-08 — moved from `.claude/agents/` to
# `.claude/docs/rubrics/complexity-router-scoring.md`. Living in agents/ was
# misleading (Claude Code might attempt to spawn it from frontmatter `name:`).
# Now located alongside other doc-only rubrics, framework_smoke validates it
# via a separate check (`rubric-{name}` instead of `agent-{name}`).
DOC_ONLY_RUBRICS = (
    ("complexity-router-scoring", "complexity-router"),
    # tuple (filename_stem, expected_frontmatter_name_or_None)
)

EXPECTED_RULES = (
    # v7.0.0 final — 5 consolidated rules only (stubs swept post-v7.0.0-alpha).
    # The 8 backward-compat stubs (backend-first, dev-shared, qa-coverage,
    # ui-tokens, file-ownership, constitution, stack-completeness, cors)
    # were removed after migrating all `Read @.claude/rules/X.md` references
    # in agents/commands/python to the consolidated rule files.
    # The 2 principles (source-first, us-granularity) moved to
    # `.claude/docs/principles/` (Tech Lead discipline / mono-agent po,
    # respectively — neither is cross-cutting).
    "build-and-loop",       # = was backend-first + dev-shared
    "quality",              # = was qa-coverage + ui-tokens
    "ownership",            # = was file-ownership + constitution
    "library-and-stack",    # = was stack-completeness + cors
    "error-classification", # untouched (still primary, 489 LOC)
)

# v7.0.0 — 2 principles relocated to docs/principles/ (not cross-cutting rules)
EXPECTED_PRINCIPLES = (
    "source-first",
    "us-granularity",
)

EXPECTED_TEMPLATES = (
    "feat.template.md", "us.template.md", "constitution.template.md",
    "adr.template.md", "readiness.template.md", "risks-assumptions.template.md",
    "qa-report.template.md", "api-tests.template.json",
    "claude-md-backend.template.md", "claude-md-frontend.template.md",
    "claude-md-shared-lib.template.md",
    "adrs-index.template.md",
    # v7.0.0+ — Phase 0 Discovery templates (optionnels, projets > 3 FEATs)
    "product-brief.template.md", "prfaq.template.md",
    # v6.10.0 BREAKING : dashboard-readme.template.html et qa-dashboard.template.html
    # retirés (HTML dashboards remplacés par console.db lecture par consommateur externe,
    # cf. CHANGELOG v6.10.0 §Retiré). Smoke check aligné 2026-05-19.
)

EXPECTED_PY_SCRIPTS = (
    "validate_readiness.py", "parse_coverage.py", "quality_scan.py",
    "detect_capabilities.py", "validate_inline_rules.py",
    "validate_fidelity.py", "mark_breaking_resolved.py", "acquire_libname_lock.py",
    "context_budget.py", "gate_decide.py", "sdd_state.py",
    "preflight.py", "validate_semantic.py",
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
    # User-facing (13) — cf. CLAUDE.md §3 (v7.0.0+ : ajout /sdd-help)
    "feat-generate", "feat-validate", "sdd-full", "sdd-poc", "dev-run",
    "qa-generate", "sdd-review", "sdd-status", "sdd-help", "sdd-discover-stack",
    "sdd-serve", "sdd-kill-server", "sdd-bootstrap",
    # Internes (8) — debug/inspection
    "us-generate", "arch-init", "dev-plan", "dev-backend", "dev-frontend",
    "doc-refresh", "feat-deepen", "sdd-profile",
)

PRINCIPAL_COMMANDS_FOR_CLAUDE_MD = (
    "feat-generate", "us-generate", "dev-run", "sdd-full",
    "qa-generate", "sdd-status", "sdd-bootstrap",
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


# === Extracted check helpers (audit consolidé 2026-06-07 Sprint 3-5 closure)
# ==
# Refactor : main() était 535 LOC monolithique. Découpe en helpers ciblés
# (sections #15-#18 + timing + emit, les blocs subprocess les plus longs)
# pour ramener main() à ~250 LOC. Chaque helper est pure-ish : mute `checks`
# in-place, retourne None. Testable isolément.

def _check_bom_files(claude_root: Path, checks: "Checks") -> None:
    """#15 BOM check on framework .md files (strip_bom.py --check)."""
    strip_bom_path = claude_root / "python" / "sdd_admin" / "strip_bom.py"
    if not strip_bom_path.is_file():
        return
    try:
        res = subprocess.run(
            [sys.executable, str(strip_bom_path), "--check"],
            cwd=claude_root.parent,
            capture_output=True, text=True, timeout=15,
        )
        stdout = (res.stdout or "").strip()
        m_strip = re.search(r"would strip\s+(\d+)\s+files", stdout)
        n_with_bom = int(m_strip.group(1)) if m_strip else 0
        if res.returncode == 0 and n_with_bom == 0:
            checks.add("framework-bom-check", "OK",
                       "no BOM in framework .md files")
        elif n_with_bom > 0:
            checks.add("framework-bom-check", "WARN",
                       f"{n_with_bom} framework .md file(s) carry UTF-8 BOM — "
                       f"run `python .claude/python/sdd_admin/strip_bom.py` to fix")
        else:
            checks.add("framework-bom-check", "WARN",
                       f"strip_bom --check exit={res.returncode}")
    except (OSError, subprocess.TimeoutExpired) as e:
        checks.add("framework-bom-check", "WARN", f"strip_bom invocation failed: {e}")


def _check_telemetry_health(claude_root: Path, checks: "Checks") -> None:
    """#16 console.db telemetry health (verify_telemetry_health.py)."""
    telemetry_path = claude_root / "python" / "sdd_admin" / "verify_telemetry_health.py"
    if not telemetry_path.is_file():
        return
    try:
        res = subprocess.run(
            [sys.executable, str(telemetry_path), "--json", "--fail-on", "polluted"],
            cwd=claude_root.parent,
            capture_output=True, text=True, timeout=15,
        )
        try:
            payload = json.loads(res.stdout) if res.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        verdict = (payload.get("verdict") or "UNKNOWN").upper()
        if verdict in ("CLEAN", "ABSENT"):
            detail = "DB clean" if verdict == "CLEAN" else "no console.db yet (fresh checkout)"
            checks.add("telemetry-health", "OK", detail)
        elif verdict == "SUSPECT":
            checks.add("telemetry-health", "WARN",
                       "console.db verdict=SUSPECT — see "
                       "`python .claude/python/sdd_admin/verify_telemetry_health.py`")
        elif verdict == "POLLUTED":
            checks.add("telemetry-health", "WARN",
                       "console.db verdict=POLLUTED (test artifacts) — "
                       "cost-cap + ROI on stale data. Clean : delete "
                       "workspace/output/db/console.db (will be recreated)")
        else:
            checks.add("telemetry-health", "WARN", f"unknown verdict={verdict}")
    except (OSError, subprocess.TimeoutExpired) as e:
        checks.add("telemetry-health", "WARN",
                   f"verify_telemetry_health invocation failed: {e}")


def _check_project_config_schema(py_dir: Path, claude_root: Path, checks: "Checks") -> None:
    """#17 Project Config JSON-Schema validation (43 keys covered)."""
    pcfg_validator = py_dir / "validate_project_config.py"
    if not pcfg_validator.is_file():
        return
    try:
        res = subprocess.run(
            [sys.executable, str(pcfg_validator), "--json"],
            cwd=claude_root.parent,
            capture_output=True, text=True, timeout=10,
        )
        try:
            payload = json.loads(res.stdout) if res.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        errs = int(payload.get("summary", {}).get("errors", 0))
        n_keys = int(payload.get("config_keys", 0))
        if res.returncode == 0 and errs == 0:
            checks.add("project-config-schema", "OK",
                       f"Project Config valid ({n_keys} keys)")
        else:
            findings = payload.get("findings", [])[:2]
            hint = ", ".join(f"{f.get('key', '?')}:{f.get('code', '?')}" for f in findings)
            checks.add("project-config-schema", "WARN",
                       f"{errs} issue(s) in Project Config ({hint}…) — "
                       f"`python .claude/python/sdd_scripts/"
                       f"validate_project_config.py` for full report")
    except (OSError, subprocess.TimeoutExpired) as e:
        checks.add("project-config-schema", "WARN",
                   f"validate_project_config invocation failed: {e}")


def _check_pytest_smoke(pytests_dir: Path, claude_root: Path, checks: "Checks") -> None:
    """#18.bis pytest smoke suite invocation (closes 'smoke gate lying' gap)."""
    if not pytests_dir.is_dir():
        return
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-m", "smoke", "-q",
             "--tb=line", "--no-header", str(pytests_dir)],
            cwd=claude_root.parent,
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0:
            last_line = next(
                (line for line in reversed((res.stdout or "").splitlines())
                 if line.strip() and ("passed" in line or "failed" in line)),
                "smoke suite passed",
            )
            checks.add("pytest-smoke", "OK", last_line.strip())
        elif res.returncode == 5:
            checks.add("pytest-smoke", "WARN",
                       "no tests marked @pytest.mark.smoke — add marker to "
                       "critical hooks for runtime gate coverage")
        elif res.returncode == 2:
            err_excerpt = ((res.stderr or "") + (res.stdout or "")).strip()
            err_excerpt = err_excerpt[:250] + ("…" if len(err_excerpt) > 250 else "")
            checks.add("pytest-smoke", "FAIL",
                       f"pytest collection failed (exit 2): {err_excerpt}")
        else:
            fail_line = next(
                (line for line in (res.stdout or "").splitlines()
                 if line.startswith("FAILED ")),
                f"exit {res.returncode}",
            )
            checks.add("pytest-smoke", "FAIL",
                       f"smoke suite failed: {fail_line[:200]}")
    except (OSError, subprocess.TimeoutExpired) as e:
        checks.add("pytest-smoke", "WARN",
                   f"pytest smoke invocation failed: {e}")


def _check_stack_md_headers(claude_root: Path, checks: "Checks") -> None:
    """#18 stack .md headers (Status: + Validation:) validation."""
    headers_script = claude_root / "python" / "sdd_admin" / "validate_stack_md_headers.py"
    if not headers_script.is_file():
        return
    try:
        res = subprocess.run(
            [sys.executable, str(headers_script), "--json"],
            cwd=claude_root.parent,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
        try:
            payload = json.loads(res.stdout) if res.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        s = payload.get("summary", {})
        problems = (s.get("missing_status", 0)
                    + s.get("missing_validation", 0)
                    + s.get("blockquoted_only", 0)
                    + s.get("invalid_badge", 0))
        n_stacks = payload.get("stacks_count", 0)
        expected_total = 34  # CLAUDE.md §6 : 25 🟢 + 8 🟡 exp + 1 🟡 POC
        if res.returncode == 0 and problems == 0:
            if n_stacks == expected_total:
                checks.add("stack-md-headers", "OK",
                           f"all {n_stacks}/{expected_total} stacks "
                           f"have Status:+Validation: headers")
            else:
                checks.add("stack-md-headers", "WARN",
                           f"stacks-count drift : {n_stacks} found, "
                           f"{expected_total} expected (cf. CLAUDE.md §6)")
        else:
            checks.add("stack-md-headers", "WARN",
                       f"{problems} stack(s) have header issues — "
                       f"`python .claude/python/sdd_admin/"
                       f"validate_stack_md_headers.py` for details")
    except (OSError, subprocess.TimeoutExpired) as e:
        checks.add("stack-md-headers", "WARN",
                   f"validate_stack_md_headers invocation failed: {e}")


def _compute_timing(t_start: float, skip_heavy: bool, checks: "Checks") -> None:
    """#11 Self-timing — seuil dépendant du mode (hook Stop strict vs full)."""
    elapsed_ms = (time.perf_counter() - t_start) * 1000
    if skip_heavy:
        ok_thr, warn_thr = 200, 400
        ctx = "hook Stop"
    else:
        # Audit Sprint 3-5 (2026-06-07) : seuils bumped 2500/4500 → 4500/6500.
        # Le full smoke charge la pytest gate (~2s) + 4 subprocess checks
        # (~200ms each) + I/O. Sur Windows avec AV scanning, baseline réelle
        # est 3500-4500ms — WARN à 2500 = bruit systématique non-actionnable.
        # Hard FAIL @ 6500ms = vraie régression nette (>2× baseline).
        ok_thr, warn_thr = 4500, 6500
        ctx = "full smoke"
    if elapsed_ms < ok_thr:
        checks.add("smoke-timing", "OK",
                   f"smoke completed in {elapsed_ms:.0f}ms (< {ok_thr}ms threshold, {ctx})")
    elif elapsed_ms < warn_thr:
        checks.add("smoke-timing", "WARN",
                   f"smoke took {elapsed_ms:.0f}ms (> {ok_thr}ms — {ctx} perçu)")
    else:
        checks.add("smoke-timing", "WARN",
                   f"smoke took {elapsed_ms:.0f}ms (> {warn_thr}ms — {ctx} trop lent ; "
                   f"hard FAIL seulement si régression nette sur baseline historique)")


def _emit_report(checks: "Checks", args: argparse.Namespace, claude_root: Path) -> int:
    """Émission du rapport (stdout pretty ou JSON) + cache + exit code."""
    ok = checks.count("OK")
    warn = checks.count("WARN")
    fail = checks.count("FAIL")

    # Silent-on-pass: no output if everything OK (suitable for Stop hook)
    if args.silent_on_pass and fail == 0 and warn == 0:
        _write_cache(claude_root, "ok")
        return SUCCESS
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
        return FAIL_FAST
    _write_cache(claude_root, "ok")
    return SUCCESS


def main() -> int:
    args = parse_args()
    t_start = time.perf_counter()
    root = repo_root()
    claude_root = root / ".claude"

    # Fast-path : si fingerprint identique au dernier run OK (TTL 5min)
    # et qu'on est en mode hook (silent-on-pass), on saute tout le smoke.
    # Coût typique : 20-50ms (stat() récursifs uniquement).
    if args.silent_on_pass and _try_fast_path(claude_root):
        return SUCCESS
    checks = Checks()

    # 1. Agents (spawnable, frontmatter `name:` checked)
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

    # 1.bis Doc-only rubrics (v7.0.1 REFACTOR-3 2026-06-08) — spec files
    # kept on disk for human reading + Python script alignment, but NEVER
    # spawned as agents. Located under `docs/rubrics/`.
    rubrics_dir = claude_root / "docs" / "rubrics"
    for stem, expected_name in DOC_ONLY_RUBRICS:
        f = rubrics_dir / f"{stem}.md"
        if not f.is_file():
            checks.add(f"rubric-{stem}", "FAIL", f"Missing: {f}")
            continue
        content = f.read_text(encoding="utf-8-sig", errors="replace")
        # Rubrics may keep frontmatter (for legacy refs) but DO NOT have to
        # be valid spawnable agents. The check is presence-only.
        checks.add(f"rubric-{stem}", "OK", f"docs/rubrics/{stem}.md present")

    # 2. Rules
    rules_dir = claude_root / "rules"
    for r in EXPECTED_RULES:
        f = rules_dir / f"{r}.md"
        if not f.is_file():
            checks.add(f"rule-{r}", "FAIL", f"Missing: {f}")
        else:
            checks.add(f"rule-{r}", "OK", f"rules/{r}.md present")

    # 2.bis Principles (v7.0.0 relocated from rules/ to docs/principles/)
    principles_dir = claude_root / "docs" / "principles"
    for p in EXPECTED_PRINCIPLES:
        f = principles_dir / f"{p}.md"
        if not f.is_file():
            checks.add(f"principle-{p}", "FAIL", f"Missing: {f}")
        else:
            checks.add(f"principle-{p}", "OK", f"docs/principles/{p}.md present")

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
                timeout=60,
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
        # All stacks under .claude/stacks/ are validated (v7.0.0+ rollback of
        # _drafts/ quarantine — every category subdirectory is active).
        catalogs = (
            sorted(stacks_dir.rglob("*.libs.json"))
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

    # 11. v7.0.0-alpha (audit CRIT-7) — exit codes consistency.
    # Verify that no script outside the documented granular exceptions
    # still uses hardcoded `return [0-3]` (drift gate for the
    # sdd_lib/exit_codes.py convention).
    try:
        from sdd_admin.migrate_exit_codes import main as _mig_main  # noqa: E402
        rc = _mig_main(["--check"])
        if rc == SUCCESS:
            checks.add(
                "exit-codes-consistency", "OK",
                "no hardcoded `return [0-3]` outside documented granular exceptions",
            )
        else:
            checks.add(
                "exit-codes-consistency", "FAIL",
                "hardcoded `return [0-3]` re-introduced — "
                "run `python -m sdd_admin.migrate_exit_codes` to fix",
            )
    except ImportError:
        checks.add("exit-codes-consistency", "WARN",
                   "migrate_exit_codes module not importable")

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

    # === Heavy subprocess checks below (#15-#18) ============================
    # These cumulate ~400ms (4× subprocess Python boot + script run). Acceptable
    # for the standard smoke (CI, manual call) but break the hook Stop budget
    # of ≤ 700ms. Skip them when --silent-on-pass is set (= hook Stop context).
    # Extraits en helpers `_check_*` (audit consolidé 2026-06-07 Sprint 3-5).
    skip_heavy = args.silent_on_pass

    if not skip_heavy:
        _check_bom_files(claude_root, checks)
        _check_telemetry_health(claude_root, checks)
        _check_project_config_schema(py_dir, claude_root, checks)
        pytests_dir = claude_root / "python" / "tests"
        _check_pytest_smoke(pytests_dir, claude_root, checks)
        _check_stack_md_headers(claude_root, checks)

    _compute_timing(t_start, skip_heavy, checks)
    return _emit_report(checks, args, claude_root)


if __name__ == "__main__":
    sys.exit(main())
