---
# TOK-C1 (audit 2026-06-12) : chargement paresseux (path-scoped rule, mécanisme natif
# Claude Code — docs memory#path-specific-rules). Cette règle ne s'auto-injecte qu'au
# contact de fichiers reverse ; hors-périmètre, les agents reverse la lisent en STEP
# contexte. Économie : 0 token dans toute session/sous-agent forward ou maintenance.
paths:
  - "workspace/old/**"
  - "workspace/.sys/.validation/reverse*"
  - "workspace/plans/*.analysis.md"
---

# Règle — Reverse Engineering (anti-derive REVERSE + taxonomie [REVERSE_*])

> **Périmètre** : règle dédiée aux 10 agents reverse (`reverse-inventory`,
> `reverse-tech-auditor`, `reverse-tech-analyst` (3a), `reverse-us-writer` (3b),
> `reverse-feat-composer` (3c), `reverse-ui-extractor`,
> `reverse-completeness-reviewer`, `reverse-paradigm-advisor` (2.7),
> `reverse-parity-inspector` (3.8), `reverse-clarifier` (3.9) — les 3 derniers
> empruntés à Reversa, audit comparatif 2026-06-12)
> et aux scripts/commandes du module `sdd_reverse`. Ne s'applique pas aux 12
> agents SDD_Pro standards.
>
> **Escalier ascendant (ADR `governance-major-reverse-spec-ladder`)** : la
> Phase 3 (`code → FEAT`) est décomposée en 3 barreaux — 3a `reverse-tech-analyst`
> (analyse technique → `plans/{n}-{Name}.analysis.md`), 3b
> `reverse-us-writer` (user stories → `us/`), 3c `reverse-feat-composer`
> (FEAT métier → `feats/`). Remplace l'ex-`reverse-functional-extractor`
> (saut mono-prompt décommissionné, D2). Fil de traçabilité FEAT→US→task→evidence,
> confidence min-monotone ascendante.
>
> **Cohabitation** : cette règle vit **à côté** de `error-classification.md`,
> `output-protocol.md`, `ownership.md`, `library-and-stack.md`, `quality.md`,
> `build-and-loop.md`. Aucune modification de ces règles existantes (D4 strict
> isolation, design doc §3.1).
>
> **SSoT** : `.sdd/docs/reverse-engineering-workflow.md` — ce fichier en est
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

**Jamais hardcodé** dans le code Python ou les agents. Source unique : `.sdd/python/sdd_reverse/language_signatures.yml` champ `confidence_cap`.

