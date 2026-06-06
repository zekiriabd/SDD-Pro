# FEAT: Calc-Backend-Node

FEAT ID: 6-Calc-Backend-Node
Status: Draft

## Context
FEATs 1-5 ont livré le backend Kotlin Spring Boot puis substitué par .NET 10 Minimal API sur le même port :44329, consommé par 4 frontends (React, Blazor, Vue, Angular) sans modification. Pour boucler le bench multi-backend, on enchaîne sur Node.js Express + TypeScript strict + Pino + Zod + Swagger (stack `backend/node-express.md`).

## Objective
Substituer le backend .NET par un backend Node.js Express TypeScript sur le **même port :44329**, exposant le même contrat `POST /api/calc {a,b} → {c=a+b}` + Swagger UI, sans modification d'aucun des 4 fronts.

## Quantified Goal
- Metric: parité fonctionnelle stricte avec backends Kotlin (FEAT 1) et .NET (FEAT 6 antérieur)
- Target: les 4 fronts consomment Node sans rebuild (3 AC × 4 fronts = 12 cas runtime tous 🟢)
- Deadline: session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: réponse < 200ms p95 (calcul trivial + Express overhead minimal)
- Data retention: n/a (stateless)
- Compliance: n/a
- Integration: 4 fronts existants sur :5186, :5004, :5180, :4200 (CORS allowlist héritée)
- Degraded mode: payload invalide → 400 ProblemDetail Zod ; erreur runtime → 500 ProblemDetail global handler

## Actors
- Tech Lead: opérateur bench
- Système Back Node: Express 4 + TypeScript strict
- Système Front: les 4 SPA existants (inchangés)

## Functional Needs
- SFD-1: exposer `POST /api/calc` body JSON `{a:int, b:int}` → 200 `{c:int}`
- SFD-2: documenter via Swagger UI à `/api-docs` (obligation stack §1.6)
- SFD-3: valider input via Zod (stack §1.4 — Schemas Zod inline)
- SFD-4: logger structuré Pino (stack §1.4 — pas de console.log)
- SFD-5: CORS allowlist explicite multi-port (cf. `library-and-stack.md §B`)

## Business Rules
- BR-1: `a` et `b` doivent être des entiers (Zod `z.number().int()`) — sinon 400
- BR-2: calcul in-memory stateless (cf. FEAT 1 BR-2 identique)
- BR-3: pas d'authentification (cf. FEAT 1 BR-3 identique)
- BR-4: TypeScript strict (`noUncheckedIndexedAccess`, ESM `"type": "module"`) — stack §1.4 ajouts Node

## Acceptance Criteria
- AC-1: backend Node démarré sur :44329, `POST /api/calc {a:5,b:5}` → 200 `{"c":10}` en < 200ms
- AC-2: `GET /api-docs` retourne UI Swagger interactive ; `GET /api-docs.json` retourne OpenAPI 3.0.3 valide avec endpoint POST /api/calc documenté
- AC-3: `POST /api/calc {a:"abc",b:5}` → 400 ProblemDetail RFC 7807 avec `errors.a: [...]` Zod
- AC-4 (cross-cutting) : les 4 fronts consomment l'API en cross-origin sans rebuild — vérifié par curl preflight OPTIONS depuis chaque port (5186, 5004, 5180, 4200)

## Dependencies
- 1-Calc-A-B-C (FEAT backend Kotlin — contrat HTTP cible identique)

## Functional Deliverables
- FD-1: app.ts Express + helmet + cors + compression + rate-limit + pino-http + swagger-ui
- FD-2: routes/calc.routes.ts + schemas/calcSchemas.ts (Zod) + services/calcService.ts
- FD-3: swagger/swaggerConfig.ts (swagger-jsdoc) + middleware/errorHandler.ts
- FD-4: server.ts (entry) + graceful shutdown SIGINT/SIGTERM

## Out of Scope
- Prisma / DB (capability `prisma` non triggered — bench stateless)
- Authentification JWT (cf. BR-3)
- Rate limiting strict (configuré permissif pour bench)
- Tests vitest (déclaration QA séparée, hors scope code applicatif dev-*)
- Routing multi-version (1 endpoint v1 unique, pas de `Asp.Versioning` équivalent)
