# Reverse Engineering Workflow — Design Doc (v1, 2026-06-09)

> **Statut** : Draft pour validation Tech Lead.
> **Master prompt** : [reverse-engineering-master-prompt.md](reverse-engineering-master-prompt.md)
> **Isolation** : nouveau fichier. Aucun fichier existant SDD_Pro modifié.
> **Périmètre v1** : spec complète des 4 phases (1+2+3+4). Implémentation MVP couvre phases 1+3 uniquement (cf. §13).

---

## TOC

- §1 — Vue d'ensemble et principes
- §2 — Phase 1 : Inventory (scan + détection unités fonctionnelles)
- §3 — Phase 2 : Tech audit (optionnel, informational)
- §4 — Phase 3 : Functional extraction (unité → FEAT.md)
- §5 — Phase 4 : UI extraction (templates → HTML mockup) [V2]
- §6 — Configuration : `language_signatures.yml`
- §7 — Format FEAT généré (frontmatter + sections)
- §8 — Contrats inter-phases (data flow)
- §9 — Walkthrough sur un mini-legacy fictif
- §10 — Plan de tests
- §11 — Codes d'erreur `[REVERSE_*]`
- §12 — Considérations runtime (coût, idempotence, parallélisme)
- §13 — Périmètre MVP vs V2 vs V3
- §14 — Questions ouvertes à arbitrer avant code

---

## 1. Vue d'ensemble et principes

### 1.1 Objectif

Transformer un projet legacy déposé dans `workspace/old/{LegacyProject}/` en un ensemble de FEATs SDD_Pro standards, exploitables tels quels par `/sdd-full {n}` ou `/sdd-poc {n}` pour régénérer une application moderne. Le workflow n'altère aucun fichier existant du framework SDD_Pro.

### 1.2 Principes load-bearing

| Principe | Mécanisme |
|---|---|
| **Language-agnostic** | Détection via `language_signatures.yml` (déclaratif extensible). L'agent LLM lit n'importe quel texte ; les scripts Python font le déterministe |
| **Chunking fin par intention** | 1 FEAT = 1 intention utilisateur cohérente (grid CRUD, menu, wizard, recherche). 1-4 FEATs par page legacy |
| **Evidence-driven** | Chaque AC/SFD/BR cite `file.ext:Lstart-Lend`. Pas d'evidence = item rejeté |
| **Bias toward present** | Si non visible dans le code → non documenté. Anti-hallucination strict |
| **Confidence calibrée** | Chaque item porte `high\|medium\|low`. Cap par langage |
| **Output français** | FEATs, inventaires, audits en français. Comments evidence en anglais |
| **Pipeline reproductible** | Re-run idempotent : même legacy → même output (modulo timestamp) |
| **Validation aval** | Toute FEAT générée passe `/feat-validate {n} --json` sans NO-GO structural |

### 1.3 Pipeline complet (6 phases)

```
Phase 0 [humain]    → dépôt code legacy dans workspace/old/{LegacyProject}/
Phase 1 [scan]      → /sdd-reverse-inventory → inventory.{md,json}
                      (langages, frameworks, pages, unités fonctionnelles candidates)
Phase 2 [optionnel] → /sdd-reverse-audit → tech-audit.md, db-schema.{json,md}
                      (architecture, anti-patterns, deps EOL — informational)
Phase 3 [extract]   → /sdd-reverse {unit-id} → workspace/input/feats/{n}-{Name}.md
                      (1 invocation = 1 unité fonctionnelle = 1 FEAT)
Phase 4 [UI]        → /sdd-reverse-ui {unit-id} → workspace/input/ui/{n}-{m}-{Name}.html
                      (templates legacy → HTML mockup sémantique) [V2]
Phase 5 [humain]    → revue Tech Lead + designer optionnel
                      (correction confidence low, ajustement chunking, redesign CSS)
Phase 6 [migration] → /sdd-full {n} ou /sdd-poc {n} (workflow EXISTANT, inchangé)
```

### 1.4 Mapping rôles : qui produit quoi

| Acteur | Phase | Output |
|---|---|---|
| **Tech Lead humain** | 0, 5 | Dépose le legacy, valide l'inventory et les FEATs, déclenche /sdd-full |
| **Script Python `scan_legacy.py`** | 1a | Détection langages déterministe → `inventory-raw.json` |
| **Script Python `inventory_builder.py`** | 1a | Modules, pages, LOC, entry points → `inventory-raw.json` enrichi |
| **Script Python `ui_unit_detector.py`** | 1b | Pre-détection unités évidentes (GridView, FormView, etc.) → `units-candidates.json` |
| **Agent `reverse-inventory`** | 1b | Inventaire lisible humain + arbitrage unités ambiguës → `inventory.md` |
| **Agent `reverse-tech-auditor`** | 2 | Architecture, anti-patterns, deps → `tech-audit.md` |
| **Script Python `db_schema_extractor.py`** | 2 | DB schema déterministe → `db-schema.json` |
| **Agent `reverse-functional-extractor`** | 3 | Une unité → une FEAT.md (frontmatter + sections SDD_Pro) |
| **Agent `reverse-ui-extractor`** | 4 | Une unité → un mockup HTML sémantique |
| **Designer humain** | 5 (optionnel) | Améliore CSS / redessine HTML mockups |

---

## 2. Phase 1 : Inventory (scan + détection unités fonctionnelles)

### 2.1 Objectif

Produire un inventaire structuré du legacy avec :
- Langages et frameworks détectés
- Liste des pages / écrans / formulaires
- Découpage en **unités fonctionnelles candidates** (= FEATs potentielles)
- Suggestion d'ordre de traitement (du plus simple au plus complexe)

### 2.2 Sous-étapes 1a + 1b

```
1a. Scan déterministe (Python, 0 token)
    scan_legacy.py + inventory_builder.py + ui_unit_detector.py
    → workspace/old/{P}/.sys/inventory-raw.json
    → workspace/old/{P}/.sys/units-candidates.json

1b. Synthèse LLM (agent reverse-inventory, Sonnet 4.6, ~10-15 KB context)
    Lit inventory-raw.json + units-candidates.json
    → workspace/old/{P}/.sys/inventory.md (lisible humain)
    → workspace/old/{P}/.sys/inventory.json (machine, source de vérité Phase 3)
```

### 2.3 Format `inventory-raw.json` (sortie 1a)

