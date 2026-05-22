# Runbook — Bench FEAT M Kotlin (exécution concrète)

> **Objectif** : produire **UNE phrase chiffrée** publiable dans
> `roi-baseline.md` :
> *« Sur 3 runs FEAT M Kotlin (3 US, workflow métier) : coût médian
> $X.XX, wall-clock médian YY min, AC verified ZZ%, variance ±N%. »*
>
> **Effort total** : 3-4 jours-homme. Suit le plan recommandé
> « 1 cellule mesurée > 6 cellules bâclées ».
>
> **Combo cible** : C2 — `kotlin-spring-boot × react × shadcn ×
> kotlin-junit + node-vitest × azure-ad × postgres × ddd`.

> ## ⚠️ Périmètre de mesure (à lire AVANT d'exécuter)
>
> Ce bench mesure la **génération de code depuis spec figée + mockups HTML
> statiques**. Il NE mesure PAS l'adéquation UI/UX réelle, les bugs
> post-déploiement, la perf en charge, ni le cycle de vie produit complet.
>
> Toute valeur reportée dans `roi-baseline.md` §3 FEAT M doit être suffixée
> du label `[scope: code-gen from fixed spec]`. Les ratios humain/framework
> ne doivent **jamais** être extrapolés en "gain produit total" (sinon
> risque R2 — claim ROI surévalué — resurgit à la première démo critique).
>
> Détail complet : `@.claude/docs/roi-baseline.md` callout "Périmètre de
> mesure (anti-R2)".

---

## J1 matin (2 h) — Préparation FEAT et mockups

### Étape 1.1 — Copier le template FEAT M

```powershell
# Choisir un numéro de FEAT libre dans workspace/input/feats/
# Exemple : la FEAT N+1 (si dernière FEAT existante = 4, alors N=5)
$N = 5  # adapter
cp .claude/templates/bench-feats/feat-m.template.md `
   workspace/input/feats/$N-BenchM.md
```

### Étape 1.2 — Copier le mockup HTML existant + créer les 2 manquants

```powershell
# US-1 : liste — mockup fourni, juste à copier
cp .claude/templates/bench-feats/mockups/feat-m-1-orders-list.html `
   workspace/input/ui/$N-1-Orders-List.html

# US-2 : formulaire création (à créer manuellement, ~20 min)
# Inspiration : un seul écran avec
#   - Select "Client"
#   - Tableau "Lignes" avec colonnes Produit, Quantité, Prix unitaire, Total ligne
#   - Bouton "+ Ajouter une ligne"
#   - Footer avec Total commande (calculé) + boutons "Annuler" / "Enregistrer"
# Style cohérent avec feat-m-1-orders-list.html (badges, table, btn-primary)

# US-3 : détail commande (à créer manuellement, ~15 min)
# Inspiration :
#   - Header "Commande #1042" + badge statut
#   - Section "Client" + "Lignes" (read-only)
#   - Boutons d'action conditionnels :
#     - Draft → bouton vert "Confirmer la commande"
#     - Confirmed → bouton rouge "Annuler" (ouvre modal avec textarea reason)
#     - Cancelled → pas de bouton, juste affichage reason
```

### Étape 1.3 — Préparer DB de test

```powershell
# DB postgres locale isolée du workspace actif (sinon contamine CMSPrint)
# Suggestion : container Docker dédié
docker run -d --name bench-postgres `
  -p 5433:5432 `
  -e POSTGRES_USER=bench `
  -e POSTGRES_PASSWORD=bench `
  -e POSTGRES_DB=bench_orders `
  postgres:16

# Créer tables seed customers + products
# (DDL minimal, à exécuter via psql ou DBeaver)
```

```sql
CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO customers (name) VALUES ('ACME Corp'), ('Globex Inc'), ('Initech SARL');

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  sku VARCHAR(50) UNIQUE NOT NULL,
  name VARCHAR(200) NOT NULL,
  current_price NUMERIC(10,2) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);
