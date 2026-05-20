# Proposal — From-Plan Strict + Cache Discipline (v6.2)

> Système pro de matérialisation rapide en mode From-Plan : Sonnet 4.6 sur chemin chaud, validation de complétude du plan, observabilité, garde-fous reproductibilité.
> Statut : design draft. À valider avant implémentation.
> Auteur : SDD_Pro v6.1.1 audit + analyse Levier 1+3.
> Cible : v6.2 release.

---

## 1. Vision & objectifs

### 1.1 Pourquoi

Aujourd'hui, en mode From-Plan (`/dev-run` après `/dev-plan`), `dev-backend` / `dev-frontend` re-tournent en Opus 4.7 alors que **le raisonnement est déjà fait** dans le `.back.md` / `.front.md`. Il ne reste qu'à matérialiser des fichiers à partir d'un plan structuré — tâche de templating contrôlée.

**Constat mesurable** :
- Opus 4.7 latence dev-* From-Plan : 30-90s par US
- Si le plan est complet et validé, la valeur ajoutée Opus vs Sonnet pour la matérialisation est marginale (< 5% qualité observée empiriquement sur templating contraint)

### 1.2 Objectifs chiffrés

| Métrique | Avant (v6.1) | Cible (v6.2) | Gain |
|---|---|---|---|
| Latence `dev-backend` From-Plan / US | 45s médiane | 15s médiane | ×3 |
| Coût tokens `dev-backend` From-Plan / US | ~25 KT Opus | ~25 KT Sonnet (= 5× moins cher tarif) | -80% $ |
| Cache hit rate prompt (5min TTL) | non mesuré | ≥ 70% | nouveau |
| Plan staleness silencieuse | non détectée | 0 (validate_plan.py) | +robustesse |
| Idempotence cross-machine | OK | OK (préservée) | invariant |

### 1.3 Non-objectifs

- **PAS** de changement du mode Inline (plan-then-code dans la même invocation) — reste Opus 4.7.
- **PAS** de mémoire cross-session — reste file-based (cf. discussion claude-mem).
- **PAS** de modification du contrat fichier (`preserves:`/`adds:`).
- **PAS** d'API directe au `cache_control` Anthropic — Claude Code gère le cache pour nous.

---

## 2. Architecture cible

### 2.1 Vue d'ensemble

```
                ┌─────────────────────────────────────────┐
                │     /dev-plan {n}  (inchangé, Opus)     │
                │   Raisonnement complet → plans MD       │
                └────────────────┬────────────────────────┘
                                 │
                                 ▼
                ┌────────────────────────────────────────┐
                │   validate_plan.py  (NOUVEAU)          │
                │   - Complétude (preserves/adds, layer) │
                │   - Cohérence (fichiers ↔ AC coverage) │
                │   - Hash US → plan (anti-staleness)    │
                │   - Capabilities triggers détectées    │
                └────────────────┬───────────────────────┘
                                 │
                                 ▼ (exit 0 = ready)
                ┌────────────────────────────────────────┐
                │   /dev-run {n} (modifié, gate STEP 6.0)│
                │   PlanCacheStrict: true                │
                └────────────────┬───────────────────────┘
                                 │
                                 ▼
          ┌──────────────────────────────────────────┐
          │  dev-backend [From-Plan-Strict]           │
          │  - Modèle : Sonnet 4.6 (configurable)     │
          │  - Lecture : plan + US uniquement         │
          │  - Skip : re-Read stack §1.3 (déjà digé.) │
          │  - Output : code direct, build_loop       │
          └──────────────────────────────────────────┘
```

### 2.2 Trois modes coexistants (préservation backward compat)

| Mode | Trigger | Modèle | Lectures | Quand utilisé |
|---|---|---|---|---|
| **Inline** | Plan absent | Opus 4.7 | US + HTML + stack §1.3 + CLAUDE.md + schema | `/dev-backend 1-1` direct |
| **From-Plan classique** (v6.1 existant) | Plan présent, `PlanCacheStrict: false` | Opus 4.7 | Plan + US + tout le contexte (par sécurité) | défaut backward-compat |
| **From-Plan Strict** (NOUVEAU v6.2) | Plan présent + validé, `PlanCacheStrict: true` | Sonnet 4.6 | Plan + US uniquement | chemin chaud post-`/dev-plan` |

