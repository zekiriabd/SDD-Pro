# Tech FEAT: delphi-vcl (desktop)

> §2.4 (Librairies) regeneree depuis `delphi-vcl.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id delphi-vcl`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits le 2026-09-02, en accompagnement de `mobiles/delphi-fmx` (même écosystème, même IDE). Chaque version de lib est le dernier tag de release stable du dépôt GitHub upstream, vérifié à cette date — **aucun registre indexé n'existe pour l'écosystème Delphi**, donc `validate_libs_catalog.py` ne peut pas les cross-checker (cf. §2.3). **Jamais exécuté end-to-end via `/sdd-full`** : aucun `MSBuild` n'a tourné en CI (RAD Studio absent de l'environnement). Non supporté commercialement en l'état.
Tech FEAT ID: tech-delphi-vcl
Scope: **client desktop Windows natif** — application **Delphi VCL** dans UN seul projet `{AppName}/`. Object Pascal compilé en binaire natif Win32/Win64, UI composée de contrôles Windows natifs. Cible **Windows uniquement**. Pas de séparation `{BackendName}` / `{LibName}`.

> **VCL ≠ FMX.** La VCL enveloppe les contrôles **Win32/Win64 du système** : le rendu *est* celui de Windows. FireMonkey (`mobiles/delphi-fmx.md`) dessine ses propres contrôles pour être portable. Choisir la VCL, c'est choisir le meilleur rendu natif Windows contre l'abandon de toute portabilité — cf. §8.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application VCL native Windows** :

- **Object Pascal** compilé **AOT** en binaire natif — pas de runtime à installer chez l'utilisateur
- **VCL** : `TForm` + contrôles Win32 natifs, conçus pour le clavier/souris et le poste de travail
- **RAD** : le concepteur visuel produit un `.dfm` (description de la fiche) associé à un `.pas` (code-behind). C'est le cycle de développement le plus rapide du catalogue pour une application de gestion.
- **Spring4D** : collections génériques, DI et `Nullable<T>` — ce que la RTL ne fournit pas
- **DUnitX** : tests unitaires (livré avec RAD Studio)

Architecture cible :

```
{AppName}/
├── {AppName}.dpr                 ── programme principal
├── {AppName}.dproj               ── projet MSBuild
├── src/
│   ├── Presentation/
│   │   ├── Forms/                ── {Name}Form.pas + .dfm
│   │   ├── Frames/               ── TFrame reutilisables
│   │   └── ViewModels/           ── etat + logique de presentation
│   ├── Domain/
│   │   ├── Entities/             ── classes metier
│   │   ├── Services/             ── regles metier
│   │   └── Interfaces/           ── contrats (pour la DI et les tests)
│   ├── Data/
│   │   ├── Repositories/
│   │   └── Api/                  ── client REST vers le backend optionnel
│   └── Infrastructure/
│       ├── Container.pas         ── enregistrement Spring4D
│       └── Logging.pas
├── tests/
│   └── {AppName}Tests.dpr        ── projet DUnitX separe
└── res/                          ── icones, manifeste, versioninfo
```

**Le point de vigilance structurel** : le RAD encourage à écrire la logique métier
dans le `OnClick` d'un bouton. C'est ce qui produit les `.pas` de 5 000 lignes
que l'on retrouve dans tout parc Delphi ancien. Les règles du §1.4 existent
pour l'éviter.

---

## 1.2 Couches

