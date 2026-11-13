#!/usr/bin/env python3
"""SDD_Pro SubagentStop hook — enforcement de la matrice d'ownership.

Audits the matrice file-ownership.md §1 after each sub-agent dispatch.

- Agent : `agent_type` du payload SubagentStop (audit 2026-11 — l'ancienne
  lecture de `tool_input.subagent_type`, absent de cet événement, faisait
  sortir le hook en ALLOW AVANT tout scan : la matrice n'était jamais
  appliquée en conditions réelles, seuls les tests fabriquaient un faux
  payload).
- Fichiers écrits : extraits du transcript du sous-agent
  (`agent_transcript_path` → tool_use Write/Edit/MultiEdit/NotebookEdit),
  attribution exacte même avec plusieurs agents en parallèle. Repli si le
  transcript est absent/illisible : walk de `workspace/` sur les fichiers
  modifiés depuis $SDD_DISPATCH_START_TS (marker run-id, sinon now-5min) —
  attribution approximative en cas d'agents parallèles.
- Violations journalisées dans workspace/.sys/.audit/ownership-violations.log
- Mode `SDD_AUDIT_OWNERSHIP_MODE` = strict (défaut, session ET CI) | warn | off :
  strict → exit 2 (le sous-agent ne peut pas s'arrêter, il reçoit la liste
  et doit corriger) ; warn → stderr + exit 0 ; off → log seul.
- Limite : une écriture faite via Bash/PowerShell n'apparaît pas dans le
  transcript (le repli walk ne s'applique que sans transcript).

Migrated from .claude/scripts/audit-file-ownership.ps1 (2026-05-13).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import (  # noqa: E402
    get_agent_transcript_path,
    get_caller_agent_type,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.paths import audit_dir_path, workspace_root, normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402


# Matrix extracted from file-ownership.md §1 (must stay in sync)
OWNERSHIP_MATRIX: dict[str, list[str]] = {
    "po": [
        r"^workspace/us/.+\.md$",
        r"^workspace/\.sys/\.context/constitution\.md$",  # append-only §3 §2
    ],
    "arch": [
        r"^workspace/src/[^/]+\.sln$",
        r"^workspace/src/[^/]+/(\w+\.csproj|package\.json|pyproject\.toml|build\.gradle.*)$",
        r"^workspace/src/[^/]+/Entities/.+",
        r"^workspace/src/[^/]+/CLAUDE\.md$",
        r"^workspace/db/.+",
        r"^workspace/\.sys/\.context/(constitution\.md|adrs/.+)$",
    ],
    "dev-backend": [
        r"^workspace/src/[^/]+/(Services|Endpoints|DTOs|Mappers|Validators|Controllers)/.+",
        r"^workspace/src/[^/]+/Program\.cs$",
        r"^workspace/src/[^/]+/Models/.+",
        r"^workspace/plans/.+\.back\.md$",
        r"^workspace/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "dev-frontend": [
        r"^workspace/src/[^/]+/(Pages|Components|Layouts|Auth)/.+",
        r"^workspace/src/[^/]+/wwwroot/.+",
        r"^workspace/src/[^/]+/Program\.cs$",
        r"^.+\.razor\.css$",
        r"^workspace/plans/.+\.front\.md$",
        r"^workspace/\.sys/\.context/adrs/ADR-.+\.md$",
        # desktop/wpf (wpf.md §1.3 layer mapping) — 2026-11-12, décision PO : la
        # matrice ne couvrait que les dossiers web ; un projet WPF + Core écrit
        # Views/ViewModels/Services/Models/Converters/Controls/Resources.
        r"^workspace/src/[^/]+/(Views|ViewModels|Services|Models|Converters|Controls|Resources|Behaviors)/.+",
        r"^workspace/src/[^/]+/(App|MainWindow)\.xaml(\.cs)?$",
        r"^workspace/src/[^/]+/appsettings(\.[A-Za-z]+)?\.json$",
        # Dossiers propres à un projet (bibliothèque métier, etc.) : jamais en dur
        # ici — déclarés par le projet dans PROJECT_EXTRA_FILE (cf. plus bas).
    ],
    "qa": [
        r"^workspace/src/.+\.Tests/.+",
        r"^workspace/src/.+/__tests__/.+",
        r"^workspace/src/.+\.(FEAT|test)\.(ts|tsx|js|jsx)$",
        r"^workspace/src/.+(Test|FEAT)\.kt$",
        r"^workspace/src/.+test_.+\.py$",
        # 2026-07-06 : QA telemetry is SQLite-only (no qa/). The only file
        # the qa agent still writes is the transient api-tests JSON under
        # .sys/.validation/, which ingest_agent_report.py ingests then deletes.
        r"^workspace/\.sys/\.validation/[0-9]+-api-tests\.json$",
    ],
    # `dashboard` retiré v7.0.0 (governance-major-auditors-trim) — remplacé par
    # script déterministe index_adrs.py. Aucune entrée matrice nécessaire.
    "elicitor": [
        r"^workspace/feats/.+\.md$",  # append-only
        r"^workspace/\.sys/\.context/constitution\.md$",  # append-only §7
    ],
    # ----------------------------------------------------------------------- #
    # Module db-reverse (base de données → FEAT). Audit 2026-08-29, M3.
    #
    # Ces 6 agents n'avaient AUCUNE entrée ici, alors que la doc de deux d'entre
    # eux annonce une séparation faits/hypothèses « garantie par construction ».
    # Rien ne l'auditait : un Write direct sur la branche de faits de
    # db-context.json ne laissait aucune trace.
    #
    # Deux mécanismes, complémentaires et volontairement distincts :
    #   - `merge_architect_output` (db_context.py) est la whitelist de fusion :
    #     seules les clés de `hypotheses` passent, tout le reste est droppé.
    #     C'est ce qui protège le CONTENU.
    #   - cette matrice est l'audit a posteriori : elle constate quel agent a
    #     touché quel fichier pendant sa fenêtre de dispatch. C'est ce qui
    #     protège le PÉRIMÈTRE.
    #   - le blocage a priori d'un Write direct relève de `protect_framework.py`
    #     (hook PreToolUse), pas d'ici : ce hook-ci tourne APRÈS l'écriture.
    #
    # `db-context.json`, son digest et l'arbre de fiches figurent dans le
    # périmètre de l'architecte parce que le script de fusion qu'il DOIT invoquer
    # (`db_context_build.py --merge-hypotheses`) les régénère pendant sa fenêtre
    # de dispatch. Les y interdire produirait une violation à chaque exécution
    # nominale, et un journal d'audit qui crie toujours n'est plus lu.
    "reverse-db-architect": [
        # Le seul fichier que l'agent écrit lui-même (Phase 0.B).
        r"^workspace/old/[^/]+/\.sys/db-context\.hypotheses\.json$",
        # Régénérés par db_context_build.py, que l'agent invoque.
        r"^workspace/old/[^/]+/\.sys/db-context\.json$",
        r"^workspace/old/[^/]+/\.sys/db-context\.digest\.json$",
        r"^workspace/old/[^/]+/\.sys/db-context\.waves-completed\.json$",
        r"^workspace/old/[^/]+/\.sys/db-context/.+",
    ],
    # Les 4 spécialistes d'objet SQL n'écrivent QU'UNE User Story (1 objet = 1
    # US). Ni FEAT, ni contexte, ni snapshot : le corps qu'ils lisent est
    # produit en amont, en lecture seule, par l'introspection.
    "reverse-sql-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    "reverse-sql-function-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    "reverse-sql-view-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    "reverse-sql-trigger-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    # Rung 2 : compose la FEAT du module, et back-fille les US du module
    # (`Covers:` / `Status` / `Parent FEAT hash`) — cf. l'agent, section
    # anti-derive « Écrit uniquement … (+ Edit back-fill des US du module) ».
    "reverse-sql-feat-composer": [
        r"^workspace/feats/.+\.md$",
        r"^workspace/us/.+\.md$",
    ],
}

# Paths to ignore during ownership audit
IGNORE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.sys/\.audit/"),
    re.compile(r"\.sys/\.state/"),
    re.compile(r"\.tmp$"),
)

# Pre-compiled ownership patterns (M7 fix v7.0.0-alpha 2026-06-05).
# Previously these were re.compile()d inside main() on every SubagentStop —
# 76 patterns × ~6-10 invocations per /sdd-full = wasted CPU on hot path.
# Module-level cache : compiled once at import, reused across invocations.
_COMPILED_OWNERSHIP: dict[str, list[re.Pattern[str]]] = {
    agent: [re.compile(p) for p in patterns]
    for agent, patterns in OWNERSHIP_MATRIX.items()
}


#: Extension de la matrice propre au projet (2026-11-13) : chemins métier d'un
#: projet (ex. dossiers d'une bibliothèque) qu'aucune règle générique ne couvre.
#: Fichier local sous workspace/ (non versionné) : aucun nom de projet client ne
#: vit dans le framework. Format : {"dev-frontend": ["^workspace/src/MaLib/.+"]}.
PROJECT_EXTRA_FILE = Path(".sys") / ".context" / "ownership-extra.json"
#: Une extension ne peut ouvrir que du code applicatif : elle n'élargit jamais
#: un agent sur les specs, l'état du pipeline ou les rapports.
_EXTRA_ALLOWED_PREFIX = "^workspace/src/"


def load_project_extra(workspace: Path) -> dict[str, list[re.Pattern[str]]]:
    """Motifs supplémentaires déclarés par le projet, par agent connu de la matrice.

    Fichier absent → aucune extension. Fichier illisible ou motif invalide →
    WARN et motif ignoré (la matrice reste la plus stricte).
    """
    path = workspace / PROJECT_EXTRA_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warn(f"WARN audit-file-ownership : {PROJECT_EXTRA_FILE} illisible ({type(exc).__name__}) — ignoré")
        return {}
    if not isinstance(data, dict):
        warn(f"WARN audit-file-ownership : {PROJECT_EXTRA_FILE} doit être un objet agent → motifs — ignoré")
        return {}
    extra: dict[str, list[re.Pattern[str]]] = {}
    for agent, patterns in data.items():
        if agent not in OWNERSHIP_MATRIX or not isinstance(patterns, list):
            continue
        for pattern in patterns:
            if not isinstance(pattern, str) or not pattern.startswith(_EXTRA_ALLOWED_PREFIX):
                warn(f"WARN audit-file-ownership : motif ignoré pour {agent} "
                     f"(doit commencer par {_EXTRA_ALLOWED_PREFIX}) : {pattern!r}")
                continue
            try:
                extra.setdefault(agent, []).append(re.compile(pattern))
            except re.error:
                warn(f"WARN audit-file-ownership : motif invalide ignoré pour {agent} : {pattern!r}")
    return extra


def _parse_cutoff() -> datetime:
    """Return cutoff datetime: env $SDD_DISPATCH_START_TS, marker file, or now-5min.

    v7.0.1 : delegated resolution to sdd_lib/run_id helper which scopes the
    cutoff to the current run's start (run_id marker mtime) when the env
    var is not explicitly set. Final fallback remains now-5min for safety.
    """
    raw = os.environ.get("SDD_DISPATCH_START_TS", "").strip()
    if not raw:
        try:
            from sdd_lib.run_id import get_or_create_dispatch_start_ts
            raw = get_or_create_dispatch_start_ts()
        except Exception:
            return datetime.now(timezone.utc) - timedelta(minutes=5)
    # Accept ISO 8601 with optional 'Z' suffix
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc) - timedelta(minutes=5)


# Directories to skip during the workspace walk. These are either
# vendor-managed (node_modules), build artifacts (dist/build/bin/obj/target),
# venvs, caches, or VCS metadata. Including them in the walk wasted seconds
# per SubagentStop on real projects with 50k+ files in node_modules.
# Audit P0-doc 2026-06-05.
_AUDIT_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", "dist", "build", "bin", "obj", "out", "target",
    ".venv", "venv", ".tox", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".gradle", ".angular", ".next", ".nuxt", ".svelte-kit",
    ".vite", ".turbo", "coverage", ".nyc_output",
    ".git", ".hg", ".svn",
    ".idea", ".vscode",
})


def _iter_modified_files_walk(workspace: Path, cutoff: datetime) -> list[Path]:
    """Walk workspace/ and yield files modified after cutoff (fallback).

    Uses `os.walk(topdown=True)` with in-place dirs pruning to skip vendor
    directories (node_modules, .venv, build artifacts, VCS metadata). On a
    real project with 50k+ files under node_modules, this changes the
    SubagentStop latency from seconds to ~100ms.

    This is the sole implementation since the 2026-06-12 audit fix: the
    `git status` fast-path (REFACTOR-2) was removed because it could NEVER
    see the files this hook must audit. The agents write under
    `workspace/`, which is **gitignored by design** — `git status`
    (even with `--untracked-files=all`) does not list ignored files, so the
    fast-path returned 0 files where the walk finds thousands, silently
    disabling the ownership matrix (INVARIANTS.yml `file-ownership-matrix-
    enforced`). The pruned walk (~100ms, vendor dirs skipped) is correct and
    fast enough.
    """
    import os
    cutoff_ts = cutoff.timestamp()
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(workspace, topdown=True):
        # Prune: mutate dirnames in-place to skip vendor/build dirs.
        dirnames[:] = [d for d in dirnames if d not in _AUDIT_SKIP_DIRS]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if full.stat().st_mtime > cutoff_ts:
                    out.append(full)
            except OSError:
                continue
    return out


def _iter_modified_files(workspace: Path, cutoff: datetime) -> list[Path]:
    """Yield files modified after cutoff via a pruned walk of `workspace/`.

    v7.0.1 audit REFACTOR-2 (2026-06-08) introduced a `git status` fast-path;
    the 2026-06-12 audit removed it (see `_iter_modified_files_walk` docstring)
    — the audit targets are gitignored, so git could not see them. This
    indirection is kept as the stable public entry-point in case a
    git-ignored-aware fast-path is reintroduced later.
    """
    return _iter_modified_files_walk(workspace, cutoff)


#: Tools whose `input.file_path` / `notebook_path` is a disk write.
_WRITE_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def _iter_tool_uses(node):
    """Yield every `{"type": "tool_use", ...}` dict nested in a transcript line."""
    if isinstance(node, dict):
        if node.get("type") == "tool_use":
            yield node
        for v in node.values():
            yield from _iter_tool_uses(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_tool_uses(v)


def files_written_from_transcript(transcript: Path, root: Path) -> list[Path] | None:
    """Exact list of files the sub-agent wrote via Write/Edit/MultiEdit/NotebookEdit.

    Audit 2026-11 : avec `MaxParallel: 3`, dev-backend et dev-frontend tournent
    en parallèle — un scan par fenêtre de mtime attribue à l'un les fichiers
    de l'autre (faux positifs → DENY injustifié). Le transcript
    (`agent_transcript_path`, payload SubagentStop documenté) donne
    l'attribution exacte. Limite assumée : une écriture via Bash/PowerShell
    n'apparaît pas ici (couverte a priori par `protect_framework` mode shell).

    Returns None if the transcript is unreadable (caller falls back to the walk).
    """
    try:
        text = transcript.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out: list[Path] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        for tu in _iter_tool_uses(obj):
            if tu.get("name") not in _WRITE_TOOLS:
                continue
            inp = tu.get("input") or {}
            fp = inp.get("file_path") or inp.get("notebook_path")
            if not isinstance(fp, str) or not fp.strip():
                continue
            p = Path(fp)
            if not p.is_absolute():
                p = root / p
            key = normalize(str(p)).lower()
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def _resolve_mode() -> str:
    """`SDD_AUDIT_OWNERSHIP_MODE` = strict|warn|off ; défaut **strict** partout.

    Audit 2026-11 : l'ancien défaut (`warn` interactif, DENY seulement en CI)
    faisait de la matrice d'ownership un simple journal en usage réel. La
    variable est protégée par `block_env_bypass` (`SDD_AUDIT_*`) : un agent ne
    peut pas la positionner à chaud.
    """
    mode = (os.environ.get("SDD_AUDIT_OWNERSHIP_MODE") or "").strip().lower()
    return mode if mode in ("warn", "strict", "off") else "strict"


def main() -> int:
    payload = read_hook_input()
    # SubagentStop porte `agent_type` (pas `tool_input.subagent_type`) —
    # get_caller_agent_type d'abord, get_subagent_type en compat.
    subagent = get_caller_agent_type(payload) or get_subagent_type(payload)
    if not subagent or subagent not in _COMPILED_OWNERSHIP:
        return HOOK_ALLOW
    allowed = _COMPILED_OWNERSHIP[subagent]  # M7 : reuse precompiled patterns

    root = repo_root()
    workspace = workspace_root(root)
    if not workspace.is_dir():
        return HOOK_ALLOW
    allowed = allowed + load_project_extra(workspace).get(subagent, [])

    source = "walk"
    modified: list[Path] | None = None
    transcript = get_agent_transcript_path(payload)
    if transcript:
        modified = files_written_from_transcript(Path(transcript), root)
        if modified is not None:
            source = "transcript"
    if modified is None:
        cutoff = _parse_cutoff()
        modified = _iter_modified_files(workspace, cutoff)
    if not modified:
        return HOOK_ALLOW

    ws_resolved = workspace.resolve()
    violations: list[str] = []
    for f in modified:
        try:
            f.resolve().relative_to(ws_resolved)
        except (ValueError, OSError):
            # Hors workspace : relève de protect_framework (framework) ou
            # n'est pas un livrable — la matrice ne couvre que workspace/.
            continue
        try:
            rel = normalize(f.resolve().relative_to(root.resolve()))
        except (ValueError, OSError):
            rel = "workspace/" + normalize(f.resolve().relative_to(ws_resolved))
        if any(ign.search(rel) for ign in IGNORE_PATTERNS):
            continue
        if not any(pat.match(rel) for pat in allowed):
            violations.append(rel)

    if not violations:
        return HOOK_ALLOW
    audit_dir = audit_dir_path(workspace=workspace)
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_file = audit_dir / "ownership-violations.log"

    timestamp = datetime.now(timezone.utc).isoformat()
    with log_file.open("a", encoding="utf-8") as fh:
        for v in violations:
            fh.write(
                f"{timestamp} [FILE_OWNERSHIP] {subagent} wrote {v} "
                f"(pattern hors matrice ownership.md §1, source={source})\n"
            )

    mode = _resolve_mode()
    if mode == "off":
        return HOOK_ALLOW
    shown = ", ".join(violations[:5]) + (f" (+{len(violations) - 5})" if len(violations) > 5 else "")
    if mode == "warn":
        warn(
            f"WARN audit-file-ownership : {subagent} a ecrit {len(violations)} fichier(s) "
            f"hors matrice ownership.md §1 : {shown}"
        )
        return HOOK_ALLOW
    warn(f"ERROR: audit-file-ownership — {subagent} a ecrit hors de son perimetre")
    warn(f"CAUSE: [FILE_OWNERSHIP] {len(violations)} fichier(s) hors matrice ownership.md §1 "
         f"(source={source}) : {shown}")
    warn("FIX: annuler/deplacer ces ecritures (elles appartiennent a un autre agent) puis terminer ; "
         "Tech Lead : SDD_AUDIT_OWNERSHIP_MODE=warn dans l'environnement du process Claude Code "
         "si la matrice est en retard sur un besoin legitime")
    return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
