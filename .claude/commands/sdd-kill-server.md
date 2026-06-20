# /sdd-kill-server — Arrête backend + frontend + console SDD

> **Utilitaire runtime** (depuis v7.0.0) — pendant de `/sdd-serve`.
> Stoppe les 3 process tournant en arrière-plan (Spring Boot / Vite /
> Fastify console) en les identifiant par port. Idempotent. Aucun agent
> invoqué, aucune mutation du code.

Arrête les 3 process runtime du projet généré :
1. **Backend** Java / Spring Boot (port lu depuis `application.yml` ou
   défaut stack — `8080` Spring, `5097` .NET, `8000` FastAPI, etc.)
2. **Frontend** Node / Vite (port lu depuis `vite.config.ts` ou défaut `5173`)
3. **Console** SDD (Node / Fastify, port défaut `4000` ou env `PORT`)

**Usage :**
- `/sdd-kill-server` — kill les 3
- `/sdd-kill-server back` — backend seul
- `/sdd-kill-server front` — frontend seul
- `/sdd-kill-server console` — console seule
- `/sdd-kill-server back front` — sous-ensemble
- `/sdd-kill-server --port 5185` — kill un port arbitraire (utile pour processes orphelins après crash)

**Read-only sur le code généré, mutations limitées au runtime (kill PID).**

---

## STEP 1 — Charger Project Config

Read `workspace/input/stack/stack.md` `## Project Config` + `## Active Tech Specs`
pour identifier :
- **Backend stack** → port défaut canonique :

| Stack | Port défaut | Détection |
|---|---:|---|
| `backend/kotlin-spring-boot` | `8080` (ou `44328` si override `server.port` dans `application.yml`) | grep `server.port:` dans `application.yml` |
| `backend/dotnet-minimalapi` | `5097` | grep `applicationUrl` dans `launchSettings.json` |
| `backend/python-fastapi` | `8000` | constante |
| `backend/node-express` | `3000` | constante |

- **Frontend stack** → port défaut :

| Stack | Port défaut |
|---|---:|
| `frontend/react` (Vite) | `5173` (ou override `server.port` dans `vite.config.ts`) |
| `frontend/vue` (Vite) | `5173` |
| `frontend/angular` | `4200` |
| `frontend/blazor-webassembly` | `5097` |

- **Console** → toujours `4000` (HTTPS) défini dans `workspace/console/server.js`,
  override possible via env `PORT`.

Si `## Project Config` absent → continuer avec les defaults (cas `/sdd-kill-server`
sans projet généré, où seule la console est susceptible de tourner).

---

## STEP 2 — Résoudre les ports à killer

Calculer `$PORTS = liste de tuples (label, port)` selon les arguments :

```python
ports = []
if "back" in args or args == []:
    ports.append(("Backend", read_backend_port_from_appsyml() or DEFAULT_BACK_PORT))
if "front" in args or args == []:
    ports.append(("Frontend", read_frontend_port_from_viteconfig() or DEFAULT_FRONT_PORT))
if "console" in args or args == []:
    ports.append(("Console", 4000))
if "--port" in args:
    ports.append(("Custom", int(arg_value_after_--port)))
```

Anti-derive : tout token inconnu → ERROR `[INVALID_ARG]` :
```
ERROR: /sdd-kill-server — argument invalide
CAUSE: "{arg}" ne matche pas back|front|console|--port
FIX: /sdd-kill-server [back] [front] [console] [--port N]
```

---

## STEP 3 — Procédure de kill par port (Windows / Unix)

Pour chaque `(label, port)` dans `$PORTS`, identifier le PID qui écoute,
puis le tuer. Idempotent : un port libre = no-op silencieux.

### 3.1 — Détection PID (cross-platform)

**Windows (PowerShell ou Git Bash via netstat)** :
```bash
PID=$(netstat -ano | grep ":$PORT " | grep LISTENING | awk '{print $5}' | head -1)
```

**Unix/macOS** :
```bash
PID=$(lsof -ti :$PORT 2>/dev/null | head -1)
# Fallback : ss -tlnp | grep ":$PORT "
```

### 3.2 — Kill PID

**Windows** : `taskkill //F //PID $PID 2>&1` (force kill, attend exit ≤ 5s).

**Unix** : `kill -9 $PID 2>&1`.

### 3.3 — Vérification post-kill

Attendre 1-2s puis re-checker le port :
```bash
sleep 1.5
STILL=$(netstat -ano | grep ":$PORT " | grep LISTENING | head -1)
if [ -n "$STILL" ]; then
  # Process zombie ou re-spawn (Spring Boot daemon ?) — tenter une 2e passe
  PID2=$(echo "$STILL" | awk '{print $5}')
  taskkill //F //PID "$PID2" 2>&1
fi
```

### 3.4 — Émettre 1 ligne par port

```
  ✓ Backend  (port 44328) → killed (PID 27012)
  ✓ Frontend (port 5185)  → killed (PID 29792)
  ⊘ Console  (port 4000)  → not running
```

---

## STEP 4 — Cleanup orphelins (best-effort, optionnel)

Pour les stacks JVM (Spring Boot via Gradle), le wrapper `gradlew` peut
forker un JVM enfant qui survit au kill du wrapper. Détection :

```bash
# Liste tous les java.exe avec dans la ligne de commande "CMSPrintBack" ou app name
wmic process where "name='java.exe'" get processid,commandline 2>/dev/null | grep -i "{AppName}\|{BackendName}\|bootRun"
```

