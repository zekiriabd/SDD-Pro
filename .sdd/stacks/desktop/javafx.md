# Tech FEAT: javafx (desktop)

> §2.4 (Librairies) regeneree depuis `javafx.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id javafx`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits le 2026-09-02, chaque coordonnée résolue contre le `maven-metadata.xml` de Maven Central. **Un piège de résolution a été évité** : la « dernière version » de `org.openjfx:javafx-controls` est un build **early access** (`28-ea+6`) que les filtres de prerelease usuels ne détectent pas (cf. §2.3). **Jamais exécuté end-to-end via `/sdd-full`** : aucun `gradle run` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-javafx
Scope: **client desktop multiplateforme** — application **JavaFX 21 LTS sur JDK 21 LTS** dans UN seul projet `{AppName}/`. Cible Windows + Linux + macOS depuis une base de code unique. Pas de séparation `{BackendName}` / `{LibName}`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application JavaFX MVVM sur la JVM** :

- **FXML** — vues déclaratives, éditables dans Scene Builder. L'équivalent XAML de ce stack.
- **Propriétés observables** (`StringProperty`, `ObservableList`) — data binding **bidirectionnel** natif, ce qui rapproche JavaFX de WPF et l'éloigne de Swing
- **Guice** (capability `dependency-injection`) — JavaFX n'a pas de conteneur, et les Controllers FXML sont instanciés par le `FXMLLoader`
- **Logback + SLF4J** — journal fichier local
- **jlink + jpackage** (plugin `org.beryx.jlink`) — installeur natif **sans JDK requis chez l'utilisateur**

Architecture cible :

```
{AppName}/
├── build.gradle.kts
├── settings.gradle.kts
├── gradle/libs.versions.toml
└── src/main/
    ├── java/
    │   ├── module-info.java           ── JPMS : requis par jlink
    │   └── {package}/
    │       ├── App.java               ── extends Application
    │       ├── presentation/
    │       │   ├── controllers/       ── Controllers FXML
    │       │   ├── viewmodels/        ── proprietes observables
    │       │   └── components/
    │       ├── domain/
    │       │   ├── entities/
    │       │   └── services/
    │       ├── data/
    │       │   ├── repositories/
    │       │   └── api/
    │       └── infrastructure/
    └── resources/
        ├── {package}/views/*.fxml     ── vues (Scene Builder)
        ├── css/app.css                ── feuilles de style JavaFX
        └── i18n/                      ── ResourceBundle
```

**Différence vs les autres stacks `desktop/`** :
- **Portable et data-bindé** : c'est le seul du catalogue à combiner portabilité réelle et binding déclaratif bidirectionnel. `desktop/qt-cpp` est portable mais sans binding comparable ; `desktop/wpf` a le binding mais est Windows-only.
- **Sur JVM** : démarrage plus lent qu'un natif, empreinte mémoire intermédiaire entre Qt et Electron
- **Look/feel jamais totalement natif** — JavaFX dessine ses propres contrôles et les stylise en CSS. C'est le reproche principal fait au stack, et la capability `modern-theme` existe pour l'atténuer.

---

## 1.2 Couches

