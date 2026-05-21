# SDD_Pro

Framework FEAT-driven development pour Claude Code — branche `next` : **v7.0.0-alpha** (cf. [.claude/VERSIONING.md](.claude/VERSIONING.md)). Branche `main` : v6.10.4-LTS (freeze actif jusqu'au 2026-06-18).

> 🌍 [English README](README.en.md) — quickstart + console essentials (les docs FR restent canoniques).

Documentation principale : [.claude/CLAUDE.md](.claude/CLAUDE.md)

---

## 🚀 Quickstart — nouveau projet

**Option recommandée : utiliser ce repo comme [GitHub Template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository).** Cliquer sur **"Use this template"** → "Create a new repository" → cloner localement → lancer le bootstrap interactif :

```bash
# macOS / Linux
python3 bootstrap.py

# Windows (PowerShell)
.\bootstrap.ps1

# Non-interactive (CI / scripted) — uses validated combo C1
python bootstrap.py --combo c1 --skip-install
```

Le bootstrap :
- Demande le nom du projet + 3-4 questions (stack, DB, auth)
- Génère `workspace/input/stack/stack.md` (43 clés Project Config, defaults sûrs)
- Crée la structure `workspace/output/.sys/` complète
- Installe les dépendances Python (`pip install -e .claude/python[dev]`)
- Propose l'install des deps console (`npm install` dans `workspace/console/`)
- Lance un smoke check final

Combos validés bout-en-bout :
- **C1** : .NET Minimal API + React + shadcn + Azure AD + xUnit (recommended)
- **C2** : Kotlin Spring Boot + React + shadcn + Azure AD + JUnit
- `--combo custom` : composition manuelle (4 backends × 4 frontends × 3 UI)

---

## Démarrage rapide (après bootstrap)

1. Éditer les secrets dans [workspace/input/stack/stack.md](workspace/input/stack/stack.md) (DB password, Azure AD client ID, etc.) — fichier gitignored.
2. Dans Claude Code : `/feat-generate <Nom>` — répondre aux 3-6 questions.
3. (Optionnel) déposer mockups HTML sous `workspace/input/ui/{n}-{m}-{Name}.html`.
4. `/sdd-full {n}` — pipeline complet de A à Z.
5. `/sdd-status [{n}]` — vérifier l'état.

---

## Console web — cockpit de validation

Depuis **v6.10**, une console web React + Fastify centralise toute la télémétrie du projet (QA, sécurité, coverage, runs, gates) en lisant la base SQLite `workspace/output/db/console.db`. Aucun fichier `.json` ni `.jsonl` de stats ne subsiste sur le FS — la DB est la source de vérité unique.

### Lancer la console

```bash
cd workspace/console
npm install        # première fois uniquement (Fastify + SDK Anthropic)
npm start          # démarre sur http://127.0.0.1:4000
```

Pré-requis : Node.js ≥ 20 et Python ≥ 3.8 sur le PATH (utilisé pour requêter `console.db` via les helpers `sdd_lib`).

### Trois pages principales

| Page | URL | Fonction |
|---|---|---|
| **Dashboard** *(défaut)* | `/` | KPI cards (FEATs, Tests API, Sécurité, Quality), grille statuts par FEAT, audit qualité style SonarQube (Vulnerabilities / Code Smells / Coverage avec ratings A→E), 4 charts modernes (coverage bars, quality stack, API gate, security donut), sparklines, theme dark/light persisté. |
| **Features** *(ex-SDD Jira)* | `/` puis onglet Features | 3 vues : **Vue PO** (FEAT → US), **Vue technique** (FEAT → US → plans back/front), **Vue UX** (carrousel des mockups HTML par FEAT). Header avec bouton **Rafraîchir** qui re-scanne le FS (les nouveaux fichiers `.md`/`.html` apparaissent dynamiquement). |
| **Documentation** | dropdown topbar | Pages **Fonctionnelle** et **Technique** servies en inline (HTML body extrait, restylé avec le thème natif du site — plus d'iframe). |

### Highlights

- 🎨 **Theme light / dark** avec toggle en topbar, persisté en localStorage, suit `prefers-color-scheme` au premier load. **Logos adaptatifs** (versions claire / sombre).
- 📊 **Charts SVG natifs** (donut, bar stacks, sparklines, gradient progress bars) — palette indigo/cyan/amber/red/emerald/violet, theme-aware. KPI cards avec valeurs en gradient clip-text.
- 🛡 **Section Audit qualité (style SonarQube)** : 1 ligne par FEAT avec ratings A→E (Vulnerabilities, Code Smells, Coverage). Cartes affichées **uniquement** si les données existent en DB (pas de placeholder).
- 🔍 **Drill-down expandable** : un clic sur une ligne FEAT déplie 3 tables (vulnerabilities critique/serious, code smells, coverage gaps) avec file:line, OWASP/CWE, règles, severities colorées.
- 🖼 **Vue UX carrousel** : mockups HTML servis via route statique `/ui/*` (CSS relatif `design-system.css` chargé naturellement, **pas de duplication**). Thumbs cliquables + flèches `‹ ›` + iframe sandboxé.
- 📚 **Documentation inline** : pages Fonctionnelle / Technique rendues directement dans le body (HTML extrait + restylé avec le thème natif du site, plus de fichiers ouverts dans un onglet).
- ⏳ **Loading spinner** : SVG natif animé (rotation gradient + 3 dots pulse, theme-aware).
- 🛡 **Gates manuels** : les phases `afterUS / afterReadiness / afterPlan / afterCode` posées par `/sdd-full --manual-gates` sont résolues depuis la console (POST `/api/gate-decide`), atomic write protégé par lock cross-language Python ↔ Node.
- 🤖 **Reformulation IA** (LOT 4, opt-in) : bouton « Reformuler avec IA » sur les FEAT/US/Plans, utilise l'Anthropic SDK pour produire une version PO-friendly.
- 📡 **Live updates** : SSE (`/api/events`) pousse les changements FS et les modifs `status.json` côté client — l'arbre se met à jour sans rechargement. Bouton **Rafraîchir** force un re-scan du filesystem.

### API HTTP exposée

| Endpoint | Description |
|---|---|
| `GET /api/tree` | Arbre FEATs → US → plans + état `status.json` mergé |
| `GET /api/dashboard` | Vue agrégée toutes FEATs (5 KPIs + 1 ligne par FEAT) |
| `GET /api/feat/:n` | Détail d'une FEAT (coverage, quality, security, api-tests) |
| `GET /api/feat/:n/details` | Issues sonar (vulns + smells + coverage gaps) |
| `GET /api/audit` | Aggrégat tokens / contexte par agent |
| `GET /api/state` | Dernier run + 30 derniers events |
| `GET /api/gates?feat=N` | Historique gates pour 1 FEAT |
| `GET /api/help/:id` | Body extrait + nettoyé d'une page de documentation |
| `GET /api/file?path=…` | Lecture brute d'un fichier MD du workspace |
| `POST /api/validate` | Enregistre la décision PO/Tech Lead sur une US/Task |
| `POST /api/gate-decide` | Résout un gate `afterUS/afterReadiness/...` |
| `GET /api/events` | Server-Sent Events (broadcast modifs FS + gates) |
| `GET /ui/*` | Sert directement `workspace/input/ui/` (mockups HTML avec leur CSS relatif `design-system.css`) |

Détails techniques : [.claude/docs/MCP-SERVER.md](.claude/docs/MCP-SERVER.md) (pour l'exposition MCP côté Python).

---

## Documentation détaillée

### Pour les utilisateurs SDD_Pro

- [.claude/CLAUDE.md](.claude/CLAUDE.md) — entry-point slim (~150 lignes, références vers le détail)
- [.claude/docs/quickstart.md](.claude/docs/quickstart.md) — démarrage pas à pas
- [.claude/docs/architecture.md](.claude/docs/architecture.md) — vision, modèles, agents, stacks
- [.claude/docs/workflow.md](.claude/docs/workflow.md) — 4 phases du pipeline (FEAT → US → Code)
- [.claude/docs/conventions.md](.claude/docs/conventions.md) — anti-derive, idempotence, plans

### Pour les contributeurs framework

- [.claude/CHANGELOG.md](.claude/CHANGELOG.md) — historique versions (focus v6.10 : SQLite source-of-truth)
- [.claude/MIGRATION.md](.claude/MIGRATION.md) — guides de mise à niveau
- [.claude/WORKING-AGREEMENT.md](.claude/WORKING-AGREEMENT.md) — contrat d'autonomie agents
- [.claude/docs/AUDIT-FRAMEWORK.md](.claude/docs/AUDIT-FRAMEWORK.md) — audit complet v6.1.1
- [.claude/docs/DESIGN-FROMPLAN-STRICT.md](.claude/docs/DESIGN-FROMPLAN-STRICT.md) — pattern strict v6.2
- [.claude/docs/MCP-SERVER.md](.claude/docs/MCP-SERVER.md) — serveur MCP (14 tools exposés à Cursor/Windsurf/Claude Desktop)
- [.claude/loader.yml](.claude/loader.yml) — manifest reads/writes par agent
- [.claude/rules/](.claude/rules/) — 9 règles opérationnelles (`backend-first`, `constitution`, `error-classification`, `file-ownership`, `qa-coverage`, `source-first`, `stack-completeness`, `us-granularity`, `cors`, `dev-shared`, `ui-tokens`)

### Documentation dans la console (inline)

Une fois la console lancée, le dropdown **Documentation** de la topbar donne accès à deux pages :

- **Fonctionnelle** — vue d'ensemble du framework (cible : PO / Product Manager / non-tech)
- **Technique** — architecture, agents, pipeline (cible : Tech Lead / dev / architecte)

Ces pages vivent dans [workspace/console/help/](workspace/console/help/) et sont servies inline (le contenu HTML est extrait et restylé avec le thème natif du site).

---

## Stack technique

Framework écrit en **Python** (stdlib pure pour le moteur, pytest pour les tests — suite > 500 tests couvrant `sdd_lib/`, `sdd_scripts/`, `sdd_mcp/`, `sdd_hooks/`). **Console web** : Node.js 20+ (Fastify 5 + React 18 via CDN, pas de build step). **SQLite** (WAL mode) pour la télémétrie centralisée (`workspace/output/db/console.db`, 24 tables, 36 index).

Compte vérifiable localement :
```bash
python -m pytest .claude/python/tests/ -q          # collecte pytest complète (~570)
python -m unittest discover -s .claude/python/tests -p "test_*.py"   # subset compatible stdlib (~530)
```

Aucun runtime applicatif imposé sur le code généré — SDD_Pro produit du code dans le stack du projet cible.

**Catalogue stacks (v7.0.0-alpha)** — terminologie stricte :

| Statut | Définition | Compte |
|:---:|---|:---:|
| 🟢 **validé** | Combo `/sdd-full` testé bout-en-bout sur ≥ 1 FEAT M (3 US, back+front), pipeline complet sans intervention humaine | **2 combos** ([.claude/docs/validated-combos.md](.claude/docs/validated-combos.md)) |
| 🟢 **reference** | Stack avec entête `Validation: 🟢 reference` ET utilisé dans un combo validé | 7 stacks (composants de C1+C2) |
| 🟡 **experimental** | Stack avec entête `Validation: 🟡 experimental` — utilisable mais aucun PoC formel bout-en-bout | 17 stacks |
| ⏸️ **draft (quarantaine)** | Stack dans [`.claude/stacks/_drafts/`](.claude/stacks/_drafts/) — non chargé par le framework actif, procédure de réactivation documentée | 9 stacks |

**Total actif** : 24 stacks répartis : Backend (4), Frontend (4), UI DS (3), QA (9, dont 2 opt-in `mutation-testing` + `playwright`), Auth (2), Archi (2 patterns `mvc`/`ddd`). Détail : [.claude/CLAUDE.md §6](.claude/CLAUDE.md).

> ⚠️ Hors les 2 combos validés `C1`/`C2`, la composition multi-stacks n'a pas été validée par un PoC complet ; le pipeline peut échouer en runtime de manière non triviale. Pour activer une 3ᵉ combo, exécuter d'abord le PoC ROI méthodologie ([.claude/docs/poc-roi-methodology.md](.claude/docs/poc-roi-methodology.md)).

Voir [.claude/python/README.md](.claude/python/README.md) pour les scripts utilitaires.

---

## Licence & auteur

Conçu et maintenu par **SDD-Pro maintainer** · 2026
