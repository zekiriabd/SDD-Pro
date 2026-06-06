# FEAT: Calc-Web-UI-Angular

FEAT ID: 5-Calc-Web-UI-Angular
Status: Draft

## Context
Suite FEATs 1-4 (Kotlin back + React + Blazor + Vue). Bench Angular standalone consommant la même API Kotlin.

## Objective
SPA Angular standalone avec 3 champs A/B/C consommant POST /api/calc, port :4200 (convention Angular).

## Quantified Goal
- Metric: parité AC avec FEAT 2, 3, 4
- Target: 100 %
- Deadline: 2026-06-05 session bench

## Non-Functional Constraints
- Expected volume: n/a
- Performance SLA: < 200ms
- Data retention: n/a
- Compliance: n/a
- Integration: Kotlin :44329, CORS :4200 OK
- Degraded mode: erreur visible

## Actors
- Tech Lead
- Système Front Angular
- Système Back Kotlin

## Functional Needs
- SFD-1: page Angular 3 champs
- SFD-2: ngModel saisie entiers
- SFD-3: bouton + HttpClient
- SFD-4: affichage C
- SFD-5: erreur visible

## Business Rules
- BR-1: int32 signé
- BR-2: calcul backend
- BR-3: pas d'auth
- BR-4: environment.apiBaseUrl ou hardcoded

## Acceptance Criteria
- AC-1: A=5 B=5 + Calculate → C=10
- AC-2: back down → alerte
- AC-3: champ vide → bouton disabled

## Dependencies
- 1-Calc-A-B-C

## Functional Deliverables
- FD-1: composant `AppComponent` standalone
- FD-2: HttpClient injection
- FD-3: gestion erreur RxJS / try

## Out of Scope
- Routing
- Material/Radzen UI
- Tests Jasmine