```json
{
  "schema_version": 1,
  "project": "AcmeCRM",
  "project_path": "workspace/old/AcmeCRM",
  "scanned_at": "2026-06-09T14:32:18Z",
  "languages": [
    { "id": "dotnet-webforms", "confidence_hint": "high", "files_count": 23, "loc": 4521 },
    { "id": "javascript-jquery", "confidence_hint": "medium", "files_count": 8, "loc": 1203 },
    { "id": "css", "confidence_hint": "n/a", "files_count": 3, "loc": 412 }
  ],
  "frameworks": [
    { "id": "asp.net-webforms", "evidence": "Web.config:line=23 + *.aspx with runat=server" },
    { "id": "jquery", "version_detected": "1.11.3", "evidence": "Scripts/jquery-1.11.3.min.js" }
  ],
  "manifests": [
    { "path": "AcmeCRM.csproj", "type": "msbuild" },
    { "path": "Web.config", "type": "iis-config" },
    { "path": "Scripts/packages.config", "type": "nuget" }
  ],
  "entry_points": [
    { "path": "Default.aspx", "type": "page", "route": "/" },
    { "path": "Customers/List.aspx", "type": "page", "route": "/Customers/List" }
  ],
  "pages": [
    {
      "id": "page-001",
      "path": "Customers/List.aspx",
      "code_behind": "Customers/List.aspx.cs",
      "title_detected": "Liste des clients",
      "loc": 145,
      "complexity_score": 3
    }
  ],
  "modules_suggested": [
    { "id": "module-customers", "label": "Gestion des clients", "pages": ["page-001", "page-002"], "loc_total": 412 }
  ],
  "exclusions": {
    "vendored": ["Scripts/jquery-1.11.3.min.js", "Scripts/jquery-ui/"],
    "generated": ["obj/", "bin/", "*.designer.cs"],
    "tests": [],
    "dead_code_candidates": ["OldStuff/Legacy.aspx (no inbound reference)"]
  },
  "stats": {
    "files_total": 47,
    "files_analyzed": 31,
    "files_excluded": 16,
    "loc_total": 6136,
    "loc_analyzed": 5724
  }
}
```

### 2.4 Format `units-candidates.json` (sortie 1a)

```json
{
  "schema_version": 1,
  "extracted_at": "2026-06-09T14:32:18Z",
  "units": [
    {
      "id": "unit-001",
      "page_id": "page-001",
      "page_path": "Customers/List.aspx",
      "type": "grid-crud",
      "label_proposed": "Liste et CRUD clients",
      "evidence": [
        { "file": "Customers/List.aspx", "lines": "45-120", "pattern": "asp:GridView with OnRowEditing+OnRowDeleting" }
      ],
      "code_behind_evidence": [
        { "file": "Customers/List.aspx.cs", "lines": "23-89", "methods": ["GridView1_RowEditing", "GridView1_RowDeleting", "BindGrid"] }
      ],
      "merge_hint": null,
      "split_hint": null,
      "confidence_hint": "high"
    },
    {
      "id": "unit-002",
      "page_id": "page-001",
      "page_path": "Customers/List.aspx",
      "type": "filter-panel",
      "label_proposed": "Filtres recherche clients",
      "evidence": [
        { "file": "Customers/List.aspx", "lines": "20-44", "pattern": "asp:DropDownList + asp:TextBox + asp:Button OnClick=BtnSearch" }
      ],
      "merge_hint": "unit-001 (filtres = sous-flux du CRUD)",
      "confidence_hint": "medium"
    },
    {
      "id": "unit-003",
      "page_id": "page-master",
      "page_path": "Site.Master",
      "type": "navigation-menu",
      "label_proposed": "Menu principal",
      "evidence": [
        { "file": "Site.Master", "lines": "8-35", "pattern": "asp:Menu DataSourceID=SiteMapDataSource1" }
      ],
      "confidence_hint": "high"
    }
  ]
}
```

### 2.5 Format `inventory.md` (sortie 1b — lecture humaine)

```markdown
# Inventaire — AcmeCRM

> Généré par /sdd-reverse-inventory le 2026-06-09T14:32:18Z
> Confidence globale : high (legacy bien structuré, ASP.NET WebForms standard)

## Vue d'ensemble

- **Langage principal** : ASP.NET WebForms (.NET Framework 4.x)
- **Langages secondaires** : jQuery 1.11.3, CSS 2
- **Architecture détectée** : monolithe MVC pattern code-behind
- **Fichiers analysés** : 31 / 47 (16 exclus : vendored, generated)
- **LOC totales analysées** : 5 724

## Modules proposés (3)

### Module 1 — Gestion des clients
- Pages : Customers/List.aspx, Customers/Edit.aspx
- Unités fonctionnelles candidates : 3
- Complexité : moyenne

### Module 2 — Navigation et layout
- Pages : Site.Master, Default.aspx
- Unités fonctionnelles candidates : 2
- Complexité : faible

### Module 3 — Authentification
- Pages : Login.aspx, Logout.aspx
- Unités fonctionnelles candidates : 2
- Complexité : faible

## Unités fonctionnelles candidates (7 total)

### Module 1 — Gestion des clients
| ID | Type | Label | Evidence principale | Confidence |
|---|---|---|---|---|
| unit-001 | grid-crud | Liste et CRUD clients | `Customers/List.aspx:45-120` (GridView) | high |
| unit-002 | filter-panel | Filtres recherche clients | `Customers/List.aspx:20-44` | medium (fusion possible avec unit-001) |
| unit-004 | form-edit | Édition fiche client | `Customers/Edit.aspx:10-95` (FormView) | high |

### Module 2 — Navigation et layout
| ID | Type | Label | Evidence | Confidence |
|---|---|---|---|---|
| unit-003 | navigation-menu | Menu principal | `Site.Master:8-35` | high |
| unit-005 | layout-header | Header avec logo + user info | `Site.Master:40-60` | medium (cosmétique, peut être omis) |

### Module 3 — Authentification
| ID | Type | Label | Evidence | Confidence |
|---|---|---|---|---|
| unit-006 | form-login | Formulaire de login | `Login.aspx:15-50` | high |
| unit-007 | flow-logout | Déconnexion + redirection | `Logout.aspx.cs:8-22` | high |

## Suggestions d'arbitrage Tech Lead

1. **Fusion proposée** : `unit-001 + unit-002` (le filter-panel est le pré-flux du grid). Si tu valides, j'écris 1 seule FEAT "Liste et recherche clients" couvrant les 2 unités.
2. **Omission proposée** : `unit-005` (header layout). C'est cosmétique sans intention métier. Si tu valides, je ne génère pas de FEAT pour cette unité.
3. **Ordre d'extraction recommandé** : unit-006 → unit-007 → unit-003 → unit-001 (+unit-002 fusionnée) → unit-004 (du plus simple au plus complexe, permet d'itérer la qualité de l'extraction).

## Exclusions automatiques détectées

- `Scripts/jquery-1.11.3.min.js` (vendored library)
- `Scripts/jquery-ui/` (vendored)
- `obj/`, `bin/`, `*.designer.cs` (generated)
- `OldStuff/Legacy.aspx` (no inbound reference — dead code candidate, à confirmer)

## Prochaines étapes

1. Valider / corriger ce découpage (édite directement ce fichier OU réponds en chat)
2. Exécuter optionnellement `/sdd-reverse-audit` pour rapport architectural
3. Lancer `/sdd-reverse unit-006` pour extraire la première unité fonctionnelle
```

### 2.6 Format `inventory.json` (sortie 1b — machine, source de vérité Phase 3)

Identique à `units-candidates.json` mais après arbitrage agent (fusion/split appliqués), avec ajout du champ `feat_number_proposed` (séquentiel pour l'ordre d'extraction).

```json
{
  "schema_version": 1,
  "project": "AcmeCRM",
  "validated_by_lead": false,
  "units": [
    {
      "id": "unit-006",
      "feat_number_proposed": 1,
      "feat_name_proposed": "Authentication-Login",
      "type": "form-login",
      "merged_with": null,
      "evidence": [...],
      "confidence_hint": "high"
    }
  ]
}
```

