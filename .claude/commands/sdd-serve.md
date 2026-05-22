# /sdd-serve — Lance backend + frontend + console en parallèle

> **Renommée v7.0.0** : ex-`/sdd-run` (renommée pour lever l'ambiguïté
> UX avec `/sdd-full` — orchestrateur pipeline — et `/dev-run` —
> orchestrateur dev). `/sdd-serve` est un **utilitaire runtime**
> read-only, jamais un orchestrateur.

Démarre les 3 process runtime du projet généré en arrière-plan :

1. **Backend** (`{BackendName}`) — selon stack actif
2. **Frontend** (`{FrontendName}` aka `{AppName}`) — selon stack actif
3. **Console** SDD (`workspace/console/`) — cockpit de validation

**Lecture seule sur le code généré, aucune invocation d'agent, aucun
build.** Chaque process tourne en `run_in_background` ; les logs
sont accessibles via `BashOutput` / Monitor sur le shell parent.

**Usage :**
- `/sdd-serve` — lance les 3
- `/sdd-serve back` — backend seul
- `/sdd-serve front` — frontend seul
- `/sdd-serve console` — console seule
- `/sdd-serve back front` — combinaison (sous-ensemble)

---

## STEP 1 — Charger Project Config

Read `workspace/input/stack/stack.md` § `## Project Config` :

- `FrontendName` (ou alias `AppName`) → répertoire frontend
- `BackendName` → répertoire backend

Read `## Active Tech Specs` pour identifier :
- **Backend stack** : `backend/kotlin-spring-boot` | `backend/dotnet-minimalapi`
  | `backend/python-fastapi` | `backend/node-express`
- **Frontend stack** : `frontend/react` | `frontend/vue` | `frontend/angular`
  | `frontend/blazor-webassembly`

Si `## Project Config` absent OU `FrontendName`/`BackendName` non lisibles :
```
ERROR: /sdd-serve — Project Config incomplet
CAUSE: [STACK_MALFORMED] FrontendName ou BackendName absent de workspace/input/stack/stack.md
FIX: renseigner FrontendName et BackendName dans ## Project Config
```

---

## STEP 2 — Résoudre la commande de run par stack

### Backend

| Stack actif | Répertoire | Commande de run |
|---|---|---|
| `backend/kotlin-spring-boot` | `workspace/output/src/{BackendName}/` | `./gradlew bootRun` (PowerShell : `.\gradlew.bat bootRun`) |
| `backend/dotnet-minimalapi` | `workspace/output/src/{BackendName}/` | `dotnet run --project {BackendName}.csproj` |
| `backend/python-fastapi` | `workspace/output/src/{BackendName}/` | `uvicorn app.main:app --reload --port 8000` |
| `backend/node-express` | `workspace/output/src/{BackendName}/` | `npm run dev` (fallback `npm start`) |
| `fullstack/*` | `workspace/output/src/{BackendName}/` | suivre §1 du stack fullstack |

### Frontend

| Stack actif | Répertoire | Commande de run |
|---|---|---|
| `frontend/react` | `workspace/output/src/{FrontendName}/` | `npm run dev` (Vite) |
| `frontend/vue` | `workspace/output/src/{FrontendName}/` | `npm run dev` (Vite) |
| `frontend/angular` | `workspace/output/src/{FrontendName}/` | `npm start` (ng serve) |
| `frontend/blazor-webassembly` | `workspace/output/src/{FrontendName}/` | `dotnet watch run` |

### Console

| Répertoire | Commande |
|---|---|
| `workspace/console/` | `npm start` (fastify, défini dans `package.json`) |

---

## STEP 3 — Pré-checks (avant launch)

Pour chaque cible activée :

1. **Répertoire existe** : Glob du dossier cible. Absent → ERROR :
   ```
   ERROR: /sdd-serve — projet absent
   CAUSE: [PROJECT_NOT_INIT] workspace/output/src/{Name}/ introuvable — arch n'a pas tourné
   FIX: lancer /arch-init OU /dev-run {n} pour matérialiser le projet
   ```

2. **Manifest présent** : selon stack
   - Kotlin Spring Boot : `build.gradle.kts` + `gradlew[.bat]`
   - .NET : `*.csproj`
   - Node : `package.json`
   - Python : `pyproject.toml` ou `requirements.txt`
   Absent → même ERROR `[PROJECT_NOT_INIT]`.

3. **Console** : `workspace/console/package.json` + `workspace/console/server.js`.
   Si `node_modules/` absent → lancer `npm install` (sync) AVANT `npm start`.

---

## STEP 4 — Lancement parallèle (`run_in_background`)

Lancer chaque cible activée via Bash avec `run_in_background: true`.
Toutes les commandes en parallèle dans **un seul message** (tool calls
multiples).

### Exemple — combo kotlin-spring-boot + react + console