**Enforcement déterministe à la racine (audit 2026-06-12, reverse-C2)** : avant
ce fix, le calcul `cap_effectif` vivait **uniquement dans le prompt** 3a — un 3a
écrivant `confidence: high` sur un langage `medium`-cap (php-procedural, vbnet,
classic-asp, delphi-source) passait toutes les gates et déverrouillait
`/sdd-full` sans revue. Désormais `check_ladder_traceability.py` compare
`confidence(analyse 3a)` à `min(confidence_cap[unit.language], unit.confidenceEstimate)`
(le plancher déterministe de la formule ; `cap_db` runtime-only reste prompt-side)
et émet un gap `confidence cap: analysis (X) > cap[lang] (Y)` sous
`[REVERSE_LADDER_TRACEABILITY_GAP]` (informational). Best-effort : disponible en
mode `--project --unit` (lit `units[].language` de `inventory.json`) ; skip
silencieux en mode `--feat-path` (pas d'inventory). Le parseur du cap est
line-based (pas de dépendance PyYAML sur ce script déterministe), vérifié
iso-PyYAML par `test_reverse_ladder_traceability.py`.

Valeurs initiales MVP (+ ajouts 2026-06-10 audit C7) :
- `aspx-webforms`, `dotnet-mvc`, `csharp`, `wpf-xaml`, `java-ee`, `spring-mvc`, `php-framework`, `tsql` → `high`
- `php-procedural`, `javascript-jquery`, `vb6`, `vbnet`, `classic-asp`, `delphi-source` → `medium`
  (`vbnet` : parsing structurel line-based best-effort ; `classic-asp` : VBScript dynamique ;
  `delphi-source` : downgrade high→medium audit 2026-06-11 M14 — pas de graphe de classes hors .NET)

**Profondeur d'extraction par langage (audit 2026-06-11 M14)** : le graphe
classes/rôles (`code_graph_builder.py`) est **.NET-only** (`.cs`/`.vb`) ; pour
les autres langages, l'extraction couvre la détection d'unités + data-access
(SQL inline multi-langage) + seeds UI. Un cap `high` hors .NET signifie « la
*lecture* du code est fiable », pas « l'extraction structurelle est profonde ».
- `unknown` → `low`

## §5 Isolation framework intouchable (D4)

**Zéro édition** de fichier existant sous :
- `.claude/agents/`, `.claude/commands/`, `.sdd/rules/`, `.sdd/skills/`
- `.sdd/python/sdd_lib/`, `.sdd/python/sdd_scripts/`, `.sdd/python/sdd_admin/`, `.sdd/python/sdd_hooks/`
- `.sdd/loader.yml`, `.sdd/INVARIANTS.yml`, `.claude/CLAUDE.md`, `.claude/settings.json`
- `bootstrap.py`, `workspace/console/`

**Création de nouveaux fichiers** autorisée dans ces répertoires. Toute tentative d'**édition** → STOP + ERROR `[REVERSE_ISOLATION_VIOLATION]` + escalade.

Helpers Python sont **dupliqués localement** dans `sdd_reverse/` (`atomic_write_local.py`, `file_locks_local.py`) — D4 strict. Parité sémantique vérifiée par tests `test_local_helpers_parity.py` + drift detection via `_parity_snapshots.json` (ADV-16).

## §6 Taxonomie classes d'erreur `[REVERSE_*]`

Format ERROR 3-lignes disque, 1 ligne chat (cf. `error-classification.md §2` qui reste SSoT pour le format, **pas** pour les classes `[REVERSE_*]` qui vivent ici).

| Code | Bloquant | Sens |
|---|:---:|---|
| `[REVERSE_NO_SOURCE]` | **OUI** | `workspace/old/{P}/` vide ou inexistant |
| `[REVERSE_BINARY_ONLY]` | **OUI** | Seuls des exécutables détectés → hors-scope §0, escalade Tech Lead |
| `[REVERSE_UNIT_NOT_FOUND]` | **OUI** | `/sdd-reverse U-N` où U-N absent de `inventory.json` |
| `[REVERSE_FEAT_VALIDATE_FAILED]` | NON (WARN) | 3 itérations `validate_reverse_feat.py` sans GO → FEAT marquée `low` + bannière |
| `[REVERSE_EVIDENCE_MISSING]` | **OUI** au niveau item | AC/SFD/BR sans `<!-- evidence: ... -->` → item rejeté |
| `[REVERSE_ISOLATION_VIOLATION]` | **OUI** | Tentative d'écriture sur path framework existant |
| `[REVERSE_INVENTORY_STALE]` | NON (WARN) | mtime legacy > `inventory.legacyMtimeMax` (ADV-1) |
| `[REVERSE_LOCK_HELD]` | **OUI** | `.alloc.lock` détenu < TTL (1800s extraction legacy, 60s pré-allocation/crosscut — ADV-2 ; en mode pré-alloué aucun lock n'est pris, C5) |
| `[REVERSE_NAME_COLLISION]` | NON (info) | Suffixe `-Legacy` appliqué (ADV-4) |
| `[REVERSE_ENRICHMENT_INVALID]` | **OUI** | enrichment.json référence entity absente de base (ADV-3) |
| `[REVERSE_ENRICHMENT_TYPE_CONFLICT]` | NON (info, V2) | Conflit type base vs enrichment, base wins (ADV-12) |
| `[REVERSE_TEMPLATE_MISSING]` | **OUI** | `feat.reverse.template.md` absent (ADV-9) |
| `[REVERSE_UI_PARSER_MISSING]` | NON (WARN, Phase 4) | `reverse-ui-extractor` : un template dont la famille UI est détectée mais sans parseur structurel dédié (`delphi-dfm`, `vb6-form`) — `ui_template_parser.parse_template` renvoie `error:"parser_unsupported"`. L'agent **saute** ce template et le signale au lieu d'émettre une maquette vide trompeuse (audit C4 2026-07-24). Jamais bloquant. |
| `[REVERSE_VALIDATOR_DRIFT]` | NON (WARN V2) | `validate_readiness.py` standard a évolué (ADV-14) |
| `[REVERSE_HELPER_DRIFT]` | NON (WARN V2) | Hash `sdd_lib/file_locks.py` ou `atomic_write.py` changé (ADV-16) |
| `[REVERSE_GATE_DRIFT]` | **OUI** | Désync frontmatter `confidence` ↔ commentaire REVERSE-GATE (ADV-22) |
| `[REVERSE_INVENTORY_SCHEMA_STALE]` | NON (INFO) | `--use-cache` sur cache pre-v0.4.0 (ADV-23) → refresh forcé |
| `[REVERSE_COMPLETENESS_GAP]` | NON (informational, L5) | `reverse-completeness-reviewer` + Phase 1 (M7) : une classe repository/service/viewmodel ou une requête SQL/procédure de l'unité n'est mentionnée nulle part dans la FEAT (sous-extraction probable), OU une classe métier n'est couverte par aucune unité (section dédiée d'inventory.md). Verdict ASCII `complete`/`partial`/`incomplete` informational, jamais bloquant. |
| `[REVERSE_SECRETS_DETECTED]` | NON (WARN, C10) | `reverse_inventory.py` : clés privées / certificats / keystores sous `workspace/old/{P}/` (`.ppk`, `.pem` PRIVATE, `.pfx`, `id_rsa*`, …). Inventoriés dans `inventory.json.secretsDetected` + section `[!]` d'inventory.md + relayés OBLIGATOIREMENT par tech-audit.md §6. Action : révoquer + provisionner via vault, jamais copier vers la cible. |
| `[REVERSE_LADDER_TRACEABILITY_GAP]` | NON (informational, escalier) | ADR `governance-major-reverse-spec-ladder` D3. Un item d'un barreau n'a pas de `<!-- covers: ... -->` vers le barreau inférieur (FEAT sans US, US AC sans task `T-N`, task sans evidence). Fil de traçabilité incomplet. **Jamais comblé par invention** (`bias toward not-verified`) — l'item reste, le gap est noté. Détecté par `check_ladder_traceability.py` + `reverse-completeness-reviewer`. |
| `[REVERSE_LADDER_STALE]` | NON (informational, escalier) | ADR `governance-major-reverse-spec-ladder` (ré-câblé audit 2026-06-29 — l'émetteur avait été purgé MA-7 alors que l'ADR en documentait le risque en *Conséquences négatives*). Un barreau inférieur a été ré-exécuté **après** les barreaux supérieurs (mtime 3a > 3b/3c, ou 3b > 3c) → analyse/US/FEAT désynchronisées. Le cache d'extraction (grain unité) ne couvre PAS une régénération partielle de barreau. mtime-based (même patron qu'`[REVERSE_INVENTORY_STALE]`/ADV-1), tolérance 1s. Émis par `check_ladder_traceability.py` (séparé du fil de traçabilité). Fix : re-run le(s) barreau(x) supérieur(s) (`/sdd-reverse-stories` puis `/sdd-reverse-feat`). |
| `[REVERSE_INVENTORY_CORRUPTED]` | NON (WARN, diagnostic) | `/sdd-reverse-status` (`reverse_status.py`) : `inventory.json` présent mais JSON invalide — re-run `/sdd-reverse-inventory`. |
| `[REVERSE_INVENTORY_IO_ERROR]` | NON (WARN, diagnostic) | `/sdd-reverse-status` (`reverse_status.py`) : lecture `inventory.json` impossible (permissions/I-O). |
| `[REVERSE_FEAT_UNREADABLE]` | NON (WARN, diagnostic) | `/sdd-reverse-status` (`reverse_status.py`) : une FEAT de `workspace/feats/` est illisible pendant le scan des markers `[REV]`. |
| `[REVERSE_GATE_BLOCKED]` | **OUI** (bloquant) | Hook `PreToolUse` (matcher Skill) `preflight_reverse_gate.py` (audit M1-reverse 2026-06-12) : `/sdd-full`, `/sdd-poc` ou `/dev-run` invoqué sur une FEAT `generated-by: sdd-reverse` dont `confidence != high` (REVERSE-GATE `allow-sdd-full=false`), sans bypass. Délègue le verdict à `check_reverse_feat_for_full.py` (exit 1). Fail-open sur toute ambiguïté (FEAT non-reverse / introuvable / glob ambigu). Bypass audit-loggué : `SDD_ALLOW_REVERSE_LOW=1`. |
| `[REVERSE_PARITY_INVALID]` | NON (WARN, Phase 3.8) | `validate_parity_features.py` : `.feature` structurellement invalide (Feature/Scenario manquant, scénario sans Given/When/Then, scénario sans tag `@AC-N`, tag orphelin ne référençant aucun AC de la FEAT). L'agent `reverse-parity-inspector` itère (max 3) ; au-delà → bannière dans parity-map.md (miroir `[REVERSE_FEAT_VALIDATE_FAILED]`). |
| `[REVERSE_PARITY_COVERAGE_GAP]` | NON (informational, Phase 3.8) | `validate_parity_features.py` : un AC-N de la FEAT n'est couvert par aucun scénario de parité. Listé dans `parity-map.md §Non dérivables` — **jamais comblé par invention** (bias toward not-verified). |
| `[REVERSE_PARADIGM_GAP]` | NON (informational, Phase 2.7) | `reverse-paradigm-advisor` : écart de paradigme legacy↔cible documenté (`paradigm-decision.md`) OU stack cible non déclarée dans `stack.md`. Décision consciente (`adopt-target`/`preserve-legacy`/`hybrid`) à arbitrer par le Tech Lead. |
| `[REVERSE_CURATION_PENDING]` | NON (WARN, Phase 2.7) | `reverse-paradigm-advisor` : ≥ 1 unité en verdict `HUMAN-DECISION` non arbitrée OU `Décision: PENDING` dans paradigm-decision.md. Le Tech Lead doit arbitrer avant `/sdd-full` — jamais bloquant, jamais destructif. |
| `[REVERSE_QUESTIONS_PENDING]` | NON (informational, Phase 3.9) | `reverse-clarifier` : ≥ 1 bloc `Q-N` de `questions.md` sans `Réponse:` remplie. La boucle de validation humaine reste ouverte. |
| `[REVERSE_ANSWER_INGEST_FAILED]` | NON (WARN, Phase 3.9) | `reverse-clarifier --ingest` : réponse `Q-N` inexploitable (ambiguë, hors sujet) — le bloc reste ouvert, aucun item FEAT édité pour ce Q-N. **Jamais comblé par interprétation**. |
| `[REVERSE_DB_CONFIG_MISSING]` | **OUI** | db-reverse : section `## Active Database` de `stack.md` absente/incomplète, OU `DatabaseType` non supporté par un dialecte implémenté. Émis par `stack_db_config.py` + `dialects.get_dialect`. |
| `[REVERSE_DB_UNREACHABLE]` | **OUI** | db-reverse : base injoignable (timeout/firewall) OU driver lecture seule absent (`pip install -e .sdd/python[reverse-db]`). Émis par `db_introspect.connect`. |
| `[REVERSE_DB_AUTH_FAILED]` | **OUI** | db-reverse : authentification refusée / droits insuffisants à la connexion lecture seule. Émis par `db_introspect.connect`. |
| `[REVERSE_PROC_NOT_FOUND]` | **OUI** | db-reverse : `/sdd-db-reverse {nom}` sur une procédure absente du catalogue. Émis par `db_introspect.introspect` + `reverse_proc_introspect.py`. |
| `[REVERSE_PROC_ENCRYPTED]` | NON (info) | db-reverse : procédure `WITH ENCRYPTION` (corps `OBJECT_DEFINITION` NULL) — US `low` + bannière, jamais devinée. Émis par `db_introspect.build_introspection`. |
| `[REVERSE_DB_READONLY_VIOLATION]` | **OUI** | db-reverse : tentative d'envoyer au serveur un statement non-`SELECT` (DDL/DML/EXEC), **ou** un pragma de session hors liste blanche. Deux barrières mécaniques : `readonly_guard.assert_readonly` (requêtes de catalogue) et `readonly_guard.assert_session_pragma` (les 3 `SET TRANSACTION …` émis à la connexion — audit 2026-08-25 N1 : ils partaient auparavant **sans garde**, ce qui rendait faux l'invariant `reverse-db-readonly`). Défense en profondeur — ne devrait jamais se déclencher. |
| `[REVERSE_DB_SCHEMA_PARTIAL]` | NON (WARN) | db-reverse : une requête de **structure live** (`columns`/`primary_keys`/`foreign_keys`/`indexes`/`checks`) a échoué ou n'a rien renvoyé — droit manquant, version de moteur, catalogue absent. La section correspondante de `db-schema.json` reste vide, le reste du schéma est produit. Émis par `db_schema_live.fetch_structure` + `build_live_schema`. Un droit refusé dégrade le rapport, il n'interrompt jamais un run par ailleurs réussi. |
| `[REVERSE_DB_OBJECTS_PARTIAL]` | NON (WARN) | db-reverse : une famille d'**objets sans corps** (job/séquence/synonyme/linked server/type utilisateur) n'est pas lisible. Cas NORMAL et fréquent : `msdb` non accordé au login d'introspection, extension `pg_cron` absente, `CHECK_CONSTRAINTS` inexistant avant MySQL 8.0.16. Émis par `db_schema_live.fetch_catalog_objects`. |
| `[REVERSE_DB_HOMONYM]` | NON (info) | db-reverse : une même nom de table existe dans ≥ 2 schémas (`dbo.Orders` **et** `sales.Orders`). Légitime, mais signalé car tout consommateur qui indexe les entités par nom nu les fusionnerait — utiliser `qualifiedName`. Émis par `db_schema_live.build_live_schema`. |

