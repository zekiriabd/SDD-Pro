# FEAT: Calc-Web-UI-Vue

FEAT ID: 4-Calc-Web-UI-Vue
Status: Draft

## Context
Suite des FEATs 1-3 (Kotlin back + React + Blazor). Bench Vue 3 + Vite + Composition API consommant la même API Kotlin pour valider parité fonctionnelle multi-framework front.

## Objective
SPA Vue 3 avec 3 champs A/B/C, bouton Calculate qui POST sur backend Kotlin, affichage résultat C.

## Quantified Goal
- Metric: parité AC avec FEAT 2 et 3
- Target: 100 %
- Deadline: 2026-06-05 session bench

## Non-Functional Constraints
- Expected volume: n/a
- Performance SLA: réponse < 200ms
- Data retention: n/a
- Compliance: n/a
- Integration: Kotlin backend :44329 (CORS allowlist élargie)
- Degraded mode: message erreur si back down

## Actors
- Tech Lead
- Système Front Vue
- Système Back Kotlin

## Functional Needs
- SFD-1: page Vue avec 3 champs
- SFD-2: saisie entiers
- SFD-3: bouton + appel POST
- SFD-4: affichage C readonly
- SFD-5: erreur visible si KO

## Business Rules
- BR-1: int32 signé
- BR-2: calcul backend only
- BR-3: pas d'auth
- BR-4: VITE_API_BASE_URL ou fallback :44329

## Acceptance Criteria
- AC-1: A=5 B=5 + Calculate → C=10 affiché
- AC-2: back down → alerte
- AC-3: champ vide → bouton disabled

## Dependencies
- 1-Calc-A-B-C

## Functional Deliverables
- FD-1: page Vue `/`
- FD-2: composable fetch typé
- FD-3: gestion erreur

## Out of Scope
- Routing
- Vuex/Pinia
- i18n
- Tests Vitest
