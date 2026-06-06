# FEAT: Calc-Backend-Python

FEAT ID: 13-Calc-Backend-Python
Status: Draft

## Context
FEATs 1-12 ont validé runtime 17/18 combinaisons (3 backends REST × 4 fronts SPA, 5 fullstack monolithes, 1 mobile scaffold). Pour clore la matrice de substitution backend, on enchaîne sur **Python FastAPI** sur le même port :44329 substituant Node Express, sans modification des 4 fronts (contrat HTTP préservé).

## Objective
Substituer le backend Node Express par FastAPI + Pydantic + Uvicorn sur :44329, exposant `POST /api/calc {a,b} → {c}` + Swagger UI auto-généré + CORS multi-origins, consommé sans modification par les 4 SPA fronts existants.

## Quantified Goal
- Metric: 4/4 SPA fronts consomment FastAPI sans rebuild
- Target: 100 % (12 cross-origin curl OK)
- Deadline: 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: réponse < 200ms p95 (FastAPI async)
- Data retention: n/a (stateless)
- Compliance: n/a
- Integration: 4 fronts SPA sur :5186, :5004, :5180, :4200 (CORS allowlist héritée)
- Degraded mode: payload invalide → 422 Pydantic validation error JSON ; erreur runtime → 500 JSON

## Actors
- Tech Lead
- Système Back Python: FastAPI + Pydantic + Uvicorn async
- Système Front: 4 SPA invariants

## Functional Needs
- SFD-1: endpoint async `POST /api/calc` body Pydantic → 200 JSON `{c:int}`
- SFD-2: documenter via Swagger UI auto `/docs` (OpenAPI 3.1 généré par FastAPI)
- SFD-3: validation Pydantic auto `int` strict (stack §1.4 — Pydantic models inline)
- SFD-4: logger structuré structlog (stack §1.4 — pas de print)
- SFD-5: CORS middleware multi-origins (cf. `library-and-stack.md §B`)

## Business Rules
- BR-1: `a` et `b` int signés (Pydantic `int` strict — sinon 422)
- BR-2: calcul stateless in-memory
- BR-3: pas d'authentification
- BR-4: Python 3.12+ + uv ou pip + uvicorn[standard] ASGI

## Acceptance Criteria
- AC-1: backend FastAPI démarré sur :44329, `POST /api/calc {a:5,b:5}` → 200 `{"c":10}` en < 200ms
- AC-2: `GET /docs` retourne UI Swagger interactive ; `GET /openapi.json` retourne OpenAPI 3.1 valide avec endpoint POST /api/calc documenté
- AC-3: `POST /api/calc {a:"abc",b:5}` → 422 Pydantic validation error structured JSON
- AC-4 (cross-cutting) : les 4 SPA consomment l'API en cross-origin sans rebuild — vérifié curl preflight depuis chaque port

## Dependencies
- 1-Calc-A-B-C (contrat HTTP identique)

## Functional Deliverables
- FD-1: `main.py` ASGI app FastAPI + CORS middleware + structlog
- FD-2: `routers/calc.py` + `schemas/calc.py` Pydantic
- FD-3: `pyproject.toml` (uv) ou `requirements.txt` (pip)
- FD-4: `uvicorn` ASGI server async config

## Out of Scope
- SQLAlchemy + Alembic (stateless)
- Authentification JWT
- slowapi rate limiting strict
- pytest tests
- Multi-version OpenAPI