- **Controllers** (`presentation/controllers/`) : liés à un FXML par `fx:controller`. **Câblage uniquement** — ils lient les contrôles au ViewModel.
- **ViewModels** (`presentation/viewmodels/`) : propriétés observables et logique de présentation. **Aucun import `javafx.scene.control`** — c'est ce qui les rend testables sans démarrer le toolkit.
- **Services** (`domain/services/`) : règles métier. Java pur.
- **Entities** (`domain/entities/`) : objets métier.
- **Repositories / Api** (`data/`) : persistance et appels distants.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path (sous `src/main/`) |
|---|---|
| Point d'entrée | `java/{package}/App.java` (`extends Application`) |
| **Descripteur de module** | `java/module-info.java` |
| Controller FXML | `java/{package}/presentation/controllers/{Name}Controller.java` |
| ViewModel | `java/{package}/presentation/viewmodels/{Name}ViewModel.java` |
| Composant | `java/{package}/presentation/components/{Name}View.java` |
| Service métier | `java/{package}/domain/services/{Name}Service.java` |
| Entité | `java/{package}/domain/entities/{Name}.java` |
| Repository | `java/{package}/data/repositories/{Name}Repository.java` |
| Client API | `java/{package}/data/api/{Name}ApiClient.java` |
| Module Guice | `java/{package}/infrastructure/{Name}Module.java` |
| Vue FXML | `resources/{package}/views/{name}-view.fxml` |
| Styles | `resources/css/app.css` |
| Traductions | `resources/i18n/messages_{locale}.properties` |
| Test | `src/test/java/{package}/{Name}ServiceTest.java` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune règle métier dans un Controller** — il lie la vue au ViewModel, rien de plus.
- **Un ViewModel n'importe pas `javafx.scene.control`** : il expose des `Property` et des `ObservableList` (qui sont dans `javafx.base`), jamais des contrôles. C'est la condition pour le tester sans démarrer le toolkit JavaFX.
- **Binding plutôt qu'affectation** : `label.textProperty().bind(vm.titleProperty())`, et non `label.setText(...)` appelé à chaque changement. C'est tout l'intérêt du stack.
- **`ObservableList` pour les listes liées** — une `ArrayList` ne notifie rien et la vue ne se rafraîchit pas.
- **`TableView` avec `cellValueFactory`** ; pour de très gros volumes, pagination ou chargement paresseux — `TableView` matérialise ses lignes visibles mais garde le modèle entier en mémoire.
- **Aucun travail long sur le JavaFX Application Thread** — utiliser `Task<T>` / `Service<T>`, dont les callbacks reviennent automatiquement sur le bon thread.
- **Un nœud n'est jamais modifié depuis un thread secondaire** — utiliser `Platform.runLater`.
- **`module-info.java` maintenu** : c'est lui qui rend `jlink` possible. Chaque dépendance ajoutée doit y être déclarée (`requires`), et les paquets contenant des Controllers FXML doivent être `opens` vers `javafx.fxml` — sinon la réflexion échoue **au runtime**, pas à la compilation (§2.3).
- **`.fxml` édité dans Scene Builder**, pas à la main.

