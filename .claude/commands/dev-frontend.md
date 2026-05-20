# /dev-frontend — Génère le code client d'UNE US

> ⚠️ **Commande interne v7.0.0** — invoquée par /dev-run STEP 6.c.
> Génère 1 US frontend — invoqué en batch par /dev-run.
> Utilisateur final : préférer la commande orchestrante (`/sdd-full` ou `/dev-run`)
> qui gère pré-conditions, idempotence et état. Conservée comme command pour
> debug/inspection ciblée et préservation des chaînes d'invocation documentées.

Invoque l'agent `dev-frontend` pour matérialiser l'US
`workspace/output/us/{n}-{m}-{Name}.md` + le mockup HTML éventuel
`workspace/input/ui/{n}-{m}-{Name}.html` en code client (Pages, Components,
Layouts, theme.css, bootstrap HTML). L'agent planifie inline les
fichiers à produire à partir de l'US + du mockup HTML + des stacks
frontend/ui actifs.

Si l'US n'a aucune contrepartie frontend (US backend pure), l'agent
exit silencieusement avec une ligne `skipped (backend-only US)`.

**1 invocation = 1 US = 1 build frontend.** Pour traiter plusieurs US,
lancer la commande plusieurs fois ou utiliser `/dev-run {n}`.

**Usage :** `/dev-frontend {n}-{m}` — où `{n}-{m}` cible une US existante
(ex. `/dev-frontend 1-2`).

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}-{m}`.

Si absent → demander :
```
Quelle est l'US à matérialiser côté frontend ? (format : {n}-{m}, ex. 1-2)
```

Si format invalide →
```
ERROR: /dev-frontend — argument invalide
CAUSE: "{argument}" ne respecte pas le format {n}-{m}
FIX: relancer /dev-frontend {n}-{m} (ex. /dev-frontend 1-2)
```

---

## STEP 2 — (délégué à l'agent v5.0)

> Les vérifications **US existe**, **mockup HTML cohérent (0 ou 1)**,
> **stack frontend actif**, **stack UI si HTML présent**, **CLAUDE.md
> projet présent**, **project_file présent** sont absorbées par le
> **STEP 0 HARD-GATE** de l'agent `dev-frontend` (Phase A + Phase B).
> Pas de duplication ici. La commande se contente de valider l'argument
> (STEP 1) puis d'invoquer l'agent (STEP 5).

---

## STEP 3 — (délégué à l'agent v5.0)

> Voir STEP 2 ci-dessus. Vérification mockup HTML = HARD-GATE A4.

---

## STEP 4 — (délégué à l'agent v5.0)

> Voir STEP 2 ci-dessus. Vérification stacks frontend + UI = HARD-GATE
> B1 + B5.

---

## STEP 5 — Invoquer l'agent dev-frontend

Lancer l'agent `dev-frontend` (défini dans `.claude/agents/dev-frontend.md`)
avec l'argument `{n}-{m}`. L'agent gère :
- la lecture sélective de l'US, du mockup HTML, des stacks frontend +
  UI actifs
- le plan inline des fichiers client (ou exit silencieux si US
  backend-only)
- la génération de code conforme au mapping du stack (HTML brut
  traduit en composants natifs DS)
- le build loop (max 3 itérations)
- la vérification de fidélité textuelle (libellés HTML présents dans
  le markup généré)
- la confirmation 1 ligne

Attendre la fin de l'agent. Relayer sa sortie telle quelle.

---

## STEP 6 — Confirmation finale

Si l'agent réussit avec génération, ajouter UNE SEULE ligne :
```
Prochaine étape : si l'US a une partie backend, lancer /dev-backend {n}-{m}.
```

Si l'agent réussit en `skipped` ou échoue, ne rien ajouter.

---

## Règles de cette commande

- **Une seule US par invocation.**
- Pas de Q/R utilisateur après le STEP 1
- Pas de modification des US, mockups HTML ou stack
- Pas de génération de tests (QA hors scope)
- Pas de lecture des FEATs