INSERT INTO products (sku, name, current_price) VALUES
  ('SKU-001', 'Câble HDMI 2m', 12.50),
  ('SKU-002', 'Souris ergonomique', 45.00),
  ('SKU-003', 'Clavier mécanique', 120.00),
  ('SKU-004', 'Webcam HD', 89.90),
  ('SKU-005', 'Hub USB-C 4 ports', 38.00);
```

### Étape 1.4 — Configurer stack.md pour le bench

Créer un **fork temporaire** du `stack.md` actuel (le workspace CMSPrint
ne doit pas être modifié) :

```powershell
# Sauvegarde
cp workspace/input/stack/stack.md workspace/input/stack/stack.md.cmsprint-backup

# Éditer workspace/input/stack/stack.md :
#   BackendName: BenchOrdersBack
#   FrontendName: BenchOrdersFront
#   BackendLocalPort: 44329  (différent du CMSPrint)
#   FrontendLocalPort: 5186
#   ## Active Database :
#     DatabaseType: postgres
#     DB_HOST: 127.0.0.1
#     DB_PORT: 5433  ← container dédié
#     DB_NAME: bench_orders
#     DB_USER: bench
#     DB_PASSWORD: bench
#   ## Active Architecture Pattern : ddd
#   ## Active Tech Specs : kotlin-spring-boot + react
#   ## Active UI Specs : shadcn
#   ## Active QA Specs : kotlin-junit + node-vitest + code-quality
#   ## Active Auth Specs : azure-ad (mêmes vars que CMSPrint OK)
```

---

## J1 après-midi (4-6 h) — Baseline humaine

**Objectif** : chrono toi-même en codant la FEAT M à la main (sans
SDD_Pro, sans Claude Code, sans IA). C'est le comparateur indispensable.

### Étape 2.1 — Setup chrono

```
Heure début : ____________
```

### Étape 2.2 — Implémenter (sans aide IA)

Périmètre minimal pour avoir un comparable honnête :

- [ ] Spring Boot 4.0 + Kotlin 2.3 + JPA + Postgres driver (gradle init + dépendances)
- [ ] 3 entités JPA (`Order`, `OrderLine`, `Product`) + repositories
- [ ] DTOs entrants/sortants pour les 6 endpoints (FD-4 à FD-9)
- [ ] Service de validation cross-field (BR-2 total = SUM lines)
- [ ] Workflow statut (BR-1 transitions)
- [ ] 6 endpoints REST testables (Postman ou curl)
- [ ] React 19 + Vite : 3 pages (liste, détail, formulaire) avec shadcn
- [ ] Tests unit kotlin-junit pour le service (BR-2 cross-field au minimum)
- [ ] Coverage ≥ 80 % du service

**Ne fais pas** : auth Azure AD (utilise un mock JWT), CI, déploiement,
docs poussées, refactors esthétiques.

### Étape 2.3 — Mesurer

```
Heure fin     : ____________
Wall-clock    : ___ h ___ min
```

Comptes-rendus à noter dans `workspace/output/.sys/.bench/snapshots/baseline-humaine.md` :

- Lignes de code écrites (`cloc workspace/output/src/BenchOrders*/` ou équivalent)
- Tests écrits + coverage atteint
- Bugs rencontrés pendant codage (qui auraient été des `[BUILD_CORRECTIBLE]` côté framework)
- AC couvertes (sur les 10 AC totales)

> **Coût humain estimé** : wall-clock × $150/h (tarif dev senior).

---

## J2 (3-4 h cumulées) — 3 runs framework

**IMPORTANT** : entre chaque run, **reset complet** :

```powershell
# Drop tables order_lines, orders dans postgres bench
# (products + customers restent — seed inchangé)
docker exec bench-postgres psql -U bench -d bench_orders -c `
  "DROP TABLE IF EXISTS order_lines CASCADE; DROP TABLE IF EXISTS orders CASCADE;"

# Reset workspace output
rm -rf workspace/output/src/BenchOrders*
rm -rf workspace/output/.sys/.state/run-*.json
# (Conserver workspace/output/.sys/.bench/ et adrs/ — pas du run précédent)

# Réinitialiser console.db pour mesure propre (OPTIONNEL — si déjà bench déjà fait, garde le delta)
# python .claude/python/sdd_scripts/init_console_db.py --reset
```

