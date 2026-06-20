# Règle — Reverse Engineering (anti-derive REVERSE, v1.0)

> **Statut** : Nouvelle règle (workflow reverse engineering, isolée du pipeline SDD_Pro principal).
> **Master prompt** : `@.claude/docs/reverse-engineering-master-prompt.md`
> **Design doc** : `@.claude/docs/reverse-engineering-workflow.md`
> **Périmètre** : règle lue par les 4 agents reverse (`reverse-inventory`, `reverse-tech-auditor`, `reverse-functional-extractor`, `reverse-ui-extractor`) + 6 commandes `/sdd-reverse-*` + scripts Python `sdd_reverse/`.
> **Anti-derive** : aucune référence depuis les agents/commandes/règles SDD_Pro existants. Isolation stricte.

## TOC

- §1 — Principe load-bearing (bias toward present, evidence-driven)
- §2 — Confidence calibrée par langage (cap par tier de fiabilité)
- §3 — Format obligatoire : `<!-- evidence: -->` + `<!-- confidence: -->`
- §4 — Anti-derive REVERSE (5 bullets stricts)
- §5 — Classification des erreurs `[REVERSE_*]` (16 classes, taxonomie SDD_Pro)
- §6 — Workflow d'exécution par phase
- §7 — Compatibilité aval avec `/feat-validate` et `/sdd-full`
- §8 — Idempotence et hash d'unité
- §9 — Enforcement et auto-checks

---

## 1. Principe load-bearing

Le reverse engineering produit des FEATs qui guident le re-développement complet d'une application. **Une FEAT incorrecte = des semaines de re-développement gaspillées**. La règle d'or :

> **Si le code legacy ne le montre pas, la FEAT ne le décrit pas.**

Cette discipline (« bias toward present », empruntée à superpowers v5.1) impose :

1. **Lecture stricte** : chaque AC/SFD/BR vient d'une observation concrète du code (`file.ext:lines`).
2. **Pas d'invention** : même si l'agent suppose qu'une feature « devrait » exister (login sans recovery password par ex.), il ne la documente pas si elle n'est pas dans le code.
3. **Faux positifs tolérés, faux négatifs interdits** : mieux vaut un AC manquant signalé en confidence:low qu'un AC inventé en confidence:high.
4. **Pas de proposition d'amélioration métier** : la sortie reverse décrit l'existant tel quel. Améliorations = nouvelle FEAT manuelle après reverse, hors scope du workflow.

---

## 2. Confidence calibrée par langage

Chaque langage detecté impose un **cap de confidence** sur les items générés. L'agent ne peut JAMAIS émettre `confidence: high` si le langage source est en cap medium ou low.

| Tier | Langages | Cap confidence | Justification |
|---|---|---|---|
| **A — fortement structuré** | .NET MVC, Blazor, Java Spring, Java JEE moderne, PHP framework (Laravel/Symfony), Python Django | `high` possible | Conventions explicites, séparation MVC, annotations claires |
| **B — structuré** | ASP.NET WebForms, Delphi avec DFM, Ruby on Rails | `medium-high` (high autorisé si evidence forte) | UI déclarative parsable + code-behind localisable |
| **C — semi-structuré** | jQuery / JavaScript classique, PHP procédural, Java Swing, C# console legacy | `medium` max | Mix HTML/code, intentions implicites, peu de conventions |
| **D — exotique / inconnu** | VB6, Cobol, Visual FoxPro, langages non reconnus | `low` forcé | Hors confort de l'agent, hallucination probable |

**Bannière humaine obligatoire** : si **≥ 1 item** de la FEAT générée porte `confidence: low`, une bannière en tête signale la revue requise (cf. §3.2).

---

## 3. Format obligatoire

### 3.1 Evidence citation

Chaque AC, SFD, FD, BR de la FEAT générée DOIT être suivi d'un commentaire HTML :

