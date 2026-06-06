# FEAT: Calc-A-B-C-NuxtJS

FEAT ID: 10-Calc-A-B-C-NuxtJS
Status: Draft

## Context
FEAT 9 a livré Next.js 15 (App Router + Server Actions, équivalent React fullstack). On enchaîne sur **Nuxt 3** : équivalent fullstack Vue 3 avec Server Routes (`server/api/*`) au lieu de Server Actions React.

## Objective
Servir une application Nuxt 3 unique avec page Vue (3 champs A/B/C) qui invoque une Server Route `/api/calc` (Nitro server) pour calculer C=A+B côté serveur Node.js, sans CORS cross-origin (même origine).

## Quantified Goal
- Metric: parité fonctionnelle AC avec FEATs 7/8/9 (Blazor Server, Mustache, Next.js)
- Target: 100 % (3 AC couverts dans 1 seul projet Nuxt)
- Deadline: session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: rendu initial < 200ms, Server Route roundtrip < 100ms
- Data retention: n/a (stateless)
- Compliance: n/a
- Integration: aucune (monolithe Nitro), pas de backend externe, pas de CORS
- Degraded mode: validation Zod côté Server Route → 400 avec message

## Actors
- Tech Lead: opérateur bench
- Système FullStack (Nuxt): Vue 3 + Nitro server fusionnés

## Functional Needs
- SFD-1: page `pages/index.vue` avec form 3 champs A, B, C
- SFD-2: Server Route `server/api/calc.post.ts` qui calcule C=A+B
- SFD-3: validation Zod inline dans la Server Route
- SFD-4: `$fetch('/api/calc', { method: 'POST', body })` côté Vue (Nuxt magic — pas de CORS)
- SFD-5: TypeScript strict + Vue Composition API `<script setup>`

## Business Rules
- BR-1: A et B sont des entiers signés (Zod `z.number().int()`)
- BR-2: calcul C exécuté côté Nitro server (preuve : log côté terminal serveur)
- BR-3: aucune authentification
- BR-4: Nuxt 3 + Vue 3 + TypeScript

## Acceptance Criteria
- AC-1: Nuxt démarré sur :44369, saisir A=5 B=5 + clic Calculate → C=10 affiché < 500ms (Server Route via Nitro)
- AC-2: ouvrir `http://localhost:44369/` → page Vue rendue SSR avec form interactif
- AC-3: A vide → bouton désactivé OU 400 Zod si soumis quand même

## Dependencies
- NONE (fullstack autonome)

## Functional Deliverables
- FD-1: `pages/index.vue` (Vue 3 `<script setup>` + form)
- FD-2: `server/api/calc.post.ts` (Nitro Server Route avec Zod)
- FD-3: scaffolding Nuxt 3 minimaliste (pas de Pinia, Vuetify, nuxt-i18n, nuxt-auth pour bench)

## Out of Scope
- Pinia state management
- Nuxt UI / Vuetify modules
- nuxt-i18n
- nuxt-auth
- Prisma DB
- Tests Vitest
