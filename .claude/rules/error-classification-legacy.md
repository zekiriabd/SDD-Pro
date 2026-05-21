# Error Classification — Legacy classes (v6.x heritage, v7.0.0+ no-op)

> Annexe extraite de `error-classification.md` lors de l'audit
> v7.0.0-alpha (2026-05-20, critique Mineure : *« classes héritage
> conservées comme schéma de mapping futur — code mort déclaratif »*).
>
> Ces classes ne sont **plus émises** par aucun agent SDD_Pro après
> v6.10.5 (retraits `accessibility-auditor` et `performance-auditor` via
> `governance-major-auditors-trim`). Elles sont **préservées comme
> schéma cible** au cas où un outil d'ingest CI consommerait les sorties
> `axe-core` (frontend a11y) ou `Lighthouse CI` (Core Web Vitals).
>
> Aucun script d'ingest n'est aujourd'hui planifié dans le framework
> SDD_Pro — la décision de câbler un tel pont relève du projet
> consommateur (CI templates générés). Voir `docs/scope-reduction-v7-ga.md`
> pour le périmètre actuel.
>
> Le caller v7.0.0+ ne doit **pas s'attendre** à voir ces classes dans
> les rapports actuels. Tout traitement runtime de ces préfixes doit
> être considéré comme un no-op (warning OK, blocking non).

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

## 3. Migration path (si pont d'ingest CI est câblé un jour)

Si un projet consommateur décide de câbler un pont
axe-core/Lighthouse → console.db :

1. Importer ces classes de ce fichier-ci, **PAS** les redéfinir
2. Conserver le mapping sévérité (compatibilité Project Config)
3. Persister dans `console.db` tables `qa_a11y` / `qa_perf` (schéma
   déjà présent depuis v6.3.0/6.4.0)
4. Ne **pas** restaurer ces sections dans `error-classification.md`
   tant que les agents ne sont pas réactivés (les classes sont émises
   par scripts d'ingest CI, pas par agents Sonnet/Haiku)

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

- `@.claude/rules/error-classification.md` — fichier principal (sans
  §1.9/§1.12 depuis 2026-05-20)
- `@.claude/docs/AUDIT-FRAMEWORK-v7.md §1.3` — critique audit motivant
  la séparation
- ADR `governance-major-auditors-trim` (2026-05-19) — retrait initial
  des agents
- Tables `qa_a11y` et `qa_perf` dans `console.db` (schéma préservé pour
  ingest futur)

---

## 6. Références "fantômes" intentionnellement conservées (H4 audit 2026-05-20)

Un audit ciblé v7.0.0-alpha a relevé **28 fichiers** mentionnant les
agents retirés (`accessibility-auditor`, `performance-auditor`,
`dashboard`, `dev-backend-strict`, `dev-frontend-strict`). Vérification
sémantique : **0 référence à nettoyer**. Toutes sont l'une des classes
ci-dessous, **intentionnellement load-bearing ou historiques**.

### 6.1 Load-bearing backward-compat (NE PAS RETIRER)

| Fichier | Pourquoi conservé |
|---|---|
| `python/sdd_hooks/preflight_agent_budget.py::REJECTED_AGENTS_V7` | dict de **rejection active** — bloque les spawns d'agents retirés avec message d'erreur explicite + pointer vers le replacement (axe-core CI, Lighthouse CI, `index_adrs.py`) |
| `python/sdd_scripts/context_budget.py::ALLOWED_AGENTS` | whitelist `argparse choices=` — accepte les noms legacy pour parsing de lignes historiques de `console.db` table `context_budget` |
| `python/sdd_scripts/context_budget.py::DEFAULT_BUDGETS` | budgets pour lecture rétro de lignes legacy (mêmes raisons) |
| `python/sdd_scripts/phase_planner.py::_decide_a11y / _decide_perf / _decide_threat_model` | phase entries marquées `agent_removed: True` + `enabled: False` toujours, avec champ `replacement:` pointant vers le nouvel outil — consumers parsent le plan JSON et savent qu'il n'y a pas de spawn |

### 6.2 Annotations historiques (lecture humaine — pas de code drift)

| Fichier | Format de l'annotation |
|---|---|
| `agents/code-reviewer.md`, `agents/security-reviewer.md`, `agents/arch-reviewer.md`, `agents/spec-compliance-reviewer.md` | `~~accessibility-auditor~~ retiré v7.0.0` dans sections "Coordination" ou tableaux comparatifs |
| `CHANGELOG.md`, `MIGRATION.md`, `docs/version-notes.md` | trace historique des retraits (rétention permanente) |
| `python/sdd_admin/framework_smoke.py` | commentaire `# accessibility-auditor + performance-auditor REMOVED v7.0.0` |
| `error-classification-legacy.md` (ce fichier) | schéma `[A11Y_*]` / `[PERF_*]` figé pour ingest CI futur |

### 6.3 Heuristique pour audits futurs

Avant de signaler une référence comme "drift à corriger" :
1. Le contexte porte-t-il un marqueur explicite de retrait
   (`~~`, `agent_removed: True`, `REJECTED_AGENTS_V7`, `RETIRÉ v7.0.0`,
   "removed v7.0.0") ?
2. La référence est-elle dans un `argparse choices=` ou une whitelist
   READ-side compat ?
3. La référence est-elle dans un document historique (CHANGELOG,
   MIGRATION, version-notes, ADR) ?

Si oui à l'un des 3 → **OK, ne pas signaler**. C'est de la documentation
ou du backward-compat actif, pas du drift.

> **Décision (2026-05-20)** : retraits v7.0.0 sont sémantiquement
> propres ; aucune action H4 nécessaire. Cette section sert de garde
> contre les faux positifs d'audits futurs.
