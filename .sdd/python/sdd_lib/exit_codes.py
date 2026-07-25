"""SDD_Pro standard exit codes (v7.0.0 P1, 2026-05-20).

Convention unifiée pour tous les scripts `sdd_scripts/` et `sdd_admin/`.
Avant v7.0.0, chaque script inventait sa propre convention (0/1/2/3/4/5
selon les cas, parfois `exit 1 = succès` pour `mark_breaking_resolved.py`).
Cette hétérogénéité piègeait les callers bash `cmd || handle_error` et
rendait le pipeline `build_loop` fragile.

Convention canonique :

| Exit | Sens | Comportement caller attendu |
|---:|---|---|
| `0` | SUCCESS — operation completed, side-effects applied | continue |
| `1` | FAIL_FAST — erreur bloquante non-correctible (config, contrat) | STOP + ERROR |
| `2` | CORRECTIBLE — erreur récupérable par retry/edit (build, lint) | retry max BuildLoopMaxIter |
| `3` | INFRA_BLOCKED — outil/DB/réseau down (pas une régression code) | STOP + ERROR différent |

Cas hors convention (legacy granular — préservés pour [CLASS] granularity) :
  - `mark_breaking_resolved.py` : ✅ MIGRÉ v7.0.0 (0=SUCCESS, 3=INFRA_BLOCKED).
    Discrimination marked/skipped via stdout [OK]/[SKIP] ou env-export.
  - `validate_us_deps.py` exit 3 = cycle, exit 4 = missing ref, exit 5 =
    infra error (granularité utile pour la classification d'erreur, mais
    dévie de la convention 0/1/2/3) — préservé par design.
  - `set_us_status.py` exit 1-5 granular (US_NOT_FOUND, US_STATUS_INVALID,
    US_STATUS_TRANSITION_INVALID, US_STATUS_PARSE_ERROR, I/O) — préservé.
  - `sdd_review.py` exit 2 = invalid --fail-on, exit 3 = sources missing
    (ensure-scans flag) — préservé.
  - `phase_planner.py` exit 2 = STACK_MALFORMED granularité — préservé.

  Régularisations audit consolidé 2026-06-07 Sprint 2 (étaient transgressions
  non documentées M10-M14) :
  - `bench_run.py` exit 4 = snapshot-before unreadable (I/O error sur fichier
    JSON d'état antérieur au bench) — distinct de 3 (INFRA general) pour
    permettre au caller de re-run avec snapshot fresh ; préservé par design.
  - `ingest_axe.py` exit 4 = verdict 🔴 RED depasse threshold (sans `--no-fail`)
    — distinct de 1 (FAIL_FAST config) car le code généré est OK, seul le
    rapport accessibilité indique une régression. Caller CI peut différencier
    config-error (1) vs rapport-red (4). Préservé.
  - `ingest_lighthouse.py` exit 4 = idem ingest_axe (verdict 🔴 perf).
  - `compute_us_complexity.py` exit 5 = I/O error sur écriture metadata
    (file permission denied OU disk full) — distinct de 3 (INFRA general)
    pour préciser que la cause-racine est filesystem write, pas réseau ou
    DB. Préservé.
  - `migrate_us_v1_to_v2.py` exit 5 = migration partielle avec ≥ 1 fichier
    en erreur — distinct de 1 (FAIL_FAST tout-ou-rien) car certains US ont
    pu être migrés ; caller peut décider relancer sur le subset failed.
    Préservé.

Pour les nouveaux scripts : utiliser exclusivement les constantes ci-dessous.
Toute nouvelle dérogation (exit 4/5/6) DOIT être documentée ici avec
rationale explicite, sinon `framework_smoke.py` check `no hardcoded return [0-3]`
émettra un WARN (gate non-bloquant mais signalé).
"""
from __future__ import annotations

# Standard exit codes (SDD scripts under sdd_scripts/ + sdd_admin/)
SUCCESS = 0
FAIL_FAST = 1            # Config invalide, contrat violé, FEAT introuvable, etc.
CORRECTIBLE = 2          # Build error retry-able, lint warning, validation soft
INFRA_BLOCKED = 3        # Outil absent, DB down, réseau timeout, FS read-only

# Aliases sémantiques (lisibilité)
OK = SUCCESS
BLOCKING_ERROR = FAIL_FAST
RETRY_POSSIBLE = CORRECTIBLE
ENV_PROBLEM = INFRA_BLOCKED

# === Claude Code hook protocol (sdd_hooks/ uniquement) ===
# Distinct de la convention SDD scripts ci-dessus — Claude Code définit
# son propre protocole pour les hooks (PostToolUse, SubagentStop, Stop,
# UserPromptSubmit, etc.) :
#   exit 0  → allow (continuer normalement)
#   exit 2  → deny / block (afficher stderr à l'utilisateur, bloquer
#             l'action déclenchant le hook). NE PAS confondre avec
#             SDD CORRECTIBLE — sémantique totalement différente.
# Les 6 hooks de sdd_hooks/ utilisent EXCLUSIVEMENT ces constantes.
HOOK_ALLOW = 0
HOOK_DENY = 2


# Inversion guards — utilitaires pour les callers Python qui veulent
# une interprétation sémantique plutôt que numérique
def is_success(code: int) -> bool:
    """True iff exit code = 0."""
    return code == SUCCESS


def is_correctible(code: int) -> bool:
    """True iff exit code = 2 (caller may retry)."""
    return code == CORRECTIBLE


def is_infra_problem(code: int) -> bool:
    """True iff exit code = 3 (caller should not retry, env is broken)."""
    return code == INFRA_BLOCKED


def is_fatal(code: int) -> bool:
    """True iff exit code = 1 (config/contract violation — never retry)."""
    return code == FAIL_FAST


def describe(code: int) -> str:
    """Human-readable label for an exit code."""
    return {
        0: "SUCCESS",
        1: "FAIL_FAST (config/contract violation)",
        2: "CORRECTIBLE (retry possible)",
        3: "INFRA_BLOCKED (env/tool problem)",
    }.get(code, f"UNKNOWN ({code})")
