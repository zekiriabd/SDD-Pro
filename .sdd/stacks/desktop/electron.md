# Tech FEAT: electron (desktop)

> §2.4 (Librairies) regeneree depuis `electron.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id electron`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque paquet résolu contre le registre npm. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `electron-vite build` ni `electron-builder` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-electron
Scope: **client desktop multiplateforme** — application **Electron 44 + TypeScript** dans UN seul projet `{AppName}/`. Chromium pour le rendu, Node.js pour l'accès système. Cible Windows + Linux + macOS depuis une base de code unique. Pas de séparation `{BackendName}` / `{LibName}`.

---

# 1. Architecture

## 1.1 Pattern applicatif — trois processus, et c'est la clé

Electron n'est pas « une page web dans une fenêtre ». C'est **trois processus
aux privilèges distincts**, et toute la sécurité du stack repose sur ce
cloisonnement :

| Processus | Runtime | Privilèges | Rôle |
|---|---|---|---|
| **main** | Node.js | **accès complet à l'OS** | fenêtres, menus, système de fichiers, base locale |
| **preload** | contexte isolé | pont contrôlé | expose une API **typée et restreinte** au renderer via `contextBridge` |
| **renderer** | Chromium | **aucun accès Node** | l'UI — c'est une page web |

- **Electron 44** (exige Node ≥ 22.12.0)
- **electron-vite** — construit les trois processus avec rechargement à chaud
- **electron-builder** — empaquette et signe (`.exe` NSIS, `.dmg`, `.AppImage`, `.deb`)
- **TypeScript 6** — typage de l'API exposée par le pont, de bout en bout
- **electron-log** — journal fichier local

Architecture cible :

```
{AppName}/
├── src/
│   ├── main/                      ── processus MAIN (Node, acces OS complet)
│   │   ├── index.ts               ── creation de la fenetre, cycle de vie
│   │   ├── ipc/                   ── handlers ipcMain (frontiere de confiance)
│   │   ├── services/              ── logique metier, base locale, fichiers
│   │   └── store.ts
│   ├── preload/
│   │   ├── index.ts               ── contextBridge.exposeInMainWorld
│   │   └── index.d.ts             ── types de l'API exposee (partages)
│   └── renderer/                  ── UI (page web, SANS Node)
│       ├── index.html
│       └── src/
│           ├── App.tsx
│           ├── components/
│           └── stores/
├── electron.vite.config.ts        ── build des 3 processus
├── electron-builder.yml           ── empaquetage et signature
├── resources/                     ── icones
├── tsconfig.json · tsconfig.node.json · tsconfig.web.json
└── package.json
```

**Différence vs les autres stacks `desktop/`** :
- **Le seul vraiment multiplateforme avec une UI web** : `desktop/qt-cpp` et `desktop/javafx` sont portables aussi, mais avec des toolkits natifs
- **Réutilise les compétences front** — le renderer est une page web, n'importe quel framework du catalogue y fonctionne
- **Le coût est assumé** : ~150 Mo de binaire livré, plusieurs centaines de Mo de RAM par instance. C'est le prix d'embarquer Chromium, et c'est le critère de rejet n°1 (§8).

---

## 1.2 Couches

