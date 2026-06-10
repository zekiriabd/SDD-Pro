# Règle — Reverse Engineering (anti-derive REVERSE + taxonomie [REVERSE_*])

> **Périmètre** : règle dédiée aux 4 agents reverse (`reverse-inventory`,
> `reverse-tech-auditor`, `reverse-functional-extractor`, `reverse-ui-extractor`)
> et aux scripts/commandes du module `sdd_reverse`. Ne s'applique pas aux 12
> agents SDD_Pro standards.
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

Valeurs initiales MVP :
- `aspx-webforms`, `dotnet-mvc`, `csharp`, `java-ee`, `spring-mvc`, `php-framework`, `delphi-source`, `tsql` → `high`
- `php-procedural`, `javascript-jquery`, `vb6` → `medium`
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
| `[REVERSE_LOCK_HELD]` | **OUI** | `.alloc.lock` détenu < 30s (ADV-2 séquentialité Phase 3) |
| `[REVERSE_NAME_COLLISION]` | NON (info) | Suffixe `-Legacy` appliqué (ADV-4) |
| `[REVERSE_ENRICHMENT_INVALID]` | **OUI** | enrichment.json référence entity absente de base (ADV-3) |
| `[REVERSE_ENRICHMENT_TYPE_CONFLICT]` | NON (info, V2) | Conflit type base vs enrichment, base wins (ADV-12) |
| `[REVERSE_TEMPLATE_MISSING]` | **OUI** | `feat.reverse.template.md` absent (ADV-9) |
| `[REVERSE_VALIDATOR_DRIFT]` | NON (WARN V2) | `validate_readiness.py` standard a évolué (ADV-14) |
| `[REVERSE_HELPER_DRIFT]` | NON (WARN V2) | Hash `sdd_lib/file_locks.py` ou `atomic_write.py` changé (ADV-16) |
| `[REVERSE_GATE_DRIFT]` | **OUI** | Désync frontmatter `confidence` ↔ commentaire REVERSE-GATE (ADV-22) |
| `[REVERSE_ALLOCATED_NAME_STALE]` | NON (WARN V2) | `_allocatedNames[Name]` orphelin (ADV-21) |
| `[REVERSE_INVENTORY_SCHEMA_STALE]` | NON (INFO) | `--use-cache` sur cache pre-v0.4.0 (ADV-23) → refresh forcé |

### §6.1 Format ERROR

```
ERROR: reverse-{agent} {context} — {résumé}
CAUSE: [REVERSE_{CLASS}] {détail 1L pointant evidence/cause}
FIX: {action concrète 1-2L}
```

### §6.2 Exemple

```
ERROR: reverse-functional-extractor U-3 — extraction interrompue
CAUSE: [REVERSE_LOCK_HELD] workspace/input/feats/.alloc.lock détenu par reverse-functional-extractor-U-1 depuis 12s
FIX: attendre fin Phase 3 en cours OU --force après vérification (Phase 3 séquentielle stricte, ADV-2)
```

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

## §8 Phase 3 séquentielle stricte (ADV-2)

`/sdd-reverse {U-N}` **n'est pas conçu** pour tourner en parallèle multi-`U-N` simultanément. Si un utilisateur lance deux `/sdd-reverse` en parallèle manuellement, le second attend le lock (jusqu'à TTL 30s) ou émet `[REVERSE_LOCK_HELD]`.

L'orchestrateur `/sdd-reverse-full` (V2) séquence les invocations Phase 3 sans parallélisme.

Le lock élargi couvre :
```
acquire .alloc.lock
  → READ inventory.json (_featAllocations + units)
  → COMPUTE n + Name (anti-collision intra-run §6 design doc)
  → WRITE FEAT atomique (.sddtmp + os.replace)
  → UPDATE inventory.json atomique
release .alloc.lock
```

## §9 Pas de spawn d'agent (no-spawn)

Aucun agent reverse ne spawn un autre agent. Règle stricte SDD_Pro étendue au reverse :
- `reverse-inventory` ne spawn pas `reverse-functional-extractor`
- `reverse-functional-extractor` ne spawn pas `reverse-ui-extractor` (V2)
- L'orchestrateur `/sdd-reverse-full` (V2) **séquence des commandes** (qui chacune spawn un agent), il **ne spawn pas** d'agents directement

Cette discipline préserve le contrat d'isolation et la traçabilité (1 invocation utilisateur = 1 agent identifiable).

---

## Pointeurs

- Design doc complet : `.claude/docs/reverse-engineering-workflow.md` (v0.4.1)
- Rapports adversariaux : `workspace/output/.sys/.validation/reverse-design-doc-adversarial*.md`
- Schémas JSON : design doc §5
- Annexe A conformité FEAT : design doc Annexe A
- Annexe B isolation : design doc Annexe B
