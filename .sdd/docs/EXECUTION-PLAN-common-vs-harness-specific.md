# Plan d'exécution — Séparation commun (`.sdd/`) vs spécifique par harnais

> **Statut** : PLAN (aucune exécution).
> **Auteur** : Analyse expert AI/prompt-eng/senior-dev SDD_Pro, 2026-07-25.
> **Périmètre** : compléter la migration multi-harnais commencée le 2026-07-24.
> **Contrat non négociable** : **Claude Code doit continuer à fonctionner
> à l'identique à chaque étape**. Aucun batch ne peut casser le pipeline
> `/sdd-full` ou l'auto-chargement `.claude/CLAUDE.md`.
> **Ancrage** : ce plan complète et supersede l'interprétation naïve des
> Phases 1.1/1.6 du plan
> `MIGRATION-PLAN-multi-harness-multi-provider.md` — la stratégie parallèle
> qu'a adoptée l'équipe le 2026-07-24 n'y était pas explicite.

---

## 1. Analyse — Taxonomie commun vs spécifique par harnais

### 1.1 Ce qui EST commun (doit vivre dans `.sdd/`)

Contenu **LLM-agnostique** : la description est indépendante du harnais qui
l'exécute. Un `dev-backend` fait la même chose sous Claude Code, Codex ou
Gemini — seul le mécanisme d'orchestration change.

