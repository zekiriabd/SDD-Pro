# SDD_Pro — Proposition de réduction de périmètre v7.0.0 GA (Option A)

> Résout la critique audit v7.0.0-alpha §4.2 :
> *« 2/120 combos validés là où la doc annonce 16 stacks supportés. Le framework est commercialisable sur 2 stacks, vendu pour 16. »*
>
> **Décision recommandée** : adopter l'**Option A** (réduire officiellement le périmètre)
> avant le tag GA v7.0.0. L'Option B (extension par PoC matrix) est planifiée
> moyen terme (v7.1+). L'option C (quarantaine élargie) est rejetée
> (perte d'investissement v6.x).
>
> **Statut** : proposition. À valider par décision tracée via ADR
> `governance-scope-reduction-v7-ga` avant exécution.

---

## 1. Diagnostic — désalignement promesse / preuve

| Promesse marketing (CLAUDE.md §7) | Preuve empirique (audit) |
|---|---|
| « 16 stacks actifs + 1 pattern archi » | 2 combos validés bout-en-bout (C1, C2) |
| « 4 backend, 4 frontend, 3 UI DS, 2 auth, 7 QA, 1 archi » | 0 PoC sur python-fastapi, node-express, vue, angular, blazor-webassembly, vuetify, radzen-blazor, auth-local |
| « Combos validés bout-en-bout : 2 sur ~120 combinaisons possibles » | Reconnu explicitement dans CLAUDE.md §7 lui-même — la doc se contredit |
| « Cohérence multi-stack » | 6/8 stacks QA sans entête `Validation:` (cf. audit §3.2) |

**Conséquence runtime** : utilisateur tiers qui choisit `vue + vuetify`
peut voir son pipeline casser de manière non triviale (scaffolding,
mapping HTML→DS, capabilities on-demand). Rupture de confiance.

---

## 2. Périmètre cible v7.0.0 GA

### 2.1 Stacks « Production-ready » (🟢)

**2 combos exclusivement** — tous les composants ont un PoC `/sdd-full`
bout-en-bout réussi :

| Combo | Backend | Frontend | UI | QA | Auth | DB | Archi |
|:---:|---|---|---|---|---|---|---|
| **C1** | `dotnet-minimalapi` | `react` | `shadcn` | `dotnet-xunit` | `azure-ad` | PostgreSQL | `mvc` |
| **C2** | `kotlin-spring-boot` | `react` | `shadcn` | `kotlin-junit` + `node-vitest` | `azure-ad` | PostgreSQL | `ddd` (workspace) ou `mvc` |

### 2.2 Stacks « Experimental — usage à vos risques » (🟡)

Présents dans `.claude/stacks/{cat}/`, **chargeables runtime** mais
sans garantie de fonctionnement bout-en-bout :

| Catégorie | Stacks experimental |
|---|---|
| Backend | `python-fastapi`, `node-express` |
| Frontend | `blazor-webassembly`, `vue`, `angular` |
| UI DS | `vuetify`, `radzen-blazor` |
| QA | `python-pytest`, `angular-jasmine`, `blazor-bunit`, `mutation-testing`, `playwright` |
| Auth | `auth-local` |
| Archi | `ddd` |

### 2.3 Stacks « Quarantine — non chargés » (🔴 dans `_drafts/`)

Inchangé par cette proposition (cf. `.claude/stacks/_drafts/README.md`) :

- 6 fullstack, 2 mobiles, 1 archi (`microservice`)

---

## 3. Changements opérationnels à exécuter

### 3.1 Marketing / Documentation utilisateur

| # | Action | Fichier | Effort |
|:---:|---|---|---|
| 1 | Renommer le tagline CLAUDE.md ligne 1 : « FEAT-Driven Development pour Claude Code » → « FEAT-Driven Development — .NET & Kotlin / React (production-ready) » | `CLAUDE.md §0` | 5 min |
| 2 | Ajouter §0.5 « Scope GA » avant §1 : encart explicite « 2 combos production-ready, autres = experimental » | `CLAUDE.md` | 15 min |
| 3 | Réécrire CLAUDE.md §7 avec 3 colonnes (🟢 production / 🟡 experimental / 🔴 quarantine) au lieu de 2 (reference / experimental) | `CLAUDE.md §7` | 30 min |
| 4 | Ajouter alerte runtime dans `preflight.py` : si combo détecté ≠ C1/C2, émettre WARN explicite « combo experimental — aucun PoC formel ; voir docs/validated-combos.md » | `preflight.py` (1 fonction `_warn_if_experimental_combo()`) | 1 h |
| 5 | Mettre à jour README.md projet (si existe) | `README.md` | 30 min |

### 3.2 Entête `Validation:` (gap audit §3.2)

Ajouter l'entête manquante aux 6 stacks QA + 1 stack UI :

```markdown
META:
  type: qa-spec
  id: <stack-id>
  Validation: 🟡 experimental    # ← AJOUTER
```

| Fichier | Cible Validation |
|---|---|
| `stacks/qa/dotnet-xunit.md` | 🟢 reference (combo C1) |
| `stacks/qa/kotlin-junit.md` | 🟢 reference (combo C2) |
| `stacks/qa/node-vitest.md` | 🟢 reference (combo C2) |
| `stacks/qa/blazor-bunit.md` | 🟡 experimental |
| `stacks/qa/angular-jasmine.md` | 🟡 experimental |
| `stacks/qa/python-pytest.md` | 🟡 experimental |
| `stacks/ui/radzen-blazor.md` | 🟡 experimental (format header non-standard à corriger) |

Effort : **15 min** (7 edits triviaux).

### 3.3 Garde-fou CI

Créer hook PreToolUse Agent dans `.claude/settings.json` :

```json
{
  "PreToolUse.Agent": [
    {
      "name": "validate_stack_combo_warn",
      "command": "python .claude/python/sdd_scripts/validate_stack_combo.py --quiet",
      "on_exit_code": {
        "0": "continue",
        "1": "continue_with_warning",
        "2": "block_unless_env:SDD_ALLOW_UNTESTED_COMBO=1",
        "3": "block",
        "4": "block"
      }
    }
  ]
}
```

Effort : **30 min** (édition + test 1 cas par exit code).

### 3.4 Communication externe

| # | Action | Effort |
|:---:|---|---|
| 1 | Annonce v7.0.0 GA explicite : « 2 combos production-ready, 8 experimental » | 1 h |
| 2 | FAQ « Pourquoi mon stack X est experimental ? » avec lien `docs/validated-combos.md` | 30 min |
| 3 | Roadmap publique : combos C3-C5 prioritaires post-GA | 30 min |

---

## 4. Trajectoire post-GA — Option B (extension progressive)

Plan PoC matrix CI v7.1+ (cf. `docs/validated-combos.md §3`) :

| Combo | Effort | Cible release |
|:---:|---|---|
| C3 — stack microsoft pur (`dotnet-minimalapi × blazor-webassembly × radzen-blazor`) | 2-3 j | v7.1.0 |
| C4 — stack JS pur (`node-express × vue × vuetify`) | 3-4 j | v7.2.0 |
| C5 — stack Python (`python-fastapi × angular`) | 4-5 j | v7.3.0 |

Chaque PoC suit `docs/poc-roi-methodology.md` + bench S/M/L + ROI publié.
Décision passage 🟡 → 🟢 par ADR `governance-validate-combo-{id}` post-PoC.

---

## 5. Critères de décision

L'Option A est retenue ssi **les 3 conditions suivantes sont vraies** :

| Condition | Validation |
|---|---|
| Aucun client externe identifié demande Vue/Angular/Blazor/microservices | 🟢 (audit mono-utilisateur confirme — `roi-baseline.md` est vide) |
| Investissement Option B (10-15 j-homme) n'est pas finançable v7.0 | 🟢 (priorité = sortir GA, pas étendre périmètre) |
| Le freeze `main` (jusqu'au 2026-06-18) reste respecté | 🟢 (changements sur `next` uniquement) |

Si 3/3 → Option A. Si une condition bascule (ex. client demande Angular),
trancher cas par cas.

---

## 6. Risques de l'Option A

| Risque | Mitigation |
|---|---|
| Perception « régression » côté community (16 → 2 stacks officiels) | Communication explicite : « experimental ≠ supprimé » ; stacks restent chargeables avec `SDD_ALLOW_UNTESTED_COMBO=1` |
| Perte d'investissement v6.x sur stacks experimental | Aucune (stacks restent dans le repo, juste leur status communiqué change) |
| Adoption ralentie sur niches Vue/Angular | Acceptable (priorité fiabilité > croissance) ; roadmap publique mitige |
| Confusion utilisateur sur la frontière 🟢 / 🟡 | Document `docs/validated-combos.md` est canonique ; script `validate_stack_combo.py` est source de vérité |

---

## 7. Anti-pattern à éviter

**Ne PAS** :
- Supprimer les stacks experimental du repo (perte de réversibilité)
- Bloquer purement les combos experimental (`exit_code=2` par défaut) — empêche les utilisateurs courageux qui sont OK avec le risque
- Communiquer « 2 stacks » sans expliquer pourquoi (perception négative)
- Tag GA avant exécution complète du protocole (`docs/benchmarks/README.md` + ROI publié)

**À FAIRE** :
- Communiquer « 2 production-ready + 8 experimental + 9 quarantine » (positionnement honnête)
- Garder `exit_code=1` (WARN, continue) pour experimental → permet expérimentation sans friction
- Publier ROI baseline en même temps que tag GA → tagline crédible
- Démarrer C3 PoC immédiatement post-GA pour montrer la trajectoire

---

## 8. Plan d'exécution (post-validation ADR)

| # | Action | Bloquant pour GA ? | Estimé |
|:---:|---|:---:|---|
| 1 | Créer ADR `governance-scope-reduction-v7-ga` (référence ce doc) | OUI | 30 min |
| 2 | Exécuter §3.1 (5 changements docs) | OUI | 2 h |
| 3 | Exécuter §3.2 (entêtes Validation manquantes) | OUI | 15 min |
| 4 | Exécuter §3.3 (hook CI validate_stack_combo) | RECOMMANDÉ | 30 min |
| 5 | Exécuter §3.4 (annonces) | NON (post-GA) | 2 h |
| 6 | Exécuter bench protocol (`docs/benchmarks/README.md`) | OUI | 5-6 j |
| 7 | Tag v7.0.0 GA | — | — |

**Total bloquant pour GA** : ~6 jours-homme (dominé par exécution bench).

---

## 9. Pointers

- `@.claude/docs/validated-combos.md` — matrice canonique combos
- `@.claude/docs/benchmarks/README.md` — protocole ROI
- `@.claude/docs/AUDIT-FRAMEWORK-v7.md` §3.2 — gap entête Validation
- `@.claude/python/sdd_scripts/validate_stack_combo.py` — validateur déterministe
- `@.claude/CLAUDE.md §7` — table stacks (à réécrire selon §3.1.3)
- ADR `governance-major-stacks-quarantine` (2026-05-19) — précédent
- ADR `governance-restore-ddd-archi-pattern` (2026-05-20) — précédent

---

*Document de proposition. Décision finale par ADR `governance-scope-reduction-v7-ga`. Toute exécution avant validation ADR est nulle.*
