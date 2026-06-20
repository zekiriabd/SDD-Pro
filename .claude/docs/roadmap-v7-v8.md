# SDD_Pro — Roadmap v7 → v8 (audit CTO 2026-05-20)

> Document de planification stratégique post-audit CTO 2026-05-20. Donne
> l'état d'avancement réel des 22 recommandations P0/P1/P2 + plan v7.1
> et v8 stratégique.

---

## 1. État v7.0.0-alpha (2026-05-20)

### P0 — Avant tag v7.0.0 final (8 items)

| # | Item | État | Détail |
|---|---|:---:|---|
| 1 | PoC ROI 3 runs FEAT M | 🟡 partiel | 1 run FEAT 2 mesuré ($23.76, 40.8% cache hit). Manque : 2 runs supplémentaires pour variance. |
| 2 | Mutation testing | 🟢 stack + STEP 8.5 câblés | `stacks/qa/mutation-testing.md` + `qa.md` STEP 8.5. À valider sur PoC. |
| 3 | MaxCostPerRun $50 | 🟢 done | Config + `preflight_cost_cap.py` hook + classe `[COST_CAP_EXCEEDED]` + **hard-block sans condition is_ci (R1 fix post-audit)** + **scope by run_id (trou #1 fix)** + **telemetry health alert (trou #2 fix)**. |
| 4 | SDD_ALLOW_FORCE verrou bypasses | 🟢 done | sdd-full STEP 3.6.quart + classe `[FORCE_CUMUL_REJECTED]`. |
| 5 | CI templates a11y/perf | 🟢 done | `templates/ci-quality.github-actions.yml.template` + arch.md instancie si `CiTemplatesGeneration: true`. |
| 6 | QaFailOnSddFull symétrie | 🟢 done | Config + sdd-full STEP 4.5 + classe `[QA_FAIL_BLOCKING_SDD_FULL]`. |
| 7 | Migrations versionnées console.db | 🟢 done | Infra existait, ajout migration 0002 (`qa_mutation`) + SCHEMA_VERSION=2. |
| 8 | Cache hit rate doc + markers | 🟡 partiel | Mesuré (40.8%) + doc `cache-strategy.md`. Implémentation markers reportée v7.1. |

**Verdict v7.0.0 tag** : **7/8 P0 done** → tag bloqué uniquement par l'item 1 (2 runs supplémentaires PoC ROI).

> **Statut v7.0.0** (audit CTO closure 2026-06-07) : **v7.0.0 GA tagué**
> sur `main`. 20 Critical + 38 Major audit issues fermés. v6.10.4
> conservée en LTS pour projets legacy. Cf. `@.claude/docs/VERSIONING.md`
> (SSoT) pour la politique.

### P1 — v7.1 post-freeze (9 items)

| # | Item | État | Détail |
|---|---|:---:|---|
| 9 | Kahn batching strict | 🟢 done | `validate_us_deps.py::layered_kahn_batches()` + dev-run STEP 2.bis. |
| 10 | feat-generate étoffé | 🟢 done | `feat.template.md` v7 + `Quantified Goal` + `Non-Functional Constraints` + readiness check. |
| 11 | feat-hash dans US Covers | 🟢 done | Template `Parent FEAT hash:` + po.md calcule sha256 + classe `[FEAT_HASH_MISMATCH]` + **consommateur câblé `preflight.py::_check_feat_hash` v7.0.0-alpha post-audit** (US legacy = WARN, mismatch = ERROR). |
| 12 | Hard cap US 10 + --allow-large-feat | 🟢 done | `UsGranularityHardCap: 10` + `UsGranularityWarnAt: 6` (config). Flag CLI reporté v7.1. |
| 13 | /feat-deepen obligatoire complexity ≥3 | 🟢 done | `FeatDeepenThreshold: 3` + `FeatDeepenMode: warn` (config) + validate_readiness honore. |
| 14 | Dé-dup file+line cross-source | 🟢 done | `sdd_review.py::deduplicate_findings()` + CANONICAL_CLASS mapping. |
| 15 | Auditors lean preset | 🟡 partiel | Flag `LeanReviewersPreset` ajouté. Activation auto par taille FEAT reportée v7.1. |
| 16 | Stack qa/playwright | 🟡 doc only | `stacks/qa/playwright.md` créé. Câblage `qa.md` STEP 8.bis reporté v7.1. |
| 17 | IntegrationTestMode containers | 🟢 done | Flag config `IntegrationTestMode: memory|hybrid|containers`. |

**v7.1** : 5/9 done complet, 4 partiels (avec roadmap claire).

### P2 — v7.2+ stratégique (5 items)

| # | Item | Plan v8 | Effort estimé |
|---|---|---|---|
| ~~24~~ | ~~`audit_orphans.py` + `cleanup_orphans.py`~~ | ✅ **DONE v7.0.0-alpha (2026-06-05)** : scripts livrés sous `sdd_admin/`, 11 tests pytest verts, doc `orphan-cleanup-policy.md` mise à jour, périmètre PROTÉGÉ enforcement, backup `.trash/{ts}/` avec recovery 7j, telemetry `console.db.events`. | — |
| 25 | `app.jsx` refactor (2056 L monolithe → 5-8 composants) + ≥1 Playwright fumée console + setup React modules (drop Babel client-side). | 🟡 **PARTIEL v7.0.0-alpha (2026-06-05)** : test smoke `tests/smoke.test.js` ajouté (intégré CI ; ex `structure.smoke.test.js` renommé/refactor 2026-06-08). Garde le mode "no build step" pour l'instant. Reste roadmap v7.2 : décision bundler (esbuild minimal) puis split réel en `app-shell.jsx`/`app-charts.jsx`/`app-dashboard.jsx`/`app-features.jsx` + Playwright. | 4-6 jours restants |
| 26 | `dev-run.md` / `sdd-full.md` : remplacer le pseudo-code orchestrateur par un script Python testable. | 🟡 **PARTIEL v7.0.0-alpha (2026-06-05)** : `sdd_scripts/sdd_full_planner.py` livré (planner déterministe — produit un PLAN JSON exécutable avec phases + status `pending/skip/blocked`, 10 tests pytest verts). Reste roadmap v7.2 : remplacer le pseudo-code dans `sdd-full.md` par invocation `python sdd_full_planner.py --json` puis `jq` les phases ; refactor symétrique `dev-run.md`. Décision tracée dans `CHANGELOG.md` entrée v7.0.0-alpha (pas d'ADR séparé). | 4-6 jours restants |
| 18 | Combos validés ≥ 5 | PoC : `dotnet+react+azure`, `kotlin+react+azure`, `dotnet+vue+azure`, `python+react+local`, `kotlin+vue+local`. Méthodo `docs/poc-roi-methodology.md`. | 5× 0.5 jour-homme = 2.5 jours |
| 19 | Cross-model validation QA | Opus review Sonnet (vraie indépendance épistémique). Nécessite refonte loader + retry budget. | 1-2 semaines |
| 20 | Mémoire Claude scoped Tech Lead | Cf. discussion ouverte 2026-05-18. Sans casser source-first invariant. Implementation server-side. | 1 semaine |
| 21 | Console web packagée | Embarquer `workspace/console/` dans framework (template + serveur Node minimal). Actuellement couplage soft. | 3-5 jours |
| ~~22~~ | ~~Sweep stubs backward-compat~~ | ✅ **DONE v7.0.0-alpha post-audit 2026-05-20** : 8 stubs supprimés + 2 principes relocés à `docs/principles/`. 45+11+7 refs migrées dans agents/commands/python/stacks. Banners des 4 rules consolidées mis à jour. 0 ref orpheline (vérifié grep). |
| ~~R7~~ | ~~Réactivation a11y/perf via ingest CI déterministe~~ | ✅ **DONE v7.2.0 (2026-05-24)** : Option B livrée. `sdd_scripts/ingest_axe.py` (axe-core JSON → `qa_a11y`, 53 assertions) + `sdd_scripts/ingest_lighthouse.py` (Lighthouse → `qa_performance`). Template CI `templates/ci-quality.github-actions.yml.template` instrumenté (steps Python + dérivation FEAT depuis branche). `error-classification.md §1.9/§1.12` MAJ. Pas de coût LLM. `/sdd-review` lit déjà `qa_a11y`/`qa_performance` (aggrégation inchangée). |
| ~~R1~~ | ~~Adversarial review mode (BMAD pattern)~~ | ✅ **DONE v7.2.0 (2026-05-24)** : agent `adversarial-reviewer` (Sonnet 4.6, 240L, joue l'avocat du diable) + flag `/sdd-review --adversarial` + classe `[ADV_*]` (§1.15 — 5 angles : edge_case, fragile_assumption, hidden_tech_debt, failure_mode, ux_confusion). Verdict **purement informational** (jamais bloquant — pas mixé dans verdict consolidé). Persistance dans `validation_reports(report_type='adversarial')` via `ingest_agent_report --type adversarial` (7 nouveaux tests unit). Anti-duplication §2.5 stricte : drop des findings déjà émis par autres reviewers. 12ᵉ agent au framework. |
| 23 | Refactor 5 gros stacks `.md` > 800 L | `dotnet-minimalapi` (1016), `kotlin-spring-boot` (982), `react` (933), `python-fastapi` (849), `azure-ad` (795). Migrer §2.4 vers `.libs.json` (déjà partiellement fait via `sync_stack_md.py`), §3 conventions vers `docs/stacks/{id}-conventions.md`, garder `.md` à ~400 L (overview + layer mapping + scope). | 5× 1.5h = ~8h |

**Décision M4 audit v7.0.0-alpha (2026-05-21)** : item 23 deferred v7.1.
Rationale = **risque rupture compat agents** existants qui Read sélectivement
les §1.3 / §2.4 / §3 via offset/limit. Refactor nécessite (a) audit des
~80 invocations `Read .claude/stacks/.../X.md` dans `.claude/agents/`,
(b) test d'intégration sur les 2 combos validés C1/C2, (c) régénération
`.libs.json` pour chaque stack touché. Faible valeur immédiate vs risque —
les 5 stacks fonctionnent (`/sdd-full` les utilise sans drift), le cache
Anthropic absorbe le coût tokens. Décision conservée pour roadmap v7.1 ; pas d'ADR séparé pour l'instant
(le scope reste à arbitrer en sprint planning).

---

## 2. Plan v7.1 (post-freeze 2026-06-19)

Ordre suggéré (par dépendances) :

1. **Sweep stubs** (#22 P2) — 4 heures, prerequis pour réduire le volume framework.
2. **Cache markers** (#8 P0 reste) — instrumenter `loader.yml` champ `cache_layer`.
3. **Stack Playwright câblage** (#16 P1) — `qa.md` STEP 8.bis + migration 0003 `qa_e2e`.
4. **Mutation testing PoC** (#2 P0 validation) — 1 FEAT M pilote, mesurer mutation score réel.
5. **Lean reviewers auto** (#15 P1) — heuristique taille FEAT (S=lean / M+L=full).
6. **Flag CLI --allow-large-feat** (#12 P1) — propagation dans `feat-generate.md` + `us-generate.md`.
7. **Cross-model validation** (#19 P2) — proto sur 1 FEAT, mesurer indep épistémique.

---

## 3. Critères release v8.0.0 (estimé Q3 2026)

| Critère | Cible | Mesure |
|---|---|---|
| Combos validés bout-en-bout | ≥ 5 | PoC ROI par combo |
| Cache hit rate moyen Opus | ≥ 60 % | report_roi.py agrégé |
| Coût FEAT M médian | ≤ $15 | report_roi.py |
| Mutation score moyen | ≥ 60 % | qa_mutation aggregate |
| E2E coverage AC | ≥ 80 % AC UI | qa_e2e aggregate |
| Variance 3 runs FEAT M | ≤ 15 % | report_roi.py |
| Stubs backward-compat | 0 (tous supprimés) | grep `Read @.claude/rules/X.md` legacy = 0 |
| User-facing commands | 13 user-facing + 8 internes (CLAUDE.md §3) | acté v7.0.0+ (12 v7.0.0-alpha → 13 v7.0.0+ avec `/sdd-help`) |

---

## 4. Marketing « 13 user-facing + 8 internes » (v7.0.0+ avec `/sdd-help`)

Le découpage v7.0.0+ est `13 user-facing + 8 internes [debug]`
(cf. CLAUDE.md §3). v7.0.0-alpha avait 12 ; ajout `/sdd-help` (guidance
contextuelle, emprunt bmad-help) en v7.0.0+. Les internes sont
signalés `[debug]` dans la table. Évolutions futures envisagées :

- **v7.1** : audit usage réel (telemetry `token_usage`) — promouvoir
  toute commande interne dépassant un seuil d'invocations en user-facing.
- **v8.0** : réviser si l'usage révèle des commandes orphelines
  effectivement non-utilisées — décision data-driven, pas a priori.

---

## 4.bis. Décisions abandonnées en v7.0.0

| Décision | Statut | Raison | Reversibilité |
|---|---|---|---|
| **MCP integration** (`mcp.json`, `docs/MCP-SERVER.md`) | ❌ Abandonné v7.0.0 | Pas de consommateur production identifié, intégration jamais validée bout-en-bout. Coût maintenance > valeur démontrée. | Restauration v8+ possible si demande utilisateur (ADR `governance-major-mcp-reintroduction` requis). Récupération code : `git checkout main -- .claude/mcp.json .claude/docs/MCP-SERVER.md` (v6.10.4-LTS). |
| **`accessibility-auditor` (agent LLM)** | ❌ Retiré v7.0.0 | Coût LLM élevé pour bénéfice marginal (axe-core CI fait le même check en 0 token). | Remplacé par `ingest_axe.py` (Option B, v7.2.0). |
| **`performance-auditor` (agent LLM)** | ❌ Retiré v7.0.0 | Idem accessibility — Lighthouse CI fait le même check déterministe. | Remplacé par `ingest_lighthouse.py` (Option B, v7.2.0). |
| **`dashboard` (agent LLM)** | ❌ Retiré v7.0.0 | Génération HTML statique remplacée par console web React (`workspace/console/`). | console web restaurée v7.0.0-alpha (2026-06-05). |
| **`dev-*-strict` (variants Sonnet 4.6)** | ❌ Retirés v7.0.0 | Plans v2 + Inline Digest pas livrés bénéfice token attendu vs complexité. | Clé `PlanCacheStrict` tolérée no-op pour backward-compat. |

---

## 5. Risques résiduels post-v7.0.0

| Risque | Mitigation v7.0 | Mitigation v8.0 |
|---|---|---|
| Auto-confirmation bias QA | Mutation testing opt-in | Cross-model validation par défaut |
| Coverage = signal faible | Coverage gate + mutation testing | Mutation testing intégré au gate |
| In-memory ≠ prod DB | Flag containers opt-in | Containers défaut pour FEAT large |
| 4 reviewers redondants | Dé-dup cross-source done | Auto-routing par taille (LeanReviewersPreset) |
| Tokens caching opaque | Doc cache-strategy.md | cache_control markers explicites |

---

*Maintenu par Tech Lead, mis à jour à chaque release MAJOR/MINOR.*
