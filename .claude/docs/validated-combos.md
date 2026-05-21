# SDD_Pro — Validated stack combos (référence canonique)

> Document chargé **à la demande** (`Read @.claude/docs/validated-combos.md`).
> Crée pour résoudre la critique M3 (audit v7.0.0) :
> *« 16 stacks → ~120 combinaisons possibles, 2 validées bout-en-bout ;
> le risque que le pipeline casse en runtime sur un combo non-PoC est
> explicitement reconnu. Promesse multi-stacks largement théorique. »*
>
> **Objectif** : avant tout `/sdd-full {n}`, savoir en **10 secondes** si
> le combo actif est `validated`, `experimental` ou `untested` — et
> ce que cela implique.

---

## 1. Quick reference — combos validés bout-en-bout

| ID | Backend | Frontend | UI DS | QA | Auth | DB | Status | Dernière PoC |
|:---:|---|---|---|---|---|---|:---:|---|
| **C1** | `dotnet-minimalapi` | `react` | `shadcn` | `dotnet-xunit` | `azure-ad` | PostgreSQL | 🟢 validated | 2026-05-07 |
| **C2** | `kotlin-spring-boot` | `react` | `shadcn` | `kotlin-junit` + `node-vitest` | `azure-ad` | PostgreSQL | 🟢 validated | 2026-05-11 (workspace CMSPrint) |

**Garanties C1/C2** : `/sdd-full {n}` complet (FEAT → US → arch → dev → QA →
auditors) a tourné bout-en-bout sans intervention humaine non documentée
sur ≥ 1 FEAT M (3 US, back+front).

**Hors C1/C2 : aucune garantie.** Le pipeline peut échouer en runtime de
manière non triviale (scaffolding DB, mapping HTML→DS, capabilities
on-demand, conventions stack-specific).

---

## 2. Matrice de couverture — dimensions × statut

| Dimension | 🟢 Validé (combo PoC) | 🟡 Expérimental (stack OK, combo jamais testé) | 🔴 Non testé |
|---|---|---|---|
| **Backend** | `dotnet-minimalapi`, `kotlin-spring-boot` | `python-fastapi`, `node-express` | — |
| **Frontend** | `react` | `blazor-webassembly`, `vue`, `angular` | — |
| **UI DS** | `shadcn` | `vuetify`, `radzen-blazor` | — |
| **QA** | `dotnet-xunit`, `kotlin-junit`, `node-vitest`, `code-quality` | `python-pytest`, `angular-jasmine`, `blazor-bunit`, `mutation-testing`, `playwright` | — |
| **Auth** | `azure-ad` | `auth-local` | — |
| **DB** | PostgreSQL (via Kotlin + .NET) | SqlServer (via .NET stacks, doc OK) | MySql, MariaDb, Sqlite, Oracle, MongoDb |
| **Archi pattern** | `mvc` (implicite C1) | `ddd` (workspace CMSPrint, non-PoC formel) | `microservice` (en quarantaine v7) |
| **AppType** | `back-front/web` | `fullstack`, `back-front/mobile` | `mobile-{react-native,maui}` (stacks quarantine) |

> Lecture : un stack 🟡 est conforme techniquement (entête `Validation:`,
> `.libs.json` valide, tests stack-level OK) mais **n'a jamais été utilisé
> dans une PoC `/sdd-full` complète**. La conformité unitaire ≠ garantie d'intégration.

---

## 3. Combos prioritaires post-v7.0.0 GA

Plan de validation (3 PoCs additionnels pour atteindre 5 combos validés) :

| ID | Hypothèse | Backend | Frontend | UI DS | QA | Auth | DB | Effort estimé |
|:---:|---|---|---|---|---|---|---|---|
| **C3** | Stack microsoft pur | `dotnet-minimalapi` | `blazor-webassembly` | `radzen-blazor` | `dotnet-xunit` + `blazor-bunit` | `azure-ad` | SqlServer | 2-3 j |
| **C4** | Stack JS pur | `node-express` | `vue` | `vuetify` | `node-vitest` | `auth-local` | PostgreSQL | 3-4 j |
| **C5** | Stack Python | `python-fastapi` | `angular` | (custom Material 3) | `python-pytest` + `angular-jasmine` | `azure-ad` | PostgreSQL | 4-5 j |

