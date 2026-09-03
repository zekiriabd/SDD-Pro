# Tech FEAT: qt-cpp (desktop)

> §2.4 (Librairies) regeneree depuis `qt-cpp.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id qt-cpp`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits le 2026-09-02. Les lignes Qt disponibles ont été relevées sur `download.qt.io` (6.5, 6.8, 6.9, 6.10, 6.11) ; **6.8 est retenue comme LTS**. Premier stack `cmake` du catalogue : le `buildSystem` correspondant a été ajouté au schéma, au validateur et à `sync_stack_md.py` au même passage. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `cmake --build` n'a tourné en CI (aucune toolchain Qt disponible). Non supporté commercialement en l'état.
Tech FEAT ID: tech-qt-cpp
Scope: **client desktop multiplateforme natif** — application **C++20 + Qt 6.8 LTS (Widgets)** dans UN seul projet `{AppName}/`. Compilée en binaire natif pour Windows, Linux et macOS. Pas de séparation `{BackendName}` / `{LibName}`.

> ⚠️ **La licence Qt est un arbitrage à trancher AVANT de choisir ce stack**, pas après. Voir §2.3 — c'est la contrainte la plus structurante du stack, et elle est budgétaire autant que technique.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application Qt Widgets native**, compilée pour chaque OS cible :

- **C++20** — compilation AOT, pas de runtime à installer
- **Qt Widgets** — contrôles desktop classiques, rendu proche du système sur chaque plateforme
- **Signaux / slots** — le mécanisme d'événements de Qt, vérifié à la compilation avec la syntaxe pointeur-sur-membre
- **CMake** — le système de build, avec `find_package(Qt6 ...)`
- **QTest** — tests unitaires, inclus dans Qt

Architecture cible :

```
{AppName}/
├── CMakeLists.txt                 ── cible principale + find_package
├── CMakePresets.json              ── presets debug/release par plateforme
├── src/
│   ├── main.cpp
│   ├── presentation/
│   │   ├── windows/               ── QMainWindow, dialogues
│   │   ├── widgets/               ── widgets reutilisables
│   │   └── models/                ── QAbstractItemModel (Model/View)
│   ├── domain/
│   │   ├── entities/
│   │   └── services/              ── regles metier, sans dependance Qt UI
│   ├── data/
│   │   ├── repositories/
│   │   └── api/                   ── QNetworkAccessManager
│   └── infrastructure/
│       └── logging.cpp
├── ui/                            ── fichiers .ui (Qt Designer)
├── resources/
│   └── resources.qrc              ── icones, traductions embarquees
├── translations/                  ── fichiers .ts (capability i18n)
└── tests/
    └── CMakeLists.txt             ── cibles QTest
```

**Différence vs les autres stacks `desktop/`** :
- **Le seul portable ET compilé nativement** : `desktop/electron` est portable mais interprété ; `desktop/wpf`, `desktop/winforms` et `desktop/delphi-vcl` sont natifs mais Windows-only ; `desktop/javafx` est portable mais sur JVM.
- **Empreinte la plus faible du catalogue portable** — quelques dizaines de Mo de RAM, démarrage instantané
- **En contrepartie** : C++ (gestion mémoire, temps de compilation), et une **licence à arbitrer**

---

## 1.2 Couches

