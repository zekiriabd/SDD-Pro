# SDD_Pro — Méthodologie PoC ROI (humain vs framework)

> **Méthodologie reproductible** pour mesurer objectivement le ROI temps/coût/qualité
> du framework SDD_Pro vs une implémentation humaine traditionnelle. Cf.
> `ADR-20260519T193000-governance-roi-poc` pour la décision et la cible
> v7.0.0 (PoC obligatoire avant release).

---

## 1. Objectif

Démontrer (ou réfuter) sur **chiffres mesurés** les promesses du framework :
- Réduction tokens/FEAT (claims v7 : -45 KB auditors-trim, -110 KB prompts-trim, -65 % cumul)
- Wall-clock par FEAT vs équipe humaine
- Qualité output (coverage, AC verified, bugs en review)
- Reproductibilité cross-machine

**Anti-objectif** : confirmer ce qu'on espère. La méthodologie est conçue pour
biaiser **contre** le framework (FEATs de difficulté croissante incluant cas où
le humain doit gagner), pas pour le valoriser.

---

## 2. FEATs de référence figées

3 FEATs canoniques, hash gelé dans le repo sous
`workspace/input/feats/roi-poc/`. Chaque FEAT inclut :
- Spec complète (sections Functional Needs, Business Rules, Acceptance Criteria, Functional Deliverables, Actors)
- Mockup HTML statique (si applicable)
- `stack.md` figé associé (~/.sdd/profiles/roi-poc.yml)

### 2.1 FEAT S — Trivial (cible : framework devrait gagner faiblement)

**Cas** : Page de connexion local-only (1 endpoint + 1 page React).
- 1 endpoint POST `/api/login` (validation password local hash bcrypt)
- 1 composant React `<LoginForm>` avec validation Zod
- 0 base de données externe (in-memory)
- 0 design system spécifique
- 0 capability on-demand

**Estimation humaine baseline** : 2-4 h dev senior.
**Estimation framework** : 1 cycle `/sdd-full`, ~10-20 min wall-clock LLM.

### 2.2 FEAT M — Moyen (cible : framework devrait gagner clairement)

**Cas** : CRUD entité métier avec auth Azure AD.
- 4 endpoints REST CRUD (`GET list paginated`, `GET by id`, `POST`, `PUT`, `DELETE`)
- 1 page liste + 1 page détail + 1 page formulaire (shadcn + TanStack Query)
- Validation FluentValidation (back) + Zod (front)
- Auth Azure AD avec scope check
- Tests xunit (back) + Vitest (front) avec coverage ≥ 80 %
- 3 US (CRUD list, CRUD edit, CRUD delete)

**Estimation humaine baseline** : 16-32 h dev senior.
**Estimation framework** : 1 cycle `/sdd-full`, ~40-90 min wall-clock LLM.

### 2.3 FEAT L — Complexe (cible : test stress, framework potentiellement en difficulté)

**Cas** : Workflow métier multi-étapes avec règles complexes.
- 8-12 endpoints avec règles business cross-entités
- State machine (5-7 états avec transitions conditionnelles)
- Export Excel + génération PDF
- Notifications (email + in-app)
- Permissions granulaires (3 rôles, 8 actions)
- 5-6 US dépendantes (graphe DAG via `## Dependencies`)
- Mock externe (gateway paiement Stripe-like)

**Estimation humaine baseline** : 60-120 h équipe (back+front).
**Estimation framework** : 1 cycle `/sdd-full`, ~3-6 h wall-clock LLM.

> Note honnête : à ce niveau de complexité, **on s'attend** à ce que le framework
> nécessite ≥ 1 cycle correctif manuel (Tech Lead corrige un AC, relance). Mesurer
> aussi ces cycles correctifs dans le bench.

---

## 3. Baseline humaine (méthodologie)

### 3.1 Profil senior

- 1 dev senior expérimenté (.NET + React/TS), 5+ ans d'expérience
- **Pas de** SDD_Pro, **pas de** Copilot/Cursor — éditeur nu (VS Code stdlib)
- Lecture autorisée : doc Microsoft, MDN, Stack Overflow, npm/NuGet sites officiels
- Stack imposé : identique au `stack.md` figé du PoC

### 3.2 Mesures captées

