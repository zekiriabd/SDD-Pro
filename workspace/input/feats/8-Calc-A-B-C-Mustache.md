# FEAT: Calc-A-B-C-Mustache

FEAT ID: 8-Calc-A-B-C-Mustache
Status: Draft

## Context
FEAT 7 a livré Blazor Server (fullstack monolithe SignalR + Razor server-rendered avec hydration). Pour boucler le bench fullstack côté JVM, on enchaîne sur **kotlin-mustache** : Spring Boot 3 Kotlin + Mustache template engine, HTML 100 % server-rendered classique (form POST → page reload, pas de JS bundler, pas de SignalR).

## Objective
Servir une application Spring Boot Kotlin monolithique qui rend une page HTML via Mustache template, contient un formulaire POST `/calc` avec champs A et B, et affiche le résultat C dans la même page après soumission (pattern web SSR classique).

## Quantified Goal
- Metric: parité fonctionnelle AC avec FEAT 7 (Blazor Server) en pattern SSR classique
- Target: 100 % (3 AC couverts dans 1 seul projet monolithe JVM)
- Deadline: session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: première page rendue < 100ms (stack §1.1 promesse "pas d'hydration JS, pas de download bundle")
- Data retention: n/a (stateless, scope requête HTTP)
- Compliance: n/a
- Integration: aucune (monolithe), pas de backend externe
- Degraded mode: erreur conversion int → re-render page avec message erreur Mustache

## Actors
- Tech Lead: opérateur bench
- Système FullStack (Kotlin Mustache): UI HTML + Spring Boot fusionnés

## Functional Needs
- SFD-1: page `GET /` rendue via template `index.mustache` avec formulaire 3 champs A, B, C
- SFD-2: action `POST /calc` qui reçoit A et B en form-data, calcule C, render même template avec C populated
- SFD-3: validation @Min/@Max sur A, B (int signé) — sinon re-render avec erreur
- SFD-4: pas de JS bundler, pas de SPA — interactivité native HTML form
- SFD-5: HTTP 200 sur GET et POST, HTML retourné avec content-type `text/html;charset=UTF-8`

## Business Rules
- BR-1: A et B sont des Int Kotlin (form @RequestParam Int) — type-safe binding Spring
- BR-2: calcul C=A+B exécuté côté contrôleur Spring (preuve SSR : C est dans le HTML retourné, pas calculé client-side)
- BR-3: aucune authentification
- BR-4: pas de capability HTMX ni Alpine.js (bench minimal — soumission form classique avec reload page)

## Acceptance Criteria
- AC-1: application démarrée sur :44349, `GET /` retourne 200 + HTML avec formulaire (A, B, C, bouton submit)
- AC-2: `POST /calc` avec form-data `a=5&b=5` retourne 200 + HTML avec C=10 affiché dans le champ C de la même page
- AC-3: `POST /calc` avec `a=abc&b=5` retourne 400 (erreur Spring binding) OU 200 avec message erreur Mustache (selon design controller)

## Dependencies
- NONE (fullstack autonome)

## Functional Deliverables
- FD-1: `src/main/kotlin/.../CalcController.kt` (@Controller avec GET / et POST /calc, return template name)
- FD-2: `src/main/resources/templates/index.mustache` (HTML form avec placeholders Mustache)
- FD-3: projet Spring Boot Kotlin Gradle scaffoldé avec spring-boot-starter-mustache + web

## Out of Scope
- Persistance JPA (stateless)
- Authentification Spring Security
- HTMX / Alpine.js (capabilities)
- Tests JUnit (hors scope code applicatif dev-*)
- Theming / i18n
- API REST `@RestController` (uniquement MVC controller)