- **Windows / Widgets** (`presentation/`) : `QMainWindow`, dialogues, widgets. Câblage seulement.
- **Models** (`presentation/models/`) : `QAbstractItemModel` — l'architecture Model/View de Qt. C'est ce qui permet d'afficher un million de lignes : la vue n'interroge que ce qui est visible.
- **Services** (`domain/services/`) : les règles métier. **Peuvent utiliser `QtCore`** (conteneurs, `QString`) mais **jamais `QtWidgets`** — c'est ce qui les rend testables sous QTest sans afficher de fenêtre.
- **Entities** (`domain/entities/`) : objets métier.
- **Repositories / Api** (`data/`) : persistance et appels distants.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Point d'entrée | `src/main.cpp` |
| Build | `CMakeLists.txt` + `CMakePresets.json` |
| Fenêtre | `src/presentation/windows/{Name}Window.{h,cpp}` |
| Widget | `src/presentation/widgets/{Name}Widget.{h,cpp}` |
| Modèle Model/View | `src/presentation/models/{Name}Model.{h,cpp}` |
| Service métier | `src/domain/services/{Name}Service.{h,cpp}` |
| Entité | `src/domain/entities/{Name}.{h,cpp}` |
| Repository | `src/data/repositories/{Name}Repository.{h,cpp}` |
| Client API | `src/data/api/{Name}ApiClient.{h,cpp}` |
| Formulaire Designer | `ui/{name}_window.ui` |
| Ressources | `resources/resources.qrc` |
| Traductions | `translations/{AppName}_{locale}.ts` |
| Test | `tests/tst_{name}service.cpp` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune règle métier dans un slot d'UI.** Un slot appelle un service, rien de plus.
- **Un service n'inclut jamais `<QtWidgets>`** — sinon il n'est pas testable sans display, et la CI headless échoue.
- **Syntaxe moderne des connexions** : `connect(sender, &Sender::signal, receiver, &Receiver::slot)`. L'ancienne syntaxe `SIGNAL()`/`SLOT()` résout au **runtime** : une faute de frappe passe la compilation et échoue silencieusement.
- **Model/View pour toute liste non triviale** — `QAbstractItemModel`, pas un `QTableWidget` rempli par boucle. Le second matérialise chaque cellule et s'effondre en volume.
- **Parenté Qt pour la durée de vie** : un `QObject` avec parent est détruit avec lui. Pour tout le reste, `std::unique_ptr`. **Pas de `new` nu.**
- **Aucun travail long dans le thread UI** — utiliser la capability `threading` (`QtConcurrent::run` + `QFuture`). Un `QThread` piloté à la main est presque toujours une erreur de conception.
- **Un widget n'est jamais touché depuis un thread secondaire** — Qt l'interdit. Passer par un signal, que Qt marshalle vers le thread propriétaire.
- **`.ui` modifié par Qt Designer**, pas à la main.
- **Chaînes visibles dans `tr()`** dès le départ, même sans traduction prévue — les rattraper après coup coûte un passage sur tout le code.