### 2.3 Invariants préservés

- ✅ Source-first : code = cible, jamais source. Plans MD restent SSOT.
- ✅ Stateless agents : re-run produit même output (le plan est déterministe input).
- ✅ Reproductibilité cross-machine : tout est dans le plan, pas dans une mémoire opaque.
- ✅ Idempotence : strict mode = same plan + same US → same code.
- ✅ Ownership : `dev-backend` reste seul écrivain `src/{BackendName}/`.
- ✅ Anti-derive : si plan incomplet → STOP via validate_plan, pas de "fallback créatif".

---

## 3. Composants — détail technique

### 3.1 Format `*.{back|front}.md` enrichi (rétro-compatible)

**Aujourd'hui** (v6.1) :
```yaml
---
us: 1-2-Login
family: backend
generated-at: 2026-05-10T14:32:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot
---

# Plan technique backend — 1-2-Login

## Files
- path: src/main/kotlin/auth/AuthService.kt
  operation: create
  layer: Service
  covers_acs: [AC-1, AC-2]
...
```

**Ajouts v6.2** (front-matter étendu, sections optionnelles) :
```yaml
---
us: 1-2-Login
family: backend
generated-at: 2026-05-10T14:32:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot

# NOUVEAUX champs
plan-schema-version: 2
us-hash: sha256:a1b2c3...   # hash du fichier US au moment de la planification
stack-snapshot:
  layers-mapping: src/main/kotlin/{layer}/  # digest §1.3 stack
  build-cmd: ./gradlew build
  test-cmd: ./gradlew test
capabilities-triggered: [auth-azure-ad]  # détectées au plan-time
claude-md-hash: sha256:d4e5f6...  # hash CLAUDE.md projet au moment du plan
strict-ready: true   # mis à true par validate_plan.py si tout est OK
---
```

**Nouvelle section optionnelle** `## Inline Digest` :
```markdown
## Inline Digest
### Stack §1.3 mapping (kotlin-spring-boot)
- Service → src/main/kotlin/{app}/service/
- Controller → src/main/kotlin/{app}/controller/
- DTO → src/main/kotlin/{app}/dto/
- Entity → src/main/kotlin/{app}/entity/

### CLAUDE.md backend (extrait pertinent)
- AppNamespace : com.acme.cms
- Entities scaffoldées : User, Role, Session
- BREAKING CHANGES : (none)

### Schema.json (entités touchées)
- User { id, email, passwordHash, ... }
- Session { id, userId, expiresAt, ... }
```

**Pourquoi** : en strict mode, `dev-backend` n'a plus besoin de re-Read stack-backend `.md` (15-30 KB) ni `CLAUDE.md` ni `schema.json` — tout le pertinent est déjà digéré dans le plan. Économie ~20-50 KB de contexte par invocation.

### 3.2 Script `validate_plan.py`

**Localisation** : `.claude/python/sdd_scripts/validate_plan.py`

**Invocateurs** :
- `/dev-plan {n}` STEP 5 (post-génération) — validation auto
- `/dev-run {n}` STEP 6.0 (pre-exécution strict) — gate cache
- `/sdd-status` (diagnostic plan-readiness)

**Algorithme** :
```
1. Args : --plan-path <path> [--us-path <path>] [--strict]
2. Parse YAML frontmatter
3. Validations structurelles :
   - plan-schema-version >= 2
   - us, family, stack-backend|frontend présents
   - section ## Files non vide
   - chaque entrée a operation (create|augment), layer, covers_acs
   - augment → preserves: et adds: présents
4. Validations strictes (si --strict) :
   - us-hash matche le hash actuel de l'US
   - claude-md-hash matche le hash actuel de CLAUDE.md
   - section ## Inline Digest présente et non vide
   - ## ACs Coverage Summary cohérente avec ACs de l'US
   - capabilities-triggered toutes présentes dans .libs.json §onDemand
5. Output :
   - exit 0 : plan strict-ready (write strict-ready: true au plan)
   - exit 1 : plan valide mais pas strict-ready (manque digest)
   - exit 2 : plan invalide / corrompu / stale (US a changé)
6. Optionnel : --json output structuré
```

