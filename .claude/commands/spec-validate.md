# /spec-validate — Implementation Readiness Gate (déterministe, v6.1)

Vérifie qu'une SPEC + ses US + mockups HTML sont prêts pour `/dev-run`.
**Validation 100% déterministe** via PowerShell (`validate-readiness.ps1`
+ `validate-semantic.ps1`, 0 token LLM, 0 agent invoqué).

**v6.1 (réintroduction validation sémantique low-cost)** : à la couche
structurelle (readiness) s'ajoute une couche sémantique déterministe
(vocabulaire + regex) qui détecte ambiguïtés, AC non mesurables,
keywords sécurité sans mécanisme de protection, PII sans mention de
privacy, et routes `/api/*` mentionnées sans endpoint backend déclaré.
Toujours 0 token LLM ; WARN non bloquant par défaut.

**Usage :**
- `/spec-validate {n}` — valide la SPEC `{n}` et produit le rapport
- `/spec-validate {n} --json` — sortie JSON pour CI/CD

**Décisions possibles** :
- 🟢 **GO** : prêt pour `/dev-run`
- 🟡 **WARN** : passable mais review humaine recommandée
- 🔴 **NO-GO** : bloque `/dev-run` (sauf `/dev-run {n} --force`)

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent →
```
ERROR: /spec-validate — argument manquant
CAUSE: aucun numéro de SPEC fourni
FIX: relancer /spec-validate {n} (ex. /spec-validate 1)
```

Si non numérique →
```
ERROR: /spec-validate — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /spec-validate {n}
```

---

## STEP 2 — Localiser la SPEC

Glob `workspace/input/specs/{n}-*.md`.

- 0 fichier → ERROR `[SPEC_NOT_FOUND]` (créer via `/spec-generate`)
- > 1 fichier → ERROR `[SPEC_AMBIGUOUS]` (renommer)
- 1 fichier → OK, stocker `{SpecName}` extrait du nom de fichier

---

## STEP 3 — Validations déterministes (PowerShell, 0 token)

Exécuter via Bash avec **fallback automatique pwsh → powershell** :

```bash
if command -v pwsh >/dev/null 2>&1; then PS_BIN=pwsh; else PS_BIN=powershell; fi
$PS_BIN -NoProfile -ExecutionPolicy Bypass `
  -File .claude/scripts/validate-readiness.ps1 -SpecNumber {n}
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
| `SFD-COVERAGE`, `FD-COVERAGE`, `BR-COVERAGE`, `AC-COVERAGE` | Traçabilité | IDs SPEC couverts par les US |
| `STACK-ACTIVE`, `STACK-MISSING`, `STACK-EMPTY` | Stack | Stacks actifs déclarés |
| `PROJECT-CONFIG`, `DB-TYPE` | Project Config | AppName, DatabaseType définis |
| `HTML-US-MATCH`, `HTML-ORPHAN` | UI | Coïncidence basenames HTML ↔ US |
| `SPEC-DEEPEN-DONE`, `SPEC-DEEPEN-RECOMMENDED`, `SPEC-COMPLEXITY-LOW` | Élicitation | SPEC complexe → `/spec-deepen` recommandé |

**Score complexité** : la SPEC obtient 1 point pour chacun des
critères suivants ; ≥ 2 points = SPEC "complexe" :
- ≥ 10 SFD
- ≥ 8 BR
- ≥ 15 AC
- `DatabaseType` ≠ none
- ≥ 5 items en `## Out of Scope`

Si SPEC complexe ET sections d'élicitation absentes → WARN
`[SPEC-DEEPEN-RECOMMENDED]`. Combiné au mode strict `/sdd-full`,
ce WARN bloque le pipeline sauf `--force`.

---

## STEP 4 — Validations sémantiques déterministes (PowerShell, 0 token)

**Réintroduit en v6.1** sous forme purement déterministe (vocabulaire +
regex). Aucun agent LLM, aucun coût token.

Lire la valeur `SemanticValidationStrictness` dans `## Project Config`
de `workspace/input/stack/stack.md` (défaut `standard`). Valeurs valides :
`conservative` (~2-5 WARN/SPEC), `standard` (~5-15 WARN/SPEC), `strict`
(~20-40 WARN/SPEC).

Exécuter via Bash :

```bash
$PS_BIN -NoProfile -ExecutionPolicy Bypass `
  -File .claude/scripts/validate-semantic.ps1 -SpecNumber {n} -Strictness {strictness}