**Sécurité** :
- **Aucun secret dans le binaire** — un exécutable C++ se parcourt avec `strings`.
- **Requêtes SQL préparées** (`QSqlQuery::prepare` + `bindValue`), jamais de concaténation.
- **Validation TLS laissée active** : ne jamais appeler `QNetworkReply::ignoreSslErrors()` inconditionnellement.
- **Secrets via le trousseau du système** (`libsecret`, Keychain, DPAPI) — Qt n'offre pas d'abstraction, c'est du code par plateforme.
- **Binaire signé** sur Windows (Authenticode) et macOS (notarisation).
- **Pas de `system()` ni de `QProcess` sur une commande construite depuis une saisie utilisateur.**

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Base locale | capability `local-db` (`Qt6::Sql` + pilote `QSQLITE`) |
| Préférences | `QSettings` — registre (Windows), plist (macOS), ini (Linux). **Non chiffré** |
| **Secrets** | trousseau système, par plateforme — jamais `QSettings` |
| Fichiers | `QStandardPaths` pour les emplacements conventionnels |
| Backend distant | `Qt6::Network` (`QNetworkAccessManager`), en CORE |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C** si une base serveur est atteinte : aucun DDL par un agent sur une base existante.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-qt-cpp`
- **Langage** : **C++20**
- **Framework UI** : **Qt 6.8 LTS**, module Widgets
- **Plateformes** : Windows, Linux, macOS
- **Build** : CMake ≥ 3.21 + CMakePresets
- **Compilateurs** : MSVC 2022 / GCC 13+ / Clang 17+
- **Toolchain Qt** : Qt online installer, vcpkg ou Conan
- **Runtime chez l'utilisateur** : bibliothèques Qt déployées avec l'application (`windeployqt`, `macdeployqt`, `linuxdeployqt`)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/CMakeLists.txt`
- **Configure** : `cmake --preset debug`
- **Build** : `cmake --build --preset debug`
- **Run** : `./build/debug/{AppName}`
- **Tests** : `ctest --preset debug --output-on-failure`
- **Déploiement Windows** : `windeployqt build/release/{AppName}.exe`
- **Déploiement macOS** : `macdeployqt build/release/{AppName}.app -dmg`
- **Traductions** : `lupdate` puis `lrelease` (capability `i18n`)
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && cmake --preset debug && cmake --build --preset debug)
test -f workspace/src/{AppName}/CMakeLists.txt
```

- **Smoke Timeout** : 600s (la compilation C++ + `moc` est longue au premier passage)

> **`moc`, `uic` et `rcc`** sont invoqués automatiquement par CMake grâce à `CMAKE_AUTOMOC` / `AUTOUIC` / `AUTORCC` (§2.2.1 STEP 3). Sans eux, toute classe portant `Q_OBJECT` échoue à l'édition de liens sur des symboles de métaobjet manquants — une erreur qui ne mentionne pas `moc`.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/CMakeLists.txt" ]; then

# STEP 0 — Gate toolchain, bloquant
command -v cmake >/dev/null 2>&1 || {
  echo "ERROR: arch {AppName} — CMake introuvable"
  echo "CAUSE: [INFRA_BLOCKED] cmake absent du PATH (>= 3.21 requis)"
  echo "FIX: installer CMake >= 3.21"
  exit 3
}
if [ -z "$Qt6_DIR" ] && [ -z "$CMAKE_PREFIX_PATH" ]; then
  echo "ERROR: arch {AppName} — toolchain Qt introuvable"
  echo "CAUSE: [INFRA_BLOCKED] ni Qt6_DIR ni CMAKE_PREFIX_PATH ne sont definis — find_package(Qt6) echouera"
  echo "FIX: installer Qt 6.8 (online installer, vcpkg ou Conan) puis exporter Qt6_DIR"
  exit 3
fi
cmake --version

APP=workspace/src/{AppName}

# STEP 1 — Arborescence en couches
mkdir -p \
  "$APP/src/presentation"/{windows,widgets,models} \
  "$APP/src/domain"/{entities,services} \
  "$APP/src/data"/{repositories,api} \
  "$APP/src/infrastructure" \
  "$APP/ui" "$APP/resources" "$APP/translations" "$APP/tests"

# STEP 2 — main.cpp minimal
cat > "$APP/src/main.cpp" <<'CPP'
#include <QApplication>
#include "presentation/windows/MainWindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("{AppName}"));

    MainWindow window;
    window.show();

    return app.exec();
}
CPP

# STEP 3 — CMakeLists.txt
#   AUTOMOC / AUTOUIC / AUTORCC sont LOAD-BEARING : sans eux, toute classe
#   Q_OBJECT echoue a l'edition de liens sur des symboles de metaobjet.
cat > "$APP/CMakeLists.txt" <<'CMAKE'
cmake_minimum_required(VERSION 3.21)
project({AppName} VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC_SEARCH_PATHS ${CMAKE_CURRENT_SOURCE_DIR}/ui)

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Widgets Network Test)

qt_standard_project_setup()

qt_add_executable({AppName}
    src/main.cpp
    src/presentation/windows/MainWindow.cpp
    src/presentation/windows/MainWindow.h
)

target_include_directories({AppName} PRIVATE src)
target_link_libraries({AppName} PRIVATE Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Network)

# Traite les avertissements avec le serieux qu'ils meritent en C++.
if (MSVC)
    target_compile_options({AppName} PRIVATE /W4 /permissive-)
else()
    target_compile_options({AppName} PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
add_subdirectory(tests)
CMAKE

# STEP 4 — CMakePresets.json
cat > "$APP/CMakePresets.json" <<'JSON'
{
  "version": 3,
  "configurePresets": [
    {
      "name": "debug",
      "binaryDir": "${sourceDir}/build/debug",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Debug" }
    },
    {
      "name": "release",
      "binaryDir": "${sourceDir}/build/release",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Release" }
    }
  ],
  "buildPresets": [
    { "name": "debug", "configurePreset": "debug" },
    { "name": "release", "configurePreset": "release" }
  ],
  "testPresets": [
    { "name": "debug", "configurePreset": "debug", "output": { "outputOnFailure": true } }
  ]
}
JSON

# STEP 5 — tests/CMakeLists.txt (QTest, inclus dans Qt)
cat > "$APP/tests/CMakeLists.txt" <<'CMAKE'
find_package(Qt6 6.8 REQUIRED COMPONENTS Test)
# Une cible de test par fichier tst_*.cpp — ajoutees par qa au fil des US.
CMAKE

# STEP 6 — Gate
(cd "$APP" && cmake --preset debug && cmake --build --preset debug)

fi
```

