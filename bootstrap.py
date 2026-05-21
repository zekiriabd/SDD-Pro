#!/usr/bin/env python3
"""SDD_Pro bootstrap — interactive project init.

Scaffolds a new SDD_Pro project from this repo (used as GitHub Template).
Zero external dependencies (stdlib only).

What it does
============
  1. Detect if `workspace/input/feats/` already has content
     → if yes, prompt "re-init from scratch ?" (refuse by default = safe)
  2. Interactive prompts (5 questions max) :
     - Application name (used for AppName + BackendName + AppNamespace)
     - Stack combo : choose one of the 2 validated combos OR custom
     - Database type
     - Auth profile (azure-ad / auth-local / none)
     - Frontend / backend dev ports
  3. Generate `workspace/input/stack/stack.md` from the .template
  4. Create `workspace/input/feats/`, `workspace/input/ui/` (empty)
  5. Create `workspace/output/.sys/` skeleton (gitignored)
  6. Run `pip install -e .claude/python[dev]`
  7. Run `npm install` in `workspace/console/` (lazy, on user confirmation)
  8. Run framework smoke as final check

Usage
=====
    python bootstrap.py                # interactive
    python bootstrap.py --dry-run      # show actions, no write
    python bootstrap.py --combo c1     # combo C1 (.NET + React + Azure AD)
    python bootstrap.py --combo c2     # combo C2 (Kotlin + React + Azure AD)
    python bootstrap.py --combo custom # full interactive
    python bootstrap.py --skip-install # skip pip/npm install (CI use)
    python bootstrap.py --force        # overwrite existing workspace/input/

Exit codes
==========
    0 : SUCCESS — project ready, next step printed
    1 : USER_ABORT — user declined re-init or stack choice
    2 : INVALID_INPUT — bad argument / unreachable combo
    3 : INFRA_ERROR — pip / npm / file write failure
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows (cp1252 defaults break the emoji-rich
# bootstrap output). Python 3.7+ supports reconfigure(). No-op on Linux/macOS
# where UTF-8 is already the default.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


REPO_ROOT = Path(__file__).resolve().parent
STACK_TEMPLATE = REPO_ROOT / "workspace" / "input" / "stack" / "stack.md.template"
STACK_TARGET = REPO_ROOT / "workspace" / "input" / "stack" / "stack.md"
FEATS_DIR = REPO_ROOT / "workspace" / "input" / "feats"
UI_DIR = REPO_ROOT / "workspace" / "input" / "ui"
SYS_DIR = REPO_ROOT / "workspace" / "output" / ".sys"
PYTHON_DIR = REPO_ROOT / ".claude" / "python"
CONSOLE_DIR = REPO_ROOT / "workspace" / "console"
SMOKE_SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_admin" / "framework_smoke.py"


# ---------------------------------------------------------------------------
# Combos validated bout-en-bout (cf. docs/validated-combos.md)
# ---------------------------------------------------------------------------
COMBOS = {
    "c1": {
        "label": "C1 — .NET Minimal API + React + shadcn + Azure AD (recommended)",
        "backend": "dotnet-minimalapi",
        "frontend": "react",
        "ui": "shadcn",
        "qa": ["dotnet-xunit", "node-vitest"],
        "auth": "azure-ad",
        "archi": "mvc",
        "lib_strategy": "openapi-codegen",
        "backend_port": "5097",
        "frontend_port": "5173",
    },
    "c2": {
        "label": "C2 — Kotlin Spring Boot + React + shadcn + Azure AD",
        "backend": "kotlin-spring-boot",
        "frontend": "react",
        "ui": "shadcn",
        "qa": ["kotlin-junit", "node-vitest"],
        "auth": "azure-ad",
        "archi": "mvc",
        "lib_strategy": "openapi-codegen",
        "backend_port": "8080",
        "frontend_port": "5173",
    },
}

DB_TYPES = ("none", "PostgreSql", "SqlServer", "MySql", "Sqlite", "MariaDb", "Oracle", "MongoDb")


# ---------------------------------------------------------------------------
# IO helpers (zero deps, work on bare Python)
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str | None = None, choices: list[str] | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    if choices:
        choices_str = " / ".join(choices)
        suffix = f" ({choices_str}){suffix}"
    while True:
        try:
            raw = input(f"{prompt}{suffix} : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        if not raw and default is not None:
            return default
        if not raw:
            print("  ⚠️  Required.")
            continue
        if choices and raw.lower() not in [c.lower() for c in choices]:
            print(f"  ⚠️  Must be one of : {' / '.join(choices)}")
            continue
        return raw


def _ask_yn(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = _ask(prompt, default="Y" if default else "N", choices=["y", "n", "Y", "N"])
    return raw.lower() == "y"


def _print_header(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    print()


def _print_info(msg: str) -> None:
    print(f"  ℹ️  {msg}")


def _print_ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def _print_warn(msg: str) -> None:
    print(f"  ⚠️  {msg}", file=sys.stderr)


def _print_error(msg: str) -> None:
    print(f"  ❌ {msg}", file=sys.stderr)


def _validate_app_name(name: str) -> str | None:
    """Return error message if name invalid, None if OK.

    SDD_Pro convention : PascalCase, no spaces, no accents.
    """
    if not re.match(r"^[A-Z][A-Za-z0-9]+$", name):
        return ("must be PascalCase (starts uppercase, letters/digits only, "
                "no spaces, no accents). Example : MyApp, EcommerceApi")
    if len(name) > 32:
        return f"too long ({len(name)} chars, max 32)"
    return None


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def detect_existing_project() -> bool:
    """True if workspace/input/feats/ has FEAT files (project already initialised)."""
    if not FEATS_DIR.is_dir():
        return False
    feats = [f for f in FEATS_DIR.glob("*.md") if not f.name.startswith(".")]
    return len(feats) > 0


def detect_stack_md() -> bool:
    """True if a stack.md already exists (not the template)."""
    return STACK_TARGET.is_file() and STACK_TARGET.stat().st_size > 100


# ---------------------------------------------------------------------------
# Interactive flow
# ---------------------------------------------------------------------------

def choose_combo(forced: str | None) -> dict:
    """Return a combo config dict from preset or interactive choice."""
    if forced:
        forced = forced.lower()
        if forced in COMBOS:
            _print_info(f"Using preset {forced.upper()} : {COMBOS[forced]['label']}")
            return dict(COMBOS[forced])
        if forced != "custom":
            _print_error(f"Unknown combo '{forced}'. Valid : c1 / c2 / custom")
            sys.exit(2)

    _print_header("Stack combo")
    print("  Validated combos (bout-en-bout, tested) :")
    print(f"    [1] {COMBOS['c1']['label']}")
    print(f"    [2] {COMBOS['c2']['label']}")
    print(f"    [3] Custom (pick each stack manually)")
    print()
    choice = _ask("Pick a combo", default="1", choices=["1", "2", "3"])
    if choice == "1":
        return dict(COMBOS["c1"])
    if choice == "2":
        return dict(COMBOS["c2"])

    # Custom
    _print_header("Custom stack")
    backend = _ask(
        "Backend stack",
        default="dotnet-minimalapi",
        choices=["dotnet-minimalapi", "kotlin-spring-boot", "node-express", "python-fastapi"],
    )
    frontend = _ask(
        "Frontend stack",
        default="react",
        choices=["react", "vue", "angular", "blazor-webassembly"],
    )
    ui = _ask(
        "UI design system",
        default="shadcn",
        choices=["shadcn", "vuetify", "radzen-blazor"],
    )
    archi = _ask(
        "Architecture pattern",
        default="mvc",
        choices=["mvc", "ddd"],
    )

    qa_map = {
        "dotnet-minimalapi": "dotnet-xunit",
        "kotlin-spring-boot": "kotlin-junit",
        "node-express": "node-vitest",
        "python-fastapi": "python-pytest",
    }
    qa_front_map = {
        "react": "node-vitest",
        "vue": "node-vitest",
        "angular": "angular-jasmine",
        "blazor-webassembly": "blazor-bunit",
    }
    return {
        "label": f"Custom : {backend} + {frontend} + {ui}",
        "backend": backend,
        "frontend": frontend,
        "ui": ui,
        "qa": [qa_map.get(backend, "dotnet-xunit"), qa_front_map.get(frontend, "node-vitest")],
        "auth": _ask("Auth profile", default="azure-ad", choices=["azure-ad", "auth-local", "none"]),
        "archi": archi,
        "lib_strategy": "openapi-codegen",
        "backend_port": _ask("Backend dev port", default="5000"),
        "frontend_port": _ask("Frontend dev port", default="5173"),
    }


def collect_project_info(combo: dict) -> dict:
    """5-question prompt for the project-specific values."""
    _print_header("Project")
    while True:
        app_name = _ask("Application name (PascalCase)", default="MyApp")
        err = _validate_app_name(app_name)
        if err is None:
            break
        _print_warn(err)

    backend_name = _ask("Backend project name", default=f"{app_name}Back")
    err = _validate_app_name(backend_name)
    if err:
        _print_warn(err)
        backend_name = f"{app_name}Back"

    db_type = _ask("Database type", default="PostgreSql", choices=list(DB_TYPES))
    return {
        "app_name": app_name,
        "backend_name": backend_name,
        "db_type": db_type,
        **combo,
    }


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_stack_md(info: dict) -> str:
    """Substitute placeholders in stack.md.template."""
    tpl = STACK_TEMPLATE.read_text(encoding="utf-8")
    backend_line = f" - .claude/stacks/backend/{info['backend']}.md"
    frontend_line = f" - .claude/stacks/frontend/{info['frontend']}.md"
    ui_line = f" - .claude/stacks/ui/{info['ui']}.md" if info["ui"] else "# (no UI)"
    qa_lines = "\n".join(f" - .claude/stacks/qa/{qa}.md" for qa in info["qa"])

    auth = info.get("auth", "none")
    if auth == "azure-ad":
        auth_lines = """\
 - .claude/stacks/auth/azure-ad.md
 - AZ_TENANTID:"<your-tenant-id>"
 - AZ_CLIENTID:"<your-client-id>"
 - AZ_DOMAIN:"<your-domain.com>"
 - AZ_AUDIENCES:"'<your-client-id>'"
 - AZ_BE_CALLBACKPATH:"/signin-oidc"
 - AZ_FE_CALLBACKPATH:"/authentication/login-callback\""""
    elif auth == "auth-local":
        auth_lines = """\
 - .claude/stacks/auth/auth-local.md
 - AUTH_JWT_AUDIENCE:{app_name}
 - AUTH_JWT_EXPIRATION:4
 - AUTH_JWT_ISSUER:{app_name}Back
 - AUTH_JWT_SECRET:<replace-with-long-random-secret>""".format(app_name=info["app_name"])
    else:
        auth_lines = "# (no auth profile active — uncomment azure-ad or auth-local if needed)"

    db_type = info["db_type"]
    if db_type == "none":
        db_env = "# (no DB — DatabaseType=none)"
    elif db_type.lower() in ("postgres", "postgresql"):
        db_env = (
            " - DB_HOST:127.0.0.1\n"
            f" - DB_NAME:{info['app_name']}\n"
            " - DB_PASSWORD:<replace-with-secret>\n"
            " - DB_PORT:5432\n"
            " - DB_USER:postgres"
        )
    elif db_type == "SqlServer":
        db_env = (
            " - DB_HOST:127.0.0.1\n"
            f" - DB_NAME:{info['app_name']}\n"
            " - DB_PASSWORD:<replace-with-secret>\n"
            " - DB_PORT:1433\n"
            " - DB_USER:sa"
        )
    else:
        db_env = (
            " - DB_HOST:127.0.0.1\n"
            f" - DB_NAME:{info['app_name']}\n"
            " - DB_PASSWORD:<replace-with-secret>\n"
            " - DB_PORT:<default-port-for-engine>\n"
            " - DB_USER:<engine-user>"
        )

    replacements = {
        "{{AppName}}": info["app_name"],
        "{{BackendName}}": info["backend_name"],
        "{{FrontendPort}}": info["frontend_port"],
        "{{BackendPort}}": info["backend_port"],
        "{{LibStrategy}}": info["lib_strategy"],
        "{{ArchiPattern}}": info["archi"],
        "{{BackendActiveLine}}": backend_line,
        "{{FrontendActiveLine}}": frontend_line,
        "{{UiActiveLine}}": ui_line,
        "{{QaActiveLines}}": qa_lines,
        "{{AuthActiveLines}}": auth_lines,
        "{{DatabaseType}}": db_type,
        "{{DatabaseEnvLines}}": db_env,
    }
    for k, v in replacements.items():
        tpl = tpl.replace(k, v)
    return tpl