```

Capturer `stdout` (= section §2 du rapport readiness) et `exit_code`
(toujours 0 — sémantique = WARN uniquement, jamais bloquant).

### Checks couverts

| ID check | Type | Description |
|---|---|---|
| `VAGUE_TERM` | Ambiguïté | Mots qualitatifs non mesurables (`fast`, `easy`, `scalable`, `user-friendly`…) dans AC/BR/SFD/Objective |
| `SECURITY_GAP` | Sécurité | Mention de `password`/`token`/`auth`/`credential` sans mention de mécanisme (`hash`, `bcrypt`, `encrypt`, `https`, `httponly`…) |
| `SENSITIVE_DATA` | PII | Mention de `email`/`phone`/`adresse`/`iban`/`ssn` sans mention de privacy (`encrypt`, `mask`, `anonymis`, `gdpr/rgpd`) |
| `ROUTE_CONTRACT_GAP` | Contrat back/front | Route `/api/*` mentionnée dans SPEC/US sans endpoint correspondant dans `workspace/output/src/{BackendName}/` (skip si code pas encore généré) |

### Mode opt-in d'escalation (futur v6.2)

`SemanticValidationMode: hybrid` (futur) déclenchera un agent
`validator-lite` (Haiku 4.5) **uniquement** si ≥ N WARN sémantiques, pour
distinguer les faux positifs des vraies ambiguïtés. Aujourd'hui (v6.1) :
mode `deterministic` exclusivement, 0 token.

---

## STEP 5 — Écrire le rapport readiness

Read `.claude/templates/readiness.template.md`.

Composer le rapport final :
- En-tête (date, décision finale)
- §1 = stdout de `validate-readiness.ps1` (STEP 3, structurel)
- §2 = stdout de `validate-semantic.ps1` (STEP 4, sémantique — v6.1)
- §3 = liste consolidée des erreurs déterministes (toujours `validate-readiness`)
- §4 = liste consolidée des warnings déterministes (readiness + semantic mergés)
- §5 = bloc "Décision finale" selon le résultat
- §6 = prochaines actions

**Décision finale** : `NO-GO` si readiness exit_code ≠ 0 ; sinon `WARN`
si readiness OU semantic produisent ≥ 1 warning ; sinon `GO`. La couche
sémantique ne peut pas escalader en NO-GO (par design — WARN non
bloquant, cf. STEP 4).

Write `workspace/output/validation/{n}-readiness.md` (mode `create`, écrase si
existe). Créer le répertoire `workspace/output/validation/` si absent.

---

## STEP 6 — Confirmation et sortie

Émettre **un seul bloc final** :

```
{🟢|🟡|🔴} /spec-validate {n}-{SpecName} → {GO|WARN|NO-GO}

Validations  : {N_pass_struct} struct + {N_pass_sem} sém (déterministes, 0 token)
Erreurs      : {E} (bloquantes, struct uniquement)
Warnings     : {W_struct} struct + {W_sem} sém (non bloquantes)

Rapport      : workspace/output/validation/{n}-readiness.md

Prochaine étape :
  - 🟢 GO     : /dev-run {n}
  - 🟡 WARN   : review workspace/output/validation/{n}-readiness.md puis /dev-run {n}
  - 🔴 NO-GO  : corriger les erreurs (§3 du rapport) puis /spec-validate {n}
                (bypass exceptionnel : /dev-run {n} --force)
```

**Exit code** :
- `GO` ou `WARN` → exit 0
- `NO-GO` → exit 1

---

## Mode JSON (pour CI/CD)

Si l'argument `--json` est fourni :
- Exécuter `validate-readiness.ps1 -Json` ET `validate-semantic.ps1 -Json`
- Fusionner en un objet `{ readiness: {...}, semantic: {...} }` sur stdout
- Ne PAS écrire `workspace/output/validation/{n}-readiness.md`
- Exit code = exit code de `validate-readiness.ps1` (la sémantique
  est toujours 0)

---

## Règles de cette commande

- **100% déterministe (v6.1)** : 0 token LLM, 0 agent invoqué. Le travail
  est fait par `validate-readiness.ps1` (structurel) + `validate-semantic.ps1`
  (sémantique low-cost, vocabulaire + regex).
- **Idempotente** : relancer `/spec-validate {n}` régénère le rapport.
- **Read-only sur SPEC/US/HTML** : aucune modification des artefacts
  (l'humain corrige manuellement après NO-GO).
- **Ne lance JAMAIS automatiquement `/dev-run`** : la décision finale
  est laissée à l'humain (ou à `/sdd-full` qui chaîne les commandes).
- **Économie v6.0** : –1.4M tokens par `/sdd-full` vs v5.0 (suppression
  agent validator + lectures sémantiques associées).