- **main/index.ts** : création de `BrowserWindow`, cycle de vie de l'app.
- **main/ipc/** : les handlers `ipcMain.handle`. **C'est la frontière de confiance** — tout payload y est validé (§1.4).
- **main/services/** : logique métier, base locale, système de fichiers. Testable sans UI.
- **preload/index.ts** : `contextBridge.exposeInMainWorld` — la seule surface visible du renderer.
- **preload/index.d.ts** : les types de cette surface, **partagés** avec le renderer. C'est ce qui rend le pont typé de bout en bout.
- **renderer/** : l'UI. Ne connaît que `window.api`, jamais Node.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Entrée main | `src/main/index.ts` |
| Handler IPC | `src/main/ipc/{domaine}.ipc.ts` |
| Service (main) | `src/main/services/{name}.service.ts` |
| Schéma de validation IPC | `src/main/ipc/{domaine}.schema.ts` (Zod) |
| Pont preload | `src/preload/index.ts` |
| **Types de l'API exposée** | `src/preload/index.d.ts` |
| Racine renderer | `src/renderer/src/App.tsx` |
| Composant renderer | `src/renderer/src/components/{Name}.tsx` |
| Store renderer | `src/renderer/src/stores/{name}.store.ts` |
| Config build | `electron.vite.config.ts` |
| Config packaging | `electron-builder.yml` |
| Icônes | `resources/icon.{ico,icns,png}` |
| Test unitaire | `src/**/{name}.spec.ts` |
| Test E2E | `e2e/{flow}.spec.ts` (Playwright) |

---

## 1.4 Principes non negociables

**Sécurité — ce sont les règles les plus load-bearing du stack** :

- **`nodeIntegration: false`** et **`contextIsolation: true`** sur chaque `BrowserWindow`. Ce sont les défauts d'Electron depuis la v12 : **ne jamais les désactiver**. Les remettre à l'ancienne valeur donne au code de la page un accès complet au système de fichiers de l'utilisateur.
- **`sandbox: true`** sur le renderer.
- **Toute communication passe par `contextBridge` + IPC.** Jamais `require('fs')` depuis le renderer, jamais `remote`.
- **Tout payload IPC est validé** côté main (capability `ipc-validation`, Zod). Le processus main a un accès complet à l'OS : un handler qui fait confiance à son entrée est équivalent à un endpoint HTTP non validé. C'est la faille la plus spécifique à ce stack.
- **N'exposer que des fonctions, jamais `ipcRenderer` lui-même** : `exposeInMainWorld('api', { readFile: (p) => ipcRenderer.invoke('file:read', p) })`, et non l'objet entier — sinon le renderer peut invoquer n'importe quel canal.
- **`webSecurity` laissé actif**, `allowRunningInsecureContent` à `false`.
- **Navigation restreinte** : intercepter `will-navigate` et `setWindowOpenHandler` pour rejeter toute URL hors allowlist. Sans cela, un lien externe ouvre une fenêtre Electron privilégiée.
- **Pas de secret dans le renderer** — c'est du JS livré, trivialement lisible. Ni dans le main d'ailleurs : le paquet `.asar` s'extrait avec une commande.
- **Mise à jour signée** (capability `auto-update`) : un canal non signé permet l'exécution de code arbitraire sur le poste.

**Architecture** :
- **Aucune logique métier dans le renderer** — elle vit dans `main/services/`. Le renderer affiche.
- **Un service main ne connaît pas l'IPC** : le handler traduit, le service exécute. C'est ce qui rend le service testable.
- **Module natif ⇒ capability `native-rebuild`** : un binaire compilé pour Node ne se charge **pas** dans Electron (ABI différente). `@electron/rebuild` est obligatoire dès qu'on utilise `better-sqlite3`, `serialport` ou `keytar`.
- **`electron` en `devDependencies`** — il est empaqueté, pas installé chez l'utilisateur.
- **Travail long hors du thread principal du main** — sinon la fenêtre se figera, exactement comme sur un stack natif.

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Préférences | capability `settings` (`electron-store`) — **non chiffré**, jamais de jeton |
| Base locale | capability `local-db` (`better-sqlite3`, **côté main uniquement**) + `native-rebuild` |
| Fichiers | `node:fs` côté main, exposé par IPC |
| **Secrets** | `safeStorage` d'Electron (Keychain / DPAPI / libsecret) — **jamais** `electron-store` |
| Backend distant | `fetch` natif (Node 22) côté main |

> **`electron-store` n'est pas un coffre** : c'est un fichier JSON en clair dans
> le répertoire utilisateur. Y écrire un jeton revient à l'écrire dans un
> `.txt`. Pour un secret, `safeStorage` est la seule voie — il est fourni par
> Electron, donc absent du catalog.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-electron`
- **Langage** : TypeScript **6.0.3**
- **Runtime** : Electron **44.1.1** (Chromium + Node) — exige **Node ≥ 22.12.0** pour builder
- **Plateformes** : Windows, Linux, macOS
- **Build** : electron-vite (3 processus) + electron-builder (packaging)
- **UI du renderer** : React par défaut (capability `renderer-react`) — libre
- **Package manager** : npm

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/package.json`
- **Run dev** : `npm run dev` (`electron-vite dev` — rechargement à chaud des 3 processus)
- **Build** : `npm run build` (`electron-vite build`)
- **Empaquetage** : `npm run build:win` / `build:linux` / `build:mac` (electron-builder)
- **Type-check** : `npm run typecheck` (main+preload et renderer ont des `tsconfig` distincts)
- **Tests unitaires** : `npm test` (Vitest)
- **Tests E2E** : `npm run test:e2e` (Playwright, capability `e2e-tests`)
- **Rebuild natif** : `npx @electron/rebuild` (capability `native-rebuild`)
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && npm install --silent && npm run typecheck && npm run build)
test -f workspace/src/{AppName}/src/main/index.ts
test -f workspace/src/{AppName}/src/preload/index.ts
test -d workspace/src/{AppName}/out
```