- **Forms** (`Presentation/Forms/`) : la fiche et son code-behind. **Uniquement** du câblage : lire un contrôle, appeler un ViewModel, rafraîchir l'affichage.
- **ViewModels** (`Presentation/ViewModels/`) : état de l'écran et logique de présentation. Classes ordinaires, **sans référence à un `TForm`** — c'est ce qui les rend testables sous DUnitX.
- **Services** (`Domain/Services/`) : les règles métier. Reçoivent des interfaces, pas des composants visuels.
- **Entities** (`Domain/Entities/`) : objets métier.
- **Interfaces** (`Domain/Interfaces/`) : contrats — le point d'ancrage de la DI Spring4D et des doubles de test.
- **Repositories / Api** (`Data/`) : persistance et appels distants.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Programme principal | `{AppName}.dpr` |
| Projet MSBuild | `{AppName}.dproj` |
| Fiche | `src/Presentation/Forms/{Name}Form.pas` + `{Name}Form.dfm` |
| Frame | `src/Presentation/Frames/{Name}Frame.pas` + `.dfm` |
| ViewModel | `src/Presentation/ViewModels/{Name}ViewModel.pas` |
| Service métier | `src/Domain/Services/{Name}Service.pas` |
| Entité | `src/Domain/Entities/{Name}.pas` |
| Interface | `src/Domain/Interfaces/I{Name}.pas` |
| Repository | `src/Data/Repositories/{Name}Repository.pas` |
| Client API | `src/Data/Api/{Name}ApiClient.pas` |
| Conteneur DI | `src/Infrastructure/Container.pas` |
| Test | `tests/{Name}ServiceTests.pas` |
| Ressources | `res/` (icône, manifeste, VersionInfo) |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune règle métier dans un gestionnaire d'événement.** Un `OnClick` appelle un ViewModel ou un Service, rien de plus. C'est la règle qui distingue un projet Delphi maintenable d'un projet Delphi legacy.
- **Un ViewModel ne référence jamais `Vcl.Forms`** — sinon il n'est pas testable sous DUnitX.
- **Interfaces + Spring4D pour toute dépendance externe** (base, HTTP, horloge, système de fichiers). C'est ce qui permet de tester un Service sans base.
- **`try..finally` sur tout objet créé manuellement.** Object Pascal n'a pas de garbage collector : un `Create` sans `Free` dans un `finally` est une fuite. Les interfaces sont, elles, comptées par référence.
- **Aucun travail long dans le thread principal** — l'UI VCL est mono-thread et se figerait. Utiliser la capability `threading` (OmniThreadLibrary) ou `TTask`.
- **Grilles volumineuses en `VirtualTreeView`** (capability `data-grid`) : `TListView` et `TStringGrid` s'effondrent au-delà de quelques milliers de lignes, car ils matérialisent chaque élément.
- **`.dfm` modifié par le concepteur**, pas à la main — le format est positionnel et sensible.
- **Pas de variable globale** pour porter l'état applicatif — passer par le conteneur DI.

**Sécurité** :
- **Aucun secret dans le binaire** — un `.exe` Delphi se parcourt avec `strings`. Toute clé sensible passe par le backend déclaré en `## Active Tech Specs`.
- **Chaîne de connexion hors du binaire** : fichier de configuration protégé par les ACL, ou service distant. Jamais en constante.
- **Requêtes SQL paramétrées** (`TFDQuery.ParamByName`), jamais de concaténation — l'injection SQL est le défaut le plus fréquent des applications de gestion Delphi.
- **Jeton en mémoire uniquement**, ou dans le Credential Manager Windows via l'API DPAPI. Jamais dans un `.ini`.
- **Binaire signé** (Authenticode) — sans signature, SmartScreen bloque l'installation chez l'utilisateur.
- **Manifeste avec `requestedExecutionLevel: asInvoker`** — ne pas exiger l'élévation par défaut.

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Base locale de poste | **FireDAC + SQLite** (livré avec RAD Studio) |
| Base serveur (SQL Server, Oracle, PostgreSQL) | **FireDAC** (livré) ou capability `db-universal` (UniDAC, commercial) |
| Alternative libre au commercial | capability `db-zeos` (ZeosLib) |
| ORM | capability `ormot-orm` (mORMot2) |
| Préférences | `TIniFile` ou registre — **non chiffré**, jamais de secret |

