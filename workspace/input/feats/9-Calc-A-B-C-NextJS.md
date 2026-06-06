# FEAT: Calc-A-B-C-NextJS

FEAT ID: 9-Calc-A-B-C-NextJS
Status: Draft

## Context
FEATs 7-8 ont validé les patterns fullstack monolithe Blazor Server (SignalR) et Kotlin Mustache (SSR classique). Pour boucler le tour des patterns fullstack modernes, on enchaîne sur **Next.js 15 App Router** : React Server Components + Server Actions, monolithe Node.js qui combine UI React + serveur dans le même projet.

## Objective
Servir une application Next.js 15 unique avec App Router qui rend une page Server Component avec 3 champs A/B/C, invoque une Server Action `'use server'` pour calculer C=A+B côté serveur, et affiche le résultat sans appel API REST cross-origin.

## Quantified Goal
- Metric: parité fonctionnelle AC avec FEAT 7 (Blazor Server) et FEAT 8 (Mustache)
- Target: 100 % (3 AC couverts dans 1 seul projet Next.js)
- Deadline: session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: rendu initial Server Component < 200ms, Server Action roundtrip < 100ms
- Data retention: n/a (stateless)
- Compliance: n/a
- Integration: aucune (monolithe), pas de backend externe, pas de CORS
- Degraded mode: validation Zod côté Server Action → re-render avec message erreur

## Actors
- Tech Lead: opérateur bench
- Système FullStack (Next.js): React Server Components + Server Actions Node.js

## Functional Needs
- SFD-1: page `app/page.tsx` Server Component avec form 3 champs A, B, C
- SFD-2: Server Action `'use server'` (`app/actions.ts`) qui calcule C=A+B
- SFD-3: validation Zod inline dans la Server Action
- SFD-4: useState/useFormState côté Client Component pour afficher C
- SFD-5: pas de Route Handler `app/api/calc/route.ts` — uniquement Server Action

## Business Rules
- BR-1: A et B sont des entiers signés (validation Zod `z.number().int()`)
- BR-2: calcul C exécuté côté serveur Node.js (preuve : `console.log` dans la Server Action visible dans le terminal serveur, pas la console navigateur)
- BR-3: aucune authentification
- BR-4: TypeScript strict, ESM, React 19, Next.js 15 App Router (pas Pages Router legacy)

## Acceptance Criteria
- AC-1: application Next.js démarrée sur :44359, saisir A=5 B=5 + clic Calculate → C=10 affiché < 500ms (Server Action roundtrip)
- AC-2: ouvrir `http://localhost:44359/` → page Server Component rendue server-side avec form interactif (Client Component pour state)
- AC-3: laisser A vide → bouton Calculate `disabled` OU validation Zod retourne erreur après submit

## Dependencies
- NONE (fullstack autonome)

## Functional Deliverables
- FD-1: `src/app/page.tsx` (Server Component coquille)
- FD-2: `src/app/CalcForm.tsx` (Client Component avec `'use client'` pour useState)
- FD-3: `src/app/actions.ts` (`'use server'` Server Action calcSum)
- FD-4: `src/app/layout.tsx` + `globals.css` + `next.config.js`

## Out of Scope
- Route Handlers REST API (uniquement Server Actions)
- Auth NextAuth
- Prisma DB (stateless)
- next-intl i18n
- TanStack Query (Server Actions remplacent)
- Tests Vitest