> **Classes retirées (audit 2026-06-11 MA-7)** : `[REVERSE_LANG_UNKNOWN]`,
> `[REVERSE_DB_SCHEMA_MISSING]`, `[REVERSE_DB_SCHEMA_DEGRADED]`,
> `[REVERSE_UNIT_RENAMED]`, `[REVERSE_ALLOCATED_NAME_STALE]` étaient déclarées
> sans aucun émetteur câblé (code mort déclaratif). Supprimées de la taxonomie.
> Si l'un de ces comportements doit être enforced, ré-ajouter la classe ICI
> **en même temps** que son émetteur (script/agent), jamais en avance.
>
> **`[REVERSE_LADDER_STALE]` ré-câblé (audit 2026-06-29)** : retiré par MA-7
> faute d'émetteur, mais l'ADR `governance-major-reverse-spec-ladder` en
> documentait explicitement le risque (*Conséquences négatives* : « three rungs
> must be kept in sync »). Ré-ajouté **avec** son émetteur déterministe
> (`check_ladder_traceability.py`, mtime-based) — exactement la procédure
> prescrite ci-dessus (classe + émetteur ensemble).

### §6.1 Format ERROR

```
ERROR: reverse-{agent} {context} — {résumé}
CAUSE: [REVERSE_{CLASS}] {détail 1L pointant evidence/cause}
FIX: {action concrète 1-2L}
```