### Étape 3.1 — Run 1

```powershell
# Snapshot avant
python .claude/python/sdd_scripts/bench_run.py --snapshot-before `
  --bench-id bench-m-kotlin-run-1

# Chrono manuel — note l'heure
$start = Get-Date
Write-Host "Start: $start"

# Lancer le pipeline (interactif — répondre aux 3-6 questions /feat-generate
# uniquement si la FEAT n'existe pas encore ; sinon /sdd-full direct)
# Si tu as copié le template à l'étape 1.1, la FEAT existe déjà :
/sdd-full 5

# À la fin (succès ou échec) — chrono fin
$end = Get-Date
$wallclock = ($end - $start).TotalMinutes
Write-Host "Wallclock: $wallclock min"

# Snapshot après + génération rapport
python .claude/python/sdd_scripts/bench_run.py --snapshot-after `
  --bench-id bench-m-kotlin-run-1 `
  --wallclock-min $wallclock `
  --feat-n 5 `
  --output .claude/docs/benchmarks/runs/bench-m-kotlin-run-1.json
```

### Étape 3.2 — Run 2 et Run 3

**Identique** à 3.1, avec `--bench-id bench-m-kotlin-run-2` puis `-run-3`.

> **Variations attendues** : LLM stochastique, le code généré et les
> tests vont varier. C'est précisément ce qu'on veut mesurer (σ).
> Ne tweake **rien** entre les 3 runs (FEAT, stack, config tous figés).

### Étape 3.3 — Verdict par run

Pour chaque run, noter :

| Métrique | Run 1 | Run 2 | Run 3 |
|---|:---:|:---:|:---:|
| Wall-clock (min) | | | |
| `total_cost_usd` (`bench_run.py` summary) | | | |
| `total_invocations` | | | |
| `auditor_artifacts_present` (sur 7) | | | |
| Verdict global pipeline (🟢/🟡/🔴) | | | |
| Build loops déclenchés | | | |
| Crash mid-run ? | | | |
| `[FRONTEND_BACKEND_CONTRACT_GAP]` ? | | | |

### Étape 3.4 — AC verified ratio

Pour chaque run, ouvrir
`workspace/output/.sys/.validation/5-spec-compliance.json` :

```powershell
$specs = Get-Content `
  workspace/output/.sys/.validation/5-spec-compliance.json | ConvertFrom-Json
$verified = ($specs.acs | Where-Object { $_.status -eq 'verified' }).Count
$total = $specs.acs.Count
"AC verified: $verified / $total = $([math]::Round($verified*100/$total, 1))%"
```

---

## J3 (3-4 h) — Review humaine indépendante + publication

### Étape 4.1 — Review bugs post-run (1 h)

Idéalement par un collègue qui n'a pas vu le code généré. À défaut, toi
avec une grille structurée.

Grille (par run, sur le code généré dans `workspace/output/src/BenchOrdersBack/`) :