```bash
# Backend
cd workspace/output/src/CMSPrintBack && .\gradlew.bat bootRun

# Frontend
cd workspace/output/src/CMSPrintFront && npm run dev

# Console (si node_modules présent)
cd workspace/console && npm start
```

PowerShell : utiliser `Set-Location` + `&` au lieu de `cd && cmd` car
`&&` n'existe pas en PowerShell 5.1. Préférer le tool Bash (Git Bash
sur Windows) qui supporte `&&`.

Chaque process retourne un `bash_id`. Conserver les 3 IDs pour STEP 5.

---

## STEP 5 — Rapport (1 passe, format compact)

Après les 3 lancements, afficher en une seule sortie :

```
🚀 SDD Run — process démarrés en arrière-plan

  Backend  ▶ CMSPrintBack         (kotlin-spring-boot) → :8080   [bash_id: xxx]
  Frontend ▶ CMSPrintFront        (react)              → :5173   [bash_id: yyy]
  Console  ▶ workspace/console    (fastify)            → :4000   [bash_id: zzz]
            (default v7.0.0-alpha — was 5173 conflicting with Vite ;
             override via env PORT=)

Logs : BashOutput / Monitor sur bash_id.
Stop : KillShell sur bash_id.
```

Ports inférés selon le stack (valeurs par défaut documentées dans les
`stacks/*.md` §dev) :

| Stack | Port défaut |
|---|---:|
| `backend/kotlin-spring-boot` | 8080 |
| `backend/dotnet-minimalapi` | 5097 |
| `backend/python-fastapi` | 8000 |
| `backend/node-express` | 3000 |
| `frontend/react` (Vite) | 5173 |
| `frontend/vue` (Vite) | 5173 |
| `frontend/angular` | 4200 |
| `frontend/blazor-webassembly` | 5097 |
| `workspace/console` | 4000 (cf. `server.js`) |

Si un override `PORT` / `SERVER_PORT` / `VITE_PORT` est détecté dans
`application.yml` / `.env` / `vite.config.ts`, le mentionner à côté
du port avec un `(override)`.

---

## STEP 6 — Cas particuliers

### 6.1 Aucune cible activée

Si l'argument restreint à un sous-ensemble qui ne matche rien (ex.
`/sdd-serve xyz`) → STOP + ERROR :
```
ERROR: /sdd-serve — cible inconnue
CAUSE: [INVALID_ARG] argument "{arg}" ne matche pas back|front|console
FIX: /sdd-serve [back] [front] [console] (ou sans argument pour les 3)
```

### 6.2 Fullstack mono-projet

Si `appType=fullstack` (1 seul stack `fullstack/*`, ni backend/* ni
frontend/* déclarés), il n'y a qu'**un seul** process à lancer pour
le couple back+front. Adapter le rapport STEP 5 :

```
🚀 SDD Run — fullstack
  Fullstack ▶ {BackendName}   (next | blazor-server | ...) → :{port}
  Console   ▶ workspace/console                              → :4000
```

### 6.3 Console seule (sans projets générés)

Cas valide : utiliser `/sdd-serve console` pour ouvrir le cockpit sans
avoir lancé `/dev-run`. STEP 3 ne vérifie que `workspace/console/`.

### 6.4 Port déjà occupé

Pas de check préalable (coûte un socket scan déterministe non
disponible cross-platform). Si le process échoue au boot, l'utilisateur
voit l'erreur via `BashOutput`. Pas de retry automatique.

---

## Règles de cette commande

- **Read-only** sur `workspace/output/src/**`, `.claude/stacks/**`,
  `workspace/input/stack/stack.md`. Aucun Write/Edit, aucun build,
  aucun agent.
- **Pas de Q/R utilisateur.** Sortie déterministe en 1 passe.
- **Run uniquement.** Pas d'install (sauf `npm install` console si
  `node_modules/` absent — STEP 3.3).
- **Background obligatoire.** Les 3 process tournent en parallèle ;
  jamais en foreground sync (sinon le shell bloque le 1er).
- **Pas de hot-reload custom.** Utilise les commandes dev natives du
  stack (`bootRun`, `npm run dev`, `dotnet watch run`).
- **Pas d'impact sur le pipeline SDD.** N'invoque ni `arch`, ni
  `dev-*`, ni `qa`. Strictement utilitaire runtime.

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[ANALYSIS]` (label runtime, hors pipeline
SDD — pas de phase métier dédiée)
**Plage de progression couverte** : `0-100%` (lifecycle serveurs)

**Granularité cible** : 3-4 updates (start backend, start frontend,
start console, verdict tous OK). Format
`[ANALYSIS] {service} démarré (port {N}). (X%)`.

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- stdout/stderr des process backend/front/console
- détails npm install / dotnet restore
- logs de hot-reload

**Verdict final** : 1 ligne récap ports. Exemple :
`[ANALYSIS] Backend :8080, Front :5173, Console :4000 — tous démarrés. (100%)`.

**Erreurs** : 1L par service qui échoue, classe `[CLASS]` + port en conflit.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
