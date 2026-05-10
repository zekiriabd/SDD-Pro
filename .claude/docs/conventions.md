# SDD_Pro — Conventions strictes (référence)

> Document chargé **à la demande** (`Read @.claude/docs/conventions.md`).
> Pas en system prompt.

Ce document est l'index des conventions opératoires du framework. Le
détail complet de chaque règle vit dans `.claude/rules/` ; ce fichier
en est la **TOC commentée**.

## 1. Anti-derive (universel)

Aucun agent n'invente :
- des SFD, BR, AC, FD non présents dans la SPEC parente
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
**obligatoire** quand `/spec-validate` retourne 🟡 WARN ou 🔴 NO-GO
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
`@.claude/rules/file-ownership.md §6.bis`).

## 13. Capabilities core vs on-demand

§2.4 de chaque stack backend est scindée en deux sous-sections :

| Sous-section | Qui installe | Quand |
|---|---|---|
| **§2.4.a CORE** | arch | toujours, au bootstrap (§2.2.1) |
| **§2.4.b ON-DEMAND** | dev-backend (STEP 5.bis) | si l'US contient un trigger keyword |

Triggers : chaque ligne §2.4.b déclare 1+ patterns regex à chercher
dans l'US courante (et son mockup HTML).

**v5.0 — détection externalisée** : la détection des capabilities et
décision install/skip est exécutée par `.claude/scripts/detect-capabilities.ps1`
(workload déterministe, ~0 token LLM). L'agent dev-backend invoque le
script et consomme son JSON. Détail : `agents/dev-backend.md STEP 5.bis`.

## 14. Règles — index `.claude/rules/`

| Fichier                         | Domaine                                          |
|---------------------------------|--------------------------------------------------|
| `responsibilities.md`           | Périmètre strict de chaque rôle (humain + agent) |
| `us-granularity.md`             | Découpage SPEC → US (cible 1-3, warning 4-6, hard cap 6 ; INVEST) |
| `constitution.md`               | Constitution projet + ADRs (qui écrit quoi)      |
| `file-ownership.md`             | Matrice ownership fichiers partagés + ADR timestamp atomique |
| `qa-ownership.md`               | L'agent QA est seul propriétaire des tests, dev-* read-only |
| `qa-coverage.md`                | Seuil 80% (WARN si en-dessous), schéma normalisé coverage.json |
| `stack-completeness.md`         | Anti-derive sur libs : lib non listée en §2.4 → STOP + ERROR |
| `library-policy.md` **(v5.0)**  | Politique CVE / origine / version pinnée (extracted from arch.md v2.2) |

> Substance de `responsibilities.md`, `stack-completeness.md`,
> `file-ownership.md §1-§2`, `qa-ownership.md`, `qa-coverage.md`,
> `us-granularity.md`, `.claude/rules/constitution.md` est **inlinée**
> dans les agents qui en dépendent (depuis v5.0). Les fichiers complets
> restent disponibles pour les cas-limites.
>
> **Validation drift** : `.claude/scripts/validate-inline-rules.ps1`
> détecte si une rule a été modifiée après l'agent qui l'inline (mtime
> comparison). Lancer après toute édition de `rules/*.md` ou `agents/*.md`.

## 15. Templates — index `.claude/templates/`

| Fichier                          | Consommé par             |
|----------------------------------|--------------------------|
| `spec.template.md`               | `/spec-generate`         |
| `us.template.md`                 | agent `po`               |
| `constitution.template.md`       | `/spec-generate` (bootstrap projet) |
| `adr.template.md`                | agent `arch` + agents dev-* |
| `readiness.template.md`          | `/spec-validate`         |
| `risks-assumptions.template.md`  | agent `elicitor`         |
| `qa-report.template.md`          | agent `qa`               |
| `coverage.template.json`         | schéma normalisé coverage.json |
| `quality.template.json`          | schéma quality.json (sonar-like) |

## 16. Loader manifest

`@.claude/loader.yml` est le **miroir consolidé** de ce que chaque
agent charge en lecture pendant son exécution (source de vérité
unique pour l'audit du contexte par agent, les chevauchements, et
l'estimation des coûts tokens).

Toute modification d'un agent ou d'une commande DOIT être reflétée
dans `loader.yml` (descriptive, pas exécutoire).