**Contrat post-init** :
- `CMakeLists.txt` porte `AUTOMOC`, `AUTOUIC`, `AUTORCC` **et** `find_package(Qt6 6.8 ...)`
- `CMakePresets.json` déclare les presets `debug` et `release`
- `cmake --build --preset debug` sort 0
- `enable_testing()` est actif et `tests/` est ajouté

---

## 2.3 Licence Qt — l'arbitrage à faire en premier

C'est la contrainte la plus structurante de ce stack, et elle n'est pas
technique.

**Qt est en double licence : LGPL-3.0 ou commerciale.** Ce qui découle du choix
LGPL, pour une application dont le code n'est pas ouvert :

| Obligation LGPL | Conséquence concrète |
|---|---|
| **Liaison dynamique** de Qt | Interdit le binaire statique unique. Il faut déployer les `.dll` / `.so` / `.dylib` Qt à côté de l'exécutable (`windeployqt`, `macdeployqt`). |
| **Remplaçabilité** des bibliothèques Qt | L'utilisateur doit pouvoir substituer sa propre version de Qt. Un packaging qui l'empêche (binaire statique, `.dll` signées et vérifiées) sort du cadre. |
| **Mention de la licence** | Le texte LGPL et l'attribution Qt doivent être fournis avec l'application. |

**Une licence commerciale devient nécessaire** dès qu'on veut : un binaire
**statique** à code fermé, l'utilisation de modules **non-LGPL** (voir
ci-dessous), ou l'accès au support Qt. Son coût est significatif et se compte
par développeur et par an — c'est une ligne budgétaire, pas un détail
d'implémentation.

> ⚠️ **`Qt6::Charts` n'est PAS sous LGPL.** Le module Charts (capability
> `charts`) est en **GPL-3.0 ou commerciale**. L'utiliser dans une application
> à code fermé impose une licence commerciale **même en liaison dynamique** —
> contrairement au reste de Qt. C'est le piège de licence le plus fréquent sur
> ce stack, parce que rien dans l'API ne le signale.

### Pourquoi Qt 6.8 et non 6.11

`download.qt.io` expose les lignes **6.5, 6.8, 6.9, 6.10 et 6.11**. Qt désigne
périodiquement une version **LTS** (support étendu, correctifs de sécurité
prolongés) : 6.5 et 6.8 en font partie. La 6.11 est la plus récente mais n'est
pas LTS.

`rules/library-and-stack.md §0` impose « runtime LTS only » — d'où **6.8**.

> **Note de vérifiabilité** : la *présence* des lignes 6.5 à 6.11 sur
> `download.qt.io` a été constatée le 2026-09-02. Leur **désignation LTS**
> relève en revanche de la politique de support commercial de Qt, qui n'est
> pas exposée sous forme machine-lisible. Ce point est à reconfirmer par le
> mainteneur avant tout engagement contractuel.

### Aucune installation par CLI

`buildSystem: cmake` décrit la **compilation**, pas l'installation des
dépendances. Les modules Qt ne s'installent pas paquet par paquet : ils sont
fournis en bloc par une toolchain (Qt online installer, vcpkg ou Conan), puis
résolus par `find_package(Qt6 ...)`.

