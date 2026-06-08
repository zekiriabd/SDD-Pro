# /feat-validate — Implementation Readiness Gate (déterministe, v6.1)

Vérifie qu'une FEAT + ses US + mockups HTML sont prêts pour `/dev-run`.
**Validation 100% déterministe** via Python (`validate_readiness.py`
+ `validate_semantic.py`, 0 token LLM, 0 agent invoqué).

**v6.1 (réintroduction validation sémantique low-cost)** : à la couche
structurelle (readiness) s'ajoute une couche sémantique déterministe
(vocabulaire + regex) qui détecte ambiguïtés, AC non mesurables,
keywords sécurité sans mécanisme de protection, PII sans mention de
privacy, et routes `/api/*` mentionnées sans endpoint backend déclaré.
Toujours 0 token LLM ; WARN non bloquant par défaut.

**Usage :**
- `/feat-validate {n}` — valide la FEAT `{n}` et produit le rapport
- `/feat-validate {n} --json` — sortie JSON pour CI/CD

**Décisions possibles** :
- 🟢 **GO** : prêt pour `/dev-run`
- 🟡 **WARN** : passable mais review humaine recommandée
- 🔴 **NO-GO** : bloque `/dev-run` (sauf `/dev-run {n} --force`)

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent →
```
ERROR: /feat-validate — argument manquant
CAUSE: aucun numéro de FEAT fourni
FIX: relancer /feat-validate {n} (ex. /feat-validate 1)
```

Si non numérique →
```
ERROR: /feat-validate — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /feat-validate {n}
```

---

## STEP 2 — Localiser la FEAT

Glob `workspace/input/feats/{n}-*.md`.

- 0 fichier → ERROR `[FEAT_NOT_FOUND]` (créer via `/feat-generate`)
- > 1 fichier → ERROR `[FEAT_AMBIGUOUS]` (renommer)
- 1 fichier → OK, stocker `{FeatName}` extrait du nom de fichier

---

## STEP 3 — Validations déterministes (Python, 0 token)

Exécuter via Bash :

```bash
python .claude/python/sdd_scripts/validate_readiness.py --feat-number {n}
```

Capturer :
- `stdout` → contenu du rapport readiness (§1 + décision)
- `exit_code` → `0` si toutes validations passent, `1` si erreur bloquante

Stocker `decision` = `GO` (exit 0 + pas de warning) | `WARN`
(exit 0 + ≥1 warning) | `NO-GO` (exit 1).

### Validations couvertes par le script

| ID check | Type | Description |
|---|---|---|
| `SFD-IDS`, `FD-IDS`, `BR-IDS`, `AC-IDS` | Continuité | Numérotation continue, pas de doublons |
| `SFD-COVERAGE`, `FD-COVERAGE`, `BR-COVERAGE`, `AC-COVERAGE` | Traçabilité | IDs FEAT couverts par les US |
| `STACK-ACTIVE`, `STACK-MISSING`, `STACK-EMPTY` | Stack | Stacks actifs déclarés |
| `PROJECT-CONFIG`, `DB-TYPE`, `DB-KEYS`, `AUTH-KEYS` | Project Config + blocs Active | AppName défini ; `## Active Database` complet (DB_*) ; `## Active Auth Specs` complet (AZ_*) si auth listé |
| `HTML-US-MATCH`, `HTML-ORPHAN` | UI | Coïncidence basenames HTML ↔ US |
| `FEAT-DEEPEN-DONE`, `FEAT-DEEPEN-RECOMMENDED`, `FEAT-COMPLEXITY-LOW` | Élicitation | FEAT complexe → `/feat-deepen` recommandé |

**Score complexité** : la FEAT obtient 1 point pour chacun des
critères suivants ; ≥ 2 points = FEAT "complexe" :
- ≥ 10 SFD
- ≥ 8 BR
- ≥ 15 AC
- `DatabaseType` ≠ none
- ≥ 5 items en `## Out of Scope`

Si FEAT complexe ET sections d'élicitation absentes → WARN
`[FEAT-DEEPEN-RECOMMENDED]`. Combiné au mode strict `/sdd-full`,
ce WARN bloque le pipeline sauf `--force`.

---

