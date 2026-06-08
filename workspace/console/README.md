# SDD Console — Cockpit de validation

Console web locale pour **consulter** les artefacts SDD_Pro (FEATs, US, plans
techniques) en français lisible PO et **valider manuellement** les étapes
du pipeline `/sdd-full`.

## Démarrage rapide

```bash
cd workspace/console
npm install
node server.js
```

→ http://127.0.0.1:4000

## Stack

- **Frontend** : React 18 via CDN + Babel standalone (zéro build)
- **Backend** : Fastify 5 + `@fastify/static`
- **Données** (depuis v6.10) :
  - `workspace/output/db/console.db` — **source de vérité unique** pour la télémétrie (runs, gates, qa_*, context_budget, token_usage, events). Aucun `.json`/`.jsonl` de stats ne subsiste sur le FS.
  - `workspace/console/status.json` — statuts humains (validations PO/Tech Lead, gates manuels), hors DB pour rester éditable simplement.
  - Scan FS dynamique de `workspace/input/feats/`, `workspace/output/us/`, `workspace/output/plans/`, `workspace/input/ui/` pour l'arbre des artefacts (`/api/tree`).

## Architecture

```
workspace/console/
├── index.html              # entry point (charge React + data-loader + app)
├── styles.css              # design system (OKLCH palette, Inter + JetBrains Mono)
├── app.jsx                 # composants React (compilés au runtime par Babel)
├── data-loader.js          # fetch /api/tree au boot
├── server.js               # Fastify + 4 endpoints
├── lib/
│   └── markdown-filter.js  # parsers SDD_Pro (FEAT / US / plan)
├── status.json             # source de vérité statuts humains (créé par init_status_json.py)
├── package.json
└── README.md
```

## Endpoints API

Tous les endpoints "stats" (audit, state, dashboard, feat, gates) lisent **exclusivement** `workspace/output/db/console.db` depuis la v6.10. Aucun fallback `.jsonl` n'est conservé.

| Verbe | Path | Rôle | Source |
|---|---|---|---|
| `GET`  | `/api/health`            | Smoke check | — |
| `GET`  | `/api/tree`              | Arbo FEATs > US > Plans + status.json fusionné + état pipeline | FS scan + `status.json` |
| `GET`  | `/api/file`              | Contenu brut d'un MD du workspace (path-restricted) | FS |
| `GET`  | `/api/status`            | `status.json` brut | `status.json` |
| `GET`  | `/api/dashboard`         | Vue agrégée toutes FEATs (5 KPIs + 1 ligne par FEAT) | `console.db` |
| `GET`  | `/api/feat/:n`           | Détail d'une FEAT (coverage, quality, security, api-tests) | `console.db` |
| `GET`  | `/api/feat/:n/details`   | Issues sonar (vulns + smells + coverage gaps) | `console.db` |
| `GET`  | `/api/gates?feat=N`      | Historique gates pour 1 FEAT | `console.db` |
| `GET`  | `/api/audit`             | Budget tokens / coût par agent | `console.db` (tables `context_budget` + `token_usage`) |
| `GET`  | `/api/state`             | Dernier run `/sdd-full` + 30 derniers events | `console.db` (tables `runs` + `run_phases` + `events`) |
| `GET`  | `/api/help/:id`          | Page de documentation inline | `workspace/console/help/` |
| `GET`  | `/api/explain`           | Reformulation IA PO-friendly (cache disque content-addressed) | Anthropic API |
| `POST` | `/api/validate`          | Valider/refuser un item (atomic write + lock + broadcast SSE) | `status.json` |
| `POST` | `/api/gate-decide`       | Résout un gate manuel (atomic + broadcast SSE) | `status.json` |
| `GET`  | `/api/events`            | Server-Sent Events (status + tree + status-file + gate) | FS watcher |

### Contract `POST /api/validate`

```json
{
  "kind": "us" | "task",
  "FeatId": "1-FEAT-connexion",
  "usId":   "1-1-Connexion",
  "family": "back" | "front" | "ui" | "qa",   // requis si kind=task
  "decision": "validated" | "rejected" | "pending-validation",
  "comment": "..."                              // optionnel, max 1000 chars
}
```

`decision: "pending-validation"` annule une décision précédente (efface validatedBy/At/comment).

### Events SSE (`/api/events`)

| Type | Quand | Payload |
|---|---|---|
| `status`      | Réponse immédiate à `POST /api/validate` | `{ kind, FeatId, usId, family?, decision, validatedBy, validatedAt }` |
| `status-file` | FS watcher sur `status.json` (changement externe) | Contenu complet du `status.json` |
| `tree`        | FS watcher sur FEATs/US/plans/UI | `{ dir, filename }` |