Tuer ces orphelins individuellement (même approche `taskkill //F //PID`).

Skip silencieux sur Unix (lsof + grep app name).

Cleanup analogue pour `node.exe` orphelins (Vite, Fastify) — match sur
cwd ou commandline.

---

## STEP 5 — Récap final (1 bloc compact ≤ 6 lignes)

```
🛑 /sdd-kill-server — 3 process arrêtés

  ✓ Backend  (port 44328) → killed (PID 27012, Java/Spring Boot)
  ✓ Frontend (port 5185)  → killed (PID 29792, Node/Vite)
  ✓ Console  (port 4000)  → killed (PID 16860, Node/Fastify)

Pour redémarrer : /sdd-serve
```

Cas où rien à killer (3 ports libres) :
```
⊘ /sdd-kill-server — aucun process à arrêter (3 ports libres)
```

Cas erreur (PID introuvable malgré port LISTENING) :
```
🟡 /sdd-kill-server — partiel
  ✓ Backend  → killed
  ⚠ Frontend (port 5185) → LISTENING mais PID introuvable (kill manuel requis : Task Manager → java.exe / node.exe)
  ✓ Console  → killed
```

---

## Règles de cette commande

- **Pas de Q/R utilisateur.** Sortie déterministe en 1 passe.
- **Idempotent** : ports libres = no-op silencieux.
- **Best-effort sur orphelins** : si JVM enfant Spring Boot survit, signaler
  via WARNING — pas d'erreur.
- **Pas de modification** des configs/code — uniquement kill PID.
- **Pas d'arrêt de la DB** PostgreSQL ou autres services système — out of scope.
- **Pas d'invocation d'agent** — pure CLI / netstat / taskkill.

---

## Implémentation référence (Claude Code via Bash tool)

L'orchestrateur (commande utilisateur) doit faire les opérations
suivantes en une passe :

```bash
# Variables par défaut
BACK_PORT=${BACK_PORT:-44328}
FRONT_PORT=${FRONT_PORT:-5185}
CONSOLE_PORT=${CONSOLE_PORT:-4000}

# Override depuis configs si disponibles
[ -f workspace/output/src/*/src/main/resources/application.yml ] && \
  BACK_PORT=$(grep -E "^\s*port:" workspace/output/src/*/src/main/resources/application.yml | head -1 | awk '{print $NF}')

[ -f workspace/output/src/*/vite.config.ts ] && \
  FRONT_PORT=$(grep -oE "port:\s*[0-9]+" workspace/output/src/*/vite.config.ts | head -1 | awk -F: '{print $2}' | tr -d ' ')

# Kill function
kill_port() {
  local LABEL=$1 PORT=$2
  local PID=$(netstat -ano 2>/dev/null | grep ":${PORT} " | grep LISTENING | awk '{print $5}' | head -1)
  if [ -z "$PID" ]; then
    echo "  ⊘ ${LABEL} (port ${PORT}) → not running"
    return 0
  fi
  taskkill //F //PID "$PID" >/dev/null 2>&1 || kill -9 "$PID" 2>/dev/null
  sleep 1
  local STILL=$(netstat -ano 2>/dev/null | grep ":${PORT} " | grep LISTENING | awk '{print $5}' | head -1)
  if [ -n "$STILL" ]; then
    taskkill //F //PID "$STILL" >/dev/null 2>&1 || kill -9 "$STILL" 2>/dev/null
  fi
  echo "  ✓ ${LABEL} (port ${PORT}) → killed (PID ${PID})"
}

# Apply
echo "🛑 /sdd-kill-server"
[[ "$*" == *"back"*    || "$*" == "" ]] && kill_port "Backend"  "$BACK_PORT"
[[ "$*" == *"front"*   || "$*" == "" ]] && kill_port "Frontend" "$FRONT_PORT"
[[ "$*" == *"console"* || "$*" == "" ]] && kill_port "Console"  "$CONSOLE_PORT"
echo ""
echo "Pour redémarrer : /sdd-serve"
```

---

## Anti-patterns rejetés

- ❌ Kill par PID hardcodé (fragile entre runs)
- ❌ `pkill -f node` ou `pkill -f java` global (risque collatéral, kille des process non-SDD)
- ❌ Suppression des fichiers logs / output / build (out of scope)
- ❌ Arrêt de PostgreSQL ou autres services système (out of scope)
- ❌ Désinstallation de deps Node/Gradle (réservé Tech Lead manuel)

---

## Use cases typiques

1. **Restart propre** : `/sdd-kill-server && /sdd-serve` (entre deux configs)
2. **Nettoyage avant `/dev-run`** : si build Gradle bloqué par JVM orphelin
3. **Libérer 4000 après crash console** : `/sdd-kill-server --port 4000`
4. **Fin de session dev** : `/sdd-kill-server` pour libérer toutes les ressources

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[ANALYSIS]` (label runtime, hors pipeline
SDD)
**Plage de progression couverte** : `0-100%` (lifecycle serveurs)

**Granularité cible** : 2-3 updates (scan PIDs ports, kill, verdict).
Format `[ANALYSIS] Arrêt {service} (PID {N})... (X%)`.

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- stdout/stderr de `taskkill` / `kill` / `lsof`
- liste exhaustive des PIDs (compteur suffit)

**Verdict final** : 1 ligne récap. Exemple :
`[ANALYSIS] 3 process arrêtés (ports 8080, 5173, 4000). (100%)`.
Ou : `[ANALYSIS] Aucun process actif. (100%)`.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