### §6.2 Exemple

```
ERROR: reverse-tech-analyst U-3 — analyse interrompue
CAUSE: [REVERSE_LOCK_HELD] workspace/feats/.alloc.lock détenu par reverse-tech-analyst-U-1 depuis 12s
FIX: attendre fin Phase 3a en cours OU supprimer manuellement .alloc.lock après vérification que U-1 est mort (mode legacy séquentiel, ADV-2 §8.1 ; le lock est pris par le barreau 3a qui possède l'allocation)
```

### §6.3 État d'implémentation des émetteurs (audit 2026-06-11)

Le tableau §6 déclare le **contrat** ; tous les émetteurs ne sont pas
encore câblés. État vérifié par grep croisé code/prompts :

- **Émises par scripts déterministes (23)** : `NO_SOURCE`, `UNIT_NOT_FOUND`,
  `EVIDENCE_MISSING`, `LOCK_HELD`, `ENRICHMENT_INVALID`,
  `ENRICHMENT_TYPE_CONFLICT`, `GATE_DRIFT`, `INVENTORY_SCHEMA_STALE`,
  `COMPLETENESS_GAP`, `SECRETS_DETECTED`, `LADDER_TRACEABILITY_GAP`,
  `LADDER_STALE` (ré-câblé 2026-06-29, `check_ladder_traceability.py` mtime-based),
  `INVENTORY_CORRUPTED`, `INVENTORY_IO_ERROR`, `FEAT_UNREADABLE`
  (les 3 dernières : diagnostics `/sdd-reverse-status`, ajoutées à la
  taxonomie par l'audit 2026-06-11 — elles étaient émises par
  `reverse_status.py` sans figurer en §6, violant le contrat réciproque),
  `PARITY_INVALID`, `PARITY_COVERAGE_GAP` (`validate_parity_features.py`,
  emprunt Reversa 2026-06-12), plus db-reverse (DB live read-only) :
  `DB_CONFIG_MISSING`, `DB_UNREACHABLE`, `DB_AUTH_FAILED`, `PROC_NOT_FOUND`,
  `PROC_ENCRYPTED`, `DB_READONLY_VIOLATION` (`stack_db_config.py` /
  `db_introspect.py` / `readonly_guard.py` / `reverse_proc_introspect.py`).