- **Smoke Timeout** : 420s (`npm install` télécharge le binaire Electron, ~100 Mo)

> **Empaquetage cross-plateforme** : produire un `.dmg` signé exige macOS ; un `.exe` signé exige un certificat Windows. `electron-builder` peut construire pour Linux depuis n'importe quel hôte, mais **pas** signer pour les trois. Prévoir une matrice CI par OS.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/package.json" ]; then

# STEP 0 — Gate Node : Electron 44 exige Node >= 22.12.0
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a>22||(a===22&&b>=12))?0:1)' || {
  echo "ERROR: arch {AppName} — runtime Node insuffisant"
  echo "CAUSE: [INFRA_BLOCKED] Node $(node -v) < 22.12.0 requis par electron 44"
  echo "FIX: installer Node 22 LTS (>= 22.12.0)"
  exit 3
}

# STEP 1 — Scaffold electron-vite (genere les 3 processus + tsconfig separes)
npm create --yes @quick-start/electron@latest {AppName} -- \
  --template react-ts --skip-install
mkdir -p workspace/src && mv {AppName} workspace/src/{AppName}
cd workspace/src/{AppName}

# STEP 2 — Pinner TypeScript sur la ligne 6 AVANT le premier install
npm install --save-dev typescript@6.0.3
npm install --silent

# STEP 3 — Dependances CORE (cf. 2.4.a)
npm install --save-dev \
  electron@44.1.1 \
  electron-vite@5.0.0 \
  electron-builder@26.15.3 \
  vite@8.2.2
npm install \
  @electron-toolkit/preload@3.0.2 \
  @electron-toolkit/utils@4.0.0 \
  electron-log@5.4.4

# STEP 4 — Arborescence
mkdir -p \
  src/main/{ipc,services} \
  src/preload \
  src/renderer/src/{components,stores} \
  resources \
  e2e

# STEP 5 — Durcissement de la fenetre : NON NEGOCIABLE (cf. 1.4)
cat > src/main/window.ts <<'TS'
import { BrowserWindow, shell } from 'electron'
import { join } from 'node:path'

/** Allowlist de navigation — tout le reste part dans le navigateur systeme. */
const ALLOWED_ORIGINS: string[] = []

export function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    show: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      // Les trois lignes qui portent la securite du stack (cf. 1.4).
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  })

  // Sans ces deux gardes, un lien externe ouvre une fenetre Electron privilegiee.
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    if (!ALLOWED_ORIGINS.some((o) => url.startsWith(o))) event.preventDefault()
  })

  return win
}
TS

# STEP 6 — Pont preload : n'exposer que des FONCTIONS, jamais ipcRenderer
cat > src/preload/index.ts <<'TS'
import { contextBridge, ipcRenderer } from 'electron'

// Exposer `ipcRenderer` entier permettrait au renderer d'invoquer n'importe
// quel canal. On expose donc une API nommee et fermee (cf. 1.4).
const api = {
  ping: (): Promise<string> => ipcRenderer.invoke('app:ping'),
}

contextBridge.exposeInMainWorld('api', api)

export type Api = typeof api
TS

cat > src/preload/index.d.ts <<'TS'
import type { Api } from './index'

