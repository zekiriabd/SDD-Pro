# FEAT: Calc-A-B-C-FullStack

FEAT ID: 7-Calc-A-B-C-FullStack
Status: Draft

## Context
FEATs 1-6 ont validé le pattern "3 backends REST × 4 frontends SPA" avec contrat HTTP unique sur :44329. Pour boucler le bench avec le pattern alternatif **fullstack monolithique** (UI + serveur dans le même projet, sans CORS, sans API REST cross-origin), on enchaîne sur **Blazor Server** : C# Razor server-side rendering streamé via SignalR vers le navigateur.

## Objective
Servir une application Blazor Server unique qui combine UI Razor (3 champs A/B/C) + logique serveur (calcul C=A+B) dans le même process .NET, sans CORS, sans API REST externe, sans frontend séparé.

## Quantified Goal
- Metric: parité fonctionnelle AC avec FEAT 1 (calcul) et FEATs 2-5 (UI 3 champs)
- Target: 100 % (3 AC couverts dans 1 seul projet monolithe)
- Deadline: session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench local)
- Performance SLA: réponse calcul < 100ms via SignalR roundtrip (LAN local triviale)
- Data retention: n/a (stateless, scope page courante)
- Compliance: n/a
- Integration: aucune (monolithe), pas de backend externe
- Degraded mode: connexion SignalR perdue → Blazor affiche bandeau reconnexion natif

## Actors
- Tech Lead: opérateur bench
- Système FullStack (Blazor Server): UI Razor + serveur SignalR fusionnés

## Functional Needs
- SFD-1: page Razor unique `/` avec 3 champs A, B, C
- SFD-2: bind bidirectionnel `@bind` sur A et B (type int?)
- SFD-3: bouton Calculate qui invoque méthode @code C# côté serveur
- SFD-4: calcul C=A+B exécuté server-side, résultat rendered automatiquement via SignalR
- SFD-5: validation int? non null avant calcul (sinon bouton désactivé)

## Business Rules
- BR-1: A et B sont des int signés (`int?`), validation native Blazor `@bind` int
- BR-2: calcul exécuté côté serveur (preuve via Pino-like log)
- BR-3: aucune authentification (page publique)
- BR-4: aucun appel HTTP externe, aucun fetch (différence forte vs SPA)

## Acceptance Criteria
- AC-1: application Blazor Server démarrée sur :44339, saisir A=5 B=5 + clic Calculate → C=10 affiché en lecture seule en < 500ms (SignalR roundtrip)
- AC-2: application démarrée, ouvrir `http://localhost:44339/` → page Razor rendue (server-side initial HTML + SignalR hydration)
- AC-3: laisser A vide → bouton Calculate `disabled` ; bouton actif dès que A et B contiennent un entier

## Dependencies
- NONE (fullstack autonome, ne consomme aucun backend externe)

## Functional Deliverables
- FD-1: page Razor `Pages/Calc.razor` (ou `Home.razor`) avec 3 champs + bouton + @code C#
- FD-2: projet Blazor Server scaffoldé `dotnet new blazorserver` (.NET 8 LTS ou 9)
- FD-3: pas de WebApi controllers, pas de @page additional, monolithe single-page

## Out of Scope
- Routing multi-pages
- Authentification ASP.NET Identity
- Persistance EF Core (stateless)
- API REST externe (différence stricte vs FEATs 1, 6)
- CORS (pas de cross-origin, tout sur :44339)
- Tests bUnit (stack QA `blazor-bunit` archivé, hors scope bench)
- Theming / i18n