### 2.7 Agent `reverse-inventory` — I/O contract

**Inputs lus** :
- `workspace/old/{P}/.sys/inventory-raw.json` (obligatoire)
- `workspace/old/{P}/.sys/units-candidates.json` (obligatoire)
- `.claude/docs/reverse-engineering-cookbook/_generic-monolith.md` (lecture passive)
- `.claude/docs/reverse-engineering-cookbook/{language}.md` si langage détecté dans cookbook (lecture passive)
- Échantillon de 5-10 fichiers représentatifs du legacy (chosen by inventory_builder.py — pas tous les fichiers !)

**Outputs écrits** :
- `workspace/old/{P}/.sys/inventory.md` (Write atomique)
- `workspace/old/{P}/.sys/inventory.json` (Write atomique)

**Hors scope** : lecture du code en profondeur (Phase 3), modification de fichiers legacy (read-only strict).

**Anti-derive bullets** :
1. Ne JAMAIS lire des fichiers hors `workspace/old/{P}/` ou `.claude/docs/reverse-engineering-cookbook/`
2. Ne JAMAIS proposer d'amélioration métier ou suggérer une refonte
3. Ne JAMAIS écrire dans `workspace/input/` (ce sera Phase 3)
4. Ne JAMAIS spawner d'autre agent
5. Si ambiguïté irrécupérable → STOP + ERROR `[REVERSE_INVENTORY_AMBIGUOUS]`

---

## 3. Phase 2 : Tech audit (optionnel, informational)

### 3.1 Objectif

Produire un rapport architectural lisible humain pour informer le Tech Lead sur :
- Architecture détectée (monolithe, MVC, n-tier, microservices…)
- Anti-patterns récurrents (SQL inline, no validation, god classes…)
- Dépendances EOL ou vulnérables
- Schéma DB (entités, relations, contraintes)
- Suggestion de stack cible compatible (parmi les 25 🟢 stacks SDD_Pro)

### 3.2 Sortie principale : `tech-audit.md`

Structure type :

```markdown
# Audit technique — AcmeCRM

> Généré par /sdd-reverse-audit le 2026-06-09T15:00:00Z
> Statut : informational (non consommé par /sdd-full)

## Architecture détectée

**Pattern dominant** : monolithe MVC pattern code-behind ASP.NET WebForms
**Couches identifiées** : Présentation (.aspx) ↔ Code-behind (.cs) ↔ DAL (ADO.NET inline)
**Absence notable** : aucune couche Service / Repository, pas d'ORM

## Anti-patterns récurrents

| Anti-pattern | Occurrences | Sévérité | Exemples |
|---|---|---|---|
| SQL inline dans code-behind | 23 | critical | `Customers/List.aspx.cs:34`, `Login.aspx.cs:42` |
| Pas de validation server-side | 8 forms | serious | `Customers/Edit.aspx.cs` (uniquement RequiredFieldValidator client) |
| ViewState lourd (>50 KB) | 4 pages | moderate | `Customers/List.aspx` (GridView non paginé) |
| Hardcoded connection strings | 2 | critical | `Web.config:23`, `LegacyLogin.aspx.cs:15` |

## Dépendances et runtimes

| Composant | Version | Statut | Recommandation |
|---|---|---|---|
| .NET Framework | 4.6.2 | EOL probable 2027 | Migrer vers .NET 10 LTS |
| jQuery | 1.11.3 | EOL (2014) | Remplacer par React + shadcn ou vanilla TS |
| Bootstrap | 3.3 | EOL | Migrer Tailwind via shadcn |

## Schéma DB extrait

> Détail dans `db-schema.{json,md}`

- 8 tables détectées
- 12 foreign keys
- Aucun index secondaire détecté
- Procédures stockées : 4 (cf. `Stored_Procs.sql`)

## Suggestion de stack cible (parmi 13 combos SLA SDD_Pro)

**Recommandation primaire** : **C1** (`dotnet-minimalapi + react + shadcn + dotnet-xunit + azure-ad`)
- Justification : continuité écosystème .NET, modernisation front via React, ORM via EF Core (élimine SQL inline)

**Alternative** : **C2** (`kotlin-spring-boot + blazor-webassembly + radzen-blazor + ...`) si migration vers JVM souhaitée
```

### 3.3 Sortie secondaire : `db-schema.json`

Produit par `db_schema_extractor.py` (déterministe). Format :

```json
{
  "schema_version": 1,
  "extracted_from": ["Database/CreateSchema.sql", "Customers/List.aspx.cs (inline SQL)"],
  "tables": [
    {
      "name": "Customer",
      "columns": [
        { "name": "Id", "type": "int", "pk": true, "identity": true, "nullable": false },
        { "name": "Name", "type": "nvarchar(100)", "nullable": false },
        { "name": "Email", "type": "nvarchar(200)", "nullable": true }
      ],
      "foreign_keys": []
    }
  ],
  "stored_procedures": ["sp_GetCustomers", "sp_DeleteCustomer"],
  "indexes": [],
  "warnings": [
    "No index on Customer.Email but used in WHERE clause Customers/List.aspx.cs:67",
    "Table Customer has no audit columns (created_at, updated_at)"
  ]
}
```

### 3.4 Agent `reverse-tech-auditor` — I/O contract

**Inputs** :
- `workspace/old/{P}/.sys/inventory-raw.json`
- `workspace/old/{P}/.sys/inventory.json`
- `workspace/old/{P}/.sys/db-schema.json` (si DB détectée, produit par script Python)
- `workspace/old/{P}/.sys/deps-graph.json` (produit par script Python)
- Lecture sélective : ~20-30 fichiers représentatifs (pas tous)

**Outputs** :
- `workspace/old/{P}/.sys/tech-audit.md`

**Skippable** via `/sdd-reverse-inventory --skip-audit` ou en n'invoquant simplement pas `/sdd-reverse-audit`.

---

## 4. Phase 3 : Functional extraction (unité → FEAT.md)

### 4.1 Objectif

Pour **une seule unité fonctionnelle** (identifiée par `unit-id` dans `inventory.json`), produire **une seule FEAT.md** au format SDD_Pro standard, exploitable par `/sdd-full`.

**Critique** : 1 invocation = 1 unité = 1 FEAT. Pas de batch. Permet :
- Coût contrôlé (context budget < 40 KB par invocation)
- Idempotence (re-run = re-écriture déterministe)
- Parallélisation possible (plusieurs unités en parallèle si paths disjoints)

### 4.2 Commande

```bash
/sdd-reverse {unit-id}
# Exemple : /sdd-reverse unit-001
# Exemple : /sdd-reverse unit-001+unit-002  (fusion explicite)
```

### 4.3 Workflow agent `reverse-functional-extractor`