**Sécurité** :
- **Aucun secret dans le JAR** — un `.jar` se décompile trivialement (`javap`, CFR).
- **Requêtes préparées** (`PreparedStatement`), jamais de concaténation SQL.
- **Secrets via le trousseau du système** — la JVM n'offre pas d'abstraction portable ; c'est du code par plateforme, ou un `KeyStore` protégé par une phrase saisie par l'utilisateur.
- **Installeur signé** : Authenticode (Windows), notarisation (macOS) — `jpackage` accepte les paramètres de signature.
- **Validation TLS laissée active** — ne jamais installer un `TrustManager` permissif.

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Base locale | capability `local-db` (`sqlite-jdbc`) |
| Préférences | `java.util.prefs.Preferences` — registre / plist / fichier. **Non chiffré** |
| **Secrets** | trousseau système par plateforme, ou `KeyStore` |
| Fichiers | `java.nio.file` |
| Backend distant | `java.net.http.HttpClient` (JDK, aucune dépendance) |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C** si une base serveur est atteinte : aucun DDL par un agent sur une base existante.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-javafx`
- **Langage** : Java 21 (**JDK 21 LTS**)
- **Framework UI** : **JavaFX 21.0.12** (ligne LTS-alignée)
- **Plateformes** : Windows, Linux, macOS
- **Build** : Gradle (Kotlin DSL) + plugin `org.openjfx.javafxplugin`
- **Packaging** : `org.beryx.jlink` → runtime image + installeur natif
- **Runtime chez l'utilisateur** : **aucun** si `jpackage` est utilisé (le runtime est embarqué)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/build.gradle.kts`
- **Run dev** : `./gradlew run`
- **Build** : `./gradlew build`
- **Runtime image** : `./gradlew jlink`
- **Installeur natif** : `./gradlew jpackage`
- **Tests** : `./gradlew test`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && ./gradlew build --no-daemon)
test -f workspace/src/{AppName}/src/main/java/module-info.java
test -f workspace/src/{AppName}/build.gradle.kts
```

- **Smoke Timeout** : 420s (résolution Gradle + compilation)

> **`jpackage` ne cross-compile pas** : produire un `.msi` exige Windows, un `.dmg` exige macOS, un `.deb` exige Linux. Prévoir une matrice CI par OS — même contrainte que `desktop/qt-cpp` et `desktop/electron`.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/build.gradle.kts" ]; then

# STEP 0 — Gate JDK, bloquant
java -version 2>&1 | head -1
JAVA_MAJOR=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+).*/\1/')
if [ "${JAVA_MAJOR:-0}" -lt 21 ]; then
  echo "ERROR: arch {AppName} — JDK insuffisant"
  echo "CAUSE: [INFRA_BLOCKED] JDK $JAVA_MAJOR < 21 LTS requis"
  echo "FIX: installer un JDK 21 LTS (Temurin, Zulu, Corretto)"
  exit 3
fi

APP=workspace/src/{AppName}
NS_PATH=$(echo "{AppNamespace}" | tr '.' '/')

# STEP 1 — Arborescence
mkdir -p \
  "$APP/src/main/java/$NS_PATH"/{presentation/{controllers,viewmodels,components},domain/{entities,services},data/{repositories,api},infrastructure} \
  "$APP/src/main/resources/$NS_PATH/views" \
  "$APP/src/main/resources"/{css,i18n} \
  "$APP/src/test/java/$NS_PATH" \
  "$APP/gradle"

# STEP 2 — settings.gradle.kts
cat > "$APP/settings.gradle.kts" <<'EOF'
rootProject.name = "{AppName}"
EOF

# STEP 3 — build.gradle.kts
#   Le plugin org.openjfx.javafxplugin est LOAD-BEARING : c'est lui qui resout
#   les artefacts JavaFX AVEC leur classifier de plateforme (win/linux/mac).
#   Sans lui, le build ne produit un binaire utilisable que pour l'OS courant.
cat > "$APP/build.gradle.kts" <<'EOF'
plugins {
    application
    id("org.openjfx.javafxplugin") version "0.1.0"
    id("org.beryx.jlink") version "3.1.1"
}

group = "{AppNamespace}"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

javafx {
    // Ligne LTS-alignee. NE PAS resoudre en "latest" : Maven Central expose
    // des builds early access (28-ea+6) non detectes comme prereleases.
    version = "21.0.12"
    modules = listOf("javafx.controls", "javafx.fxml")
}

repositories { mavenCentral() }

dependencies {
    implementation("org.slf4j:slf4j-api:2.0.18")
    implementation("ch.qos.logback:logback-classic:1.6.3")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.2")

    testImplementation("org.junit.jupiter:junit-jupiter:5.14.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainModule.set("{AppNamespace}")
    mainClass.set("{AppNamespace}.App")
}

jlink {
    options.set(listOf("--strip-debug", "--compress", "2", "--no-header-files", "--no-man-pages"))
    launcher { name = "{AppName}" }
    jpackage { installerType = if (System.getProperty("os.name").startsWith("Windows")) "msi" else "deb" }
}

tasks.test { useJUnitPlatform() }
EOF

# STEP 4 — module-info.java
#   `opens ... to javafx.fxml` est OBLIGATOIRE : le FXMLLoader instancie les
#   Controllers par REFLEXION. Sans l'ouverture, l'echec survient au RUNTIME
#   (IllegalAccessException), pas a la compilation. Cf. 2.3.
cat > "$APP/src/main/java/module-info.java" <<'EOF'
module {AppNamespace} {
    requires javafx.controls;
    requires javafx.fxml;
    requires org.slf4j;
    requires com.fasterxml.jackson.databind;

    // Sans ces deux lignes, le FXMLLoader echoue au runtime.
    opens {AppNamespace}.presentation.controllers to javafx.fxml;
    exports {AppNamespace};
}
EOF

# STEP 5 — Wrapper Gradle pinne
(cd "$APP" && gradle wrapper --gradle-version 8.14.5 --distribution-type bin)

# STEP 6 — Gate
(cd "$APP" && ./gradlew build --no-daemon)

fi
```