C'est pourquoi le §2.4 généré liste des lignes `find_package(...)` à écrire
dans `CMakeLists.txt`, et non des commandes à exécuter. Le STEP 0 vérifie donc
la **présence** de la toolchain (`Qt6_DIR` ou `CMAKE_PREFIX_PATH`) plutôt que
de tenter une installation.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Lignes Qt publiées sur `download.qt.io` (2026-09-02) | `cmake --build` |
| Cohérence `.md` ↔ `.libs.json` | `find_package(Qt6)` contre une toolchain réelle |
| — | Désignation LTS de 6.8 (non machine-lisible) |
| — | Déploiement (`windeployqt` / `macdeployqt`) |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/qt-cpp.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id qt-cpp`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Core | 6.8 | Socle Qt : QObject, signaux/slots, boucle d'evenements, conteneurs |
| Gui | 6.8 | Primitives graphiques et gestion des fenetres |
| Widgets | 6.8 | Controles desktop classiques. Retenu plutot que Qt Quick/QML : pour une application metier desktop, les Widgets donnent le rendu natif de chaque OS et un modele de layout adapte au clavier/souris |
| Network | 6.8 | QNetworkAccessManager — client HTTP vers le backend separe optionnel |
| Test | 6.8 | Framework de tests Qt (QTest) — inclus dans la distribution, aucune dependance externe |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| local-db | Sql | 6.8 | base.*locale, sqlite, base.*donnees, hors.*ligne |
| threading | Concurrent | 6.8 | thread, parallel, tache.*fond, traitement.*long |
| charts | Charts | 6.8 | chart, graphique, courbe, visualisation.*donnees |
| svg | Svg | 6.8 | svg, icone.*vectorielle |
| printing | PrintSupport | 6.8 | impression, imprimer, \bpdf\b |
| media | Multimedia | 6.8 | audio, video, lecture.*media, camera |
| webview | WebEngineWidgets | 6.8 | webview, contenu.*web, navigateur.*embarque |
| i18n | LinguistTools | 6.8 | i18n, traduction, multi.*langue, localisation |
| qml-ui | Quick (alt) | 6.8 | qml, interface.*animee, tactile, quick |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Fenêtre | `{Name}Window.{h,cpp}` → `class {Name}Window` | `MainWindow.h` |
| Widget | `{Name}Widget.{h,cpp}` | `CustomerFormWidget.h` |
| Modèle Model/View | `{Name}Model.{h,cpp}` | `CustomerTableModel.h` |
| Service | `{Name}Service.{h,cpp}` | `InvoiceService.h` |
| Entité | `{Name}.{h,cpp}` | `Customer.h` |
| Repository | `{Name}Repository.{h,cpp}` | `CustomerRepository.h` |
| Formulaire Designer | `ui/{name}_window.ui` (snake_case) | `ui/main_window.ui` |
| Test | `tests/tst_{name}service.cpp` | `tests/tst_invoiceservice.cpp` |
| Membre privé | `m_{name}` | `m_customerId` |
| Signal | verbe au passé | `customerSaved()` |
| Slot | `on{Objet}{Evenement}` ou verbe | `onSaveClicked()` |

**Conventions Qt** : classes en `PascalCase`, membres préfixés `m_`, signaux au passé (un signal rapporte un fait accompli), fichiers `.ui` en `snake_case` (c'est ce qu'attend `uic` pour générer `ui_{name}.h`).

**INTERDITS** :
- Classe `Q_OBJECT` sans `.h` séparé — `moc` traite les en-têtes
- Signal nommé à l'impératif (`saveCustomer()`) — c'est le rôle d'un slot
- Widget nommé par défaut dans Designer (`pushButton_2`)
- `using namespace` dans un en-tête

---

## 3. Backend consomme (optionnel)

Ce stack fonctionne **soit** en autonome (capability `local-db`), **soit** en
client d'un backend déclaré en `## Active Tech Specs`.

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | authentification |
| `GET /api/me` | utilisateur courant |

`Qt6::Network` est en CORE : `QNetworkAccessManager` couvre le besoin sans
dépendance supplémentaire. Base URL lue depuis `QSettings` ou un fichier de
configuration — jamais en constante compilée.

**CORS : sans objet** — l'application n'est pas un navigateur.

---

## 4. Versioning et livraison