declare global {
  interface Window {
    api: Api
  }
}
TS

# STEP 7 — Scripts npm
node -e "
  const fs=require('fs');
  const p=JSON.parse(fs.readFileSync('package.json','utf8'));
  p.main='./out/main/index.js';
  p.scripts={...p.scripts,
    dev:'electron-vite dev',
    build:'electron-vite build',
    typecheck:'tsc --noEmit -p tsconfig.node.json && tsc --noEmit -p tsconfig.web.json',
    'build:win':'electron-vite build && electron-builder --win',
    'build:linux':'electron-vite build && electron-builder --linux',
    'build:mac':'electron-vite build && electron-builder --mac'};
  fs.writeFileSync('package.json', JSON.stringify(p,null,2));
"

# STEP 8 — Gate
npm run typecheck
npm run build

fi
```

**Contrat post-init** :
- `src/main/index.ts`, `src/preload/index.ts`, `src/renderer/` existent
- `src/main/window.ts` porte `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`
- `src/preload/index.ts` n'expose **pas** `ipcRenderer`
- `src/preload/index.d.ts` déclare les types de `window.api`
- `package.json` pin `typescript` sur la ligne `6.0` et `main` pointe sur `out/main/index.js`
- `npm run build` sort 0

---

## 2.3 Notes de construction

### Le cloisonnement des processus est la spécification, pas une bonne pratique

Les trois flags du STEP 5 (`nodeIntegration: false`, `contextIsolation: true`,
`sandbox: true`) sont les défauts d'Electron depuis la v12. La tentation de les
désactiver apparaît dès qu'on veut appeler `fs` depuis le renderer — et c'est
exactement ce qu'il ne faut pas faire : cela donne au code de la page un accès
complet au poste de l'utilisateur, y compris à du code tiers chargé par une
dépendance npm du renderer.

La voie correcte est toujours : **handler IPC dans le main + fonction exposée
par le preload**. Plus verbeux, et c'est le point.

### La frontière IPC est une frontière de confiance

Un `ipcMain.handle('file:read', (_e, path) => readFile(path))` laisse le
renderer lire **n'importe quel fichier** du poste. Le handler doit valider et
contraindre :

```ts
const ReadFileInput = z.object({ path: z.string().max(4096) })

