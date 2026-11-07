"""Hook launcher — cwd-independent bootstrap for SDD_Pro hooks.

Why this file exists:
- Claude Code hook commands in settings.json use relative paths
  (`python .sdd/python/...`). These break if the parent process'
  cwd has drifted away from the repo root (sub-agent, Bash cd, etc.).
- This launcher resolves the repo root via CLAUDE_PROJECT_DIR env var
  if set, otherwise walks up from cwd to find a directory matching the
  strict repo layout. Then chdir + sys.path + runpy the target module.

The settings.json hook commands call this launcher via inline
`python -c` that finds the launcher itself the same way. Once Python
is running, everything anchors here.

Fail-CLOSED policy (audit sécurité 2026-11)
-------------------------------------------
Avant cet audit, `run()` n'avait aucun try/except : une exception non
gérée dans un hook (import cassé, payload inattendu, OSError) sortait en
**exit 1** — que Claude Code traite comme *non bloquant* (stderr montré,
tool call autorisé). Autrement dit, planter un hook de protection
revenait à le désactiver. Désormais :

  * hook **bloquant** (défaut) : toute exception non gérée → message 3L
    `ERROR / CAUSE: [HOOK_CRASH] / FIX` sur stderr + **exit 2** (DENY).
  * hook **informatif** (liste explicite `INFORMATIONAL_HOOKS` : statusline,
    bannière session, télémétrie, auto-router, sentinel po, smoke Stop) :
    exception → WARN stderr + **exit 0** (ne jamais casser une session pour
    de la télémétrie).
  * `SystemExit` (le hook a décidé de son code) et `KeyboardInterrupt`
    passent tels quels.

Timeout policy (corrigé audit 2026-11 — l'ancien docstring annonçait
"~30 s") :
  Claude Code applique un timeout **par hook de 600 s par défaut**
  (configurable par entrée `timeout` dans settings.json). Si le module
  lancé se bloque (verrou SQLite, boucle infinie), le harnais tue le
  process et le tool call retombe sur le comportement par défaut
  (généralement ALLOW) — un hook qui pend est donc fail-open par
  construction du harnais, indépendamment de ce fichier. Ce launcher ne
  pose pas de `signal.alarm` (POSIX-only ; SDD_Pro cible Windows + Linux +
  macOS). Les hooks qui spawnent des sous-process DOIVENT borner leur
  `subprocess.run(..., timeout=N)` eux-mêmes (ex. preflight_stack_combo
  timeout=15) et traiter l'expiration en DENY.

Racine du dépôt — risque documenté
----------------------------------
`find_repo_root()` exige les 3 marqueurs `.sdd/agents` + `.sdd/commands` +
`workspace` (strict, identique à `sdd_lib.paths._looks_like_repo_root`
côté `.sdd/`). Sans `CLAUDE_PROJECT_DIR`, la racine est déduite en
remontant depuis le cwd : si Claude Code est lancé depuis un sous-dossier
d'un **clone non fiable** (ex. un dépôt tiers déposé sous `workspace/old/`
qui contiendrait lui-même un `.sdd/`), c'est le code Python de CE clone
qui serait exécuté avec les droits de l'utilisateur. `CLAUDE_PROJECT_DIR`
(positionné par Claude Code pour les hooks) est donc la source à
privilégier ; en son absence, le premier candidat trouvé en remontant
est pris, jamais un candidat plus profond que le cwd.

Usage (from settings.json):
    python -c "import os,sys,pathlib; r=os.environ.get('CLAUDE_PROJECT_DIR') or next((str(p) for p in [pathlib.Path.cwd()]+list(pathlib.Path.cwd().parents) if (p/'.sdd').is_dir()),'.'); sys.path.insert(0,r+'/.sdd/python'); import _hook; _hook.run('sdd_hooks.protect_framework')"
"""
from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path

#: Hooks dont un crash ne doit JAMAIS bloquer l'outil appelant : purement
#: informatifs (télémétrie, bannière, statusline, smoke de fin de session).
#: Tout module absent de cette liste est traité en fail-CLOSED (exit 2).
INFORMATIONAL_HOOKS: frozenset[str] = frozenset({
    "sdd_hooks.statusline",
    "sdd_hooks.session_start",
    "sdd_hooks.record_token_usage",
    "sdd_hooks.auto_invoke_complexity_router",
    "sdd_hooks.resolve_po_hash_sentinel",
    "sdd_admin.framework_smoke",
    "sdd_admin.statusline",
})

#: Exit codes du protocole hook Claude Code (miroir de sdd_lib.exit_codes,
#: dupliqué ici car ce fichier tourne AVANT que sys.path connaisse sdd_lib).
_HOOK_ALLOW = 0
_HOOK_DENY = 2


