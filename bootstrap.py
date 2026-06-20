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
    python bootstrap.py --auto-init    # non-interactive CI mode (reads env vars)

Auto-init env vars (when --auto-init)
=====================================
    SDD_APP_NAME       (required) PascalCase application name
    SDD_COMBO          (required) c1 | c2 | c3 | c4 | c5 | custom
    SDD_BACKEND_NAME   (optional) defaults to {AppName}Back
    SDD_DB_TYPE        (optional) defaults to PostgreSql
    SDD_AUTH           (optional) azure-ad | auth-local | none (default: combo's auth)
    SDD_BACKEND_PORT   (optional) defaults to combo's port
    SDD_FRONTEND_PORT  (optional) defaults to combo's port
    SDD_CONFIRM        (optional) "1" auto-confirms proceed prompt

Exit codes
==========
    0 : SUCCESS — project ready, next step printed
    1 : USER_ABORT — user declined re-init or stack choice
    2 : INVALID_INPUT — bad argument / unreachable combo / missing env var in --auto-init
    3 : INFRA_ERROR — pip / npm / file write failure
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
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
STACK_TEMPLATE = REPO_ROOT / ".claude" / "templates" / "stack.md.template"
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
        "label": "C1 — .NET Minimal API + React + shadcn + Azure AD (validated 🟢)",
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
        "label": "C2 — Kotlin Spring Boot + React + shadcn + Azure AD (validated 🟢)",
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
    "c3": {
        "label": "C3 — Node Express + React + shadcn + auth-local (bench-validated 🟢)",
        "backend": "node-express",
        "frontend": "react",
        "ui": "shadcn",
        "qa": ["node-vitest"],
        "auth": "auth-local",
        "archi": "mvc",
        "lib_strategy": "openapi-codegen",
        "backend_port": "3000",
        "frontend_port": "5173",
    },
    "c4": {
        "label": "C4 — Python FastAPI + React + shadcn + auth-local (bench-validated 🟢)",
        "backend": "python-fastapi",
        "frontend": "react",
        "ui": "shadcn",
        "qa": ["python-pytest", "node-vitest"],
        "auth": "auth-local",
        "archi": "mvc",
        "lib_strategy": "openapi-codegen",
        "backend_port": "8000",
        "frontend_port": "5173",
    },
    "c5": {
        "label": "C5 — .NET Minimal API + Vue + Vuetify + Azure AD (bench-validated 🟢)",
        "backend": "dotnet-minimalapi",
        "frontend": "vue",
        "ui": "vuetify",
        "qa": ["dotnet-xunit", "node-vitest"],
        "auth": "azure-ad",
        "archi": "mvc",
        "lib_strategy": "openapi-codegen",
        "backend_port": "5097",
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

# Audit consolidé 2026-06-07 Sprint 2 (CRIT-11 closure) : C3-C13 sont
# désormais `bench-validated` dans combos.json (SLA Tier 2 best-effort) au
# lieu de "pending validation". L'ensemble est vidé mais le garde-fou
# `_confirm_unvalidated_combo` est préservé pour réintroduction future
# (si un nouveau combo Cx pending validation arrive en pré-bench).
_UNVALIDATED_COMBOS: set[str] = set()

# Audit CTO 2026-06-07 — replaced hardcoded `_EXPERIMENTAL_*` sets with
# a derivation from `combos.json/componentLevels` (SSoT, cf.
# `sdd_lib/combos.py`). The previous hardcoded values drifted from
# reality :
#   • `node-express` + `python-fastapi` were marked experimental in
#     bootstrap.py but `combos.json` reports them as `validated`
#     (bench-validated runtime, supported best-effort).
#   • `vue` + `angular` were marked experimental but `combos.json`
#     reports them as `validated`.
#   • `radzen-blazor` was marked experimental but `combos.json`
#     reports it as 🟢 reference (`validated`).
# A stack is flagged as "needs warn" if its declared level in
# `componentLevels[category]` is NOT `validated` (i.e. one of
# experimental / untested / poc-only / scaffold-validated).
_NON_VALIDATED_LEVELS = {"experimental", "untested", "poc-only", "scaffold-validated"}


def _is_non_validated(category: str, stack_id: str) -> bool:
    """Return True if `stack_id` in `category` is NOT `validated` per combos.json.

    Falls back to `False` (treat as validated) when combos.py is unavailable
    — defensive : bootstrap must still work if `.claude/python/` isn't
    importable yet (fresh checkout edge case, although unlikely since this
    script lives at repo root).
    """
    try:
        # Imported lazily to keep bootstrap stdlib-only at module import time.
        sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))
        from sdd_lib.combos import get_component_level  # noqa: E402
        level = get_component_level(category, stack_id, root=REPO_ROOT)
        return level in _NON_VALIDATED_LEVELS
    except (ImportError, FileNotFoundError, OSError):
        return False