| Catégorie | Volume actuel dans `.claude/` | Nature | Statut cible |
|---|---:|---|---|
| **Bodies d'agents** (le corps markdown : STEPs, règles, décisions) | 25 × ~500 lignes | prose métier, décrit CE QUE l'agent fait | `.sdd/agents/*.body.md` |
| **Bodies de commandes** (semantique du slash-command) | 40 × ~200-400 lignes | prose métier, décrit CE QUE la commande fait | `.sdd/commands/*.body.md` |
| **Rules** (11 fichiers) | 256 KB | contrats framework (build-and-loop, quality, ownership…) | `.sdd/rules/*.md` |
| **Stacks** (35 fichiers .md + 35 .libs.json) | 1.2 MB | définitions tech-stack (backend/frontend/ui/auth/qa/mobiles) | `.sdd/stacks/**` |
| **Templates** (25 fichiers) | 208 KB | scaffolds bootstrap (stack.md.template, combos.json, JSON schemas) | `.sdd/templates/**` |
| **Docs** (41 fichiers + adrs/, rubrics/, benchmarks/) | 988 KB | documentation framework | `.sdd/docs/**` |
| **ADRs** (13 dans `.sdd/docs/adrs/` + 1 dans `.sdd/docs/adrs/`) | ~200 KB | décisions d'architecture historisées | `.sdd/docs/adrs/**` |
| **Python déterministe** (331 scripts) | 11 MB | gates, validate_*, build_loop, ingest, quality_scan — **0 token, 0 API LLM** | `.sdd/python/**` |
| **Loader manifests** (`loader.yml` 62 KB + `loader.reverse.yml` 22 KB) | 84 KB | contrats reads/writes par agent (SSoT ADR governance-major-config-ssot) | `.sdd/loader{,.reverse}.yml` |
| **INVARIANTS** (`INVARIANTS.yml` + `INVARIANTS.reverse.yml`) | ~23 KB | 13 + N contrats load-bearing avec pointeurs enforcer | `.sdd/INVARIANTS{,.reverse}.yml` |
| **Config base** (`config.base.yml`) | 16 KB | valeurs par défaut framework | `.sdd/config.base.yml` |
| **Bootstrap** (`bootstrap.py`) | ~42 KB | init projet greenfield | `.sdd/bootstrap.py` |
| **Skills bodies** (SKILL.md corps) | 596 KB (arborescences) | descriptions des skills SDD-owned + tiers vendorés | `.sdd/skills/**` |
| **Docs infra** (`mkdocs.yml` 11 KB, `requirements-docs.txt`, `CONTRIBUTING.md` 11 KB) | ~22 KB | site docs, guide contrib | `.sdd/` (racine) |
| **Digests** (176 KB — extraits pré-générés d'error-classification) | 176 KB | pré-calculs pour agents | `.sdd/digests/` |

**Sous-total commun** : ~14.5 MB, ~600 fichiers.

### 1.2 Ce qui reste harness-spécifique

Contenu qui **encode un mécanisme natif d'un harnais donné** — le déplacer
casse la découverte automatique par ce harnais.

| Catégorie | Localisation | Mécanisme natif |
|---|---|---|
| **Fichier mémoire** | `.claude/CLAUDE.md` / `.codex/AGENTS.md` / `.gemini/GEMINI.md` | Auto-chargé au démarrage de la session par chaque harnais respectif |
| **Frontmatter agents** | `.claude/agents/*.md` frontmatter YAML (`name`, `description`, `tools`, `model`) | Contrat Claude Code pour découverte des sub-agents via tool `Task`/`Agent` |
| **Frontmatter commands** | `.claude/commands/*.md` frontmatter (si présent) | Contrat Claude Code pour slash-commands |
| **Format commands Gemini** | `.gemini/commands/*.toml` | Format TOML natif Gemini CLI (`{{args}}`) |
| **Format commands Codex** | `.codex/prompts/*.md` | Custom prompts Codex (`$ARGUMENTS`) |
| **Skills auto-trigger** | `.sdd/skills/*/SKILL.md` frontmatter | Mécanisme d'auto-déclenchement Claude Code (`name` + `description` déclenchent injection contextuelle). **Ce mécanisme n'a pas d'équivalent natif Codex/Gemini** — pour ces harnais les skills sont soit inlinés dans le fichier mémoire, soit invoqués comme commandes explicites. |
| **Config permissions** | `.claude/settings.json` / `.claude/settings.local.json` | Format Claude Code (`permissions.allow`, `permissions.additionalDirectories`, `hooks`) |
| **Config Codex** | `.codex/config.toml` | Format TOML natif Codex (`base_url`, `approval_policy`, `sandbox`) |
| **Config Gemini** | `.gemini/settings.json` | Format JSON natif Gemini CLI |
| **Harness-impact reports** | `.codex/harness-impact.md` / `.gemini/harness-impact.md` | Rapport d'honnêteté généré par `impact_report.py` — spécifique au combo harnais × provider actif |

**Bilan** : ~5 % du volume framework, mais 100 % des points d'entrée
mécaniques.

### 1.3 Le distinguo LOAD-BEARING (agents + commands)

Les agents et commandes portent **deux couches** :

| Couche | Contenu | LLM-agnostique ? | Destination |
|---|---|---|---|
| **Frontmatter YAML** | `name`, `description`, `tools`, `model`, `paths` (rules) | ❌ format Claude Code | `.claude/` (généré par transpileur) |
| **Body markdown** | Les STEPs, règles inline, exemples, decision tree | ✅ prose métier | `.sdd/` (source de vérité) |

**Le pivot doit inverser la relation actuelle** : aujourd'hui `.sdd/agents/po.agent.yaml` = métadonnées + `body_source: .claude/agents/po.md`. Cible : `.sdd/agents/po.body.md` = body ; `.sdd/agents/po.meta.yaml` = métadonnées neutres (`model_tier`, `tools`, `description`) ; `.claude/agents/po.md` = **régénéré** (frontmatter Claude Code + body inline).

---

## 2. Audit — État réel vs cible (2026-07-25)

### 2.1 Ce qui EST déjà dans `.sdd/`

| Élément | État |
|---|---|
| `.sdd/agents/*.agent.yaml` | ✅ 25 fichiers — métadonnées seulement, `body_source:` pointe encore vers `.claude/` |
| `.sdd/commands/*.cmd.yaml` | ✅ 40 fichiers — métadonnées seulement, `body_source:` pointe encore vers `.claude/` |
| `.sdd/providers/*.yaml` | ✅ NEUF (anthropic, openai, moonshot, google) |
| `.sdd/agent-bounds.yaml` | ✅ NEUF (bornes tier par agent) |
| `.sdd/capability-matrix.yml` | ✅ NEUF (harnais × mécanismes) |
| `.sdd/rules-manifest.yaml` | ✅ NEUF (classification 11 rules) |
| `.sdd/skills-manifest.yaml` | ✅ NEUF (classification 13 skills owned/vendored) |
| `.sdd/python/sdd_lib/` | ⚠️ **8 modules NEUFS** (paths, model_resolver, spawn_agent, stack_config, config_loader, harness_diff, harness_preflight, impact_report) — **paths.py neuf indépendant du legacy** |
| `.sdd/python/tests/` | ✅ 212 tests passing (couvrent uniquement les modules neufs) |
| `.sdd/harness_build.py` | ✅ transpileur fonctionnel (--harness claude-code\|codex\|gemini-cli, --stack, --deploy) |
| `.sdd/docs/adrs/` | ⚠️ 1 seul ADR (le fondateur harness) — 13 autres restent dans `.claude/` |
| `.sdd/experiments/p04-codex-subagent/` | ✅ Prototype Phase 0.4 (20 tests) |

### 2.2 Ce qui N'EST PAS encore dans `.sdd/`

**Tous les bodies + tous les contenus historiques restent dans `.claude/`** :

| Élément resté dans `.claude/` | Volume | Blocage transpileur ? |
|---|---:|---|
| Bodies des 25 agents (`.claude/agents/*.md`) | ~12 500 lignes | ⚠️ Oui — `harness_build.py` suit `body_source:` vers `.claude/` |
| Bodies des 40 commandes (`.claude/commands/*.md`) | ~12 000 lignes | ⚠️ Oui — idem |
| 11 rules (`.sdd/rules/*.md`) | 256 KB | ✅ Non (lues via `@include`) |
| 35 stacks (`.sdd/stacks/`) | 1.2 MB | ✅ Non |
| 25 templates (`.sdd/templates/`) | 208 KB | ✅ Non |
| 41 docs (`.sdd/docs/`) | 988 KB | ✅ Non |
| 13 ADRs (`.sdd/docs/adrs/`) | ~200 KB | ✅ Non |
| 13 skills (`.sdd/skills/`) | 596 KB | ✅ Non |
| 331 scripts Python (`.sdd/python/`) | 11 MB | ⚠️ **Collision** `sdd_lib/paths.py` legacy vs neuf |
| Loaders + INVARIANTS + config.base | ~120 KB | ✅ Non |
| bootstrap.py + mkdocs.yml + CONTRIBUTING.md | ~60 KB | ✅ Non |
| digests (176 KB) | 176 KB | ✅ Non |

### 2.3 Contraintes non négociables (validées par ce plan)

1. **Windows-safe** : `AUCUN symlink`. Résolution = env var `SDD_HOME` + chemins relatifs.
2. **Rétro-compat Claude Code** : `.claude/CLAUDE.md` reste auto-chargé, tous les `@`-includes doivent résoudre à un fichier réel à tout instant.
3. **Golden test** : après chaque batch, `python .sdd/harness_build.py --harness claude-code ... --out .sdd/.build/claude` doit produire une sortie byte-identique à `.claude/` HEAD (ou au baseline explicite du batch).
4. **Tests** : les 144 tests legacy (`.sdd/python/tests/`) + 212 tests neufs (`.sdd/python/tests/`) = **356 tests doivent rester verts** à la fin de chaque batch. Toute régression = STOP + rollback.
5. **Pas d'action destructive sans commit préalable** : chaque batch = 1 commit minimum, revertible par `git revert`.

---

## 3. Cible architecturale finale

```
.sdd/                              # SSoT ÉDITÉE À LA MAIN
├── sdd.yml                        # manifest racine (version, schéma)
├── agents/
│   ├── po.body.md                 # BODY prose neutre (LLM-agnostique)
│   ├── po.meta.yaml               # META neutre (name, desc, tools, model_tier, tier_floor, tier_ceiling)
│   └── ... (25 paires)
├── commands/
│   ├── sdd-full.body.md
│   ├── sdd-full.meta.yaml         # META : args, flags, spawns
│   └── ... (40 paires)
├── rules/                         # 11 rules (frontmatter paths: préservé — traité par adapter Claude)
├── skills/
│   ├── sdd/                       # 6 skills SDD-owned (body neutre)
│   └── vendor/                    # ~8 skills tiers (pass-through, licences)
├── stacks/                        # 35 stacks + .libs.json
├── templates/                     # 25 templates
├── docs/                          # 41 docs + adrs/ + rubrics/ + benchmarks/
├── python/                        # 331 scripts + 8 neufs = 339 total
│   ├── sdd_lib/                   # 34 modules (26 legacy + 8 neufs, paths.py unifié)
│   ├── sdd_admin/ sdd_scripts/ sdd_hooks/
│   ├── sdd_reverse/ sdd_reverse_scripts/
│   ├── tests/                     # 144 + 212 = 356 tests
│   └── pyproject.toml
├── providers/                     # 4 providers (anthropic, openai, moonshot, google)
├── loader.yml                     # + loader.reverse.yml (chemins re-racinés .sdd/)
├── INVARIANTS.yml                 # + INVARIANTS.reverse.yml
├── config.base.yml
├── capability-matrix.yml          # + agent-bounds.yaml + rules-manifest.yaml + skills-manifest.yaml
├── bootstrap.py
├── mkdocs.yml                     # + CONTRIBUTING.md + requirements-docs.txt
├── harness_build.py               # transpileur (déjà en place)
└── entrypoint.md                  # entry point neutre

# FAÇADES GÉNÉRÉES (jetables, en-tête # GENERATED FROM .sdd/ — DO NOT EDIT)
.claude/                           # harnais Claude Code
├── CLAUDE.md                      # généré (Claude Code entry point)
├── agents/*.md                    # généré (frontmatter reconstruit + body inline)
├── commands/*.md                  # généré
├── rules/*.md                     # généré (byte-copy) OU pass-through
├── skills/                        # généré/pass-through (skills natifs Claude Code)
├── stacks/, templates/, docs/     # généré/pass-through
└── settings.json + settings.local.json  # NON généré (permissions locales machine)

.codex/                            # harnais Codex
├── AGENTS.md                      # généré (canonique open standard)
├── prompts/*.md                   # généré ($ARGUMENTS)
├── config.toml                    # généré (provider actif)
└── harness-impact.md              # généré (par build)

.gemini/                           # harnais Gemini CLI / Antigravity
├── GEMINI.md                      # généré
├── commands/*.toml                # généré ({{args}}, format natif)
├── settings.json                  # généré
└── harness-impact.md              # généré
```

---

## 4. Plan d'exécution — 7 batches à faible risque

**Principes du "faible modèle"** :
- Chaque batch est **indépendamment reversible** (1 commit, `git revert` sûr)
- **Byte-copy stratégique** : lors du move d'un fichier, on GARDE une byte-copy committée dans `.claude/` jusqu'à ce que le transpileur soit adapté. Aucune période où Claude Code voit un fichier manquant.
- Chaque batch a **1 gate de validation** (test précis, verdict binaire) et **1 stratégie de rollback**
- Ordre par risque **croissant** — les batches les plus sûrs d'abord

### Batch 1 — Contenu pur non-exécutable (2-3h) — RISQUE MINIMAL

**Périmètre** : déplacement de contenus lus par `@include` ou par bootstrap, jamais exécutés au runtime.

| Fichier / répertoire | Source | Destination | Copie kept dans `.claude/` ? |
|---|---|---|---|
| 13 ADRs | `.sdd/docs/adrs/*.md` | `.sdd/docs/adrs/*.md` | ✅ byte-copy |
| 35 stacks + .libs.json | `.sdd/stacks/**` | `.sdd/stacks/**` | ✅ byte-copy |
| 25 templates | `.sdd/templates/**` | `.sdd/templates/**` | ✅ byte-copy |
| 3 rubrics | `.sdd/docs/rubrics/**` | `.sdd/docs/rubrics/**` | ✅ byte-copy |
| Benchmarks | `.sdd/docs/benchmarks/**` | `.sdd/docs/benchmarks/**` | ✅ byte-copy |
| `mkdocs.yml` + `CONTRIBUTING.md` + `requirements-docs.txt` | `.claude/` | `.sdd/` | ✅ byte-copy |

**Actions** :
1. `git mv` de chaque source vers `.sdd/`
2. Créer les byte-copies dans `.claude/` par simple `cp` post-mv (pour Claude Code)
3. **AUCUNE réécriture** de `@`-include à ce stade — les copies dans `.claude/` répondent aux refs existantes

**Gate de validation** :
- `git status` : les fichiers apparaissent en `renamed` (git détecte le mv) + `.claude/` byte-copies en `new file`
- `diff -r .sdd/stacks .claude/stacks` retourne 0 (byte-identiques)
- `python .sdd/python/sdd_admin/framework_smoke.py` reste vert (gate `stacks-count` = 35)
- 356 tests passent (aucun script Python ne bouge)

**Rollback** : `git reset --hard HEAD~1` (avant push)

**Sortie** : `.sdd/` contient les vrais contenus, `.claude/` a des byte-copies. Aucun comportement Claude Code changé.

---

### Batch 2 — Rules + Docs (2h) — RISQUE FAIBLE

**Périmètre** : les 11 rules + 41 docs. Lus via `@include` par CLAUDE.md et par les agents (au STEP contexte).

| Fichier | Source | Destination | Copie kept ? |
|---|---|---|---|
| 11 rules | `.sdd/rules/*.md` | `.sdd/rules/*.md` | ✅ byte-copy |
| 41 docs (moins adrs/rubrics/benchmarks déjà B1) | `.sdd/docs/**` | `.sdd/docs/**` | ✅ byte-copy |

**Actions identiques à B1**.

**Gate** :
- `python .sdd/python/tests/test_impact_report.py` reste vert (charge capability-matrix)
- `test_rules_frontmatter_paths.py` (à créer) : vérifie que les 9 rules path-scoped ont bien leur frontmatter préservée après copy
- 356 tests verts
- Ouvrir `.claude/CLAUDE.md` dans une nouvelle session Claude Code test : les `@.sdd/docs/architecture.md` doivent toujours résoudre (byte-copies présentes)

**Rollback** : `git revert` du commit.

---

### Batch 3 — Skills (1h) — RISQUE FAIBLE

**Périmètre** : 13 skills (5 SDD-owned + 8 vendored).

| Élément | Source | Destination | Copie kept ? |
|---|---|---|---|
| Skills SDD-owned | `.sdd/skills/{using-sddpro,starting-*,debugging-*,test-driven-development,a11y-local}/` | `.sdd/skills/sdd/*/` | ✅ byte-copy dans `.sdd/skills/` (nécessaire — Claude Code auto-trigger LIT `.sdd/skills/`) |
| Skills tiers | `.sdd/skills/{c4-model,codeql,frontend-design,insecure-defaults,sarif-parsing,semgrep,webapp-testing}/` | `.sdd/skills/vendor/*/` | ✅ byte-copy dans `.sdd/skills/` |
| `VENDORED.md` (licence) | `.sdd/skills/VENDORED.md` | `.sdd/skills/VENDORED.md` | ✅ byte-copy |

**Note critique** : le mécanisme d'auto-trigger Claude Code exige que les
skills soient à `.sdd/skills/*/SKILL.md`. Les byte-copies **doivent
rester** dans `.sdd/skills/` (n'est PAS un stub, doit être le contenu
complet). Pour les autres harnais, `harness_build.py` **inline** les skills
SDD-owned critiques dans `AGENTS.md`/`GEMINI.md` (déjà en place Phase 3.1/4.1).

**Gate** :
- Compter les skills : `find .sdd/skills -name SKILL.md | wc -l` = 13
- `find .claude/skills -name SKILL.md | wc -l` = 13 (byte-copies)
- `diff -r .sdd/skills/sdd/using-sddpro .sdd/skills/using-sddpro` = 0
- 356 tests verts

**Rollback** : `git revert`.

---

### Batch 4 — Loader + INVARIANTS + config.base + bootstrap (30 min) — RISQUE FAIBLE

**Périmètre** : fichiers de gouvernance et bootstrap. Aucun code ne les exécute au runtime hors bootstrap.py lui-même.

| Fichier | Source | Destination | Copie kept ? |
|---|---|---|---|
| `loader.yml` (62 KB) | `.claude/loader.yml` | `.sdd/loader.yml` | ✅ byte-copy |
| `loader.reverse.yml` (22 KB) | `.claude/loader.reverse.yml` | `.sdd/loader.reverse.yml` | ✅ byte-copy |
| `INVARIANTS.yml` (11 KB) | `.claude/INVARIANTS.yml` | `.sdd/INVARIANTS.yml` | ✅ byte-copy |
| `INVARIANTS.reverse.yml` (11 KB) | `.claude/INVARIANTS.reverse.yml` | `.sdd/INVARIANTS.reverse.yml` | ✅ byte-copy |
| `config.base.yml` (16 KB) | `.claude/config.base.yml` | `.sdd/config.base.yml` | ✅ byte-copy |
| `bootstrap.py` (~42 KB) | `.claude/` | `.sdd/` | ⚠️ byte-copy — voir action 2 |

**Actions** :
1. `git mv` + byte-copies
2. **Bootstrap.py** doit être aware du bi-racine. Modifier son point d'entrée pour préférer `.sdd/` s'il existe, fallback `.claude/`. Ajouter un test.

**Gate** :
- `python .claude/bootstrap.py --dry-run --combo c1` : exit 0
- `python .sdd/bootstrap.py --dry-run --combo c1` : exit 0
- `test_invariants_manifest.py` vert (charge INVARIANTS.yml)

**Rollback** : `git revert`.

---

### Batch 5 — Python (5-8h) — RISQUE ÉLEVÉ (le batch délicat)

**Périmètre** : fusionner les 26 modules legacy `sdd_lib/` + 8 neufs = 34 modules unifiés. Déplacer les 5 autres sous-packages (`sdd_admin`, `sdd_scripts`, `sdd_hooks`, `sdd_reverse`, `sdd_reverse_scripts`, `tests`).

**Sous-batches** :

#### 5a — Concevoir `paths.py` unifié (1h)
- Lire `.sdd/python/sdd_lib/paths.py` (193 lignes, API legacy : `_looks_like_repo_root`, `repo_root`, `iso_now`, `normalize`, ...) et `.sdd/python/sdd_lib/paths.py` (76 lignes, API neuve : `sdd_home`, `resolve`, `providers_dir`, ...).
- Produire un fichier fusionné qui expose LES DEUX APIs :
  - Legacy inchangée (100 fichiers importent)
  - Neuve inchangée (5 fichiers importent, 212 tests)
  - `_looks_like_repo_root` **bi-racine** (`.sdd/agents/` OU `.claude/agents/` = repo root valide)
- **Aucun code applicatif modifié à ce stade** — seul `paths.py` change.

**Gate** : les 356 tests passent (à ce stade `.sdd/python/sdd_lib/paths.py` et `.sdd/python/sdd_lib/paths.py` sont byte-identiques).

#### 5b — Fusion physique des `sdd_lib/` (1h)
- `.sdd/python/sdd_lib/` reçoit les 26 modules legacy manquants (`git mv .sdd/python/sdd_lib/adr_id.py .sdd/python/sdd_lib/adr_id.py`, etc. — sauf `paths.py` déjà unifié)
- byte-copy des 26 legacy dans `.sdd/python/sdd_lib/` (pour ne pas casser les 100 imports actuels)

**Gate** : `python -c "from sdd_lib import adr_id; adr_id.next_id()"` fonctionne depuis les 2 chemins.

#### 5c — Déplacement des 5 sous-packages (1h)
- `git mv .sdd/python/sdd_admin .sdd/python/sdd_admin`
- `git mv .sdd/python/sdd_scripts .sdd/python/sdd_scripts`
- `git mv .sdd/python/sdd_hooks .sdd/python/sdd_hooks`
- `git mv .sdd/python/sdd_reverse .sdd/python/sdd_reverse`
- `git mv .sdd/python/sdd_reverse_scripts .sdd/python/sdd_reverse_scripts`
- `git mv .sdd/python/tests .sdd/python/tests_legacy` (renommé pour éviter collision avec `.sdd/python/tests`)
- byte-copies dans `.sdd/python/` correspondantes

**Gate** : 144 tests legacy + 212 tests neufs = 356, tous verts.

#### 5d — Réécriture des 233 littéraux `.claude` (2h)
- `grep -rn "'\.claude" .sdd/python/` — identifier chaque littéral (~171 fichiers, 233 occurrences)
- Trier par type :
  - **Chemin fonctionnel** (`Path('.sdd/templates/...')`) → `sdd_home() / 'templates' / ...`
  - **Message/docstring** (`"See .sdd/rules/..."`) → réécriture cosmétique batch
- Ajouter test `test_no_hardcoded_claude_paths.py` (grep-gate CI : 0 littéral `.claude/` fonctionnel dans `sdd_*` hors `adapters/claude.py`)

**Gate** : 356 tests verts + nouveau test `test_no_hardcoded_claude_paths` vert.

#### 5e — Réécriture des 97 invocations `.md` (1h)
- `grep -rn 'python \.claude/python' .claude/` — 97 occurrences
- Réécriture batch : `python .sdd/python/xxx` → `python .sdd/python/xxx`
- Update `.claude/settings.local.json` : `Bash(python:.sdd/python/**)` → `Bash(python:.sdd/python/**)` (manuel, documenté)

**Gate** : `python .sdd/python/sdd_admin/framework_smoke.py` exit 0. Lancer 1 commande SDD manuellement (`/sdd-status` ou équivalent Python direct) pour valider bout-en-bout.

**Rollback global B5** : `git revert` du/des commits — mais **plus complexe** car 5 sous-commits. Prévoir un tag `pre-B5` avant démarrage.

---

### Batch 6 — Bodies d'agents + de commandes (2-3h) — RISQUE MODÉRÉ

**Périmètre** : extraire les bodies markdown des 25 agents + 40 commandes vers `.sdd/`, adapter `harness_build.py` pour les prendre depuis `.sdd/`.

**Actions** :

#### 6a — Renommage architectural
- Actuel : `.sdd/agents/po.agent.yaml` (métadonnées) + `body_source: .claude/agents/po.md`
- Cible : `.sdd/agents/po.body.md` (body pur) + `.sdd/agents/po.meta.yaml` (métadonnées neutres)

Ou alternative plus compacte :
- Cible : `.sdd/agents/po.agent.yaml` contient AUSSI le body embarqué sous une clé `body: |` multiligne (comme dans le format pivot §4.1 du plan)

**Choix recommandé** : fichier séparé (`.body.md` + `.meta.yaml`) — plus lisible en review, plus grep-friendly, revert d'une modif de body ne touche pas les métadonnées.

#### 6b — Extraction mécanique
- Script `extract_bodies.py` (à créer sous `.sdd/python/sdd_scripts/`) :
  - Lit `.claude/agents/*.md`
  - Splite frontmatter YAML (déjà connu, en `.sdd/agents/*.agent.yaml`) et body
  - Écrit `.sdd/agents/po.body.md`
  - Le `.agent.yaml` gagne `body_source: .sdd/agents/po.body.md` (pointeur re-raciné)
- Idem pour les 40 commandes

#### 6c — Adaptation `harness_build.py`
- `ClaudeAdapter.emit_agents` : reconstruit le frontmatter depuis `.meta.yaml` + inline le body depuis `.body.md`
- `CodexAdapter.emit_agents` : idem mais frontmatter neutre pour AGENTS.md
- `GeminiAdapter.emit_agents` : idem
- Golden test byte-identique préservé

**Gate** :
- `python .sdd/harness_build.py --harness claude-code --agents-only --out .sdd/.build/claude` génère `.claude/agents/*.md` byte-identique aux `.claude/agents/*.md` actuels
- Golden test test_harness_identity.py vert
- 356 tests verts

**Rollback** : `git revert` — les bodies sont juste des copies, la source reste dans `.claude/` byte-copie qui n'a pas encore été supprimée.

---

### Batch 7 — Refresh CLAUDE.md + bascule façade générée (1-2h) — RISQUE MODÉRÉ

**Périmètre** : passer `.claude/` au statut de **façade générée** officiellement. Ajouter en-tête `GENERATED FROM .sdd/ — DO NOT EDIT` + garde CI.

**Actions** :

#### 7a — Réécriture des `@`-includes dans CLAUDE.md et agents/commands
- **Décision** : garder `@.sdd/rules/...` (les byte-copies dans `.sdd/rules/` répondent) OU réécrire en `@.sdd/rules/...` (plus propre, mais teste que Claude Code accepte des paths hors `.claude/` dans `@`-includes).
- Recommandation : **garder `@.claude/`** pour B7 (byte-copies suffisent), planifier réécriture en `@.sdd/` pour un batch B8 futur (une fois la garde CI mature).

#### 7b — En-tête généré + hash de build
- Chaque fichier généré par `harness_build.py` porte en tête :
  ```
  # GENERATED FROM .sdd/ — DO NOT EDIT
  # build-hash: sha256:{16 premiers chars}
  ```
- Modifier les adapters pour émettre cet en-tête (déjà en place partiellement — verifier)

#### 7c — Garde CI anti-drift
- Nouveau workflow `.github/workflows/harness-parity.yml` (ou hook local) :
  - À chaque PR touchant `.claude/`, `.codex/`, `.gemini/`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`
  - Exécute `python .sdd/harness_build.py ...` en mode dry-run
  - Diff byte-à-byte contre les fichiers committés
  - Échoue la PR si drift détecté (message : « éditer `.sdd/` puis re-run `harness_build` »)

#### 7d — Documenter dans INVARIANTS.yml
- Ajouter invariant n°14 `harness-parity` (déjà prévu par le plan §9 P0.3)
- Pointer vers l'enforcer (`test_harness_identity.py` + workflow CI)

**Gate** :
- `test_harness_identity.py` vert
- Sur une PR test qui édite `.claude/agents/po.md` directement : la CI doit ÉCHOUER avec message clair
- Sur une PR qui édite `.sdd/agents/po.body.md` et régénère : la CI PASS

**Rollback** : `git revert` du workflow CI + retirer en-tête generated.

---

## 5. Garanties de non-régression

### 5.1 Golden test comme verrou principal

À la fin de **chaque** batch, exécuter :

```bash
python .sdd/harness_build.py --harness claude-code \
    --agents-only --commands-only --rules-only --memory-only \
    --out .sdd/.build/claude
diff -r .sdd/.build/claude .claude/  # doit être vide (byte-identité)
```

Si diff non-vide → STOP → rollback → diagnostiquer.

### 5.2 Tests — les 356 doivent rester verts

```bash
# À la fin de chaque batch :
python -m pytest .sdd/python/tests/ -q          # 212 attendus
python -m pytest .sdd/python/tests_legacy/ -q   # 144 attendus (après B5)
# ou avant B5 :
python -m pytest .sdd/python/tests/ -q       # 144
```

Régression → STOP + rollback.

### 5.3 Framework smoke

```bash
python .sdd/python/sdd_admin/framework_smoke.py
```

Doit passer les gates : `stacks-count`, `agents-count`, `commands-count`, `invariants`.

### 5.4 Test manuel bout-en-bout

Après B5 + B6 (les 2 batches sensibles) : lancer manuellement une commande simple qui exerce plusieurs sous-systèmes (`python .sdd/python/sdd_admin/framework_smoke.py` OU un `/sdd-help` synthétique). Zero erreur en stdout.

### 5.5 Points de contrôle git

- **Avant B1** : `git tag pre-migration-common`
- **Avant B5** : `git tag pre-python-move`
- **Avant B6** : `git tag pre-body-extraction`
- **Après B7** : `git tag migration-common-complete`

En cas de désastre non détecté par les gates : `git reset --hard {tag}` puis analyse.

---

## 6. Effort estimé et séquencement

| Batch | Contenu | Effort | Risque | Cumul |
|---|---|---:|:---:|---:|
| B1 | Contenus purs (stacks, templates, ADRs, rubrics, benchmarks, mkdocs) | 2-3h | 🟢 minimal | 3h |
| B2 | Rules + docs | 2h | 🟢 faible | 5h |
| B3 | Skills | 1h | 🟢 faible | 6h |
| B4 | Loader + INVARIANTS + config + bootstrap | 30min | 🟢 faible | 6.5h |
| B5 | Python (5 sous-batches, `paths.py` unifié, 233+97 refs) | 5-8h | 🔴 élevé | 14.5h |
| B6 | Bodies agents + commandes | 2-3h | 🟡 modéré | 17.5h |
| B7 | Bascule façade générée + garde CI | 1-2h | 🟡 modéré | 19.5h |
| **Total** | | **13-19h** | | |

**Fenêtre recommandée** : 2-3 jours avec vérification humaine entre B4 et B5, puis entre B5 et B6.

**Séquencement critique** : B1→B4 peuvent être faits d'affilée (risque faible). **B5 impose une pause** — c'est là que ça peut casser. **B6→B7 dépendent de B5** (les scripts Python doivent être sous `.sdd/` pour que le transpileur soit dans le bon package).

---

## 7. Points de décision à trancher avant démarrage

Ces choix influencent le plan — à valider par le Tech Lead avant B1 :

1. **Byte-copies dans `.claude/` — combien de temps ?**
   - Option A : gardées jusqu'à B7 (bascule façade), retirées au coup par coup après régénération OK
   - Option B : retirées après chaque batch (test que `harness_build.py` régénère bien)
   - **Recommandation** : A (moins de risque)

2. **Fusion `.sdd/python/tests/` vs `.sdd/python/tests/`** — 2 dossiers ou 1 ?
   - Option A : 2 dossiers séparés (`tests/` neuf + `tests_legacy/` migré) — plus lisible transitoirement
   - Option B : fusion immédiate dans `tests/`
   - **Recommandation** : A pour B5, unification en B8 futur

3. **Réécriture `@.claude/` → `@.sdd/`** — dans B7 ou plus tard ?
   - Option A : dans B7 (propre, mais teste la résolution `@` cross-tree)
   - Option B : jamais — `.claude/` byte-copies gardent les refs résolvables
   - **Recommandation** : B (les byte-copies sont générées, aucun coût de maintien)

4. **Skills — mécanisme d'auto-trigger** — préserve-t-on dans `.sdd/skills/` ?
   - **Non négociable** : oui, byte-copies obligatoires dans `.sdd/skills/` (auto-trigger Claude Code)

5. **`settings.local.json` — machine-local** — comment le migrer ?
   - **Non déplaçable** : reste dans `.claude/settings.local.json` (permissions machine spécifiques utilisateur)
   - Action : documenter le nouveau path `Bash(python:.sdd/python/**)` dans B5.e (manuel)

---

## 8. Rollback global

Si un batch casse quelque chose de non détecté par les gates :

```bash
# Retour au tag avant le batch défectueux
git reset --hard pre-python-move   # exemple

# Ou revert du/des commits
git revert HEAD~3..HEAD             # 3 derniers commits
```

Aucun batch n'introduit de changement destructif irréversible côté disque
(le `git mv` est trackable, les byte-copies sont commitées, les tests
protègent contre les régressions silencieuses).

**Le seul point non-revertible** : les décisions humaines dans le
`settings.local.json` (permissions locales) — mais ce fichier n'est pas
commité, donc chaque machine gère son rollback local.

---

## 9. Pointeurs

- Plan général : `MIGRATION-PLAN-multi-harness-multi-provider.md` (racine repo)
- État actuel : `.sdd/README.md`
- Transpileur : `.sdd/harness_build.py`
- Golden test : `.sdd/python/tests/test_harness_identity.py` (via harness_diff)
- Tests neufs : `.sdd/python/tests/` (212)
- Tests legacy : `.sdd/python/tests/` (144)
- Matrice mécanismes : `.sdd/capability-matrix.yml`
- ADR fondateur : `.sdd/docs/adrs/ADR-20260724T164529-harness-and-provider-abstraction.md`
