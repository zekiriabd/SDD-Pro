# SDD_Pro v6.0.0 — Spec-Driven Development pour Claude Code

> Framework SDD strict : SPEC fonctionnelle → User Stories → Code
> (back/front en parallèle). Lecture sélective, anti-derive, isolation
> par US et par famille.

> **Slim entry point (v5.0)** : ce fichier est volontairement court
> (~150 lignes). Le détail vit dans `.claude/docs/` chargé à la
> demande :
> - `@.claude/docs/architecture.md` — vision, modèles, agents, stacks, scope
> - `@.claude/docs/workflow.md` — 4 phases, flux détaillé, BREAKING CHANGES
> - `@.claude/docs/conventions.md` — anti-derive, idempotence, parallélisme, plan, capabilities, index rules/templates

---

## 1. Convention de nommage cross-fichiers (CRITIQUE)

Pour une US donnée, le **basename `{n}-{m}-{Name}` est rigoureusement
identique** à travers tous les artefacts :

| Artefact            | Chemin                                                    |
|---------------------|-----------------------------------------------------------|
| Mockup HTML         | `workspace/input/ui/{n}-{m}-{Name}.html` (optionnel, déposé manuellement par UX Designer) |
| User Story          | `workspace/output/us/{n}-{m}-{Name}.md`                             |
| Code généré         | `workspace/output/src/{AppName|BackendName|LibName}/...` (paths résolus par mapping stack) |
| Plan technique      | `workspace/output/plans/{n}-{m}-{Name}.{back|front}.md` (mode `:plan`) |

C'est cette convention qui permet la lecture sélective : pour
matérialiser `1-2-Menu-Navigation`, Dev-Frontend lit UNIQUEMENT
`workspace/output/us/1-2-*.md` + `workspace/input/ui/1-2-*.html`.

Le nom `{Name}` :
- Capitale initiale, pas d'accents, tirets pour les espaces
- Valides : `Auth`, `Reset-Password`, `Menu-Navigation`
- Invalides : `auth`, `reset_password`, `Menu Navigation`

---

## 2. IDs stables dans la SPEC (CRITIQUE)

Les bullets de `## Functional Needs` et `## Functional Deliverables`
portent un **identifiant explicite stable** :

```markdown
## Functional Needs
- SFD-1: Se connecter via Azure AD
- SFD-2: Réinitialiser son mot de passe

## Functional Deliverables
- FD-1: Écran de connexion
- FD-2: Écran de réinitialisation
```

**Règles** :
- Ne jamais réordonner ni renuméroter après génération des US.
- Ajout : créer `SFD-N+1` en fin de liste.
- Retrait : supprimer la ligne et **régénérer les US**.
- Les `Covers` des US référencent ces IDs **par valeur**.

Même règle pour `BR-N` et `AC-N`.

---

## 3. Commandes disponibles

| Commande                        | Phase        | Rôle                                              |
|---------------------------------|--------------|---------------------------------------------------|
| `/spec-generate [Nom]`          | 1            | Cadrage interactif SPEC + bootstrap constitution |
| `/spec-deepen {n} [--quick]`    | 1.5          | Élicitation structurée (Pre-mortem, Red Team…) |
| `/us-generate {n}`              | 2            | Découpe SPEC en User Stories (agent PO) |
| `/spec-validate {n} [--json]`   | 2.6          | Implementation Readiness Gate (déterministe, PowerShell) |
| `/arch-init`                    | 3            | ⚠️ legacy — utiliser `/dev-run` (qui invoque arch automatiquement) |
| `/dev-plan {n}`                 | 3.5          | Produit plans `workspace/output/plans/...` sans coder |
| `/dev-backend {n}-{m}[:plan]`   | 4            | Code serveur pour 1 US (`:plan` = Plan Only) |
| `/dev-frontend {n}-{m}[:plan]`  | 4            | Code client pour 1 US (`:plan` = Plan Only) |
| `/dev-run {n} [--force] [--max-parallel N]` | 3 → 4 | Orchestrateur : arch+db → back+front parallèle borné |
| `/sdd-full {n} [--plan] [--force] [--no-plan-on-warn] [--no-validate]` | 2 → 5 | Pipeline complet de A à Z |
| `/qa-generate {n} [--mode M]`       | 5            | Tests unitaires + coverage + quality scan sonar-like |
| `/sdd-status [{n}]`             | diagnostic   | État du pipeline (lecture seule) |
| `/sdd-clear [{n}] [--force] [--all] [--quiet]` | maintenance | Nettoyage des artefacts générés (dry-run par défaut) |
| `/doc-refresh`                  | rendu        | Régénère README.html + INDEX.md ADRs + QA dashboards (agent `dashboard` Haiku 4.5) |

