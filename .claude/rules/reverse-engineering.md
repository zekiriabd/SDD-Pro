# Règle — Reverse Engineering (anti-derive REVERSE + taxonomie [REVERSE_*])

> **Périmètre** : règle dédiée aux 7 agents reverse (`reverse-inventory`,
> `reverse-tech-auditor`, `reverse-tech-analyst` (3a), `reverse-us-writer` (3b),
> `reverse-feat-composer` (3c), `reverse-ui-extractor`,
> `reverse-completeness-reviewer`)
> et aux scripts/commandes du module `sdd_reverse`. Ne s'applique pas aux 12
> agents SDD_Pro standards.
>
> **Escalier ascendant (ADR `governance-major-reverse-spec-ladder`)** : la
> Phase 3 (`code → FEAT`) est décomposée en 3 barreaux — 3a `reverse-tech-analyst`
> (analyse technique → `output/plans/{n}-{Name}.analysis.md`), 3b
> `reverse-us-writer` (user stories → `output/us/`), 3c `reverse-feat-composer`
> (FEAT métier → `input/feats/`). Remplace l'ex-`reverse-functional-extractor`
> (saut mono-prompt décommissionné, D2). Fil de traçabilité FEAT→US→task→evidence,
> confidence min-monotone ascendante.
>
> **Cohabitation** : cette règle vit **à côté** de `error-classification.md`,
> `output-protocol.md`, `ownership.md`, `library-and-stack.md`, `quality.md`,
> `build-and-loop.md`. Aucune modification de ces règles existantes (D4 strict
> isolation, design doc §3.1).
>
> **SSoT** : `.claude/docs/reverse-engineering-workflow.md` — ce fichier en est
> l'extrait opérationnel pour les agents.

## TOC