**Méthodologie** : suivre `docs/poc-roi-methodology.md` — bench S/M/L,
mesurer wall-clock + coût + coverage, publier dans `roi-baseline.md`.

**Critères d'acceptation combo** :
- ≥ 1 FEAT M (3 US, back+front, AC traçables) bout-en-bout sans bypass
- Coverage ≥ `CoverageMin` (80 % défaut)
- Spec-compliance verdict ≠ RED
- Security-scan verdict ≠ RED
- Build vert sans intervention manuelle
- ROI publié (3 runs, variance ≤ 15 %)

---

## 4. Comment savoir si MON combo est validé

### 4.1 Méthode manuelle (10 secondes)

1. Ouvrir `workspace/input/stack/stack.md`
2. Lire les blocs `## Active *`
3. Comparer avec §1 ci-dessus :
   - **Tous** les composants (Backend + Frontend + UI + QA + Auth + DB)
     matchent C1 ou C2 → 🟢
   - **Au moins un** composant 🟡 → 🟡 expérimental
   - **Au moins un** composant 🔴 → 🔴 non testé (risque élevé)

### 4.2 Méthode automatisée (script déterministe)

```powershell
python .claude/python/sdd_scripts/validate_stack_combo.py --json
```

Exit codes :

| Exit | Status | Action recommandée |
|:---:|---|---|
| `0` | 🟢 validated | Aucune. Pipeline `/sdd-full` safe. |
| `1` | 🟡 experimental | WARN. Vérifier le PoC ROI méthodologie avant prod. Bypass auto. |
| `2` | 🔴 untested | STOP. Refuser run automatique. Bypass : `SDD_ALLOW_UNTESTED_COMBO=1` env var (audit-loggué). |
| `3` | invalid | `[STACK_COMBO_INVALID]` — combo incohérent (ex. mix back+fullstack). |

Output JSON (extrait) :
```json
{
  "signature": "kotlin-spring-boot+react+shadcn+kotlin-junit+azure-ad+postgres+ddd",
  "matched_combo": "C2",
  "status": "validated",
  "exit_code": 0,
  "components": {
    "backend": {"id": "kotlin-spring-boot", "level": "validated"},
    "frontend": {"id": "react", "level": "validated"},
    "ui": {"id": "shadcn", "level": "validated"},
    "qa": [{"id": "kotlin-junit", "level": "validated"}, {"id": "node-vitest", "level": "validated"}],
    "auth": {"id": "azure-ad", "level": "validated"},
    "db": {"type": "postgres", "level": "validated"},
    "archi": {"id": "ddd", "level": "experimental"}
  },
  "warnings": [
    "Archi pattern 'ddd' is experimental (workspace CMSPrint uses it but no formal PoC)"
  ]
}
```

### 4.3 Intégration pipeline

Le script peut être câblé dans :

- **Hook PreToolUse Agent** (`.claude/settings.json`) — bloque les invocations
  Agent si exit ≥ 2 et `SDD_ALLOW_UNTESTED_COMBO` absent.
- **STEP 0.5 de `/sdd-full`** — appel manuel par Tech Lead avant pipeline.
- **CI gate** — block les merges qui changent `stack.md` vers un combo
  non-PoC sans ADR justificatif.

> Pas câblé en hook par défaut (v7.0.0-alpha) — décision discrétionnaire
> du Tech Lead via `.claude/settings.local.json`. Sera décision GA v7.0.0
> selon retours adoption (cf. roadmap v7-v8).

---

## 5. Politique commerciale recommandée

L'audit a identifié un désalignement entre la **promesse marketing**
(16 stacks supportés) et la **vérité empirique** (2 combos validés).
Trois positionnements possibles :

### 5.1 Option A — *« SDD_Pro for .NET & Kotlin »* (recommandé v7.0.0 GA)

**Communiquer** : SDD_Pro v7.0 supporte officiellement 2 combos
(C1, C2). Tous les autres sont expérimentaux et nécessitent un PoC
préalable.