```
STEP 0 — Preflight (script-driven)
  python sdd_reverse_scripts/reverse_preflight.py --unit-id {id}
  → vérifie inventory.json présent, unit-id valide, FEAT n° libre
  → retourne JSON avec : feat_number, feat_name, evidence_files, confidence_cap

STEP 0.5 — Context budget HARD-GATE
  python sdd_lib/context_budget.py --agent reverse-functional-extractor --unit-id {id}

STEP 1 — Lecture sélective
  - inventory.json (passage de l'unité ciblée)
  - tech-audit.md (si présent, lecture passive)
  - Fichiers cités en evidence de l'unité (5-15 fichiers typiquement)
  - Cookbook fiche langage si présent

STEP 2 — Analyse LLM (intention utilisateur)
  - Identifier les actions utilisateur supportées
  - Identifier les règles métier (validations, calculs, workflows)
  - Identifier les acteurs (rôles, permissions)
  - Identifier les entités métier (croisement avec db-schema.json)
  - Identifier les contraintes non-fonctionnelles (perf, sécurité)

STEP 3 — Génération FEAT.md
  - Frontmatter complet (cf. §7)
  - Section ## Actors
  - Section ## Functional Needs (SFD-1, SFD-2, ...)
  - Section ## Functional Deliverables (FD-1, FD-2, ...)
  - Section ## Business Rules (BR-1, BR-2, ...)
  - Section ## Acceptance Criteria (AC-1, AC-2, ...) au format Given/When/Then
  - Section ## Project Config (vide, à compléter par /feat-generate ou Tech Lead)
  - Section ## Reverse Engineering Notes (méta : confidence, sources, biais)

STEP 4 — Auto-validation
  - Chaque item porte evidence + confidence
  - Bannière humaine si ≥ 1 item confidence:low
  - Test : pré-validation via parse_feat_yaml() si helper disponible
  - Si KO → itère STEP 3 (max 2 itérations)

STEP 5 — Write atomique
  - workspace/input/feats/{n}-{Name}.md
  - workspace/old/{P}/.sys/modules/{module-id}/extraction-{unit-id}.md (rapport agent)

STEP 6 — Verdict
  - 1L chat : [REVERSE] FEAT {n}-{Name} extraite (confidence: high|medium|low). (100%)
```

### 4.4 Anti-derive bullets

1. Ne JAMAIS lire d'autres unités que celle ciblée
2. Ne JAMAIS lire d'autres FEATs déjà écrites
3. Ne JAMAIS proposer d'amélioration métier ("on pourrait ajouter…")
4. Ne JAMAIS écrire en `confidence: high` si la moindre hésitation existe
5. Ne JAMAIS générer un AC sans evidence concrète
6. Ne JAMAIS spawner d'autre agent
7. Si l'unité ciblée ne contient pas d'intention utilisateur claire → STOP + ERROR `[REVERSE_NO_INTENT]`

---

## 5. Phase 4 : UI extraction (templates → HTML mockup) [V2]

### 5.1 Objectif

Pour **une seule unité fonctionnelle** déjà extraite en FEAT, produire **un seul HTML mockup sémantique** dans `workspace/input/ui/{n}-{m}-{Name}.html`, exploitable par `dev-frontend` en Phase 6.

### 5.2 Préservation visuelle

L'objectif n'est PAS de figer le CSS legacy mais de :
- Préserver la **structure logique** (sections, formulaires, grids, navigation)
- Préserver les **labels et libellés** (textes UI)
- Fournir des **hints structurels** au designer via `data-legacy-*` attributes
- Extraire la palette legacy dans `workspace/input/ui/_legacy-style/tokens.css` pour référence

### 5.3 Format HTML sémantique généré

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Liste et CRUD clients</title>
  <link rel="stylesheet" href="_legacy-style/tokens.css">
</head>
<body>
  <main data-legacy-source="Customers/List.aspx" data-legacy-component="Page">
    <header>
      <h1>Liste des clients</h1>
    </header>

    <section data-legacy-component="FilterPanel" data-legacy-lines="20-44">
      <form>
        <label for="filter-status">Statut</label>
        <select id="filter-status">
          <option>Tous</option>
          <option>Actif</option>
          <option>Inactif</option>
        </select>

        <label for="filter-name">Nom</label>
        <input type="text" id="filter-name">

        <button type="submit">Rechercher</button>
      </form>
    </section>

    <section data-legacy-component="GridView" data-legacy-lines="45-120">
      <table>
        <thead>
          <tr>
            <th>N°</th>
            <th>Nom</th>
            <th>Email</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>1</td>
            <td>Acme Corp</td>
            <td>contact@acme.com</td>
            <td>Actif</td>
            <td>
              <button data-action="edit">Éditer</button>
              <button data-action="delete">Supprimer</button>
            </td>
          </tr>
          <!-- exemple data row uniquement, structure répétée -->
        </tbody>
      </table>
      <nav data-legacy-component="Pager">
        <button>Précédent</button>
        <span>Page 1 / N</span>
        <button>Suivant</button>
      </nav>
    </section>
  </main>
</body>
</html>
```

### 5.4 Format `_legacy-style/tokens.css`

```css
/* Extracted from AcmeCRM/Styles/site.css + inline styles, 2026-06-09 */
:root {
  --legacy-primary: #2c5aa0;      /* extracted from site.css:12 (background-color: #2c5aa0) */
  --legacy-bg: #f7f7f7;
  --legacy-text: #333333;
  --legacy-font: "Tahoma", "Arial", sans-serif;
  --legacy-radius: 0;             /* no border-radius detected in legacy */
  --legacy-spacing-unit: 4px;
  --legacy-table-border: #cccccc;
}
```

### 5.5 Format `_legacy-style/components-inventory.md`

```markdown
# Composants UI legacy détectés — AcmeCRM

> Référence designer pour mapping vers DS moderne

| Composant legacy | Occurrences | Pages | Suggestion DS moderne |
|---|---|---|---|
| GridView | 4 | Customers/List, Orders/List, Products/List, Users/List | `<Table>` shadcn ou `<DataTable>` Radzen |
| FormView | 3 | Customers/Edit, Orders/Edit, Users/Edit | `<Form>` + `<Field>` shadcn |
| asp:Menu (SiteMap) | 1 | Site.Master | `<NavigationMenu>` shadcn ou `<Sidebar>` |
| ModalPopupExtender (AjaxControlToolkit) | 2 | Confirmations | `<Dialog>` shadcn |
```

### 5.6 Agent `reverse-ui-extractor` — I/O contract

**Inputs** :
- `workspace/input/feats/{n}-{Name}.md` (la FEAT déjà extraite — pour cohérence)
- Fichiers template legacy de l'unité (cités en evidence)
- `workspace/input/ui/_legacy-style/tokens.css` (si existe)

**Outputs** :
- `workspace/input/ui/{n}-{m}-{Name}.html`
- `workspace/input/ui/_legacy-style/tokens.css` (créé ou enrichi via Edit append-only)
- `workspace/input/ui/_legacy-style/components-inventory.md` (créé ou enrichi)

**Note V2** : phase 4 est hors scope MVP. Spec ici à titre de contrat futur.

---

## 6. Configuration : `language_signatures.yml`

### 6.1 Emplacement et rôle

`.claude/python/sdd_reverse/language_signatures.yml` — déclaratif, extensible sans modification de code. Source de vérité pour `scan_legacy.py`.

### 6.2 Schéma

```yaml
schema_version: 1

