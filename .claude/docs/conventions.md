# SDD_Pro — Conventions strictes (référence)

> Document chargé **à la demande** (`Read @.claude/docs/conventions.md`).
> Pas en system prompt.

Ce document est l'index des conventions opératoires du framework. Le
détail complet de chaque règle vit dans `.claude/rules/` ; ce fichier
en est la **TOC commentée**.

> **Voir aussi** (audit mineur #9 v7.0.0-alpha 2026-06-05 — cross-ref) :
> `@.claude/docs/glossary.md` pour la **taxonomie canonique** (agents,
> rôles, termes métier SDD_Pro). Ce fichier-ci décrit les **règles
> d'exécution** ; le glossaire décrit le **vocabulaire** sur lequel elles
> reposent. Si un terme apparaît ici sans définition explicite, le
> glossaire en est la source.

## 1. Anti-derive (universel)

Aucun agent n'invente :
- des SFD, BR, AC, FD non présents dans la FEAT parente
- une couleur, un libellé, un composant ou une icône non visible dans
  le HTML source (ou non listé dans le stack UI actif)
- une lib, un pattern, un middleware non déclaré dans le stack actif

Sur ambiguïté irrécupérable → `STOP + ERROR`. Pas de devinette.

## 2. Format ERROR — 3 lignes obligatoires

```
ERROR: <agent ou commande> — <résumé court>
CAUSE: <cause précise>
FIX: <action utilisateur concrète>
```

Aucun agent ne produit de stack trace verbeux.

## 3. Idempotence

Toutes les commandes sont idempotentes : relancer `/us-generate {n}`
écrase les US précédentes. Aucun état caché entre invocations. Le
bootstrap arch + scaffolding DB sont idempotents par construction.

## 4. Lecture sélective

Aucun agent ne fait de Glob `workspace/output/us/*.md` ou `workspace/input/ui/*.html`
quand il traite UNE US. Chaque agent ne lit que ses fichiers de
travail.

## 5. Parallélisme des agents Dev (borné)

`/dev-run {n}` invoque Dev-Backend ET Dev-Frontend **en parallèle**
sur les US, **par batches de `MaxParallel` US** (default 3,
configurable via `--max-parallel N` ou `MaxParallel: N` dans
`## Project Config`).

Pour `U` US et `MaxParallel = K` :
- `B = ceil(U / K)` batches enchaînés séquentiellement
- chaque batch : jusqu'à `2 × K` invocations dev-* parallèles dans un
  seul message
- les batches `i+1` démarrent quand TOUTES les invocations du batch
  `i` sont terminées

## 6. Plan inline (pas de phase TASKS)

Les agents `dev-backend` et `dev-frontend` planifient eux-mêmes la
liste des fichiers à produire à partir de l'US + (HTML mockup) +
stacks actifs. **Pas de fichier `workspace/output/tasks/...`**, pas de
Lead-Dev.

## 7. Bootstrap unifié (pas d'agent DB séparé)

L'agent `arch` absorbe l'introspection DB et le scaffolding
Database-First en Phase B. Si `DatabaseType: none`, la phase B est
silencieusement skip. **Pas d'agent `db` séparé**.

## 8. CLAUDE.md par projet (digest, depuis v2.5)

Arch produit en Phase C **un fichier CLAUDE.md par projet généré** :
- `workspace/output/src/{BackendName}/CLAUDE.md` — architecture backend
- `workspace/output/src/{AppName}/CLAUDE.md` — architecture frontend + UI
- `workspace/output/src/{LibName}/CLAUDE.md` (si LibName défini) — contrats
  partagés

Hash-validé (`stack-md-hash` en frontmatter, calculé sur stack.md +
stacks pertinents). Si périmé → fallback automatique sur les stacks
bruts. Régénération au prochain `/arch-init`.

## 9. HTML mockup comme source de vérité visuelle (depuis v4)

`dev-frontend` lit **directement** le fichier HTML statique
`workspace/input/ui/{n}-{m}-{Name}.html` (texte, pas vision multimodale).

Trois sources de vérité hiérarchisées :
- **HTML mockup** = source de vérité visuelle : libellés exacts,
  structure des zones, classes CSS, couleurs inline ou dans `<style>`,
  ordre des éléments, hiérarchies typographiques
- **Stack UI §2 + §7** = source de mapping vers les primitives du
  design system actif. Le HTML brut est traduit, jamais recopié tel
  quel
- **US** = source de vérité workflow (validation, navigation,
  conditions d'affichage)

Au STEP 11 **Fidelity Check (text-based)** : grep des libellés et
structures clés extraits du HTML source dans le markup généré.

## 10. Mode Plan Only / From Plan (depuis v2.4)

`/dev-plan {n}` invoque les agents dev-* en mode `:plan` : ils
planifient inline puis écrivent le plan dans
`workspace/output/plans/{n}-{m}-{Name}.{back|front}.md` **sans coder**.

`/dev-run {n}` détecte automatiquement les plans existants et les
**consomme** (mode From Plan).

**Plan-then-review gate** : `/sdd-full {n}` rend `/dev-plan {n}`
**obligatoire** quand `/feat-validate` retourne 🟡 WARN ou 🔴 NO-GO
ET que `--force` est passé. Par défaut, `/sdd-full` **STOP** sur 🟡
WARN ou 🔴 NO-GO.

**Plan-review opt-in sur GO** : `--plan` (ou
`PlanReviewDefault: true` dans `## Project Config`) déclenche le
plan-then-review **même sur GO**.

## 11. Persistence cross-stack

Chaque stack backend déclare une section `## 8. Persistence` avec :
- §8.1 DB Drivers (matrice `DatabaseType → package`)
- §8.2 Connection String Pattern (builder/URL canonique du langage)
- §8.3 Scaffolding tool (`dotnet ef` / `prisma db pull` / `sqlacodegen`)

## 12. Cleanup BREAKING CHANGES post-build

`dev-*` peuvent renommer une section `## BREAKING CHANGES` du
`CLAUDE.md` projet en `## BREAKING CHANGES — RESOLVED {YYYY-MM-DD}`
quand le build est vert et que la dérive est résolue (cf.
`@.claude/rules/ownership.md §6.bis`).

## 13. Capabilities core vs on-demand

§2.4 de chaque stack backend est scindée en deux sous-sections :

| Sous-section | Qui installe | Quand |
|---|---|---|
| **§2.4.a CORE** | arch | toujours, au bootstrap (§2.2.1) |
| **§2.4.b ON-DEMAND** | dev-backend (STEP 5.bis) | si l'US contient un trigger keyword |

Triggers : chaque ligne §2.4.b déclare 1+ patterns regex à chercher
dans l'US courante (et son mockup HTML).

**v5.0 — détection externalisée** : la détection des capabilities et
décision install/skip est exécutée par `.claude/python/sdd_scripts/detect_capabilities.py`
(workload déterministe, ~0 token LLM). L'agent dev-backend invoque le
script et consomme son JSON. Détail : `agents/dev-backend.md STEP 5.bis`.

## 14. Règles — index `.claude/rules/`

| Fichier                         | Domaine                                          |
|---------------------------------|--------------------------------------------------|
| `us-granularity.md`             | Découpage FEAT → US (cible 1-3, warning 4-6, hard cap 6 ; INVEST) |
| `constitution.md`               | Constitution projet + ADRs (qui écrit quoi)      |
| `ownership.md`             | Matrice ownership fichiers partagés + ADR timestamp atomique |
| `quality.md (Partie A)`                | Seuil 80% (RED bloquant si en-dessous), schéma normalisé coverage.json |
| `library-and-stack.md`         | Anti-derive sur libs + §0 runtime LTS / CVE / origine (ex-`library-policy.md`, fusionné v6.1) |
| `build-and-loop.md (Partie A)`              | Workflow gated back → API gate → front |
| `error-classification.md`       | Taxonomie codes `[CLASS]` cross-agent |
| `source-first.md`               | Discipline MD-avant-code pour fix bugs |
| `build-and-loop.md (Partie B)`                 | Patterns strictement identiques dev-backend/dev-frontend |

> Substance de `library-and-stack.md`, `ownership.md §1-§2`,
> `quality.md (Partie A)`, `us-granularity.md`, `ownership.md (Partie B)`
> est **inlinée** dans les agents qui en dépendent (depuis v5.0). Les
> fichiers complets restent disponibles pour les cas-limites.
>
> **Supprimés v6.1.2 (substance entièrement inlinée)** :
> `responsibilities.md`, `qa-ownership.md`, `chat-output.md`.
>
> **Validation drift** : `.claude/python/sdd_scripts/validate_inline_rules.py`
> détecte si une rule a été modifiée après l'agent qui l'inline (mtime
> comparison). Lancer après toute édition de `rules/*.md` ou `agents/*.md`.

### 14.1 Notes opérationnelles (détails utiles ex-CLAUDE.md §5)

- **`build-and-loop.md (Partie A)`** (depuis 2026-05-07) — chargée par `/dev-run`
  et agent `qa` mode `api-tests`. Pilote la séquence back → API gate →
  front (cf. `commands/dev-run.md §6`).
- **`error-classification.md`** (depuis 2026-05-08) — chargée par
  `dev-backend`, `dev-frontend`, `qa`, `arch`. Pilote `build_loop` :
  `[BUILD_CORRECTIBLE]` itère (max `BuildLoopMaxIter`),
  `[BUILD_BLOCKING]` fail-fast. Taxonomie 8 classes (BUILD_*, SCHEMA_*,
  LAYER_*, UI_*, QA_*, DERIVE_*, STACK_*, NETWORK_*, etc.).
- **`source-first.md`** (depuis 2026-05-12) — tout bug code = trou
  dans une source MD (FEAT, US, plan, stack, rule). Patcher la source
  d'abord, le code ensuite. Chargée par `dev-backend`, `dev-frontend`
  (référence sur échec `build_loop`) + Tech Lead humain.
- **`ownership.md §1.bis`** (depuis 2026-05-12) — Front/Back
  isolation stricte : `{AppName}/` et `{BackendName}/` au même niveau
  sous `workspace/output/src/`, jamais imbriqués. Hard-gate
  `[FILE_OWNERSHIP_NESTED]` dans `arch`, `dev-backend`, `dev-frontend`.
- **`build-and-loop.md (Partie B)`** — source de vérité unique pour les patterns
  strictement identiques `dev-backend`/`dev-frontend` (context budget
  HARD-GATE, LibName lock, anti-derive bullets, QA ownership interdits,
  stack-completeness, BREAKING CHANGES cleanup, reads on-demand).
  Réduit la duplication entre les deux agents.

## 15. Templates — index `.claude/templates/`

| Fichier                            | Consommé par             |
|------------------------------------|--------------------------|
| `feat.template.md`                 | `/feat-generate`         |
| `us.template.md`                   | agent `po`               |
| `constitution.template.md`         | `/feat-generate` (bootstrap projet) |
| `adr.template.md`                  | agent `arch` + agents dev-* |
| `readiness.template.md`            | `/feat-validate`         |
| `risks-assumptions.template.md`    | agent `elicitor`         |
| `qa-report.template.md`            | agent `qa`               |
| `api-tests.template.json`          | schéma rapport API Gate (cf. `rules/build-and-loop.md (Partie A) §1.4`) — produit par `/qa-generate --mode api-tests` |
| `claude-md-backend.template.md`    | agent `arch` STEP 12 — gabarit CLAUDE.md projet backend |
| `claude-md-frontend.template.md`   | agent `arch` STEP 12 — gabarit CLAUDE.md projet frontend |
| `claude-md-shared-lib.template.md` | agent `arch` STEP 12 — gabarit CLAUDE.md projet lib partagée (si `LibName` défini) |
| ~~`dashboard-readme.template.html`~~ | **retiré v6.10** — HTML dashboards remplacés par `console.db` lecture par consommateur externe |
| `adrs-index.template.md`           | script `sdd_scripts/index_adrs.py` (INDEX.md ADRs — remplace agent `dashboard` retiré v7.0.0) |
| ~~`qa-dashboard.template.html`~~   | **retiré v6.10** — métriques QA dans `console.db` (tables `qa_*`) |
| `libs-catalog.schema.json`         | JSON Schema des `.libs.json` (cf. `library-and-stack.md §1.0`) |
| `status.schema.json`               | JSON Schema de `workspace/console/status.json` (console gates manuels) |
| `runbook.template.md` (v6.4.0)     | Tech Lead humain (mise en prod) — procédure d'intervention on-call |
| `postmortem.template.md` (v6.4.0)  | Tech Lead humain (post-incident, 48h max cf. `source-first.md §5`) |
| `slo-sli.template.md` (v6.4.0)     | Tech Lead humain (définition SLO + alerting multi-burn-rate + error budget) |

## 16. Loader manifest

`@.claude/loader.yml` est le **miroir consolidé** de ce que chaque
agent charge en lecture pendant son exécution (source de vérité
unique pour l'audit du contexte par agent, les chevauchements, et
l'estimation des coûts tokens).

Toute modification d'un agent ou d'une commande DOIT être reflétée
dans `loader.yml` (descriptive, pas exécutoire).
