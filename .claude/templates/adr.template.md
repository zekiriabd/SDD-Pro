# ADR-{nnn} — {Titre}

- **Statut** : {Proposed | Accepted | Deprecated | Superseded by ADR-XXX}
- **Date** : {YYYY-MM-DD}
- **Auteur** : {agent ou commande, ex: arch / dev-backend / Tech Lead}
- **Phase** : {1-FEAT | 2-US | 3-UI | 4-ARCH | 5-CODE}

---

## Context

> Contexte de la décision en 2-4 phrases. Ce qui motive le choix
> (contrainte stack, exigence métier, limitation technique observée).
> Pas d'option d'implémentation — uniquement les faits.

---

## Decision

> La décision retenue, formulée comme une affirmation. Inclure le
> *quoi* (technologie, pattern, règle) et la portée (projet entier,
> US spécifique, layer précis).

---

## Consequences

> Effets attendus de la décision, positifs ET négatifs.

**Positifs :**
- <conséquence positive 1>

**Négatifs / dette acceptée :**
- <conséquence négative ou contrainte ajoutée>

---

## Alternatives considérées

> Options écartées, avec une phrase de justification chacune. Si la
> décision est imposée par le stack ou la FEAT, écrire `NONE — imposé
> par {raison}`.

- **<alternative-1>** : écartée car <raison>
- **<alternative-2>** : écartée car <raison>

---

## Liens

- FEAT : `workspace/input/feats/{n}-{Name}.md` (si applicable)
- US : `workspace/output/us/{n}-{m}-{Name}.md` (si applicable)
- Stack : `.claude/stacks/{cat}/{stack}.md` (si applicable)
- ADRs liés : ADR-XXX (si superseded ou dépendance)
