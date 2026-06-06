# FEAT: Calc-A-B-C

FEAT ID: 1-Calc-A-B-C
Status: Draft

## Context
Bench end-to-end SDD_Pro : valider que le pipeline complet (FEAT → US → arch → dev → QA → reviewers) génère un backend Kotlin Spring Boot fonctionnel avec un endpoint trivial et Swagger opérationnel. Aucune base de données, aucun frontend, aucune authentification — strict minimum pour mesurer la chaîne de génération de code backend bout-en-bout.

## Objective
Servir un endpoint REST `POST /api/calc` qui prend deux entiers `a` et `b` en payload JSON et retourne leur somme `c = a + b`, documenté et testable via Swagger UI sans intervention manuelle après `/sdd-full 1`.

## Quantified Goal
- Metric: pourcentage de runs `/sdd-full 1` produisant un backend testable Swagger sans intervention manuelle
- Target: 100 %
- Deadline: validation immédiate en session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench unitaire — pas de charge)
- Performance SLA: réponse < 100ms p95 (calcul trivial in-memory)
- Data retention: n/a (stateless, aucune persistance)
- Compliance: n/a (pas de données personnelles)
- Integration: n/a (pas de système externe)
- Degraded mode: n/a (pas de dépendance externe)

## Actors
- Tech Lead: opérateur du bench, soumet `a` et `b` via Swagger UI et vérifie le résultat
- Système: backend Kotlin Spring Boot qui expose l'endpoint et la documentation Swagger

## Functional Needs
- SFD-1: exposer un endpoint REST acceptant deux entiers et retournant leur somme
- SFD-2: fournir une documentation Swagger/OpenAPI auto-générée accessible via navigateur
- SFD-3: valider les entrées et retourner une erreur structurée si payload invalide

## Business Rules
- BR-1: `a` et `b` sont des entiers signés 32 bits (Int côté Kotlin) ; tout autre type renvoie 400 Bad Request
- BR-2: le résultat `c` est calculé en mémoire sans aucune persistance, aucun appel externe, aucun cache
- BR-3: aucune authentification requise (endpoint public, scope strict bench)

## Acceptance Criteria
- AC-1: étant donné le backend démarré, lorsque j'envoie `POST /api/calc` avec body `{"a": 5, "b": 5}`, alors je reçois une réponse 200 avec body `{"c": 10}`
- AC-2: étant donné le backend démarré, lorsque j'ouvre `/swagger-ui.html` (ou équivalent OpenAPI UI exposé par Spring Boot), alors je vois l'endpoint `POST /api/calc` documenté avec son schéma de requête/réponse et un bouton "Try it out" fonctionnel
- AC-3: étant donné le backend démarré, lorsque j'envoie `POST /api/calc` avec un payload invalide (par exemple `{"a": "abc", "b": 5}`), alors je reçois une réponse 400 avec un corps d'erreur structuré indiquant le champ fautif

## Dependencies
- NONE

## Functional Deliverables
- FD-1: endpoint REST `POST /api/calc` retournant la somme de deux entiers
- FD-2: documentation Swagger/OpenAPI UI accessible sur le backend démarré
- FD-3: gestion d'erreur 400 pour payload invalide avec ProblemDetail RFC 7807 ou équivalent Spring

## Out of Scope
- Toute autre opération arithmétique (soustraction, multiplication, division)
- Persistance des calculs (historique, audit log)
- Authentification, autorisation, rate limiting
- Support des nombres flottants ou décimaux
- Frontend, UI utilisateur (validation se fait via Swagger UI uniquement)
- Multi-tenancy, multi-utilisateur (endpoint public)
- Versioning d'API (v1 implicite, pas de stratégie de versioning)