Le client (`app.jsx`) refetch `/api/tree` sur n'importe lequel de ces 3 events.

## Statuts (5 valeurs)

| Statut | Sens | Couleur |
|---|---|---|
| `not-started`        | Pas encore touché par un agent | gris |
| `in-progress`        | Agent travaille / brouillon produit | bleu |
| `pending-validation` | En attente de validation humaine | orange |
| `validated`          | Validé par humain | vert |
| `rejected`           | Refusé par humain (boucle révision) | rouge |

## Acteurs validateurs

| Item | Validé par |
|---|---|
| **FEAT (feature)** | Aucun (consultation seule) |
| **User Story** | PO Humain |
| **Plan technique back/front** | Tech Lead / Architecte |
| **Maquette UI** | Auto-validé (déposé par UX Designer) |

## Bootstrap du `status.json`

Si `status.json` n'existe pas, lance :

```bash
python .claude/python/sdd_admin/init_status_json.py
```

→ crée `workspace/console/status.json` squelette vide (idempotent).

## Path d'écriture concurrent

`status.json` est partagé entre :
- La console web (clic Valider — LOT 2)
- Le pipeline `/sdd-full` (pose `gates.{n}.afterX = pending` — LOT 3)

Lock file `workspace/console/.status.lock` (création atomique `O_EXCL`,
retry 3× backoff 50ms). Mécanisme aligné sur `.claude/rules/file-ownership.md §4`.

## État actuel — LOT 4 (reformulation IA opt-in)

