# FEAT: Calc-A-B-C-AngularUniversal

FEAT ID: 11-Calc-A-B-C-AngularUniversal
Status: Draft

## Context
FEATs 7-10 ont validé 4 patterns fullstack monolithes (Blazor Server SignalR, Kotlin Mustache SSR, Next.js Server Actions, Nuxt Server Routes Nitro). Pour boucler la triade SSR JS, on enchaîne sur **Angular Universal** : Angular 19 + SSR (Express engine) qui rend la même composante côté serveur Node.js + hydration client.

## Objective
Servir une application Angular SSR sur :44379 avec composante Vue standalone (3 champs A/B/C), bouton Calculate qui invoque une fonction de calcul + signal binding, et démontre le pattern hybride SSR + CSR (page initial rendu serveur, interactivité hydraté client).

## Quantified Goal
- Metric: parité fonctionnelle AC avec FEATs 7/8/9/10
- Target: 100 % (3 AC dans 1 projet Angular SSR)
- Deadline: 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a
- Performance SLA: rendu SSR initial < 500ms, calcul interactif côté client < 50ms
- Data retention: n/a
- Compliance: n/a
- Integration: aucune (monolithe Angular SSR + Express server), pas de backend externe, pas de CORS
- Degraded mode: SSR fallback → CSR si serveur en erreur

## Actors
- Tech Lead
- Système FullStack (Angular Universal): SSR Express engine + Angular 19 standalone

## Functional Needs
- SFD-1: composant standalone `app.component.ts` avec form 3 champs A, B, C
- SFD-2: signals Angular pour state réactif (consistent avec FEAT 5 frontend Angular)
- SFD-3: page rendue SSR (HTML initial server-side) + hydration client
- SFD-4: bouton Calculate exécute le calcul côté client (différence vs Next/Nuxt Server Actions — bench Angular SSR pur)
- SFD-5: TypeScript strict, Angular 19 standalone (pas modules)

## Business Rules
- BR-1: A et B int signés via signal `number | null`
- BR-2: calcul exécuté côté client après hydration (différence vs Server Actions Next.js)
- BR-3: SSR Express engine prouve qu'Angular 19 supporte SSR out-of-box (`ng new --ssr`)
- BR-4: aucune authentification

## Acceptance Criteria
- AC-1: Angular SSR démarré sur :44379, saisir A=5 B=5 + clic Calculate → C=10 affiché < 100ms (calcul client)
- AC-2: ouvrir `http://localhost:44379/` → HTML SSR contient déjà la structure form (test `curl http://localhost:44379/ | grep "Calc A"` retourne match avant JS)
- AC-3: A vide → bouton Calculate désactivé (signal computed)

## Dependencies
- NONE (autonome)

## Functional Deliverables
- FD-1: scaffolding `ng new --ssr --standalone` Angular 19
- FD-2: `app.component.ts` customisé avec form Calc
- FD-3: Express server.ts par défaut pour SSR

## Out of Scope
- ngx-translate i18n
- msal-angular auth
- Prisma DB
- Tests Jasmine