```markdown
- **AC-1** : Given un utilisateur connecté, When il accède à /Customers/List, Then la liste s'affiche paginée par 10
  <!-- evidence: Customers/List.aspx.cs:45-60 -->
  <!-- confidence: high -->
  <!-- covers: SFD-1, FD-1 -->
```

Règles :
- `evidence:` est **obligatoire** sur AC, SFD, FD, BR. Pas d'evidence = item rejeté (l'agent itère).
- Format : `evidence: {path}:{Lstart}-{Lend}` (path relatif au project root legacy, lignes 1-indexées).
- Si plusieurs fichiers contribuent : `evidence: {path1}:{lines}, {path2}:{lines}` ou plusieurs commentaires successifs.
- Le commentaire `evidence:` reste en anglais (convention code, parsable par scripts d'audit).

### 3.2 Confidence per item

Chaque item porte un commentaire confidence :

```markdown
<!-- confidence: high|medium|low -->
```

- `high` : pattern clair, conventions standard, ambiguïté nulle
- `medium` : intention probable mais quelques ambiguïtés résiduelles
- `low` : intention déduite, plusieurs interprétations possibles, **revue humaine requise**

**Si ≥ 1 item est `low`**, ajouter en tête de la FEAT (sous le frontmatter) :

```markdown
> ⚠️ **Revue humaine requise** — Cette FEAT contient {N} item(s) en `confidence: low`
> (langage : {langue} ou intention ambiguë). Lire les commentaires `<!-- confidence: low -->`
> et compléter / corriger avant `/sdd-full {n}`.
```

### 3.3 Frontmatter complet

```yaml
---
title: {label}
version: 1
created: {YYYY-MM-DD}

generated-by: sdd-reverse
extraction-date: {ISO-8601 UTC}
language-detected: {language-id}
legacy-sources:
  - {path1 relatif workspace/old/{P}/}
  - {path2 relatif workspace/old/{P}/}
unit-id: {unit-NNN}
unit-hash: sha256:{hex64}
confidence: {high|medium|low}
confidence-low-items: {N}
human-review-required: {true|false}
---
```

`unit-hash` : sha256 du contenu concaténé des fichiers cités en `legacy-sources` (triés par path). Permet l'idempotence (cf. §8).

---

## 4. Anti-derive REVERSE (5 bullets stricts)

Les 4 agents reverse appliquent strictement :

1. **Bias toward present** — Décrire UNIQUEMENT ce qui est observable dans le code legacy. Pas d'extrapolation, pas de « ça devrait avoir », pas de « les bonnes pratiques voudraient ».
2. **Evidence-driven** — Aucun AC/SFD/BR sans citation `<!-- evidence: file:lines -->`. Pas d'evidence ⇒ item rejeté avant écriture, l'agent itère (max 2 fois).
3. **No invention métier** — Pas de proposition d'amélioration (« on pourrait ajouter… », « ce serait mieux de… »). Le workflow décrit l'existant ; les améliorations sont des FEATs greenfield ultérieures.
4. **No spawn d'agent** — Les agents reverse ne spawn jamais d'autre agent. Toutes les invocations cross-phase passent par les commandes `/sdd-reverse-*` orchestrantes.
5. **Lecture sélective stricte** — Un agent ne lit JAMAIS plus de fichiers que nécessaire :
   - `reverse-inventory` : inventory-raw.json + units-candidates.json + échantillon 5-10 fichiers représentatifs (pas tous)
   - `reverse-functional-extractor` : 1 unité ciblée → fichiers en evidence de cette unité uniquement (5-15 typiquement)
   - `reverse-ui-extractor` : 1 unité + templates legacy de cette unité

**Doute irrécupérable** → STOP + ERROR 3L au format `[REVERSE_*]` (cf. §5).

---

## 5. Classification des erreurs `[REVERSE_*]`

16 classes alignées sur la taxonomie SDD_Pro (`rules/error-classification.md`). Format : `[CLASS]` dans la ligne `CAUSE:` d'un bloc ERROR 3L (ERROR/CAUSE/FIX).

| Préfixe | Phase | Sévérité | Sens |
|---|---|---|---|
| `[REVERSE_PRECONDITION]` | toutes | critical | workspace/old/{P}/ absent ou vide |
| `[REVERSE_SCAN_FAILED]` | 1a | critical | scan_legacy.py exit ≠ 0 (I/O, YAML invalide) |
| `[REVERSE_NO_LANGUAGE]` | 1a | critical | Aucun langage détecté (legacy vide ou exotique non reconnu) |
| `[REVERSE_INVENTORY_AMBIGUOUS]` | 1b | critical | Agent ne peut pas trancher fusion/split d'unités |
| `[REVERSE_NO_INTENT]` | 3 | critical | Unité ciblée sans intention utilisateur claire (fichier de config sans UI, etc.) |
| `[REVERSE_UNIT_NOT_FOUND]` | 3 | critical | `unit-id` passé en arg absent de inventory.json |
| `[REVERSE_FEAT_INVALID]` | 3 | critical | FEAT générée échoue `/feat-validate` après 2 itérations |
| `[REVERSE_FEAT_NUMBER_TAKEN]` | 3 | critical | `workspace/input/feats/{n}-*.md` déjà existant (collision numérotation) |
| `[REVERSE_EVIDENCE_MISSING]` | 3 | warning | Item généré sans evidence → rejeté du draft, agent itère |
| `[REVERSE_CONFIDENCE_DEGRADED]` | 3 | info | Langage à confidence_cap medium/low — bannière humaine ajoutée |
| `[REVERSE_LANGUAGE_UNKNOWN]` | 1a, 3 | info | Fichiers en langage non reconnu — confidence forcée low |
| `[REVERSE_DB_NOT_DETECTED]` | 2 | warning | Aucun schéma DB détectable (legacy sans .sql ni ORM) |
| `[REVERSE_TECH_AUDIT_SKIPPED]` | 2 | info | Phase 2 skippée par `--skip-audit` |
| `[REVERSE_UI_EXTRACTION_PARTIAL]` | 4 | warning | UI mockup généré mais composants non identifiés → fallback wireframe |
| `[REVERSE_HASH_MISMATCH]` | 3 (re-run) | info | unit-hash diff vs FEAT existante → re-écriture déclenchée |
| `[REVERSE_OUTPUT_LANGUAGE]` | 3 | info | Output forcé en français (D6 master prompt) — informational |

### Format ERROR 3L canonique

```
ERROR: reverse-{agent} {phase} — {résumé court}
CAUSE: [REVERSE_{CLASS}] {détail 1L observable}
FIX: {action 1L exécutable par le Tech Lead}
```

Exemple :
```
ERROR: reverse-functional-extractor unit-001 — extraction blocked
CAUSE: [REVERSE_NO_INTENT] Customers/Helpers.aspx contains no user-facing UI (only utility methods)
FIX: skip this unit OR add it to inventory.json exclusion list, then relaunch /sdd-reverse unit-001
```

---

## 6. Workflow d'exécution par phase

### Phase 1 — Inventory (`/sdd-reverse-inventory`)

```
1. Préflight : workspace/old/{P}/ existe + non vide
2. scan_legacy.py (Python, 0 token) → inventory-raw.json
3. inventory_builder.py → enriched inventory (pages, entry points, modules)
4. ui_unit_detector.py → units-candidates.json (pre-détection patterns évidents)
5. Agent reverse-inventory : synthèse humaine + arbitrage fusion/split
   → inventory.md (lisible) + inventory.json (machine, source de vérité Phase 3)
6. STOP — Tech Lead valide avant Phase 3
```

### Phase 3 — Functional extraction (`/sdd-reverse {unit-id}`)

```
1. Préflight : inventory.json présent + unit-id valide
2. Hash check : workspace/input/feats/{n}-{Name}.md déjà présent ?
   - Si oui ET unit-hash inchangé → skip silencieux (idempotence)
   - Si oui ET unit-hash diff → re-write avec warning
3. Context budget HARD-GATE (cap 40 KB par invocation)
4. Lecture sélective : 1 unité + fichiers en evidence (5-15 typiquement)
5. Analyse intention métier (LLM Opus 4.7)
6. Génération FEAT.md (frontmatter + sections SDD_Pro + meta reverse)
7. Auto-validation : /feat-validate {n} --json (exit 0 requis)
8. Si échec → itère STEP 5-7 (max 2 fois) ; sinon STOP + [REVERSE_FEAT_INVALID]
9. Write atomique workspace/input/feats/{n}-{Name}.md
10. Émettre verdict 1L : [REVERSE] FEAT {n}-{Name} extraite (confidence: X). (100%)
```

---

## 7. Compatibilité aval avec `/feat-validate` et `/sdd-full`

Les FEATs générées par `/sdd-reverse` sont **strictement compatibles** avec le pipeline SDD_Pro existant. Aucune modification de `/feat-validate`, `/feat-generate`, `/us-generate`, `/sdd-full` n'est requise.

**Test de conformité automatique** : chaque FEAT générée passe `/feat-validate {n} --json` avant write atomique. Exit code 0 = OK, sinon l'agent itère ou échoue avec `[REVERSE_FEAT_INVALID]`.

**Sections additionnelles tolérées** : `## Reverse Engineering Notes` est ajoutée en queue de FEAT pour traçabilité (sources legacy, confidence agrégée, items écartés). Cette section ne perturbe pas `/feat-validate` (qui valide la présence des 6 sections obligatoires sans interdire les extras).

**Numérotation** : `/sdd-reverse` prend le prochain `N` libre dans `workspace/input/feats/` (continuité avec `/feat-generate`). Le frontmatter `generated-by: sdd-reverse` distingue l'origine sans nouvelle convention de naming.

---

## 8. Idempotence et hash d'unité

`unit-hash` (frontmatter FEAT) = `sha256(concat(legacy_sources_contents_sorted_by_path))`.

Re-run `/sdd-reverse {unit-id}` :
- Hash identique + FEAT présente → skip silencieux (output: `[REVERSE] unit-{id} : skip (hash unchanged). (100%)`)
- Hash différent → re-write avec warning `[REVERSE_HASH_MISMATCH]`
- FEAT absente → write nouvelle

Cette discipline permet :
- Re-run sûr sans perte de modifications manuelles (si humain édite le code legacy, hash change, re-extraction propose merge)
- Détection de drift (legacy modifié sans re-extraction = warning)
- Coût zéro pour les re-runs idempotents

---

## 9. Enforcement et auto-checks

### 9.1 Agents reverse

Les 4 agents reverse (`reverse-inventory`, `reverse-tech-auditor`, `reverse-functional-extractor`, `reverse-ui-extractor`) chargent cette règle en STEP contexte. Coût ~5 KB par invocation.

### 9.2 Scripts Python

- `scan_legacy.py`, `inventory_builder.py`, `ui_unit_detector.py` émettent leurs ERROR avec préfixe `[REVERSE_*]`.
- `reverse_inventory.py` (CLI) propage exit codes : 0=OK, 1=précondition, 2=scan failed, 3=no language.

### 9.3 Hooks d'audit

V2 (post-MVP) : un hook `PostToolUse` matcher=`reverse-*` peut vérifier que les FEATs écrites portent bien le frontmatter `generated-by: sdd-reverse` + un hash valide. Pas critique pour le MVP.

### 9.4 Isolation stricte

Cette règle vit dans `.claude/rules/reverse-engineering.md` (nouveau fichier). Elle est **lue uniquement** par les agents/commandes/scripts du workflow reverse. Aucun fichier SDD_Pro existant ne référence cette règle.

Réciproquement, les agents reverse ne référencent **aucune** règle SDD_Pro existante (`build-and-loop.md`, `ownership.md`, `quality.md`, etc.). Le seul point de jonction est : les FEATs écrites dans `workspace/input/feats/` qui sont ensuite consommées par `/feat-validate` et `/sdd-full` — mais cette consommation est read-only et standard, sans connaissance de l'origine reverse.

---

## §6 — Phase 4 UI extraction (extension v1.1, 2026-06-10)

Cette section étend la règle générale aux spécificités de la capture UI runtime (cf. design doc `docs/reverse-engineering-phase4-runtime.md`).

### 6.1 Principe load-bearing UI

> « Le mockup HTML ne contient QUE ce qui était dans le HTML capturé (post-JS) ou dans le template legacy (mode static fallback). »

L'agent `reverse-ui-extractor` est :
- **HTML-driven, pas spec-driven** : il ne consulte la FEAT qu'en lecture passive pour cohérence (titre, langue). Les SFD/AC ne génèrent JAMAIS de composant dans le mockup s'ils ne sont pas observables dans le HTML capturé.
- **Strictement transformatif** : strip + annotation + normalisation. Aucune restructuration sémantique inventée.
- **Modèle Sonnet 4.6** (pas Opus) : la tâche est mécanique. Choix Opus = sur-dimensionnement + risque accru d'hallucination créative.

### 6.2 Confidence par mode de capture

| Mode | Confidence par défaut | Cap autorisé | Raison |
|---|---|---|---|
| `runtime` (Playwright headless) | high | high | HTML rendu exactement comme dans Chrome — fidélité maximale |
| `static` (fallback : template legacy brut) | medium | medium | Manque le HTML JS-injecté (DataTable, modals dynamiques, etc.) |

Le mode est encodé dans le commentaire HTML de tête `<!-- capture-mode: runtime|static -->`.

### 6.3 Codes d'erreur `[REVERSE_UI_*]`

| Préfixe | Phase | Sévérité | Sens |
|---|---|---|---|
| `[REVERSE_UI_RUNNER_UNSUPPORTED]` | 4a | critical | Stack legacy non supporté par `runner_signatures.yml` (langage exotique) |
| `[REVERSE_UI_RUNNER_UNAVAILABLE]` | 4a | warning | Binaire runner absent du PATH → fallback static automatique |
| `[REVERSE_UI_RUNNER_TIMEOUT]` | 4a | critical | Subprocess legacy démarré mais HTTP pas ready avant `timeout_s` |
| `[REVERSE_UI_PORT_CONFLICT]` | 4a | warning | 5 ports successifs occupés autour de `default_port` |
| `[REVERSE_UI_ARTIFACT_MISSING]` | 4a | critical | Artefact requis (`*.csproj`, `pom.xml`, etc.) absent |
| `[REVERSE_UI_PLAYWRIGHT_MISSING]` | 4b | critical | Package Python `playwright` ou Chromium absent |
| `[REVERSE_UI_CAPTURE_EMPTY]` | 4b | critical | outerHTML < 500 chars (page d'erreur, redirection, vide) |
| `[REVERSE_UI_AUTH_REQUIRED]` | 4b | warning | Capture retourne 401/403 — fournir `auth-cookies.json` |
| `[REVERSE_UI_CAPTURE_FAILED]` | 4b | critical | Erreur Playwright (timeout networkidle, crash Chromium) |
| `[REVERSE_UI_MOCKUP_INVALID]` | 4c | critical | Auto-validation HTML échoue après 2 itérations (tags déséquilibrés, attributs interdits) |
| `[REVERSE_UI_NO_TARGETS]` | 4c | critical | Aucun composant identifiable dans le HTML (page vide ou bizarre) |
| `[REVERSE_UI_CONFIG_INVALID]` | 4a | critical | `runner_signatures.yml` malformé ou schema_version inattendu |

### 6.4 Anti-derive supplémentaires (UI-specific)

L'agent `reverse-ui-extractor` suit les 5 bullets §4 + ces 5 supplémentaires :

6. **Préservation des libellés** : ne JAMAIS traduire, raccourcir ou réécrire les textes UI capturés. « Rechercher » reste « Rechercher ».
7. **Préservation de l'ordre** : ordre des colonnes de table, ordre des champs de form, ordre des options de select — TOUS préservés.
8. **Strip exhaustif** : aucun attribut `style="..."` inline, aucun script (sauf `data-keep="true"` en mode static), aucun token ViewState/CSRF/EventValidation dans le mockup.
9. **Référence tokens.css obligatoire** : tous les mockups portent `<link rel="stylesheet" href="_legacy-style/tokens.css">` dans `<head>`. La palette vit là, pas inline.
10. **Annotations `data-legacy-*` obligatoires** sur `<main>` : au minimum `data-legacy-source`, `data-legacy-component="Page"`, `data-capture-mode`, `data-unit-id`, `data-unit-hash`. Composants secondaires (table, form, nav) portent leurs propres `data-legacy-component`.

### 6.5 Idempotence (hash basé)

Le mockup HTML contient `<!-- unit-hash: sha256:... -->` (récupéré de la FEAT correspondante). Re-run de `/sdd-reverse-ui` :
- Hash identique + mockup présent → SKIP silencieux
- Hash différent → re-capture (legacy modifié)
- Mockup absent → capture initiale

### 6.6 Isolation Phase 4

Les nouveaux fichiers Phase 4 vivent **uniquement** dans les paths suivants :

| Path | Owner | Type |
|---|---|---|
| `.claude/python/sdd_reverse/legacy_runner.py` | Phase 4 | nouveau module |
| `.claude/python/sdd_reverse/playwright_capture.py` | Phase 4 | nouveau module |
| `.claude/python/sdd_reverse/css_palette_extractor.py` | Phase 4 | nouveau module |
| `.claude/python/sdd_reverse/legacy_components_extractor.py` | Phase 4 | nouveau module |
| `.claude/python/sdd_reverse/runner_signatures.yml` | Phase 4 | nouveau config |
| `.claude/python/sdd_reverse_scripts/legacy_runner.py` | Phase 4 | nouveau CLI |
| `.claude/agents/reverse-ui-extractor.md` | Phase 4 | nouveau agent |
| `.claude/commands/sdd-reverse-ui.md` | Phase 4 | nouvelle commande |
| `.claude/docs/reverse-engineering-phase4-runtime.md` | Phase 4 | nouveau design doc |
| `.claude/docs/adrs/ADR-*-reverse-phase4-runtime-capture.md` | Phase 4 | nouveau ADR |
| `workspace/old/{P}/.sys/captures/*` | Phase 4 | artefacts capture |
| `workspace/old/{P}/.sys/.runner.pid` | Phase 4 | pidfile cleanup |
| `workspace/old/{P}/.sys/modules/{module-id}/ui-extraction-*.md` | Phase 4 | rapports agent |
| `workspace/input/ui/{n}-1-{Name}.html` | Phase 4 | mockup sémantique (cohabite avec /feat-generate) |
| `workspace/input/ui/_legacy-style/tokens.css` | Phase 4 | palette |
| `workspace/input/ui/_legacy-style/components-inventory.md` | Phase 4 | inventaire composants |

**Aucune** modification de fichier SDD_Pro existant. Aucune modification du loader.yml principal. Extension de `loader.reverse.yml` (loader autonome dédié) + extension §6 de cette règle uniquement.

### 6.7 Dépendances externes

Phase 4 introduit une dépendance **opt-in** : Python `playwright` + Chromium (~150 MB). Détection au runtime via `is_playwright_available()`. Absence → fallback static automatique. Aucune modification de `requirements.txt` principal SDD_Pro.

Install commande standard :
```bash
pip install playwright
python -m playwright install chromium
```

L'agent `reverse-ui-extractor` lui-même fonctionne **sans** Playwright (il consomme le HTML déjà capturé OU le template legacy en fallback). Seul le script `playwright_capture.py` requiert la dépendance, et uniquement quand le legacy a été lancé avec succès.

---

**FIN DE LA RÈGLE — Reverse Engineering v1.1 (avec extension §6 Phase 4 UI)**