def _confirm_unvalidated_combo(combo_key: str, *, auto_init: bool = False) -> None:
    """Bloc explicite avant d'engager un combo 🟡 non validé end-to-end.

    v7.0.0-alpha (audit 2026-06-05) : avant ce gate, l'utilisateur pouvait
    choisir C3/C4/C5 sans réaliser que le pipeline `/sdd-full` n'a jamais
    tourné end-to-end dessus (risque runtime non-trivial). On force un
    consentement explicite ; en CI (`--auto-init`), il faut poser
    SDD_ALLOW_UNTESTED_COMBO=1 pour passer.
    """
    if combo_key not in _UNVALIDATED_COMBOS:
        return
    if os.environ.get("SDD_ALLOW_UNTESTED_COMBO") == "1":
        _print_info(f"Combo {combo_key.upper()} 🟡 — bypass via SDD_ALLOW_UNTESTED_COMBO=1")
        return
    if auto_init:
        _print_error(
            f"Combo {combo_key.upper()} est 🟡 pending validation (jamais "
            f"validé bout-en-bout). En --auto-init, poser "
            f"SDD_ALLOW_UNTESTED_COMBO=1 pour confirmer."
        )
        sys.exit(2)
    _print_header(f"⚠️  Combo {combo_key.upper()} non validé end-to-end")
    print(
        f"  Le combo {combo_key.upper()} est marqué 🟡 « pending validation » :\n"
        "    • aucun PoC formel `/sdd-full` FEAT M (3 US back+front) sans intervention.\n"
        "    • le pipeline peut échouer en runtime (CORS, codegen, capabilities).\n"
        "    • voir .claude/docs/validated-combos.md pour la matrice à jour.\n"
        "\n"
        "  Combos 🟢 validés (recommandés) : C1 (.NET) / C2 (Kotlin Spring).\n"
    )
    answer = _ask("Continuer quand même ?", default="N", choices=["y", "Y", "n", "N"])
    if answer.lower() != "y":
        _print_info("Bootstrap annulé. Relance avec --combo c1 ou --combo c2.")
        sys.exit(0)