# ---------------------------------------------------------------------------
# Scaffolding actions
# ---------------------------------------------------------------------------

def write_stack_md(content: str, dry_run: bool) -> None:
    if dry_run:
        _print_info(f"(dry-run) would write {STACK_TARGET}")
        return
    STACK_TARGET.parent.mkdir(parents=True, exist_ok=True)
    STACK_TARGET.write_text(content, encoding="utf-8")
    _print_ok(f"Wrote {STACK_TARGET.relative_to(REPO_ROOT)}")


def create_workspace_skeleton(dry_run: bool) -> None:
    targets = [
        REPO_ROOT / "workspace" / "input" / "feats",
        REPO_ROOT / "workspace" / "input" / "ui",
        REPO_ROOT / "workspace" / "input" / "assets",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".audit",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".context" / "adrs",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".state",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".validation",
        REPO_ROOT / "workspace" / "output" / "src",
        REPO_ROOT / "workspace" / "output" / "us",
        REPO_ROOT / "workspace" / "output" / "plans",
        REPO_ROOT / "workspace" / "output" / "db",
    ]
    for p in targets:
        if dry_run:
            _print_info(f"(dry-run) would mkdir {p.relative_to(REPO_ROOT)}")
        else:
            p.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        _print_ok(f"Created {len(targets)} workspace directories")