FireDAC est fourni avec RAD Studio et n'apparaît donc pas au catalog : ce n'est
pas une dépendance à installer.

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C.** Sur une base **existante**,
> un agent n'exécute **jamais** de DDL : il écrit le SQL souhaité dans
> `workspace/db/migration-pending.sql` et émet `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-delphi-vcl`
- **Langage** : Object Pascal (Delphi 13 / RAD Studio 13 « Florence »)
- **Framework UI** : VCL — contrôles Windows natifs
- **Plateformes** : **Windows uniquement** (Win32 + Win64)
- **Build** : `MSBuild.exe` sur le `.dproj`
- **IDE** : RAD Studio 13 Florence (12 Athens / 11 Alexandria également supportés)
- **Gestionnaires de paquets** : GetIt, DPM, Boss, ou clone + search path
- **Runtime chez l'utilisateur** : **aucun** — binaire natif autonome

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/{AppName}.dproj`
- **Pré-requis** : `rsvars.bat` du RAD Studio Command Prompt doit être sourcé (il place MSBuild et les chemins Delphi dans le `PATH`)
- **Build Debug Win64** : `MSBuild {AppName}.dproj /p:Config=Debug /p:Platform=Win64`
- **Build Release Win64** : `MSBuild {AppName}.dproj /p:Config=Release /p:Platform=Win64`
- **Build Win32** : `/p:Platform=Win32`
- **Tests** : compiler puis exécuter `tests/{AppName}Tests.dproj` (DUnitX, sortie console)
- **Nettoyage** : `MSBuild {AppName}.dproj /t:Clean`
- **Smoke Command** :

```bash
call "%BDS%\bin\rsvars.bat"
MSBuild workspace/src/{AppName}/{AppName}.dproj /p:Config=Debug /p:Platform=Win64 /v:minimal
test -f workspace/src/{AppName}/Win64/Debug/{AppName}.exe
```

- **Smoke Timeout** : 300s (compilation Delphi + liaison)

> ⚠️ **Ces commandes exigent Windows + RAD Studio installé.** Sur tout autre hôte, `arch` doit émettre `[INFRA_BLOCKED]` — et non un faux vert.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/{AppName}.dproj" ]; then

# STEP 0 — Gate d'hote et de toolchain, bloquant
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) : ;;
  *) echo "ERROR: arch {AppName} — stack delphi-vcl non scaffoldable"
     echo "CAUSE: [INFRA_BLOCKED] hote $(uname -s) — RAD Studio requis (Windows uniquement)"
     echo "FIX: executer le pipeline sur un hote Windows avec RAD Studio 12+, ou choisir un stack portable (desktop/qt-cpp, desktop/electron)"
     exit 3 ;;
esac
if [ -z "$BDS" ]; then
  echo "ERROR: arch {AppName} — RAD Studio introuvable"
  echo "CAUSE: [INFRA_BLOCKED] variable BDS non definie — rsvars.bat non source"
  echo "FIX: ouvrir un « RAD Studio Command Prompt », ou appeler rsvars.bat avant le pipeline"
  exit 3
fi

APP=workspace/src/{AppName}

# STEP 1 — Arborescence en couches
mkdir -p \
  "$APP/src/Presentation"/{Forms,Frames,ViewModels} \
  "$APP/src/Domain"/{Entities,Services,Interfaces} \
  "$APP/src/Data"/{Repositories,Api} \
  "$APP/src/Infrastructure" \
  "$APP/tests" \
  "$APP/res"

# STEP 2 — Le .dproj n'est PAS generable en ligne de commande
#   RAD Studio ne fournit aucune CLI equivalente a `dotnet new` : MSBuild
#   CONSTRUIT un .dproj, il ne le CREE pas. Trois voies, par ordre de
#   preference SDD_Pro :
#     (a) copier le template versionne `.sdd/templates/delphi/vcl/{AppName}.dproj`
#         puis substituer le nom de projet et les Library Paths ;
#     (b) generer depuis un .dpr minimal + un .dproj de reference du depot ;
#     (c) creation unique par le Tech Lead dans l'IDE, puis versionnement.
#   arch retient (a) si le template existe, sinon STOP [INFRA_BLOCKED] avec la
#   consigne (c). Un .dproj est un XML MSBuild dont l'ordre des noeuds compte :
#   arch ne le fabrique JAMAIS a la main.

# STEP 3 — Dependances CORE (cf. 2.4.a)
#   L'ecosysteme Delphi n'a pas de gestionnaire unique : chaque entree du
#   catalog porte son propre installCommand (GetIt / DPM / Boss / clone).
#   Voir la section 2.4 generee pour les commandes exactes.

# STEP 4 — Enregistrer les search paths des libs clonees dans le .dproj
#   (noeud <DCC_UnitSearchPath>) — via l'IDE ou une edition XML ciblee.

# STEP 5 — Build de validation
MSBuild "$APP/{AppName}.dproj" /p:Config=Debug /p:Platform=Win64 /v:minimal

fi
```