- [ ] Validation BR-2 (total mismatch) effectivement codée côté serveur ?
- [ ] Transitions de statut BR-1 effectivement appliquées (pas juste DTO) ?
- [ ] Snapshot prix BR-4 effectivement copié vers `order_lines.unit_price` (pas une référence) ?
- [ ] Quantité 0 rejetée avant persistence (pas après) ?
- [ ] Pagination respecte `page_size` max 100 ?
- [ ] Frontend appelle bien les routes telles que déclarées backend (pas d'invention) ?

Compte les bugs par sévérité **critical** (logique métier cassée) et
**serious** (validation incomplète) sur chacun des 3 runs.

### Étape 4.2 — Calculer la médiane + variance

```python
# .claude/docs/benchmarks/aggregate.py (1-shot, à exécuter)
import json, statistics
from pathlib import Path

runs = []
for i in (1, 2, 3):
    p = Path(f".claude/docs/benchmarks/runs/bench-m-kotlin-run-{i}.json")
    runs.append(json.loads(p.read_text(encoding="utf-8")))

wallclocks = [r["summary"]["wallclock_min"] for r in runs]
costs = [r["summary"]["total_cost_usd"] for r in runs]
invocations = [r["summary"]["total_invocations"] for r in runs]

def stats(label, values):
    m = statistics.median(values)
    s = statistics.stdev(values) if len(values) > 1 else 0
    var_pct = (s / m * 100) if m else 0
    print(f"{label}: median={m:.2f}, stdev={s:.2f}, variance={var_pct:.1f}%")

stats("wallclock_min", wallclocks)
stats("cost_usd", costs)
stats("invocations", invocations)
```

### Étape 4.3 — Écrire le rapport agrégé

Créer `.claude/docs/benchmarks/feat-m-kotlin.md` selon le template
défini dans `README.md §4`. Inclure :

- Méta (date, machine, modèles, FEAT hash)
- Tableau 3 runs + médiane + σ
- Verdict vs critères `roi-baseline.md §5.2`
- Section "Pain points découverts" (qualitatif, observations bench)

### Étape 4.4 — Mettre à jour `roi-baseline.md`

Remplir **uniquement** la cellule FEAT M C2 :

```markdown
## 3. FEAT M — Moyen

> **Scope mesuré** : `[code-gen from fixed spec]` — FEAT M template + 3
> mockups HTML statiques + DDL postgres seed. NE PAS extrapoler ces
> ratios en "gain produit total" (cf. callout "Périmètre de mesure
> (anti-R2)" en tête de ce fichier).

### 3.1 Baseline humaine `[code-gen from fixed spec]`
| Métrique | Valeur |
|---|---:|
| Heures-homme | X.X h |
| Coût @ 150 $/h | $XXX |
| Coverage lines | XX % |
| AC verified (sur 10) | X |
| Quality issues (serious+) | X |
| Bugs review (1 h indep) | N (critical: M) |

### 3.2 Framework (3 runs, combo C2 Kotlin/React) `[code-gen from fixed spec]`
| Run | Wall-clock | Tokens input | Tokens output | Tokens cache | Coût $ |
|---|---:|---:|---:|---:|---:|
| Run 1 | XX min | XXX | XXX | XXX | $XX |
| Run 2 | XX min | XXX | XXX | XXX | $XX |
| Run 3 | XX min | XXX | XXX | XXX | $XX |
| **Médiane** | XX min | XXX | XXX | XXX | $XX |
| **Variance** | X.X % | X.X % | X.X % | X.X % | X.X % |

### 3.3 Verdict comparatif `[code-gen from fixed spec]`
| Métrique | Humain | Framework (médiane) | Ratio | Verdict |
|---|---:|---:|---:|---|
| Wall-clock | X.X h | X.X h | XX× | 🟢/🟡/🔴 |
| Coût $ | $XXX | $XX | XX× | 🟢/🟡/🔴 |
| Coverage lines | XX % | XX % | +/- N pts | 🟢/🟡/🔴 |
| AC verified | X/10 | X/10 | +/- N | 🟢/🟡/🔴 |
| Quality issues | X | X | XX× | 🟢/🟡/🔴 |
| Bugs review | X | X | +/- N | 🟢/🟡/🔴 |

**Verdict global FEAT M Kotlin** `[scope: code-gen from fixed spec]` : 🟢 / 🟡 / 🔴

> Rappel publication : phrase autorisée *« sur la génération de code conforme
> à une spec figée, framework ≤ humain / N »*. Phrase **interdite** : ~~« le
> framework remplace un dev senior pour livrer un produit en prod »~~.

> Cellules FEAT S et FEAT L : non mesurées (décision audit 2026-05-20 —
> 1 cellule mesurée > 6 cellules bâclées). À benchmarker en v7.1+.
> Cellules C1 dotnet : non mesurées dans ce bench. Extrapolation
> conservatrice : multiplier coût C2 par 0.9-1.1 (Sonnet/Opus pricing
> identique, stack équivalent). À confirmer empiriquement en v7.1.
```

### Étape 4.5 — Tag `v7.0.0-rc1`

```powershell
git add -A
git commit -m "feat(v7.0.0-rc1): bench M Kotlin mesuré, ROI publié"
git tag v7.0.0-rc1 -m "Release candidate 1 — FEAT M Kotlin ROI mesuré (3 runs)"
# Pas de push sur main (freeze)
```

---

## Cleanup post-bench

```powershell
# Restaurer stack.md original (CMSPrint)
mv workspace/input/stack/stack.md.cmsprint-backup workspace/input/stack/stack.md

# Stopper container postgres bench (optionnel)
docker stop bench-postgres
docker rm bench-postgres

# Conserver :
# - workspace/output/.sys/.bench/snapshots/*.json (forensique)
# - .claude/docs/benchmarks/runs/*.json (rapports)
# - .claude/docs/benchmarks/feat-m-kotlin.md (synthèse)
# - workspace/output/src/BenchOrders*/ (code généré pour review post-tag)
```

---

## Critères d'abandon

Si à J2 (runs framework) :

- ≥ 2/3 runs **crash mid-run** → 🔴 framework non assez stable pour bench M. STOP.
  Issue à investiguer avant rc1.
- Variance σ wall-clock ou coût ≥ 30 % → 🟡 framework non assez déterministe.
  Lancer un 4ème run pour confirmer ; si toujours ≥ 30 %, document the
  cause-root (logs) et reporte le tag.
- `[COST_CAP_EXCEEDED]` sur ≥ 1 run → ajuster `MaxCostPerRun` puis re-run.

Si l'un de ces seuils est franchi : **ne tag pas rc1**. Le framework
n'est pas prêt pour la communication "ROI mesuré".

---

## Résultat attendu publication finale

Une **release note rc1** d'une page contenant (formulation calibrée
anti-R2) :

