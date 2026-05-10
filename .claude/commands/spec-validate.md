# /spec-validate — Implementation Readiness Gate (déterministe pure, v6.0)

Vérifie qu'une SPEC + ses US + mockups HTML sont prêts pour `/dev-run`.
**Validation 100% déterministe** via PowerShell (`validate-readiness.ps1`,
0 token LLM, 0 agent invoqué). L'agent validator a été retiré en v6.0
pour économie tokens — la review sémantique (AC vagues, ambiguïtés)
est désormais à la charge du PO/Tech Lead lors de la review humaine
de la SPEC.

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

## STEP 4 — (retiré v6.0)

> **Anciennement** : invocation de l'agent `validator` (Sonnet 4.6) pour
> validation sémantique (AC vagues, ambiguïtés cross-artefact, hypothèses
> implicites). **Retiré en v6.0** pour économie ~1.4M tokens par
> `/sdd-full`. La review sémantique est désormais à la charge du PO
> humain lors de la relecture de la SPEC.
>
> Si tu veux retrouver une review sémantique, options :
> 1. Relire toi-même la SPEC avant `/dev-run`
> 2. Demander à Claude (en chat libre, hors framework) un audit sémantique
> 3. Réintroduire l'agent validator localement (cf. git history < v6.0)

---

## STEP 5 — Écrire le rapport readiness

Read `.claude/templates/readiness.template.md`.

Composer le rapport final :
- En-tête (date, décision finale)
- §1 = stdout du script PowerShell (STEP 3)
- §2 = (retiré v6.0 — section sémantique vide ou absente du template)
- §3 = liste consolidée des erreurs déterministes
- §4 = liste consolidée des warnings déterministes
- §5 = bloc "Décision finale" selon le résultat
- §6 = prochaines actions

Write `workspace/output/validation/{n}-readiness.md` (mode `create`, écrase si
existe). Créer le répertoire `workspace/output/validation/` si absent.

---

## STEP 6 — Confirmation et sortie

Émettre **un seul bloc final** :

```
{🟢|🟡|🔴} /spec-validate {n}-{SpecName} → {GO|WARN|NO-GO}

Validations  : {N_pass}/{N_total} déterministes (sémantiques retirées v6.0)
Erreurs      : {E} (bloquantes)
Warnings     : {W} (non bloquantes)

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
- Exécuter uniquement le script PowerShell avec `-Json`
- Émettre directement la sortie JSON sur stdout
- Ne PAS écrire `workspace/output/validation/{n}-readiness.md`
- Exit code identique au script

---

## Règles de cette commande

- **100% déterministe (v6.0)** : 0 token LLM, 0 agent invoqué.
  Tout le travail est fait par `validate-readiness.ps1`.
- **Idempotente** : relancer `/spec-validate {n}` régénère le rapport.
- **Read-only sur SPEC/US/HTML** : aucune modification des artefacts
  (l'humain corrige manuellement après NO-GO).
- **Ne lance JAMAIS automatiquement `/dev-run`** : la décision finale
  est laissée à l'humain (ou à `/sdd-full` qui chaîne les commandes).
- **Économie v6.0** : –1.4M tokens par `/sdd-full` vs v5.0 (suppression
  agent validator + lectures sémantiques associées).