**Tests** : `tests/test_validate_plan.py` couvre :
- Plan valide v1 (legacy) → exit 1
- Plan valide v2 ready → exit 0
- Plan v2 stale (us-hash mismatch) → exit 2
- Plan corrompu YAML → exit 2
- Plan v2 sans Inline Digest → exit 1

**LOC estimée** : ~250 lignes Python stdlib pur.

### 3.3 Modification `agents/dev-backend.md`

**Nouveau STEP 0.7** (juste après détection mode au 1.ter) :
```
Si FROM_PLAN_PATH != null ET PlanCacheStrict == true :
  - Bash : validate_plan.py --plan-path $FROM_PLAN_PATH --us-path workspace/output/us/{n}-{m}-*.md --strict
  - Si exit 0 → STRICT_MODE = true, MODEL_HINT = sonnet-4-6
  - Si exit 1 → STRICT_MODE = false (fallback v6.1 From-Plan classique, Opus)
  - Si exit 2 → STOP + ERROR [PLAN_STALE]
```

**Modification STEP 4 (charger contexte)** :
```
Si STRICT_MODE == true :
  - Read uniquement : plan (FROM_PLAN_PATH) + US (workspace/output/us/{n}-{m}-*.md)
  - SKIP : stack §1.3 (déjà digéré dans plan), CLAUDE.md (hash matché), schema.json (digest dans plan)
  - Budget contexte attendu : ≤ 10 KB
Sinon :
  - Comportement v6.1 inchangé
```

**Modification STEP 6+ (génération code)** :
- Inchangé : même contrat `preserves:`/`adds:`, même build_loop, même cleanup BREAKING CHANGES
- Le mode strict n'affecte que la **lecture** + le **modèle**, pas l'écriture

**Note d'implémentation** : le choix du modèle (`MODEL_HINT`) n'est pas pris par l'agent lui-même mais par `/dev-run` qui spawn le sub-agent. Cf. §3.5.

### 3.4 Modification `agents/dev-frontend.md`

Symétrique à dev-backend, avec spécificité supplémentaire :
- **Fidelity check post-build** reste actif (`validate_fidelity.py`)
- Le digest CLAUDE.md frontend doit inclure le mapping UI DS (RadzenButton, shadcn/Button, etc.)
- HTML mockup reste lu (texte direct, source vérité visuelle non-déléguable)

Réutilisation patterns dev-shared.md §7 (Plan Construction).

### 3.5 Modification `commands/dev-run.md`

**Nouveau STEP 6.0.bis** (entre détection plans et exécution dev-*) :
```
Si PlanCacheStrict == true :
  Pour chaque US à matérialiser :
    - Bash : validate_plan.py --plan-path $BACK_PLAN --us-path $US --strict
    - Bash : validate_plan.py --plan-path $FRONT_PLAN --us-path $US --strict
    - Si exit 0 sur les 2 → MARK_STRICT[$US] = true
    - Sinon → MARK_STRICT[$US] = false (fallback Opus inline ou classic from-plan)
  
  Log dans state.jsonl : { event: "plan_cache_evaluation", us, strict, reason }
```

**Modification STEP 6.a (dev-backend ×U)** :
```
Pour chaque US :
  Si MARK_STRICT[$US] = true :
    - Spawn sub-agent dev-backend avec model: sonnet-4-6
  Sinon :
    - Spawn sub-agent dev-backend avec model: opus-4-7 (défaut)
```

