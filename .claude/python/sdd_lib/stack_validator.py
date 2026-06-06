"""SDD_Pro shared stack coherence validator (Security audit 2026-06-06, SSoT).

Avant ce module, la validation de cohérence de `stack.md` était dupliquée
(et incohérente) entre :
- `phase_planner.py` : `_validate_stack_coherence()` strict, retourne erreur
- `sdd_full_planner.py` : aucune validation, produit un plan même incohérent
- `validate_readiness.py` : WARN seulement, ne bloque pas

Ce module centralise la logique pour que toute Gate utilise la **même
sémantique**. Cf. R2 audit gates uniformes.

Usage :

    from sdd_lib.stack_validator import validate_active_stacks_coherence

    err = validate_active_stacks_coherence({
        "backend": "node-express",
        "frontend": "react",
        "ui": "shadcn",
        "auth": "auth-local",
        "fullstack": None,
        "mobiles": None,
    })
    if err:
        # err = {'code': '[STACK_MALFORMED]', 'message': '...'}
        ...
"""
from __future__ import annotations

from typing import Any


def validate_active_stacks_coherence(stacks: dict[str, Any]) -> dict[str, str] | None:
    """Retourne `{'code': '...', 'message': '...'}` si incohérent, sinon None.

    Cas couverts (cf. CLAUDE.md §7 matrice AppType) :
    - Aucun stack actif → STACK_EMPTY
    - fullstack + (backend OR frontend) → mutuellement exclusif
    - frontend + mobiles → frontendKind unique
    - fullstack + mobiles → idem

    Aucun cas n'est marqué WARN — toute incohérence est bloquante car
    elle empêche la sélection univoque d'AppType par les commands.
    """
    active = {k: v for k, v in stacks.items() if v}
    if not active:
        return {
            "code": "STACK_MALFORMED",
            "message": (
                "aucun stack actif dans workspace/input/stack/stack.md — "
                "décommenter au moins un stack backend/frontend/fullstack/mobiles "
                "dans `## Active Tech Specs`."
            ),
        }
    has_fullstack = bool(stacks.get("fullstack"))
    has_backend = bool(stacks.get("backend"))
    has_frontend = bool(stacks.get("frontend"))
    has_mobiles = bool(stacks.get("mobiles"))

    if has_fullstack and (has_backend or has_frontend):
        return {
            "code": "STACK_MALFORMED",
            "message": (
                f"mix interdit : fullstack/* est mutuellement exclusif avec "
                f"backend/* et frontend/* (détecté: fullstack={stacks.get('fullstack')!r} "
                f"+ backend={stacks.get('backend')!r} + frontend={stacks.get('frontend')!r})."
            ),
        }
    if has_frontend and has_mobiles:
        return {
            "code": "STACK_MALFORMED",
            "message": (
                f"mix interdit : frontend/* et mobiles/* sont mutuellement exclusifs "
                f"(frontendKind unique) — détecté: frontend={stacks.get('frontend')!r} "
                f"+ mobiles={stacks.get('mobiles')!r}."
            ),
        }
    if has_fullstack and has_mobiles:
        return {
            "code": "STACK_MALFORMED",
            "message": (
                f"mix interdit : fullstack/* + mobiles/* — décider un AppType unique "
                f"(fullstack={stacks.get('fullstack')!r} vs mobiles={stacks.get('mobiles')!r})."
            ),
        }
    return None