- **Émises par prompts agents/commandes uniquement (11)** : `BINARY_ONLY`,
  `FEAT_VALIDATE_FAILED`, `ISOLATION_VIOLATION`, `INVENTORY_STALE`,
  `NAME_COLLISION`, `TEMPLATE_MISSING`, `PARADIGM_GAP`, `CURATION_PENDING`,
  `QUESTIONS_PENDING`, `ANSWER_INGEST_FAILED`, `UI_PARSER_MISSING` (émission
  LLM, pas de gate déterministe — acceptable, l'agent porte le contrat ;
  `PARADIGM_GAP`/`CURATION_PENDING`/`QUESTIONS_PENDING`/`ANSWER_INGEST_FAILED` :
  agents `reverse-paradigm-advisor` + `reverse-clarifier`, emprunt Reversa
  2026-06-12 ; `UI_PARSER_MISSING` : agent `reverse-ui-extractor`, audit C4
  2026-07-24, sur signal déterministe `ui_template_parser`).
- **Enforced par `reverse_smoke` sous leur nom de check (2)** :
  `VALIDATOR_DRIFT` (`check_validator_parity_drift`), `HELPER_DRIFT`
  (`check_helper_parity_drift`) — le préfixe `[CLASS]` n'apparaît pas
  littéralement dans l'output smoke.