---

## 4. Agents (4 cœur + 2 support, depuis v6.0)

**Cœur** — invoqués sur tout `/sdd-full` standard :

| Agent          | Modèle | Rôle (résumé)                                            | Phase |
|----------------|--------|----------------------------------------------------------|-------|
| `po`           | Sonnet 4.6 | SPEC → User Stories structurées (cible 1-3 US)           | 2     |
| `arch`         | Sonnet 4.6 | Bootstrap solution + scaffolding DB READ-ONLY + ADRs     | 3     |
| `dev-backend`  | **Opus 4.7** | US → code serveur (services, endpoints, DTOs, mappers)   | 4     |
| `dev-frontend` | **Opus 4.7** | US + HTML mockup → code client (Pages, Components, theme) | 4    |

> **Split modèles (depuis 2026-05-08)** : `dev-backend` et `dev-frontend` utilisent
> Opus 4.7 (raisonnement fin sur génération de code, `preserves:`/`adds:`, layer
> mapping, fidélité HTML). Les autres agents (transformations déterministes)
> restent en Sonnet 4.6. `dashboard` (rendu déterministe) en Haiku 4.5.

**Support** — optionnels ou invoqués conditionnellement :

| Agent          | Modèle | Rôle (résumé)                                            | Phase | Quand invoqué |
|----------------|--------|----------------------------------------------------------|-------|----------------|
| `elicitor`     | Sonnet 4.6 | Élicitation structurée 5 techniques (`/spec-deepen`)     | 1.5   | Sur SPECs complexes, `/sdd-full` strict force `/spec-deepen` |
| `qa`           | Sonnet 4.6 | Tests intégration HTTP (api-tests, gate) + tests unitaires + coverage + quality scan | 4 (gate) + 5 | API Gate auto par `/dev-run` (depuis 2026-05-07) ; phase 5 selon `QAMode` |
| `dashboard`    | **Haiku 4.5** | Régénère README.html projet + INDEX.md ADRs + dashboards QA HTML | fin de pipeline | Auto en fin de `/sdd-full`, `/dev-run`, `/qa-generate` ; manuel via `/doc-refresh` |

> **v6.0** : agent `validator` **retiré** (économie ~1.4M tokens/run).
> `/spec-validate` est désormais 100% déterministe via PowerShell
> (`validate-readiness.ps1`). Review sémantique à la charge du PO humain.

**Tous strictement autonomes** : aucun ne pose de question utilisateur.
Sur ambiguïté → `STOP + ERROR (CAUSE / FIX)`.

Détail (lectures/écritures, isolation, modèles) :
`@.claude/docs/architecture.md §3`.

---

## 5. Règles (rules/) — substance opérationnelle

Les règles vivent dans `.claude/rules/`. **Substance inlinée** dans
les agents `dev-backend` et `dev-frontend` (depuis v5.0) :
- `responsibilities.md` — périmètre des rôles
- `stack-completeness.md` — anti-derive sur les libs
- `file-ownership.md §1-§2` — matrice ownership fichiers partagés
- `qa-ownership.md §1, §4` — propriété QA exclusive sur tests