- [§1 Principes anti-derive REVERSE](#1-principes-anti-derive-reverse)
- [§2 Bias toward present (anti-hallucination)](#2-bias-toward-present-anti-hallucination)
- [§3 Evidence obligatoire par item](#3-evidence-obligatoire-par-item)
- [§4 Confidence cap par langage (D1)](#4-confidence-cap-par-langage-d1)
- [§5 Isolation framework intouchable (D4)](#5-isolation-framework-intouchable-d4)
- [§6 Taxonomie classes d'erreur `[REVERSE_*]`](#6-taxonomie-classes-derreur-reverse_)
- [§7 Label chat `[REVERSE]` (output-protocol)](#7-label-chat-reverse-output-protocol)
- [§8 Phase 3 séquentielle stricte (ADV-2)](#8-phase-3-séquentielle-stricte-adv-2)
- [§9 Pas de spawn d'agent (no-spawn)](#9-pas-de-spawn-dagent-no-spawn)

---

## §1 Principes anti-derive REVERSE

Les agents reverse opèrent sous 5 principes **non négociables** :

1. **Pas d'invention** : si une intention métier n'est pas visible dans le code, elle n'est pas documentée. Ne JAMAIS extrapoler depuis "ce qu'un projet de ce type aurait probablement".
2. **Bias toward not-verified** : en cas de doute entre "vérifié" et "non-visible", choisir "non documenté" (cf. pattern superpowers v5.1).
3. **Pas d'amélioration métier** : décrire l'existant tel quel, pas tel qu'il devrait être. Les ACs reflètent le comportement actuel du legacy, même si bugué ou désuet.
4. **Pas de proposition d'archi cible** : c'est `/sdd-full` qui décide de l'archi cible via le pipeline standard, pas l'agent reverse.
5. **Lecture sélective stricte** : un agent reverse ne lit JAMAIS plus de fichiers que listés dans `units[U-N].evidenceFiles` du périmètre de son unité courante.

## §2 Bias toward present (anti-hallucination)

**Règle d'or** : chaque assertion (SFD, FD, BR, AC) doit pouvoir être pointée vers une **ligne précise** de code observable dans le legacy. Si l'agent ne peut pas citer file:line, l'item est **rejeté**, pas inventé.

Exemples interdits :
- ❌ AC "le système envoie un email de confirmation" si aucun `SmtpClient`/`MailMessage`/`mail()` n'est trouvé
- ❌ BR "le mot de passe doit faire 8 caractères minimum" si aucun check `Length >= 8` ni regex équivalent n'est visible
- ❌ SFD "permettre l'export en CSV" si aucun `Response.ContentType = "text/csv"` ou équivalent n'est trouvé

Exemples acceptés :
- ✅ AC observable : `Login.aspx.cs:34-38` montre un `Session["UserId"] = ...; Response.Redirect("Default.aspx");` → "Given crédentiels valides, when soumission, then session créée et redirect Default"
- ✅ BR observable : `App_Code/DataAccess.cs:32` montre `WHERE Username = @u AND PasswordHash = @p` → "Le password est comparé contre PasswordHash (non en clair)"

## §3 Evidence obligatoire par item

Chaque item de FEAT reverse **DOIT** porter immédiatement après son texte :

```html
<!-- evidence: path/relative.ext:Lstart-Lend --> <!-- confidence: high|medium|low -->
```

Règles :
- `path` est **relatif** à `workspace/old/{P}/`
- `Lstart-Lend` est obligatoire (range, même 1 ligne → `Lstart-Lstart`)
- `confidence` ∈ {`high`, `medium`, `low`} strict, pas d'autres valeurs
- Items sans evidence → **rejetés** par l'agent (jamais inclus dans la FEAT)
- Si zéro item valide reste après rejet → STOP + ERROR `[REVERSE_FEAT_VALIDATE_FAILED]`

## §4 Confidence cap par langage (D1)

Le cap effectif est calculé par :

```
cap_effectif = min(
    confidence_cap[unit.language] depuis language_signatures.yml,
    agent.confidenceEstimate (heuristique unit.confidenceEstimate),
    cap_dégradation_db_schema (medium si entities déduites du code)
)
```

**Jamais hardcodé** dans le code Python ou les agents. Source unique : `.claude/python/sdd_reverse/language_signatures.yml` champ `confidence_cap`.

Valeurs initiales MVP (+ ajouts 2026-06-10 audit C7) :
- `aspx-webforms`, `dotnet-mvc`, `csharp`, `wpf-xaml`, `java-ee`, `spring-mvc`, `php-framework`, `delphi-source`, `tsql` → `high`
- `php-procedural`, `javascript-jquery`, `vb6`, `vbnet`, `classic-asp` → `medium`
  (`vbnet` : parsing structurel line-based best-effort ; `classic-asp` : VBScript dynamique)
- `unknown` → `low`

## §5 Isolation framework intouchable (D4)

**Zéro édition** de fichier existant sous :
- `.claude/agents/`, `.claude/commands/`, `.claude/rules/`, `.claude/skills/`
- `.claude/python/sdd_lib/`, `.claude/python/sdd_scripts/`, `.claude/python/sdd_admin/`, `.claude/python/sdd_hooks/`
- `.claude/loader.yml`, `.claude/INVARIANTS.yml`, `.claude/CLAUDE.md`, `.claude/settings.json`
- `bootstrap.py`, `workspace/console/`

**Création de nouveaux fichiers** autorisée dans ces répertoires. Toute tentative d'**édition** → STOP + ERROR `[REVERSE_ISOLATION_VIOLATION]` + escalade.

Helpers Python sont **dupliqués localement** dans `sdd_reverse/` (`atomic_write_local.py`, `file_locks_local.py`) — D4 strict. Parité sémantique vérifiée par tests `test_local_helpers_parity.py` + drift detection via `_parity_snapshots.json` (ADV-16).

## §6 Taxonomie classes d'erreur `[REVERSE_*]`

Format ERROR 3-lignes disque, 1 ligne chat (cf. `error-classification.md §2` qui reste SSoT pour le format, **pas** pour les classes `[REVERSE_*]` qui vivent ici).

| Code | Bloquant | Sens |
|---|:---:|---|
| `[REVERSE_NO_SOURCE]` | **OUI** | `workspace/old/{P}/` vide ou inexistant |
| `[REVERSE_BINARY_ONLY]` | **OUI** | Seuls des exécutables détectés → hors-scope §0, escalade Tech Lead |
| `[REVERSE_LANG_UNKNOWN]` | NON (WARN) | Aucun langage matché → fallback `id: unknown` + cap forcé `low` |
| `[REVERSE_DB_SCHEMA_MISSING]` | NON (WARN) | `db-schema.json.entities` vide → entities déduites du code, cap `medium` |
| `[REVERSE_DB_SCHEMA_DEGRADED]` | NON (info) | Schema partiel, entities mixtes (DB + code) |
| `[REVERSE_UNIT_NOT_FOUND]` | **OUI** | `/sdd-reverse U-N` où U-N absent de `inventory.json` |
| `[REVERSE_FEAT_VALIDATE_FAILED]` | NON (WARN) | 3 itérations `validate_reverse_feat.py` sans GO → FEAT marquée `low` + bannière |
| `[REVERSE_EVIDENCE_MISSING]` | **OUI** au niveau item | AC/SFD/BR sans `<!-- evidence: ... -->` → item rejeté |
| `[REVERSE_ISOLATION_VIOLATION]` | **OUI** | Tentative d'écriture sur path framework existant |
| `[REVERSE_INVENTORY_STALE]` | NON (WARN) | mtime legacy > `inventory.legacyMtimeMax` (ADV-1) |
| `[REVERSE_UNIT_RENAMED]` | NON (info) | Fingerprint `core` match mais pas `full` (ADV-1) |
| `[REVERSE_LOCK_HELD]` | **OUI** | `.alloc.lock` détenu < TTL (1800s extraction legacy, 60s pré-allocation/crosscut — ADV-2 ; en mode pré-alloué aucun lock n'est pris, C5) |
| `[REVERSE_NAME_COLLISION]` | NON (info) | Suffixe `-Legacy` appliqué (ADV-4) |
| `[REVERSE_ENRICHMENT_INVALID]` | **OUI** | enrichment.json référence entity absente de base (ADV-3) |
| `[REVERSE_ENRICHMENT_TYPE_CONFLICT]` | NON (info, V2) | Conflit type base vs enrichment, base wins (ADV-12) |
| `[REVERSE_TEMPLATE_MISSING]` | **OUI** | `feat.reverse.template.md` absent (ADV-9) |
| `[REVERSE_VALIDATOR_DRIFT]` | NON (WARN V2) | `validate_readiness.py` standard a évolué (ADV-14) |
| `[REVERSE_HELPER_DRIFT]` | NON (WARN V2) | Hash `sdd_lib/file_locks.py` ou `atomic_write.py` changé (ADV-16) |
| `[REVERSE_GATE_DRIFT]` | **OUI** | Désync frontmatter `confidence` ↔ commentaire REVERSE-GATE (ADV-22) |
| `[REVERSE_ALLOCATED_NAME_STALE]` | NON (WARN V2) | `_allocatedNames[Name]` orphelin (ADV-21) |
| `[REVERSE_INVENTORY_SCHEMA_STALE]` | NON (INFO) | `--use-cache` sur cache pre-v0.4.0 (ADV-23) → refresh forcé |
| `[REVERSE_COMPLETENESS_GAP]` | NON (informational, L5) | `reverse-completeness-reviewer` + Phase 1 (M7) : une classe repository/service/viewmodel ou une requête SQL/procédure de l'unité n'est mentionnée nulle part dans la FEAT (sous-extraction probable), OU une classe métier n'est couverte par aucune unité (section dédiée d'inventory.md). Verdict ASCII `complete`/`partial`/`incomplete` informational, jamais bloquant. |
| `[REVERSE_SECRETS_DETECTED]` | NON (WARN, C10) | `reverse_inventory.py` : clés privées / certificats / keystores sous `workspace/old/{P}/` (`.ppk`, `.pem` PRIVATE, `.pfx`, `id_rsa*`, …). Inventoriés dans `inventory.json.secretsDetected` + section `[!]` d'inventory.md + relayés OBLIGATOIREMENT par tech-audit.md §6. Action : révoquer + provisionner via vault, jamais copier vers la cible. |
| `[REVERSE_LADDER_TRACEABILITY_GAP]` | NON (informational, escalier) | ADR `governance-major-reverse-spec-ladder` D3. Un item d'un barreau n'a pas de `<!-- covers: ... -->` vers le barreau inférieur (FEAT sans US, US AC sans task `T-N`, task sans evidence). Fil de traçabilité incomplet. **Jamais comblé par invention** (`bias toward not-verified`) — l'item reste, le gap est noté. Détecté par `check_ladder_traceability.py` + `reverse-completeness-reviewer`. |
| `[REVERSE_LADDER_STALE]` | NON (WARN, escalier) | ADR `governance-major-reverse-spec-ladder`. Le hash d'un barreau N (ex. analyse 3a) a changé sans régénération du barreau N+1 (US 3b / FEAT 3c) → escalier désynchronisé. Fix : re-lancer le ou les barreaux supérieurs (`/sdd-reverse-stories`, `/sdd-reverse-feat`). |

### §6.1 Format ERROR

```
ERROR: reverse-{agent} {context} — {résumé}
CAUSE: [REVERSE_{CLASS}] {détail 1L pointant evidence/cause}
FIX: {action concrète 1-2L}
```

### §6.2 Exemple

```
ERROR: reverse-tech-analyst U-3 — analyse interrompue
CAUSE: [REVERSE_LOCK_HELD] workspace/input/feats/.alloc.lock détenu par reverse-tech-analyst-U-1 depuis 12s
FIX: attendre fin Phase 3a en cours OU supprimer manuellement .alloc.lock après vérification que U-1 est mort (mode legacy séquentiel, ADV-2 §8.1 ; le lock est pris par le barreau 3a qui possède l'allocation)
```

### §6.3 État d'implémentation des émetteurs (audit 2026-06-11)

Le tableau §6 déclare le **contrat** ; tous les émetteurs ne sont pas
encore câblés. État vérifié par grep croisé code/prompts :

- **Émises par scripts déterministes (11)** : `NO_SOURCE`, `UNIT_NOT_FOUND`,
  `EVIDENCE_MISSING`, `LOCK_HELD`, `ENRICHMENT_INVALID`,
  `ENRICHMENT_TYPE_CONFLICT`, `GATE_DRIFT`, `INVENTORY_SCHEMA_STALE`,
  `COMPLETENESS_GAP`, `SECRETS_DETECTED`, `LADDER_TRACEABILITY_GAP`.
- **Émises par prompts agents/commandes uniquement (6)** : `BINARY_ONLY`,
  `FEAT_VALIDATE_FAILED`, `ISOLATION_VIOLATION`, `INVENTORY_STALE`,
  `NAME_COLLISION`, `TEMPLATE_MISSING` (émission LLM, pas de gate
  déterministe — acceptable, l'agent porte le contrat).
- **Enforced par `reverse_smoke` sous leur nom de check (2)** :
  `VALIDATOR_DRIFT` (`check_validator_parity_drift`), `HELPER_DRIFT`
  (`check_helper_parity_drift`) — le préfixe `[CLASS]` n'apparaît pas
  littéralement dans l'output smoke.
- **Déclaratives sans émetteur câblé (6)** : `LANG_UNKNOWN`,
  `DB_SCHEMA_MISSING`, `DB_SCHEMA_DEGRADED`, `UNIT_RENAMED`,
  `ALLOCATED_NAME_STALE`, `LADDER_STALE` — **à câbler ou requalifier**
  avant toute communication les présentant comme actives. Ne pas en
  ajouter de nouvelles sans émetteur identifié.

> **Monotonie de confidence (Q3)** : enforced depuis 2026-06-11 par
> `check_ladder_traceability.py` (gaps `confidence uprank: ...` sous
> `[REVERSE_LADDER_TRACEABILITY_GAP]`, frontmatter-based, informational).

## §7 Label chat `[REVERSE]` (output-protocol)

Les agents reverse émettent UNIQUEMENT le label `[REVERSE]` en chat (cf. `output-protocol.md` §3 mapping label → agent). Suffixes d'état applicables :
- `[REVERSE/FIXING]` (itération validate_reverse_feat)
- `[REVERSE/SKIP]` (legacy vide ou binaire-only)
- `[REVERSE/WARN]` (confidence ≠ high)
- `[REVERSE/FAIL]` (RED bloquant)

Format ligne unique :
```
[REVERSE] {action} ... (PROGRESS%)
```

Le label `[REVERSE]` est documenté localement ici (cette règle) et accepté par `output-protocol.md` (qui ne hardcode pas la liste fermée des labels).

## §8 Phase 3 : séquentielle stricte (ADV-2) → parallèle borné après pré-allocation (L5)

### §8.1 Mode legacy (sans pré-allocation) — séquentiel strict (ADV-2)

Si la pré-allocation L5 n'a **pas** tourné, `/sdd-reverse {U-N}` alloue `(n, Name)`
au moment de l'extraction sous `.alloc.lock`, ce qui **force le séquentiel** :
deux `/sdd-reverse` simultanés → le second émet `[REVERSE_LOCK_HELD]` (TTL
**1800 s** — le lock couvre l'extraction complète, qui dure des minutes ;
l'ancien TTL 30s faisait voler le lock comme stale en cours d'extraction,
audit C5 2026-06-09). En mode pré-alloué, **aucun lock n'est pris** (l'agent
skip son STEP 3). Le lock élargi couvre :
```
acquire .alloc.lock
  → READ inventory.json (_featAllocations + units)
  → COMPUTE n + Name (anti-collision intra-run §6 design doc)
  → WRITE FEAT atomique (.sddtmp + os.replace)
  → UPDATE inventory.json atomique
release .alloc.lock
```

### §8.2 Mode industrialisé (L5) — pré-allocation déterministe → parallèle borné

Depuis L5, l'orchestrateur lance **d'abord** la pré-allocation déterministe :
```bash
python .claude/python/sdd_reverse_scripts/preallocate_feats.py --project workspace/old/{P}
```
Elle fige `(n, Name)` pour **toutes** les unités dans `inventory.json`
(`_featAllocations` + `_allocatedNames`), une fois, sous un unique lock.

**Conséquence** : la race d'allocation disparaît. Chaque extraction Phase 3 lit
son `(n, Name)` pré-alloué (STEP 4 de l'agent : `_featAllocations[{U-N}]` présent)
et écrit un fichier `{n}-{Name}.md` **disjoint**, sans toucher `inventory.json`
→ **pas de write partagé, pas de contention de lock**. La Phase 3 peut donc
tourner en **parallèle borné** (`MaxParallel`, défaut 3, aligné sur le pipeline
forward `ownership.md §5`).

**Invariant de sûreté** : la parallélisation n'est autorisée **que si** la
pré-allocation a tourné (sinon §8.1 séquentiel). L'agent extractor ne ré-écrit
`inventory.json` que si `_featAllocations[{U-N}]` est **absent** (mode legacy) ;
en mode pré-alloué il skip le write-back (idempotent, parallel-safe).

### §8.3 Cache d'extraction (L5)

`reverse_cache.py` permet à l'orchestrateur de **skipper** une unité dont
l'evidence (hash sha256 normalisé des `evidenceFiles`) est inchangée ET dont la
FEAT existe encore — évite de re-spawner Opus inutilement. Doute → re-extraire
(fail-safe, jamais skip optimiste).

## §9 Pas de spawn d'agent (no-spawn)

Aucun agent reverse ne spawn un autre agent. Règle stricte SDD_Pro étendue au reverse :
- `reverse-inventory` ne spawn pas `reverse-tech-analyst`
- aucun barreau de l'escalier (`reverse-tech-analyst` 3a, `reverse-us-writer` 3b, `reverse-feat-composer` 3c) ne spawn un autre agent
- `/sdd-reverse` est un **séquenceur** des 3 sous-commandes 3a→3b→3c — il ne spawn aucun agent directement (chaque sous-commande spawn son agent)
- L'orchestrateur `/sdd-reverse-full` (V2) **séquence des commandes** (qui chacune spawn un agent), il **ne spawn pas** d'agents directement — y compris pour la revue de complétude L5, qui passe par la commande wrapper `/sdd-reverse-review {U-N}` (audit M11 2026-06-10)
- Enforcement déterministe : `reverse_smoke.check_no_spawn_of_agents` (INVARIANTS.reverse.yml `reverse-no-spawn-of-agents`)

Cette discipline préserve le contrat d'isolation et la traçabilité (1 invocation utilisateur = 1 agent identifiable).

---

## Pointeurs

- Design doc complet : `.claude/docs/reverse-engineering-workflow.md` (v0.4.1)
- Rapports adversariaux : `workspace/output/.sys/.validation/reverse-design-doc-adversarial*.md`
- Schémas JSON : design doc §5
- Annexe A conformité FEAT : design doc Annexe A
- Annexe B isolation : design doc Annexe B