Note : ceci suppose que le mécanisme Task spawn d'un sub-agent supporte un override modèle. Si pas supporté nativement par Claude Code → variante : ENV var lue par l'agent dans STEP 0 pour adapter son comportement (toujours Sonnet ne dépend pas vraiment du model invoqué côté Task — c'est plus une heuristique de prompt).

**Realistic note** : on ne peut pas forcer le modèle d'un sub-agent depuis le caller. Le sub-agent hérite du modèle de l'agent définition. **Donc :** la stratégie "Sonnet sur From-Plan strict" exige soit :
- (a) un agent séparé `dev-backend-strict.md` configuré Sonnet 4.6
- (b) ou un mécanisme Claude Code de model override (non-existant à ce jour à ma connaissance)

→ Option **(a) recommandée** : créer `dev-backend-strict.md` et `dev-frontend-strict.md` qui sont **des forks minces** de l'agent principal, model: sonnet-4-6, comportement strict imposé.

### 3.6 Nouveau Project Config

```yaml
## Project Config
PlanCacheStrict: false          # défaut false v6.2 (opt-in)
PlanCacheModel: sonnet-4-6      # modèle utilisé en strict (informatif)
PlanStalenessCheck: true        # active hash US/CLAUDE.md
PlanStrictFallback: classic     # classic | inline | fail
                                #   classic = v6.1 From-Plan Opus
                                #   inline  = re-planifier inline (Opus)
                                #   fail    = STOP + ERROR
```

### 3.7 Observabilité dans `state.jsonl`

Nouveaux event types :
```json
{ "event": "plan_validate", "us": "1-2", "exit_code": 0, "strict_ready": true, "duration_ms": 142 }
{ "event": "plan_cache_evaluation", "us": "1-2", "strict": true, "reason": "ok" }
{ "event": "dev_backend_strict_start", "us": "1-2", "model": "sonnet-4-6" }
{ "event": "dev_backend_strict_end", "us": "1-2", "duration_ms": 14500, "tokens_input": 4200, "tokens_output": 2100 }
{ "event": "plan_cache_hit_rate", "feat": 1, "us_strict": 3, "us_classic": 1, "rate": 0.75 }
```

Dashboard affichera un widget "Plan Cache" avec hit rate cross-FEAT.

---

## 4. Workflow utilisateur (avant/après)

### 4.1 Pipeline complet v6.1 actuel

```bash
$ /sdd-full 1
# 5-15 min (Opus partout sauf dashboard)
```

### 4.2 Pipeline complet v6.2 avec PlanCacheStrict

```yaml
# Édition workspace/input/stack/stack.md
## Project Config
PlanCacheStrict: true
```

```bash
$ /sdd-full 1 --plan
# Phase 1-3 : /us-generate, /feat-validate (inchangé)
# Phase 3.5 : /dev-plan (Opus, ~30-60s par US) — INVESTISSEMENT
# Phase 3.5.bis : validate_plan.py (déterministe, ~150ms)
# Phase 4 : /dev-run
#   - back: dev-backend-strict (Sonnet, ~15s par US) — RETOUR
#   - api-gate (inchangé)
#   - front: dev-frontend-strict (Sonnet, ~15s par US) — RETOUR
# Phase 5 : QA + dashboard
# Total : 3-8 min (×2 plus rapide sur FEAT ≥ 3 US)
```

### 4.3 Re-run idempotent

```bash
$ /sdd-full 1     # second run, plans existent
# Phase 3.5 : skip /dev-plan (plans valides + non-stale)
# Phase 4 : strict path immédiat
# Total : 2-4 min
```

---

## 5. Migration & backward compatibility

### 5.1 Stratégie

- `PlanCacheStrict: false` par défaut → **aucun projet existant ne change de comportement**
- Format plan v1 reste supporté → `validate_plan.py` exit 1 (= utilise classic From-Plan Opus)
- Pas de migration forcée des projets existants

### 5.2 Adoption recommandée

Phase A — Test isolé :
1. Sur 1 FEAT de référence (combo Kotlin+React validé)
2. Setter `PlanCacheStrict: true`
3. Lancer `/sdd-full 1 --plan`
4. Comparer durée + tokens + qualité output avec run précédent
5. Si OK → adopter sur le projet entier

Phase B — Promotion défaut (v6.3 ou v7.0) :
- Si benchmark concluant sur 5+ projets pendant 2-3 mois
- Promouvoir `PlanCacheStrict: true` en défaut
- Documenter dans MIGRATION.md

### 5.3 Documentation à produire

- `CHANGELOG.md` v6.2 : section "From-Plan Strict + Cache"
- `MIGRATION.md` v6.1 → v6.2 : flag adoption
- `docs/conventions.md` §11.bis (nouveau) : PlanCacheStrict explained
- `agents/dev-backend-strict.md` + `agents/dev-frontend-strict.md` : nouveaux agents
- `rules/dev-shared.md` §8 (nouveau) : pattern strict mode

---

## 6. Tests & validation

### 6.1 Tests Python

| Test | Cible | Cas |
|---|---|---|
| `test_validate_plan.py` | `validate_plan.py` | 8 cas : v1 legacy, v2 ready, stale, corrompu, sans digest, AC coverage incomplète, capability orpheline, JSON output |

### 6.2 Tests d'intégration (smoke)

- Lancer `/sdd-full 1` sur FEAT de référence avec `PlanCacheStrict: false` → output A
- Lancer `/sdd-full 1` sur même FEAT avec `PlanCacheStrict: true` → output B
- **Assertions** :
  - Build vert dans les deux cas
  - API Gate GREEN dans les deux cas
  - Coverage A ≈ Coverage B (± 5%)
  - Fichiers générés A ≡ Fichiers générés B (structure, contrats `preserves`/`adds`)
  - Durée B < Durée A × 0.6 (×1.67 minimum)

### 6.3 Qualité output (manuel sur 3 combos)

Combo 1 — Kotlin + React :
- Vérifier 5 fichiers backend + 5 frontend générés strict
- Comparer ligne par ligne avec output Opus pour détection régression qualité
- Critère : différences uniquement syntaxiques (commentaires, ordre déclaration), pas sémantique

Combo 2 — .NET full stack
Combo 3 — Python + Vue (si validé d'ici-là)

---

## 7. Risques & mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Sonnet 4.6 génère code de qualité inférieure sur templating complexe | Moyenne | Moyen | Tests §6.2 + fallback `classic` configurable + opt-in défaut |
| Plan staleness silencieuse (US modifiée post-plan) | Faible | Élevé | `validate_plan.py --strict` + us-hash check, exit 2 → STOP |
| Plan incomplet (manque digest, AC coverage gap) | Moyenne | Moyen | exit 1 → fallback classic Opus automatique, log state.jsonl |
| Bug régression dans `validate_plan.py` | Faible | Élevé | 8 tests unitaires + CI run smoke avant release |
| Mécanisme model override Claude Code non disponible | Quasi-certain | Bloquant si non géré | Option (a) §3.5 : 2 nouveaux agents `dev-*-strict.md` |
| Sub-agents strict mode + parallélisme race condition | Faible | Moyen | Hérite des locks file-ownership.md existants, pas de partage état |
| Tech Lead oublie `PlanCacheStrict` et perd les gains | Élevée | Faible (perte gain, pas casse) | Doc + dashboard widget visible + warning si `/dev-plan` tourné mais `PlanCacheStrict: false` |
| Plan format v2 cassant projets antérieurs | Faible | Élevé | Backward compat v1 garanti, schema-version field |

---

## 8. Phasing & deliverables

### Sprint 1 — Foundation (3 jours)
- ✅ Brouillon `validate_plan.py` + 8 tests unitaires
- ✅ Spec format plan v2 (frontmatter étendu + ## Inline Digest)
- ✅ Mise à jour `templates/` si template plan existe
- ✅ Doc inline du script

### Sprint 2 — Agent forks (3 jours)
- ✅ `agents/dev-backend-strict.md` (fork minimaliste, Sonnet 4.6, mode lecture restreint)
- ✅ `agents/dev-frontend-strict.md` (idem + fidelity check)
- ✅ Mise à jour `loader.yml` (reads/writes des nouveaux agents)
- ✅ Mise à jour `rules/dev-shared.md` §8 (pattern strict)

### Sprint 3 — Orchestration (2 jours)
- ✅ Modif `commands/dev-run.md` STEP 6.0.bis + 6.a routing
- ✅ Modif `commands/dev-plan.md` STEP 5 (validate_plan auto)
- ✅ `sdd_scripts/sdd_state.py` events nouveaux
- ✅ `agents/dashboard.md` widget Plan Cache hit rate

### Sprint 4 — Tests & benchmark (3 jours)
- ✅ Smoke tests cross-combo
- ✅ Mesures latence + tokens sur 3 FEATs référence
- ✅ Vérification qualité output (diff manuel)
- ✅ Ajustement seuils si nécessaire

### Sprint 5 — Documentation & release (1 jour)
- ✅ `CHANGELOG.md` v6.2
- ✅ `MIGRATION.md` v6.1 → v6.2
- ✅ Update `CLAUDE.md` projet (mention PlanCacheStrict)
- ✅ Update `docs/conventions.md` §11.bis
- ✅ Update `docs/architecture.md` (modèles Claude split)

**Total estimé** : 12 jours dev + benchmark, livrable v6.2 release candidate.

---

## 9. Décisions ouvertes (à valider avant Sprint 1)

### D1 — Stratégie modèle

**Option A (proposée)** : Sonnet 4.6 sur From-Plan strict via 2 nouveaux agents `dev-*-strict.md` (forks minces).
- Pro : gain latence ×3, gain coût ×5
- Con : 2 fichiers agents supplémentaires à maintenir

**Option B** : Garder Opus 4.7 partout, capitaliser uniquement sur lecture réduite (digest plan) + cache prompt.
- Pro : pas de fork agent, robustesse Opus préservée
- Con : gain latence réduit à ~30-40% (vs ×3)

**Option C** : Haiku 4.5 sur strict (extrême low-cost).
- Pro : gain coût ~×15
- Con : risque qualité élevé sur code, jamais testé pour templating contraint

### D2 — Comportement défaut

**Option A (proposée)** : `PlanCacheStrict: false` par défaut, opt-in projet par projet.
- Pro : aucune régression sur projets existants
- Con : adoption lente

**Option B** : `PlanCacheStrict: true` par défaut en v6.2.
- Pro : tous les projets bénéficient immédiatement
- Con : surprises sur projets pas re-testés

**Option C** : Auto-détection (= true si plans existent et validés, false sinon).
- Pro : zéro friction
- Con : moins prévisible pour Tech Lead

### D3 — Fallback strict

**Option A (proposée)** : `PlanStrictFallback: classic` (= v6.1 From-Plan Opus).
- Pro : continuité fluide, jamais bloquant
- Con : Tech Lead peut ne pas remarquer la dégradation de chemin

**Option B** : `PlanStrictFallback: inline` (re-planifier inline avec Opus).
- Pro : qualité max sur plan stale
- Con : coût élevé, latence

**Option C** : `PlanStrictFallback: fail` (STOP + ERROR).
- Pro : oblige Tech Lead à régénérer le plan (cohérence forte)
- Con : friction, risque blocage

---

## 10. Critères de succès release

Pour passer v6.2 RC → v6.2 stable :

- ✅ 100% tests unitaires `validate_plan.py` passent
- ✅ Smoke test 3 combos référence : output strict ≡ output classic (structure)
- ✅ Latence dev-* strict ≤ Latence dev-* classic × 0.5
- ✅ Coverage strict ≥ Coverage classic - 5%
- ✅ Zéro régression sur projets antérieurs (`PlanCacheStrict: false`)
- ✅ Dashboard plan cache hit rate ≥ 70% sur run de référence
- ✅ Documentation complète (5 fichiers mis à jour)
- ✅ MIGRATION.md path d'adoption documenté

---

*Fin de la proposition. À valider via 3 questions D1/D2/D3 avant démarrage Sprint 1.*