### LOT 1 — Lecture seule
✅ Tree FEATs > US > Plans + UI mockups  
✅ Détail formaté français déterministe (Critères d'acceptation, Histoire utilisateur, Plans techniques)  
✅ Filtres par statut + chips  
✅ Pipeline state heuristique en topbar  

### LOT 2 — Validation interactive
✅ Boutons Valider/Refuser actifs — POST `/api/validate`  
✅ Commentaire sur refus — textarea inline expand, max 1000 chars  
✅ Annulation de décision — bouton ghost qui repasse en `pending-validation`  
✅ Hot-reload SSE — indicateur live/offline en topbar, reconnexion auto  
✅ FS watcher — modification externe d'un MD recharge le tree automatiquement  
✅ Atomic write + lock — pas de race entre console et `/sdd-full`  
✅ `validatedBy` — `$SDD_USER_EMAIL`, fallback `git config user.email`, fallback `anonymous@local`  

### LOT 3 — Gates manuels dans `/sdd-full`
✅ Bandeau "Validation manuelle" interactif sur les 4 phases (afterUS / afterReadiness / afterPlan / afterCode)  
✅ POST `/api/gate-decide` — atomic write + broadcast SSE `gate`  
✅ Lock partagé Node ↔ Python (`workspace/console/.status.lock`)  
✅ `.claude/python/sdd_scripts/gate_decide.py` côté pipeline (read / pose-pending / set / is-resolved)  
✅ `/sdd-full {n} --manual-gates [--resume]` — articulation propre legacy ↔ LOT 3  

### LOT 4 — Reformulation IA opt-in
✅ Toggle **Vue technique / Vue PO** dans le détail droite  
✅ GET `/api/explain?path=...` — Anthropic SDK + cache disque content-addressed  
✅ Prompt versionné `.claude/templates/explain-po.prompt.md` (règles strictes anti-jargon)  
✅ Cache `workspace/console/.cache/explained/{key}.json` — invalide si contenu source change  
✅ Bouton **Régénérer** (force=1) pour bypasser le cache  
✅ Modèle par défaut **Claude Haiku 4.5** (rapide, économique pour reformulation)  
✅ Toggle Vue PO **désactivé proprement** (icône 🔒) si `ANTHROPIC_API_KEY` absent  
✅ Rendu markdown via marked.js v14 (CDN)

### LOT 5 — Observabilité (`console.db`)
✅ GET `/api/audit` — agrège les tables `context_budget` + `token_usage` de `console.db` par agent (runs, tokens moyens/max, budget, % usage, coût USD, warnings/errors)  
✅ GET `/api/state` — dernier run (table `runs`) + phases (table `run_phases`) + 30 derniers événements (table `events`)  
✅ Panneau **Observabilité** sur la page Home — sous le dashboard, 2 cards :
   - **Budget tokens par agent** : table triée par fréquence, barre d'usage `tokensMax / budgetTokens` (vert < 70%, jaune < 90%, rouge ≥ 90%)
   - **Dernier run `/sdd-full`** : runId, status, phase courante, table des phases avec payload, événements récents (collapsible)
✅ Rafraîchissement auto toutes les 10s + bouton manuel  
✅ Empty states explicites si la DB est vide (pas encore de pipeline lancé)

## Observabilité — `console.db` est la source unique (depuis v6.10)

Toutes les métriques runtime du pipeline SDD_Pro (audit budget, runs, gates, tests API, coverage, quality, security, perf, a11y, code-review, spec-compliance, arch-review, token_usage) sont écrites par le moteur Python dans `workspace/output/db/console.db` (SQLite WAL, 24 tables).

| Table | Producteur principal | Lu par endpoint |
|---|---|---|
| `context_budget` | hook `preflight_agent_budget.py` + `sdd_scripts/context_budget.py` | `/api/audit` |
| `token_usage` | hook `record_token_usage.py` | `/api/audit` |
| `runs` + `run_phases` + `events` | `sdd_scripts/sdd_state.py` | `/api/state` |
| `qa_api_tests` | agent `qa` mode `api-tests` + `ingest_agent_report.py` | `/api/feat/:n`, `/api/dashboard` |
| `qa_coverage` | `parse_coverage.py` | `/api/dashboard`, `/api/feat/:n` |
| `qa_quality` | `quality_scan.py` | `/api/feat/:n/details` |
| `qa_security` / `qa_perf` / `qa_a11y` / `qa_code_review` / `qa_spec_compliance` | auditors dédiés + `ingest_agent_report.py` | `/api/feat/:n/details` |
| `gates` | `gate_decide.py` | `/api/gates` |

Les anciens fichiers `.audit/context-budget.jsonl`, `.state/run-*.json`, `.state/events.jsonl` (architecture LOT 5 v6.9 et antérieures) sont **retirés**. Seuls subsistent côté FS :

| Artefact | Rôle | Statut |
|---|---|---|
| `workspace/output/.sys/.audit/plan-archive/{basename}.{ts}.full.md` | Snapshots des plans avant compaction (`compact_front_plans.py`) | conservé (audit hors-ligne) |
| `workspace/output/.sys/.audit/force-bypass.log` | Une ligne par `/sdd-full --force` (audit humain) | conservé |
| `workspace/output/.sys/.audit/legacy-parallel.log` | Une ligne par `/dev-run` avec `GatedWorkflow: false` | conservé |

Pour repartir d'un état propre (rare — utile en debug du moteur) :
```powershell
Remove-Item workspace/output/db/console.db
python .claude/python/sdd_scripts/init_console_db.py
```
La prochaine invocation du pipeline repeuple la DB idempotemment.

## Variables d'environnement (mises à jour)

| Var | Default | Rôle |
|---|---|---|
| `PORT`                  | `4000` (v7.0.0-alpha, was 5173)  | Port du serveur Fastify (changé pour éviter collision avec Vite frontend) |
| `SDD_USER_EMAIL`        | `git config` ou `anonymous@local` | Identité du validateur (champ `validatedBy`) |
| `ANTHROPIC_API_KEY`     | (absent → toggle Vue PO 🔒)       | Clé API Anthropic pour reformulation IA |
| `SDD_EXPLAIN_MODEL`     | `claude-haiku-4-5-20251001`      | Modèle utilisé pour la reformulation |
| `SDD_EXPLAIN_MAX_TOKENS`| `1500`                           | Plafond tokens output par appel |
| `SDD_EXPLAIN_DISABLE`   | (non défini)                     | `1`/`true` désactive même avec une clé valide |

## Activer la reformulation IA (LOT 4)

```bash
# PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
node server.js

# bash
export ANTHROPIC_API_KEY=sk-ant-...
node server.js
```

Une fois activé, le toggle "Vue PO" devient actif. Premier appel sur
un fichier ~3-8 s, ensuite servi depuis le cache (instantané).

Le cache est content-addressed (SHA-256 de `model + template + file
content`), donc :
- Modification d'un fichier → nouvelle clé, regen automatique
- Modification du prompt template → nouvelle clé, regen automatique
- Changement de modèle → nouvelle clé, regen automatique

Pour vider manuellement le cache :
```bash
rm -rf workspace/console/.cache/explained/
```

## Sécurité

- Bind `127.0.0.1` uniquement (pas exposé réseau)
- `/api/file` et `/api/explain` restreints aux paths sous `workspace/`
- `/api/validate` et `/api/gate-decide` valident strictement les arguments (kind, decision, phase, family enum)
- Lock file `workspace/console/.status.lock` (TTL 10s, retry 5×, backoff 50ms)
- Comment tronqué à 1000 chars côté serveur
- Clé Anthropic lue uniquement depuis `process.env`, jamais loggée
- Cache IA local (jamais transmis sur le réseau côté inbound)
