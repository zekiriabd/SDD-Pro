# Error Classification — Legacy classes (v6.x heritage, réactivées CI v7.2.0)

> **Rôle de ce fichier** (audit mineur #8 v7.0.0-alpha 2026-06-05 — clarification) :
>
> - **SSoT** (lecture par scripts d'ingest CI) pour les préfixes `[A11Y_*]`
>   et `[PERF_*]` — taxonomie exhaustive + mapping sévérité OWASP/WCAG.
> - **Archive** (lecture humaine) de l'historique v6.3-v6.10 où ces préfixes
>   étaient émis par des agents LLM (`accessibility-auditor`, `performance-auditor`).
>
> Ces deux rôles **cohabitent sans contradiction** : le schéma de mapping
> conservé en archive **est aussi** la SSoT consommée par les ingests CI v7.2.0.
> Si un ingest CI futur a besoin d'un nouveau préfixe, l'ajouter ici (pas dans
> `error-classification.md` qui couvre seulement les classes émises par les
> agents/scripts en vie).

> Annexe extraite de `error-classification.md` lors de l'audit
> v7.0.0-alpha (2026-05-20).
>
> **MAJ v7.2.0 (R7 — réactivation Option B)** : ces classes sont
> désormais émises par les **scripts d'ingest CI** déterministes
> `sdd_scripts/ingest_axe.py` (axe-core → qa_a11y) et
> `sdd_scripts/ingest_lighthouse.py` (Lighthouse → qa_performance) —
> pas par un agent LLM. Le verdict 🟢/🟡/🔴 est calculé par les
> scripts contre le seuil `--threshold` (défaut `serious`).
>
> Les classes ne sont **plus émises par un agent SDD_Pro** depuis le
> retrait v7.0.0 de `accessibility-auditor` / `performance-auditor`
> (`governance-major-auditors-trim`). L'ingest CI est strictement
> additif (scripts + workflow GitHub Actions), sans coût LLM.
>
> Voir `docs/CHANGELOG.md` (entrée v7.0.0-alpha) pour le périmètre actuel
> et `templates/ci-quality.github-actions.yml.template` pour le pipeline
> CI cible auto-généré par `arch` quand `CiTemplatesGeneration: true`.

---

## 1. A11Y (accessibility WCAG 2.2 — depuis v6.3.0, retiré v7.0.0)

Historique (v6.3.0-v6.10) : émis par `accessibility-auditor` (Haiku 4.5).
Chaque classe portait une **sévérité** ordinale
`critical > serious > moderate > minor` qui pilotait le verdict 🟢/🟡/🔴
contre le seuil `A11yFailOn` du Project Config.

| Préfixe | WCAG | Sévérité | Phase d'émission (legacy) |
|---|---|---|---|
| `[A11Y_MISSING_ALT]` | 1.1.1 | critical | accessibility-auditor STEP 3 |
| `[A11Y_INPUT_NO_LABEL]` | 1.3.1 | critical | accessibility-auditor STEP 3 |
| `[A11Y_BUTTON_NO_LABEL]` | 2.4.6 | serious | accessibility-auditor STEP 3 |
| `[A11Y_TABINDEX_POSITIVE]` | 2.4.3 | serious | accessibility-auditor STEP 3 |
| `[A11Y_HEADING_SKIP]` | 1.3.1 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_LANG_MISSING]` | 3.1.1 | serious | accessibility-auditor STEP 3 |
| `[A11Y_FORM_NO_SUBMIT]` | 3.3.2 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_ROLE_INCOMPLETE]` | 4.1.2 | serious | accessibility-auditor STEP 3 |
| `[A11Y_TARGET_TOO_SMALL]` | 2.5.5 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_STATUS_NO_LIVE]` | 4.1.3 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_SCAN_TOO_LARGE]` | — | (infra) | accessibility-auditor STEP 2 (> 500 fichiers) |

**Remplacement v7.0.0+** : `axe-core` intégré au CI du projet généré
(`.github/workflows/quality.yml` auto-généré par `arch` si
`CiTemplatesGeneration: true` — défaut). La sortie JSON d'axe-core
expose des violations avec `impact: minor|moderate|serious|critical` ;
un éventuel pont d'ingest mapperait 1:1 via le tableau ci-dessus.