**Action immédiate** : renommer le tagline dans README + CLAUDE.md.
Marquer 🟢/🟡/🔴 explicitement dans chaque stack `.md`. Ajouter le
script §4.2 au pipeline preflight.

**Avantage** : honnêteté → confiance utilisateur. Pas de mauvaise
surprise runtime.

**Inconvénient** : positionnement plus modeste, mais défendable
empiriquement.

### 5.2 Option B — *« Multi-stack PoC matrix CI »*

**Investir** : ressources pour valider C3-C5 (effort 2-5 jours chacun
selon §3). Cible : 5 combos validés à v7.1.0.

**Avantage** : promesse multi-stack tenue.

**Inconvénient** : coût significatif (10-15 jours-homme) sans utilisateur
demandeur identifié.

### 5.3 Option C — *« Quarantaine élargie »*

**Réduire la surface** : déplacer tous les stacks 🔴 / 🟡 jamais utilisés
en `.claude/stacks/_drafts/` (déjà fait pour fullstack/mobile/DDD/microservice
en v7.0.0 — étendre à `python-fastapi`, `node-express`, `vue`, `angular`,
`blazor-webassembly`, `vuetify`, `radzen-blazor`, `auth-local`).

**Avantage** : framework v7.0.0 = 2 combos officiels, 0 ambiguïté.

**Inconvénient** : retour en arrière sur le travail v6.x sur ces stacks.

---

## 6. Risques runtime spécifiques aux combos non-validés

Pour information / mitigation préventive si vous tentez un combo 🟡/🔴 :

| Risque | Probabilité 🟡 | Probabilité 🔴 | Mitigation |
|---|:---:|:---:|---|
| Scaffolding DB échoue (introspection driver/dialect) | Moyenne | Élevée | Tester `arch --rebuild-arch` sur DB de test |
| Mapping HTML→DS partiel (composants exotiques) | Faible | Élevée | Valider mockups simples (table, form, button) d'abord |
| Capabilities on-demand non triggered (regex stack-specific) | Moyenne | Élevée | Lire `.libs.json` `onDemand[].triggers[]` avant FEAT |
| Convention naming endpoints divergente | Faible | Moyenne | Lire `stacks/backend/{id}.md §2.6` (convention URL) |
| Build loop ne converge pas (BUILD_BLOCKING) | Faible | Élevée | Réduire complexité US, splitter en plusieurs FEATs |
| Auth flow stack-specific cassé | Faible | Moyenne | PoC isolé `/feat-generate Auth` d'abord |
| QA fixtures in-memory incompatible | Moyenne | Élevée | Override `IntegrationTestMode: containers` (Docker) |
| CORS préset frontend dev port incorrect | Faible | Faible | `Cors:AllowedOrigins` explicite dans Project Config |

---

## 7. Historique combos validés

| Combo | Tag SDD_Pro | Date | Validateur | Note |
|:---:|---|---|---|---|
| C1 | v6.0.0 | 2026-05-07 | SDD-Pro maintainer | Stack initial du framework |
| C2 | v6.10.4-LTS | 2026-05-11 | SDD-Pro maintainer | Workspace CMSPrint (4 FEATs, 10 US, schema PostgreSQL) |
| C3-C5 | `<TBD>` | `<TBD>` | `<TBD>` | Planifiés post-v7.0.0 GA (cf. §3) |

---

## 8. Pointers

- `@.claude/CLAUDE.md §7` — table stacks (statut `Validation:` par stack)
- `@.claude/docs/architecture.md §4` — détail des stacks supportés
- `@.claude/docs/poc-roi-methodology.md` — méthodologie de validation combo
- `@.claude/docs/roi-baseline.md` — résultats PoCs (à remplir)
- `@.claude/python/sdd_scripts/validate_stack_combo.py` — script §4.2
- `@.claude/stacks/_drafts/README.md` — procédure réactivation stack quarantine

---

*Document maintenu à chaque nouvelle PoC combo validée. Source de vérité
pour la décision « ce combo est-il safe ? ». Référencé depuis CLAUDE.md §7.*