| Métrique | Méthode |
|---|---|
| **Heures-homme** | Horodatage début/fin par US + journal des pauses (`workspace/input/feats/roi-poc/baseline-human-log.md`) |
| **Coût $** | heures × **150 $/h** (taux marché senior fullstack Europe Ouest 2026) |
| **Coverage** | Run `dotnet test --collect:"XPlat Code Coverage"` + `vitest --coverage` |
| **AC verified** | Run `spec-compliance-reviewer` sur le code humain (oui : on utilise SDD_Pro pour **mesurer** la baseline humaine — c'est asymétrique mais nécessaire) |
| **Bugs review** | 1 reviewer indépendant pendant 2 h grep + manual trace cross-fichier. Catégoriser : critical/serious/moderate/minor. |
| **Lignes de code** | `cloc` sur les répertoires src/ générés |

### 3.3 Anti-cherry-pick

- Le dev senior **ne connaît pas** SDD_Pro (sinon biaisé pour optimiser le PoC).
- Le dev senior **ne sait pas** que c'est un PoC (jusqu'à la fin) — présenté comme « cahier des charges client ».
- Le dev senior fait **toute la FEAT** avant que le framework ne tourne (pour ne pas voir les solutions framework).

---

## 4. Run framework (méthodologie)

### 4.1 Setup

```powershell
# Setup propre, repo cloné fresh
git checkout v6.10.4-LTS  # ou v7.0.0 selon cible PoC
$env:SDD_TOKEN_USAGE_MODE = "record"

# FEAT de référence figée
cp workspace/input/feats/roi-poc/feat-S.md workspace/input/feats/1-Login.md
# (idem pour M et L)
```

### 4.2 Pipeline

```powershell
# Pipeline complet, mesures activées
/sdd-full 1 --manual-gates  # capture wall-clock par phase
```

Wall-clock par phase remonte automatiquement dans `console.db` table `run_phases`.

### 4.3 Mesures captées

| Métrique | Source |
|---|---|
| **Wall-clock total** | `console.db` `runs.ended_at - runs.started_at` |
| **Wall-clock par phase** | `console.db` `run_phases.{started_at,ended_at}` |
| **Tokens input/output/cache** | `console.db` `token_usage` (un row par invocation LLM) |
| **Coût $ Anthropic** | tokens × pricing (`Sonnet 4.6: $3/M input, $15/M output, $0.3/M cache read`) |
| **Coverage** | `qa_coverage` table (déjà writter par `parse_coverage.py`) |
| **AC verified** | `qa_spec_compliance` table |
| **Quality scan issues** | `qa_quality` table (count par sévérité) |
| **Auditor verdicts** | `qa_a11y` + `qa_code_review` + `qa_security` + `qa_performance` |
| **Cycles correctifs manuels** | log Tech Lead dans `workspace/output/.sys/.roi-poc/feat-{S\|M\|L}-corrections.md` |

### 4.4 Bench script (livré v7.0.0)

Disponible : `.claude/python/sdd_scripts/bench_run.py` qui orchestre :

```bash
python bench_run.py --feat 1 --label "framework-v7.0.0" \
    --baseline-human-hours 12.5 --baseline-human-cost-per-hour 150
```

Lit `console.db` + applique pricing + produit `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`
table comparative auto-générée.

---

## 5. Métriques publiées (table comparative)

Format normé pour `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md` :

```markdown
## FEAT M — Comparaison humain vs framework v7.0.0

| Métrique | Humain | Framework | Ratio | Verdict |
|---|---:|---:|---:|---|
| Wall-clock total | 24.5 h | 1.2 h | ×20 | 🟢 framework |
| Coût $ | 3 675 $ | 8.40 $ | ×437 moins cher | 🟢 framework |
| Coverage lines | 78 % | 84 % | +6 pts | 🟢 framework |
| AC verified | 18/20 (90 %) | 19/20 (95 %) | +5 pts | 🟢 framework |
| Quality issues (serious+) | 7 | 12 | +5 issues | 🔴 humain |
| Bugs review (1h indépendant) | 3 (1 critical) | 5 (0 critical) | +2 mineurs | 🟡 mitigé |
| Lignes code | 1 240 | 1 480 | +19 % | 🟡 framework verbeux |

**Verdict global FEAT M** : 🟢 framework dominant (4/7 métriques), 🟡 2 nuancées, 🔴 1 régression (qualité scan).
```

---

## 6. Reproductibilité

### 6.1 Fixé dans le repo

- `workspace/input/feats/roi-poc/feat-{S|M|L}.md` — specs figées, hash SHA-256 dans `roi-poc/MANIFEST.json`
- `workspace/input/stack/roi-poc-stack.md` — stack figé
- `workspace/input/feats/roi-poc/baseline-human-log.md` — log baseline humaine
- `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md` — résultats publiés (régénéré par `bench_run.py`)