## STEP 4 — Validations sémantiques déterministes (Python, 0 token)

**Réintroduit en v6.1** sous forme purement déterministe (vocabulaire +
regex). Aucun agent LLM, aucun coût token.

Lire la valeur `SemanticValidationStrictness` dans `## Project Config`
de `workspace/input/stack/stack.md` (défaut `standard`). Valeurs valides :
`conservative` (~2-5 WARN/FEAT), `standard` (~5-15 WARN/FEAT), `strict`
(~20-40 WARN/FEAT).

Exécuter via Bash :

```bash
python .claude/python/sdd_scripts/validate_semantic.py --feat-number {n} --strictness {strictness}
```

Capturer `stdout` (= section §2 du rapport readiness) et `exit_code`
(toujours 0 — sémantique = WARN uniquement, jamais bloquant).

### Checks couverts

| ID check | Type | Description |
|---|---|---|
| `VAGUE_TERM` | Ambiguïté | Mots qualitatifs non mesurables (`fast`, `easy`, `scalable`, `user-friendly`…) dans AC/BR/SFD/Objective |
| `SECURITY_GAP` | Sécurité | Mention de `password`/`token`/`auth`/`credential` sans mention de mécanisme (`hash`, `bcrypt`, `encrypt`, `https`, `httponly`…) |
| `SENSITIVE_DATA` | PII | Mention de `email`/`phone`/`adresse`/`iban`/`ssn` sans mention de privacy (`encrypt`, `mask`, `anonymis`, `gdpr/rgpd`) |
| `ROUTE_CONTRACT_GAP` | Contrat back/front | Route `/api/*` mentionnée dans FEAT/US sans endpoint correspondant dans `workspace/output/src/{BackendName}/` (skip si code pas encore généré) |

### Mode opt-in d'escalation (futur v6.2)

`SemanticValidationMode: hybrid` (futur, non spécifié) pourrait déclencher
un sub-agent léger Haiku 4.5 **uniquement** si ≥ N WARN sémantiques, pour
distinguer les faux positifs des vraies ambiguïtés. Aujourd'hui (v6.1) :
mode `deterministic` exclusivement, 0 token. Nom et spec exacte du futur
sub-agent non figés — pas encore créé sur disque.

---

## STEP 4.5 — Spec-compliance gate (post-dev uniquement, v7.0.0)

**But** : empêcher de valider une FEAT comme "prête / terminée" tant que
le code matérialisé n'a pas été indépendamment vérifié contre chaque AC
par `spec-compliance-reviewer` (pattern "Do not trust the report"
hérité superpowers v5.1).