- **`project({AppName} VERSION x.y.z)`** dans `CMakeLists.txt` — source unique de la version
- **Déploiement des bibliothèques Qt obligatoire** (`windeployqt` / `macdeployqt` / `linuxdeployqt`) : l'application ne démarre pas sans elles. En LGPL, la **liaison dynamique** est de toute façon requise (§2.3).
- **Signature** : Authenticode (Windows), notarisation (macOS)
- **Matrice CI par OS** — la compilation C++ ne se cross-compile pas trivialement

---

## 5. Interdits projet (qt-cpp)

**Architecture** :
- Règle métier dans un slot d'UI
- Service incluant `<QtWidgets>` — casse la testabilité headless
- Syntaxe `SIGNAL()` / `SLOT()` — résolution runtime, faute de frappe silencieuse
- `QTableWidget` / `QListWidget` rempli par boucle pour un volume important — utiliser Model/View
- `new` nu — parenté `QObject` ou `std::unique_ptr`
- Accès à un widget depuis un thread secondaire — passer par un signal
- Travail long dans le thread UI
- `QThread` sous-classé et piloté à la main là où `QtConcurrent` suffit
- `.ui` édité à la main
- Chaîne visible hors de `tr()`

**Build** :
- `AUTOMOC` / `AUTOUIC` / `AUTORCC` désactivés (§2.2)
- `find_package(Qt6)` sans contrainte de version
- Avertissements du compilateur désactivés ou ignorés
- Committer `build/`, `CMakeCache.txt`, `*.user`
- **Lier `Qt6::Charts` sans avoir tranché la licence** (§2.3)
- Binaire statique à code fermé sans licence commerciale (§2.3)

**Sécurité** :
- Secret dans le binaire
- Requête SQL concaténée — utiliser `prepare` + `bindValue`
- `ignoreSslErrors()` inconditionnel
- Secret dans `QSettings`
- `QProcess` ou `system()` sur une commande construite depuis une saisie
- Binaire non signé

---

## 6. Persistance — voir §1.5

`Qt6::Sql` + SQLite via la capability `local-db`. Phase B (DB) d'`arch` : **applicable** si une base serveur est déclarée, **lecture seule** sur une base existante.

---

## 7. Temps reel

- **WebSocket** : module `Qt6::WebSockets` — **non catalogué**, à instruire si nécessaire
- **SSE** : `QNetworkAccessManager` avec lecture incrémentale de la réponse
- **Polling** : `QTimer` + `QNetworkAccessManager` — suffisant dans la plupart des cas
- **Notifications système** : `QSystemTrayIcon::showMessage` — inclus dans Widgets

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Vraie portabilité avec performance native** — c'est le seul du catalogue à cumuler les deux
- **Applications exigeantes** : traitement de données, instrumentation, visualisation lourde
- **Empreinte mémoire faible** et démarrage instantané
- **Équipes C++** existantes
- **Longévité** — Qt est stable depuis plus de vingt ans, les LTS sont réellement supportées

**NE PAS choisir si** :
- ❌ **La licence commerciale n'est pas budgétée et le code est fermé avec liaison statique** — c'est le critère de rejet n°1, et il est contractuel (§2.3)
- ❌ **Aucune compétence C++ dans l'équipe** — gestion mémoire, temps de compilation, outillage : la courbe est la plus raide du catalogue `desktop/`
- ❌ **Time-to-market court** — le RAD de `desktop/delphi-vcl` ou la productivité de `desktop/electron` sont d'un autre ordre
- ❌ **Cible Windows uniquement** → `desktop/wpf` ou `desktop/delphi-vcl` donnent un meilleur rendu natif pour moins d'effort
- ❌ **Équipe web** → `desktop/electron` ; **Python** → `desktop/pyside` (même Qt, sans le C++)
- ❌ **CI/CD simple attendue** — matrice par OS, toolchain Qt à provisionner sur chaque agent