ipcMain.handle('file:read', async (_event, raw) => {
  const { path } = ReadFileInput.parse(raw)          // capability ipc-validation
  if (!isInsideUserDataDir(path)) throw new Error('path refuse')
  return readFile(path, 'utf8')
})
```

C'est le même raisonnement qu'un endpoint HTTP : **le payload vient de
l'extérieur**, même si « l'extérieur » est la fenêtre de la même application.

### Modules natifs : l'ABI d'Electron n'est pas celle de Node

`better-sqlite3` installé par npm est compilé pour l'ABI de **Node**. Chargé
dans Electron, il échoue avec un message sur une version de module
incompatible — sans mentionner Electron.

`@electron/rebuild` (capability `native-rebuild`) recompile contre l'ABI
d'Electron. C'est **obligatoire** dès qu'un module natif est utilisé, et cela
doit tourner à chaque changement de version d'Electron.

### `electron-store` n'est pas un coffre

Fichier JSON en clair dans le répertoire utilisateur. Correct pour un thème ou
une taille de fenêtre ; jamais pour un jeton. Le coffre est `safeStorage`,
fourni par Electron (donc absent du catalog).

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (npm, 2026-09-02) | `electron-vite build` |
| `engines.node` d'Electron 44 (`>= 22.12.0`) | `electron-builder` et signature |
| Cohérence `.md` ↔ `.libs.json` | Rebuild d'un module natif |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/electron.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id electron`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| electron | 44.1.1 | Runtime (devDependency : il est empaquete, pas installe chez l'utilisateur). Exige Node >= 22.12.0 |
| electron-vite | 5.0.0 | Build des TROIS processus (main / preload / renderer) avec rechargement a chaud. Sans lui, il faut trois configurations de bundler distinctes |
| electron-builder | 26.15.3 | Empaquetage et signature : .exe (NSIS), .dmg, .AppImage, .deb |
| @electron-toolkit/preload | 3.0.2 | Helpers contextBridge — expose une API typee au renderer sans ouvrir Node |
| @electron-toolkit/utils | 4.0.0 | Utilitaires du processus main (detection dev/prod, raccourcis fenetre) |
| electron-log | 5.4.4 | Journalisation fichier + console, cote main ET renderer. Sur un poste client, le fichier local est le seul journal disponible |
| vite | 8.2.2 | Peer d'electron-vite |
| typescript | 6.0.3 | Pin ligne 6.0 — coherent avec les autres stacks TypeScript du catalogue |
| @types/node | 26.4.1 |  |
| eslint | 10.9.1 |  |
| typescript-eslint | 8.69.0 |  |
| prettier | 3.9.6 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| renderer-react | react | 19.2.8 | react, interface, \bui\b, composant |
| renderer-react | react-dom | 19.2.8 | react |
| renderer-react | @types/react | 19.2.18 | react |
| renderer-react | @types/react-dom | 19.2.5 | react |
| renderer-state | zustand | 5.0.15 | state, store, etat.*global |
| ipc-validation | zod | 4.5.4 | validation, ipc, schema, message.*inter.*processus |
| settings | electron-store | 11.0.2 | preference, reglage, configuration.*utilisateur, settings |
| local-db | better-sqlite3 | 13.0.3 | base.*locale, sqlite, hors.*ligne, donnees.*locales |
| local-db | @types/better-sqlite3 | 9.6.0 | sqlite |
| native-rebuild | @electron/rebuild | 4.2.0 | module.*natif, better-sqlite3, serialport, rebuild |
| auto-update | electron-updater | 6.8.9 | mise.*a.*jour, auto-update, deploiement.*poste |
| dev-tools | electron-devtools-installer | 4.0.0 | devtools, react.*devtools, debug |
| unit-tests | vitest | 4.1.11 | tests.*unitaires, vitest |
| e2e-tests | @playwright/test | 1.62.1 | test.*e2e, playwright, test.*bout.*en.*bout |
| e2e-tests | playwright | 1.62.1 | playwright |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Handler IPC | `src/main/ipc/{domaine}.ipc.ts` | `file.ipc.ts` |
| Canal IPC | `{domaine}:{action}` | `file:read`, `app:ping` |
| Schéma IPC | `src/main/ipc/{domaine}.schema.ts` | `file.schema.ts` |
| Service main | `{name}.service.ts` → `class {Name}Service` | `backup.service.ts` |
| Composant renderer | `{Name}.tsx` (PascalCase) | `CustomerList.tsx` |
| Store renderer | `{name}.store.ts` → `use{Name}Store` | `customer.store.ts` |
| Type de l'API exposée | `src/preload/index.d.ts` → `window.api` | — |
| Test unitaire | `{name}.spec.ts` à côté du sujet | `backup.service.spec.ts` |
| Test E2E | `e2e/{flow}.spec.ts` | `e2e/launch.spec.ts` |

**Convention des canaux IPC** : toujours `domaine:action`, en minuscules. C'est ce qui rend la surface IPC lisible d'un coup d'œil — et donc auditable.

**INTERDITS** :
- Canal IPC sans préfixe de domaine (`read`, `save`)
- Fichier renderer et fichier main de même nom sans distinction de dossier
- `any` sur le type d'un payload IPC — c'est précisément la frontière à typer
- Suffixe `.ts` manquant sur un module preload (le build le résout par extension)

---

## 3. Backend consomme (optionnel)

Ce stack fonctionne **soit** en autonome (capability `local-db`), **soit** en
client d'un backend déclaré en `## Active Tech Specs`.

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | authentification |
| `GET /api/me` | utilisateur courant |

**Les appels réseau se font depuis le `main`**, pas depuis le renderer :
- le jeton reste hors de la page (donc hors d'atteinte du JS du renderer et de ses dépendances) ;
- **aucune contrainte CORS** ne s'applique — le main n'est pas un navigateur. C'est un avantage concret sur `mobiles/ionic-capacitor`, où l'origine WebView doit être allowlistée côté backend.

---

## 4. Versioning et livraison

- **`version`** du `package.json` — c'est elle qu'`electron-builder` inscrit dans l'installeur
- **Signature obligatoire** : Authenticode (Windows), notarisation (macOS). Sans elle, SmartScreen et Gatekeeper bloquent.
- **Matrice CI par OS** (§2.2) : la signature ne se fait pas en cross-compilation
- **`apiVersion`** côté configuration si un backend est consommé — un poste client n'est pas mis à jour de façon synchrone

---

## 5. Interdits projet (electron)

**Sécurité** (les plus graves de ce stack) :
- **`nodeIntegration: true`** — donne au code de la page l'accès complet au poste
- **`contextIsolation: false`**
- **`sandbox: false`** sans justification écrite
- **Exposer `ipcRenderer` entier** par `contextBridge`
- **Handler IPC sans validation du payload** (§2.3)
- **`webSecurity: false`** ou `allowRunningInsecureContent: true`
- `will-navigate` et `setWindowOpenHandler` non interceptés — un lien externe ouvre une fenêtre privilégiée
- Secret dans le renderer **ou** dans le main (le `.asar` s'extrait)
- Jeton dans `electron-store` (§1.5) — utiliser `safeStorage`
- `shell.openExternal` sur une URL non validée — vecteur d'exécution de commande
- Canal de mise à jour non signé
- Module `remote` (retiré, mais des tutoriels le citent encore)

**Architecture** :
- Logique métier dans le renderer
- Service main dépendant d'`ipcMain`
- Module natif sans `@electron/rebuild` (§2.3)
- `electron` en `dependencies` au lieu de `devDependencies`
- Travail long synchrone dans le main — fenêtre figée
- `any` sur un payload IPC

**Build / packaging** :
- Committer `node_modules/`, `out/`, `dist/`, `release/`
- Laisser `npm install` remonter TypeScript au-delà de `6.0.x`
- Prétendre livrer les trois OS depuis un seul agent CI (§2.2)
- Empaqueter sans signature
- `asar` désactivé (expose l'arborescence source telle quelle)

---

## 6. Persistance — voir §1.5

`better-sqlite3` côté main via la capability `local-db` (+ `native-rebuild`). Phase B (DB) d'`arch` : **SKIP** — base locale, pas de scan DB serveur.

---

## 7. Temps reel

- **WebSocket** : `WebSocket` natif (Node 22) côté main, résultat relayé au renderer par IPC
- **SSE** : `fetch` en streaming côté main
- **Notifications système** : API `Notification` d'Electron — natif, aucune dépendance
- **Push** : pas de canal natif ; passer par une connexion persistante ouverte depuis le main

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Équipes front web** livrant du desktop **sans apprendre de toolkit natif** — c'est son argument décisif
- **Trois OS depuis une base de code unique**
- **UI riche et très personnalisée** — tout le CSS et tout l'écosystème npm sont disponibles
- **Réutilisation d'un design system web existant**
- **Time-to-market court**

**NE PAS choisir si** :
- ❌ **Empreinte mémoire ou taille de binaire contraintes** — ~150 Mo livrés, plusieurs centaines de Mo de RAM par instance. C'est le critère de rejet n°1, et il est structurel : Chromium est embarqué.
- ❌ **Démarrage à froid critique** — l'initialisation de Chromium s'ajoute au lancement
- ❌ **Rendu 100 % natif attendu** — l'UI est du web, elle ne ressemblera pas à une application système. Préférer `desktop/wpf` (Windows), `desktop/qt-cpp` (portable natif).
- ❌ **Calcul intensif** — Node reste mono-thread ; il faut des worker threads ou un module natif
- ❌ **Politique de sécurité interdisant le code interprété côté client** — le `.asar` s'extrait
- ❌ **Parc de postes anciens ou peu dotés en RAM**
- ❌ **Équipe .NET** → `desktop/wpf` ; **Delphi** → `desktop/delphi-vcl` ; **Python** → `desktop/pyside`

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-electron` autonome (capability `local-db`) | 🟡 experimental | jamais validé end-to-end |
| `desktop-electron` + backend `node-express` + `auth-local` | 🟡 experimental | affinité forte (même langage, DTOs et schémas Zod partageables) |
| `desktop-electron` + backend `nestjs` + `auth-local` + `postgres` | 🟡 experimental | idem |
| `desktop-electron` + `qa/node-vitest` | 🟡 experimental | capabilities `unit-tests` + `e2e-tests` |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate Node bloquant** : `node -v` ≥ **22.12.0** (`engines` d'Electron 44). Sinon STOP `[INFRA_BLOCKED]`.
2. **Détecter** `desktop/electron.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
3. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** (`preflight.validate_stack_combo`)
4. **Pinner TypeScript sur `6.0.3` avant le premier `npm install`** — cohérence avec les autres stacks TS du catalogue
5. **Le durcissement de la fenêtre est un livrable du bootstrap** (STEP 5), pas une tâche ultérieure : `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`, plus les gardes `will-navigate` / `setWindowOpenHandler`
6. **Le preload n'expose jamais `ipcRenderer`** (STEP 6) — seulement des fonctions nommées
7. **`main` du `package.json` doit pointer sur `out/main/index.js`** (sortie d'electron-vite), pas sur `src/`
8. **Injecter** la base URL et l'`apiVersion` dans la configuration lue par le **main**. Ne rien injecter dans le renderer : ce serait du JS livré.
9. **CORS : sans objet** — les appels partent du main, qui n'est pas un navigateur. Ne pas configurer d'allowlist côté backend pour ce stack (contrairement à `mobiles/ionic-capacitor`).
10. **`## Active UI Specs`** : les design systems web **sont** compatibles ici (le renderer est une page web) — c'est le seul stack `desktop/` dans ce cas. `shadcn` est utilisable si `renderer-react` est actif.
11. **Phase B (DB)** : SKIP — base locale
12. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-electron.md` documentant Electron 44 + TypeScript, le modèle à trois processus, le durcissement retenu et le coût mémoire assumé

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome), mais il a
**deux moitiés aux privilèges différents** — c'est la frontière d'ownership la
plus délicate du catalogue `desktop/` :

- **`dev-frontend`** matérialise `src/renderer/**` (l'UI) **et** `src/preload/**` (le pont, avec ses types)
- **`dev-backend`** matérialise `src/main/**` — services, handlers IPC, accès système. C'est du code privilégié : il relève de la même vigilance qu'un endpoint serveur.

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `src/renderer/**` | `dev-frontend` |
| `src/preload/**` | `dev-frontend` (l'API exposée est le contrat de la vue) |
| `src/main/services/**` | `dev-backend` |
| `src/main/ipc/**` | `dev-backend` — **frontière de confiance**, validation obligatoire |
| `src/main/index.ts`, `src/main/window.ts` | `arch` (create, durcissement) + `dev-backend` |
| `electron.vite.config.ts`, `tsconfig*.json` | `arch` exclusif |
| `electron-builder.yml` | `arch` exclusif |
| `resources/**` | `dev-frontend` |
| `package.json` | `arch` (create) + les deux (deps on-demand) |
| `**/*.spec.ts`, `e2e/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a>22||(a===22&&b>=12))?0:1)'

npm install --silent

test -f src/main/index.ts
test -f src/preload/index.ts
test -f src/preload/index.d.ts
test -d src/renderer

# Durcissement — les trois flags qui portent la securite (cf. 1.4)
grep -q "nodeIntegration: false"  src/main/window.ts
grep -q "contextIsolation: true"  src/main/window.ts
grep -q "sandbox: true"           src/main/window.ts
grep -q "setWindowOpenHandler"    src/main/window.ts

# Le preload ne doit PAS exposer ipcRenderer entier (cf. 1.4)
! grep -q "exposeInMainWorld('electron', ipcRenderer" src/preload/index.ts
! grep -q "exposeInMainWorld(\"electron\", ipcRenderer" src/preload/index.ts

# TypeScript ligne 6, et electron en devDependencies
grep -qE '"typescript": *"[~^]?6\.0\.' package.json
node -e "const p=require('./package.json'); process.exit(p.devDependencies?.electron ? 0 : 1)"

npm run typecheck
npm run build
test -d out

echo "smoke OK"
```
