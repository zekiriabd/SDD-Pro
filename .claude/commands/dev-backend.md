# /dev-backend — Génère le code serveur d'UNE US

> ⚠️ **Commande interne v7.0.0** — invoquée par `/dev-run` STEP 6.a (batch 1 US).
> Utilisateur final : préférer `/sdd-full` ou `/dev-run` (gèrent pré-conditions, idempotence, état).

Invoque l'agent `dev-backend` pour matérialiser l'US
`workspace/output/us/{n}-{m}-{Name}.md` en code serveur (services, endpoints,
DTOs, entities, mappers, Program.cs, middleware). L'agent planifie
inline les fichiers à produire à partir de l'US + du stack actif.

Si l'US n'a aucune contrepartie backend (US frontend pure), l'agent
exit silencieusement avec une ligne `skipped (frontend-only US)`.

**1 invocation = 1 US = 1 build backend.** Pour traiter plusieurs US,
lancer la commande plusieurs fois ou utiliser `/dev-run {n}`.

**Usage :** `/dev-backend {n}-{m}` — où `{n}-{m}` cible une US existante
(ex. `/dev-backend 1-3`).

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}-{m}` (deux entiers ≥ 1 séparés par un
tiret).

Si absent → demander :
```
Quelle est l'US à matérialiser côté backend ? (format : {n}-{m}, ex. 1-3)
```

Si format invalide →
```
ERROR: /dev-backend — argument invalide
CAUSE: "{argument}" ne respecte pas le format {n}-{m}
FIX: relancer /dev-backend {n}-{m} (ex. /dev-backend 1-3)
```

---

## STEP 2 — Invoquer l'agent dev-backend

Lancer l'agent `dev-backend` (défini dans `.claude/agents/dev-backend.md`)
avec l'argument `{n}-{m}`. L'agent gère :
- la lecture sélective de l'US, du mockup HTML éventuel (passif), du stack actif
- le plan inline des fichiers serveur (ou exit silencieux si US
  frontend-only)
- la génération de code conforme au mapping du stack
- le build loop (max 3 itérations)
- la confirmation 1 ligne

Attendre la fin de l'agent. Relayer sa sortie telle quelle.

---

## STEP 3 — Confirmation finale

Si l'agent réussit avec génération, ajouter UNE SEULE ligne :
```
Prochaine étape : si l'US a une partie frontend, lancer /dev-frontend {n}-{m}.
```

Si l'agent réussit en `skipped` ou échoue, ne rien ajouter.

---

## Règles de cette commande

- **Une seule US par invocation.**
- Pas de Q/R utilisateur après le STEP 1
- Pas de modification des US, mockups HTML ou stack
- Pas de génération de tests (QA hors scope)
- Pas de lecture des FEATs ou d'autres mockups HTML