### 6.2 Reproductible par tout Tech Lead

```bash
git checkout v7.0.0
cp workspace/input/feats/roi-poc/feat-M.md workspace/input/feats/1-M.md
/sdd-full 1 --manual-gates
python bench_run.py --feat 1 --label "framework-v7.0.0" \
    --baseline-human-hours 24.5 --baseline-human-cost-per-hour 150
```

Doit produire la table §5 à ±5 % (variance LLM acceptée).

### 6.3 Re-mesure semestrielle

À chaque release MAJOR (v8.0, v9.0…), re-run les 3 FEATs → vérifier
absence de régression. Publier dans `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md` avec un
historique par version.

---

## 7. Honnêteté intellectuelle (anti-biais)

### 7.1 Cas où le framework doit perdre

- **FEAT S très trivial** (1 endpoint, 0 dépendance) : un senior tape ça en 30 min, le framework prend 15-20 min mais consomme 5-10 $ tokens. ROI négatif sur tasks simples.
- **Refactoring** : SDD_Pro ne fait pas de refactoring (génère depuis spec). Un humain refactor 10× plus vite.
- **Debug runtime** : framework ne sait pas debug post-prod. Humain seul peut.

Inclure explicitement ces cas dans le rapport `BENCH-GLOBAL-REPORT.md` section
« Cas où SDD_Pro N'EST PAS le bon outil ». Ne pas les cacher.

### 7.2 Variance LLM

Lancer chaque FEAT framework **3 fois** (3 runs indépendants à `temperature=0`).
Mesurer écart-type tokens/wall-clock. Si > 15 % de variance sur 3 runs identiques
→ flag de reproductibilité dans le rapport.

### 7.3 Auditeur indépendant pour la review humaine

La review « bugs trouvés en 1 h » sur le code humain doit être faite par un
auteur **différent** du framework et **différent** du dev senior baseline.
Sinon biais de confirmation.

### 7.4 Périmètre de mesure (anti-R2) — ajouté 2026-05-22

Toute mesure produite par cette méthodologie a un **scope étroit volontaire** :
génération de code depuis une **spec figée** + mockups HTML statiques.

**Hors scope explicite** :
- Adéquation UI/UX réelle sous usage utilisateur (mockups = stubs HTML)
- Bugs surfaçant post-déploiement / canary deploy
- Perf en charge, résilience runtime, observabilité
- Edge cases métier non spec, variance "produit" sous clients réels
- Coût cycle de vie complet (déploiement, monitoring, evolutions, debt)

**Implication** : les ratios humain/framework publiés dans `BENCH-GLOBAL-REPORT.md`
doivent **toujours** être suffixés `[scope: code-gen from fixed spec]`. Toute
extrapolation en "gain produit total" est interdite — c'est précisément le
piège que le risque R2 (claim ROI surévalué) cherche à éviter.

Détail complet et phrases autorisées/interdites : callout "Périmètre de
mesure (anti-R2)" en tête de `@.claude/workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`.

---

## 8. Critères de release v7.0.0

Pour que v7.0.0 puisse être taguée (post-2026-06-19), le PoC doit avoir :

| Critère | Cible | Si non atteint |
|---|---|---|
| FEAT M wall-clock | framework ≤ humain / 5 | Bloque release, investiguer |
| FEAT M coût $ | framework ≤ humain / 50 | Bloque release |
| FEAT M coverage | framework ≥ humain - 5 pts | Bloque release |
| FEAT M AC verified | framework ≥ 90 % | Bloque release |
| FEAT M quality serious+ | framework ≤ humain + 50 % | WARN, ne bloque pas |
| Variance 3 runs | ≤ 15 % écart-type | WARN, investiguer flake |

> Ces seuils sont volontairement **conservateurs**. Si les ADRs v7 disent
> « -65 % tokens », le PoC doit le démontrer (au moins -40 % en pratique).

---

## 9. Pointers

- `@.claude/docs/glossary.md §10` — verdict / severity canoniques
- `@.claude/python/sdd_scripts/report_token_usage.py` — agrégation tokens existante
- `@.claude/python/sdd_scripts/parse_coverage.py` — agrégation coverage
- `@.claude/python/sdd_scripts/query_console_db.py` — read queries SQL
- `@.claude/docs/CHANGELOG.md` lignes 489, 530, 600, 850 — promesses ROI non mesurées historiquement
- `workspace/output/.sys/.context/adrs/ADR-20260519T193000-governance-roi-poc.md` — décision + plan
- `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md` — résultats publiés (à créer post-exécution PoC)