- **Émise par hook déterministe (1)** : `GATE_BLOCKED` —
  `sdd_hooks/preflight_reverse_gate.py` (PreToolUse Skill, audit M1-reverse
  2026-06-12), délègue à `check_reverse_feat_for_full.py`.

> **Code mort retiré (audit 2026-06-11 MA-7)** : la sous-liste « Déclaratives
> sans émetteur câblé (6) » (`LANG_UNKNOWN`, `DB_SCHEMA_MISSING`,
> `DB_SCHEMA_DEGRADED`, `UNIT_RENAMED`, `ALLOCATED_NAME_STALE`, `LADDER_STALE`)
> a été supprimée de §6 et de cet état : ces classes n'avaient aucun émetteur.
> Total taxonomie après réconciliation audit 2026-06-11 + ajout `GATE_BLOCKED`
> (audit 2026-06-12) + 6 classes des phases optionnelles 2.7/3.8/3.9 (emprunt
> Reversa, audit comparatif 2026-06-12) + 6 classes db-reverse (DB live
> read-only, 2026-06-29) + ré-câblage `[REVERSE_LADDER_STALE]` (2026-06-29)
> + `[REVERSE_UI_PARSER_MISSING]` (audit C4 2026-07-24, agent `reverse-ui-extractor`) :
> **37 classes** (23 scripts déterministes + 11 prompts
> agents/commandes + 2 enforced par `reverse_smoke` + 1 hook). Règle : aucune
> classe `[REVERSE_*]` ne vit dans §6 sans émetteur identifié.

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

Le label `[REVERSE]` est documenté localement ici (cette règle) et déclaré dans la table fermée `output-protocol.md §3` (entrée « module reverse », ajoutée à l'audit 2026-06-11 — la liste des labels est bien FERMÉE, l'ancienne formulation prétendant le contraire était fausse).

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
python .sdd/python/sdd_reverse_scripts/preallocate_feats.py --project workspace/old/{P}
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

### §8.4 Routage de modèle par complexité (ADR `governance-reverse-complexity-ladder`)

L'escalier appliquait 2 passes **Opus** (3a + 3c) à **toute** unité. Depuis
l'ADR `governance-reverse-complexity-ladder` (2026-06-29), un classifieur
**déterministe** (`sdd_reverse/code_unit_complexity.py`, 0 token, signaux L0 de
`inventory.json`) étiquette chaque unité `simple | complex`, et les commandes
`/sdd-reverse-analyze` (3a) + `/sdd-reverse-feat` (3c) **routent le modèle** :
unité `simple` → Sonnet 4.6 sur tout l'escalier ; unité `complex` → 3a/3c
restent Opus 4.8 (3b est Sonnet dans les deux cas).

