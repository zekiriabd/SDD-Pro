---
name: a11y-local
description: Use ONLY when the Tech Lead EXPLICITLY asks to run an accessibility (a11y / WCAG / axe) audit locally against a running SDDPro frontend — phrases like "audit a11y local", "lance axe sur le front", "check accessibilité", "run accessibility scan", "vérifie WCAG en local". Runs axe-core CLI against the served front, pipes the JSON into the existing sdd_scripts/ingest_axe.py bridge (console.db qa_a11y), and renders the verdict via query_console_db.py. Does NOT trigger during /sdd-full, /sdd-poc, /dev-run, or dev-frontend — the pipeline uses CI ingest (ingest_axe.py in .github/workflows/quality.yml), NOT this skill. Mode A (hors-pipeline, à la demande). Read-only sur le code généré.
---

# Skill — Accessibility audit local (axe-core → qa_a11y)

> **Mode A — hors-pipeline (VENDORED.md §Coexistence)**. Ce skill est un
> **outil Tech Lead à la demande**. Il ne s'auto-déclenche JAMAIS pendant
> `/sdd-full`, `/sdd-poc`, `/dev-run` ou l'agent `dev-frontend` : le pipeline
> couvre l'a11y par **ingest CI** (`ingest_axe.py` appelé depuis
> `.github/workflows/quality.yml` auto-généré par `arch`). Ce skill donne au
> Tech Lead le même verdict **en local, avant push**, en réutilisant la
> plomberie existante — il n'invente aucun script ni table.

> **Anti-derive** : aucune modification du code généré (`workspace/src/`).
> Le seul artefact écrit sur disque est le JSON axe transitoire sous
> `workspace/.sys/.a11y/` (jamais `workspace/{feats,us,plans,src}/`). La
> télémétrie va dans `console.db` (table `qa_a11y` existante), lue à la demande.

## Pré-conditions (STEP 0)

1. **Front lancé** : le frontend doit tourner. Le lancer via `/sdd-serve`
   (qui affiche l'URL réelle, ex. `Frontend ▶ … → :5173`). Ports défaut :
   Vite/React `5173`, Angular `4200`, Next/Blazor Server `3000`, autres →
   lire la sortie de `/sdd-serve`.
2. **axe-core CLI dispo** : `npx @axe-core/cli --version` (installé à la volée
   via `npx` si Node présent). Si Node absent → STOP `[QA_FRAMEWORK_MISSING]`
   (l'a11y reste couvert par le CI du projet ; ce skill est local-only).
3. **FEAT connue** : le numéro `{n}` de la FEAT auditée (pour ranger la
   télémétrie dans `qa_a11y` sous le bon FEAT — même clé que l'ingest CI).

Si le front n'est pas joignable → STOP `[NETWORK]` (ne pas ingérer un scan vide
qui écraserait une télémétrie CI valide via `replace_qa_auditor_for_feat`).

## Procédure (STEP 1-3)

### STEP 1 — Scan axe-core local

```bash
mkdir -p workspace/.sys/.a11y
npx @axe-core/cli "$URL" --save workspace/.sys/.a11y/axe-report.json --exit
```

- `$URL` = l'URL affichée par `/sdd-serve` (ou fournie par le Tech Lead).
- Plusieurs pages : passer plusieurs URLs ou relancer par route ; axe agrège
  en un tableau `[result, …]` que `ingest_axe.py` sait normaliser.
- `--exit` fait sortir axe en non-zéro s'il trouve des violations : ignorer ce
  code, c'est l'ingest qui décide du verdict contre `--threshold`.

### STEP 2 — Ingest dans console.db (script existant, 0 invention)

```bash
python -m sdd_scripts.ingest_axe \
  --report workspace/.sys/.a11y/axe-report.json \
  --feat {n} --threshold serious --json
```

- `--threshold serious` = défaut historique `A11yFailOn` (déprécié comme clé
  config v7.0.0 ; le seuil vit maintenant sur le flag). Ajuster `critical` /
  `moderate` / `minor` à la demande.
- Exit codes (cf. entête `ingest_axe.py`) : `0` green/warn, `4` RED (≥1
  violation ≥ threshold), `1` report absent, `2` JSON illisible, `3` schéma axe
  non supporté. En usage Tech Lead, ne PAS mettre `--no-fail` : le code 4 est le
  signal RED.
- Le script mappe chaque `rule_id` axe → classe `[A11Y_*]` (table `AXE_RULE_MAP`),
  persiste dans `qa_a11y` et pose `record_auditor_run(auditor='a11y')`.

### STEP 3 — Rendu du verdict (lecture à la demande)

```bash
python -m sdd_scripts.query_console_db a11y --feat {n} --format md
```

Rend `{verdict, critical, serious, moderate, minor}` en Markdown. Reporter en
chat **1 seule ligne** (protocole `output-protocol.md`) :

```
[QA] A11y local FEAT {n} — 🟢/🟡/🔴, {X} violations ≥ serious. (n/a%)
```

## Interprétation → action (jamais de fix créatif)

| Verdict | Action recommandée |
|---|---|
| 🟢 green | Rien. Télémétrie posée pour `/sdd-review --ensure-scans`. |
| 🟡 warn | Violations < seuil : reporter la liste, laisser le Tech Lead arbitrer. |
| 🔴 red | Violations ≥ seuil. Corriger via l'US frontend fautive : re-run `/dev-frontend {n}-{m}` (le mockup reste SSoT), PAS d'édit sauvage du markup. Les classes (`[A11Y_MISSING_ALT]`, `[A11Y_INPUT_NO_LABEL]`, …) pointent le WCAG SC exact. |

> **Ne jamais** baisser le `--threshold` juste pour passer au vert : c'est un
> masquage, pas un fix. Un défaut a11y réel se corrige dans le composant via
> l'agent `dev-frontend`, ou se documente en ADR si écart assumé.

## Coexistence pipeline (rappel load-bearing)

- **CI (pipeline)** : `ingest_axe.py` appelé par `.github/workflows/quality.yml`
  sur l'artefact `@axe-core/cli`. Bloquant PR selon `continue-on-error`.
- **Local (ce skill)** : même script, même table, invocation Tech Lead. Aucune
  divergence de logique de verdict → un vert local = un vert CI (même seuil).

## Pointeurs

- `.claude/python/sdd_scripts/ingest_axe.py` — pont d'ingest (SSoT logique verdict)
- `.claude/rules/error-classification-legacy.md §1` — taxonomie `[A11Y_*]` × WCAG × sévérité
- `.claude/skills/VENDORED.md` — politique mode A / minage / natif
- `query_console_db.py a11y --feat {n} --format md` — rendu télémétrie
- Pendant : un skill `perf-local` (Lighthouse → `ingest_lighthouse.py` → `qa_performance`) suivrait le même patron.
