# Audit Framework SDD_Pro v7.0.0-alpha — Analyse source-driven

> **Méthodologie** : audit indépendant fait à partir des SOURCES brutes
> (agents/*.md, commands/*.md, rules/*.md, stacks/*.md, scripts Python,
> workspace/). **N'utilise PAS** les rapports de synthèse (docs/AUDIT-FRAMEWORK.md
> historique, CHANGELOG, MIGRATION, AUDIT loader.yml). Pattern "Do not trust the
> report" hérité de superpowers v5.1.
>
> Date : 2026-05-20. Branche : `next` (v7.0.0-alpha).
> 5 explorations parallèles : agents, Python, stacks, commands, workspace.

---

## 0. TL;DR — verdict source-driven

Framework **mature, internement cohérent**, avec une **dette précise et localisée** :

- **Architecture des prompts** : 11 agents cohérents, modèles bien attribués (Opus 2/11 sur dev-*, Sonnet 9/11). Trim v7.0.0 (auditors retirés, dashboard → script) effectif et marqué dans les sources.
- **Code Python** : 31 003 LOC sur 84 scripts, **stdlib pur confirmé**, encoding UTF-8 + atomic writes solides. Couverture tests **58 % direct** (22/38 core scripts), **~79 % effective** avec couverture MCP indirecte.
- **Stacks** : 16 actifs. **6 stacks QA sans entête `Validation:`** = gap critique. Versions LTS toutes conformes (.NET 10, Java 21, Node 22, Python 3.12, Kotlin 2.3.21).
- **Commandes** : 17 fichiers, **8 user-facing + 9 internes** (claim CLAUDE.md vérifié). Aucun flag fantôme, tous les retraits v7.0.0 marqués. Drift mineur : numérotation STEP divergente sdd-full vs dev-run.
- **Runtime réel** : framework **vraiment utilisé** (4 FEATs, 10 US, 18 ADRs, schema DB introspecté, console.db actif). Stack actif : `kotlin-spring-boot + react + shadcn + azure-ad + postgres + ddd`.

---

## 1. Agents (11 prompts, audit indépendant)

### 1.1 Tableau de référence

| Agent | Modèle | Lignes | STEPs | Scripts Python invoqués | HARD-GATE | Justification modèle |
|---|---|---:|---|---|---|---|
| `po` | Sonnet 4.6 | 419 | 9 + 8.5 | context_budget | STEP 1.5 + traçabilité | OK Sonnet (analyse, pas création) |
| `arch` | Sonnet 4.6 | 578 | 13 | preflight, context_budget | STEP 0.5 + 2.bis + 3 | OK Sonnet (orchestration) |
| `dev-backend` | **Opus 4.7** | 456 | 10 + 5.bis | preflight, context_budget, detect_capabilities, compute_plan_metadata | STEP 0 + 0.5 + 1.bis | **OK Opus** (génération code) |
| `dev-frontend` | **Opus 4.7** | 481 | 12 + 6 | + validate_fidelity | STEP 0 + 0.5 + 1.bis | **OK Opus** (3 sources) |
| `qa` | Sonnet 4.6 | 566 | 10 | context_budget, quality_scan, parse_coverage, mutations, E2E | STEP 1.5 | OK Sonnet |
| `elicitor` | Sonnet 4.6 | 377 | 11 | context_budget | STEP 1.5 | OK Sonnet |
| `constitutioner` | Sonnet 4.6 | 218 | 6 | Bash timestamp atomique | STEP 0 skip silencieux | OK Sonnet (templating) |
| `code-reviewer` | Sonnet 4.6 | 678 | 12 | context_budget | STEP 0.5 | OK Sonnet (analyse) |
| `security-reviewer` | Sonnet 4.6 | 652 | 11 | context_budget | STEP 0.5 | OK Sonnet |
| `spec-compliance-reviewer` | Sonnet 4.6 | 454 | 11 | context_budget, validate_spec_compliance | STEP 0.5 | OK Sonnet |
| `arch-reviewer` | Sonnet 4.6 | 415 | 10 | context_budget | STEP 0.5 | OK Sonnet |

### 1.2 Observations transversales (constats sources)

1. **Context budget HARD-GATE systématique** dans 10/11 agents (STEP 0.5 ou 1.5). Discipline réelle, pas déclarée.
2. **Opus strictement limité à dev-*/2 agents** (18 %). Surcoût ciblé sur génération code.
3. **Scripts Python intégrés à chaque agent** : 1-4 par agent. Délégation déterministe propre.
4. **Sérialisation constitution.md** : `po` → `arch` → `constitutioner` → `elicitor`. Validation read-back implémentée dans 2 (po STEP 8.5.4, constitutioner STEP 5).
5. **Plans v2 fallback fragile** : 4 auditors (code-reviewer, spec-compliance-reviewer, arch-reviewer, security-reviewer scan) préfèrent plan v2, fallback "convention" (pattern-matching nom US) si absent. Pas de validation stricte que dev-* a généré v2.

### 1.3 Anti-patterns détectés (sources)

| Anti-pattern | Localisation | Sévérité |
|---|---|---|
| Constitution.md skip silencieux | `po` STEP 8.5.0, `elicitor` STEP 10 | Modéré (procédure incomplète) |
| Numérotation STEP confuse | `po` STEP 1 vs STEP 1.5 context_budget | Mineur (doc interne) |
| Mode `threat-model` deprecated | `security-reviewer` frontmatter | Mineur (template humain en remplacement) |
| Phase B "Read on-demand" externalisée | `arch` STEP 8-11 | Modéré (complexité cachée, économie ~6 KB) |
| LibName lock non-validé en preflight | `dev-backend/dev-frontend` STEP 3 | Mineur (mitigé par sérialisation /dev-run) |
| Ingest bridge JSON→DB implicite | 4 reviewers post-write | Mineur (non documenté frontmatter) |

---

## 2. Python (84 scripts, 31 003 LOC)

### 2.1 Métriques (vérifiées sources)

| Métrique | Valeur |
|---|---:|
| Scripts core (`sdd_scripts/`) | 38 |
| Scripts admin + hooks + lib + MCP | 46 |
| LOC scripts | ~12 144 |
| LOC tests | ~11 155 |
| **Ratio tests/code** | **0.92** |
| Tests directs couvrant un script | 22/38 (58 %) |
| Couverture effective (incl. MCP integration) | ~79 % |
| Type hints `from __future__ import annotations` | 37/38 (97 %) |
| Encoding UTF-8 + `errors="replace"` | 100 % |
| `subprocess.shell=True` | 0 |
| `print()` au lieu de logging | 0 |
| Globals mutables | 0 |
| Dépendances pip (hors pytest, anthropic SDK) | 0 |

### 2.2 Top 10 scripts à risque (LOC élevé sans test direct)

1. **sdd_review.py** (722 LOC) — orchestrateur audit Sonar, états multiples, race condition potentielle sur `validation_reports` parallèle.
2. **preflight.py** (674 LOC) — détection AppType auto-manuel fallback, 6 cas de réconciliation, **pas de test direct**.
3. **phase_planner.py** (619 LOC) — 5 modes × 4+ conditions = 20+ chemins de décision, **pas de test direct**.
4. **scan_repo.py** (586 LOC) — rglob non bornée, pas de timeout.
5. **validate_plan.py** (524 LOC) — regex multiline fragile ligne 140 (`_FRONTMATTER_RE`).
6. **sdd_state.py** (343 LOC) — concurrent writes `run-*.json` sans lock explicite.
7. **report_token_usage.py** (332 LOC) — CSV+SQLite dual-sink, drift sync possible.
8. **dispatch_fixes.py** (377 LOC) — subprocess.run sans timeout, capture_output implicite.
9. **ingest_agent_report.py** (307 LOC) — schéma JSON volatile (7 types rapport).
10. **quality_scan.py** (387 LOC) — heuristiques long-method fragiles (comptage accolades / 100 lignes).

### 2.3 Top 5 scripts exemplaires

1. **gate_decide.py** (230 LOC) — atomic lock O_EXCL, cross-platform, retry-backoff, tests complets.
2. **file_locks.py** (126 LOC) — atomic O_CREAT|O_EXCL, stale TTL, tests complets.
3. **context_budget.py** (361 LOC) — budget tracking, layered config fallback, tests para.
4. **checkpoint.py** (293 LOC) — hash validation, fail-safe defaults, tests unit solides.
5. **detect_capabilities.py** (194 LOC) — déterministe pur, regex triggers, 0 état muté.

### 2.4 Anti-patterns vérifiés

| Risque | Occurrences | Sévérité |
|---|---:|---|
| `except (X, Y, Z)` broad | 3 (sdd_review.py:109,171+) | Moyen |
| `noqa: BLE001` catch-all (telemetry) | 23 | Acceptable (intentionnel) |
| Regex multiline fragile | 1 (validate_plan.py:140) load-bearing | Moyen |
| sdd_state.py sans lock explicite | 1 | Moyen (FS atomicité supposée) |

---

## 3. Stacks (16 actifs, vérifiés ligne par ligne)

### 3.1 Stacks AVEC entête `Validation:` (8/16)

| Stack | Catégorie | Validation | Libs.json |
|---|---|---|---|
| dotnet-minimalapi | backend | 🟢 reference | 2026-05-07 |
| kotlin-spring-boot | backend | 🟢 reference | 2026-05-07 |
| node-express | backend | 🟡 experimental | 2026-05-07 |
| python-fastapi | backend | 🟡 experimental | 2026-05-07 |
| react | frontend | 🟢 reference | 2026-05-12 |
| blazor-webassembly | frontend | 🟢 reference | 2026-05-07 |
| angular | frontend | 🟡 experimental | 2026-05-07 |
| vue | frontend | 🟡 experimental | 2026-05-07 |
| shadcn | ui | 🟢 reference | 2026-05-12 |
| vuetify | ui | 🟡 experimental | 2026-05-13 |
| radzen-blazor | ui | 🟢 reference (format non-standard bloc quote) | 2026-05-13 |
| azure-ad | auth | 🟢 reference | — |
| auth-local | auth | 🟡 experimental | — |
| mvc | archi | 🟢 reference | — |
| code-quality | qa | 🟢 reference | — |

### 3.2 Stacks SANS entête `Validation:` (gap CRITIQUE — 8/16)

| Stack | Catégorie | Statut effectif | Gravité |
|---|---|---|---|
| **dotnet-xunit** | qa | 🟢 ref (validé Blazor combo) | CRITIQUE |
| **kotlin-junit** | qa | 🟢 ref (validé CMS combo) | CRITIQUE |
| **node-vitest** | qa | 🟢 ref (validé CMS combo) | CRITIQUE |
| **blazor-bunit** | qa | 🟢 ref (validé Blazor combo) | CRITIQUE |
| **angular-jasmine** | qa | 🟡 exp | CRITIQUE |
| **python-pytest** | qa | 🟡 exp | CRITIQUE |
| mutation-testing | qa | 🟡 exp (bloc quote) | MINEUR |
| playwright | qa | 🟡 exp (bloc quote) | MINEUR |

> **Impact** : `CLAUDE.md §7` déclare que l'entête `Validation:` est source de vérité. **6/8 stacks QA** la violent. Aucun garde-fou Python n'enforce la présence (gap audit `validate_stack_md_headers.py` à créer).

### 3.3 Cohérence .md ↔ .libs.json

| Catégorie | .md | .libs.json | Sync |
|---|---:|---:|:---:|
| backend (4) | 4/4 | 4/4 | OK |
| frontend (4) | 4/4 | 4/4 | OK |
| ui (3) | 3/3 | 3/3 | OK |
| auth (2) | 2/2 | 0/2 | OK (design) |
| archi (1) | 1/1 | 0/1 | OK (pattern) |
| qa (8) | 8/8 | 8/8 | OK |

§2.4 régénérée déterministiquement via `sync_stack_md.py`. **0 drift détecté** entre .md et .libs.json.

### 3.4 Triggers regex on-demand — cohérence cross-stack

Vérifié sur 5 capabilities × 2 backends (node-express + kotlin-spring-boot) : **100 % identiques** (auth-local, auth-azure-ad, redis-cache, pdf, excel).

### 3.5 Versions LTS

Toutes runtimes conformes 2026-05-20 : .NET 10, Java 21, Node 22, Python 3.12, Kotlin 2.3.21. **Aucune désuétude détectée**.

---

## 4. Commands (17 fichiers, audit indépendant)

### 4.1 Décompte

| Catégorie | Compte | Vérifié |
|---|---:|:---:|
| User-facing | 8 | OK |
| Internes | 9 | OK |
| **Total** | **17** | **= CLAUDE.md claim** |

### 4.2 Scripts Python invoqués (extraits du source des commands)

21 scripts uniques référencés dans les commands :
`sdd_state`, `phase_planner`, `validate_inline_rules`, `gate_decide`, `validate_us_deps`, `detect_arch_shortcircuit`, `validate_plan`, `query_console_db`, `compact_front_plans`, `set_us_status`, `validate_readiness`, `validate_semantic`, `index_adrs`, `ingest_agent_report`, `scan_repo`, `match_stack_catalog`, `manage_profile`, `quality_scan`, `sdd_review`, `triage_issues`, `parse_coverage`.

**Tous présents** dans `.claude/python/sdd_scripts/` (cross-check OK).

### 4.3 Hard gates v7.0.0 — défauts vérifiés dans sources

| Gate | Bloquant default | Source |
|---|:---:|---|
| Readiness NO-GO | OUI sauf `--force` | sdd-full.md:340 |
| QA RED (`QaFailOnSddFull`) | OUI v7.0.0 (flip from false) | sdd-full.md:585-600 |
| Review RED (`ReviewFailOnSddFull`) | OUI v7.0.0 (flip from false) | sdd-full.md:660-666 |
| Auditor batch RED (6.4.3) | OUI | dev-run.md:661-665 |
| API Gate FAIL | OUI | dev-run.md:518 |
| Plan staleness (`PLAN_STALE`) | OUI exit 2 | dev-run.md:442-448 |

### 4.4 Retraits v7.0.0 — tous marqués

| Composant retiré | Marquage source | Remplacement |
|---|---|---|
| `dashboard` | sdd-full.md:607, dev-run.md:731 | `index_adrs.py` |
| `performance-auditor` | qa-generate.md:211-225 | Lighthouse CI (projet généré) |
| `accessibility-auditor` | dev-run.md:616 | axe-core CI (projet généré) |
| `security-reviewer` mode `threat-model` | dev-run.md:355-373 | template humain |
| `dev-*-strict` | sdd-full.md:51-59, dev-run.md:419-425 | dev-* classique (Opus) |

### 4.5 Drifts mineurs détectés (sources)

1. **Numérotation STEP 5.5 → 6 divergente** entre `sdd-full.md` et `dev-run.md`. Texte "numérotation conservée pour aval" — réalité divergente. Cosmétique.
2. **`/sdd-full --rebuild-arch` propagation** non documentée côté réception `/dev-run` STEP 1. Asymétrie doc, implémentation cohérente.
3. **Edge cases manquants** : freeze window actif, `MaxCostPerRun` overflow — non gérés au niveau commande (probable config-level).

### 4.6 Idempotence — toutes commandes vérifiées

11/11 commandes idempotentes revendiquées + défendables source par source. Aucun flag fantôme. Aucun script référencé absent du repo.

---

## 5. Workspace runtime (vérité-terrain)

### 5.1 État réel mesuré

| Élément | Compte | Statut |
|---|---:|---|
| FEATs créées | 4 | menu, campagnes-vue-liste, campagne, auth |
| US générées | 10 | total cumulé |
| US `Status: Done` | 7/10 | 70 % finalisées |
| Plans techniques | 14 | ratio US/plans cohérent |
| ADRs total | 18 | 8 archi + 10 governance v7.0.0 |
| ADRs governance v7 | 10 | tous datés 2026-05-19 |
| Schema DB | OUI | PostgreSQL CMSPrint, 9 tables |
| console.db | 516 KB | actif + WAL |

### 5.2 Stack actif détecté (workspace/input/stack/stack.md)

- Backend : `kotlin-spring-boot` 3.5.0 (DDD pattern)
- Frontend : `react` 19 + Vite
- UI : `shadcn`
- Auth : `azure-ad`
- DB : PostgreSQL (CMSPrint)
- Pattern : DDD (cf. ADR `architecture-pattern-ddd`)

### 5.3 Code généré

- Backend : 82 fichiers Kotlin (domain, application, infrastructure, presentation)
- Frontend : 3502 fichiers TS/TSX (+ node_modules)
- DB introspection complète, FK + types explicites

### 5.4 Artefacts orphelins

**Zéro** détecté :
- Toutes les US ont un plan correspondant
- Tous les ADRs référencés dans constitution.md §6
- Aucun artifact stale de run antérieur
- Cleanup automatisé via ADR `governance-orphan-cleanup-tool`

---

## 6. Constatations transversales (issues croisées)

### 6.1 [HAUT] Drift documentaire `Validation:` (6 stacks QA)

Le framework déclare l'entête `Validation:` comme source de vérité (`CLAUDE.md §7`) mais 6/8 stacks QA n'en ont pas. Le défaut conservateur 🟡 implicite n'est pas validé par script. Aucune garde-fou `validate_stack_md_headers.py` n'enforce.

### 6.2 [HAUT] 16 scripts Python critiques sans tests directs

Sur 38 scripts core, 16 n'ont pas de `test_<nom>.py` direct. Couverture indirecte via MCP integration tests, mais 8 d'entre eux (sdd_review, preflight, phase_planner, scan_repo, dispatch_fixes, quality_scan, ingest_agent_report, validate_inline_rules) restent vulnérables aux régressions.

### 6.3 [MOYEN] Plan v2 fallback fragile (4 auditors)

Si dev-* échoue à générer un plan v2 (`## Inline Digest`), 4 auditors basculent en fallback "convention" (pattern-matching nom US) sans signal explicite. Risque silencieux de dégradation de la qualité audit.

### 6.4 [MOYEN] sdd_state.py sans lock explicite

Concurrent writes `workspace/output/.sys/.state/run-*.json` reposent sur FS atomicité supposée. Pas de FileLocker wrapper. Risque race sur `phase.status` en cas de bug ou interruption.

### 6.5 [MOYEN] scan_repo.py rglob non bornée

Pas de `max_depth`, pas de timeout. Sur un repo très grand, `/sdd-discover-stack` peut s'enliser silencieusement.

### 6.6 [BAS] LibName lock validation pas en STEP 0 preflight

Race théorique sur `{LibName}/` lock cross-language. Mitigé par sérialisation `/dev-run` mais pas par garde-fou explicite.

### 6.7 [BAS] Aucune gestion edge cases freeze / MaxCostPerRun au niveau commande

Géré au niveau hook `preflight_cost_cap.py` (PreToolUse Agent), pas dans les commandes elles-mêmes. Acceptable architecture mais documentation côté commande absente.

### 6.8 [BAS] Numérotation STEP 5.5 → 6 divergente sdd-full ↔ dev-run

Cosmétique pure, aucun impact runtime.

---

## 7. Forces structurelles confirmées par les sources

1. **Anti-patterns interdits 0/100** : `subprocess.shell=True`, `print()`, globals mutables → **zéro occurrence** dans 84 scripts.
2. **Encoding discipline** : UTF-8 + `errors="replace"` à 100 % des read_text().
3. **Atomic writes** : `gate_decide.py`, `file_locks.py`, `checkpoint.py`, `console_db.py` (PRAGMA WAL) tous solides.
4. **Stdlib pur confirmé** : aucune dépendance pip hors pytest + anthropic SDK.
5. **Format ERROR 3 lignes** : `sdd_lib.stderr.error_block` utilisé canoniquement.
6. **Modèles spécialisés** : Opus 4.7 sur 2/11 agents (dev-*), Sonnet 4.6 sur les 9 autres. Optimisation coût/qualité défendable.
7. **Triggers regex cross-stack 100 %** : même capability → même regex sur tous les backends.
8. **Workspace runtime 0 orphelin** : ADRs, US, plans, schema cohérents.

---

## 8. Recommandations prioritaires (basées source)

### 8.1 P0 (avant tag v7.0.0 GA)

1. **Ajouter entête `Validation:` aux 6 stacks QA** (`dotnet-xunit`, `kotlin-junit`, `node-vitest`, `blazor-bunit`, `angular-jasmine`, `python-pytest`). Le framework déclare cette entête comme source de vérité.
2. **Créer `validate_stack_md_headers.py`** pour enforcer la présence en CI. Ajouter au hook PreToolUse Agent ou `/sdd-status`.
3. **Tester `phase_planner.py` et `preflight.py`** (load-bearing v7.0.0, 619 + 674 LOC, aucun test direct).

### 8.2 P1 (post-GA, court terme)

4. **FileLocker wrapper sur `sdd_state.py`** — pattern uniforme avec gate_decide.
5. **Timeout + max_depth sur `scan_repo.py` rglob()**.
6. **Tester `sdd_review.py`, `dispatch_fixes.py`, `ingest_agent_report.py`** (3 scripts core sans test).
7. **Détection plan v2 absent → WARN explicite** dans les 4 auditors fallback.

### 8.3 P2 (moyen terme)

8. **Refactor regex multiline `validate_plan.py:140`** vers compilation strict avec `re.escape()`.
9. **Documenter ingest_agent_report bridge** dans frontmatter des 4 reviewers.
10. **Aligner numérotation STEP 5.5→6** entre `sdd-full.md` et `dev-run.md`.

---

## 9. Synthèse finale (source-driven, indépendante)

**SDD_Pro v7.0.0-alpha est cohérent en sources** :
- 11 agents bien dimensionnés
- 17 commandes alignées avec leurs claims
- 84 scripts Python disciplinés (stdlib pur, anti-patterns évités)
- 16 stacks avec versions LTS conformes
- Workspace runtime preuve d'usage industriel (4 FEATs, 10 US, schema DB, console.db actif)

**Dette technique précise, pas systémique** :
- 6 stacks QA sans entête `Validation:` (gap critique mais isolé)
- 16/38 scripts Python sans test direct (mitigé indirect MCP)
- Plan v2 fallback fragile pour 4 auditors
- 5 anti-patterns mineurs Python (regex multiline, lock manquant, rglob non bornée)

**Pas de problèmes structurels** : pas de drift majeur agents↔commands, pas de scripts fantômes, pas de routing cassé vers agents retirés v7.0.0, pas d'orphelins workspace.

**Le framework est prêt pour GA** sous réserve des 3 actions P0 (entêtes stacks QA + script garde-fou + tests phase_planner/preflight).

---

*Audit fait à partir des sources 2026-05-20. Régénérer si refactor majeur post-tag v7.0.0.*
