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
| 18 | Combos validés ≥ 5 | PoC : `dotnet+react+azure`, `kotlin+react+azure`, `dotnet+vue+azure`, `python+react+local`, `kotlin+vue+local`. Méthodo `docs/poc-roi-methodology.md`. | 5× 0.5 jour-homme = 2.5 jours |
| 19 | Cross-model validation QA | Opus review Sonnet (vraie indépendance épistémique). Nécessite refonte loader + retry budget. | 1-2 semaines |
| 20 | Mémoire Claude scoped Tech Lead | Cf. discussion ouverte 2026-05-18. Sans casser source-first invariant. Implementation MCP server-side. | 1 semaine |
| 21 | Console web packagée | Embarquer `workspace/console/` dans framework (template + serveur Node minimal). Actuellement couplage soft. | 3-5 jours |
| ~~22~~ | ~~Sweep stubs backward-compat~~ | ✅ **DONE v7.0.0-alpha post-audit 2026-05-20** : 8 stubs supprimés + 2 principes relocés à `docs/principles/`. 45+11+7 refs migrées dans agents/commands/python/stacks. Banners des 4 rules consolidées mis à jour. 0 ref orpheline (vérifié grep). |
| 23 | Refactor 5 gros stacks `.md` > 800 L | `dotnet-minimalapi` (1016), `kotlin-spring-boot` (982), `react` (933), `python-fastapi` (849), `azure-ad` (795). Migrer §2.4 vers `.libs.json` (déjà partiellement fait via `sync_stack_md.py`), §3 conventions vers `docs/stacks/{id}-conventions.md`, garder `.md` à ~400 L (overview + layer mapping + scope). | 5× 1.5h = ~8h |

**Décision M4 audit v7.0.0-alpha (2026-05-21)** : item 23 deferred v7.1.
Rationale = **risque rupture compat agents** existants qui Read sélectivement
les §1.3 / §2.4 / §3 via offset/limit. Refactor nécessite (a) audit des
~80 invocations `Read .claude/stacks/.../X.md` dans `.claude/agents/`,
(b) test d'intégration sur les 2 combos validés C1/C2, (c) régénération
`.libs.json` pour chaque stack touché. Faible valeur immédiate vs risque —
les 5 stacks fonctionnent (`/sdd-full` les utilise sans drift), le cache
Anthropic absorbe le coût tokens. Trace ADR à créer lors du sprint v7.1
sous identifiant `governance-major-stacks-refactor`.

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
| User-facing commands | 8 réelles (pas 17) | CLAUDE.md §3 cohérent avec usage réel |

---

## 4. Marketing "8 user-facing + 9 internes"

Audit CTO §6.15 a flag cette communication comme "aspirationnelle". Action :

- **v7.1** : préciser dans CLAUDE.md §3 que les 9 "internes" sont en
  réalité **invocables debug** (pas user-facing primaires) — distinguer
  visuellement (badge `[debug]`) dans la table.
- **v8.0** : réviser le découpage — privilégier la simplicité (3 vraies
  user-facing : `/feat-generate`, `/sdd-full`, `/sdd-status`) + 14 internes.

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