> **⚠ Portée d'activation** (clarifié audit CTO 2026-06-07) : ce gate
> se déclenche **uniquement quand `/feat-validate` est invoqué en
> standalone APRÈS un cycle dev** (`/feat-validate {n}` post-`/dev-run`).
>
> Dans le flow nominal `/sdd-full {n}`, `feat-validate` est invoqué
> **PRÉ-dev** (STEP 3.5) → `HAS_CODE=null` → `MODE=pre-dev` → gate skip
> silencieusement. C'est **intentionnel** : spec-compliance ne peut pas
> tourner sans code matérialisé.
>
> Pour activer le gate dans un pipeline automatisé post-dev :
> - soit lancer `/feat-validate {n}` à la main après `/sdd-full`,
> - soit utiliser `/sdd-review {n} --ensure-scans` (spawne
>   `spec-compliance-reviewer` directement),
> - soit attendre v7.2.0 qui déplacera le gate à `/sdd-full §4.8`
>   (roadmap v7.2 — cf. `docs/roadmap-v7-v8.md`, ADR à émettre lors
>   du sprint d'implémentation).

### 4.5.1 Détection mode (pre-dev vs post-dev)

Le gate ne tourne qu'**après** matérialisation du code. Détecter via
présence d'un projet sous `workspace/output/src/` :

```bash
HAS_CODE=$(find workspace/output/src -maxdepth 3 \
  \( -name '*.csproj' -o -name 'package.json' -o -name 'pyproject.toml' \
  -o -name 'build.gradle.kts' -o -name 'angular.json' -o -name 'vite.config.*' \) \
  2>/dev/null | head -1)

if [ -z "$HAS_CODE" ]; then
  MODE="pre-dev"   # pas de code → skip silencieusement, continuer STEP 5
else
  MODE="post-dev"  # code matérialisé → gate active
fi
```

- **`pre-dev`** : émettre 1 ligne info
  `spec-compliance gate: pre-dev — skipped (no materialized code yet)`,
  passer STEP 5.
- **`post-dev`** : continuer 4.5.2.

### 4.5.2 Lire la config layered

```bash
REQUIRED=$(python -c "
import sys; sys.path.insert(0, '.claude/python')
from sdd_lib.layered_config import read_layered_config
cfg = read_layered_config()
print(str(cfg.get('SpecComplianceRequiredForFeatValidate', 'true')).lower())
" 2>/dev/null || echo 'true')
```

- `REQUIRED=false` (project bypass explicite, tracé git blame) →
  émettre WARN 1 ligne et passer STEP 5
  (`spec-compliance gate: bypassed via Project Config`)
- `REQUIRED=true` (défaut v7.0.0) → continuer 4.5.3.

### 4.5.3 Vérifier la présence d'un rapport spec-compliance récent

```bash
SPEC_PATH="workspace/output/qa/feat-{n}/spec-compliance.json"
if [ ! -f "$SPEC_PATH" ]; then
  cat <<EOF
ERROR: /feat-validate {n} — spec-compliance absent
CAUSE: [SPEC_COMPLIANCE_REQUIRED] code matérialisé détecté mais $SPEC_PATH manquant
FIX: lancer /sdd-review {n} --ensure-scans (spawne spec-compliance-reviewer)
     OU /qa-generate {n} (pipeline QA complet)
     OU baisser SpecComplianceRequiredForFeatValidate à false (décision tracée)
EOF
  exit 1
fi
```

### 4.5.4 Lire le verdict + appliquer le gate

```bash
VERDICT=$(python -c "
import json, sys
d = json.load(open('$SPEC_PATH'))
print(d.get('summary', {}).get('verdict', 'UNKNOWN').upper())
" 2>/dev/null || echo 'UNKNOWN')
```

| `verdict` | Action |
|---|---|
| `GREEN`            | continuer STEP 5 (gate passée) |
| `YELLOW`           | continuer STEP 5 + propager WARN au rapport readiness §4 |
| `RED`              | **NO-GO** — ERROR `[SPEC_COMPLIANCE_RED]` + exit 1 |
| `UNKNOWN` / parse fail | **NO-GO** — ERROR `[SPEC_COMPLIANCE_PARSE_ERROR]` + exit 1 |

Format ERROR `[SPEC_COMPLIANCE_RED]` :
```
ERROR: /feat-validate {n} — spec-compliance verdict RED
CAUSE: [SPEC_COMPLIANCE_RED] N ACs non vérifiées dans le code matérialisé
       (cf. workspace/output/qa/feat-{n}/spec-compliance.md)
FIX: corriger les ACs flag NOT_VERIFIED via /dev-run {n} (idempotent)
     puis /sdd-review {n} --ensure-scans
     puis /feat-validate {n} (idempotent)
```

### 4.5.5 Anti-bypass

- **Jamais** bypass par `--json` (CI/CD doit transporter le signal exit code).
- **Bypass** possible par `/sdd-full --force --no-validate` (audit log
  `force-bypass.log` capture la décision).
- Pre-dev (`MODE=pre-dev`) **n'est jamais** bloqué (par construction —
  spec-compliance ne peut pas s'exécuter sans code).

---

## STEP 5 — Écrire le rapport readiness

Read `.claude/templates/readiness.template.md`.

Composer le rapport final :
- En-tête (date, décision finale)
- §1 = stdout de `validate_readiness.py` (STEP 3, structurel)
- §2 = stdout de `validate_semantic.py` (STEP 4, sémantique — v6.1)
- §3 = liste consolidée des erreurs déterministes (toujours `validate-readiness`)
- §4 = liste consolidée des warnings déterministes (readiness + semantic mergés)
- §5 = bloc "Décision finale" selon le résultat
- §6 = prochaines actions

**Décision finale** : `NO-GO` si readiness exit_code ≠ 0 ; sinon `WARN`
si readiness OU semantic produisent ≥ 1 warning ; sinon `GO`. La couche
sémantique ne peut pas escalader en NO-GO (par design — WARN non
bloquant, cf. STEP 4).

Write `workspace/output/.sys/.validation/{n}-readiness.md` (mode `create`, écrase si
existe). Créer le répertoire `workspace/output/.sys/.validation/` si absent.

---

## STEP 5.bis — Status flip US (v6.10.5, fix CRIT-2)

Si verdict = `GO` ou `WARN` (exit 0), flipper toutes les US de la FEAT
de `Draft → Ready`. Idempotent (même status = no-op exit 0).
Non-bloquant : un échec de transition (US déjà Ready/InProgress/Done)
n'interrompt pas le pipeline.

```bash
for us_file in workspace/output/us/{n}-*.md; do
  us_id=$(basename "$us_file" .md | grep -oE '^[0-9]+-[0-9]+')
  python .claude/python/sdd_scripts/set_us_status.py \
    --us "$us_id" --status Ready 2>/dev/null || true
done
```

Skip si verdict `NO-GO` (US restent `Draft`).

---

## STEP 6 — Confirmation et sortie

Émettre **un seul bloc final** :

```
{🟢|🟡|🔴} /feat-validate {n}-{FeatName} → {GO|WARN|NO-GO}

Validations  : {N_pass_struct} struct + {N_pass_sem} sém (déterministes, 0 token)
Erreurs      : {E} (bloquantes, struct uniquement)
Warnings     : {W_struct} struct + {W_sem} sém (non bloquantes)

Rapport      : workspace/output/.sys/.validation/{n}-readiness.md

Prochaine étape :
  - 🟢 GO     : /dev-run {n}
  - 🟡 WARN   : review workspace/output/.sys/.validation/{n}-readiness.md puis /dev-run {n}
  - 🔴 NO-GO  : corriger les erreurs (§3 du rapport) puis /feat-validate {n}
                (bypass exceptionnel : /dev-run {n} --force)
```

**Exit code** :
- `GO` ou `WARN` → exit 0
- `NO-GO` → exit 1

---

## Mode JSON (pour CI/CD)

Si l'argument `--json` est fourni :
- Exécuter `validate_readiness.py --json` ET `validate_semantic.py --json`
- Fusionner en un objet `{ readiness: {...}, semantic: {...} }` sur stdout
- Ne PAS écrire `workspace/output/.sys/.validation/{n}-readiness.md`
- Exit code = exit code de `validate_readiness.py` (la sémantique
  est toujours 0)

---

## Règles de cette commande

- **100% déterministe (v6.1)** : 0 token LLM, 0 agent invoqué. Le travail
  est fait par `validate_readiness.py` (structurel) + `validate_semantic.py`
  (sémantique low-cost, vocabulaire + regex).
- **Idempotente** : relancer `/feat-validate {n}` régénère le rapport.
- **Read-only sur FEAT/US/HTML** : aucune modification des artefacts
  (l'humain corrige manuellement après NO-GO).
- **Ne lance JAMAIS automatiquement `/dev-run`** : la décision finale
  est laissée à l'humain (ou à `/sdd-full` qui chaîne les commandes).
- **Économie v6.0** : –1.4M tokens par `/sdd-full` vs v5.0 (suppression
  agent validator + lectures sémantiques associées).

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[VALIDATE]` (cf. output-protocol.md §3)
**Plage de progression couverte** : `12-15%` (cf. output-protocol.md §4)

**Granularité cible** : 2-4 updates (lecture FEAT, scoring readiness,
verdict). Format `[VALIDATE] Action au gérondif... (X%)`.

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- détail score-by-section (verdict global 🟢/🟡/🔴 suffit)
- stdout/stderr scripts validate_readiness.py / validate_semantic.py
- JSON dumps

**Verdict final** : 1 ligne avec emoji 🟢 GO / 🟡 WARN / 🔴 NO-GO +
pointeur fichier rapport en cas de WARN/NO-GO. Exemple :
`🔴 [VALIDATE/FAIL] FEAT {n} NO-GO — [READINESS_NO_GO] 2 ACs sans Given/When/Then → workspace/output/.sys/.validation/{n}-readiness.md. (15%)`.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
