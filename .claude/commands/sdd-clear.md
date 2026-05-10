# /sdd-clear — Nettoyage des artefacts générés sous `workspace/output/`

Supprime les fichiers générés par le pipeline SDD_Pro sous `workspace/output/` et
ses sous-répertoires. **Destructif** — par défaut mode `dry-run` (aucune
suppression). `--force` requis pour exécuter.

**Logique exécutoire** : 100% PowerShell déterministe via
`.claude/scripts/sdd-clear.ps1` (0 token LLM, 0 agent invoqué).

---

## Utilisation

| Commande | Effet |
|---|---|
| `/sdd-clear` | dry-run global (preview seul) |
| `/sdd-clear --force` | supprime tous les artefacts générés sous `workspace/output/` |
| `/sdd-clear {n}` | dry-run scope SPEC `{n}` uniquement |
| `/sdd-clear {n} --force` | supprime artefacts SPEC `{n}` |
| `/sdd-clear --force --quiet` | rapport 1-ligne |

**Préservés systématiquement** : `workspace/input/**` (sources humaines),
`workspace/output/.audit/**` (log force-bypass), `.gitkeep`.

> Note : la documentation framework (`presentation.html`, `readme.html`,
> guides markdown) vit désormais sous `.claude/docs/` — hors scope
> `/sdd-clear`. Le flag `--all` (legacy v5.0, ciblait `workspace/output/docs/`)
> est retiré.

---

## STEP 1 — Parser les arguments

| Token | Effet |
|---|---|
| `{n}` | entier ≥ 1 → restreint au scope SPEC `{n}` |
| `--force` | active la suppression réelle (sinon dry-run) |
| `--quiet` | rapport condensé 1 ligne |

Token non reconnu → ERROR `[INVALID_ARG]` :
```
ERROR: /sdd-clear — argument invalide
CAUSE: token "{tok}" non reconnu
FIX: usages valides — /sdd-clear [{n}] [--force] [--quiet]
```

---

## STEP 2 — Invoquer le script

```bash
if command -v pwsh >/dev/null 2>&1; then PS_BIN=pwsh; else PS_BIN=powershell; fi
$PS_BIN -NoProfile -ExecutionPolicy Bypass `
  -File .claude/scripts/sdd-clear.ps1 `
  $(if ($n)     { "-SpecNumber $n" }) `
  $(if ($force) { "-Force" }) `
  $(if ($quiet) { "-Quiet" })
```

Le script gère :
- énumération des fichiers cibles (scope global ou par-SPEC)
- garde-fou anti-suppression hors `workspace/output/` (STOP + ERROR si tenté)
- preview ventilé par sous-répertoire
- exécution conditionnelle (`-Force` requis)
- rapport post-exécution (`-Quiet` ou détaillé)
- idempotence stricte (re-run no-op si déjà nettoyé)

---

## STEP 3 — Propagation de la sortie

Relayer `stdout` du script tel quel. Capturer `exit_code` :

| `exit_code` | Signification |
|---|---|
| `0` | Succès (dry-run ou suppression réelle) |
| `2` | Erreur garde-fou (chemin hors périmètre) — bug framework à signaler |
| autre | Erreur PS bas-niveau (permissions, etc.) |

---

## Scope global vs scope par-SPEC

### Scope global (pas d'argument `{n}`)

Sous-répertoires ciblés : `workspace/output/{context, db, plans, qa, src, us, validation}/`.

### Scope par-SPEC (argument `{n}`)

Patterns ciblés :
- `workspace/output/us/{n}-*.md`
- `workspace/output/plans/{n}-*-*.{back,front}.md`
- `workspace/output/validation/{n}-readiness.md`
- `workspace/output/qa/feat-{n}/**`

**NON supprimés en scope par-SPEC** (partagés cross-SPEC) :
`workspace/output/context/`, `workspace/output/db/`, `workspace/output/src/`.

Pour un reset complet (incluant code source), utiliser le scope global
`/sdd-clear --force`.

---

## Cas limites

| Cas | Comportement |
|---|---|
| `workspace/output/` n'existe pas | `Aucun workspace/output/ — rien à nettoyer.` STOP exit 0 |
| Tous sous-dossiers vides | preview vide STEP 2 puis STOP exit 0 |
| `{n}` sans artefact | preview vide STEP 2 puis STOP exit 0 |
| `--force` sur 0 fichier | rapport "0 fichier supprimé" |

---

## Règles de cette commande

- **Destructif par construction** — `--force` explicite requis pour
  toute suppression. Dry-run par défaut.
- **0 agent IA invoqué** — 100% PowerShell déterministe via
  `.claude/scripts/sdd-clear.ps1`. 0 token LLM.
- **Pas de Q/R utilisateur** — autonome, dry-run remplace la
  confirmation interactive.
- **Idempotence stricte** — re-run sans effet une fois nettoyé.
- **Anti-derive sécurité** — script vérifie qu'aucun chemin ne sort
  de `workspace/output/`. Tentative → exit 2 avec ERROR explicite.
- **Préservés systématiquement** : `workspace/input/**`, `workspace/output/.audit/**`,
  `.gitkeep`. Dossiers `workspace/output/{...}/` eux-mêmes préservés (seul leur
  contenu est purgé), pour ne pas casser arborescence IDE/git.
