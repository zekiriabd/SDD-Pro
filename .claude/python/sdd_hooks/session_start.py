#!/usr/bin/env python3
"""SDD_Pro SessionStart hook — inject SDDPro context at session bootstrap.

Pattern emprunt superpowers v5.1 : injecter au démarrage de chaque
session Claude Code un bref message expliquant que SDDPro est chargé,
listant les commandes user-facing principales.

Coût : 0 token LLM (texte 100 % statique depuis v7.0.0+ audit P2 M4).

**Cache-friendliness v7.0.0+ (audit P2 M4 2026-06-08)** : le banner est
maintenant **100 % statique** (pas de `{state}` interpolé). Les sessions
`resume|compact|clear` réinjectent le même texte byte-identique → le
prompt cache d'Anthropic hit le prefix complet entre sessions. L'état
dynamique du projet n'est PLUS dans le banner ; il est obtenu via
`/sdd-status` (tree ASCII) ou `/sdd-help` (guidance contextuelle).
Justification : un banner variable invalidait le cache à chaque
resume → coût caché récurrent sur workflows longs (compact toutes
les ~30 min).

Idempotent : appelé à chaque `startup|resume|clear|compact` selon
settings.json matcher.

Output : JSON sur stdout avec `hookSpecificOutput.additionalContext`,
format Claude Code SessionStart hook (cf. docs/hooks-and-protections.md).

Bypass : `SDD_DISABLE_SESSION_START=1` → no-op (texte vide).
Mode silencieux CI : `CI=1` env var → texte minimal 1L (toujours
statique, cache-friendly). Évite de polluer les logs CI avec le
banner full.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS  # noqa: E402


# =============================================================================
# Static banners (cache-friendly — byte-identical across sessions)
# =============================================================================
#
# Why "static" matters : Anthropic's prompt cache keys on prefix-identity.
# A banner that interpolates project state (e.g. "3 FEAT(s) detected") would
# differ between resume calls and invalidate the cache, forcing full
# system-prompt re-tokenization on every compact / resume. By keeping the
# banner constant and routing state to user-invoked commands (/sdd-status,
# /sdd-help), the prefix stays cacheable across the entire session lifecycle.

_BANNER_FULL = """# SDDPro v7.0.0+ — FEAT-Driven Development Framework

Framework chargé. **13 commandes user-facing** + **13 agents** spécialisés (12 cœur + `complexity-router` opt-in via script Python déterministe).

## Pipeline canonique (strict, gated)

```
Phase 0 (optionnel)  Discovery (vision, personas, KPIs)  → workspace/input/discovery/
       ↓
Phase 1-2            /feat-generate {Nom} → /us-generate {n} → /feat-validate {n}
       ↓
Phase 4              /dev-run {n}  (arch + DB → back → API gate → front)
       ↓
Phase 5              /qa-generate {n} → /sdd-review {n}  (two-stage v7.0.0+ : spec gate → quality batch)
```

Raccourci A→Z : `/sdd-full {n}` (pipeline complet). POC rapide : `/sdd-poc {n}`.

## Commandes essentielles

| But | Commande |
|---|---|
| Cadrer une FEAT | `/feat-generate <Nom>` |
| Validation gate avant code | `/feat-validate {n}` |
| Pipeline complet A→Z | `/sdd-full {n}` |
| Matérialiser le code | `/dev-run {n}` |
| Audit consolidé | `/sdd-review {n}` |
| **Aide contextuelle "what's next"** | `/sdd-help [{n}\\|"question"]` |
| État brut (tree ASCII) | `/sdd-status [{n}]` |

## Conventions load-bearing

- **Source-first** : tout dans `.md` versionnés, jamais dans mémoire opaque
- **Two-stage auditor** (v7.0.0+) : spec-compliance gate AVANT code/security/arch reviewers — économie ~3 invocations Sonnet sur spec RED
- **File ownership matrix** stricte (`@.claude/rules/ownership.md`) — chaque path a 1 owner
- **Anti-derive** : pas de lib hors `§2.4` du stack, pas de scope hors US, STOP + ERROR sur ambiguïté
- **Stack `.md` = SSoT** des secrets (gitignored). Code lit via `IConfiguration` / `@Value` — jamais `process.env` direct.

> **Pour connaître l'état du projet** : lancer `/sdd-help` (guidance "what's next" — détecte FEAT existantes, gaps pipeline, propose la prochaine commande logique). État brut : `/sdd-status`.
"""

_BANNER_MINIMAL = (
    "SDDPro v7.0.0+ actif (13 commandes, 13 agents). "
    "Pour démarrer : `/sdd-help` (guidance) ou `/sdd-status` (état)."
)


def emit() -> dict:
    """Construit le payload JSON SessionStart à émettre.

    100 % déterministe — la sortie ne dépend QUE des env vars
    `SDD_DISABLE_SESSION_START` et `CI`. Aucune lecture disque, donc le
    `additionalContext` est byte-identique cross-session → cacheable.
    """
    if os.environ.get("SDD_DISABLE_SESSION_START", "").lower() in ("1", "true", "yes", "on"):
        # No-op : émettre un context vide (Claude Code ignore)
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ""}}

    is_ci = os.environ.get("CI", "").lower() in ("1", "true", "yes", "on")
    context = _BANNER_MINIMAL if is_ci else _BANNER_FULL

    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


def _rotate_audit_logs_best_effort() -> None:
    """v7.0.1 audit P1 v2 (2026-06-08) — best-effort audit log rotation.

    Invoked at every session_start (startup|resume|clear|compact) BUT
    throttled to once per 24h via marker file (cf. `rotate_if_due`).
    Cumulative impact on session_start latency : <5 ms when throttled,
    50-100 ms when actually rotating (rare, ~once/day).

    Non-blocking : ANY failure here is silently swallowed (rotation is
    housekeeping, not a security gate). The banner output above is what
    matters for session_start ergonomics.

    Bypass : SDD_DISABLE_SESSION_START=1 already short-circuits the whole
    hook before this is called. No separate bypass needed.
    """
    try:
        from sdd_admin.rotate_audit_logs import rotate_if_due
        rotate_if_due(throttle_hours=24)
    except Exception:
        # Silent : rotation failure must never affect session bootstrap.
        pass


def main() -> int:
    """Entry point. Always exit 0 — never fail the session over a hook error.

    Audit P3 C3 (2026-06-08) narrow scope : catch only recoverable categories
    (OSError, JSON, encoding). System exceptions (KeyboardInterrupt etc.)
    propagate as intended.

    v7.0.1 audit P1 v2 (2026-06-08) — appel best-effort à rotate_audit_logs
    pour housekeeping périodique (throttled 24h via marker file).
    """
    try:
        result = emit()
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
        sys.stdout.write("\n")
        # Best-effort audit log rotation (throttled, non-blocking).
        _rotate_audit_logs_best_effort()
        return SUCCESS
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        # Defensive : session bootstrap continues without our banner.
        sys.stderr.write(f"[SDDPro session_start hook] non-fatal error: {exc}\n")
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ""}
        }, ensure_ascii=False, sort_keys=True))
        sys.stdout.write("\n")
        return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