**Verdict global (legacy)** : `🔴 RED` si ∃ issue de sévérité
`≥ A11yFailOn`, sinon `🟡 WARN` si issues présentes (< seuil), sinon
`🟢 GREEN`.

**Remplacement v7.0.0+** : `axe-core` intégré au CI du projet généré
(`.github/workflows/quality.yml` auto-généré par `arch` si
`CiTemplatesGeneration: true` — défaut). La sortie JSON d'axe-core
expose des violations avec `impact: minor|moderate|serious|critical` ;
un éventuel pont d'ingest mapperait 1:1 via le tableau ci-dessus
(décision out-of-scope du framework SDD_Pro — à arbitrer par le
projet consommateur).

---

## 2. Performance (Core Web Vitals + SLO — depuis v6.4.0, retiré v7.0.0)

Historique (v6.4.0-v6.10) : émis par `performance-auditor` (Sonnet 4.6).
Aucune classe n'était hard-blocking par défaut — la perf est
contextuelle. Le seuil était piloté par `PerfFailOn` du Project Config.
**Exception** : `[PERF_AC_VIOLATION]` était hard-blocking quand une AC
d'US mentionnait explicitement une métrique perf.

| Préfixe | Métrique | Seuil défaut | Sévérité | Phase d'émission (legacy) |
|---|---|---|---|---|
| `[PERF_LCP_TOO_HIGH]` | LCP frontend | > 2500 ms (WCAG AA) | critical | perf-auditor §5.1 |
| `[PERF_CLS_TOO_HIGH]` | CLS | > 0.1 | serious | perf-auditor §5.1 |
| `[PERF_FID_TOO_HIGH]` | FID (legacy) | > 100 ms | serious | perf-auditor §5.1 |
| `[PERF_INP_TOO_HIGH]` | INP (Chrome 125+) | > 200 ms | serious | perf-auditor §5.1 |
| `[PERF_TTFB_TOO_HIGH]` | TTFB backend | > 600 ms | serious | perf-auditor §5.2 |
| `[PERF_API_P95_HIGH]` | API p95 latency | > 300 ms | serious | perf-auditor §5.2 |
| `[PERF_API_P99_HIGH]` | API p99 latency | > 1000 ms | moderate | perf-auditor §5.2 |
| `[PERF_DB_QUERY_P95_HIGH]` | DB query p95 | > 100 ms | moderate | perf-auditor §5.2 |
| `[PERF_BUNDLE_TOO_LARGE]` | JS bundle size | > 250 KB gzipped | serious | perf-auditor §4.1 |
| `[PERF_BUNDLE_LARGE]` | JS bundle size | 500-1500 KB raw | moderate | perf-auditor §4.1 |
| `[PERF_RENDER_BLOCKING]` | scripts sync dans `<head>` | — | serious | perf-auditor §4.2 |
| `[PERF_N_PLUS_ONE_RISK]` | N+1 query (cross-fichier) | — | serious | perf-auditor §4.3 |
| `[PERF_MEMORY_LEAK_SUBSCRIPTION]` | subscriptions sans cleanup | — | moderate | perf-auditor §4.4 |
| `[PERF_LONG_SYNC_LOOP]` | loop sync > 1000 itérations main thread | — | moderate | perf-auditor §4.5 |
| `[PERF_DB_QUERY_NO_INDEX]` | query sur champ non indexé | — | moderate | perf-auditor §4.6 |
| `[PERF_AC_VIOLATION]` | AC d'US explicite non respectée | — | critical (hard-blocking) | perf-auditor §6.3 |

**Coordination historique avec code-reviewer** : `[PERF_N_PLUS_ONE_RISK]`
étendait `[REVIEW_ANTI_PATTERN_N_PLUS_ONE]` (cf.
`error-classification.md §1.10`) avec heuristique cross-fichier (lazy
load dans loop). Si `code-review.json` flag déjà N+1 sur même
file+line, perf-auditor dé-dupliquait.

