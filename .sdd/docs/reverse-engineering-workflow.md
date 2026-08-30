---
title: Reverse Engineering Workflow — Design Doc Maître
status: Draft (en attente validation Tech Lead)
version: 0.7.2
created: 2026-06-10
updated: 2026-08-30
authors: SDD_Pro Architect
scope: workflow nouveau, isolé, cohabitant avec SDD_Pro v7.0.0+ sans édition de fichier existant
canonical_source: .sdd/rules/reverse-engineering.md
changelog:
  - v0.7.2 (2026-08-30) — **Deuxième passe de correctifs ciblés (suivi audit 2026-08-29).**
      Le rafraîchissement complet annoncé "NON fait" en v0.7.1 reste hors périmètre
      (chantier trop large pour une passe de suivi mécanique — cf. note en fin de
      ce changelog) ; corrigés cette fois : (a) décompte taxonomie 42 → **45**
      classes (3 classes ajoutées le 2026-08-30 par le remède reverse-DB du même
      audit — `OBJECT_KIND_MISMATCH`/`DB_PACK_MISSING`/`DB_CONTEXT_STALE`) ;
      (b) les 5 mentions codées en dur « Opus 4.8 » pour 3a/3c (§4.3 tableau
      barreaux, §4.5 récapitulatif modèles) remplacées par « tier `deep`, routé
      par complexité » — ces deux agents sont routés Sonnet/Opus par unité
      depuis l'ADR `governance-reverse-complexity-ladder` (2026-06-29), et le
      tableau affirmait encore un modèle fixe près de deux mois après ce
      changement ; `reverse-ui-extractor` reste correctement `deep` fixe (non
      routé, aucune correction nécessaire sur cette ligne au-delà du vocabulaire
      tier vs modèle).
  - v0.7.1 (2026-08-29) — **Correctifs de dérive documentaire (audit code-reverse, M7).**
      Ce document est resté figé au 2026-06-11 pendant que le module doublait de
      taille, tout en étant cité comme SSoT par la règle qui, elle, était à jour.
      Trois corrections ciblées : (a) le périmètre « 4 agents reverse » (effectif
      v0.3.0) est porté à **16** (10 code-reverse + 6 db-reverse, SSoT
      `loader.reverse.yml`) ; (b) la **copie dupliquée** de la taxonomie
      `[REVERSE_*]` en §10 — 16 classes gelées, contredisant la règle sur le TTL
      du lock et l'émetteur de `FEAT_VALIDATE_FAILED` — est remplacée par un
      renvoi vers la table canonique ; (c) note de préséance ci-dessous.
      **Rafraîchissement complet du contenu : NON fait** (hors périmètre de cette
      passe) — le corps décrit encore l'état de juin 2026 sur plusieurs chapitres.
  - v0.7.0 (2026-06-11) — **Escalier ascendant Phase 3 (ADR `governance-major-reverse-spec-ladder`)**.
      La Phase 3 mono-saut (agent `reverse-functional-extractor`, code→FEAT en un prompt — qui faisait
      baver l'altitude technique dans la FEAT métier) est **décomposée** en 3 barreaux ascendants :
      **3a `reverse-tech-analyst`** (code → analyse technique fidèle, `plans/{n}-{Name}.analysis.md`),
      **3b `reverse-us-writer`** (analyse → user stories par capability, `us/{n}-{m}-{Name}.md`),
      **3c `reverse-feat-composer`** (US → FEAT métier propre, plomberie démotée, `feats/{n}-{Name}.md`).
      `reverse-functional-extractor` est **décommissionné** (D2 no-dead-code, gate `reverse_smoke.check_no_dangling_spawn`).
      `/sdd-reverse` devient un **séquenceur** de `/sdd-reverse-analyze` + `/sdd-reverse-stories` + `/sdd-reverse-feat`.
      Fil de traçabilité FEAT→US→task→evidence (`check_ladder_traceability.py`, D3), confidence min-monotone
      ascendante (3c ≤ 3b ≤ 3a). Intent A (documentation legacy) forward-compatible B (rebuild via /sdd-full).
      (Audit 2026-06-11 : §4.3, roster modèles, mirror loader et exemples de lock
      ont été réécrits pour refléter l'escalier — plus de section décrivant
      `reverse-functional-extractor` comme agent vivant.)
  - v0.5.0 (2026-06-10) — **Refonte profondeur d'extraction (lots L0→L6)** suite audit CTO.
      L0 : code-graph symbole-level (`code_graph_builder.py` + `class_role_classifier.py`) —
        chaque classe classée par rôle (repository/service/dto/code-behind/controller/complex/…),
        evidence `units[].evidenceFiles` enrichie transitivement (page→behind→service→repo),
        fingerprint U-N pinné sur le seed (stabilité). Corrige « ne capture que la 1ère interface ».
      L1 : extraction technique profonde — `data_access_extractor.py` (SQL inline + procs DDL/calls +
        params), `config_extractor.py` (connection strings, secrets masqués), `dependency_inventory.py`
        (NuGet packages.config + .csproj PackageReference + Directory.Packages.props + assembly refs +
        bin DLLs), champs ORM remplis. Artefacts §5.6.
      L2 : `code_unit_detector.py` — unités pilotées par le code (controllers→api, modules backend
        orphelins→module). Backend/API-only passe de 0 unité → unités exploitables.
      L3 : `crosscutting_feats.py` + `generate_crosscutting_feats.py` — FEATs transversales
        déterministes « Librairies à installer » + « Base de données / procédures stockées /
        connection strings », conformes `validate_reverse_feat.py`.
      L4 : `ui_template_parser` — colonnes de grid (BoundField/TemplateField), contrôles ASPX
        (DropDownList/CheckBox/Radio/textarea/select/Image), data-binding (Eval/Bind/@Model),
        navTargets ; `css_palette_extractor` lit `<style>` inline + `style="…"`.
      L5 : `preallocate_feats.py` (pré-allocation déterministe → Phase 3 parallèle bornée, ADV-2
        relâché §8.2), `reverse_cache.py` (skip unités inchangées), `check_feat_completeness.py` +
        agent `reverse-completeness-reviewer` (revue back informational).
      L6 : orchestrateur `/sdd-reverse-full` industrialisé (préalloc→parallèle→crosscut→review),
        test round-trip de parité, INVARIANTS deepening_contracts. Isolation D4 préservée (smoke 13/13 — recompte audit 2026-06-11 MA-8, le registre `_ALL_CHECKS` a 13 checks).
  - v0.4.1 (2026-06-10) — Patch micro 4ème revue (ADV-23) : initialisation explicite `_allocatedNames: {}` + `_featAllocations: {}` à la création de `inventory.json` (§5.1) ; mode `--use-cache` (§4.1) doit vérifier `schemaVersion` ≥ 1 ET présence `_allocatedNames` sinon refresh forcé. Statement reviewer : **convergence stable, loop adversarial CLOS**.
  - v0.4.0 (2026-06-10) — Closure 3ème revue contradictoire (convergence). Patches micro :
      ADV-18 (§6 tableau inter-phases : `db-schema.json enrichi` stale → `db-schema.enrichment.json` + `db-schema.merged.json`) ;
      ADV-19 (§5.1 inventory.json exemple : ajout `_allocatedNames` pour cohérence avec §3.3) ;
      ADV-20 (§3.2 strip BOM UTF-8/UTF-16 dans normalisation bytes avant replace CRLF) ;
      ADV-22 (Annexe A : statement que `<!-- REVERSE-GATE -->` n'interfère pas avec parsing sections, test associé).
    Différé V2 :
      ADV-21 (désync `_allocatedNames` ↔ disque sur suppression manuelle FEAT, §15.4).
    Statement reviewer : "v0.3.0 prêt pour impl MVP après v0.4.0 léger" — convergence atteinte, pas de revue v4 prévue.
  - v0.3.0 (2026-06-10) — Integration 2ème revue contradictoire 8 ADV. Bloquants levés :
      ADV-17 (regression ADV-3 dans loader.reverse.yml §7.1 — writes corrigé `db-schema.enrichment.json`) ;
      ADV-13 (collision intra-run sur suggestedName — check étendu à _featAllocations du run + Names déjà alloués, §3.3).
    Corrections importantes :
      ADV-10 (psutil optionnel, fallback TTL seul, caveat Windows PID recycling documenté, §3.5) ;
      ADV-11 (fingerprint `core` basé sur hash bytes content + non sur LOC — stable cross-OS, §3.2) ;
      ADV-14 (test parité validate_reverse_feat vs validate_readiness + alarme drift, §12) ;
      ADV-16 (tests parité helpers locaux file_locks_local/atomic_write_local vs sdd_lib originaux, §12).
    Mitigation légère :
      ADV-15 (commentaire `<!-- REVERSE-GATE: confidence=... -->` dans FEAT reverse, parseable sans toucher /sdd-full, §3.3 + Annexe A).
    Différé V2 explicite :
      ADV-12 (type conflict merge_db_schema, §15.3).
  - v0.2.0 (2026-06-10) — Integration revue contradictoire 9 ADV. Corrections MVP critiques :
      ADV-5 (validate_reverse_feat.py séparé, §4.3) ;
      ADV-2 (lock élargi + TTL 30s + Phase 3 séquentielle, §3.5) ;
      ADV-3 (db-schema.enrichment.json séparé + merge_db_schema.py, §4.2) ;
      ADV-6 (gate /sdd-full sur reverse low + marker [REV] /sdd-status, §2 + §6) ;
      ADV-4 (sanitize Name avec check unicité + suffixe -Legacy, §3.3).
    Mitigations légères :
      ADV-1 (snapshot Phase 0 immuable + [REVERSE_INVENTORY_STALE] détaillé, §3.2) ;
      ADV-9 (feat.template.md dans loader.reverse.yml.reads + test absence, §4.3 + §7.1).
    Différé V2/V3 : ADV-7 (INVARIANTS.reverse.yml), ADV-8 (max_file_size_kb + Unicode) — voir §15.
  - v0.1.0 (2026-06-10) — Draft initial post master-prompt 2026-06-09 corrigé 2026-06-10.
---

# Reverse Engineering Workflow — Design Doc Maître

> ⚠️ **Préséance (audit 2026-08-29, M7)** — en cas de désaccord entre ce document
> et `.sdd/rules/reverse-engineering.md`, **la règle fait foi**. C'est elle que
> les agents chargent à l'exécution, elle qui est tenue à jour à chaque audit, et
> elle qui est verrouillée par des tests ; ce design doc est un **document de
> conception historique**, corrigé ponctuellement mais pas rafraîchi en continu.
> Il se décrivait lui-même comme la « SSoT » alors qu'il datait de 3 mois et
> contredisait la règle qui le citait — la relation est désormais explicite et
> dans l'autre sens.

> **Statut** : **v0.7.0 — implémenté** (escalier 3a/3b/3c livré, ~200 tests verts, smoke 13/13). L'historique Draft v0.4.x (4 revues adversariales, loop CLOS) est conservé dans le changelog frontmatter ci-dessus.
>
> **v0.4.0** clôt la 3ème revue contradictoire (`workspace/.sys/.validation/reverse-design-doc-adversarial-v3.md`) — 4 patches micro (ADV-18, 19, 20, 22) + 1 V2 (ADV-21).
>
> **v0.3.0** intègre les 8 attaques de la 2ème revue adversariale (`workspace/.sys/.validation/reverse-design-doc-adversarial-v2.md`) — 2 bloquants levés (ADV-17, ADV-13), 4 issues importantes corrigées (ADV-10, 11, 14, 16), 1 mitigation légère (ADV-15), 1 V2 (ADV-12).
>
> **v0.2.0** avait intégré les 9 attaques de la 1ère revue (`workspace/.sys/.validation/reverse-design-doc-adversarial.md`). Voir frontmatter `changelog` ci-dessus.
>
> **Référence prompts** : les agents `.claude/agents/reverse-*.md` + commandes `.claude/commands/sdd-reverse*.md` (le master prompt initial n'a jamais été archivé — pointeur retiré, audit 2026-06-11).
>
> **Principe directeur** : workflow reverse engineering pour SDD_Pro qui transforme un projet legacy déposé dans `workspace/old/{LegacyProject}/` en FEATs SDD_Pro standard consommables par `/sdd-full {n}` ou `/sdd-poc {n}` SANS modification du framework existant.

---

## TOC

- [§0 Précondition & hors-scope](#0-précondition--hors-scope)
- [§1 Vue d'ensemble — pipeline 7 phases](#1-vue-densemble--pipeline-7-phases)
- [§2 Workspace cible — arborescence](#2-workspace-cible--arborescence)
- [§3 Schéma d'ID `U-N` — stabilité + résolution](#3-schéma-did-u-n--stabilité--résolution)
- [§4 Schémas I/O par agent](#4-schémas-io-par-agent)
- [§5 Formats JSON des outputs Python déterministes](#5-formats-json-des-outputs-python-déterministes)
- [§6 Contrats inter-phases](#6-contrats-inter-phases)
- [§7 Mécanisme de découverte `loader.reverse.yml`](#7-mécanisme-de-découverte-loaderreverseyml)
- [§8 `language_signatures.yml` — schéma + valeurs initiales](#8-language_signaturesyml--schéma--valeurs-initiales)
- [§9 Confidence cap par langage + dégradation](#9-confidence-cap-par-langage--dégradation)
- [§10 Classification erreurs `[REVERSE_*]`](#10-classification-erreurs-reverse_)
- [§11 Exemple legacy fictif (5-10 fichiers)](#11-exemple-legacy-fictif-5-10-fichiers)
- [§12 Plan de tests](#12-plan-de-tests)
- [§13 Plan de livraison MVP / V2 / V3](#13-plan-de-livraison-mvp--v2--v3)
- [§14 Checklist auto-vérification](#14-checklist-auto-vérification)
- [§15 Mitigations V2/V3 — attaques différées](#15-mitigations-v2v3--attaques-différées)
- [Annexe A — Conformité SDD_Pro standard FEAT](#annexe-a--conformité-sdd_pro-standard-feat)
- [Annexe B — Isolation : fichiers framework intouchables](#annexe-b--isolation--fichiers-framework-intouchables)
- [Annexe C — Glossaire](#annexe-c--glossaire)

---

## §0 Précondition & hors-scope

**Précondition** : ce workflow opère sur **fichiers source lisibles** (ASPX, .cs, .java, .php, .pas/.dfm, .frm, templates HTML/Razor/Blade/JSP, SQL, CSS, JS, **.xaml**, etc.) déposés sous `workspace/old/{LegacyProject}/`.

**Hors-scope** :
- Reverse engineering d'**exécutables compilés sans source** (WPF/WinForms/Delphi/VB6 binaire-only) → palier V3, pipeline distinct (UI Automation + décompilation + capture vision). Si projet livré binaire-only : émettre `[REVERSE_BINARY_ONLY]` + STOP + escalade Tech Lead.

  > **Note WPF avec sources** (depuis 2026-06-10) : si les fichiers `.xaml` + `.xaml.cs` sont disponibles (extraits ou non-compilés), le workflow standard les supporte via la signature `wpf-xaml` (`language_signatures.yml`) et la famille `"wpf"` dans `ui_template_parser`. Cf. §4.4 et §8.2 pour le mapping XAML→HTML sémantique. Le cas binaire-only (`.exe` sans XAML extractible) reste hors-scope.

- Migration **runtime** ou **rejeu E2E** du legacy. Le workflow produit des FEATs descriptives ; la (ré)implémentation est ensuite faite par `/sdd-full {n}` via le pipeline SDD_Pro standard.
- Préservation **bit-à-bit** du look-and-feel : la Phase 4 UI produit une **interprétation sémantique** du legacy, pas un clone pixel-perfect.

---

## §1 Vue d'ensemble — pipeline 7 phases

```
Phase 0 [humain]    : dépôt code legacy → workspace/old/{LegacyProject}/
Phase 1 [scan]      : /sdd-reverse-inventory
                      → inventory.{md,json} (langages, pages, unités U-N)
                      → db-schema.{json,md} (entities + relations basique, D7)
Phase 2 [optionnel] : /sdd-reverse-audit
                      → tech-audit.md (archi, anti-patterns, deps EOL)
                      → enrichit db-schema (relations dérivées, index, contraintes)
Phase 3 [extract]   : /sdd-reverse {U-N}
                      → workspace/feats/{n}-{Name}.md
                      (1 unité U-N → 1 FEAT, evidence file:line, confidence cap)
Phase 4 [UI, V2]    : /sdd-reverse-ui {U-N}
                      → workspace/ui/{n}-{m}-{Name}.html
                      (1 unité → 1+ écrans HTML sémantique)
Phase 5 [humain]    : revue Tech Lead, ajustements designer optionnels
Phase 6 [migration] : /sdd-full {n} OU /sdd-poc {n}
                      → pipeline SDD_Pro EXISTANT, inchangé
```

**Granularité (D2)** : 1 FEAT = 1 unité fonctionnelle (intention utilisateur cohérente). Règles :
- 1 page legacy → 1 à 4 FEATs typiquement
- 1 grid CRUD → 1 FEAT
- 1 menu navigation → 1 FEAT
- 1 wizard multi-étapes → 1 FEAT
- 1 modale de confirmation isolée → 0 FEAT (intégrée à la FEAT parente)

**Unités pilotées par le code (L2, V2 2026-06-10)** : les unités ne proviennent
plus uniquement des pages UI. `code_unit_detector.py` ajoute, après les unités
de page :
- 1 unité `kind: api` par **controller** MVC/Web API (la tranche
  controller→service→repository est capturée via le code-graph) ;
- 1 unité `kind: module` par **module backend orphelin** (services/repositories
  non atteints depuis une page ou un controller — jobs, tâches planifiées,
  services domaine), groupés par namespace (sinon dossier racine).

Conséquence : une appli **backend/API-only** (zéro page UI) produit désormais
des unités exploitables — auparavant elle en produisait **zéro**. Les types
support seuls (DTO/entity/interface/enum/helper statique) ne forment jamais une
unité ; ils sont portés par `units[].classes`.

**Reprenabilité** : chaque phase est atomique. Re-lancer une phase écrase son output (pas de merge). L'état est porté par les artefacts disque (`inventory.json`, `db-schema.json`, etc.), pas par un session state.

---

## §2 Workspace cible — arborescence

```
workspace/
├── old/                                    # Phase 0 : dépôt humain
│   └── {LegacyProject}/
│       ├── {fichiers legacy bruts}
│       └── .sys/                           # Artefacts reverse, isolés
│           ├── inventory.md                # Phase 1, lecture humaine
│           ├── inventory.json              # Phase 1, machine (source de vérité)
│           ├── db-schema.md                # Phase 1, lecture humaine
│           ├── db-schema.json              # Phase 1, machine (entities)
│           ├── tech-audit.md               # Phase 2, optionnel
│           ├── deps-graph.json             # Phase 2, optionnel
│           ├── language-detected.json      # Phase 1, contrat scan
│           └── modules/
│               └── {ModuleName}/
│                   └── extraction.md       # Phase 3, log par unité
├── input/                                  # Phase 3/4 : sortie reverse
│   ├── feats/{n}-{Name}.md                 # Phase 3
│   └── ui/{n}-{m}-{Name}.html              # Phase 4
└── output/                                 # Phase 6 : SDD_Pro standard
    └── {…inchangé…}
```

**Invariants arborescence** :
- `.sys/` sous `workspace/old/{P}/` est **inscriptible uniquement** par les agents reverse + scripts `sdd_reverse_scripts/`.
- `workspace/feats/` et `workspace/ui/` partagent le namespace avec `/feat-generate` standard ; les FEATs reverse sont distinguables :
  - **À l'écriture** : frontmatter `generated-by: sdd-reverse`
  - **À l'affichage** (`/sdd-status`, console web) : marker `[REV]` (FEAT reverse `high`) ou `[REV⚠️]` (FEAT reverse `medium`/`low`) — voir §6 contrat outils en aval
  - **Au lancement `/sdd-full`** : gate optionnelle (corrigé ADV-6) — voir §6
- Aucun fichier n'est écrit en dehors de `workspace/old/{P}/.sys/` ou `workspace/{feats,ui}/`.

**Artefacts `.sys/` (récap v0.2.0)** :
| Fichier | Producteur | Phase | Note |
|---|---|---|---|
| `inventory.{md,json}` | `reverse-inventory` | 1 | Source de vérité U-N |
| `db-schema.{json,md}` | `db_schema_extractor.py` | 1 | Base, jamais modifiée par Phase 2 (ADV-3) |
| `db-schema.enrichment.json` | `reverse-tech-auditor` | 2 (opt) | Additions seulement, écrit en fichier séparé (ADV-3) |
| `db-schema.merged.json` | `merge_db_schema.py` | 2 (opt) | Union déterministe base + enrichment |
| `tech-audit.md` | `reverse-tech-auditor` | 2 (opt) | Informational |
| `deps-graph.json` | `deps_graph_builder.py` | 2 (opt) | Audit |
| `language-detected.json` | `scan_legacy.py` | 1 | Caps confidence appliqués |
| `modules/{Mod}/extraction.md` | `reverse-feat-composer` (3c) | 3 | Log d'extraction par unité |

---

## §3 Schéma d'ID `U-N` — stabilité + résolution

### 3.1 Allocation

- `U-N` (Unit) : identifiant **stable** d'une unité fonctionnelle candidate produite par la Phase 1.
- `N` ∈ `ℕ⁺`, séquentiel à partir de `1`, alloué par `inventory_builder.py` lors du premier scan.
- Stocké dans `inventory.json` → `units[].id` (string `"U-1"`, `"U-2"`, …).

### 3.2 Stabilité cross-runs (durci v0.2.0 — ADV-1)

**Précondition Phase 0 — snapshot immuable** : le contenu de `workspace/old/{P}/` est considéré **figé** entre la Phase 1 et la Phase 6. Toute modification du legacy entre deux phases invalide les fingerprints et impose un re-scan.

- Re-lancer `/sdd-reverse-inventory` sur le **même état du legacy** doit produire **les mêmes IDs** pour les mêmes unités.
- Mécanisme robuste (v0.3.0 — corrigé ADV-11) : `inventory_builder.py` calcule deux fingerprints par unité, basés sur le **contenu** des fichiers (insensible CRLF/LF) :
  - `unit_fingerprint_full = sha256(sorted(evidence_paths) + label_normalized)` — strict (paths uniquement, stable)
  - `unit_fingerprint_core = sha256(sorted(top3_distinctive_evidence_paths) + label_normalized)` — résilient aux renommages partiels
  - **Sélection des "top-3 distinctifs"** : critères déterministes et cross-OS-stables (corrigé ADV-11 — n'utilise PAS LOC qui dépend des line endings) :
    1. Score primaire : `evidence_pattern.weight` cumulé sur le fichier (depuis `language_signatures.yml`)
    2. Tie-break 1 : `len(content_bytes_normalized)` où la normalisation applique successivement (corrigé ADV-20) :
       ```python
       def normalize_bytes(file_bytes: bytes) -> bytes:
           # Strip BOMs (Visual Studio sur Windows émet UTF-8 BOM systématiquement)
           for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"):  # UTF-8, UTF-16-LE, UTF-16-BE
               if file_bytes.startswith(bom):
                   file_bytes = file_bytes[len(bom):]
                   break
           # Normalize EOL (CRLF/LF/CR → LF)
           file_bytes = file_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
           return file_bytes
       content_bytes_normalized = normalize_bytes(file_bytes)
       ```
    3. Tie-break 2 : path lexicographique (`sorted()`)
  - Note : la normalisation EOL + BOM strip garantit qu'un dev Windows (Visual Studio + BOM + CRLF), un dev Linux (LF), et un dev macOS legacy (CR seul) clonant le même legacy obtiennent les mêmes fingerprints — invariant critique pour l'idempotence cross-machine.
- Résolution `U-N` :
  - Match `full` exact → mapping conservé
  - Sinon match `core` exact → mapping conservé (la classe `[REVERSE_UNIT_RENAMED]` a été retirée — audit MA-7, aucun émetteur ; ré-ajouter classe + émetteur ENSEMBLE si ce WARN est câblé un jour)
  - Sinon → nouvelle unité, `N = max(existing) + 1`
- Unité disparue (les deux fingerprints absents du nouveau scan) → marquée `status: "stale"` dans `_fingerprintMap`, ID jamais réutilisé.

**Détection legacy modifié** (`[REVERSE_INVENTORY_STALE]`) :
- `inventory_builder.py` enregistre `legacyMtimeMax` = max(`mtime(f)` pour f dans tous les fichiers scannés) au moment du scan, dans `inventory.json.legacyMtimeMax`.
- À chaque invocation Phase 3 (`/sdd-reverse {U-N}`), comparer `legacyMtimeMax` au `mtime` actuel des fichiers `units[U-N].evidenceFiles`.
- Si mtime actuel > `legacyMtimeMax` (sur au moins 1 fichier) → émettre WARN `[REVERSE_INVENTORY_STALE]` + suggérer `/sdd-reverse-inventory --refresh`.

### 3.3 Résolution `/sdd-reverse {U-N}` → `{n}-{Name}.md` (durci v0.2.0 — ADV-4)

```
/sdd-reverse U-3
    │
    ├─ acquire lock workspace/feats/.alloc.lock (TTL 30s, voir §3.5)
    │
    ├─ read inventory.json → units[id="U-3"]
    │     → { id: "U-3", label: "Liste utilisateurs", language: "aspx-webforms",
    │         evidence_files: [...], suggested_name: "UsersList", confidence_estimate: "high" }
    │
    ├─ if _featAllocations[U-3] existe :
    │     n = _featAllocations[U-3]            # idempotence : même n à chaque re-run
    │  else :
    │     n = next_free_feat_number(workspace/feats/)  # max({n} existants) + 1
    │
    ├─ Name_base = sanitize(suggested_name)    # PascalCase, no accents, hyphens
    │
    ├─ Name = resolve_name_collision(
    │           candidate=Name_base,
    │           disk_paths=glob("workspace/feats/*.md"),
    │           in_flight_allocations=inventory.json._featAllocations,    # ADV-13
    │           in_flight_names=inventory.json._allocatedNames,           # ADV-13
    │           source_unit=U-3
    │         )
    │     # Check d'unicité étendu (corrigé ADV-13) :
    │     # 1. Vs disque : si {*}-{Name_base}.md existe déjà
    │     #    - Si la FEAT existante a generated-by: sdd-reverse ET source-unit == current U-N
    │     #      → réutiliser (idempotence re-run)
    │     #    - Sinon → suffixer "-Legacy", puis "-Legacy-{U-N}" si encore collision
    │     # 2. Vs in-flight (ADV-13) : si Name_base figure déjà dans _allocatedNames du même run
    │     #    (ex. inventory contient U-3.suggestedName="Login" ET U-7.suggestedName="Login"),
    │     #    alors la seconde unité résolue dans le même run reçoit "Login-Legacy-U-7"
    │     #    (déterministe : index U-N dans le suffixe garantit unicité absolue intra-run).
    │     # 3. Émettre INFO [REVERSE_NAME_COLLISION] avec champ `collision_source` ∈
    │     #    {"disk_human", "disk_reverse", "in_flight_intra_run"}.
    │
    ├─ write workspace/feats/{n}-{Name}.md
    │   frontmatter : source-unit: U-3, generated-by: sdd-reverse, confidence: ...
    │   body header : <!-- REVERSE-GATE: confidence={C} ; allow-sdd-full={true if C==high else false} -->
    │                 (ADV-15 — parseable par tout outil aval sans toucher /sdd-full)
    │
    ├─ update inventory.json._featAllocations[U-3] = n
    ├─ update inventory.json._allocatedNames[Name] = U-3    # ADV-13
    │
    └─ release lock
```

**Invariants ADV-4 + ADV-13** :
- Une FEAT humaine `3-Login.md` et une FEAT reverse `6-Login-Legacy.md` peuvent cohabiter sans ambiguïté visuelle.
- Deux unités intra-run avec même `suggestedName` produisent des fichiers distincts : `6-Login.md` (U-3, premier vu) et `7-Login-Legacy-U-7.md` (U-7, second vu). Ordre déterministe = ordre des `U-N` dans `inventory.json.units[]`.
- `/sdd-status` distingue FEAT humaine/reverse via le marker `[REV]` (voir §6).
- L'unicité `Name` est vérifiée sur 3 axes : disque, allocations in-flight du run, source U-N. Pas de collision possible.

**ADV-15 — REVERSE-GATE comment** : tout outil aval (script CI, `/sdd-full` futur amélioré, console web V2) peut parser cette ligne sans lire le frontmatter complet :
```html
<!-- REVERSE-GATE: confidence=low ; allow-sdd-full=false ; reason=feat_validate_failed_3_iters -->
```
- `confidence=high` → `allow-sdd-full=true` (déclaratif, source de vérité = frontmatter `confidence`)
- `confidence=medium|low` → `allow-sdd-full=false` (revue humaine obligatoire)
- `reason` (optionnel) : motif machine-lisible si dégradation auto (ex. `feat_validate_failed_3_iters`, `db_schema_degraded`)
- `check_reverse_feat_for_full.py` lit cette ligne en priorité (plus rapide que parser tout le frontmatter YAML).

### 3.4 Relation `{n}` FEAT ↔ `{n}-{m}` UI

- `{n}` = numéro de FEAT (alloué Phase 3, croissant à partir du dernier `{n}` libre)
- `{m}` = index d'écran à l'intérieur d'une FEAT (1, 2, 3…)
- Une FEAT a typiquement 1 écran principal (`{n}-1-{Name}.html`) + 0..N écrans secondaires (modales, étapes wizard)
- `/sdd-reverse-ui U-3` produit les fichiers HTML pour TOUS les écrans de la FEAT correspondante à U-3 (déterminé par l'agent extracteur sur la base de l'evidence)

### 3.5 Garanties (durci v0.2.0 — ADV-2)

- **Aucun ré-arrangement** : `U-N` n'est jamais renuméroté.

- **Phase 3 : parallèle borné après pré-allocation (L5), séquentiel strict sinon** (M13 — doc alignée 2026-06-10 sur `rules/reverse-engineering.md §8`) : après `preallocate_feats.py` (STEP 2.5 de `/sdd-reverse-full`), chaque unité a son `(n, Name)` figé et écrit un fichier disjoint sans lock → invocations `/sdd-reverse {U-N}` parallèles-safe (borne `--max-parallel`, défaut 3). SANS pré-allocation, mode legacy séquentiel strict (ADV-2) : le second `/sdd-reverse` émet `[REVERSE_LOCK_HELD]` (TTL 1800 s).

- **Lock élargi (couverture full transaction)** : le lock `workspace/feats/.alloc.lock` couvre **toute la transaction** (corrigé ADV-2) :
  ```
  acquire lock (O_EXCL, contenu = {agent_id, pid, ts_unix})
    │
    ├─ READ inventory.json → _featAllocations + units
    ├─ COMPUTE n (idempotent ou next_free)
    ├─ COMPUTE Name (anti-collision §3.3)
    ├─ WRITE workspace/feats/{n}-{Name}.md (atomic via .sddtmp + os.replace)
    ├─ UPDATE inventory.json._featAllocations[U-N] = n (atomic write)
    │
  release lock
  ```

- **TTL + recovery stale** :
  - TTL : 30 secondes (cohérent avec `ownership.md §4` LibName lock)
  - Lock > 30s → considéré stale, écrasé (recovery crash agent ou interruption)
  - Lock < 30s avec autre `agent_id` → STOP + ERROR `[REVERSE_LOCK_HELD]`
  - Lock < 30s avec même `agent_id` → re-entrant, continuer (idempotence retry)
  - Implémentation : pattern identique à `sdd_lib.file_locks` (mais dupliqué dans `sdd_reverse/file_locks_local.py` pour isolation, voir §6 contrats).

- **Atomic write `inventory.json`** : mise à jour via helper local `sdd_reverse/atomic_write_local.py` (`.sddtmp` + `fsync` + `os.replace`). Crash mid-write = pas de corruption (le fichier original reste intact).

- **Idempotence** : `/sdd-reverse U-3` ré-exécuté écrase `workspace/feats/{n}-{Name}.md` ssi le mapping `U-3 → n` est connu dans `inventory.json._featAllocations[U-3]`. Le `Name` peut différer si le legacy a été retouché (warn `[REVERSE_INVENTORY_STALE]`).

- **Format du lock file** :
  ```json
  {"agent_id": "reverse-tech-analyst-U-3", "pid": 12345, "ts_unix": 1717987200, "host": "abc-laptop"}
  ```
- **Recovery stratégie (corrigé ADV-10)** :
  - **TTL 30s est la protection primaire et toujours active** (ne dépend d'aucune lib externe)
  - `pid` check est une **optimisation opportuniste désactivable** :
    - Si `psutil` (ou équivalent) installé → check si process actif avant d'attendre la TTL (UX meilleure : détection lock orphelin instantanée)
    - Si `psutil` absent → skip le check, fallback TTL silencieux (pas une ERROR, juste pas d'optim)
    - **Aucune dépendance dure sur `psutil`** dans le `requirements.txt` du module reverse (D4 isolation respectée)
  - **Caveat Windows PID recycling** (documenté) : sur Windows, les PIDs sont recyclés rapidement. Un PID qui semble actif peut être un process tiers réutilisant un PID libéré. Mitigations :
    1. Le check inclut `host` : si lock vient d'un autre hôte (rare sur dev local, possible si workspace partagé), on tombe en TTL only
    2. Le pid check est borné : si "process actif" mais aucune activité fichier de notre lock depuis > 10s, on traite comme orphelin
    3. **Source de vérité reste TTL** : pid est secondaire, TTL est l'autorité finale
  - **Cross-machine** : si `workspace/feats/` est partagé NFS/Dropbox et que deux machines lancent `/sdd-reverse` simultanément, les pid checks divergent — TTL reste l'arbitre. Recommandation : ne PAS lancer reverse en parallèle multi-machine (cf. §3.5 "Phase 3 séquentielle stricte").

---

## §4 Schémas I/O par agent

> **Périmètre (corrigé audit 2026-08-29, M7)** : ce chapitre décrivait « 4 agents »,
> l'effectif de la v0.3.0. Le module en compte **16** (`loader.reverse.yml`, SSoT) :
> 10 côté code-reverse et 6 côté db-reverse. Les schémas détaillés ci-dessous ne
> couvrent que les agents historiques ; pour les autres, le manifeste
> `loader.reverse.yml` est la référence reads/writes.

### 4.1 `reverse-inventory`

**Frontmatter** (`.claude/agents/reverse-inventory.md`) :
```yaml
---
name: reverse-inventory
description: Cartographie d'un projet legacy déposé dans workspace/old/{P}/. Détecte langages/frameworks, énumère les pages, identifie les unités fonctionnelles candidates (U-N), extrait un schéma DB basique. Produit inventory.{md,json} + db-schema.{json,md} + language-detected.json.
model: claude-sonnet-4-6
tools: Read, Write, Glob, Grep, Bash
---
```

**Inputs (Read)** :
- `workspace/old/{P}/**` (récursif, exclusions auto : `.git/`, `node_modules/`, `bin/`, `obj/`, `__pycache__/`, fichiers binaires connus)
- `.sdd/python/sdd_reverse/language_signatures.yml`
- `workspace/old/{P}/.sys/inventory.json` (si existant, pour stabilité U-N)

**Outputs (Write)** :
- `workspace/old/{P}/.sys/inventory.md` (FR, lecture humaine — résumé exécutif + tableau unités)
- `workspace/old/{P}/.sys/inventory.json` (machine, schéma §5.1)
- `workspace/old/{P}/.sys/db-schema.json` (machine, schéma §5.2)
- `workspace/old/{P}/.sys/db-schema.md` (FR, lecture humaine)
- `workspace/old/{P}/.sys/language-detected.json` (schéma §5.3)

**Délégation aux scripts déterministes** :
- L'agent invoque `python .sdd/python/sdd_reverse_scripts/reverse_inventory.py --project {P}` qui orchestre `scan_legacy.py`, `inventory_builder.py`, `ui_unit_detector.py`, `db_schema_extractor.py` (0 token).
- L'agent **synthétise** le markdown FR à partir des JSON déterministes (valeur ajoutée LLM : narratif lisible, regroupements sémantiques, signalement des zones suspectes).

**Mode skippable (durci v0.4.1 — ADV-23)** : si `inventory.json` existe et flag `--use-cache`, l'agent saute le scan ET ne régénère que le `.md`, **sous conditions strictes** :
1. `schemaVersion >= 1` (rejet caches pre-v0.4.0)
2. Clés `_allocatedNames` ET `_featAllocations` présentes (même si `{}` vides)
3. `legacyMtimeMax` présent

Si une condition échoue → `--use-cache` est **silencieusement ignoré**, scan complet relancé, et émission INFO `[REVERSE_INVENTORY_SCHEMA_STALE]` dans le rapport pour signaler le refresh forcé.

Cette gate empêche un cache de version antérieure de cascader des `KeyError` en Phase 3 (`resolve_name_collision` cherchant `_allocatedNames` absent du cache).

### 4.2 `reverse-tech-auditor`

**Frontmatter** (`.claude/agents/reverse-tech-auditor.md`) :
```yaml
---
name: reverse-tech-auditor
description: Audit architecture/anti-patterns/dépendances EOL d'un projet legacy déjà inventoryé. Enrichit db-schema avec relations dérivées, index, contraintes. Output informational, non consommé par /sdd-full.
model: claude-sonnet-4-6
tools: Read, Write, Glob, Grep, Bash
---
```

**Inputs (Read)** :
- `workspace/old/{P}/.sys/inventory.json`
- `workspace/old/{P}/.sys/db-schema.json`
- `workspace/old/{P}/**` (sélectif sur les entry points / fichiers config / SQL)

**Outputs (Write)** :
- `workspace/old/{P}/.sys/tech-audit.md` (FR)
- `workspace/old/{P}/.sys/deps-graph.json` (schéma §5.4)
- `workspace/old/{P}/.sys/db-schema.enrichment.json` (**fichier séparé** — corrigé ADV-3)

**Stratégie d'enrichissement durcie (ADV-3)** : `reverse-tech-auditor` est un LLM Sonnet 4.6 avec tool `Write`. Pour éviter toute corruption silencieuse de `db-schema.json` (suppression d'entities, merge incorrect), la séparation suivante est imposée :

1. L'agent écrit ses additions dans un fichier **distinct** : `db-schema.enrichment.json` (relations dérivées, index, contraintes nouvelles, fields manquants). Il **ne touche jamais** `db-schema.json`.
2. Schéma `db-schema.enrichment.json` (mode additif strict) :
   ```json
   {
     "schemaVersion": 1,
     "enrichmentDate": "2026-06-10T15:30:00Z",
     "addedRelations": [...],
     "addedIndexes": [...],
     "addedConstraints": [...],
     "addedFields": [ { "entity": "<name>", "field": {...} } ]
   }
   ```
3. Un script déterministe `sdd_reverse/merge_db_schema.py` applique l'union :
   ```bash
   python .sdd/python/sdd_reverse/merge_db_schema.py \
     --base workspace/old/{P}/.sys/db-schema.json \
     --enrichment workspace/old/{P}/.sys/db-schema.enrichment.json \
     --output workspace/old/{P}/.sys/db-schema.merged.json
   ```
4. Règles de merge (script déterministe, 0 token) :
   - Union stricte : `keys(merged) ⊇ keys(base)` (assertion d'intégrité avant write)
   - Conflict resolution : si `addedRelation` réfère une entity absente du base → ERROR `[REVERSE_ENRICHMENT_INVALID]`, ne pas merger
   - Aucune suppression possible (le script n'a pas d'opération `remove`)
5. La Phase 3 (agent extractor) lit **`db-schema.merged.json` si présent**, sinon **`db-schema.json`** (base). Jamais `enrichment.json` seul.

**Skippable** : oui via `--skip-audit` côté commande `/sdd-reverse-full`. La Phase 3 n'en dépend PAS (lit base seule si merge non fait).

### 4.3 Phase 3 — escalier ascendant 3a → 3b → 3c (réécrit audit 2026-06-11, remplace l'ex-`reverse-functional-extractor`)

> Section réécrite : l'agent mono-saut `reverse-functional-extractor` est
> **décommissionné** (ADR `governance-major-reverse-spec-ladder`, D2
> no-dead-code). La Phase 3 est un **escalier de 3 agents**, séquencé par
> `/sdd-reverse {U-N}` (qui ne spawn rien lui-même — no-spawn §9) :

| Barreau | Agent (`.claude/agents/`) | Modèle | Input principal | Output |
|---|---|---|---|---|
| **3a** | `reverse-tech-analyst.md` | tier `deep` **routé par complexité** (`code_unit_complexity.py`, ADR `governance-reverse-complexity-ladder` 2026-06-29 — Sonnet si unité simple, Opus sinon) | `units[U-N].evidenceFiles` + db-schema (+ tech-audit opt.) | `workspace/plans/{n}-{Name}.analysis.md` (analyse technique fidèle, tasks T-N, evidence file:line) |
| **3b** | `reverse-us-writer.md` | Sonnet 4.6 (downgrade audité 2026-06-11) | analyse 3a | `workspace/us/{n}-{m}-{Name}.md` (US par capability, AC → covers T-N, ligne header `Confidence:`) |
| **3c** | `reverse-feat-composer.md` | tier `deep` **routé par complexité** (même ADR — Sonnet si unité simple, Opus sinon) | US 3b + analyse 3a | `workspace/feats/{n}-{Name}.md` (FEAT métier, plomberie démotée, REVERSE-GATE) |

**Invariants de l'escalier** :
- Confidence **min-monotone ascendante** : `conf(3c) ≤ min(conf(US 3b)) ≤ conf(3a)`
  — enforced par `check_ladder_traceability.py` (frontmatter/ligne header +
  fallback commentaire de provenance pour les US pré-fix M2).
- Fil de traçabilité descendant D3 : FEAT → US#AC → tasks T-N → evidence
  file:line (gaps = `[REVERSE_LADDER_TRACEABILITY_GAP]`, informational).
- Templates locaux isolés ADV-9 (`analysis/us/feat.reverse.template.md` dans
  `sdd_reverse/` — couverts par `reverse_smoke.check_template_isolated`).
- Lecture sélective stricte : seul **3a** lit le code legacy
  (`evidenceFiles`) ; 3b/3c ne relisent JAMAIS le legacy (forbidden_reads,
  cf. `loader.reverse.yml`).

**Détail prompts** : les frontmatters/steps exacts vivent dans les 3 fichiers
agents (SSoT) — ce design doc ne les duplique plus.

**Outputs (Write)** :
- 3a : `workspace/plans/{n}-{Name}.analysis.md`
- 3b : `workspace/us/{n}-{m}-{Name}.md` (1..5 US)
- 3c : `workspace/feats/{n}-{Name}.md` + `workspace/old/{P}/.sys/modules/{ModuleName}/extraction.md` (log d'extraction)

**Itération validation — barreau 3c (corrigé ADV-5)** : `validate_readiness.py` (SDD_Pro standard) checke `stack.md` actif, `Parent FEAT hash`, mockups — **absents en Phase 3** (le Tech Lead édite `stack.md` seulement Phase 5). L'utiliser ferait sortir 100% des FEATs reverse en `confidence: low` artificiel.

**Solution** : script déterministe dédié `sdd_reverse_scripts/validate_reverse_feat.py` qui valide UNIQUEMENT la structure FEAT (indépendant du pipeline standard) :

```bash
python .sdd/python/sdd_reverse_scripts/validate_reverse_feat.py \
  --feat-path workspace/feats/{n}-{Name}.md \
  --json
```

**Checks** (déterministes, 0 token) :
1. Frontmatter YAML parsable + clés requises (`generated-by: sdd-reverse`, `legacy-sources`, `confidence`, `extraction-date`, `language-detected`, `source-unit`)
2. Enum `confidence` ∈ {`high`, `medium`, `low`} strict (rejet `medium-high`, etc.)
3. Sections obligatoires présentes (ordre figé) : `## Actors`, `## Functional Needs`, `## Functional Deliverables`, `## Business Rules`, `## Acceptance Criteria`, `## Project Config`
4. IDs stables non-réordonnés : `SFD-N`, `FD-N`, `BR-N`, `AC-N` (séquentiels ou avec trous, jamais réordonnés)
5. AC au format Given/When/Then (regex stricte multi-lignes acceptée)
6. Chaque item SFD/FD/BR/AC porte `<!-- evidence: path:Lstart-Lend -->` et `<!-- confidence: ... -->`
7. Bannière `⚠️` présente si `confidence: low` (frontmatter)

**Boucle d'itération** :
```
loop (max 3):
  write FEAT
  python .sdd/python/sdd_reverse_scripts/validate_reverse_feat.py --feat-path ... --json
  if exit 0: break
  else: read errors JSON (champ `errors[]`), corriger FEAT, iter++

if iter == 3 and exit != 0:
  set confidence: low in frontmatter
  prepend banner "⚠️ FEAT n'a pas passé validate_reverse_feat après 3 itérations — revue humaine requise"
  emit [REVERSE_FEAT_VALIDATE_FAILED]
```

**Distinction nette avec `/feat-validate` standard** : `/feat-validate {n}` (SDD_Pro) reste exécutable manuellement Phase 5 après que le Tech Lead a complété `## Project Config` et déposé les mockups UI. Il sert de gate avant `/sdd-full`. Le script reverse est antérieur à cette étape.

### 4.4 `reverse-ui-extractor`

**Frontmatter** (`.claude/agents/reverse-ui-extractor.md`) :
```yaml
---
name: reverse-ui-extractor
description: Pour UNE unité U-N donnée, lit les templates legacy + CSS + le FEAT déjà produit, et synthétise 1 à N écrans HTML sémantiques préservant la structure visuelle legacy (sans clonage pixel-perfect).
model: claude-opus-4-8
tools: Read, Write, Edit, Glob, Grep, Bash
---
```

**Inputs (Read)** :
- `workspace/old/{P}/.sys/inventory.json` → `units[id={U-N}]`
- `workspace/old/{P}/{template_files, css_files}` (sélectif)
- `workspace/feats/{n}-{Name}.md` (résultat Phase 3, contrat sémantique)

**Outputs (Write)** :
- `workspace/ui/{n}-{m}-{Name}.html` (1..N fichiers, où `m` = index d'écran)

**Délégation déterministe** :
- `css_palette_extractor.py` (palette/fonts/spacings)
- `ui_template_parser.py` (pré-extraction structure)
- L'agent synthétise un HTML sémantique propre (semantic tags, accessible markup, CSS vars).

#### 4.4.bis Mapping XAML → HTML sémantique (WPF, depuis 2026-06-10)

Les fichiers `.xaml` (WPF Window / Page / UserControl) sont traités par la
**famille `"wpf"`** de `ui_template_parser._parse_xaml_template`. Le mapping
suit la même doctrine que les autres familles : **sémantique, pas pixel-perfect**.

Le parser produit la même structure de sortie que pour ASPX/JSP/Blade
(`{forms[], elements[], links[], grids[]}`), avec un champ supplémentaire
`wpf_control` qui trace le contrôle XAML d'origine pour l'agent en aval.

| Contrôle XAML | Élément HTML5 | Champ extrait |
|---|---|---|
| `<Window>` / `<Page>` / `<UserControl>` | racine fichier (1 `form` record) | `wpf_root` |
| `<TextBox x:Name="..." Text="...">` | `<input type="text">` | `id`, `value`, `placeholder` |
| `<PasswordBox x:Name="...">` | `<input type="password">` | `id` |
| `<CheckBox Content="..." IsChecked="...">` | `<input type="checkbox"><label>` | `label`, `checked` |
| `<RadioButton GroupName="..." IsChecked="...">` | `<input type="radio">` | `group`, `checked` |
| `<ComboBox ItemsSource="{Binding ...}">` | `<select>` | `items_source` |
| `<Button Content="..." Click="..." Command="...">` | `<button onclick="...">` | `text`, `on_click`, `command` (MVVM) |
| `<Hyperlink NavigateUri="...">` | `<a href="...">` | `href`, `text` |
| `<TextBlock Text="...">` | `<span>` / `<p>` | `text`, kind=`"text"` |
| `<Label Content="..." Target="{Binding ElementName=...}">` | `<label for="...">` | associée via `Target` ElementName |
| `<DataGrid ItemsSource="...">` | `<table>` | grid, `items_source` |
| `<ListView>` / `<ListBox>` / `<ItemsControl>` | `<ul>` / `<table>` | grid |
| `<TreeView>` | `<ul>` (arborescence) | grid |
| `<Image Source="...">` | `<img src="...">` | — |

**Layout containers délibérément non mappés** :
`<Grid>`, `<StackPanel>`, `<DockPanel>`, `<Canvas>`, `<WrapPanel>`. L'agent
`reverse-ui-extractor` décide de la stratégie de layout finale en fonction du
design system cible (Bootstrap grid, CSS grid, flex, etc.) — figer un mapping
ici contraindrait inutilement le rendu HTML.

**Filtrage layout / entry-point** (`ui_unit_detector._classify_page`) :
- `App.xaml` (ou tout XAML avec `<Application>` racine) → kind=`"layout"`, **filtré**.
- Tout fichier XAML avec **uniquement** `<ResourceDictionary>` racine (thèmes,
  styles) → kind=`"layout"`, **filtré**.
- `<Window>`, `<Page>`, `<UserControl>` → candidats à unité fonctionnelle
  (kind = `form` / `grid` / `wizard` / `page` selon contenu).

**Fidélité attendue** :

| Cas | Fidélité estimée |
|---|---|
| `<TextBox>`, `<Button>`, `<PasswordBox>` (contrôles standards) | **95%** |
| `<DataGrid>` avec colonnes Header/Binding simples | **80%** |
| Layout `<Grid>` avec `RowDefinition` / `ColumnDefinition` | ~**70%** (agent rebuild via CSS grid) |
| `<Style>` / `<ControlTemplate>` cascadant | ~**40%** (templates custom non préservés) |
| Bindings `{Binding ...}` MVVM | préservés sous forme de `items_source` / `command` (l'agent décide quoi en faire) |

**Code-behind discovery** : pour chaque `.xaml`, `_build_pages_list` cherche
`*.xaml.cs` (C#) ou `*.xaml.vb` (VB.NET) en companion et le lie via
`codeBehindPath` dans `inventory.json`.

**Cas hors-scope (rappel)** : `.exe` WPF binaire-only — il faut décompiler
(ILSpy/dotPeek) et extraire le BAML (`baml2xml`) **avant** de déposer les
sources sous `workspace/old/{P}/`. Le workflow ne fait pas cette
décompilation lui-même (palier V3, §13.3).

### 4.5 Récapitulatif modèles

| Agent | Modèle | Phase | Mode |
|---|---|---|---|
| `reverse-inventory` | Sonnet 4.6 | 1 | Synthèse + délégation scripts |
| `reverse-tech-auditor` | Sonnet 4.6 | 2 (opt) | Audit, informational |
| `reverse-tech-analyst` (3a) | tier `deep`, routé par complexité (ADR 2026-06-29) | 3 | Analyse technique fidèle, anti-hallucination strict |
| `reverse-us-writer` (3b) | Sonnet 4.6 | 3 | Altitude-lift US (jamais de lecture code legacy) |
| `reverse-feat-composer` (3c) | tier `deep`, routé par complexité (ADR 2026-06-29) | 3 | Composition FEAT métier, plomberie démotée |
| `reverse-ui-extractor` | tier `deep` (fixe, non routé) | 4 (V2) | Génération HTML sémantique |

---

## §5 Formats JSON des outputs Python déterministes

### 5.1 `inventory.json`

```json
{
  "schemaVersion": 1,
  "project": "LegacyProject",
  "scanDate": "2026-06-10T14:32:18Z",
  "scanDurationMs": 4250,
  "languagesDetected": [
    { "id": "aspx-webforms", "label": "ASP.NET WebForms", "confidence": "high", "filesCount": 23, "locTotal": 5400 },
    { "id": "csharp", "label": "C#", "confidence": "high", "filesCount": 31, "locTotal": 8200 }
  ],
  "primaryLanguage": "aspx-webforms",
  "frameworksDetected": [
    { "id": "dotnet-framework-48", "version": "4.8", "evidence": "Web.config:18" }
  ],
  "entryPoints": [
    { "path": "Default.aspx", "type": "page" },
    { "path": "Global.asax", "type": "lifecycle" }
  ],
  "exclusions": [".git/", "bin/", "obj/", "packages/", "*.min.js"],
  "pages": [
    {
      "id": "P-1",
      "path": "Login.aspx",
      "codeBehindPath": "Login.aspx.cs",
      "locTotal": 145,
      "linkedUnits": ["U-1"]
    }
  ],
  "units": [
    {
      "id": "U-1",
      "label": "Connexion utilisateur",
      "suggestedName": "Login",
      "language": "aspx-webforms",
      "kind": "form",
      "evidenceFiles": ["Login.aspx", "Login.aspx.cs", "App_Code/AuthService.cs"],
      "entities": ["User"],
      "confidenceEstimate": "high",
      "rationale": "Form avec username/password + handler Page_Load + redirection après auth"
    }
  ],
  "_fingerprintMap": {
    "<sha256-hex>": { "unitId": "U-1", "status": "active", "firstSeen": "2026-06-10T14:32:18Z" }
  },
  "_featAllocations": {
    "U-1": 1
  },
  "_allocatedNames": {
    "Login": "U-1"
  },
  "legacyMtimeMax": 1717987200
}
```

**Notes schéma — champs L0 (V2, 2026-06-10)** :
- `units[].seedEvidenceFiles` (L0) : evidence **seed** = `[page, code-behind]` détectée par `ui_unit_detector`. **Le fingerprint U-N est calculé sur ce seed**, jamais sur l'evidence enrichie — l'enrichissement par graphe ne déstabilise donc jamais les IDs U-N entre re-runs.
- `units[].evidenceFiles` (enrichi L0) : seed **+** chaîne transitive `page→code-behind→service→repository→data-access` résolue par `code_graph_builder` (borné à `max_added_files=30`, profondeur `max_depth=3`). C'est la liste exhaustive que l'agent Phase 3 lit. **C'est le correctif structurel** au défaut « ne capture que la première interface ».
- `units[].classes` (L0) : `[{name, role, file, lines, methodCount, touchesSql, touchesHttp}]` — toutes les classes atteintes depuis le seed, classées par rôle (`repository`/`service`/`dto`/`code-behind`/`controller`/`entity`/`complex`/`classic`/`static-helper`/`interface`/`enum`). Carte exploitée par l'agent pour structurer la FEAT (cf. `agents/reverse-tech-analyst.md` — exploitation de la carte des rôles en 3a).
- `units[].entities` : entités DB déduites (classes de rôle `entity` uniquement — un `repository` n'est PAS une entité).

**Notes schéma v0.4.1** :
- `_allocatedNames` (ADV-13, ADV-19) : mapping `Name → U-N`, mis à jour atomiquement avec `_featAllocations`. Permet la détection de collision intra-run sur `suggestedName`.
- `legacyMtimeMax` (ADV-1) : timestamp UNIX max des mtimes des fichiers scannés. Phase 3 compare au mtime actuel pour émettre `[REVERSE_INVENTORY_STALE]`.
- **Initialisation obligatoire (ADV-23)** : à la création initiale de `inventory.json` (premier scan d'un projet), `inventory_builder.py` DOIT écrire `_allocatedNames: {}` et `_featAllocations: {}` (dictionnaires vides, non absents). Ces champs ne sont JAMAIS optionnels — leur absence dans un `inventory.json` chargé indique un cache pre-v0.4.0 invalide → refresh forcé (cf. §4.1 mode `--use-cache`).
- `schemaVersion: 1` est l'invariant de version : tout consumer qui lit `inventory.json` DOIT vérifier `schemaVersion >= 1` ET présence des clés `_allocatedNames` + `_featAllocations` avant usage. Si check échoue → ERROR `[REVERSE_INVENTORY_SCHEMA_STALE]` + suggestion `/sdd-reverse-inventory --refresh`.

### 5.2 `db-schema.json`

```json
{
  "schemaVersion": 1,
  "project": "LegacyProject",
  "extractDate": "2026-06-10T14:32:25Z",
  "source": "Web.config + DataAccess.cs + *.sql",
  "completeness": "basic | enriched",
  "databaseType": "SqlServer",
  "entities": [
    {
      "name": "User",
      "table": "Users",
      "evidence": ["App_Code/DataAccess.cs:42-58", "Scripts/CreateSchema.sql:5-15"],
      "fields": [
        { "name": "Id", "type": "int", "primaryKey": true, "identity": true },
        { "name": "Username", "type": "nvarchar(50)", "nullable": false, "unique": true },
        { "name": "PasswordHash", "type": "nvarchar(255)", "nullable": false },
        { "name": "CreatedAt", "type": "datetime2", "nullable": false, "default": "GETUTCDATE()" }
      ]
    }
  ],
  "relations": [
    {
      "name": "FK_UserRoles_User",
      "from": { "entity": "UserRole", "field": "UserId" },
      "to": { "entity": "User", "field": "Id" },
      "type": "many-to-one",
      "evidence": ["Scripts/CreateSchema.sql:32"]
    }
  ],
  "indexes": [],
  "missingPartsHint": []
}
```

### 5.3 `language-detected.json`

```json
{
  "schemaVersion": 1,
  "primary": "aspx-webforms",
  "secondary": ["csharp", "javascript", "tsql"],
  "confidence_caps_applied": {
    "aspx-webforms": "high",
    "csharp": "high",
    "javascript": "medium",
    "tsql": "high"
  },
  "_caps_source": ".sdd/python/sdd_reverse/language_signatures.yml"
}
```

### 5.4 `deps-graph.json` (Phase 2)

```json
{
  "schemaVersion": 1,
  "project": "LegacyProject",
  "buildDate": "2026-06-10T15:00:00Z",
  "internalEdges": [
    { "from": "Login.aspx.cs", "to": "App_Code/AuthService.cs", "kind": "call", "evidence": "Login.aspx.cs:34" }
  ],
  "externalDeps": [
    { "name": "Newtonsoft.Json", "version": "12.0.3", "eol": false, "evidence": "packages.config:5" },
    { "name": "log4net", "version": "1.2.10", "eol": true, "eolDate": "2014-12-31", "evidence": "packages.config:8" }
  ],
  "cyclesDetected": [],
  "deadCodeHint": []
}
```

### 5.5 `code-graph.json` (Phase 1, L0 — V2 2026-06-10)

Graphe **symbole-level** (classes, pas fichiers) produit par `code_graph_builder.py`
pendant la Phase 1. Distinct de `deps-graph.json` (Phase 2, niveau fichier via
`using`/`import`). Consommé par `enrich_units` pour peupler `units[].classes` +
enrichir `units[].evidenceFiles`. Lecture humaine via `inventory.md`.

```json
{
  "schemaVersion": 1,
  "project": "LegacyProject",
  "buildDate": "2026-06-10T14:32:20Z",
  "language": "aspx-webforms",
  "classes": [
    {
      "name": "DataAccess", "kind": "class", "role": "repository",
      "file": "App_Code/DataAccess.cs", "namespace": "HelloWebForms.App_Code",
      "baseTypes": [], "attributes": [], "isStatic": true, "isPartial": false,
      "isAbstract": false, "methodCount": 2, "propertyCount": 1,
      "locTotal": 40, "lines": "8-48", "touchesSql": true, "touchesHttp": false,
      "references": []
    }
  ],
  "edges": [
    { "from": "Login", "to": "DataAccess", "kind": "reference", "evidence": "Login.aspx.cs:23" }
  ],
  "rolesSummary": { "code-behind": 2, "repository": 1 },
  "filesAnalyzed": 3
}
```

**Scope L0** : C#/VB.NET (`.cs`/`.vb`). Langages non-.NET → graphe vide
bien-formé (les unités gardent le seed evidence inchangé). Java/PHP ajoutés dans
les lots ultérieurs.

### 5.6 `data-access.json` / `config.json` / `dependencies.json` (Phase 1, L1 — V2 2026-06-10)

Trois artefacts d'extraction technique profonde, produits en Phase 1, qui
comblent des lacunes auparavant à 0 % et alimentent les **FEATs transversales**
(L3 : « Librairies à installer », « Base de données / Procédures stockées »).

- **`data-access.json`** : `queries[]` (SQL inline avec `verb`/`tables`/`params`/`file:line`),
  `storedProcedureCalls[]` (`CommandType.StoredProcedure` + `EXEC sp_xxx`),
  `storedProcedureDefs[]` (`CREATE PROCEDURE` name + paramètres typés + flag `OUTPUT`).
  Producteur : `data_access_extractor.py`. Rattaché par unité via `units[].dataAccess`.
- **`config.json`** : `connectionStrings[]` (`name`/`provider`/`server`/`database`/`value` **secrets masqués `***`**),
  `appSettings[]`. Producteur : `config_extractor.py`.
- **`dependencies.json`** : `packages[]` (NuGet `packages.config` + `.csproj PackageReference` +
  `Directory.Packages.props` ; npm/maven/pypi/composer), `assemblyReferences[]`
  (`<Reference HintPath>`), `binaries[]` (`bin/*.dll`). Producteur : `dependency_inventory.py`.

Ces 3 artefacts sont aussi synthétisés en lecture humaine dans `inventory.md`
(section « ## Synthèse technique (L1) »).

---

## §6 Contrats inter-phases

| Producer | Artefact | Consumer | Champ exact |
|---|---|---|---|
| Phase 1 | `inventory.json` → `units[]` | Phase 3 (`/sdd-reverse {U-N}`) | `units[id={U-N}]` doit exister |
| Phase 1 | `inventory.json` → `units[].evidenceFiles[]` | Phase 3 (agent extractor) | Liste exhaustive des fichiers à Read |
| Phase 1 | `db-schema.json` → `entities[]` | Phase 3 (agent extractor) | Source de vérité des entities (D7) |
| Phase 1 | `language-detected.json` → `confidence_caps_applied[lang]` | Phase 3 (agent extractor) | Plafond `confidence` initial |
| Phase 2 | `tech-audit.md` (informational) | (humain) | Non consommé par Phase 3 |
| Phase 2 | `db-schema.enrichment.json` (séparé, ADV-3) | `merge_db_schema.py` (V2) | Enrichissement append-only stocké dans fichier dédié |
| Phase 2 → script | `db-schema.merged.json` (union déterministe) | Phase 3 (agent extractor) | Source de vérité enrichie si présente, sinon fallback `db-schema.json` base |
| Phase 3 | `workspace/feats/{n}-{Name}.md` | Phase 4 (`/sdd-reverse-ui {U-N}`) | Cibles d'écrans dérivées du contenu FEAT |
| Phase 3 | `inventory.json` → `_featAllocations[U-N]` | Phase 4 (résolution `{n}`) | Mapping U-N → n |
| Phase 4 | `workspace/ui/{n}-{m}-{Name}.html` | Phase 6 (`/sdd-full {n}`) | UX mockup standard SDD_Pro |
| Phase 3 | `workspace/feats/{n}-{Name}.md` | Phase 6 (`/sdd-full {n}`) | FEAT standard SDD_Pro (D6 conformité) |

**Invariant `n` ↔ `U-N`** : une fois Phase 3 exécutée pour `U-N`, la valeur de `n` est figée dans `inventory.json._featAllocations[U-N]`. Toute re-exécution de Phase 3 sur `U-N` réécrit le même `{n}-{Name}.md`.

### 6.1 Gate `/sdd-full` sur FEAT reverse (ADV-6, opt-in)

**Problème mitigé** : un Tech Lead pouvait lancer `/sdd-full 7` sur une FEAT reverse `confidence: low` non revue, déclenchant tout le pipeline (arch + dev-* + qa) sur des ACs potentiellement hallucinées.

**Solution proposée (opt-in, ne modifie pas `/sdd-full` existant)** :

Comme `/sdd-full` est un fichier existant **intouchable** (Annexe B), la gate prend la forme d'un **hook utilisateur recommandé** + script externe :

1. Script `sdd_reverse_scripts/check_reverse_feat_for_full.py` (nouveau, isolé) :
   ```bash
   python .sdd/python/sdd_reverse_scripts/check_reverse_feat_for_full.py \
     --feat-path workspace/feats/{n}-*.md \
     [--allow-reverse-low]
   ```
   - Exit 0 : FEAT non-reverse OU FEAT reverse `confidence: high`
   - Exit 1 : FEAT reverse `confidence` ∈ {medium, low} sans flag `--allow-reverse-low` → bloquant
   - Output JSON : `{ "is_reverse": bool, "confidence": str, "allowed": bool, "reason": str }`

2. **Convention utilisateur** : avant `/sdd-full {n}`, lancer le check :
   ```bash
   python .sdd/python/sdd_reverse_scripts/check_reverse_feat_for_full.py --feat-path workspace/feats/7-*.md && /sdd-full 7
   ```
   Documenté dans la commande `/sdd-reverse-status` (V2).

3. **Documentation transparente** : le cookbook reverse (`docs/reverse-engineering-cookbook/` — `index.md` + 7 fiches : `_generic-monolith`, `dotnet-webforms`, `dotnet-mvc`, `java-jee`, `php-procedural`, `javascript-jquery`, `delphi`) explique cette convention. La skill `starting-a-reverse-eng` rappelle ce check lors de la Phase 5 (revue humaine).

**Limitation assumée** : si le Tech Lead lance `/sdd-full {n}` directement sans passer par le check, la gate ne se déclenche pas (pas d'enforcement runtime sans toucher `/sdd-full`). Cette limitation est conséquence directe de la règle d'isolation §3.1. Mitigation V3 : proposer un PR officiel sur `/sdd-full` pour intégrer le check (décision Tech Lead seule, hors-scope reverse).

### 6.2 Marker `[REV]` / `[REV⚠️]` dans outils en aval

`/sdd-status` et la console web sont **intouchables**. Solution :

- **Court terme MVP** : `sdd_reverse_scripts/reverse_status.py` (nouvelle commande `/sdd-reverse-status`, V2) liste les FEATs reverse avec leur confidence et signale celles non-`high` à reviewer manuellement.
- **Documentation** : la skill et le cookbook recommandent `cat workspace/feats/*.md | head -20` ou `grep -l 'generated-by: sdd-reverse' workspace/feats/*.md` pour identifier les FEATs reverse.
- **V3** : proposer enrichissement officiel `/sdd-status` (PR séparé, décision Tech Lead).

---

## §7 Mécanisme de découverte `loader.reverse.yml`

**Contrainte D4** : `loader.reverse.yml` est **autonome**. Aucune modification de `loader.yml`. Le framework existant ignore son existence.

### 7.1 Schéma `loader.reverse.yml`

```yaml
# .sdd/loader.reverse.yml — SSoT du workflow reverse engineering
# Format miroir de loader.yml, périmètre limité aux agents reverse
# (16 au 2026-08-29 : 10 code-reverse + 6 db-reverse — cf. loader.reverse.yml).

schemaVersion: 1
manifestType: reverse-engineering
extends: null   # autonome, ne hérite pas de loader.yml

agents:
  reverse-inventory:
    reads:
      - workspace/old/{P}/**
      - .sdd/python/sdd_reverse/language_signatures.yml
    writes:
      - workspace/old/{P}/.sys/inventory.{md,json}
      - workspace/old/{P}/.sys/db-schema.{md,json}
      - workspace/old/{P}/.sys/language-detected.json

  reverse-tech-auditor:
    reads:
      - workspace/old/{P}/.sys/inventory.json
      - workspace/old/{P}/.sys/db-schema.json
      - workspace/old/{P}/**
    writes:
      - workspace/old/{P}/.sys/tech-audit.md
      - workspace/old/{P}/.sys/deps-graph.json
      - workspace/old/{P}/.sys/db-schema.enrichment.json   # ADV-3+ADV-17 : fichier séparé, JAMAIS db-schema.json
    # NOTE ADV-3+ADV-17 : ce manifest interdit l'écriture sur db-schema.json par reverse-tech-auditor.
    # L'union base+enrichment est faite par le script déterministe sdd_reverse/merge_db_schema.py
    # qui écrit db-schema.merged.json. Voir §4.2.

  # Escalier 3a/3b/3c (audit 2026-06-11 — remplace l'entrée reverse-functional-extractor ;
  # SSoT machine = loader.reverse.yml, ceci n'est qu'un mirror illustratif)
  reverse-tech-analyst:        # 3a
    reads:
      - workspace/old/{P}/.sys/inventory.json
      - workspace/old/{P}/.sys/db-schema.merged.json   # si présent (Phase 2 a tourné)
      - workspace/old/{P}/.sys/db-schema.json          # fallback base
      - workspace/old/{P}/.sys/tech-audit.md           # optionnel
      - workspace/old/{P}/{evidenceFiles}              # SEUL barreau à lire le code legacy
      - .sdd/python/sdd_reverse/language_signatures.yml
      - .sdd/python/sdd_reverse/analysis.reverse.template.md
    writes:
      - workspace/plans/{n}-{Name}.analysis.md
  reverse-us-writer:           # 3b (forbidden_reads: code legacy)
    reads:
      - workspace/plans/{n}-{Name}.analysis.md
      - .sdd/python/sdd_reverse/us.reverse.template.md
    writes:
      - workspace/us/{n}-{m}-{Name}.md
  reverse-feat-composer:       # 3c (forbidden_reads: code legacy)
    reads:
      - workspace/us/{n}-{m}-{Name}.md
      - workspace/plans/{n}-{Name}.analysis.md
      - .sdd/python/sdd_reverse/feat.reverse.template.md   # template isolé (ADV-9)
    writes:
      - workspace/feats/{n}-{Name}.md
      - workspace/old/{P}/.sys/modules/{Module}/extraction.md

  reverse-ui-extractor:
    reads:
      - workspace/old/{P}/.sys/inventory.json
      - workspace/old/{P}/{templateFiles, cssFiles}
      - workspace/feats/{n}-{Name}.md
    writes:
      - workspace/ui/{n}-{m}-{Name}.html

commands:
  sdd-reverse-init:        { phase: 0,   spawns: [] }
  sdd-reverse-inventory:   { phase: 1,   spawns: [reverse-inventory] }
  sdd-reverse-audit:       { phase: 2,   spawns: [reverse-tech-auditor] }
  sdd-reverse:             { phase: 3,   spawns: [] }   # séquenceur pur — analyze/stories/feat spawnent 3a/3b/3c
  sdd-reverse-ui:          { phase: 4,   spawns: [reverse-ui-extractor] }
  sdd-reverse-full:        { phase: 1-4, spawns: []   # séquence de commandes, pas d'agents }
  sdd-reverse-status:      { phase: any, spawns: [] }
```

### 7.2 Découverte

Le loader n'est pas chargé automatiquement par le framework. Il est **explicitement référencé** par :

1. **Frontmatter des 7 commandes reverse** (header YAML) :
   ```yaml
   ---
   command: sdd-reverse-inventory
   loader: .sdd/loader.reverse.yml
   ---
   ```

2. **Frontmatter de la skill `starting-a-reverse-eng`** :
   ```yaml
   ---
   name: starting-a-reverse-eng
   loader: .sdd/loader.reverse.yml
   ---
   ```

Chaque commande/skill lit `loader.reverse.yml` au démarrage pour résoudre paths reads/writes — comme `loader.yml` mais sur son périmètre isolé.

### 7.3 Cohabitation

- `loader.yml` continue à servir les agents SDD_Pro existants (po, arch, dev-*, qa, *-reviewer).
- `loader.reverse.yml` sert exclusivement les agents reverse (16 au 2026-08-29 — le « 4 » historique datait de la v0.3.0).
- Aucun overlap : les paths declared par l'un ne sont pas declared par l'autre (sauf `workspace/feats/` et `workspace/ui/` qui sont **lus** par les agents SDD_Pro et **écrits** par les agents reverse — séparation reader/writer claire).

---

## §8 `language_signatures.yml` — schéma + valeurs initiales

**Path** : `.sdd/python/sdd_reverse/language_signatures.yml`

### 8.1 Schéma

```yaml
schemaVersion: 1
languages:
  - id: <kebab-case-string>            # identifiant stable, ex. "aspx-webforms"
    label: <human readable>            # ex. "ASP.NET WebForms"
    family: <string>                   # ex. "dotnet" | "java" | "php" | ...
    file_extensions: [<.ext>, ...]     # extensions distinctives
    evidence_patterns:                 # regex matchant le contenu
      - pattern: <regex>
        weight: <0..1>                 # poids dans le score de détection
        discriminative: <bool>         # optionnel — cf. `exclusive_group` ci-dessous
        description: <string>
    framework_signatures:              # detection sous-frameworks
      - id: <string>
        evidence: <regex>
        version_extract: <regex group>
    confidence_cap: <high|medium|low>  # PLAFOND OFFICIEL (D1, §5.6 prompt master)
    exclusive_group: <string>          # optionnel — arbitrage mutuellement exclusif
    excluded_paths:                    # paths à ignorer pour ce langage
      - <glob>
```

**`exclusive_group` + `discriminative`** (audit F-05, 2026-08-26) — deux langages
du même `exclusive_group` ne peuvent pas revendiquer le même fichier : les quatre
dialectes SQL (`tsql`, `plpgsql`, `plsql`, `mysql`) partagent l'extension `.sql`
*et* le DDL générique (`CREATE TABLE`, `CREATE PROCEDURE`, `CREATE FUNCTION`).
Sans arbitrage, chaque fichier T-SQL était revendiqué par les 4 buckets — vues,
triggers et `parseWarnings` sortaient ×4, et le plafond de confiance min-monotone
(§5.6) dégradait une application 100 % SQL Server de `high` à `medium` à cause de
moteurs jamais présents.

L'arbitrage se joue en deux temps :

1. **Par fichier** — le mieux classé revendique le fichier. Le classement met en
   tête les dialectes ayant matché ≥ 1 pattern `discriminative: true`, puis le
   score, puis l'ordre de déclaration. `discriminative` marque un marqueur
   **impossible dans un moteur frère** (`GO` pour T-SQL, `LANGUAGE plpgsql`,
   `DELIMITER`, `PACKAGE BODY`) ; le DDL partagé ne le porte jamais et pèse ≤ 0.6,
   loin sous les marqueurs exclusifs. Sans ce critère, le score seul faisait
   gagner `plpgsql`/`mysql` (2 × `CREATE …` à 1.0) sur du T-SQL évident.
2. **Par projet** — un dialecte qui n'a jamais produit de preuve exclusive sur
   *aucun* fichier est absorbé par le survivant du groupe (ses fichiers lui sont
   transférés, rien n'est perdu). C'est ce qui empêche un unique `.sql` mal
   attribué à un moteur `cap: medium` de dégrader tout l'escalier. Un dépôt
   réellement polyglotte conserve ses deux dialectes : chacun a fait ses preuves.

Ajouter un 5ᵉ dialecte SQL sans `exclusive_group` ni pattern `discriminative`
réintroduit F-05 — deux tests d'anti-rot le verrouillent
(`tests/test_sdd_reverse_audit_f03_f05.py`).

### 8.2 Valeurs initiales MVP

```yaml
schemaVersion: 1
languages:
  # === DOTNET FAMILY ===
  - id: aspx-webforms
    label: ASP.NET WebForms
    family: dotnet
    file_extensions: [.aspx, .ascx, .master, .ashx]
    evidence_patterns:
      - { pattern: '<%@\s+Page\s+', weight: 1.0, description: "Page directive ASPX" }
      - { pattern: 'runat="server"', weight: 0.8, description: "Server-side control" }
      - { pattern: 'CodeBehind="', weight: 0.9, description: "Code-behind attribute" }
    framework_signatures:
      - { id: dotnet-framework, evidence: '<compilation\s+targetFramework="', version_extract: 'targetFramework="([0-9.]+)"' }
    confidence_cap: high
    excluded_paths: [bin/, obj/, packages/, App_Data/]

  - id: dotnet-mvc
    label: ASP.NET MVC (classique)
    family: dotnet
    file_extensions: [.cshtml, .vbhtml, .cs]
    evidence_patterns:
      - { pattern: '@model\s+', weight: 1.0 }
      - { pattern: ':\s*Controller\s*\b', weight: 0.9 }
      - { pattern: '\bActionResult\b', weight: 0.7 }
    confidence_cap: high

  - id: csharp
    label: C# (générique, non MVC/WebForms)
    family: dotnet
    file_extensions: [.cs]
    evidence_patterns:
      - { pattern: '\busing\s+System;', weight: 0.5 }
      - { pattern: '\bnamespace\s+', weight: 0.6 }
    confidence_cap: high

  # WPF Windows desktop UI (depuis 2026-06-10)
  # Couvre WPF .NET Framework 4.x ET WPF moderne (.NET 5/6/7/8).
  # Filtrage automatique App.xaml + ResourceDictionary-only par ui_unit_detector.
  # Code-behind .xaml.cs / .xaml.vb détecté par _build_pages_list.
  - id: wpf-xaml
    label: WPF (.NET Framework + Core/.NET 5+)
    family: dotnet
    file_extensions: [.xaml]
    evidence_patterns:
      - { pattern: 'xmlns="http://schemas\.microsoft\.com/winfx/2006/xaml/presentation"', weight: 5.0 }
      - { pattern: '<Window\b', weight: 3.0 }
      - { pattern: '<Page\b', weight: 3.0 }
      - { pattern: '<UserControl\b', weight: 3.0 }
      - { pattern: 'x:Class="', weight: 2.0 }
      - { pattern: '<DataGrid\b', weight: 1.5 }
      - { pattern: '<TextBox\b', weight: 1.0 }
    confidence_cap: high
    excluded_paths: [bin/, obj/, packages/, .vs/, AppPackages/]

  # === JAVA FAMILY ===
  - id: java-ee
    label: Java EE (servlets/JSP/JSF)
    family: java
    file_extensions: [.java, .jsp, .jspx, .xhtml]
    evidence_patterns:
      - { pattern: '@WebServlet', weight: 1.0 }
      - { pattern: 'extends\s+HttpServlet', weight: 0.9 }
      - { pattern: '<%@\s+page\s+', weight: 0.9 }
    confidence_cap: high

  # === PHP FAMILY ===
  - id: php-framework
    label: PHP framework (Laravel/Symfony/CodeIgniter)
    family: php
    file_extensions: [.php, .blade.php, .twig]
    evidence_patterns:
      - { pattern: '\bnamespace\s+App\\', weight: 0.8 }
      - { pattern: '\buse\s+Illuminate\\', weight: 1.0, description: "Laravel" }
      - { pattern: '\buse\s+Symfony\\', weight: 1.0, description: "Symfony" }
    confidence_cap: high

  - id: php-procedural
    label: PHP procédural (sans framework)
    family: php
    file_extensions: [.php]
    evidence_patterns:
      - { pattern: '<\?php', weight: 0.5 }
      - { pattern: '\bmysql_query\(', weight: 0.7, description: "ext/mysql legacy" }
    confidence_cap: medium     # legacy procédural = qualité inférieure attendue

  # === DELPHI ===
  - id: delphi-source
    label: Delphi (source .pas + DFM)
    family: delphi
    file_extensions: [.pas, .dfm, .dpr]
    evidence_patterns:
      - { pattern: '\bunit\s+\w+;', weight: 0.9 }
      - { pattern: '\bobject\s+\w+:\s*T\w+', weight: 1.0, description: "DFM form" }
    confidence_cap: high

  # === JS/JQUERY ===
  - id: javascript-jquery
    label: JavaScript + jQuery (legacy)
    family: web
    file_extensions: [.js]
    evidence_patterns:
      - { pattern: '\$\(document\)\.ready', weight: 1.0 }
      - { pattern: '\$\.ajax\(', weight: 0.8 }
    confidence_cap: medium

  # === VB6 ===
  - id: vb6
    label: Visual Basic 6 (source .frm/.bas)
    family: vb
    file_extensions: [.frm, .bas, .cls, .vbp]
    evidence_patterns:
      - { pattern: 'VERSION\s+5\.00', weight: 1.0 }
      - { pattern: 'Begin\s+VB\.Form\s+', weight: 1.0 }
    confidence_cap: medium

  # === FALLBACK ===
  - id: unknown
    label: Langage non signé
    family: unknown
    file_extensions: []
    evidence_patterns: []
    confidence_cap: low
```

### 8.3 Extensibilité

Ajouter un langage : ajouter une entrée YAML, faire un test smoke sur un fixture représentatif. Aucune modification de code.

---

## §9 Confidence cap par langage + dégradation

### 9.1 Computation

```
cap_effectif(unit) = min(
    confidence_cap_from_language_signatures(unit.language),
    confidence_estimate_par_agent(unit),                       # inférence LLM
    degradation_db_schema_manquant(unit)                       # voir 9.2
)
```

### 9.2 Dégradation — schéma DB manquant

Si `db-schema.json.entities` est vide ou ne couvre pas les entités référencées dans `unit.entities` :
- L'agent extractor **autorise** à déduire les entities depuis le code (DTOs, classes data, requêtes SQL inline)
- Mais le cap effectif est plafonné à `medium`
- Une bannière est ajoutée au début de la FEAT :
  ```
  > ⚠️ DB schema non extrait — entités déduites du code. Confiance plafonnée à medium.
  > Source attendue : workspace/old/{P}/.sys/db-schema.json (absent ou vide).
  ```
- (La classe historique `[REVERSE_DB_SCHEMA_DEGRADED]` a été retirée de la taxonomie — audit MA-7 2026-06-11, aucun émetteur câblé. La dégradation est appliquée silencieusement via le cap, cf. rules/reverse-engineering.md §4.)

### 9.3 Items individuels

Chaque AC, SFD, BR porte son propre `<!-- confidence: ... -->`. Le cap global est `max` des items. Si un item est `high` mais que le cap langage est `medium`, l'item est **rabaissé** à `medium`.

---

## §10 Classification erreurs `[REVERSE_*]`

Hérite du format SDD_Pro `error-classification.md` (3 lignes disque, 1 ligne chat). À documenter dans la **nouvelle** règle `.sdd/rules/reverse-engineering.md` (pas dans le fichier principal `error-classification.md`).

> **Table déplacée — SSoT unique (audit 2026-08-29, M7).** La taxonomie complète
> vivait ici EN DOUBLE, gelée à ses 16 classes de juin 2026 : elle ignorait les
> 26 classes ajoutées depuis (escalier, parité, paradigme, questions, db-reverse,
> sous-extraction en lecture) et contredisait la règle sur des points de fait —
> TTL du `.alloc.lock` annoncé à 30 s alors qu'il est passé à 1800 s (audit C5),
> `[REVERSE_FEAT_VALIDATE_FAILED]` attribué à `/feat-validate` alors que la gate
> est `validate_reverse_feat.py`. Un lecteur ne pouvait pas savoir laquelle des
> deux tables faisait foi.
>
> **Source unique : `.sdd/rules/reverse-engineering.md §6`** — 45 classes
> (42 au 2026-08-29 + 3 ajoutées le lendemain par le remède reverse-DB de ce
> même audit : `OBJECT_KIND_MISMATCH`, `DB_PACK_MISSING`, `DB_CONTEXT_STALE`),
> décompte verrouillé par `tests/test_reverse_audit_2026_08_29.py`. Ce document
> n'en garde que le format d'émission ci-dessous. Aucune classe ne s'ajoute sans
> son émetteur (règle §6.3).

### 10.1 Format ERROR exemple

```
ERROR: reverse-inventory LegacyApp — aucun langage matché
CAUSE: [REVERSE_NO_SOURCE] workspace/old/MyLegacy/ vide ou inexistant
FIX: ajouter une entrée pour le langage dans .sdd/python/sdd_reverse/language_signatures.yml, OU déposer un échantillon plus représentatif sous workspace/old/{P}/
```

---

## §11 Exemple legacy fictif (5-10 fichiers)

**Projet** : `workspace/old/HelloWebForms/` — ASP.NET WebForms .NET 4.8, 6 fichiers.

### 11.1 Fichiers déposés

```
workspace/old/HelloWebForms/
├── Default.aspx                    # Page d'accueil
├── Default.aspx.cs                 # Code-behind accueil
├── Login.aspx                      # Formulaire login
├── Login.aspx.cs                   # Logic login + appel DataAccess
├── Web.config                      # Config .NET, connection string
├── App_Code/
│   └── DataAccess.cs               # Méthodes ADO.NET CRUD User
└── Scripts/
    └── CreateSchema.sql            # Schéma SQL Server (Users table)
```

### 11.2 Sortie Phase 1 — `inventory.json` (extrait)

```json
{
  "schemaVersion": 1,
  "project": "HelloWebForms",
  "primaryLanguage": "aspx-webforms",
  "languagesDetected": [
    { "id": "aspx-webforms", "filesCount": 2, "confidence": "high" },
    { "id": "csharp", "filesCount": 3, "confidence": "high" },
    { "id": "tsql", "filesCount": 1, "confidence": "high" }
  ],
  "pages": [
    { "id": "P-1", "path": "Default.aspx", "codeBehindPath": "Default.aspx.cs", "linkedUnits": ["U-2"] },
    { "id": "P-2", "path": "Login.aspx", "codeBehindPath": "Login.aspx.cs", "linkedUnits": ["U-1"] }
  ],
  "units": [
    {
      "id": "U-1",
      "label": "Connexion utilisateur",
      "suggestedName": "Login",
      "language": "aspx-webforms",
      "kind": "form",
      "evidenceFiles": ["Login.aspx", "Login.aspx.cs", "App_Code/DataAccess.cs", "Web.config"],
      "entities": ["User"],
      "confidenceEstimate": "high",
      "rationale": "Form (txtUsername, txtPassword, btnLogin) + handler btnLogin_Click appelant DataAccess.ValidateUser"
    },
    {
      "id": "U-2",
      "label": "Accueil authentifié",
      "suggestedName": "Home",
      "language": "aspx-webforms",
      "kind": "page",
      "evidenceFiles": ["Default.aspx", "Default.aspx.cs"],
      "entities": [],
      "confidenceEstimate": "high",
      "rationale": "Page Default avec lblWelcome, vérification Session[\"UserId\"], redirect Login si null"
    }
  ]
}
```

### 11.3 Sortie Phase 1 — `db-schema.json` (extrait)

```json
{
  "schemaVersion": 1,
  "completeness": "basic",
  "databaseType": "SqlServer",
  "entities": [
    {
      "name": "User",
      "table": "Users",
      "evidence": ["Scripts/CreateSchema.sql:1-12", "App_Code/DataAccess.cs:18-45"],
      "fields": [
        { "name": "Id", "type": "int", "primaryKey": true, "identity": true },
        { "name": "Username", "type": "nvarchar(50)", "nullable": false, "unique": true },
        { "name": "PasswordHash", "type": "nvarchar(255)", "nullable": false },
        { "name": "CreatedAt", "type": "datetime2", "nullable": false }
      ]
    }
  ]
}
```

### 11.4 Sortie Phase 3 — `workspace/feats/1-Login.md` (extrait)

```markdown
---
generated-by: sdd-reverse
legacy-sources: [HelloWebForms/Login.aspx, HelloWebForms/Login.aspx.cs, HelloWebForms/App_Code/DataAccess.cs]
confidence: high
extraction-date: 2026-06-10T14:35:00Z
language-detected: aspx-webforms
source-unit: U-1
---

# FEAT 1 — Connexion utilisateur

## Actors

| Acteur | Rôle |
|---|---|
| Utilisateur | Personne disposant d'un compte (Username + PasswordHash en table Users) |

## Functional Needs

- **SFD-1** Permettre à un utilisateur identifié de prouver son identité par username + password. <!-- evidence: Login.aspx:8-22 --> <!-- confidence: high -->
- **SFD-2** Rediriger l'utilisateur authentifié vers la page d'accueil. <!-- evidence: Login.aspx.cs:34-38 --> <!-- confidence: high -->

## Functional Deliverables

- **FD-1** Formulaire de connexion avec champs username (texte) + password (masqué). <!-- evidence: Login.aspx:10-18 --> <!-- confidence: high -->
- **FD-2** Bouton "Se connecter" déclenchant validation serveur. <!-- evidence: Login.aspx:20-22, Login.aspx.cs:24 --> <!-- confidence: high -->
- **FD-3** Message d'erreur en cas d'échec ("Identifiants incorrects"). <!-- evidence: Login.aspx.cs:42-44 --> <!-- confidence: high -->

## Business Rules

- **BR-1** Username unique en base (contrainte SQL `UNIQUE` sur Users.Username). <!-- evidence: Scripts/CreateSchema.sql:7 --> <!-- confidence: high -->
- **BR-2** Le mot de passe est comparé contre `PasswordHash` (non en clair). <!-- evidence: App_Code/DataAccess.cs:32 --> <!-- confidence: high -->

## Acceptance Criteria

- **AC-1** Given un Username + Password valides en base, when l'utilisateur soumet le formulaire, then la session est créée (Session["UserId"] = User.Id) et l'utilisateur est redirigé vers Default.aspx. <!-- evidence: Login.aspx.cs:30-38 --> <!-- confidence: high -->
- **AC-2** Given un Username inexistant ou un Password incorrect, when l'utilisateur soumet le formulaire, then le message "Identifiants incorrects" s'affiche, la session reste vide, l'utilisateur reste sur Login.aspx. <!-- evidence: Login.aspx.cs:40-46 --> <!-- confidence: high -->

## Project Config

(à compléter par /sdd-full lors de la migration)
```

### 11.5 Validation

`python .sdd/python/sdd_scripts/validate_readiness.py --feat 1 --json` doit retourner exit 0 :
- IDs stables (SFD-1, SFD-2, FD-1..3, BR-1..2, AC-1..2)
- Sections obligatoires présentes
- AC au format Given/When/Then
- Frontmatter `confidence` ∈ {high, medium, low}

---

## §12 Plan de tests

### 12.1 Tests unitaires Python (`.sdd/python/tests/test_sdd_reverse_*.py`)

| Module | Tests minimaux | Coverage cible |
|---|---|---|
| `scan_legacy.py` | détection langage simple, exclusions, fichier binaire, langage inconnu | ≥ 80% |
| `inventory_builder.py` | allocation U-N stable cross-runs (fingerprint), exclusions, fichier vide, gros projet (smoke) | ≥ 80% |
| `ui_unit_detector.py` | grid CRUD → 1 unit, wizard → 1 unit, modale isolée → 0 unit | ≥ 80% |
| `db_schema_extractor.py` | SQL DDL, EF Code-First (DbSet<>), Hibernate, Doctrine, schéma absent | ≥ 80% |

### 12.2 Tests d'intégration

`.sdd/python/tests/test_sdd_reverse_e2e.py` :
- Fixture `tests/fixtures/legacy-webforms-minimal/` (6 fichiers du §11)
- Exécution `reverse_inventory.py --project legacy-webforms-minimal`
- Assertions sur shape `inventory.json` (units U-1, U-2 présents, languagesDetected non vide)
- Assertions sur `db-schema.json` (entity User avec 4 fields)

### 12.3 Test de conformité `/feat-validate`

Pour chaque FEAT générée dans une fixture de smoke (§11) :
- Lancer `validate_readiness.py --feat {n} --json`
- Assert exit 0
- Assert pas de NO-GO structural dans le JSON output

### 12.4 Smoke isolation (anti-régression framework)

`.sdd/python/tests/test_local_helpers_parity.py` + `tests/test_sdd_reverse_*.py` (le fichier historique `test_sdd_reverse_isolation.py` n'existe pas — pointeur corrigé audit 2026-06-11) :
- Snapshot des hashes SHA256 de tous les fichiers existants dans `.claude/` (hors `sdd_reverse/`, hors `.sys/`, etc.)
- Exécution complète du workflow reverse sur la fixture
- Vérification : tous les hashes pré/post identiques (aucun fichier framework modifié)

### 12.5 Smoke général

`python .sdd/python/sdd_admin/framework_smoke.py` doit rester vert après ajout du module reverse. Si nouveau gate `reverse-isolation` souhaité, à coder en **nouveau** script `.sdd/python/sdd_reverse_scripts/reverse_smoke.py` (PAS d'édition de `framework_smoke.py`).

### 12.6 Tests parité validators (ADV-14)

**Problème** : `sdd_reverse_scripts/validate_reverse_feat.py` duplique partiellement la logique de `sdd_scripts/validate_readiness.py` standard SDD_Pro. Si le standard évolue (nouvelle section obligatoire, regex AC durcie), le reverse devient désaligné silencieusement → FEAT reverse passe son check mais est rejetée par `/sdd-full`.

**Solution** : suite de tests `test_validators_parity.py` :

1. **Shared spec** : extraire dans un module utilitaire `sdd_reverse/feat_structure_spec.py` les contrats partagés (sections obligatoires, IDs `^(SFD|FD|BR|AC)-\d+$`, format Given/When/Then). Ce module est lu par `validate_reverse_feat.py` mais **PAS** importé par `validate_readiness.py` (qui reste intouchable).
2. **Tests de parité** : pour chaque check structurel de `validate_readiness.py` qui s'applique aussi en reverse, écrire un test :
   - Fixture FEAT minimaliste qui passe les deux validators → assert exit 0 sur les deux
   - Fixture FEAT cassée (ex. AC sans Given) → assert exit non-0 sur les deux
3. **Alarme drift** : `reverse_smoke.py` (V2 ADV-7) inclut une vérification :
   - Lire `validate_readiness.py` source
   - Comparer son set de checks (extrait par grep `errors.append(`) avec celui de `validate_reverse_feat.py`
   - Si checks **présents dans standard mais absents du reverse** → WARN `[REVERSE_VALIDATOR_DRIFT]`
   - Pas bloquant (le reverse peut volontairement omettre des checks infra), mais visible.
4. **Documentation** : le `CHANGELOG` doit signaler tout changement de validator standard avec impact reverse potentiel (process discipline).

### 12.7 Tests parité helpers locaux (ADV-16)

**Problème** : `sdd_reverse/file_locks_local.py` et `atomic_write_local.py` dupliquent `sdd_lib/file_locks.py` et `sdd_lib/atomic_write.py`. Bug fix upstream → reverse non patché.

**Solution** : tests `test_local_helpers_parity.py` :

1. **Property-based tests** :
   - `atomic_write_text(path, content)` : assert qu'après crash simulé mid-write, soit le fichier original intact, soit le nouveau contenu intégral (jamais partiel)
   - `acquire_lock(path, ttl)` : assert qu'un second `acquire` simultané échoue, et qu'après TTL le lock est récupérable
2. **Sémantique parallèle** : exécuter les mêmes property tests contre `sdd_lib/file_locks.py` (read-only, pas d'import direct mais via subprocess pour isolation). Si comportements divergent → FAIL test.
3. **Test API surface** : assert que `dir(file_locks_local) ⊇ {fonctions publiques de file_locks}` (signature compatible si jamais on veut fusionner V3).
4. **Alarme drift** : `reverse_smoke.py` compare les hashes SHA256 de `sdd_lib/file_locks.py` et `sdd_lib/atomic_write.py` à des snapshots stockés dans `sdd_reverse/_parity_snapshots.json` :
   - Hash inchangé → OK
   - Hash changé → WARN `[REVERSE_HELPER_DRIFT]` : lire le diff upstream, décider si appliquer au local
   - Pas bloquant, juste signal.
5. **Justification duplication** : la duplication est délibérée (D4 isolation). Les tests de parité sont le contrat qui empêche que la duplication devienne du code mort divergent.

#### 12.7.bis Divergences volontaires documentées (P2.9 closure 2026-06-10)

Tous les écarts d'API ou de comportement entre les helpers locaux et leurs
versions standard sont **délibérés** et tracés ci-dessous. Toute parité
nouvelle (ex. ajout d'une fonction publique côté `sdd_lib`) doit faire
l'objet d'une décision explicite : (a) la dupliquer côté reverse, (b) la
laisser hors scope reverse, ou (c) faire évoluer la liste ci-dessous.

| Helper | Aspect | `sdd_lib/*` standard | `sdd_reverse/*_local` | Raison |
|---|---|---|---|---|
| `atomic_write` | Signature `atomic_write_text` | `atomic_write_text(path, content, *, encoding="utf-8", newline=None, tmp_suffix=".sddtmp")` | `atomic_write_text(path, content, encoding="utf-8")` | API minimale MVP — `newline` et `tmp_suffix` non requis Phase 1-4. Si Phase 5 (impl translator V3) en a besoin, étendre côté reverse en se synchronisant. |
| `atomic_write` | Mitigation RUPT-5 | `_replace_with_retry` + `_backoff_with_jitter` (5 retries, 50 ms × jitter [0.8, 1.2]) | **Synced 2026-06-10** — mêmes constantes `_REPLACE_MAX_RETRIES=5`, `_REPLACE_BACKOFF_S=0.05` | Avant P0.1 closure, le local n'avait pas de retry. Test parité `test_atomic_write_local_byte_for_byte_against_lib_constants` enforce désormais l'égalité des constantes. |
| `file_locks` | Format payload | **3-part text** : `AGENT_ID:PID:TS_MS` (lecture multi-format) OU **2-part** : `AGENT_ID:TS_S` | **JSON** : `{"agent_id", "pid", "ts_unix", "host"}` | Le payload JSON porte un champ supplémentaire `host` (anti-confusion cross-machine) qui n'a pas d'équivalent côté `sdd_lib`. Choix design Phase 3 (lock sur `workspace/feats/.alloc.lock`). **Conséquence** : un script du framework standard qui lirait ce lock par accident ne pourrait pas le parser — acceptable par design D4, jamais un caller croisé n'est censé apparaître. |
| `file_locks` | API publique | `try_create_exclusive(path, content) -> bool` + `acquire_with_retry(path, content, ttl_ms, backoff_ms)` | `acquire_lock(path, agent_id, ttl=30) -> int` + `release_lock(path, agent_id) -> int` + `read_lock(path) -> dict\|None` | Exit codes 0/1/2/3 (cf. `ownership.md §4` table standard SDD_Pro) au lieu de booléens. Re-entrant per `agent_id` côté reverse — pas côté standard. **Pas une perte de parité** : c'est l'API attendue par les agents reverse, et le contrat est plus riche (re-entrant + host check). |
| `file_locks` | Dépendance `psutil` | absente (standard) | **optionnelle** (ADV-10) — fallback TTL-only si absente | Le check pid `_is_pid_alive` est utilisé pour court-circuiter le TTL quand on sait que l'agent crashé n'est plus là. Si `psutil` non installé, le lock attend toujours le TTL (30 s) — comportement strictement plus prudent. |
| `_parity_snapshots.json` | Régénération | n/a (pas de snapshot côté standard) | manuelle pour l'instant (V0.4 : script `sync_parity_snapshots.py`) | Quand on synchronise volontairement une mitigation upstream (ex. P0.1 RUPT-5), les hashes restent inchangés (le standard est déjà à jour). Si on **diverge volontairement** côté local (ex. retirer un fix qu'on ne veut pas), il faudra capturer le nouveau hash pré-divergence ici. |

**Règle d'or pour ajouter une nouvelle divergence** :

1. Ajouter une ligne dans le tableau ci-dessus avec la raison.
2. Ajouter un test ciblé dans `tests/test_local_helpers_parity.py` qui asserte la divergence (et empêche un futur sync accidentel de la casser).
3. Si la divergence touche une mitigation de sécurité (retry, fsync, lock), créer un ADR dans `workspace/.sys/.context/adrs/` documentant la décision.

**Symétriquement, règle pour résorber une divergence** :

1. Aligner le code local sur le standard.
2. Retirer la ligne du tableau ci-dessus.
3. Retirer le test de divergence dans `tests/test_local_helpers_parity.py` (et ajouter à la place un test de parité positive).
4. Régénérer `_parity_snapshots.json` si l'alignement modifie les hashes attendus.

---

## §13 Plan de livraison MVP / V2 / V3

### 13.1 MVP (Livraison 1)

**Inclus** :
1. Ce design doc (validé Tech Lead avant tout code)
2. `.sdd/python/sdd_reverse/language_signatures.yml`
3. `.sdd/python/sdd_reverse/feat.reverse.template.md` (template FEAT isolé, ADV-9)
4. `.sdd/python/sdd_reverse/scan_legacy.py` + tests
5. `.sdd/python/sdd_reverse/inventory_builder.py` + tests (fingerprint full + core, ADV-1 ; lock TTL, ADV-2)
6. `.sdd/python/sdd_reverse/ui_unit_detector.py` + tests
7. `.sdd/python/sdd_reverse/db_schema_extractor.py` + tests
8. `.sdd/python/sdd_reverse/file_locks_local.py` + `atomic_write_local.py` (helpers isolés, ADV-2)
9. `.sdd/python/sdd_reverse/feat_structure_spec.py` (contrats partagés validateurs reverse, ADV-14)
10. `.sdd/python/sdd_reverse/_parity_snapshots.json` (snapshots hashes helpers `sdd_lib`, ADV-16)
11. `.sdd/python/sdd_reverse_scripts/reverse_inventory.py` (CLI déterministe Phase 1)
12. `.sdd/python/sdd_reverse_scripts/validate_reverse_feat.py` (validation FEAT reverse, ADV-5+14)
13. `.sdd/python/sdd_reverse_scripts/check_reverse_feat_for_full.py` (gate /sdd-full opt-in, ADV-6)
14. `.claude/agents/reverse-inventory.md`
15. `.claude/agents/reverse-tech-analyst.md` + `reverse-us-writer.md` + `reverse-feat-composer.md` (escalier 3a/3b/3c — remplace l'ex-extractor)
16. `.claude/commands/sdd-reverse-init.md`
17. `.claude/commands/sdd-reverse-inventory.md`
18. `.claude/commands/sdd-reverse.md`
19. `.sdd/rules/reverse-engineering.md`
20. `.sdd/loader.reverse.yml`
21. `.sdd/skills/starting-a-reverse-eng/SKILL.md`
22. Fixture `.sdd/python/tests/fixtures/legacy-webforms-minimal/`

**Exclu MVP** :
- Phase 2 tech audit (`reverse-tech-auditor`, `deps_graph_builder.py`)
- Phase 4 UI extraction (`reverse-ui-extractor`, `css_palette_extractor.py`, `ui_template_parser.py`)
- Orchestrateur `/sdd-reverse-full`
- Cookbook par langage
- Commande `/sdd-reverse-status`

### 13.2 V2

- `reverse-tech-auditor` + `deps_graph_builder.py` + enrichissement DB schema séparé (ADV-3)
- `sdd_reverse/merge_db_schema.py` (script déterministe union base + enrichment, ADV-3)
- `reverse-ui-extractor` + `css_palette_extractor.py` + `ui_template_parser.py`
- `/sdd-reverse-audit`, `/sdd-reverse-ui`, `/sdd-reverse-full`, `/sdd-reverse-status`
- `reverse_status.py` (marker `[REV]`/`[REV⚠️]`, ADV-6)
- Cookbook : `_generic-monolith`, `dotnet-webforms`, `dotnet-mvc`, `java-jee`, `javascript-jquery`, `php-procedural`, `delphi`

### 13.3 V3

- Mode `--evidence-mode strict` (rejet hard sans evidence, CI-grade)
- Round-trip validation : grep des phrases d'AC dans le code source pour vérifier qu'elles existent
- Re-run incrémental (delta detection sur fingerprint)
- Support VB6, Cobol, FoxPro
- Reverse engineering binaire-only (UI Automation + décompilation IL/DFM + capture vision)

---

## §14 Checklist auto-vérification

Avant déclaration "MVP done" :

- [ ] `git diff` sur les paths Annexe B = vide
- [ ] `python .sdd/python/sdd_admin/framework_smoke.py` exit 0
- [ ] `python .sdd/python/sdd_reverse_scripts/reverse_smoke.py` exit 0 (nouveau gate optionnel)
- [ ] Tous les nouveaux fichiers UTF-8, line endings cohérents (LF préféré), frontmatter YAML valide
- [ ] Design doc (CE fichier) validé Tech Lead AVANT toute écriture de code
- [ ] Pour la fixture `legacy-webforms-minimal` : `validate_reverse_feat.py --feat-path workspace/feats/1-*.md --json` exit 0 (≤ 3 itérations) — **PAS** `/feat-validate` (corrigé ADV-5)
- [ ] Enum `confidence` ∈ {high, medium, low} dans toutes les sorties (grep négatif sur `medium-high`)
- [ ] Items `low` flaggés en bannière dans la FEAT correspondante
- [ ] Confidence caps lus depuis `language_signatures.yml` (grep négatif `confidence_cap` hardcodé dans `sdd_reverse/*.py`)
- [ ] DB schema basique produit en Phase 1 ; dégradation §9.2 testée
- [ ] DB schema enrichment Phase 2 écrit fichier séparé `db-schema.enrichment.json` (jamais `db-schema.json`) — ADV-3
- [ ] `merge_db_schema.py` assertion `keys(merged) ⊇ keys(base)` ; refus si entity inconnue — ADV-3
- [ ] Aucun import `from sdd_lib` ou `from sdd_scripts` dans `sdd_reverse/` (grep négatif)
- [ ] `loader.reverse.yml` autonome, référencé uniquement par commandes/skill reverse, jamais par `loader.yml`
- [ ] `feat.reverse.template.md` présent dans `sdd_reverse/` (ADV-9) ; absence → STOP `[REVERSE_TEMPLATE_MISSING]`
- [ ] IDs `U-N` stables (test cross-run identique) ; fingerprint `core` testé sur renommage 1 fichier (ADV-1)
- [ ] `legacyMtimeMax` enregistré dans `inventory.json` ; `[REVERSE_INVENTORY_STALE]` émis si mtime > legacyMtimeMax (ADV-1)
- [ ] Lock `.alloc.lock` TTL 30s + recovery stale + format `{agent_id, pid, ts_unix}` (ADV-2)
- [ ] Lock élargi à `read_max_n → write FEAT → update _featAllocations → release` (ADV-2)
- [ ] `Name` anti-collision avec suffixe `-Legacy` testé contre FEAT humaine existante (ADV-4)
- [ ] `check_reverse_feat_for_full.py` exit codes corrects + flag `--allow-reverse-low` testé (ADV-6)
- [ ] `loader.reverse.yml` §7.1 : `reverse-tech-auditor.writes` n'inclut PAS `db-schema.json` (ADV-17)
- [ ] `resolve_name_collision` testé sur deux U-N intra-run avec même `suggestedName` (ADV-13)
- [ ] `_allocatedNames` mis à jour atomiquement avec `_featAllocations` (ADV-13)
- [ ] Commentaire `<!-- REVERSE-GATE: ... -->` présent dans chaque FEAT générée (ADV-15)
- [ ] Fingerprint `core` basé sur bytes normalisés EOL, **pas LOC** (ADV-11) ; test cross-OS Windows/Linux identique
- [ ] `psutil` dépendance **optionnelle**, fallback TTL silencieux (ADV-10) ; `requirements.txt` reverse sans `psutil`
- [ ] Caveat Windows PID recycling documenté + test mock pid recyclé
- [ ] Test parité `validate_reverse_feat` vs `validate_readiness` (ADV-14) ; module `feat_structure_spec.py` partagé local
- [ ] Tests parité helpers locaux vs `sdd_lib/*` originaux (ADV-16) ; snapshot hashes dans `_parity_snapshots.json`
- [ ] Fingerprint normalisation strip BOM UTF-8/16 + EOL (ADV-20) ; test 3 fichiers identiques byte-à-byte sauf BOM/EOL → même fingerprint
- [ ] `_allocatedNames` présent dans schéma `inventory.json` §5.1 + dans le code (ADV-19)
- [ ] §6 tableau inter-phases référence `db-schema.enrichment.json` + `db-schema.merged.json`, plus `db-schema.json enrichi` (ADV-18)
- [ ] `inventory_builder.py` initialise toujours `_allocatedNames: {}` + `_featAllocations: {}` à la création initiale (ADV-23)
- [ ] `--use-cache` rejette caches sans `schemaVersion ≥ 1` ou sans `_allocatedNames` → refresh forcé + INFO `[REVERSE_INVENTORY_SCHEMA_STALE]` (ADV-23)
- [ ] Test `test_reverse_gate_no_interference.py` : FEAT avec/sans `<!-- REVERSE-GATE -->` donne même output `validate_readiness.py` (ADV-22)
- [ ] Sync `frontmatter.confidence` ↔ `comment.confidence` enforcée par `validate_reverse_feat.py` → `[REVERSE_GATE_DRIFT]` (ADV-22)
- [ ] Tests Python ≥ 80% coverage sur `sdd_reverse/*`
- [ ] Test isolation §12.4 vert (hashes framework inchangés)

---

## §15 Mitigations V2/V3 — attaques différées

Les 2 attaques adversariales suivantes ne sont **pas** corrigées en MVP. Elles sont tracées ici pour livraison V2/V3.

### 15.1 ADV-7 — Invariants reverse non enforcés en CI (V2)

**Problème** : `INVARIANTS.yml` du framework SDD_Pro est déclaré intouchable (Annexe B). Les nouveaux contrats reverse (`loader.reverse.yml` autonome, `sdd_reverse/` sans import de `sdd_lib`, FEAT reverse avec evidence obligatoire) ne peuvent pas y être inscrits. Conséquence : ces invariants ne sont pas enforcés par `test_invariants_manifest.py` standard et peuvent régresser silencieusement à chaque release SDD_Pro qui touche aux modules adjacents.

**Mitigation V2** :
- Créer `.sdd/INVARIANTS.reverse.yml` (format miroir de `INVARIANTS.yml`) avec les contrats reverse :
  - `reverse-isolation` (sdd_reverse/ n'importe rien de sdd_lib)
  - `reverse-loader-autonomous` (loader.reverse.yml référencé uniquement par commandes/skill reverse)
  - `reverse-evidence-required` (chaque AC/SFD/BR de FEAT reverse a son commentaire evidence)
  - `reverse-confidence-enum-strict` (uniquement `high|medium|low`)
  - `reverse-lock-format-valid` (.alloc.lock contient `{agent_id, pid, ts_unix}`)
- Créer `.sdd/python/sdd_reverse_scripts/reverse_smoke.py` qui vérifie chaque enforcer (script déterministe, 0 token).
- Documenter dans la skill `starting-a-reverse-eng` : "Avant chaque release, lancer `python .sdd/python/sdd_reverse_scripts/reverse_smoke.py` en plus de `framework_smoke.py`".
- **V3** : proposer un PR officiel sur `test_invariants_manifest.py` pour qu'il accepte un paramètre `--manifest` (lecture multi-manifests). Décision Tech Lead seule.

### 15.2 ADV-8 — Fichiers > 100k LOC + paths Unicode/espaces (V2)

**Problème** : `scan_legacy.py` peut tenter un Read complet sur un fichier de 120k LOC (OOM ou timeout). Les paths avec espaces ou Unicode (`données/fiche_élève.aspx`) peuvent casser si l'OS n'est pas UTF-8 strict.

**Mitigation V2** :
- Schéma `language_signatures.yml` étendu (champ optionnel) :
  ```yaml
  languages:
    - id: aspx-webforms
      ...
      max_file_size_kb: 500    # au-delà : sampling premiers/derniers 200KB + bypass agent
      sampling_strategy: head_tail
  ```
- `scan_legacy.py` :
  - Avant Read complet, `os.path.getsize` > `max_file_size_kb * 1024` → mode sampling (head 200KB + tail 200KB)
  - Émettre INFO `[REVERSE_LARGE_FILE_SAMPLED]` dans `inventory.json.warnings[]`
- Paths Unicode :
  - Tous les `Path` manipulés via `pathlib.Path` avec `.resolve()` + `.as_posix()` pour normalisation
  - Read avec `errors='replace'` + log `[REVERSE_FILE_UNREADABLE]` skip si UnicodeDecodeError
  - Tests fixture avec paths Unicode (`tests/fixtures/legacy-unicode-paths/`)

### 15.3 ADV-12 — Conflits de types dans merge_db_schema (V2)

**Problème** : `merge_db_schema.py` (V2) ne traite pas le cas où `enrichment.json` ajoute un `addedField` avec un type **contradictoire** avec celui du base. Exemple : base déclare `Username: nvarchar(50)` (depuis `CreateSchema.sql`), enrichment déclare `Username: text` (déduit du code `DataAccess.cs` qui utilise `string` côté C#).

**Mitigation V2 — stratégie de résolution conservatrice** :
1. **Détection** : pour chaque `addedField` dont `entity` + `field.name` existent déjà dans base :
   - Si `field.type == base.field.type` → ignore (idempotent)
   - Si types différents → conflit
2. **Résolution** : par défaut, **base wins** (SQL DDL est la source de vérité la plus stricte). L'enrichment est rejeté pour ce field seul.
3. **Émission** : INFO `[REVERSE_ENRICHMENT_TYPE_CONFLICT]` dans le rapport merge :
   ```
   INFO: merge_db_schema — type conflict on User.Username
   CAUSE: base=nvarchar(50) (Scripts/CreateSchema.sql:7) vs enrichment=text (App_Code/DataAccess.cs:18)
   FIX: base wins by default. Si enrichment correct, éditer base manuellement ou ajouter override `--force-enrichment-on User.Username`.
   ```
4. **Flag CLI optionnel** : `--force-enrichment-on {Entity.field}` pour outrepasser cas par cas.
5. **Tests** : fixtures de conflit dans `tests/fixtures/db-schema-conflicts/`.

### 15.4 ADV-21 — Désync `_allocatedNames` ↔ disque (V2)

**Problème** : `_allocatedNames` est un cache mémoire de Phase 3 persisté dans `inventory.json`. Si un Tech Lead supprime manuellement `workspace/feats/{n}-{Name}.md` sans nettoyer `inventory.json`, le prochain `/sdd-reverse {U-N}` voit `_allocatedNames[Name] = U-3` (stale) et applique un suffixe `-Legacy-U-N` injustifié.

**Mitigation V2** :
1. `validate_reverse_feat.py --reconcile` : nouveau flag qui parcourt `_allocatedNames`, vérifie l'existence sur disque de chaque FEAT, et nettoie les entrées orphelines.
2. Hook informationnel dans Phase 3 : avant résolution Name, vérifier `os.path.exists(workspace/feats/{n}-{Name}.md)` pour chaque entrée `_allocatedNames`. Si orphan détecté → WARN + suggestion `--reconcile`. (Classe `[REVERSE_ALLOCATED_NAME_STALE]` retirée — audit MA-7 : si ce hook V2 est implémenté, ré-ajouter la classe en §6 de la règle EN MÊME TEMPS que l'émetteur.)
3. Documentation : skill `starting-a-reverse-eng` rappelle que la suppression manuelle d'une FEAT reverse exige `--reconcile` avant le prochain `/sdd-reverse`.

**Pourquoi V2 et pas MVP** : impact = suffixe `-Legacy` inutile (cosmétique, pas correctness). Le Tech Lead voit immédiatement la dérive et peut éditer `inventory.json` à la main si urgence MVP.

### 15.5 Tracking

Issues à créer (V2 milestone) :
- `[REVERSE-V2-001]` Implémenter INVARIANTS.reverse.yml + reverse_smoke.py (ADV-7)
- `[REVERSE-V2-002]` Sampling gros fichiers + paths Unicode (ADV-8)
- `[REVERSE-V2-003]` Conflict resolution merge_db_schema (ADV-12)
- `[REVERSE-V2-004]` Reconcile `_allocatedNames` ↔ disque (ADV-21)
- `[REVERSE-V2-005]` Phase 2 tech-audit (déjà planifié V2)
- `[REVERSE-V2-006]` Phase 4 UI extraction (déjà planifié V2)
- `[REVERSE-V2-007]` Cookbook par langage (déjà planifié V2)

---

## Annexe D — Chemin base de données : Phase 0 et vagues (2026-08-26)

> Le corps de ce document décrit le reverse **de code** (escalier 3a→3b→3c). Le
> reverse **base de données** partage les invariants (evidence, confidence
> min-monotone, no-spawn, REVERSE-GATE) mais a une forme propre, décrite ici.
> SSoT opérationnelle : `@.sdd/docs/reverse-db-audit-2026-07.md`.

### D.1 Pourquoi une Phase 0

Le chemin code monte en altitude par barreaux (analyse → US → FEAT). Le chemin
base de données n'a pas besoin du barreau bas — **le corps de l'objet SQL *est*
l'analyse**. Mais cette économie ne tient que pour un objet **feuille et
autonome**. Dès qu'il y a composition (procédure imbriquée, SQL dynamique,
trigger en cascade), lire un corps isolément produit une User Story fausse mais
crédible.

La Phase 0 remplace le barreau manquant par une **compréhension globale
préalable**, construite une fois et partagée :

```
Phase 1 introspection READ-ONLY      -> db-introspection.json + db-schema.json
   Phase 0.A  déterministe, 0 token  -> FAITS   (CRUD, graphe, vagues, contextVersion)
   Phase 0.B  reverse-db-architect   -> HYPOTHÈSES (glossaire, domaines, rôles, risques)
        => db-context.json (SSoT versionné) + db-context/ (arbre découpé + packs)
```

### D.2 Le contrat faits ≠ hypothèses

| Branche | Producteur | Peut devenir un AC ? | Garantie |
|---|---|:---:|---|
| `facts` | scripts déterministes | **oui** (evidence `fichier:ligne`) | seule source de faits |
| `hypotheses` | agent architecte | **jamais** | écrit un fichier séparé, fusionné par script |

L'architecte ne peut pas écraser un fait **par construction** : il écrit
`db-context.hypotheses.json`, et `db_context_build.py --merge-hypotheses` ne
recopie que les cinq clés autorisées. Même patron que
`db-schema.enrichment.json` (ADV-3). Un `contextVersion` périmé fait **échouer**
la fusion plutôt qu'attacher une lecture obsolète à des faits frais.

### D.3 Context slicing — le pack

Aucun agent ne lit `db-context.json` en entier. `db_context_slice.build_pack()`
produit, par objet, `db-context/packs/{schema}.{objet}.md` :

1. l'objet — contrat, signaux, matrice CRUD, evidence ;
2. la structure des **seules** tables qu'il touche (colonnes, clés, `CHECK`) ;
3. ce qu'il appelle, profondeur ≤ 2, avec le **résumé déjà écrit** par la vague
   précédente quand il existe (sinon les effets déterministes) ;
4. ses appelants ;
5. les hypothèses de l'architecte le concernant, marquées `kind: hypothesis`.

Budget borné (`ContextPackBudget`, défaut 14 000 octets). Ordre de retrait
déclaré — `callers`, `hypotheses`, `tables`, `callees` — et **tout retrait est
annoncé dans le pack**, pour qu'un agent qui a reçu une vue tronquée baisse sa
confidence en connaissance de cause.

> La règle d'isolation (§1) n'est **pas** relâchée : l'agent lit toujours
> exactement une chose. Le pack est le canal *sanctionné* du contexte transitif,
> calculé plutôt que laissé au jugement de l'agent.

### D.4 Ordonnancement par vagues

`db_wave_planner.plan_waves()` :

1. résout chaque `callsProcs` contre le catalogue — un nom absent ou **ambigu**
   reste `unresolvedCallees` (jamais résolu au hasard : un faux arc réordonne
   tout le plan) ;
2. condense les composantes fortement connexes (Tarjan itératif — l'auto-appel
   et la récursion mutuelle sont réels en T-SQL) ;
3. tri topologique sur le graphe condensé → `waves[]`.

Propriété garantie : **tout appelé résolu est analysé dans une vague strictement
antérieure à son appelant** (hors cycle, où les membres partagent la vague).

Le débit ne baisse pas : le parallélisme borné (`MaxParallel`) joue **à
l'intérieur** d'une vague ; il n'y a qu'une barrière entre deux vagues, où
l'orchestrateur — jamais un agent — écrit les résumés dans
`db-context.findings` et régénère les packs suivants. Les agents n'écrivant que
leur propre US, les écritures restent disjointes : aucun verrou supplémentaire.

Une composante récursive de taille > 1 est confiée **d'un bloc** à un seul
agent, tous les corps du cycle dans son pack, et sort plafonnée à `medium`.

### D.5 Spécialistes et routage de tier

| Famille | Agent | Question posée à l'objet |
|---|---|---|
| procédure | `reverse-sql-analyst` | quelle opération, quels effets, quelles préconditions ? |
| fonction | `reverse-sql-function-analyst` | quel calcul réutilisable, quels cas limites ? |
| vue | `reverse-sql-view-analyst` | quelle information exposée, quels filtres cachés ? |
| trigger | `reverse-sql-trigger-analyst` | quel événement, quelle règle, quel rejet ? |

Socle d'expertise SQL commun : `@.sdd/rules/db-reverse-tsql.md`. Ce qui justifie
un agent distinct est **l'angle**, jamais le type SQL en soi.

`db_tier_router.tier_for()` grade chaque objet — `none` (0 token) / `fast` /
`balanced` / `deep` — selon ce que le corps **cache** : SQL dynamique, curseur,
récursion, appelé non résolu, orchestration (≥ 2 appels), fan-in élevé, volume.
Il retourne un **tier**, jamais un nom de modèle : la résolution appartient au
provider actif (`.sdd/providers/*.yaml`).

### D.6 Le faux vert que tout ceci ferme

Avant 2026-08-26, `complexity_reasons()` pesait branches, SQL dynamique,
erreurs, curseurs, volume, écritures et largeur de contrat — **jamais les
appels**. Un orchestrateur de 38 lignes sans branche déléguant sa règle métier à
six procédures était donc classé `simple` : User Story par template, aucun LLM,
confidence `high` faute de quoi que ce soit qui la dégrade, et **passage de la
REVERSE-GATE sans revue humaine**.

Déléguer n'est pas être simple. Désormais : tout appel force l'analyse LLM ; un
appelé non résolu ou une récursion plafonnent la confidence à `medium`, qui
remonte par min-monotonie jusqu'à la FEAT et déclenche la revue.

### D.7 Réserve

Tout ce qui précède est validé **hors ligne** (`tests/test_db_context.py`,
catalogues synthétiques, Tarjan vérifié contre une référence par force brute sur
300 graphes aléatoires). Les seuils — profondeur de pack 2, budget 14 000,
fragmentation de clustering 0.50 — sont calibrés sur corpus synthétiques et
devront être revus après le premier run contre une base réelle.

---

## Annexe A — Conformité SDD_Pro standard FEAT

Toute FEAT produite par `reverse-feat-composer` (3c) DOIT respecter :

1. **Frontmatter étendu reverse** :
   ```yaml
   ---
   generated-by: sdd-reverse              # marqueur d'origine
   legacy-sources: [<path1>, <path2>]     # liste des fichiers evidence
   confidence: high | medium | low        # enum strict
   extraction-date: <ISO-8601 UTC>
   language-detected: <id de language_signatures.yml>
   source-unit: U-N                       # mapping vers inventory.json
   ---
   ```
2. **Sections obligatoires** (ordre figé) : `## Actors`, `## Functional Needs`, `## Functional Deliverables`, `## Business Rules`, `## Acceptance Criteria`, `## Project Config`.
3. **IDs stables** : `SFD-N`, `FD-N`, `BR-N`, `AC-N`. Jamais réordonnés. Trous autorisés (si un item est rejeté pour evidence manquante, son ID est skippé, pas réutilisé).
4. **AC au format Given/When/Then** strict (regex `^Given .+, when .+, then .+\.$` ou multi-lignes équivalent).
5. **Commentaires evidence** : `<!-- evidence: path:Lstart-Lend -->` immédiatement après chaque item (SFD/FD/BR/AC).
6. **Commentaires confidence** : `<!-- confidence: high|medium|low -->` après evidence.
7. **Bannière humaine** si `confidence: low` ou `[REVERSE_FEAT_VALIDATE_FAILED]` :
   ```markdown
   > ⚠️ FEAT générée par reverse engineering avec confiance LOW.
   > Revue humaine obligatoire avant /sdd-full.
   > Raison : {raison machine-lisible, ex. REVERSE_FEAT_VALIDATE_FAILED après 3 itérations}
   ```
8. **Commentaire REVERSE-GATE machine-parseable** (ADV-15, **toujours présent** quelle que soit la confidence) :
   ```html
   <!-- REVERSE-GATE: confidence={high|medium|low} ; allow-sdd-full={true|false} ; reason={code|""} -->
   ```
   - Insérée immédiatement après le `# FEAT N — Titre` (1ère ligne après le H1)
   - `allow-sdd-full=true` ssi `confidence=high`
   - Parseable par grep/sed/awk pour outillage CI sans charger YAML
   - Source de vérité reste le frontmatter `confidence` (le commentaire est dérivé)
   - **Non-interférence avec parsing (ADV-22)** : ce commentaire HTML est invisible aux parsers Markdown standard (rendu HTML strip les commentaires). Les parsers SDD_Pro existants (`validate_readiness.py`, `/sdd-full`, etc.) cherchent les sections via regex `^## ` (ligne entière commençant par `## `). Un commentaire HTML sur sa propre ligne n'est jamais matché. **Test obligatoire MVP** : `test_reverse_gate_no_interference.py` vérifie qu'une FEAT minimaliste avec et sans le commentaire `<!-- REVERSE-GATE -->` donne le **même résultat** au parser `validate_readiness.py` (output JSON identique sur l'extraction des sections). Si futur changement parser SDD_Pro casse cette hypothèse, le test rouge alerte immédiatement.
   - **Synchronisation auto frontmatter ↔ commentaire** : `validate_reverse_feat.py` vérifie l'alignement (`frontmatter.confidence` doit matcher `comment.confidence` ; sinon ERROR `[REVERSE_GATE_DRIFT]`). Empêche désync silencieuse si humain édite l'un sans l'autre.

---

## Annexe B — Isolation : fichiers framework intouchables

**Aucune édition ni suppression** autorisée sur :

```
.claude/agents/**            (existants seulement ; création OK)
.claude/commands/**          (existants seulement ; création OK)
.sdd/rules/**             (existants seulement ; création OK)
.sdd/skills/**            (existants seulement ; création OK)
.sdd/python/sdd_lib/**
.sdd/python/sdd_scripts/**
.sdd/python/sdd_admin/**
.sdd/python/sdd_hooks/**
.sdd/loader.yml
.sdd/INVARIANTS.yml
.claude/CLAUDE.md
.claude/settings.json
.claude/settings.local.json
.sdd/docs/**              (existants seulement ; création OK)
bootstrap.py
workspace/console/**
```

**Création de nouveaux fichiers** autorisée dans tous les répertoires ci-dessus (cohabitation).

Toute tentative de modification d'un fichier listé déclenche `[REVERSE_ISOLATION_VIOLATION]` + STOP + escalade Tech Lead.

---

## Annexe C — Glossaire

| Terme | Définition |
|---|---|
| **Legacy** | Code source d'un système existant à reverse engineer, déposé dans `workspace/old/{P}/`. |
| **Unité fonctionnelle** | Intention utilisateur cohérente détectée dans le legacy (cf. D2). 1 unité = 1 FEAT. |
| **U-N** | Identifiant stable d'une unité fonctionnelle (`U-1`, `U-2`, …). Alloué Phase 1, jamais renuméroté. |
| **Evidence** | Pointeur file:line vers le code legacy qui justifie un item de la FEAT. Format `<!-- evidence: path:Lstart-Lend -->`. |
| **Confidence** | Niveau de fiabilité d'un item ou d'une FEAT. Enum strict `high | medium | low`. |
| **Confidence cap** | Plafond imposé par langage (cf. `language_signatures.yml`). Cap effectif = min(cap langage, estimation agent, dégradation §9.2). |
| **Bias toward present** | Discipline anti-hallucination : ne pas inventer ; si non visible dans le code, non documenté. |
| **`loader.reverse.yml`** | Manifeste reads/writes autonome pour les 16 agents reverse (10 code + 6 db). Ne touche jamais `loader.yml`. |
| **Phase atomique** | Phase reprenable, réexécutable, qui écrase son output (pas de merge). |

---

## §13 Couche de synthèse — Phase 3.7 (additive, non-cassante)

> Ajout v0.8.0. Récupère de Reversa les **vues système** que l'escalier
> `3a→3b→3c` ne produit pas (C4, ERD, synthèse exécutive), **sans toucher**
> à l'escalier ni au contrat FEAT.

### 13.1 Principe (pare-feu)

La couche de synthèse est un **nouvel étage AU-DESSUS de 3c** : un consommateur
**strictement en lecture seule** des artefacts déterministes Phase-1/2
(`inventory.json`, `deps-graph.json`, `db-schema.merged.json`). Elle :

- ne lit **jamais** le code legacy (l'isolation d'altitude est préservée — seul
  3a lit le code) ;
- n'altère **jamais** l'escalier `3a/3b/3c` ni les FEAT ;
- écrit **uniquement** sous `workspace/old/{P}/.sys/synthesis/` — **jamais**
  sous `workspace/feats/`, donc `/sdd-full` ne voit aucun de ces artefacts.

Retirer la couche = le pipeline d'origine fonctionne à l'identique.

### 13.2 Commande & script

| Élément | Valeur |
|---|---|
| Commande | `/sdd-reverse-synth {P} [--doc-level essentiel\|complet\|detaille] [--only c4,erd,soul] [--json]` |
| Spawns | `[]` — **no-spawn**, déterministe (0 token) |
| Script | `.sdd/python/sdd_reverse_scripts/reverse_synth.py` (CLI) + `sdd_reverse/synthesis.py` (lib pure) |
| Sorties | `.sys/synthesis/{c4-context,c4-containers,c4-components,erd-complete,soul}.md` + `manifest.json` |

`--doc-level` est le **bouton d'économie de contexte** (emprunt Reversa) :
`essentiel` = C4-contexte + ERD + soul ; `complet` = + C4 conteneurs/composants ;
`detaille` = + table de détail par composant.

### 13.3 Sources → artefacts & confiance

| Artefact | Source déterministe | Confiance |
|---|---|---|
| `c4-*.md` (Mermaid `graph TB`) | `deps-graph.json` (arêtes internes) + `inventory.json` (unités) | `high` (arêtes parsées) |
| `erd-complete.md` (Mermaid `erDiagram`) | `db-schema.merged.json` (ou base) | `high` (DDL) ; `medium` si `deduced` |
| `soul.md` (synthèse exécutive) | `inventory.json` + `db-schema` + `deps-graph` | objectif **inféré** `medium` ; entités rankées par degré FK ; contraintes EOL/cycles = faits observés |

Confiance dans l'enum reverse strict `{high, medium, low}`. **Aucun git-mining,
aucune décision « fondatrice » inventée** (lacune assumée et signalée dans `soul.md`).

### 13.4 Mémoire / observabilité

`manifest.json` est un **enregistrement dérivé** (régénéré à chaque run) : quels
artefacts produits, depuis quelles sources, répartition de confiance. **Pas une
SSoT mutable** — la vérité reste les artefacts sur disque, comme `reverse_status.py`
qui dérive l'état des fichiers présents. Idempotence : chaque catégorie régénérée
nettoie ses sorties périmées (un `--doc-level` inférieur ne laisse pas d'artefact
de niveau supérieur).

### 13.5 Hors périmètre (option ultérieure)

Un agent narratif `reverse-soul` / `reverse-architect` (LLM) pourra enrichir
`soul.md` et le C4 d'un texte explicatif. **Volontairement non inclus** dans le
cœur déterministe pour préserver reproductibilité et coût zéro-token. Items de la
liste Reversa **écartés** : extraction UI visuelle par screenshots (casse la
discipline d'evidence `file:line` — pas d'evidence pour une image).

---

**FIN DESIGN DOC v0.1.0 — en attente validation Tech Lead.**