languages:
  - id: dotnet-webforms
    label: ASP.NET WebForms
    extensions: [".aspx", ".ascx", ".asmx", ".ashx"]
    companion_extensions: [".aspx.cs", ".aspx.vb", ".ascx.cs"]
    manifests: ["*.csproj", "Web.config"]
    folder_signals: ["App_Code/", "App_Data/", "Scripts/"]
    grep_signals:
      - 'runat="server"'
      - "@\\s*Page\\s+Language="
    confidence_hint: high
    cookbook_fiche: "dotnet-webforms.md"

  - id: dotnet-mvc
    label: ASP.NET MVC
    extensions: [".cshtml", ".razor"]
    companion_extensions: []
    manifests: ["*.csproj"]
    folder_signals: ["Controllers/", "Views/", "Models/", "Areas/"]
    grep_signals:
      - "@\\s*model\\s+"
      - "ActionResult"
    confidence_hint: high
    cookbook_fiche: "dotnet-mvc.md"

  - id: java-jee
    label: Java JEE
    extensions: [".java", ".jsp", ".jspx", ".tag"]
    manifests: ["web.xml", "pom.xml", "build.gradle"]
    folder_signals: ["WEB-INF/", "src/main/java/", "src/main/webapp/"]
    grep_signals:
      - "@WebServlet"
      - "javax.servlet"
    confidence_hint: high
    cookbook_fiche: "java-jee.md"

  - id: javascript-jquery
    label: JavaScript + jQuery
    extensions: [".js"]
    manifests: []
    grep_signals:
      - "\\$\\("
      - "jQuery\\("
      - "\\.ajax\\("
    confidence_hint: medium
    cookbook_fiche: "javascript-jquery.md"

  - id: php-procedural
    label: PHP procedural
    extensions: [".php", ".phtml", ".inc"]
    manifests: [".htaccess"]
    grep_signals:
      - "<\\?php"
      - "\\$_POST"
      - "\\$_GET"
      - "mysqli_query|mysql_query"
    confidence_hint: medium
    cookbook_fiche: "php-procedural.md"

  - id: delphi
    label: Delphi
    extensions: [".pas", ".dpr", ".dfm", ".dproj"]
    manifests: ["*.dproj"]
    confidence_hint: medium
    cookbook_fiche: "delphi.md"

  - id: css
    label: CSS
    extensions: [".css", ".less", ".scss"]
    confidence_hint: n/a
    cookbook_fiche: null

  - id: unknown
    label: Inconnu
    extensions: []
    fallback: true
    confidence_hint: low
    cookbook_fiche: "_generic-monolith.md"

exclusions:
  vendored_patterns:
    - "node_modules/"
    - "vendor/"
    - "packages/"
    - "Scripts/jquery-*.min.js"
    - "Scripts/jquery-ui/"
    - "Scripts/bootstrap*.min.js"
  generated_patterns:
    - "obj/"
    - "bin/"
    - "*.designer.cs"
    - "*.g.cs"
    - "target/"
    - "build/"
  test_patterns:
    - "*.test.js"
    - "*.spec.ts"
    - "**/__tests__/**"
    - "**/Tests/**"
```

### 6.3 Ajouter un nouveau langage

Éditer ce YAML, ajouter une entrée. Pas de code Python à modifier. `scan_legacy.py` itère sur la liste.

---

## 7. Format FEAT généré (frontmatter + sections)

### 7.1 Frontmatter complet

```yaml
---
# Champs SDD_Pro standards (compat /feat-validate)
title: Liste et CRUD clients
version: 1
created: 2026-06-09

# Champs spécifiques reverse engineering
generated-by: sdd-reverse
extraction-date: 2026-06-09T15:42:18Z
language-detected: dotnet-webforms
legacy-sources:
  - workspace/old/AcmeCRM/Customers/List.aspx
  - workspace/old/AcmeCRM/Customers/List.aspx.cs
  - workspace/old/AcmeCRM/Customers/Edit.aspx
  - workspace/old/AcmeCRM/Customers/Edit.aspx.cs
unit-id: unit-001
confidence: high
confidence-low-items: 0
human-review-required: false
---
```

### 7.2 Bannière humaine (si confidence low présent)

Si **≥ 1 item** porte `confidence: low`, ajouter en haut du fichier (sous le frontmatter) :

```markdown
> ⚠️ **Revue humaine requise** — Cette FEAT contient {N} item(s) en `confidence: low` (langage : {lang} ou intention ambiguë).
> Lire les commentaires `<!-- confidence: low -->` et compléter / corriger avant `/sdd-full {n}`.
```

### 7.3 Sections obligatoires (format SDD_Pro)

```markdown
## Actors

- **Utilisateur final** : consulte la liste des clients et effectue des opérations CRUD
- **Administrateur** : a accès à toutes les opérations, y compris la suppression

<!-- evidence: Customers/List.aspx.cs:18-22 (User.IsInRole("Admin") check) -->
<!-- confidence: high -->

## Functional Needs

- **SFD-1** : Afficher une liste paginée des clients avec colonnes (N°, Nom, Email, Statut)
  <!-- evidence: Customers/List.aspx:45-90 (GridView with 5 columns) -->
  <!-- confidence: high -->

- **SFD-2** : Filtrer la liste par statut et par nom partiel
  <!-- evidence: Customers/List.aspx:20-44 (FilterPanel + BtnSearch_Click) -->
  <!-- confidence: high -->

- **SFD-3** : Éditer un client depuis la liste (édition inline ou page dédiée)
  <!-- evidence: Customers/List.aspx:95-105 (LinkButton CommandName=Edit) + Customers/Edit.aspx -->
  <!-- confidence: high -->

- **SFD-4** : Supprimer un client avec confirmation
  <!-- evidence: Customers/List.aspx:106-115 (LinkButton CommandName=Delete + OnClientClick=confirm()) -->
  <!-- confidence: high -->

## Functional Deliverables

- **FD-1** : Page de liste paginée (10 par page par défaut) — covers: SFD-1
- **FD-2** : Panel de filtres (statut dropdown + nom textbox + bouton Rechercher) — covers: SFD-2
- **FD-3** : Action éditer ouvrant un formulaire pré-rempli — covers: SFD-3
- **FD-4** : Action supprimer avec confirmation JavaScript — covers: SFD-4

## Business Rules

- **BR-1** : Un client supprimé est marqué `Inactif` (soft delete), non effacé en base
  <!-- evidence: Customers/List.aspx.cs:67-72 (UPDATE Customer SET IsActive=0) -->
  <!-- confidence: high -->

- **BR-2** : Seuls les administrateurs peuvent supprimer
  <!-- evidence: Customers/List.aspx.cs:18-22 (User.IsInRole("Admin")) + List.aspx:106 (Visible='<%# IsAdmin %>') -->
  <!-- confidence: high -->

- **BR-3** : La recherche par nom est insensible à la casse et fait du préfixe partiel
  <!-- evidence: Customers/List.aspx.cs:34-38 (WHERE Name LIKE @Name + "%") -->
  <!-- confidence: medium -->

## Acceptance Criteria

- **AC-1** : Given un utilisateur connecté, When il accède à /Customers/List, Then la liste des clients actifs s'affiche paginée par 10, triée par Nom ASC
  <!-- evidence: Customers/List.aspx.cs:45-60 (BindGrid with PageSize=10, ORDER BY Name) -->
  <!-- confidence: high -->
  <!-- covers: SFD-1, FD-1 -->