**Contrat post-init** :
- `{AppName}.dproj` existe et compile en `Debug|Win64`
- L'arborescence en couches est créée
- Les search paths des libs CORE sont enregistrés dans le `.dproj`
- `tests/{AppName}Tests.dproj` existe (projet DUnitX séparé)
- `res/` contient le manifeste (`asInvoker`) et le VersionInfo

---

## 2.3 Versions non indexees — limite structurelle du catalog

C'est la particularité de cet écosystème, et elle est **partagée avec
`mobiles/delphi-fmx`** :

**Delphi n'a pas de registre de paquets indexé.** Il n'existe ni NuGet, ni npm,
ni Maven Central pour l'Object Pascal. Les bibliothèques se consomment :

- **en source**, ajoutées au *search path* du `.dproj` (le cas le plus courant) ;
- via **GetIt**, le gestionnaire intégré à l'IDE — non scriptable de façon fiable ;
- via **DPM** ou **Boss**, gestionnaires communautaires — adoption partielle.

Conséquences opérationnelles, à connaître :

| Conséquence | Détail |
|---|---|
| **Versions non vérifiables** | Chaque version du §2.4 est le dernier **tag de release stable** du dépôt GitHub upstream, relevé le 2026-09-02. `validate_libs_catalog.py` ne peut pas les cross-checker : il n'y a pas d'API à interroger. |
| **Revalidation manuelle** | Un bump exige d'aller lire les releases du dépôt. Aucun outil ne le signalera. |
| **`installCommand` par entrée** | Le champ est renseigné **individuellement** dans le `.libs.json` (GetIt, clone, ou installeur commercial), là où les autres stacks dérivent une commande unique du `buildSystem`. |
| **`buildSystem: msbuild`** | Il décrit la **compilation**, pas l'installation des dépendances. `sync_stack_md.py` émet donc les `installCommand` explicites plutôt qu'une commande générée. |

> **Drift de schéma fermé au même audit** : `msbuild` était accepté par
> `validate_libs_catalog.py` mais **absent de l'enum `buildSystem`** du
> `libs-catalog.schema.json` — `mobiles/delphi-fmx` violait donc le schéma
> qu'il déclare en `$schema`. Corrigé le 2026-09-02.

### Libs livrées avec RAD Studio (absentes du catalog)