**Remplacement v7.0.0+** : Lighthouse CI (frontend Core Web Vitals) +
wrk/k6 (backend SLO API) au CI du projet généré. Un éventuel pont
d'ingest mapperait les sorties Lighthouse JSON
(`categories.performance.auditRefs[]`) vers les classes ci-dessus
(décision out-of-scope du framework SDD_Pro — à arbitrer par le
projet consommateur).

---

## 3. Migration path — pont d'ingest CI (réalisé v7.2.0)

Pont câblé v7.2.0 (`R7 Option B`) — scripts déterministes, pas d'agent LLM :

| Source CI | Script ingest | Table cible | Classes émises |
|---|---|---|---|
| `@axe-core/cli` JSON (`axe-report.json`) | `sdd_scripts/ingest_axe.py` | `qa_a11y` | 10 canoniques `[A11Y_MISSING_ALT]`, `[A11Y_INPUT_NO_LABEL]`, … + fallback `[A11Y_RULE_<RULE_ID>]` |
| Lighthouse CI (`.lighthouseci/lhr-*.json`) | `sdd_scripts/ingest_lighthouse.py` | `qa_performance` | 7 actives `[PERF_LCP_TOO_HIGH]`, `[PERF_CLS_TOO_HIGH]`, `[PERF_INP_TOO_HIGH]`, `[PERF_TTFB_TOO_HIGH]`, `[PERF_BUNDLE_TOO_LARGE]`, `[PERF_BUNDLE_LARGE]`, `[PERF_RENDER_BLOCKING]` |
| wrk/k6 SLO API (futur) | (à câbler v7.3+) | `qa_performance` | `[PERF_API_P95_HIGH]`, `[PERF_DB_QUERY_*]`, … |

Garanties tenues :
1. Classes importées depuis ce fichier (source de vérité — pas de
   redéfinition)
2. Mapping sévérité préservé (compatible Project Config legacy)
3. Tables `qa_a11y` / `qa_performance` (schéma v6.3.0/6.4.0 inchangé)
4. Sections §1.9 et §1.12 du fichier principal mises à jour pour
   noter la réactivation côté ingest (texte court — la taxonomie
   exhaustive reste ici)
5. `record_auditor_run(auditor='a11y'|'perf')` posé en marqueur pour
   que `/sdd-review --ensure-scans` détecte la présence côté CI

---

## 4. Décision conservation

L'audit v7.0.0-alpha §1.3 (anti-pattern « code mort déclaratif »)
recommandait de retirer ces sections du fichier principal. Compromis
retenu :

- **Schéma préservé** dans ce fichier annexe (~110 lignes)
- **Fichier principal allégé** (retrait sections §1.9 et §1.12,
  remplacées par stubs 5 lignes pointant ici)
- **Référence en taxonomie** §3.1 d'`error-classification.md` conservée
  comme `(héritage)` pour informer le caller qu'il rencontrera peut-être
  ces préfixes dans des bases console.db legacy

Ce design préserve la valeur d'archive sans polluer la lecture
opérationnelle quotidienne.

---

## 5. Pointers

- `@.claude/rules/error-classification.md §1.9, §1.12` — fichier
  principal (stubs MAJ v7.2.0 pour pointer vers ingest CI)
- ADR `governance-major-auditors-trim` (2026-05-19) — retrait initial
  des agents (cf. `docs/adrs/ADR-20260519T120000-governance-major-auditors-trim.md`)
- `sdd_scripts/ingest_axe.py` + `sdd_scripts/ingest_lighthouse.py`
  — ingest CI déterministe (v7.2.0)
- `templates/ci-quality.github-actions.yml.template` — workflow
  GitHub Actions auto-généré par arch quand `CiTemplatesGeneration: true`
- Tables `qa_a11y` et `qa_performance` dans `console.db` (schéma
  v6.3.0/6.4.0 inchangé)

---

## 6. Références "fantômes" — supprimées 2026-06-06

> Le méta-audit historique sur les annotations d'agents retirés v7.0.0
> a été retiré de cette rule de production. Consultable via `git log`.