Règles externes (lues uniquement par leurs consommateurs) :
- `us-granularity.md` — chargée par agent PO (cible 1-3, hard cap 6)
- `constitution.md` — chargée par `/spec-generate`, agent PO, agent arch
- `qa-coverage.md` — chargée par agent QA (seuil 80%, schéma normalisé)
- `chat-output.md` — verbosité minimale (succès 1L / warn 1L / err 2L)
- `backend-first.md` — workflow gated back→API gate→front (depuis
  2026-05-07) ; chargée par `/dev-run` et agent QA mode `api-tests`
- `error-classification.md` — taxonomie 8 classes (BUILD_*, SCHEMA_*,
  LAYER_*, UI_*, QA_*, DERIVE_*, STACK_*, NETWORK_*, etc.) chargée par
  dev-backend, dev-frontend, qa, arch (depuis 2026-05-08). Pilote
  `build_loop` : `[BUILD_CORRECTIBLE]` itère, `[BUILD_BLOCKING]` fail-fast.

Détail complet + index : `@.claude/docs/conventions.md §14`.

---

## 6. Templates (templates/)

Liste : `@.claude/docs/conventions.md §15`.

---

## 7. Stacks supportés

5 backend × 5 frontend × 3 UI DS × 4 auth × 6 QA = ~1800 combinaisons
théoriques. Sélection humaine dans `workspace/input/stack/stack.md`.

Liste détaillée + capabilities on-demand :
`@.claude/docs/architecture.md §4`.

**Catalogue machine (depuis 2026-05-07)** : chaque stack expose
`{stack-id}.libs.json` (source de vérité pour versions + libs core +
libs on-demand + triggers + plugins). Le `.md` reste documentation
humaine ; le tableau `§2.4` est régénéré depuis le JSON via
`sync-stack-md.ps1`. Schéma : `.claude/templates/libs-catalog.schema.json`.
Détail : `@.claude/rules/stack-completeness.md §1.0`.

**Profil de référence validé** : `dotnet-minimalapi` + `blazor-webassembly`
+ `radzen-blazor` + `azure-ad` + QA dotnet-xunit/blazor-bunit. Autres
combos : 🟡 expérimentales.

---

## 8. Conventions strictes (résumé)

- **Anti-derive** universel : aucune invention hors SPEC/US/stack/HTML
- **Format ERROR** : 3 lignes (ERROR / CAUSE / FIX)
- **Idempotence** : toutes les commandes idempotentes
- **Lecture sélective** : 1 US à la fois, pas de Glob aveugle
- **Parallélisme dev-* borné** : `MaxParallel: 3` US par batch (default)
- **Plan inline** : pas de phase TASKS séparée
- **CLAUDE.md par projet** (digest, hash-validé) : produit par arch
- **HTML mockup** = source de vérité visuelle (texte direct, pas vision)
- **Mode Plan Only / From Plan** : `/dev-plan` puis `/dev-run` consomme
- **Capabilities core vs on-demand** : §2.4.a (arch installe) vs §2.4.b
  (dev-backend installe au trigger)
- **Chat Output minimal** : succès = 1 ligne, warning = 1 ligne, erreur
  = 2 lignes max. Pas de récap multi-section, pas de narration. Détail
  → fichiers `workspace/output/...`. Cf. `@.claude/rules/chat-output.md`.

Détail complet : `@.claude/docs/conventions.md §1-§13`.

---

## 9. Loader manifest

`@.claude/loader.yml` = miroir consolidé des reads/writes par agent.
Source de vérité pour l'audit du contexte et l'estimation tokens.

---

## 10. Démarrage rapide

1. Vérifier `workspace/input/stack/stack.md` : activer 1 backend, 1 frontend,
   1 UI DS, et éventuellement 1 auth. Renseigner `## Project Config`
   (`AppName`, `BackendName`, `LibName`, `DatabaseType`,
   `LibStrategy: shared|openapi-codegen|none` — défaut auto selon
   match des langages back/front).