**Contrat post-init** :
- `build.gradle.kts` applique `org.openjfx.javafxplugin` **et** `org.beryx.jlink`
- `javafx.version` vaut `21.0.12` (pas un build `-ea`)
- `module-info.java` existe et **ouvre** le paquet des Controllers vers `javafx.fxml`
- La toolchain Java est fixée à 21
- `./gradlew build` sort 0

---

## 2.3 Notes de construction

### JavaFX n'est plus dans le JDK

Depuis le JDK 11, JavaFX est **découplé** : ce n'est plus un module du JDK mais
une dépendance à part entière (`org.openjfx:javafx-*`). C'est la première
surprise pour qui vient de Java 8, où `javafx.scene` était disponible sans
rien déclarer.

Conséquence : les artefacts JavaFX portent un **classifier de plateforme**
(`win`, `linux`, `mac`, `mac-aarch64`). Le plugin
`org.openjfx.javafxplugin` les résout automatiquement pour l'OS courant — et
c'est pourquoi il est en `plugins[]` du catalog, pas en simple commodité.
**Sans lui, le build produit un artefact qui ne démarre que sur l'OS de
compilation.**

### Piège de résolution : les builds early access

`org.openjfx:javafx-controls` publie sur Maven Central des builds **early
access** :

```
… 25.0.4, 26, 26.0.1, 26.0.2, 27-ea+3, 28-ea+6
```

Une résolution naïve de « la dernière version » retient **`28-ea+6`**. Le
suffixe `-ea` n'est pas reconnu par les filtres de prerelease habituels
(`-alpha`, `-beta`, `-rc`), et le résultat est un JavaFX de développement en
production.

Le filtre retenu pour ce catalog n'accepte qu'un **numéro pur**
(`^\d+(\.\d+){0,2}$`). C'est la même discipline que le filtre strict de
`desktop/wpf.md §2.3` face aux suffixes `-ci` et `-nblumhardt` de NuGet — deux
écosystèmes, même classe de piège.

### Pourquoi JDK 21 et non 25

Adoptium expose **8, 11, 17, 21 et 25** comme LTS ; la 25 est la plus récente,
et JavaFX publie une ligne 25.x correspondante.

Le pin reste sur **21** pour rester cohérent avec
`rules/library-and-stack.md §0`, qui déclare **Java 21 LTS** pour l'ensemble du
catalogue (`backend/kotlin-spring-boot`). Faire diverger ce stack seul créerait
deux runtimes JVM dans le même catalogue sans raison.

**Migration JDK 25** : tâche dédiée, à mener sur **tout le catalogue JVM à la
fois** — pas stack par stack.

### `module-info.java` : l'échec est différé au runtime

Le `FXMLLoader` instancie les Controllers par **réflexion**. Sous JPMS, cela
exige que le paquet soit `opens` vers `javafx.fxml` :

```java
opens {AppNamespace}.presentation.controllers to javafx.fxml;
```

Sans cette ligne, **tout compile normalement** puis l'application lève une
`IllegalAccessException` à l'ouverture du premier écran. C'est le défaut le
plus coûteux à diagnostiquer sur ce stack, parce que rien à la compilation ne
le signale.