**FireDAC** (accès aux bases), **Indy** (réseau) et **DUnitX** (tests) sont
fournis avec l'IDE. FireDAC n'apparaît pas au §2.4 — ce n'est pas une
dépendance à installer. Indy et DUnitX y figurent uniquement pour **fixer la
version attendue**, avec un `installCommand` qui le dit explicitement.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Dernier tag de release stable de chaque dépôt upstream (GitHub, 2026-09-02) | `MSBuild` sur un `.dproj` réel |
| Existence des dépôts et cohérence des licences (commercial vs libre) | Exécution de DUnitX |
| Cohérence `.md` ↔ `.libs.json` | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/delphi-vcl.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id delphi-vcl`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Spring4D | 2.0.0 | Collections generiques, DI et Nullable<T> — le socle qui manque a la RTL Delphi |
| JsonDataObjects | 1.9.6 | Parseur JSON — nettement plus rapide que System.JSON de la RTL, et son API est plus sure |
| Delphi-Neon | 4.1.0 | Serialisation objet <-> JSON par RTTI — evite d'ecrire un mapper par classe |
| Indy | 10.6.3 | Pile reseau (HTTP, TLS) — livree avec RAD Studio, listee ici pour fixer la version attendue |
| DUnitX | 0.5.1 | Framework de tests unitaires — livre avec RAD Studio |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| data-grid | VirtualTreeView | 8.1.0 | grille, arbre, grande.*liste, tableau.*volumineux, treeview |
| threading | OmniThreadLibrary | 3.07.9 | thread, parallel, tache.*fond, traitement.*long, asynchrone |
| ormot-orm | mORMot2 | 3.35.3 | \borm\b, mormot, rest.*client, persistance |
| db-universal | UniDAC | 11.0 | base.*donnees, unidac, oracle, sql.*server |
| db-zeos | ZeosLib (alt) | 8.0.0 | zeos, base.*donnees.*libre |
| modern-rendering | Skia4Delphi | 7.3.0 | svg, animation, rendu.*moderne, lottie, skia |
| jwt-auth | Delphi-JOSE-JWT | 4.0.2 | \bjwt\b, token, authentification |
| openssl | Delphi-OpenSSL | 1.0.43 | openssl, chiffrement, certificat |
| pdf-generation | SynPDF | 3.35.3 | \bpdf\b, impression, export.*pdf |
| memory-manager | FastMM5 | 5.07 | fuite.*memoire, memory.*leak, fastmm |
| charts | TeeChart-VCL | 2024.39 | chart, graphique, courbe |
| reporting | FastReport-VCL | 2024.2.20 | rapport, etat, reporting, impression.*complexe |
| redis | Delphi-Redis-Client | 0.7.0 | redis, cache.*distribue |
| method-hooking | DDetours | 2.0 | hook, detour, interception.*methode |
| templating | Sempare.Template | 1.8.1 | template, generation.*texte, publipostage |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Unité de fiche | `{Name}Form.pas` → `T{Name}Form` | `CustomerForm.pas` / `TCustomerForm` |
| Frame | `{Name}Frame.pas` → `T{Name}Frame` | `AddressFrame.pas` |
| ViewModel | `{Name}ViewModel.pas` → `T{Name}ViewModel` | `CustomerViewModel.pas` |
| Service | `{Name}Service.pas` → `T{Name}Service` | `InvoiceService.pas` |
| Interface | `I{Name}.pas` → `I{Name}` | `ICustomerRepository.pas` |
| Entité | `{Name}.pas` → `T{Name}` | `Customer.pas` / `TCustomer` |
| Repository | `{Name}Repository.pas` → `T{Name}Repository` | `CustomerRepository.pas` |
| Test | `{Name}ServiceTests.pas` → `T{Name}ServiceTests` | `InvoiceServiceTests.pas` |
| Champ privé | `F{Name}` | `FCustomerId` |
| Paramètre | `A{Name}` | `ACustomerId` |
| Variable locale | `L{Name}` ou nom simple | `LTotal` |

**Conventions Object Pascal** : types préfixés `T`, interfaces `I`, énumérations
`Tk`/`Te`, champs `F`, paramètres `A`. Ce sont les conventions de la RTL — s'en
écarter rend le code étranger à tout développeur Delphi.

**INTERDITS** :
- Composant visuel nommé par défaut (`Button1`, `Edit1`) — renommer selon son rôle (`btnSave`, `edtCustomerName`)
- Logique dans une unité nommée `Utils.pas` fourre-tout
- Préfixe `T` omis sur une classe
- Unité de plus de 1 000 lignes — découper

---

## 3. Backend consomme (optionnel)

Ce stack fonctionne **soit** en autonome (base locale FireDAC + SQLite),
**soit** en client d'un backend déclaré en `## Active Tech Specs`.

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck (état de connectivité) |
| `POST /api/auth/login` | authentification |
| `GET /api/me` | utilisateur courant |

Base URL lue depuis un fichier de configuration à côté de l'exécutable —
jamais une constante compilée (§1.4).

---

## 4. Versioning et livraison

- **VersionInfo** du `.dproj` renseigné (`FileVersion`, `ProductVersion`) — c'est ce que lit l'utilisateur dans les propriétés du fichier
- **Binaire signé** Authenticode, sinon SmartScreen bloque
- **`apiVersion`** dans la configuration si un backend est consommé : un client desktop n'est pas mis à jour de façon synchrone, le backend doit donc supporter les versions encore déployées