> **Alternative à considérer sérieusement** : `desktop/pyside` expose **le même Qt** depuis Python, sous **LGPL** (binding officiel), sans C++. Pour un outil interne ou un projet où la performance brute n'est pas critique, il livre le même résultat pour une fraction de l'effort.

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-qt-cpp` autonome (capability `local-db`) | 🟡 experimental | jamais validé end-to-end |
| `desktop-qt-cpp` + backend `python-fastapi` + `auth-local` | 🟡 experimental | jamais validé end-to-end |
| `desktop-qt-cpp` + backend `dotnet-minimalapi` + `auth-local` | 🟡 experimental | jamais validé end-to-end |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate toolchain, bloquant** : `cmake` ≥ 3.21 dans le `PATH`, **et** `Qt6_DIR` ou `CMAKE_PREFIX_PATH` défini. Sans toolchain Qt, `find_package(Qt6)` échoue — STOP `[INFRA_BLOCKED]`.
2. **Détecter** `desktop/qt-cpp.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
3. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** (`preflight.validate_stack_combo`)
4. **`AUTOMOC` / `AUTOUIC` / `AUTORCC` sont load-bearing** (STEP 3) — sans eux, toute classe `Q_OBJECT` échoue à l'édition de liens sur des symboles de métaobjet, avec une erreur qui ne mentionne pas `moc`
5. **Pas d'installation de dépendances** : le §2.4 généré décrit des `find_package`, pas des commandes (§2.3). Ne pas tenter d'installer un module Qt paquet par paquet.
6. **Signaler la contrainte de licence** dans l'ADR de Phase C : c'est un arbitrage **budgétaire**, à remonter au Tech Lead. Mentionner explicitement le cas `Qt6::Charts` (GPL/commercial, hors LGPL).
7. **Injecter** la base URL et l'`apiVersion` dans un fichier de configuration ou `QSettings`, jamais en constante compilée
8. **CORS : sans objet** — ne pas configurer d'allowlist côté backend pour ce stack
9. **`## Active UI Specs`** : aucun design system web n'est compatible. Qt Widgets **est** l'UI. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`
10. **Phase B (DB)** : applicable si base serveur, **lecture seule** sur base existante
11. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-qt-cpp.md` documentant Qt 6.8 LTS + Widgets + CMake, **le régime de licence retenu** (LGPL dynamique ou commercial) et le choix Widgets plutôt que QML

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome).

- `dev-backend` **ne touche pas** au projet Qt — il code le backend séparé s'il est déclaré
- `dev-frontend` matérialise **tout** le projet Qt

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `src/presentation/**` | `dev-frontend` |
| `src/domain/**` | `dev-frontend` (c'est le métier du client) |
| `src/data/**` | `dev-frontend` |
| `src/infrastructure/**` | `arch` (create) + `dev-frontend` |
| `ui/**` (`.ui`) | `dev-frontend` — **via Qt Designer**, jamais en édition texte |
| `resources/**` (`.qrc`) | `dev-frontend` |
| `translations/**` | `dev-frontend` (généré par `lupdate`) |
| `CMakeLists.txt`, `CMakePresets.json` | `arch` **exclusif** |
| `tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

command -v cmake >/dev/null 2>&1 || { echo "SKIP: cmake absent"; exit 3; }
[ -n "$Qt6_DIR" ] || [ -n "$CMAKE_PREFIX_PATH" ] || { echo "SKIP: toolchain Qt absente"; exit 3; }

test -f CMakeLists.txt
test -f CMakePresets.json
test -f src/main.cpp

# Load-bearing : sans eux, toute classe Q_OBJECT casse a l'edition de liens (cf. 2.2)
grep -q "CMAKE_AUTOMOC ON" CMakeLists.txt
grep -q "CMAKE_AUTOUIC ON" CMakeLists.txt
grep -q "CMAKE_AUTORCC ON" CMakeLists.txt

# Version Qt contrainte, pas un find_package nu (cf. 5)
grep -q "find_package(Qt6 6.8" CMakeLists.txt

# Qt6::Charts ne doit pas etre lie sans arbitrage de licence (cf. 2.3)
! grep -q "Qt6::Charts" CMakeLists.txt || echo "WARN: Qt6::Charts lie — licence GPL/commerciale, verifier l'ADR"

cmake --preset debug
cmake --build --preset debug
ctest --preset debug --output-on-failure

echo "smoke OK"
```