Corollaire : chaque nouvelle dépendance doit être déclarée en `requires` dans
`module-info.java`, sinon `jlink` échoue.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Dernière version **stable stricte** de chaque coordonnée (`maven-metadata.xml`, 2026-09-02) | `./gradlew build` / `run` |
| Statut LTS des JDK (API Adoptium) | `jlink` / `jpackage` |
| Cohérence `.md` ↔ `.libs.json` | Chargement FXML réel (JPMS) |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/javafx.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id javafx`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| javafx-base | 21.0.12 | Socle JavaFX (proprietes, collections observables) |
| javafx-graphics | 21.0.12 | Moteur de rendu et scene graph |
| javafx-controls | 21.0.12 | Controles standard (Button, TableView, TreeView) |
| javafx-fxml | 21.0.12 | Vues declaratives FXML + injection du Controller — l'equivalent de XAML pour ce stack |
| slf4j-api | 2.0.18 | Facade de logs |
| logback-classic | 1.6.3 | Implementation avec sink fichier — sur un poste client, c'est le seul journal disponible |
| jackson-databind | 2.22.2 | JSON (configuration, echanges avec le backend separe optionnel) |
| junit-jupiter | 5.14.2 | Tests unitaires (ligne 5, alignee sur qa/kotlin-junit) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| control-library | controlsfx | 11.2.4 | controle.*avance, notification, controlsfx, composant.*riche |
| modern-theme | atlantafx-base | 2.1.0 | theme, apparence.*moderne, dark.*mode, atlantafx |
| icons | ikonli-javafx | 12.4.0 | icone, ikonli, pictogramme |
| validation | validatorfx | 1.0.0 | validation, formulaire, regle.*saisie |
| form-builder | formsfx-core | 11.6.0 | formulaire.*genere, formsfx |
| dependency-injection | guice | 7.0.0 | injection.*dependance, \bdi\b, guice |
| local-db | sqlite-jdbc | 3.53.4.0 | base.*locale, sqlite, hors.*ligne |
| webview | javafx-web | 21.0.12 | webview, contenu.*web |
| media | javafx-media | 21.0.12 | audio, video, lecture.*media |
| ui-tests | testfx-junit5 | 4.0.18 | test.*ui, testfx, test.*bout.*en.*bout |
| unit-tests | mockito-core | 5.23.0 | mock, mockito, tests.*unitaires |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| application | built-in-gradle | Plugin Gradle application — genere les scripts de lancement |
| org.openjfx.javafxplugin | 0.1.0 | Resout les artefacts JavaFX AVEC leur classifier de plateforme (win/linux/mac). Sans lui, le build ne produit un binaire utilisable que pour l'OS de compilation |
| org.beryx.jlink | 3.1.1 | Produit un runtime image jlink + installeur natif via jpackage — c'est ce qui evite d'exiger un JDK installe chez l'utilisateur |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Application | `App.java` → `class App extends Application` | `App.java` |
| Controller | `{Name}Controller.java` | `CustomerListController.java` |
| ViewModel | `{Name}ViewModel.java` | `CustomerListViewModel.java` |
| Vue FXML | `{name}-view.fxml` (kebab-case) | `customer-list-view.fxml` |
| Service | `{Name}Service.java` + `{Name}ServiceImpl.java` | `InvoiceService.java` |
| Entité | `{Name}.java` | `Customer.java` |
| Repository | `{Name}Repository.java` | `CustomerRepository.java` |
| Module Guice | `{Name}Module.java` | `DataModule.java` |
| Test | `{Name}ServiceTest.java` | `InvoiceServiceTest.java` |
| Propriété observable | `{name}Property()` + `get{Name}()` / `set{Name}()` | `titleProperty()` |
| `fx:id` | `{role}{Type}` | `saveButton`, `customerTable` |

**Conventions** : Java standard (`PascalCase` pour les types, `camelCase` pour les membres). Un FXML et son Controller partagent le préfixe : `customer-list-view.fxml` ↔ `CustomerListController`.

**INTERDITS** :
- `fx:id` par défaut (`button1`, `tableView2`)
- Controller sans ViewModel correspondant pour un écran non trivial
- Suffixe `Impl` sur une classe sans interface
- `Manager`, `Helper`, `Util`

---

## 3. Backend consomme (optionnel)

Ce stack fonctionne **soit** en autonome (capability `local-db`), **soit** en
client d'un backend déclaré en `## Active Tech Specs`.

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | authentification |
| `GET /api/me` | utilisateur courant |

`java.net.http.HttpClient` (JDK) couvre le besoin sans dépendance — c'est
pourquoi aucun client HTTP ne figure au catalog. Base URL lue depuis un fichier
de configuration ou `Preferences`, jamais en constante.

**CORS : sans objet** — l'application n'est pas un navigateur.

> **Affinité `backend/kotlin-spring-boot`** : même JVM, mêmes DTOs Jackson possibles, même JDK 21 LTS.

---