---

## 5. Interdits projet (delphi-vcl)

**Architecture** :
- Règle métier dans un `OnClick`, `OnChange` ou tout gestionnaire d'événement
- ViewModel référençant `Vcl.Forms` ou un composant visuel
- Dépendance externe (base, HTTP, horloge) instanciée directement dans un Service — passer par une interface + DI
- `Create` sans `Free` dans un `finally` — fuite mémoire
- Travail long dans le thread principal (UI figée)
- `TListView` / `TStringGrid` pour plus de quelques milliers de lignes — utiliser la capability `data-grid`
- Variable globale portant l'état applicatif
- `.dfm` édité à la main
- Accès à un composant visuel depuis un thread secondaire — la VCL n'est pas thread-safe, passer par `TThread.Queue`
- `with` (déprécié, masque les portées)
- Unité de plus de 1 000 lignes

**Sécurité** :
- Secret ou chaîne de connexion en constante compilée
- Requête SQL construite par concaténation — utiliser des paramètres
- Jeton persisté dans un `.ini` ou le registre en clair
- Binaire non signé
- Manifeste demandant `requireAdministrator` sans nécessité prouvée
- Log d'un mot de passe ou d'un jeton

**Build / packaging** :
- Committer `Win32/`, `Win64/`, `__history/`, `__recovery/`, `*.dcu`, `*.local`, `*.identcache`
- `.dproj` reconstruit à la main par un agent (XML MSBuild à l'ordre significatif)
- Search paths absolus non paramétrés dans le `.dproj` — utiliser des variables d'environnement
- Compiler en Debug pour une livraison
- Dépendance commerciale (UniDAC, FastReport, TeeChart Pro) ajoutée sans vérification de licence

---

## 6. Persistance — voir §1.5

FireDAC (livré) pour l'accès aux données. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule ; jamais de DDL sur une base existante.

---

## 7. Temps reel

- **WebSocket** : capability `websockets` de `mobiles/delphi-fmx` (`sgcWebSockets`, commercial) — **non catalogué ici**, à instruire avant engagement
- **Polling** : `TTimer` + client HTTP Indy — suffisant pour la plupart des cas de gestion
- **Notifications système** : API Windows (`Shell_NotifyIcon`) via la RTL, aucune dépendance

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Applications de gestion Windows** — le RAD Delphi est le cycle de développement le plus rapide du catalogue pour un écran de saisie ou une grille
- **Rendu 100 % natif Windows** — ce sont les contrôles du système, pas une imitation
- **Aucun runtime à déployer** — un `.exe` autonome, ce qui simplifie radicalement l'installation en parc
- **Équipes Delphi existantes** et parcs applicatifs à maintenir
- **Démarrage instantané et faible empreinte mémoire** — l'écart avec Electron est d'un ordre de grandeur

**NE PAS choisir si** :
- ❌ **Autre OS que Windows nécessaire, même à terme** — la VCL n'est pas portable. Prendre `mobiles/delphi-fmx` (FMX, même langage, portable) ou `desktop/qt-cpp`.
- ❌ **Pas de licence RAD Studio** — c'est un IDE **commercial**, sans édition gratuite pour un usage professionnel. Contrainte budgétaire à arbitrer **avant** le choix du stack.
- ❌ **Aucune compétence Object Pascal dans l'équipe** — le vivier est étroit et le langage ne se réutilise nulle part ailleurs dans le catalogue
- ❌ **Équipe .NET** → `desktop/wpf` ; **équipe web** → `desktop/electron` ; **équipe Python** → `desktop/pyside`
- ❌ **Écosystème de bibliothèques large attendu** — l'offre Delphi est mature mais étroite, et souvent commerciale (§2.3)
- ❌ **CI/CD sur agents Linux** — la compilation exige Windows + RAD Studio installé et licencié sur l'agent

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-delphi-vcl` autonome (FireDAC + SQLite local) | 🟡 experimental | jamais validé end-to-end |
| `desktop-delphi-vcl` + backend `dotnet-minimalapi` + `auth-local` | 🟡 experimental | jamais validé end-to-end |
| `desktop-delphi-vcl` + backend `kotlin-spring-boot` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `desktop-delphi-vcl` + `mobiles/delphi-fmx` (poste + mobile, même langage) | 🟡 experimental | **deux projets distincts** sous `workspace/src/` — cf. §10 |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate d'hôte et de toolchain, bloquant.** Windows **et** variable `BDS` définie (`rsvars.bat` sourcé). Sinon STOP `[INFRA_BLOCKED]`. **Ne pas** produire de scaffolding partiel : un `.dproj` non compilable coûte plus qu'une absence de projet.
2. **Détecter** `desktop/delphi-vcl.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
3. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** dans un même projet (`preflight.validate_stack_combo`). Pour livrer un poste **et** un mobile, déclarer deux `{AppName}` distincts.
4. **`.dproj` : pas de génération en ligne de commande.** MSBuild construit, il ne crée pas. Ordre de préférence : (a) template versionné, (b) `.dproj` de référence du dépôt, (c) STOP `[INFRA_BLOCKED]` avec consigne de création manuelle. **Ne jamais fabriquer un `.dproj` à la main** — c'est un XML MSBuild dont l'ordre des nœuds compte.
5. **Enregistrer les search paths** des libs CORE dans `<DCC_UnitSearchPath>` après clonage
6. **Chaque lib porte son propre `installCommand`** (§2.3) — il n'y a pas de commande d'installation unique dérivable du `buildSystem`
7. **FireDAC est livré** avec RAD Studio : ne pas tenter de l'installer
8. **Injecter** la base URL et l'`apiVersion` dans un fichier de configuration à côté de l'exécutable, jamais en constante
9. **`## Active UI Specs`** : aucun design system web n'est compatible. La VCL **est** l'UI. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`
10. **Phase B (DB)** : applicable, **lecture seule** sur base existante
11. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-delphi-vcl.md` documentant Delphi 13 + VCL, le choix VCL plutôt que FMX (rendu natif contre portabilité), la contrainte de licence RAD Studio et l'absence de registre de paquets

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome). Convention :