2. Vérifier les variables d'environnement déclarées par les stacks
   activés :
   - Backend SQL → `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
     `DB_PASSWORD`
   - Auth Azure AD → `AZ_TENANTID`, `AZ_CLIENTID`, `AZ_DOMAIN`,
     `AZ_AUDIENCES`, `AZ_BE_CALLBACKPATH`, `AZ_FE_CALLBACKPATH`

3. `/spec-generate Auth` → répondre aux 3-6 questions → fichier créé.
4. (Optionnel) déposer les mockups HTML dans `workspace/input/ui/` (convention
   `{n}-{m}-{Name}.html`, basenames identiques aux US).
5. **`/sdd-full 1`** → pipeline complet de A à Z.

   Variantes plus granulaires :
   - `/us-generate 1` (US uniquement)
   - `/dev-run 1` (exécution seule, phases 3-4)

Pour vérifier l'état : `/sdd-status` ou `/sdd-status 1`.

---

## 11. Working Agreement (autorisation de travail dans le workspace)

**Pleine autorisation accordée** dans le répertoire SDD_Pro pour :
- Créer, éditer, supprimer, déplacer des fichiers (sources, docs, US,
  workspace, .claude/, etc.)
- Exécuter shell, builds, lints, tests, scripts PowerShell (`.claude/scripts/`)
- Opérations git locales : `add`, `commit`, `branch`, `checkout`,
  `merge`, `rebase`, `stash`
- Restore de packages : NuGet (`dotnet restore`), npm (`npm install`),
  pip, etc. depuis registres officiels

**Limites strictes** (déclenchent demande explicite si dépassement) :
1. **Structure de base de données** : aucune modification du schéma DB
   réelle. Interdits : `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/
   TRUNCATE`, `dotnet ef migrations add|remove|script`, `dotnet ef
   database update|drop`. L'introspection READ-ONLY (scaffolding
   Database-First par arch) reste autorisée.
2. **Hors répertoire SDD_Pro** : aucun accès en lecture/écriture aux
   autres projets du disque, fichiers système, profils shell, registry.
3. **Réseau sortant** : seulement ce que requièrent build/test :
   - ✅ Restore packages depuis NuGet/npm/PyPI/Maven officiels
   - ✅ Appels HTTP `localhost` (tests intégration, dev server)
   - ❌ `git push` (toute branche)
   - ❌ `curl` vers domaines arbitraires (sauf documentation explicite
     dans une règle / stack)
   - ❌ Upload, telemetry, analytics

**Conséquence comportementale** : ne JAMAIS demander confirmation
pour des opérations couvertes par cette autorisation. Demander
uniquement si l'opération franchit une des 3 limites ci-dessus.

Référence settings : `.claude/settings.json` permissions.allow couvre
les patterns shell courants ; permissions.deny bloque les opérations
DB structurelles et `git push`.

---

## 12. Pour aller plus loin

- `@.claude/docs/architecture.md` — vision, modèles, agents, stacks, scope
- `@.claude/docs/workflow.md` — 4 phases, flux, BREAKING CHANGES history
- `@.claude/docs/conventions.md` — anti-derive, idempotence, plan, etc.
- `@.claude/CHANGELOG.md` — historique versions (v4 → v5)
- `@.claude/MIGRATION.md` — guide migration entre versions majeures
- `@.claude/loader.yml` — manifest descriptif des reads/writes par agent
- `@.claude/rules/responsibilities.md` — périmètre exact de chaque acteur
- `@.claude/rules/us-granularity.md` — contrat de découpage SPEC → US
- `@.claude/rules/constitution.md` — constitution projet + ADRs
- `@.claude/rules/library-policy.md` — politique CVE/origine/version

### Scripts utilitaires (humains, hors Claude Code)

Voir `.claude/scripts/README.md` pour la liste des outils dev (smoke,
métriques, validation catalogues, sync).