def install_python_deps(dry_run: bool) -> bool:
    """Run `pip install -e .claude/python[dev]`. Returns True on success."""
    if dry_run:
        _print_info(f"(dry-run) would run : pip install -e {PYTHON_DIR.relative_to(REPO_ROOT)}[dev]")
        return True
    if not (PYTHON_DIR / "pyproject.toml").is_file():
        _print_warn(f"No pyproject.toml at {PYTHON_DIR} — skipping Python deps install")
        return False
    _print_info("Installing Python deps (pip install -e .claude/python[dev]) ...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", f"{PYTHON_DIR}[dev]"],
            cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            _print_warn(f"pip install exited {result.returncode}")
            _print_warn(f"stderr (tail) : {result.stderr[-300:]}")
            return False
        _print_ok("Python deps installed")
        return True
    except (OSError, subprocess.SubprocessError) as e:
        _print_warn(f"pip install failed: {e}")
        return False


def install_console_deps(dry_run: bool) -> bool:
    """Run `npm install` in workspace/console/. Heavy (~50MB) → confirmation."""
    if not (CONSOLE_DIR / "package.json").is_file():
        _print_warn(f"No package.json at {CONSOLE_DIR} — skipping console deps")
        return False
    if dry_run:
        _print_info(f"(dry-run) would run : npm install in {CONSOLE_DIR.relative_to(REPO_ROOT)}")
        return True
    if not _ask_yn("Install console deps now (npm install in workspace/console/, ~50MB) ?",
                   default=True):
        _print_info("Skipped — run later via : cd workspace/console && npm install")
        return False
    _print_info("Running npm install (workspace/console/) ...")
    try:
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        result = subprocess.run(
            [npm_cmd, "install"],
            cwd=CONSOLE_DIR,
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            _print_warn(f"npm install exited {result.returncode}")
            return False
        _print_ok("Console deps installed")
        return True
    except (OSError, subprocess.SubprocessError) as e:
        _print_warn(f"npm install failed: {e}")
        return False


def run_smoke_check(dry_run: bool) -> bool:
    if dry_run:
        _print_info(f"(dry-run) would run framework smoke")
        return True
    if not SMOKE_SCRIPT.is_file():
        return False
    _print_info("Running framework smoke check ...")
    try:
        result = subprocess.run(
            [sys.executable, str(SMOKE_SCRIPT), "--silent-on-pass"],
            cwd=REPO_ROOT,
            capture_output=True, text=True, check=False, timeout=30,
        )
        if result.returncode == 0:
            _print_ok("Framework smoke : all checks pass")
            return True
        _print_warn(f"Smoke returned {result.returncode}")
        if result.stdout.strip():
            print(result.stdout[-500:])
        return False
    except (OSError, subprocess.SubprocessError) as e:
        _print_warn(f"Smoke check failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def print_next_steps(info: dict) -> None:
    _print_header("Next steps")
    msg = textwrap.dedent(f"""\
      1. **Edit secrets** in workspace/input/stack/stack.md :
         - {info['db_type']} credentials (DB_PASSWORD, DB_USER, ...)
         - Auth credentials (Azure AD tenant/client, or AUTH_JWT_SECRET)
         - SMTP if needed
         → This file is gitignored — safe for local secrets.

      2. **Create your first FEAT** :
         /feat-generate Auth          # interactive — answers 3-6 questions

      3. **Run the full pipeline** :
         /sdd-full 1                  # generates US, code, tests for FEAT 1

      4. **Inspect status / verdict** :
         /sdd-status 1                # diagnostic
         /sdd-review 1                # consolidated audit

      5. **Run the live console** (optional) :
         /sdd-serve                   # spawns backend + frontend + console (http://127.0.0.1:4000)

      Docs : .claude/docs/quickstart.md (full walkthrough)
             .claude/CLAUDE.md         (framework overview)
    """)
    print(msg)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SDD_Pro project bootstrap (interactive).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
          Examples :
              python bootstrap.py
              python bootstrap.py --combo c1
              python bootstrap.py --combo custom --skip-install
              python bootstrap.py --dry-run
        """),
    )
    parser.add_argument("--combo", choices=["c1", "c2", "custom"],
                        help="Skip the stack-choice prompt with a preset.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show actions without writing files / installing.")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip pip/npm install (CI use).")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing workspace/input/ without confirmation.")
    args = parser.parse_args()

    _print_header("SDD_Pro bootstrap")
    print("  Framework version : v7.0.0-alpha")
    print(f"  Repo root         : {REPO_ROOT}")
    print(f"  Mode              : {'DRY RUN' if args.dry_run else 'EXECUTE'}")

    # Sanity
    if not STACK_TEMPLATE.is_file():
        _print_error(f"stack.md.template not found at {STACK_TEMPLATE}")
        _print_error("Is this a real SDD_Pro repo ? Aborting.")
        return 2

    # Re-init protection
    has_existing = detect_existing_project() or detect_stack_md()
    if has_existing and not args.force:
        _print_warn("This project appears to be ALREADY initialized :")
        if detect_existing_project():
            n = len(list(FEATS_DIR.glob("*.md")))
            _print_warn(f"  workspace/input/feats/ has {n} FEAT(s)")
        if detect_stack_md():
            _print_warn(f"  workspace/input/stack/stack.md exists")
        print()
        if not _ask_yn("Continue (will OVERWRITE existing stack.md) ?", default=False):
            _print_info("Aborted — your existing workspace is untouched.")
            return 1

    # Interactive
    combo = choose_combo(args.combo)
    info = collect_project_info(combo)

    _print_header("Summary")
    print(f"  AppName       : {info['app_name']}")
    print(f"  BackendName   : {info['backend_name']}")
    print(f"  Stack         : {info['label']}")
    print(f"  Database      : {info['db_type']}")
    print(f"  Auth          : {info['auth']}")
    print(f"  Ports         : backend={info['backend_port']} / frontend={info['frontend_port']}")
    print()
    if not args.dry_run and not _ask_yn("Proceed with this config ?", default=True):
        _print_info("Aborted by user.")
        return 1

    # Execute
    _print_header("Scaffolding")
    rendered = render_stack_md(info)
    write_stack_md(rendered, args.dry_run)
    create_workspace_skeleton(args.dry_run)

    if not args.skip_install:
        _print_header("Dependencies")
        install_python_deps(args.dry_run)
        install_console_deps(args.dry_run)

    if not args.dry_run:
        _print_header("Verification")
        run_smoke_check(args.dry_run)

    print_next_steps(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
