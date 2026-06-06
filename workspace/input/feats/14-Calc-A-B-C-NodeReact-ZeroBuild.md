# FEAT: Calc-A-B-C-NodeReact-ZeroBuild

FEAT ID: 14-Calc-A-B-C-NodeReact-ZeroBuild
Status: Draft

## Context
FEATs 7-11 ont validé 5 patterns fullstack moderne. Pour boucler la couverture fullstack, on enchaîne sur **node-react zero-build** : pattern monolithe Fastify 5 + React 18 chargé via CDN + Babel Standalone (JSX transpilé in-browser, pas de bundler, pas de Vite/Webpack). Ce pattern est utilisé en interne par `workspace/console/` SDD_Pro.

## Objective
Servir une application monolithe Node sur :44389 où **1 seul process Fastify** sert simultanément l'API REST + les fichiers statiques (`index.html` + `app.jsx`). Le navigateur charge React + Babel via CDN unpkg, et Babel transpile le JSX au runtime → **zéro étape build, zéro `npm run build`, zéro CI bundler**.

## Quantified Goal
- Metric: page rendue + fetch /api/calc fonctionnel sans aucune étape de build
- Target: 100 % (start = `node server.js`, end = navigateur rend React + appel API + résultat)
- Deadline: 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: page chargée < 1s (CDN unpkg + Babel transpile in-browser)
- Data retention: n/a (stateless)
- Compliance: n/a
- Integration: aucune (monolithe, pas de backend externe, pas de CORS — même origine)
- Degraded mode: API down → erreur dans le composant React (mais le serveur sert toujours l'HTML)

## Actors
- Tech Lead
- Système FullStack (Node React zero-build): Fastify 5 + React 18 CDN + Babel CDN fusionnés

## Functional Needs
- SFD-1: `server.js` Fastify 5 ESM avec route `POST /api/calc` + serve static `public/`
- SFD-2: `public/index.html` charge React 18 + Babel Standalone via CDN unpkg + script `type="text/babel"` `app.jsx`
- SFD-3: `public/app.jsx` composant React avec 3 champs + bouton + fetch `/api/calc`
- SFD-4: validation Zod côté serveur (stack §1.1)
- SFD-5: pas de webpack, pas de vite, pas de bundler, pas de `npm run build`

## Business Rules
- BR-1: A et B int (Zod validation côté serveur — 400 si non-int)
- BR-2: calcul stateless côté serveur Fastify
- BR-3: pas d'authentification
- BR-4: ESM `"type": "module"` + Node 22+ + `node server.js` direct (pas de bundler)

## Acceptance Criteria
- AC-1: démarrer avec `node server.js` (zero build), saisir A=5 B=5 → C=10 affiché < 1s
- AC-2: `curl http://localhost:44389/` retourne `index.html` + script CDN React + Babel
- AC-3: validation Zod 400 si payload invalide

## Dependencies
- NONE (monolithe)

## Functional Deliverables
- FD-1: `server.js` Fastify routes + static + Zod
- FD-2: `public/index.html` + `public/app.jsx` (React via CDN + Babel)
- FD-3: `package.json` minimal (fastify + @fastify/static + zod uniquement — pas de React npm, pas de Babel npm)

## Out of Scope
- Prisma DB
- Auth fastify-jwt
- SSE (websocket)
- Tests vitest
- HMR (zero-build : reload manuel navigateur après edit app.jsx)