def choose_combo(forced: str | None, *, auto_init: bool = False) -> dict:
    """Return a combo config dict from preset or interactive choice."""
    if forced:
        forced = forced.lower()
        if forced in COMBOS:
            _print_info(f"Using preset {forced.upper()} : {COMBOS[forced]['label']}")
            _confirm_unvalidated_combo(forced, auto_init=auto_init)
            return dict(COMBOS[forced])
        if forced != "custom":
            _print_error(f"Unknown combo '{forced}'. Valid : c1 / c2 / c3 / c4 / c5 / custom")
            sys.exit(2)

    _print_header("Stack combo")
    print("  Combos available :")
    print(f"    [1] {COMBOS['c1']['label']}")
    print(f"    [2] {COMBOS['c2']['label']}")
    print(f"    [3] {COMBOS['c3']['label']}")
    print(f"    [4] {COMBOS['c4']['label']}")
    print(f"    [5] {COMBOS['c5']['label']}")
    print(f"    [6] Custom (pick each stack manually)")
    print()
    choice = _ask("Pick a combo", default="1", choices=["1", "2", "3", "4", "5", "6"])
    combo_key = {"1": "c1", "2": "c2", "3": "c3", "4": "c4", "5": "c5"}.get(choice)
    if combo_key:
        _confirm_unvalidated_combo(combo_key, auto_init=auto_init)
        return dict(COMBOS[combo_key])

    # Custom
    _print_header("Custom stack")
    _print_info(
        "Stacks 🟢 reference (validés bout-en-bout dans un combo C1/C2) :\n"
        "  - backend  : dotnet-minimalapi, kotlin-spring-boot\n"
        "  - frontend : react, blazor-webassembly\n"
        "  - ui       : shadcn\n"
        "  - archi    : mvc\n"
        "Les autres sont 🟡 expérimentaux (chargeables, runtime non garanti)."
    )
    backend = _ask(
        "Backend stack",
        default="dotnet-minimalapi",
        choices=["dotnet-minimalapi", "kotlin-spring-boot", "node-express", "python-fastapi"],
    )
    if _is_non_validated("backend", backend):
        _print_warn(f"Backend '{backend}' = 🟡 non-validated end-to-end (cf. combos.json/componentLevels)")
    frontend = _ask(
        "Frontend stack",
        default="react",
        choices=["react", "vue", "angular", "blazor-webassembly"],
    )
    if _is_non_validated("frontend", frontend):
        _print_warn(f"Frontend '{frontend}' = 🟡 non-validated end-to-end (cf. combos.json/componentLevels)")
    ui = _ask(
        "UI design system",
        default="shadcn",
        choices=["shadcn", "vuetify", "radzen-blazor"],
    )
    if _is_non_validated("ui", ui):
        _print_warn(f"UI '{ui}' = 🟡 non-validated end-to-end (cf. combos.json/componentLevels)")
    archi = _ask(
        "Architecture pattern",
        default="mvc",
        choices=["mvc", "ddd"],
    )
    if _is_non_validated("archi", archi):
        _print_warn(f"Archi '{archi}' = 🟡 non-validated end-to-end (cf. combos.json/componentLevels)")

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