## 4. Versioning et livraison

- **`version`** du `build.gradle.kts` — source unique
- **`jpackage`** produit un installeur **avec runtime embarqué** : l'utilisateur n'a **pas** besoin d'un JDK. C'est ce qui rend ce stack déployable en parc.
- **Matrice CI par OS** — `jpackage` ne cross-compile pas (§2.2)
- **Signature** : Authenticode (Windows), notarisation (macOS)
- **`apiVersion`** en configuration si un backend est consommé

---

## 5. Interdits projet (javafx)

**Architecture** :
- Règle métier dans un Controller
- ViewModel important `javafx.scene.control` — casse la testabilité headless
- `setText(...)` appelé manuellement là où un `bind()` conviendrait
- `ArrayList` liée à un `TableView` — utiliser `ObservableList`
- Travail long sur le JavaFX Application Thread — utiliser `Task<T>`
- Modification d'un nœud depuis un thread secondaire — `Platform.runLater`
- `.fxml` édité à la main
- Dépendance ajoutée sans `requires` dans `module-info.java` — `jlink` échoue
- Paquet de Controllers non `opens` vers `javafx.fxml` — échec **au runtime** (§2.3)
- Chaîne visible en dur — utiliser un `ResourceBundle`

**Code quality** :
- Méthode de plus de 30 lignes
- `catch (Exception e) {}` silencieux
- `System.out.println` — utiliser SLF4J
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Secret dans le JAR (il se décompile)
- SQL concaténé — utiliser `PreparedStatement`
- `TrustManager` permissif
- Secret dans `Preferences`
- Installeur non signé

**Build / packaging** :
- Committer `build/`, `.gradle/`, `*.iml`
- **Résoudre `javafx.version` en « latest »** — builds `-ea` (§2.3)
- Plugin `org.openjfx.javafxplugin` absent — artefact mono-plateforme (§2.3)
- `module-info.java` supprimé pour « faire compiler » — `jlink` devient impossible
- Prétendre livrer les trois OS depuis un seul agent CI
- Wrapper Gradle non pinné

---

## 6. Persistance — voir §1.5

`sqlite-jdbc` via la capability `local-db`. Phase B (DB) d'`arch` : **applicable** si une base serveur est déclarée, **lecture seule** sur une base existante.

---

## 7. Temps reel

- **WebSocket** : `java.net.http.WebSocket` (JDK 11+), aucune dépendance
- **SSE** : `HttpClient` avec `BodyHandlers.ofLines()`
- **Polling** : `ScheduledService<T>` de JavaFX — conçu pour cela, callbacks sur le bon thread
- **Notifications système** : `java.awt.SystemTray` (module `java.desktop`) — à déclarer en `requires`

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Équipes Java** livrant du desktop sans changer de langage — et partageant DTOs et validation avec un `backend/kotlin-spring-boot`
- **Portabilité réelle avec data binding** — le seul du catalogue à combiner les deux
- **Applications métier riches** — `TableView`, formulaires, graphiques
- **Déploiement en parc** — `jpackage` produit un installeur sans prérequis

