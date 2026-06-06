# FEAT: Calc-Web-UI-Blazor

FEAT ID: 3-Calc-Web-UI-Blazor
Status: Draft

## Context
La FEAT 1 a livré un backend Kotlin Spring Boot (`/api/calc`). La FEAT 2 a livré un frontend React. Pour valider que SDD_Pro peut générer un frontend Blazor WebAssembly équivalent (même AC, même backend), on enchaîne sur la techno Microsoft.

## Objective
Servir une page Blazor WebAssembly unique avec trois champs A/B/C consommant l'API Kotlin `POST /api/calc`, build `dotnet run` et test runtime via curl + navigateur.

## Quantified Goal
- Metric: parité fonctionnelle UI avec frontend React (FEAT 2)
- Target: 100 % (3 AC couverts identiques)
- Deadline: session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench unitaire local)
- Performance SLA: rendu initial < 3s (WebAssembly bootstrap), réponse Calculate < 200ms
- Data retention: n/a
- Compliance: n/a
- Integration: backend Kotlin `http://localhost:44329/api/calc` (CORS allowlist déjà élargie)
- Degraded mode: backend down → message d'erreur lisible

## Actors
- Tech Lead: opérateur bench
- Système Front (Blazor): SPA WebAssembly
- Système Back (Kotlin): backend FEAT 1

## Functional Needs
- SFD-1: afficher page Blazor avec 3 champs A, B, C
- SFD-2: saisie entiers signés A et B
- SFD-3: bouton Calculate → POST /api/calc
- SFD-4: afficher résultat C en lecture seule
- SFD-5: message d'erreur si backend down ou 400

## Business Rules
- BR-1: A et B = int32 signés
- BR-2: C calculé par backend uniquement
- BR-3: pas d'authentification
- BR-4: URL backend depuis appsettings ou hardcoded `http://localhost:44329`

## Acceptance Criteria
- AC-1: étant donné Blazor démarré et backend up, saisir A=5 B=5 + clic Calculate → C=10 affiché < 1s
- AC-2: backend down → message d'erreur visible, app pas crashée
- AC-3: A vide → bouton désactivé OU message validation

## Dependencies
- 1-Calc-A-B-C (backend Kotlin)

## Functional Deliverables
- FD-1: page Blazor `/` avec 3 champs + bouton
- FD-2: service HTTP injecté qui appelle POST /api/calc
- FD-3: gestion d'erreur visible

## Out of Scope
- Routing multi-pages
- Authentification
- i18n
- Theming
- Tests bUnit (vérification manuelle suffit)