> *« SDD_Pro v7.0.0-rc1 — FEAT-Driven Development pour Claude Code,
> validé sur combo C2 Kotlin Spring Boot + React + shadcn pour la
> génération de code depuis spec figée.
>
> ROI mesuré sur FEAT M `[scope: code-gen from fixed spec]`
> (workflow métier, 3 US, 10 AC, mockups HTML + DDL postgres seed) :
> - Wall-clock médian : YY min (vs X h dev senior codant la même spec
>   sans IA → ratio NN×)
> - Coût médian : $X.XX (vs $YYY humain → ratio MM×)
> - AC verified : ZZ % du premier coup (sans correction Tech Lead)
> - Variance 3 runs : ±N % (σ wall-clock)
>
> **Hors scope mesuré** : adéquation UI/UX réelle, bugs post-déploiement,
> perf en charge, cycle de vie produit. Le bench qualifie le gain sur la
> phase code-generation isolée, qui reste load-bearing dans un cycle
> produit mais ne remplace pas un dev senior end-to-end.
>
> Stack .NET disponible (combo C1) sans bench mesuré — extrapolation
> conservatrice à confirmer en v7.1. Autres stacks (Vue/Angular/Blazor/
> FastAPI/Express) marqués `experimental`, non validés bout-en-bout. Voir
> `docs/validated-combos.md`. »*

**C'est ça l'argument produit honnête.** Tout le reste de l'audit attend
cette phrase calibrée.

---

## Pointers

- `@.claude/templates/bench-feats/feat-m.template.md` — FEAT canonique
- `@.claude/templates/bench-feats/mockups/feat-m-1-orders-list.html` — mockup US-1
- `@.claude/python/sdd_scripts/bench_run.py` — script d'agrégation
- `@.claude/docs/benchmarks/README.md` — protocole général
- `@.claude/docs/roi-baseline.md` — destination publication
- `@.claude/docs/poc-roi-methodology.md` — méthodologie source
