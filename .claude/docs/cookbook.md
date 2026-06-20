# SDD_Pro — Cookbook 10 minutes

> 📚 **Vous découvrez SDD_Pro ?** L'entrée canonique est
> [`docs/README.md`](README.md) (hub orienté audience). Le présent
> `cookbook.md` est la fiche **"premier projet en 30 min"**
> (variante condensée de [`quickstart.md`](quickstart.md) qui couvre
> plus de cas brownfield + customisation).
>
> Quickstart hyper-condensé : produire un premier projet fonctionnel
> en moins de 30 minutes, sans avoir lu les 8 règles ni les 47 docs.
> Pour la doctrine complète : `@.claude/docs/architecture.md`.

---

## ⏱️ Minute 0-2 — Install

```bash
# Greenfield project, automated combo C1 (.NET + React + shadcn + Azure AD)
git clone https://github.com/<your-fork>/sdd-pro my-app && cd my-app
python bootstrap.py --combo c1
```

Réponses interactives : `AppName=MyApp`, `DatabaseType=PostgreSql`, ports
par défaut. Le script installe Python deps (`pip install -e .claude/python[dev]`)
et console web Node (~50 MB).

**CI mode** :
```bash
SDD_APP_NAME=MyApp SDD_COMBO=c1 SDD_DB_TYPE=PostgreSql \
  python bootstrap.py --auto-init
```

---

## ⏱️ Minute 2-5 — Secrets + premier FEAT

Édit `workspace/input/stack/stack.md` (gitignored) — remplir au minimum :

```yaml
DB_PASSWORD: <secret>
AZ_TENANTID: <azure-tenant>
AZ_CLIENTID: <azure-client>
```

Créer un FEAT :
```
/feat-generate Auth
```
3-6 questions (acteurs, besoins fonctionnels, AC). Fichier produit :
`workspace/input/feats/1-Auth.md`.

---

## ⏱️ Minute 5-25 — Pipeline complet

```
/sdd-full 1
```

Enchaîne automatiquement : US (8-12%) → readiness gate (12-15%) → plan (15-22%) →
arch + DB scaffold (22-32%) → backend (32-58%) → API gate (58-66%) →
frontend (66-78%) → QA + coverage (78-88%) → 4 reviewers + 1 opt-in (88-99%) → verdict 🟢/🟡/🔴 (100%).

Coût attendu : $15-30 USD pour une FEAT de 2-3 US (combo C1).

---

## ⏱️ Minute 25-30 — Vérifier + lancer

```
/sdd-status 1       # diagnostic (lecture seule)
/sdd-review 1       # audit consolidé (verdict final)
/sdd-serve          # lance backend + frontend + console
```

Ouvrir http://127.0.0.1:4000 (console web) et l'app sur le port frontend.

---

## 🆘 Si ça casse — Top 10 erreurs

| Préfixe `[CLASS]` | Sens | Fix rapide |
|---|---|---|
| `[STACK_MALFORMED]` | `stack.md` manque clé requise | Compléter `## Project Config` (CoverageMin, AppName, etc.) |
| `[BUILD_LOOP_EXHAUSTED]` | 3/3 itérations de build échoué | Inspecter `workspace/output/qa/feat-1/build.md`, fix manuel |
| `[QA_COVERAGE_GAP]` | Couverture < seuil | Ajouter tests OU baisser `CoverageMin` dans Project Config |
| `[FRONTEND_BACKEND_CONTRACT_GAP]` | Frontend appelle endpoint inexistant | Vérifier OpenAPI sync, regenerer client si codegen |
| `[STACK_LIBRARY_MISSING]` | Lib hors §2.4 du stack | Ajouter dans `.libs.json`, `sync_stack_md.py`, relancer |
| `[PLAN_STALE]` | US modifiée après génération du plan | Relancer `/dev-plan {n}` |
| `[FEAT_HASH_MISMATCH]` | FEAT modifiée après US | Relancer `/us-generate {n}` (idempotent) |
| `[API_GATE_RED]` | Tests API in-memory échouent | Voir `workspace/output/qa/feat-{n}/api-tests.md` |
| `[SEC_SECRET_HARDCODED]` | Secret en code | Déplacer vers env var / appsettings.Development.json |
| `[COST_CAP_EXCEEDED]` | Run dépasse $50 | `MaxCostPerRun: 0` dans Project Config (ou augmenter) |

Toute classe : `@.claude/rules/error-classification.md`.

---

## 🧭 Pour aller plus loin

| Besoin | Lire |
|---|---|
| Comprendre l'architecture | `@.claude/docs/architecture.md` |
| Workflow détaillé | `@.claude/docs/workflow.md` |
| Choisir un combo | `@.claude/docs/validated-combos.md` |
| Ajouter une lib | `@.claude/rules/library-and-stack.md` Partie A |
| Customiser un agent | `@.claude/agents/{nom}.md` |
| Brownfield (projet existant) | `/sdd-discover-stack` |
| POC rapide (sans QA strict) | `/sdd-poc 1` (variante minimaliste) |

---

## 🎯 Combos prêts (`bootstrap.py --combo c{n}`)

| Combo | Stack | Statut |
|---|---|:---:|
| **c1** | .NET Minimal API + React + shadcn + Azure AD | 🟢 validated |
| **c2** | Kotlin Spring Boot + React + shadcn + Azure AD | 🟢 validated |
| **c3** | Node Express + React + shadcn + auth-local | 🟢 bench-validated (2026-06-05) |
| **c4** | Python FastAPI + React + shadcn + auth-local | 🟢 bench-validated (2026-06-05) |
| **c5** | .NET Minimal API + Vue + Vuetify + Azure AD | 🟢 bench-validated (2026-06-05) |
| **custom** | Pick each component manually | — |

---

*Cookbook v7.0.0-alpha — 1 page, lu en 10 minutes, applicable en 30.*