- `dev-backend` **ne touche pas** au projet Delphi — il code le backend séparé s'il est déclaré
- `dev-frontend` matérialise **tout** le projet VCL

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `src/Presentation/**` | `dev-frontend` |
| `src/Domain/**` | `dev-frontend` (c'est le métier du client) |
| `src/Data/**` | `dev-frontend` |
| `src/Infrastructure/**` | `arch` (create) + `dev-frontend` |
| `*.dfm` | `dev-frontend` — **via le concepteur uniquement**, jamais en édition texte |
| `{AppName}.dproj` | `arch` **exclusif** (XML MSBuild, jamais édité par un agent) |
| `{AppName}.dpr` | `arch` (create) + `dev-frontend` (ajout d'unités) |
| `res/**` | `arch` (manifeste, VersionInfo) |
| `tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
# Gate d'hote — le reste n'a aucun sens ailleurs
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) : ;; *) echo "SKIP: hote non-Windows"; exit 3 ;; esac
[ -n "$BDS" ] || { echo "SKIP: rsvars.bat non source"; exit 3; }

cd workspace/src/{AppName}

test -f {AppName}.dproj
test -f {AppName}.dpr
test -d src/Domain/Interfaces          # la DI passe par des interfaces (cf. 1.4)
test -d tests

MSBuild {AppName}.dproj /p:Config=Debug /p:Platform=Win64 /v:minimal
test -f Win64/Debug/{AppName}.exe

# Le manifeste ne doit pas exiger l'elevation (cf. 1.4)
! grep -qi "requireAdministrator" res/*.manifest 2>/dev/null

MSBuild tests/{AppName}Tests.dproj /p:Config=Debug /p:Platform=Win64 /v:minimal
./tests/Win64/Debug/{AppName}Tests.exe

echo "smoke OK"
```