**NE PAS choisir si** :
- ❌ **Le rendu doit être natif** — JavaFX dessine ses propres contrôles et les stylise en CSS. Le look est cohérent entre OS, mais n'est celui d'aucun. C'est le reproche principal fait au stack, et la capability `modern-theme` (AtlantaFX) l'atténue sans le supprimer.
- ❌ **Démarrage à froid critique** — la JVM démarre plus lentement qu'un binaire natif
- ❌ **Cible Windows uniquement** → `desktop/wpf` ou `desktop/delphi-vcl` donnent un meilleur rendu pour moins d'effort
- ❌ **Équipe web** → `desktop/electron` ; **C++** → `desktop/qt-cpp` ; **Python** → `desktop/pyside`
- ❌ **Écosystème de composants UI très large attendu** — l'offre JavaFX est correcte (ControlsFX, Ikonli) mais nettement plus étroite que celle de WPF ou du web
- ❌ **Aucune compétence JVM** — JPMS (`module-info`) ajoute une difficulté réelle au-delà du langage (§2.3)

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-javafx` autonome (capability `local-db`) | 🟡 experimental | jamais validé end-to-end |
| `desktop-javafx` + backend `kotlin-spring-boot` + `auth-local` + `postgres` | 🟡 experimental | combo à plus forte affinité (même JVM, même JDK 21 LTS) |
| `desktop-javafx` + backend `python-fastapi` + `auth-local` | 🟡 experimental | jamais validé end-to-end |
| `desktop-javafx` + `qa/kotlin-junit` | 🟡 experimental | JUnit 5 partagé ; `testfx` pour les tests d'UI |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate JDK bloquant** : `java -version` ≥ **21**. Sinon STOP `[INFRA_BLOCKED]`.
2. **Détecter** `desktop/javafx.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
3. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** (`preflight.validate_stack_combo`)
4. **Le plugin `org.openjfx.javafxplugin` est obligatoire** (STEP 3) — sans lui, les artefacts JavaFX sont résolus sans classifier de plateforme et le binaire ne démarre que sur l'OS de compilation (§2.3)
5. **Ne JAMAIS résoudre `javafx.version` en « latest »** — Maven Central expose des builds `-ea` que les filtres usuels ne détectent pas. Pin `21.0.12` (§2.3)
6. **`module-info.java` avec `opens ... to javafx.fxml`** (STEP 4) : sans cette ligne, tout compile et l'application échoue **au runtime** à l'ouverture du premier écran. C'est le défaut le plus coûteux du stack.
7. **Chaque dépendance ajoutée** doit recevoir son `requires` dans `module-info.java`, sinon `jlink` échoue
8. **Injecter** la base URL et l'`apiVersion` en configuration, jamais en constante
9. **CORS : sans objet** — ne pas configurer d'allowlist côté backend pour ce stack
10. **`## Active UI Specs`** : aucun design system web n'est compatible. JavaFX se stylise en **CSS JavaFX** (un dialecte, pas du CSS web). Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`. L'équivalent est la capability `modern-theme`.
11. **Phase B (DB)** : applicable si base serveur, **lecture seule** sur base existante
12. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-javafx.md` documentant JDK 21 LTS + JavaFX 21 LTS, le choix FXML + MVVM, le packaging `jpackage` et **la divergence assumée avec le JDK 25** (§2.3)

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome).

- `dev-backend` **ne touche pas** au projet JavaFX — il code le backend séparé s'il est déclaré
- `dev-frontend` matérialise **tout** le projet JavaFX

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `src/main/java/**/presentation/**` | `dev-frontend` |
| `src/main/java/**/domain/**` | `dev-frontend` (c'est le métier du client) |
| `src/main/java/**/data/**` | `dev-frontend` |
| `src/main/java/**/infrastructure/**` | `arch` (create) + `dev-frontend` |
| `src/main/resources/**/views/*.fxml` | `dev-frontend` — **via Scene Builder** |
| `src/main/resources/css/**`, `i18n/**` | `dev-frontend` |
| `src/main/java/module-info.java` | `arch` (create) + `dev-frontend` (`requires` / `opens` à chaque ajout) |
| `build.gradle.kts`, `settings.gradle.kts`, `gradle/**` | `arch` exclusif |
| `src/test/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

JAVA_MAJOR=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+).*/\1/')
[ "${JAVA_MAJOR:-0}" -ge 21 ] || { echo "SKIP: JDK < 21"; exit 3; }

test -f build.gradle.kts
test -f src/main/java/module-info.java

# Le plugin de plateforme est load-bearing (cf. 2.3)
grep -q "org.openjfx.javafxplugin" build.gradle.kts

# Version JavaFX pinnee sur la ligne LTS, PAS un build early access (cf. 2.3)
grep -q 'version = "21.0.12"' build.gradle.kts
! grep -qE '"[0-9]+-ea' build.gradle.kts

# Sans cette ouverture, le FXMLLoader echoue au RUNTIME (cf. 2.3)
grep -q "opens .* to javafx.fxml" src/main/java/module-info.java

./gradlew build --no-daemon
./gradlew test --no-daemon

echo "smoke OK"
```