- **AC-2** : Given la page liste affichée, When l'utilisateur saisit "acme" dans le filtre nom et clique Rechercher, Then seuls les clients dont le nom commence par "acme" (insensible casse) s'affichent
  <!-- evidence: Customers/List.aspx.cs:34-44 (BtnSearch_Click → BindGrid with filter) -->
  <!-- confidence: high -->
  <!-- covers: SFD-2, FD-2, BR-3 -->

- **AC-3** : Given un client dans la liste, When l'utilisateur clique Éditer, Then la page Customers/Edit.aspx s'ouvre avec le formulaire pré-rempli depuis la DB
  <!-- evidence: Customers/List.aspx:95-105 + Customers/Edit.aspx.cs:Page_Load -->
  <!-- confidence: high -->
  <!-- covers: SFD-3, FD-3 -->

- **AC-4** : Given un administrateur connecté, When il clique Supprimer sur une ligne, Then une confirmation JS s'affiche ; si confirmée, le client passe à IsActive=0 et disparaît de la liste
  <!-- evidence: Customers/List.aspx:106-115 + Customers/List.aspx.cs:67-72 -->
  <!-- confidence: high -->
  <!-- covers: SFD-4, FD-4, BR-1, BR-2 -->

## Project Config

<!-- À compléter par /feat-generate ou manuellement par le Tech Lead -->
<!-- Stack cible à choisir parmi les 13 combos SLA SDD_Pro -->

## Reverse Engineering Notes