def collect_project_info(combo: dict, auto_init: bool = False) -> dict:
    """5-question prompt for the project-specific values.

    Args:
        combo: stack combo dict from choose_combo()
        auto_init: when True, read all values from SDD_* env vars (no prompts);
                   missing required env vars -> sys.exit(2)
    """
    if auto_init:
        app_name = os.environ.get("SDD_APP_NAME", "").strip()
        if not app_name:
            _print_error("--auto-init requires SDD_APP_NAME env var (PascalCase)")
            sys.exit(2)
        err = _validate_app_name(app_name)
        if err:
            _print_error(f"SDD_APP_NAME invalid: {err}")
            sys.exit(2)
        backend_name = os.environ.get("SDD_BACKEND_NAME", f"{app_name}Back").strip()
        err = _validate_app_name(backend_name)
        if err:
            _print_warn(f"SDD_BACKEND_NAME invalid ({err}), falling back to {app_name}Back")
            backend_name = f"{app_name}Back"
        db_type = os.environ.get("SDD_DB_TYPE", "PostgreSql").strip()
        if db_type not in DB_TYPES:
            _print_error(f"SDD_DB_TYPE invalid: '{db_type}' (must be one of: {', '.join(DB_TYPES)})")
            sys.exit(2)
        # Optional auth + port overrides
        auth_override = os.environ.get("SDD_AUTH", "").strip()
        if auth_override and auth_override in ("azure-ad", "auth-local", "none"):
            combo = {**combo, "auth": auth_override}
        for env_key, combo_key in (("SDD_BACKEND_PORT", "backend_port"),
                                    ("SDD_FRONTEND_PORT", "frontend_port")):
            v = os.environ.get(env_key, "").strip()
            if v:
                combo = {**combo, combo_key: v}
        return {
            "app_name": app_name,
            "backend_name": backend_name,
            "db_type": db_type,
            **combo,
        }

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
    if auth == "auth-local":  # noqa: E501 — secrets generated; values in clear, stack.md is gitignored (Pattern B)
        # Generate a real high-entropy JWT secret (64 chars urlsafe base64).
        # Pattern B (stack.md = SSoT) — value lives in clear in gitignored stack.md.
        # Previous placeholder `<replace-with-long-random-secret>` was a footgun
        # (users shipped it to staging unchanged).
        jwt_secret = secrets.token_urlsafe(48)
        auth_lines = """\
 - .claude/stacks/auth/auth-local.md
 - AUTH_JWT_AUDIENCE:{app_name}
 - AUTH_JWT_EXPIRATION:4
 - AUTH_JWT_ISSUER:{app_name}Back
 - AUTH_JWT_SECRET:{jwt_secret}""".format(app_name=info["app_name"], jwt_secret=jwt_secret)
    elif auth == "azure-ad":
        # Azure AD requires Tech Lead to paste tenant identifiers from the
        # portal — no random generation possible. Lines are commented to force
        # explicit action (no fake placeholder shipped to prod).
        auth_lines = """\
 - .claude/stacks/auth/azure-ad.md
# - AZ_TENANTID:<paste-tenant-id-from-azure-portal>
# - AZ_CLIENTID:<paste-client-id-from-app-registration>
# - AZ_DOMAIN:<your-domain.com>
# - AZ_AUDIENCES:<client-id>
# - AZ_BE_CALLBACKPATH:/signin-oidc
# - AZ_FE_CALLBACKPATH:/authentication/login-callback"""
    else:
        auth_lines = "# (no auth profile active — uncomment azure-ad or auth-local if needed)"

    # DB password — generated random (caller can replace with the real local DB
    # password before `dotnet ef` / Prisma generate). Pattern B: lives in
    # gitignored stack.md, propagated to appsettings/application.yml by arch.
    db_password = secrets.token_urlsafe(24)
    db_type = info["db_type"]
    if db_type == "none":
        db_env = "# (no DB — DatabaseType=none)"
    elif db_type.lower() in ("postgres", "postgresql"):
        db_env = (
            " - DB_HOST:127.0.0.1\n"
            f" - DB_NAME:{info['app_name']}\n"
            f" - DB_PASSWORD:{db_password}\n"
            " - DB_PORT:5432\n"
            " - DB_USER:postgres"
        )
    elif db_type == "SqlServer":
        db_env = (
            " - DB_HOST:127.0.0.1\n"
            f" - DB_NAME:{info['app_name']}\n"
            f" - DB_PASSWORD:{db_password}\n"
            " - DB_PORT:1433\n"
            " - DB_USER:sa"
        )
    else:
        db_env = (
            " - DB_HOST:127.0.0.1\n"
            f" - DB_NAME:{info['app_name']}\n"
            f" - DB_PASSWORD:{db_password}\n"
            " - DB_PORT:5432\n"
            " - DB_USER:postgres"
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
    """Create the canonical workspace tree.

    Idempotent : `mkdir(exist_ok=True)` on every dir, safe to re-run on
    an existing project. Always invoked (never conditional) so a partial
    init can be repaired by simply re-running `python bootstrap.py`.
    """
    targets = [
        REPO_ROOT / "workspace" / "input" / "feats",
        REPO_ROOT / "workspace" / "input" / "ui",
        REPO_ROOT / "workspace" / "input" / "assets",
        REPO_ROOT / "workspace" / "input" / "discovery",  # v7.0.0+ Phase 0 templates (PRFAQ, Product Brief)
        REPO_ROOT / "workspace" / "output" / ".sys" / ".audit",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".cache",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".context" / "adrs",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".routing",  # v7.0.0+ complexity-router output
        REPO_ROOT / "workspace" / "output" / ".sys" / ".state",
        REPO_ROOT / "workspace" / "output" / ".sys" / ".validation",
        REPO_ROOT / "workspace" / "output" / "src",
        REPO_ROOT / "workspace" / "output" / "us",
        REPO_ROOT / "workspace" / "output" / "plans",
        REPO_ROOT / "workspace" / "output" / "db",
        REPO_ROOT / "workspace" / "output" / "qa",
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


def install_console_deps(dry_run: bool, auto_yes: bool = False) -> bool:
    """Run `npm install` in workspace/console/. Heavy (~50MB) → confirmation.

    Args:
        dry_run: preview only.
        auto_yes: when True (CI / --auto-init), skip the confirmation prompt and install.
    """
    if not (CONSOLE_DIR / "package.json").is_file():
        _print_warn(f"No package.json at {CONSOLE_DIR} — skipping console deps")
        return False
    if dry_run:
        _print_info(f"(dry-run) would run : npm install in {CONSOLE_DIR.relative_to(REPO_ROOT)}")
        return True
    if not auto_yes and not _ask_yn(
        "Install console deps now (npm install in workspace/console/, ~50MB) ?",
        default=True,
    ):
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


def _check_prereqs(combo: str | None) -> int:
    """Verify runtime prerequisites for a combo (or all combos).

    Sprint P1 (2026-06-08) — onboarding helper. Reads docs/prerequisites-matrix.md
    requirements implicitly (canonical version pins per combo) and probes the
    local machine. Exits 0 if all OK, 3 if any required tool missing.
    """
    _print_header(f"SDD_Pro prereq check (combo={combo or 'ALL'})")

    # (combo_key, tool_check, version_extract_pattern, min_version, doc_link)
    UNIVERSAL = [
        ("git",       ["git", "--version"],     r"(\d+\.\d+)",      "2.40", "https://git-scm.com"),
        ("python",    [sys.executable, "--version"], r"(\d+\.\d+)", "3.12", "https://python.org"),
        ("sqlite3",   ["sqlite3", "-version"],  r"(\d+\.\d+\.\d+)", "3.40", "https://sqlite.org"),
    ]
    PER_COMBO = {
        "c1": [("dotnet", ["dotnet", "--version"], r"(\d+)\.", "10", "https://dot.net")],
        "c2": [("java",   ["java", "-version"],   r'"(\d+)',     "21", "https://adoptium.net"),
               ("node",   ["node", "--version"],  r"v(\d+)\.",    "22", "https://nodejs.org")],
        "c3": [("node",   ["node", "--version"],  r"v(\d+)\.",    "22", "https://nodejs.org")],
        "c4": [("python", [sys.executable, "--version"], r"(\d+\.\d+)", "3.12", "https://python.org"),
               ("node",   ["node", "--version"],  r"v(\d+)\.",    "22", "https://nodejs.org")],
        "c5": [("dotnet", ["dotnet", "--version"], r"(\d+)\.", "10", "https://dot.net"),
               ("node",   ["node", "--version"],  r"v(\d+)\.",    "22", "https://nodejs.org")],
    }

    if combo and combo != "custom":
        checks = UNIVERSAL + PER_COMBO.get(combo, [])
    else:
        # All combos = union of all tools
        seen = set()
        checks = list(UNIVERSAL)
        for c_checks in PER_COMBO.values():
            for ck in c_checks:
                if ck[0] not in seen:
                    seen.add(ck[0])
                    checks.append(ck)

    failures: list[tuple[str, str]] = []
    for name, cmd, pattern, min_ver, doc in checks:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            output = (r.stdout or "") + (r.stderr or "")
            m = re.search(pattern, output)
            if not m:
                failures.append((name, f"could not parse version from `{' '.join(cmd)}` → see {doc}"))
                _print_warn(f"  {name:<10} : version unparseable")
                continue
            found = m.group(1)
            # Naive version compare (lexicographic ok for single-digit majors)
            if _version_lt(found, min_ver):
                failures.append((name, f"installed {found} < required {min_ver} → see {doc}"))
                _print_warn(f"  {name:<10} : {found} (< {min_ver} required)")
            else:
                _print_info(f"  {name:<10} : {found}  [OK]")
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as e:
            failures.append((name, f"not installed → see {doc}"))
            _print_warn(f"  {name:<10} : NOT INSTALLED  → {doc}")

    print()
    if failures:
        _print_error(f"{len(failures)} prerequisite(s) failed :")
        for name, reason in failures:
            print(f"  - {name} : {reason}")
        print()
        print(f"  Full matrix : docs/prerequisites-matrix.md")
        return 3
    print(f"  All {len(checks)} prerequisites OK. You can run /sdd-bootstrap.")
    return 0


def _version_lt(found: str, minimum: str) -> bool:
    """Numeric version compare, returns True if found < minimum."""
    try:
        f_parts = [int(p) for p in found.split(".")]
        m_parts = [int(p) for p in minimum.split(".")]
        # Pad to same length
        n = max(len(f_parts), len(m_parts))
        f_parts += [0] * (n - len(f_parts))
        m_parts += [0] * (n - len(m_parts))
        return f_parts < m_parts
    except ValueError:
        return False


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
    parser.add_argument("--combo", choices=["c1", "c2", "c3", "c4", "c5", "custom"],
                        help="Skip the stack-choice prompt with a preset (c1/c2 validated end-to-end, c3/c4/c5 bench-validated runtime — tous SLA-éligibles depuis v7.0.0 GA).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show actions without writing files / installing.")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip pip/npm install (CI use).")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing workspace/input/ without confirmation.")
    parser.add_argument("--auto-init", action="store_true",
                        help="Non-interactive CI mode — reads SDD_* env vars, no prompts.")
    parser.add_argument("--check-prereqs", action="store_true",
                        help="Verify runtime prerequisites for the chosen --combo (or all) and exit. See docs/prerequisites-matrix.md")
    args = parser.parse_args()

    # Sprint P1 (2026-06-08) — --check-prereqs: verify runtimes, no scaffold.
    if args.check_prereqs:
        return _check_prereqs(args.combo)

    # --auto-init implies --force (idempotent CI) AND --skip-install (CI installs
    # deps separately via cached steps). P0-3 fix 2026-06-07 : the docstring
    # promised this for years but `skip_install` was never set, causing CI to
    # potentially install deps mid-bootstrap.
    if args.auto_init:
        args.force = True
        args.skip_install = True
        if not args.combo:
            env_combo = os.environ.get("SDD_COMBO", "").lower()
            if not env_combo:
                _print_error("--auto-init requires SDD_COMBO env var (c1 | c2 | c3 | c4 | c5 | custom)")
                return 2
            args.combo = env_combo

    _print_header("SDD_Pro bootstrap")
    print("  Framework version : v7.0.0 GA")
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

    # Interactive (or env-driven in --auto-init mode)
    combo = choose_combo(args.combo, auto_init=args.auto_init)
    info = collect_project_info(combo, auto_init=args.auto_init)

    _print_header("Summary")
    print(f"  AppName       : {info['app_name']}")
    print(f"  BackendName   : {info['backend_name']}")
    print(f"  Stack         : {info['label']}")
    print(f"  Database      : {info['db_type']}")
    print(f"  Auth          : {info['auth']}")
    print(f"  Ports         : backend={info['backend_port']} / frontend={info['frontend_port']}")
    print()
    if not args.dry_run and not args.auto_init and not _ask_yn("Proceed with this config ?", default=True):
        _print_info("Aborted by user.")
        return 1

    # Execute
    _print_header("Scaffolding")
    rendered = render_stack_md(info)
    write_stack_md(rendered, args.dry_run)
    create_workspace_skeleton(args.dry_run)

    # P0-3 fix 2026-06-07 : install + smoke return booleans that used to be
    # discarded — meaning a pip/npm failure or a smoke regression silently
    # produced exit 0. Now aggregated and propagated as EXIT_INFRA_ERROR (3)
    # to honor the docstring contract.
    infra_failures: list[str] = []
    if not args.skip_install:
        _print_header("Dependencies")
        if not install_python_deps(args.dry_run):
            infra_failures.append("pip install (Python deps)")
        if not install_console_deps(args.dry_run, auto_yes=args.auto_init):
            # console deps are optional (user can run later) — only fail
            # when --auto-init since CI cannot recover interactively
            if args.auto_init:
                infra_failures.append("npm install (console deps)")

    if not args.dry_run:
        _print_header("Verification")
        if not run_smoke_check(args.dry_run):
            infra_failures.append("framework smoke check")

    if infra_failures:
        _print_header("Bootstrap incomplet — infra errors")
        for f in infra_failures:
            _print_warn(f"  - {f}")
        _print_warn("Bootstrap created the workspace but post-install verification failed.")
        _print_warn("FIX : retry the failed step manually (cf. warnings above) then re-run bootstrap.py --force")
        return 3  # EXIT_INFRA_ERROR per docstring

    print_next_steps(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