def _looks_like_repo_root(p: Path) -> bool:
    """Strict repo-root check — mirror of `sdd_lib.paths._looks_like_repo_root`.

    Post-migration 2026-07-25 : the SSoT anchors under `.sdd/` (`.sdd/agents/`
    + `.sdd/commands/` = tracked, always present after clone). The
    `.claude/agents/` / `.claude/commands/` are now transient façade
    regenerated at session_start — using them as anchor would fail on
    fresh clones before the first rebuild.

    Post-mortem 2026-05-21 : un sous-dossier d'archive `.claude/.claude/`
    faisait croire au walker que `.claude/` était le repo root → mêmes
    précautions ici avec `.sdd/.sdd/` (triple marker required).

    Bootstrap-safe duplicate de `sdd_lib.paths._looks_like_repo_root` :
    ce fichier doit fonctionner AVANT que `sys.path` connaisse `sdd_lib`,
    donc ne peut pas importer la version canonique. Toute modification
    de la logique strict-check doit être appliquée aux 2 emplacements
    (paths.py + _hook.py). Garde-fou : `test_paths.py` vérifie l'alignement.
    """
    return (
        (p / ".sdd" / "agents").is_dir()
        and (p / ".sdd" / "commands").is_dir()
        and ((p / "workspace").is_dir() or (p.parent / "workspace").is_dir())
    )


def find_repo_root() -> Path:
    """Resolve repo root: CLAUDE_PROJECT_DIR env var, else walk up from cwd.

    Uses the strict check `_looks_like_repo_root` (3 markers required)
    to avoid the v6.x bug where a sub-archive `.claude/.claude/` was
    mistaken for the real root. See the module docstring for the
    untrusted-clone risk when CLAUDE_PROJECT_DIR is absent.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        p = Path(env).resolve()
        if _looks_like_repo_root(p):
            return p
    cwd = Path.cwd().resolve()
    for cand in [cwd, *cwd.parents]:
        if _looks_like_repo_root(cand):
            return cand
    return cwd


def _crash_exit_code(module: str) -> int:
    return _HOOK_ALLOW if module in INFORMATIONAL_HOOKS else _HOOK_DENY


def _report_crash(module: str, exc: BaseException) -> int:
    """Write the 3-line ERROR block (or a WARN for informational hooks)."""
    code = _crash_exit_code(module)
    short = f"{type(exc).__name__}: {str(exc)[:200]}"
    tb = traceback.format_exc(limit=4)
    if code == _HOOK_DENY:
        sys.stderr.write(
            f"ERROR: hook {module} crashed — tool call REFUSED (fail-closed)\n"
            f"CAUSE: [HOOK_CRASH] {short}\n"
            f"FIX: corriger le hook (.sdd/python/{module.replace('.', '/')}.py) ; "
            f"traceback ci-dessous. Un hook de protection qui plante n'est "
            f"jamais un laissez-passer.\n"
        )
    else:
        sys.stderr.write(
            f"WARN [HOOK_CRASH] hook informatif {module} a planté ({short}) — "
            f"ignoré (exit 0, jamais bloquant).\n"
        )
    sys.stderr.write(tb)
    sys.stderr.flush()
    return code


def _run_guarded(module: str, args: tuple[str, ...]) -> None:
    sys.argv = [module.split(".")[-1], *args]
    try:
        runpy.run_module(module, run_name="__main__")
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 — wrapper global volontaire
        sys.exit(_report_crash(module, exc))


def run(module: str, *args: str) -> None:
    """Anchor cwd to repo root, then runpy the target module with args.

    Fail-closed : any unhandled exception in the module (including during
    the bootstrap itself) ends in exit 2 unless the module is listed in
    `INFORMATIONAL_HOOKS` (exit 0).
    """
    try:
        root = find_repo_root()
        os.chdir(root)
        py_dir = str(root / ".sdd" / "python")
        if py_dir not in sys.path:
            sys.path.insert(0, py_dir)
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001
        sys.exit(_report_crash(module, exc))
    _run_guarded(module, args)


# v7.0.0 — CLI entry-point conservé (audit CTO 2026-06-07).
# La pattern actuelle (`settings.json` → `python -c "...; import _hook;
# _hook.run('sdd_hooks.X')"`) couvre les invocations hooks runtime. Le
# mode `python _hook.py sdd_hooks.X` reste utilisé par les tests
# d'intégration qui forkent un sous-process pour tester l'isolation env
# vars + le code de sortie réel. Même politique fail-closed que `run()`.
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: python _hook.py <sdd_hooks.module> [args...]\n"
            "       python _hook.py <sdd_admin.statusline> (variant)\n"
        )
        sys.exit(2)
    target_module = sys.argv[1]
    extra_args = tuple(sys.argv[2:])
    run(target_module, *extra_args)