**Périmètre = modèle uniquement.** La **structure** de l'escalier (3 barreaux,
3 artefacts, fil D3, confidence min-monotone) est **inchangée** — ce n'est PAS le
collapse mono-prompt (écarté en V2 opt-in, il réintroduirait la bave d'altitude
que `governance-major-reverse-spec-ladder` a décommissionnée). **Fail-safe** :
tout signal manquant/ambigu (dont graphe de classes vide des langages non-.NET)
→ `complex` (= Opus). Aucune régression possible vs le comportement full-Opus
antérieur. Rubrique SSoT : `docs/rubrics/reverse-complexity-routing.md`. Pendant
de db-reverse (`build_proc_us.py`, routage déterministe par complexité).

## §9 Pas de spawn d'agent (no-spawn)

Aucun agent reverse ne spawn un autre agent. Règle stricte SDD_Pro étendue au reverse :
- `reverse-inventory` ne spawn pas `reverse-tech-analyst`
- aucun barreau de l'escalier (`reverse-tech-analyst` 3a, `reverse-us-writer` 3b, `reverse-feat-composer` 3c) ne spawn un autre agent
- `/sdd-reverse` est un **séquenceur** des 3 sous-commandes 3a→3b→3c — il ne spawn aucun agent directement (chaque sous-commande spawn son agent)
- L'orchestrateur `/sdd-reverse-full` (V2) **séquence des commandes** (qui chacune spawn un agent), il **ne spawn pas** d'agents directement — y compris pour la revue de complétude L5, qui passe par la commande wrapper `/sdd-reverse-review {U-N}` (audit M11 2026-06-10)
- Enforcement déterministe : `reverse_smoke.check_no_spawn_of_agents` (INVARIANTS.reverse.yml `reverse-no-spawn-of-agents`)

Cette discipline préserve le contrat d'isolation et la traçabilité (1 invocation utilisateur = 1 agent identifiable).

## §10 Pont reverse → /sdd-full (handoff, REV-C1 audit 2026-06-12)

L'USP du module reverse est : *legacy → FEAT reverse `high` → `/sdd-full` régénère
l'application*. Or `/sdd-full` **auto-skip `us-generate` quand des US sont présentes**
→ il **réutilise les US 3b** au lieu de les régénérer. Les US 3b brutes ne sont pas
forward-compatibles (ni `Covers: SFD-N`, ni `Parent FEAT hash` résolu).

**Le pont est posé par le barreau 3c** (`reverse-feat-composer` STEP 4.ter), pas par
un nouveau composant :
1. **`Parent FEAT hash`** : 3b écrit le sentinel `sha256:COMPUTE_REQUIRED` ; 3c le
   résout via le resolver **canonique** `resolve_us_hash_sentinel.py --feat-number {n}`
   (même algorithme `sha256(feat.read_bytes())[:8]` que le forward — aucun drift).
   Sans ça : dev-*/auditors émettent `[FEAT_HASH_MISMATCH]`.
2. **`Covers: SFD-N, FD-N, BR-N, AC-N`** : 3c back-fille chaque US à partir de
   l'inverse de sa carte de composition (`covers: US {n}-{m}#AC-x`). Sans ça :
   `validate_readiness` voit les `SFD-N` de la FEAT comme orphelins (NO-GO).
3. **`Status: Draft → Ready`** : seulement si `cap_effectif == high`.

**Garde-fou confiance** : une FEAT reverse `medium`/`low` reste bloquée pour
`/sdd-full` par la REVERSE-GATE + le hook `preflight_reverse_gate.py`
(`[REVERSE_GATE_BLOCKED]`, §6) — le back-fill ne court-circuite PAS la revue
humaine, il rend seulement le handoff *mécaniquement valide* pour les FEAT `high`.

**Ordre strict** : back-fill (Covers + Status) puis résolution hash en **dernier**
(le hash dépend des bytes finaux de la FEAT — ne plus éditer FEAT ni US après).
`bias toward not-verified` préservé : 3c n'invente aucun `Covers:` — un ID FEAT
sans US source est un bug de la carte de composition, jamais comblé par invention.

---

## Pointeurs

- Design doc complet : `.sdd/docs/reverse-engineering-workflow.md` (v0.7.0)
- Rapports adversariaux : `workspace/.sys/.validation/reverse-design-doc-adversarial*.md`
- Schémas JSON : design doc §5
- Annexe A conformité FEAT : design doc Annexe A
- Annexe B isolation : design doc Annexe B