- **Source legacy** : ASP.NET WebForms (.NET Framework 4.6.2)
- **Unité fonctionnelle ID** : unit-001
- **Fichiers analysés** : Customers/List.aspx, Customers/List.aspx.cs, Customers/Edit.aspx, Customers/Edit.aspx.cs
- **Confidence globale** : high
- **Items en confidence:low** : 0
- **Biais explicites** :
  - "Bias toward present" appliqué : 1 bouton "Export Excel" présent dans le HTML mais sans gestionnaire serveur → non documenté en SFD
  - Pagination détectée à PageSize=10 (hardcoded) → BR potentielle non émise (manque d'evidence sur "pourquoi 10")
- **Items écartés (dead code suspect)** :
  - `Customers/List.aspx:130-145` (méthode `LegacyExport` non référencée nulle part)
```

### 7.4 Test de conformité

Toute FEAT générée DOIT passer :

```bash
python .claude/python/sdd_scripts/validate_readiness.py --feat-number {n} --json
# Exit 0 requis
```

Si exit ≠ 0 → l'agent itère STEP 3 (max 2 fois) puis STOP + ERROR `[REVERSE_FEAT_INVALID]`.

---

## 8. Contrats inter-phases (data flow)

| De → vers | Artefact partagé | Format | Owner write |
|---|---|---|---|
| Phase 1a → 1b | `inventory-raw.json`, `units-candidates.json` | JSON | Scripts Python |
| Phase 1b → 3 | `inventory.json` (source de vérité unités) | JSON | Agent `reverse-inventory` |
| Phase 1b → 2 | `inventory.json`, `inventory-raw.json` | JSON | (lecture seule en Phase 2) |
| Phase 2 → 3 | `db-schema.json`, `tech-audit.md` | JSON + MD | Agent `reverse-tech-auditor` + script Python |
| Phase 3 → 4 | `workspace/input/feats/{n}-{Name}.md` | MD frontmatter | Agent `reverse-functional-extractor` |
| Phase 3 → 6 | `workspace/input/feats/{n}-{Name}.md` | MD frontmatter compatible `/feat-validate` | (lecture seule par `/sdd-full`) |
| Phase 4 → 6 | `workspace/input/ui/{n}-{m}-{Name}.html` | HTML sémantique | Agent `reverse-ui-extractor` |

**Invariant** : aucune phase ne lit d'artefact ailleurs que dans ces contrats. Aucune phase n'écrit en dehors de ses paths déclarés.

---

## 9. Walkthrough sur un mini-legacy fictif

### 9.1 Setup

```
workspace/old/AcmeCRM/
├── Default.aspx                    (page d'accueil, redirige vers /Customers/List)
├── Default.aspx.cs
├── Site.Master                     (master page avec menu navigation)
├── Site.Master.cs
├── Customers/
│   ├── List.aspx                   (GridView + filtres)
│   ├── List.aspx.cs                (BindGrid, BtnSearch_Click, delete handler)
│   ├── Edit.aspx                   (FormView)
│   └── Edit.aspx.cs                (Save_Click, Cancel_Click)
├── Login.aspx                      (formulaire de login)
├── Login.aspx.cs                   (AuthenticateUser via DB)
├── Web.config                      (connection string, auth config)
├── AcmeCRM.csproj
├── Styles/
│   └── site.css
└── Scripts/
    ├── jquery-1.11.3.min.js        (vendored, exclu)
    └── app.js                      (~50 lignes : validations client + AJAX search)
```

### 9.2 Phase 1 — Inventory

```bash
# Tech Lead invoque
/sdd-reverse-inventory workspace/old/AcmeCRM

# Scripts Python tournent (0 token, ~2s)
[REVERSE] Scan legacy AcmeCRM... (5%)
[REVERSE] 13 fichiers analysés, 1 vendored exclu. (15%)
[REVERSE] Détection langages : dotnet-webforms (high), javascript-jquery (medium), css. (25%)
[REVERSE] 5 unités fonctionnelles candidates identifiées. (35%)

# Agent reverse-inventory tourne (Sonnet ~15 KB context, ~5s)
[REVERSE-INVENTORY] Synthèse modules + arbitrages... (60%)
[REVERSE-INVENTORY] Inventaire écrit. (95%)

[DONE] Inventory AcmeCRM — 5 unités candidates, confidence globale high. (100%)
```

Output : `workspace/old/AcmeCRM/.sys/inventory.md` (lisible humain) + `inventory.json` (machine).

### 9.3 Phase 3 — Extraction unité par unité

```bash
# Tech Lead lance la 1ère extraction (la plus simple : login)
/sdd-reverse unit-006

# Agent reverse-functional-extractor (Opus ~30 KB context, ~15s)
[REVERSE] Lecture sélective unit-006 (Login.aspx + Login.aspx.cs)... (10%)
[REVERSE] Analyse intention utilisateur + règles métier... (40%)
[REVERSE] Génération FEAT 1-Authentication-Login.md... (75%)
[REVERSE] Auto-validation (/feat-validate)... (90%)

[DONE] FEAT 1-Authentication-Login extraite — confidence:high (4 SFD, 3 AC, 2 BR). (100%)
```

Output : `workspace/input/feats/1-Authentication-Login.md` (au format SDD_Pro standard, exploitable par `/sdd-full 1`).

### 9.4 Itération sur les autres unités

```bash
/sdd-reverse unit-007       # → FEAT 2-Authentication-Logout
/sdd-reverse unit-003       # → FEAT 3-Navigation-Menu
/sdd-reverse unit-001+unit-002    # → FEAT 4-Customers-List-CRUD (fusion)
/sdd-reverse unit-004       # → FEAT 5-Customers-Edit
```

### 9.5 Phase 6 — Migration vers stack moderne (existant)

```bash
/sdd-full 1     # → génère le code moderne pour FEAT 1 (Login)
/sdd-full 4     # → génère le code moderne pour FEAT 4 (Customers CRUD)
```

Le pipeline `/sdd-full` est inchangé. Il consomme les FEATs comme si elles avaient été écrites par `/feat-generate`.

---

## 10. Plan de tests

### 10.1 Tests unitaires Python (sdd_reverse/)

Couverture cible ≥ 80%.

| Fichier testé | Cas couverts |
|---|---|
| `scan_legacy.py` | Détection .NET WebForms, MVC, J2E, PHP, jQuery, Delphi, mix langages, unknown fallback, exclusions vendored/generated |
| `inventory_builder.py` | Découpage modules, LOC count, exclusions, entry points detection, complexité scoring |
| `ui_unit_detector.py` | Patterns GridView, FormView, Menu, Wizard, FilterPanel, ModalPopup |
| `db_schema_extractor.py` | Extraction depuis SQL files, EF migrations, Hibernate XML, Doctrine annotations, warnings (no index, no audit cols) |

### 10.2 Tests intégration

| Test | Setup | Assertion |
|---|---|---|
| `test_scan_dotnet_webforms_minimal` | Mini-legacy 5 .aspx + .cs | `inventory-raw.json` détecte dotnet-webforms high confidence, identifie GridView |
| `test_scan_php_procedural` | Mini-legacy 3 .php | Détection php-procedural medium, alerte mysqli inline |
| `test_scan_mixed_legacy` | .NET + jQuery + CSS | 3 langages détectés, ordre par LOC |
| `test_inventory_excludes_vendored` | Legacy avec node_modules/ et jquery-1.11.3.min.js | Vendored exclu, ne contamine pas LOC stats |
| `test_inventory_excludes_dead_code` | Page sans inbound reference | Marquée dead_code_candidate, pas dans modules suggérés |

### 10.3 Tests end-to-end (manuel, sur legacy réel)

1. Tech Lead fournit un legacy réel (idéalement < 50 fichiers pour MVP)
2. Exécuter `/sdd-reverse-inventory`
3. Valider inventaire (relire `inventory.md`, ajuster si besoin)
4. Exécuter `/sdd-reverse {unit-id}` sur 2-3 unités
5. Valider FEATs via `/feat-validate {n} --json` (exit 0 requis)
6. Exécuter `/sdd-full {n}` sur 1 FEAT
7. Vérifier que le code généré compile et démarre

### 10.4 Tests anti-régression isolation

```bash
# Avant chaque commit
git diff .claude/agents/ .claude/commands/ .claude/rules/ .claude/skills/ \
        .claude/python/sdd_lib/ .claude/python/sdd_scripts/ .claude/python/sdd_admin/ .claude/python/sdd_hooks/ \
        .claude/loader.yml .claude/INVARIANTS.yml .claude/CLAUDE.md .claude/settings.json \
        bootstrap.py workspace/console/
# DOIT être vide
```

Et :

```bash
python .claude/python/sdd_admin/framework_smoke.py
# DOIT exit 0 (framework SDD_Pro existant inchangé)
```

---

## 11. Codes d'erreur `[REVERSE_*]`

Définis dans `rules/reverse-engineering.md` (nouvelle règle dédiée). Format ERROR/CAUSE/FIX standard :

| Préfixe | Phase | Sévérité | Sens |
|---|---|---|---|
| `[REVERSE_PRECONDITION]` | toutes | critical | workspace/old/{P}/ absent ou vide |
| `[REVERSE_SCAN_FAILED]` | 1a | critical | scan_legacy.py exit ≠ 0 (I/O ou parse YAML) |
| `[REVERSE_NO_LANGUAGE]` | 1a | critical | Aucun langage détecté (legacy vide ou exotique non-supporté) |
| `[REVERSE_INVENTORY_AMBIGUOUS]` | 1b | critical | Agent reverse-inventory ne peut pas trancher la fusion/split d'unités |
| `[REVERSE_NO_INTENT]` | 3 | critical | Unité ciblée ne contient pas d'intention utilisateur claire (ex. fichier de config sans UI) |
| `[REVERSE_UNIT_NOT_FOUND]` | 3 | critical | `unit-id` passé en arg absent de `inventory.json` |
| `[REVERSE_FEAT_INVALID]` | 3 | critical | FEAT générée ne passe pas `/feat-validate` après 2 itérations |
| `[REVERSE_FEAT_NUMBER_TAKEN]` | 3 | critical | `workspace/input/feats/{n}-*.md` déjà existant (collision numérotation) |
| `[REVERSE_EVIDENCE_MISSING]` | 3 | warning | Item généré sans evidence → rejeté du draft, agent itère |
| `[REVERSE_CONFIDENCE_DEGRADED]` | 3 | info | Langage à confidence_cap medium ou low — bannière humaine ajoutée |
| `[REVERSE_DB_NOT_DETECTED]` | 2 | warning | Aucun schéma DB détectable (legacy sans .sql ni ORM) |
| `[REVERSE_TECH_AUDIT_SKIPPED]` | 2 | info | Phase 2 skippée par `--skip-audit` |
| `[REVERSE_OUTPUT_LANGUAGE]` | 3 | info | Output forcé en français (D6) — informational |

---

## 12. Considérations runtime

### 12.1 Context budget par agent

| Agent | Budget ciblé | Calcul |
|---|---|---|
| `reverse-inventory` | ~10-15 KB | inventory-raw.json (~2 KB) + units-candidates.json (~3 KB) + cookbook fiche (~3 KB) + échantillon 5-10 fichiers (~5 KB) |
| `reverse-tech-auditor` | ~20-30 KB | inputs Phase 1 + db-schema.json + deps-graph.json + 20-30 fichiers échantillons |
| `reverse-functional-extractor` | ~25-40 KB | inventory.json (1 unité) + 5-15 fichiers de l'unité + cookbook fiche + db-schema.json relevant section |
| `reverse-ui-extractor` | ~20-30 KB | FEAT.md (~5 KB) + templates legacy unit (~10 KB) + tokens.css (~1 KB) |

Hard-gate `context_budget.py` (existant) NON utilisé en MVP (le SSoT actuel ne référence pas les agents reverse). À ajouter en V2 — ce sera la 1ère exception "modification existante demandée" à arbitrer.

### 12.2 Cost cap

Réutilisation du mécanisme `MaxCostPerRun` existant ? **Non en MVP** (touche `read_layered_config` et `preflight_cost_cap.py` existants). Cap manuel via env var `SDD_REVERSE_MAX_USD` (lue uniquement par scripts reverse, isolé).

### 12.3 Idempotence

- **Re-run `/sdd-reverse-inventory`** : écrase `inventory-raw.json`, `inventory.json`, `inventory.md`. Si humain a édité `inventory.md` entre-deux, alerte avant écrasement (hash check).
- **Re-run `/sdd-reverse {unit-id}`** : si `workspace/input/feats/{n}-{Name}.md` existe ET `generated-by: sdd-reverse` ET hash unité inchangé → skip silencieux. Sinon → re-write avec warning.
- **Hash unité** : sha256 des fichiers cités en evidence (concaténation triée). Stocké dans frontmatter (`unit-hash: sha256:...`).

### 12.4 Parallélisme

Phase 3 supporte parallélisme entre unités si **paths disjoints** (paths d'écriture = `workspace/input/feats/{n}-*.md` uniques par invocation). Pas de mécanisme automatique en MVP — Tech Lead lance manuellement les invocations en parallèle si désiré.

---

## 13. Périmètre MVP vs V2 vs V3

### 13.1 MVP (Livraison 1)

✅ Phase 1 complète (scan + inventory agent)
✅ Phase 3 complète (functional extraction)
✅ Commandes : `/sdd-reverse-init`, `/sdd-reverse-inventory`, `/sdd-reverse`
✅ Scripts Python : `scan_legacy.py`, `inventory_builder.py`, `ui_unit_detector.py`
✅ Agents : `reverse-inventory`, `reverse-functional-extractor`
✅ Loader séparé `loader.reverse.yml`
✅ Règle `rules/reverse-engineering.md`
✅ Skill `starting-a-reverse-eng`
✅ Tests unitaires Python ≥ 80% coverage
✅ Cookbook fiches : `_generic-monolith.md` + 1 fiche par langage testé en MVP

❌ Phase 2 tech audit
❌ Phase 4 UI extraction
❌ Orchestrateur `/sdd-reverse-full`
❌ `/sdd-reverse-status` diagnostic
❌ `db_schema_extractor.py`, `deps_graph_builder.py`, `css_palette_extractor.py`, `ui_template_parser.py`
❌ Agents `reverse-tech-auditor`, `reverse-ui-extractor`
❌ Règle `rules/reverse-ui-fidelity.md`

### 13.2 V2 (Livraison 2)

Ajoute :
- Phase 2 complète (tech audit)
- Phase 4 complète (UI extraction)
- Orchestrateur `/sdd-reverse-full` (chaîne phases 1→4 avec validation Tech Lead)
- `/sdd-reverse-audit` standalone
- `/sdd-reverse-ui` standalone
- Cookbook complet (toutes les fiches langages)

### 13.3 V3 (long terme)

- Round-trip validation : grep AC dans le code, vérifier que chaque AC est trouvable
- Mode `--evidence-mode strict` CI-grade (refuse toute confidence:low)
- Re-run incrémental sur legacy modifié (diff vs version précédente)
- Support langages exotiques (VB6, Cobol, Visual FoxPro, etc.)
- Screenshot capture si app démarrable
- Generation de tests d'acceptation Playwright depuis les AC

---

## 14. Questions ouvertes à arbitrer avant code

Avant de démarrer l'implémentation MVP (étape B du master prompt), 5 décisions résiduelles à valider :

### Q1 — Numérotation des FEATs : comment éviter les collisions ?

**Contexte** : `workspace/input/feats/` peut déjà contenir des FEATs créées par `/feat-generate` (greenfield) avant le reverse. Comment numéroter les FEATs générées par `/sdd-reverse` ?

**Options** :
- **A** — Continuité simple : `/sdd-reverse` prend le prochain N libre (`max(existing) + 1`)
- **B** — Plage réservée : FEATs reverse numérotées à partir de `N=100` (ex. 100-Login, 101-Logout)
- **C** — Préfixe : `R1-Login.md`, `R2-Logout.md` (nouvelle convention)

**Recommandation** : **A** (continuité simple). Minimise les surprises côté `/feat-validate` et `/sdd-full` qui font déjà du `glob feats/{n}-*.md`. Le frontmatter `generated-by: sdd-reverse` distingue déjà l'origine.

### Q2 — Hash d'unité : sur quoi exactement ?

**Contexte** : pour idempotence Phase 3 §12.3, on hash quoi ?

**Options** :
- **A** — sha256(concat des contenus des fichiers cités en evidence, triés par path)
- **B** — sha256(concat des fichiers + timestamps mtime)
- **C** — sha256(unit JSON dans inventory.json)

**Recommandation** : **A**. Pure fonctionnel, ignore les changements de timestamps. Si humain édite un fichier evidence, hash change, re-extraction déclenchée.

### Q3 — Fusion d'unités : syntaxe `unit-001+unit-002`

**Contexte** : `/sdd-reverse unit-001+unit-002` est intuitive mais implique parsing CLI custom.

**Options** :
- **A** — Garder `+` (parser dans la commande)
- **B** — Forcer la fusion DANS `inventory.json` (l'agent reverse-inventory fait la fusion en amont, à la validation humaine)
- **C** — Flag `--merge unit-002` en plus de l'arg unit-001

**Recommandation** : **B**. La fusion est une décision d'inventaire, pas de runtime. Le Tech Lead édite `inventory.md` pour fusionner, ré-écrit `inventory.json` (helper `consolidate_inventory.py`), puis `/sdd-reverse unit-001` produit la FEAT couvrant le scope fusionné. Plus simple, plus traçable.

### Q4 — Cookbook : pre-rédigé MVP ou progressif ?

**Contexte** : 7 fiches cookbook listées (`_generic-monolith.md` + 6 langages). Rédiger toutes en MVP ?

**Options** :
- **A** — Rédiger les 7 en MVP (~3-4h équivalent rédaction)
- **B** — MVP = `_generic-monolith.md` + fiches générées au fil des legacys testés
- **C** — MVP = uniquement `_generic-monolith.md`, fiches V2

**Recommandation** : **B**. Le générique couvre 80% des cas. On rédige les fiches spécifiques quand on rencontre un legacy de ce type. Évite de spéculer.

### Q5 — Skill auto-trigger : forme exacte du SKILL.md

**Contexte** : `skills/starting-a-reverse-eng/SKILL.md` doit trigger conservativement. Quels mots-clés ?

**Phrases de trigger proposées** :
- "reverse engineering" / "reverse engineer"
- "convertir l'ancien système" / "convertir le legacy"
- "j'ai un legacy" / "j'ai une vieille application"
- "rétroingénierie" / "ingénierie inverse"
- "moderniser l'application" / "moderniser le code"
- "migrer le legacy" / "migration legacy"
- Mention explicite : "/sdd-reverse" ou "workspace/old"

**Phrases qui ne doivent PAS trigger** (collision avec autres skills) :
- "vieux code" seul (trop générique)
- "ajouter une feature" (route vers `starting-a-new-feat`)
- "convertir" seul (peut être conversion de données)

**Recommandation** : valider la liste ci-dessus, l'inscrire en `SKILL.md`.

---

## 15. Validation Tech Lead requise

Avant de démarrer l'implémentation MVP (étape B du master prompt), valider explicitement :

1. [ ] La structure du pipeline 6 phases (§1.3) est correcte
2. [ ] Les formats `inventory-raw.json`, `inventory.json`, `inventory.md` (§2.3-§2.6) conviennent
3. [ ] Le format FEAT généré (§7) passera bien `/feat-validate`
4. [ ] Les 5 questions ouvertes §14 sont arbitrées (par défaut : A, A, B, B, OK skill list)
5. [ ] Le périmètre MVP §13.1 est accepté (pas de Phase 2/4 en MVP)
6. [ ] Aucune contrainte d'isolation §3.1 du master prompt n'est violée par cette spec

**Une fois validé**, je démarre l'étape B : implémentation dans l'ordre `language_signatures.yml` → `scan_legacy.py` → `inventory_builder.py` → CLI → agent `reverse-inventory` → commandes → agent `reverse-functional-extractor` → règle + loader + skill.

---

**FIN DU DESIGN DOC v1**
