# `.claude/stacks/_drafts/` — Quarantined stacks (v7.0.0)

> Stacks **non chargés** par le framework actif. Conservés pour référence
> et reprise éventuelle, mais explicitement exclus de la surface validée.

## Contenu (au 2026-05-20)

| Catégorie | Stacks | Raison de quarantaine |
|---|---|---|
| `fullstack/` (6) | `angular-universal`, `blazor-server`, `kotlin-mustache`, `next`, `node-react`, `nuxt` | Aucun combo `/sdd-full` validé end-to-end. ~3 569 LOC de spec maintenue sans preuve d'exécution. |
| `mobiles/` (2) | `maui`, `react-native` | Idem — `AppType=mobile-*` jamais exercé bout-en-bout. |
| `archi/` (2) | `ddd.md`, `microservice.md` | `ddd` est en YAML pseudo-DSL non parseable par les agents (doc flair) ; `microservice` aspirational. Seul `mvc.md` est exécuté en production. |

## Conséquences runtime

- `framework_smoke.py` **ne valide pas** ces `.libs.json` (filtre `_drafts` dans le `rglob`).
- `validate_libs_catalog.py` **ne valide pas** ces catalogues non plus.
- `arch` Phase A **ne peut pas** matérialiser un projet depuis un stack en `_drafts/` — preflight retournera `STACK_NOT_FOUND` car les paths cherchés sont `.claude/stacks/{cat}/{id}.md`, pas `.claude/stacks/_drafts/{cat}/{id}.md`.
- `CLAUDE.md §7` ne les liste plus dans la table principale.

## Comment réactiver un stack

Procédure (post-freeze v7.0.0, jamais sur `main` pendant freeze) :

1. **Choisir un combo cible** (ex. `next × shadcn × azure-ad`) et l'exécuter end-to-end via `/sdd-full` sur une FEAT pilote (PoC ROI cf. `docs/poc-roi-methodology.md`).
2. **Si le PoC passe** : `git mv .claude/stacks/_drafts/{cat}/{id}.md .claude/stacks/{cat}/{id}.md` (+ `.libs.json` si applicable).
3. **Mettre à jour** `.claude/CLAUDE.md §7` pour le déclasser de quarantaine vers 🟡 ou 🟢 selon résultat du combo.
4. **Ajouter un ADR** `governance-restore-stack-{id}` documentant le PoC, sa date, son verdict.
5. Soumettre PR sur `next`.

## Historique

- **2026-05-20** (v7.0.0) : déplacement initial depuis `fullstack/`, `mobiles/`, `archi/` (ADR `governance-major-stacks-quarantine`).

> Source de vérité combos validés : `.claude/CLAUDE.md §7 "Combos validés bout-en-bout"`.
