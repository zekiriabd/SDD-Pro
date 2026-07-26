# FEAT: CalcABC

FEAT ID: 1-CalcABC
Status: Draft

## Context

Baseline de non-régression pour le conformance run multi-harness/multi-provider
SDD-Pro. Aucun système existant : la fixture décrit une calculette web minimale
tenant sur un écran (input A, input B, opérateur +/-/×/÷, résultat) — assez
simple pour être régénérable en ≤ 2 US et tenir dans les 21 déclinaisons
bench (`.NET`, `Node`, `Python`, `Blazor`, `Angular`, `Nuxt`, `Next.js`, `Vue`,
`React Native`, `MAUI`, `Kotlin Android`, `Delphi FMX` …), assez complète pour
exercer les 3 couches SDD (backend endpoint / frontend page / QA test).

Le rôle de cette fixture : offrir un artefact **stable** que `conformance_run.py`
peut charger à chaque combo `harnais × provider` pour comparer les sorties
sémantiquement (structures d'US, plan technique, code généré) contre une
baseline Claude Code × Anthropic figée. Toute dérive = `[CONFORMANCE_DRIFT]`.

## Objective

Fournir un scénario minimal, autosuffisant et testable, régénérable en < 5 min
sous tout combo `harnais × provider` cible, produisant un code fonctionnel qui
passe le smoke test manuel `2 + 3 = 5` sans intervention humaine.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: coverage lignes tests unitaires backend + frontend confondus
- Target: ≥ 80% (`CoverageMin` défaut Project Config)
- Deadline: n/a (baseline permanente — pas de deadline calendaire)

## Non-Functional Constraints (v7.0.0)

- Expected volume: n/a (fixture, jamais déployée en production)
- Performance SLA: n/a
- Data retention: n/a (opération pure, aucune persistance)
- Compliance: n/a
- Integration: n/a (autosuffisante, pas de dépendance externe)
- Degraded mode: n/a

## Actors

- User: personne quelconque qui saisit A et B, choisit un opérateur, lit le résultat.

## Functional Needs

- SFD-1: Saisir deux nombres décimaux (A et B) via deux champs texte distincts.
- SFD-2: Sélectionner l'un des 4 opérateurs arithmétiques (+, -, ×, ÷) via un contrôle unique.
- SFD-3: Calculer et afficher le résultat de l'opération sur A et B avec l'opérateur choisi.
- SFD-4: Signaler proprement la division par zéro (B=0 avec ÷) sans crash ni valeur `Infinity`/`NaN` exposée à l'utilisateur.

## Business Rules

- BR-1: Le calcul est exécuté **côté backend** (endpoint HTTP) — pas de calcul JavaScript client-side. Objectif : le conformance run vérifie la parité back/front sur tous les combos.
- BR-2: Division par zéro (opérateur ÷ avec B=0) → HTTP 400 côté API, message d'erreur non-technique côté UI.
- BR-3: Précision : opérations en `double` (IEEE 754), résultat renvoyé arrondi à 10 décimales max pour lisibilité.

## Acceptance Criteria

- AC-1: `POST /api/calc { "a": 2, "b": 3, "op": "+" }` retourne `{ "result": 5 }` en HTTP 200.
- AC-2: `POST /api/calc { "a": 10, "b": 4, "op": "-" }` retourne `{ "result": 6 }`.
- AC-3: `POST /api/calc { "a": 7, "b": 8, "op": "*" }` retourne `{ "result": 56 }`.
- AC-4: `POST /api/calc { "a": 20, "b": 4, "op": "/" }` retourne `{ "result": 5 }`.
- AC-5: `POST /api/calc { "a": 1, "b": 0, "op": "/" }` retourne HTTP 400 avec un body `{ "error": "division by zero" }` (ou équivalent i18n).
- AC-6: L'UI présente 2 champs de saisie numérique + un sélecteur d'opérateur + un bouton "Calculer" + une zone de résultat, tous visibles sans scroll sur écran 1280×720.
- AC-7: Le sélecteur d'opérateur propose exactement les 4 valeurs `+ - × ÷` (visuel ; les codes envoyés au backend sont `+ - * /`).

## Required Stack (fixture — override par le harnais du conformance run)

<Fixture polyvalente : les stacks réels sont ceux du `stack.md.fixture`
compagnon. `/feat-validate` sur cette fixture accepte tout combo `validated`
listé dans `.sdd/templates/combos.json`.>

- backend: <résolu par stack.md.fixture>
- frontend: <résolu par stack.md.fixture>
- ui: <résolu par stack.md.fixture>
- qa: <résolu par stack.md.fixture>
- auth: none

## Dependencies

- NONE

## Functional Deliverables

- FD-1: Endpoint HTTP `POST /api/calc` (backend) validant les 5 AC arithmétiques (AC-1 à AC-5).
- FD-2: Page unique "Calculatrice" (frontend) matérialisant les AC-6 et AC-7, appelant FD-1.
- FD-3: Tests unitaires backend couvrant les 5 AC arithmétiques + tests unitaires frontend couvrant AC-6/AC-7 (contrat coverage ≥ 80%).

## Out of Scope

- Historique des calculs (ne persiste rien).
- Authentification (endpoint public — c'est une fixture).
- Opérations avancées (racine, puissance, modulo, parenthèses).
- Multi-lignes / expressions composées (2 opérandes fixes, 1 opérateur).
- Responsive design mobile (le test UI cible desktop 1280×720).
- Localisation (labels en français, `division by zero` en anglais côté API).

## Notes

Fixture créée le 2026-07-26 dans le cadre de l'audit R11 (post-migration
multi-harness). Consommée par `.sdd/python/sdd_scripts/conformance_run.py`
(`DEFAULT_FEAT_FIXTURE_NAME = "1-CalcABC.md"`, `FIXTURE_FEAT_REL =
".sdd/experiments/conformance/feats"`). Ne PAS modifier sans coordonner
un re-baseline — toute dérive de contenu fait dériver les comparaisons
de conformance sur tous les combos historisés sous `.sdd/.build/conformance/`.
