# Tech FEAT: pyside (desktop)

> §2.4 (Librairies) regeneree depuis `pyside.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id pyside`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque paquet résolu contre PyPI avec sa contrainte `requires_python`. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `pytest` ni `pyinstaller` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-pyside
Scope: **client desktop multiplateforme** — application **Python 3.12 + PySide6 (Qt 6.11)** dans UN seul projet `{AppName}/`. Cible Windows + Linux + macOS. Pas de séparation `{BackendName}` / `{LibName}`.

> **PySide6, pas PyQt6 — et c'est un choix de licence.** PySide6 est le binding **officiel** de Qt, sous **LGPL-3.0**. PyQt6 (Riverbank) est en **GPL-3.0 ou commerciale**. Pour une application à code fermé, PySide6 s'utilise en liaison dynamique sans licence commerciale ; PyQt6 imposerait soit d'ouvrir le code, soit d'acheter. Voir §2.3.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application Qt en Python** :

- **PySide6 6.11** — le même Qt que `desktop/qt-cpp`, piloté depuis Python
- **Qt Widgets** — contrôles desktop classiques
- **Signaux / slots** — décorateur `@Slot`, connexions vérifiées à l'exécution
- **Model/View** (`QAbstractTableModel`) — pour tout affichage de volume
- **structlog** — logs structurés
- **PyInstaller** (capability `packaging`) — exécutable autonome, **indispensable pour livrer**

Architecture cible :

```
{AppName}/
├── pyproject.toml
└── src/{AppName}/
    ├── __main__.py                ── point d'entree (QApplication)
    ├── ui/
    │   ├── main_window.py         ── QMainWindow
    │   ├── widgets/
    │   └── models/                ── QAbstractTableModel
    ├── domain/
    │   ├── entities.py            ── dataclasses / modeles Pydantic
    │   └── services.py            ── regles metier, SANS import Qt
    ├── data/
    │   ├── repositories.py
    │   └── api_client.py          ── httpx
    └── infrastructure/
        ├── logging.py
        └── settings.py
```

**Différence vs `desktop/qt-cpp`** : le même toolkit, sans C++. On échange la
performance brute et la compilation AOT contre une productivité nettement
supérieure et l'accès à l'écosystème Python — **numpy, pandas, scikit-learn
sans passerelle**. C'est ce qui définit le cas d'usage visé (§8).

**Différence vs `desktop/electron`** : rendu Qt natif et empreinte plus faible,
mais binaire livré comparable (60–150 Mo une fois PyInstaller passé) et
démarrage lent.

---

## 1.2 Couches

- **UI** (`ui/`) : fenêtres, widgets, modèles Model/View. Câblage seulement.
- **Models** (`ui/models/`) : `QAbstractTableModel` — c'est l'architecture Model/View de Qt. Un `QTableWidget` rempli par boucle s'effondre en volume.
- **Services** (`domain/services.py`) : les règles métier. **Aucun import `PySide6`** — c'est ce qui les rend testables sans `QApplication`.
- **Entities** (`domain/entities.py`) : `dataclass` ou modèles Pydantic (capability `validation`).
- **Repositories / Api** (`data/`) : persistance et appels distants.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path (sous `src/{AppName}/`) |
|---|---|
| Point d'entrée | `__main__.py` |
| Fenêtre principale | `ui/main_window.py` → `class MainWindow(QMainWindow)` |
| Widget | `ui/widgets/{name}_widget.py` |
| Modèle Model/View | `ui/models/{name}_model.py` |
| Service métier | `domain/services.py` |
| Entité | `domain/entities.py` |
| Repository | `data/repositories.py` |
| Client API | `data/api_client.py` |
| Configuration | `infrastructure/settings.py` |
| Logs | `infrastructure/logging.py` |
| Test | `tests/test_{sujet}.py` |
| Manifeste projet | `pyproject.toml` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune règle métier dans un slot.** Un `@Slot` appelle un service, rien de plus.
- **Un service n'importe pas `PySide6`** — sinon il exige un `QApplication` pour être testé, et la CI headless échoue.
- **Model/View pour tout volume** — `QAbstractTableModel`, pas un `QTableWidget` rempli par boucle.
- **Aucun travail long dans le thread UI** : `QThread` + worker `QObject`, ou la capability `asyncio` (`qasync`). Un `time.sleep` ou un appel HTTP synchrone dans un slot **fige la fenêtre**.
- **Un widget n'est jamais touché depuis un thread secondaire** — Qt l'interdit. Passer par un signal.
- **Références Python conservées** sur les objets Qt : un widget dont la seule référence Python disparaît est **collecté par le GC**, et l'objet C++ sous-jacent détruit. Le symptôme — un widget qui s'efface sans raison — est déroutant, et c'est le piège n°1 de PySide (§2.3).
- **`@Slot()` explicite** sur les slots connectés : sans le décorateur, PySide crée un wrapper à chaque connexion, ce qui coûte en mémoire et masque les erreurs de signature.
- **Typage annoté + `mypy`** — PySide6 fournit des stubs, le typage est donc réellement exploitable.

**Sécurité** :
- **Aucun secret dans le code** — un exécutable PyInstaller **contient les `.pyc`**, qui se décompilent (`uncompyle6`, `pycdc`). Ce n'est pas de l'obfuscation.
- **Requêtes paramétrées** (SQLAlchemy ou `sqlite3` avec `?`), jamais de f-string SQL.
- **Secrets via le trousseau du système** (`keyring`) — **non catalogué**, à instruire si nécessaire. Jamais `QSettings` ni un fichier.
- **Validation TLS laissée active** — ne jamais passer `verify=False` à `httpx`.
- **Exécutable signé** sur Windows et macOS — un binaire PyInstaller non signé est très fréquemment bloqué par les antivirus, davantage qu'un binaire natif.
- **Pas de `subprocess` sur une commande construite depuis une saisie utilisateur.**

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Base locale | capability `local-db` (SQLAlchemy + SQLite) |
| Préférences | `QSettings` — registre / plist / ini. **Non chiffré** |
| **Secrets** | trousseau système (`keyring`, **non catalogué**) |
| Fichiers | `pathlib` + `QStandardPaths` pour les emplacements conventionnels |
| Backend distant | capability `http-client` (`httpx`) |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C** si une base serveur est atteinte : aucun DDL par un agent sur une base existante.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-pyside`
- **Langage** : Python **3.12**
- **Framework UI** : **PySide6 6.11.2** (Qt 6.11), module Widgets
- **Licence** : **LGPL-3.0** (binding officiel Qt)
- **Plateformes** : Windows, Linux, macOS
- **Package manager** : `uv` (aligné sur les autres stacks Python du catalogue)
- **Packaging** : PyInstaller (capability `packaging`)
- **Runtime chez l'utilisateur** : **aucun** après PyInstaller (l'interpréteur est embarqué)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/pyproject.toml`
- **Run dev** : `uv run python -m {AppName}`
- **Tests** : `uv run pytest`
- **Lint / format** : `uv run ruff check .` / `uv run ruff format .`
- **Typage** : `uv run mypy src`
- **Exécutable** : `uv run pyinstaller --noconfirm --windowed --name {AppName} src/{AppName}/__main__.py`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && uv sync && uv run python -c "import PySide6; print(PySide6.__version__)")
test -f workspace/src/{AppName}/src/{AppName}/__main__.py
test -f workspace/src/{AppName}/pyproject.toml
```

- **Smoke Timeout** : 300s (`uv sync` télécharge PySide6, ~150 Mo)

> **Tests headless en CI** : sur Linux, `pytest-qt` exige un serveur d'affichage. Utiliser `xvfb-run`, ou `QT_QPA_PLATFORM=offscreen` — sans cela, la suite échoue au premier `QApplication` avec une erreur de plugin de plateforme.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/pyproject.toml" ]; then
  APP=workspace/src/{AppName}
  mkdir -p "$APP" && cd "$APP"

  # STEP 0 — Gate runtime : PySide6 6.11 exige Python >= 3.10, < 3.15
  uv --version
  python -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)' || {
    echo "ERROR: arch {AppName} — version Python incompatible"
    echo "CAUSE: [INFRA_BLOCKED] PySide6 6.11 declare requires_python >=3.10,<3.15"
    echo "FIX: utiliser Python 3.12"
    exit 3
  }

  # STEP 1 — Projet uv + runtime pinne
  uv init --name {AppName} --python 3.12 --lib --no-workspace

  # STEP 2 — Dependances CORE (cf. 2.4.a)
  #   shiboken6 DOIT etre a la meme version que PySide6, sinon l'import
  #   echoue au demarrage (cf. 2.3).
  uv add \
    PySide6==6.11.2 \
    shiboken6==6.11.2 \
    structlog==26.1.0

  # STEP 3 — Outillage de developpement
  uv add --dev \
    ruff==0.16.5 \
    mypy==2.3.1 \
    pytest==9.1.1 \
    pytest-qt==4.5.0

  # STEP 4 — Arborescence
  mkdir -p \
    src/{AppName}/ui/{widgets,models} \
    src/{AppName}/domain \
    src/{AppName}/data \
    src/{AppName}/infrastructure \
    tests
  touch src/{AppName}/ui/__init__.py \
        src/{AppName}/domain/__init__.py \
        src/{AppName}/data/__init__.py \
        src/{AppName}/infrastructure/__init__.py

  # STEP 5 — Point d'entree
  cat > "src/{AppName}/__main__.py" <<'PY'
"""Point d'entree de l'application."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from {AppName}.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("{AppName}")

    # La reference est conservee volontairement : un widget dont la derniere
    # reference Python disparait est collecte par le GC, et l'objet C++
    # sous-jacent detruit avec lui (cf. 2.3).
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
PY

  cat > "src/{AppName}/ui/main_window.py" <<'PY'
"""Fenetre principale."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("{AppName}")
        self.resize(1000, 700)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("{AppName}", central))
        self.setCentralWidget(central)
PY

  # STEP 6 — pytest.ini : QT_QPA_PLATFORM=offscreen pour la CI headless
  cat > pytest.ini <<'INI'
[pytest]
testpaths = tests
python_files = test_*.py
addopts = --strict-markers
env = QT_QPA_PLATFORM=offscreen
INI

  # STEP 7 — Gate
  uv run python -c "import PySide6; print('PySide6', PySide6.__version__)"
  uv run ruff check .
fi
```

**Contrat post-init** :
- `pyproject.toml` pin `PySide6` **et** `shiboken6` à la **même** version
- `src/{AppName}/__main__.py` crée un `QApplication` et garde une référence à la fenêtre
- `pytest.ini` déclare `QT_QPA_PLATFORM=offscreen`
- `uv run ruff check .` sort 0

---

## 2.3 Notes de construction

### La licence est la raison du choix PySide6

| Binding | Éditeur | Licence |
|---|---|---|
| **PySide6** | **The Qt Company** (officiel) | **LGPL-3.0** |
| PyQt6 | Riverbank Computing | **GPL-3.0 ou commerciale** |

Les deux exposent le même Qt avec des API quasi identiques. La différence est
juridique, et elle est décisive : une application **à code fermé** peut utiliser
PySide6 en liaison dynamique **sans licence commerciale**, alors que PyQt6
imposerait soit d'ouvrir le code (GPL), soit un achat.

C'est aussi ce qui distingue ce stack de `desktop/qt-cpp` : là, la question de
la liaison **statique** se pose (et fait basculer vers le commercial). Ici,
PySide6 est chargé dynamiquement par construction — la contrainte LGPL est
satisfaite d'office.

> Les tutoriels PyQt et PySide sont largement interchangeables. Le catalog
> déclare **PySide6 uniquement** : introduire PyQt6 « parce qu'un exemple
> l'utilisait » ferait basculer le projet sous GPL. C'est en §5.

### `shiboken6` doit suivre `PySide6` exactement

`shiboken6` est la couche de binding C++ ↔ Python dont dépend PySide6. **Les
deux versions doivent être identiques** (`6.11.2` / `6.11.2`) : un écart fait
échouer l'import au démarrage, avec un message sur un symbole introuvable qui
ne mentionne pas la cause.

C'est pourquoi `shiboken6` est déclaré **explicitement en CORE** plutôt que
laissé en dépendance transitive : le pin doit être visible et bumpé en bloc.

### Le piège n°1 : le GC Python détruit les objets Qt

PySide expose des objets **C++** derrière des références **Python**. Quand la
dernière référence Python disparaît, le GC collecte le wrapper **et détruit
l'objet C++**.

```python
def build_ui(self) -> None:
    dialog = MyDialog()      # référence LOCALE
    dialog.show()            # la fonction retourne -> dialog collecté
                             # -> la fenêtre disparaît immédiatement
```

La correction est de conserver une référence : attribut d'instance
(`self._dialog = MyDialog()`), ou parent Qt (`MyDialog(parent=self)`, qui
transfère la propriété au parent côté C++).

Le symptôme — un widget qui s'efface sans raison, parfois par intermittence —
n'évoque rien de la cause. C'est le défaut le plus coûteux à diagnostiquer sur
ce stack, et il n'existe **pas** en C++ (`desktop/qt-cpp`), où la parenté Qt
suffit.

### Contrainte de version Python

`PySide6` 6.11.2 déclare `requires_python: >=3.10,<3.15` — une borne
**supérieure**, ce qui est inhabituel et signifie qu'une version de Python trop
récente est refusée à l'installation. `pyinstaller` 6.22.2 déclare de son côté
`<3.16`.

Le pin **3.12** est confortablement dans les deux fenêtres, et cohérent avec
`backend/python-fastapi` et `backend/django`.

### PyInstaller n'est pas optionnel pour livrer

L'utilisateur final n'a pas d'interpréteur Python. Sans la capability
`packaging`, il n'y a **rien à distribuer**. Compter 60 à 150 Mo par binaire,
Qt inclus — comparable à Electron, ce qui relativise l'avantage d'empreinte du
stack **à la livraison** (il reste réel à l'exécution).

Deux effets de bord à connaître : les binaires PyInstaller sont fréquemment
signalés par les antivirus (d'où l'exigence de signature, §1.4), et
`--windowed` est nécessaire sur Windows pour éviter l'ouverture d'une console.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (PyPI, 2026-09-02) | `uv sync`, lancement de l'app |
| `requires_python` de chaque paquet (bornes hautes incluses) | `pytest` avec `pytest-qt` |
| Alignement `PySide6` / `shiboken6` | `pyinstaller` et signature |
| Cohérence `.md` ↔ `.libs.json` | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/pyside.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id pyside`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| PySide6 | 6.11.2 | Binding Qt OFFICIEL sous LGPL — c'est le coeur du stack, et la raison du choix face a PyQt6 (GPL/commerciale) |
| shiboken6 | 6.11.2 | Couche de binding C++ <-> Python dont depend PySide6. Sa version DOIT etre identique a celle de PySide6, sinon l'import echoue au demarrage |
| structlog | 26.1.0 | Logs structures — meme choix que les stacks Python du catalogue |
| ruff | 0.16.5 | Lint + format (dev) |
| mypy | 2.3.1 | Typage statique (dev) — PySide6 expose des stubs, le typage est donc reellement exploitable |
| pytest | 9.1.1 | Runner de tests (dev) |
| pytest-qt | 4.5.0 | Fixture qtbot : pilote les widgets et attend les signaux. Sans elle, tester un widget Qt exige de gerer la boucle d'evenements a la main |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| icons | qtawesome | 1.4.2 | icone, pictogramme, qtawesome |
| charts | pyqtgraph | 0.14.0 | chart, graphique, courbe, temps.*reel, visualisation.*donnees |
| asyncio | qasync | 0.28.0 | asyncio, async, coroutine, appel.*asynchrone |
| local-db | SQLAlchemy | 2.0.52 | base.*locale, sqlite, \borm\b, hors.*ligne |
| http-client | httpx | 0.28.1 | appel.*api, backend, http, rest |
| validation | pydantic | 2.13.5 | validation, schema, parsing.*reponse |
| packaging | pyinstaller | 6.22.2 | executable, packaging, livraison, installeur, binaire |
| coverage | pytest-cov | 7.1.0 | coverage, couverture.*tests |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Point d'entrée | `__main__.py` → `def main() -> int` | — |
| Fenêtre | `ui/main_window.py` → `class MainWindow(QMainWindow)` | `main_window.py` |
| Widget | `ui/widgets/{name}_widget.py` → `class {Name}Widget` | `customer_form_widget.py` |
| Modèle Model/View | `ui/models/{name}_model.py` → `class {Name}Model` | `customer_table_model.py` |
| Service | `domain/services.py` → `class {Name}Service` | `InvoiceService` |
| Entité | `domain/entities.py` → `@dataclass class {Name}` | `Customer` |
| Repository | `data/repositories.py` → `class {Name}Repository` | `CustomerRepository` |
| Slot | `@Slot()` sur `_on_{objet}_{evenement}` | `_on_save_clicked` |
| Signal | `Signal(...)` nommé au passé | `customer_saved = Signal(str)` |
| Test | `tests/test_{sujet}.py` | `tests/test_invoice_service.py` |

**Conventions** : PEP 8 — modules et fonctions en `snake_case`, classes en `PascalCase`, membres privés préfixés `_`. Les signaux sont au passé (un signal rapporte un fait accompli), les slots à l'impératif.

**INTERDITS** :
- Nom de module en `PascalCase` (`MainWindow.py`)
- Slot connecté sans décorateur `@Slot()` (§1.4)
- Signal nommé à l'impératif (`save_customer`) — c'est un slot
- `Manager`, `Helper`, `Utils` en nom de module fourre-tout

---

## 3. Backend consomme (optionnel)

Ce stack fonctionne **soit** en autonome (capability `local-db`), **soit** en
client d'un backend déclaré en `## Active Tech Specs`.

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | authentification |
| `GET /api/me` | utilisateur courant |

Capability `http-client` (`httpx`). En mode asynchrone, **la capability
`asyncio` (`qasync`) est obligatoire** : les boucles d'événements Qt et asyncio
ne cohabitent pas nativement.

Base URL lue depuis `QSettings` ou un fichier de configuration, jamais en
constante. **CORS : sans objet** — l'application n'est pas un navigateur.

> **Affinité `backend/python-fastapi` / `backend/django`** : même langage, mêmes modèles Pydantic partageables entre le client et le serveur.

---

## 4. Versioning et livraison

- **`version`** du `pyproject.toml` — source unique
- **PyInstaller obligatoire** pour distribuer (§2.3)
- **Signature** : Authenticode (Windows), notarisation (macOS) — d'autant plus nécessaire que les binaires PyInstaller sont fréquemment signalés par les antivirus
- **Matrice CI par OS** — PyInstaller ne cross-compile pas
- **`apiVersion`** en configuration si un backend est consommé

---

## 5. Interdits projet (pyside)

**Architecture** :
- Règle métier dans un slot
- Service important `PySide6` — casse la testabilité headless
- **Widget créé sans référence conservée** (§2.3) — il disparaît au passage du GC
- `QTableWidget` rempli par boucle pour un volume important — utiliser Model/View
- Appel HTTP synchrone ou `time.sleep` dans un slot — fenêtre figée
- Modification d'un widget depuis un thread secondaire — passer par un signal
- Slot connecté sans `@Slot()`
- `asyncio` utilisé sans `qasync` (capability `asyncio`) — les deux boucles ne cohabitent pas
- **`PyQt6` introduit dans le projet** — bascule la licence sous GPL (§2.3)

**Code quality** :
- `from PySide6.QtWidgets import *`
- Fonction de plus de 30 lignes
- `except:` nu ou `except Exception: pass`
- `print()` — utiliser `structlog`
- Annotations de type absentes sur les signatures publiques
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Secret dans le code (un binaire PyInstaller contient des `.pyc` décompilables)
- SQL en f-string — utiliser des paramètres
- `verify=False` sur `httpx`
- Secret dans `QSettings`
- `subprocess` sur une commande construite depuis une saisie
- Exécutable non signé

**Build / packaging** :
- `PySide6` et `shiboken6` à des versions différentes (§2.3)
- Committer `.venv/`, `__pycache__/`, `build/`, `dist/`, `*.spec` généré
- `uv.lock` absent du dépôt (une **application** verrouille ses versions)
- Prétendre livrer les trois OS depuis un seul agent CI
- Tests CI sans `QT_QPA_PLATFORM=offscreen` ni `xvfb` (§2.2)

---

## 6. Persistance — voir §1.5

SQLAlchemy + SQLite via la capability `local-db`. Phase B (DB) d'`arch` : **applicable** si une base serveur est déclarée, **lecture seule** sur une base existante.

---

## 7. Temps reel

- **WebSocket** : `websockets` ou `httpx-ws` — **non catalogués**, à instruire ; exigent la capability `asyncio`
- **SSE** : `httpx` en streaming + `qasync`
- **Polling** : `QTimer` — le plus simple, et suffisant dans la plupart des cas
- **Notifications système** : `QSystemTrayIcon.showMessage()` — inclus dans PySide6

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Outils internes et métiers techniques** — c'est son terrain naturel
- **Data / IA / instrumentation** — accès direct à numpy, pandas, scikit-learn, sans passerelle vers un autre langage. Aucun autre stack `desktop/` ne l'offre.
- **Visualisation temps réel** — la capability `charts` (`pyqtgraph`) est conçue pour des flux qui défilent, là où matplotlib décroche
- **Équipes Python** livrant du desktop sans changer de langage
- **Portabilité** avec un toolkit Qt natif, sans écrire de C++

**NE PAS choisir si** :
- ❌ **Application grand public** — démarrage lent (interpréteur + Qt), binaire de 60–150 Mo, et les binaires PyInstaller sont fréquemment signalés par les antivirus. C'est le critère de rejet principal, et il est explicitement le point faible du stack.
- ❌ **Performance UI critique** — le pont Python↔C++ a un coût sur chaque appel ; `desktop/qt-cpp` livre le même Qt sans cette couche
- ❌ **Protection du code source attendue** — les `.pyc` embarqués se décompilent. Ce n'est pas de l'obfuscation.
- ❌ **Démarrage à froid contraint**
- ❌ **Cible Windows uniquement** → `desktop/wpf` ou `desktop/delphi-vcl` donnent un meilleur rendu et un démarrage instantané
- ❌ **Équipe .NET / Java / web / C++** → préférer le stack de leur langage
- ❌ **Contrainte GPL inacceptable ET tentation PyQt** — rester sur PySide6 (§2.3)

> **Alternative à considérer** : si la performance devient le facteur limitant, `desktop/qt-cpp` expose **le même Qt** en C++. Le portage de l'UI est direct (mêmes classes, mêmes signaux) ; c'est la logique métier qu'il faut réécrire.

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-pyside` autonome (capability `local-db`) | 🟡 experimental | jamais validé end-to-end |
| `desktop-pyside` + backend `python-fastapi` + `auth-local` | 🟡 experimental | combo à plus forte affinité (même langage, modèles Pydantic partageables) |
| `desktop-pyside` + backend `django` + `auth-local` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `desktop-pyside` + `qa/python-pytest` | 🟡 experimental | `pytest-qt` requis (fixture `qtbot`), cf. §2.2 pour la CI headless |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate runtime bloquant** : Python dans `[3.10, 3.15)` — `PySide6` 6.11 déclare une borne **supérieure**, ce qui est inhabituel (§2.3). Pin **3.12**.
2. **Détecter** `desktop/pyside.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
3. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** (`preflight.validate_stack_combo`)
4. **`PySide6` et `shiboken6` doivent être pinnés à la MÊME version** (§2.3) — un écart fait échouer l'import au démarrage avec un message qui ne mentionne pas la cause
5. **Ne JAMAIS introduire `PyQt6`** — bascule le projet sous GPL (§2.3). Si un exemple ou une US le mentionne, remonter au Tech Lead comme arbitrage de licence.
6. **`QT_QPA_PLATFORM=offscreen` dans `pytest.ini`** (STEP 6) — sans quoi la suite échoue en CI headless au premier `QApplication`
7. **Injecter** la base URL et l'`apiVersion` en configuration ou `QSettings`, jamais en constante
8. **CORS : sans objet** — ne pas configurer d'allowlist côté backend pour ce stack
9. **`## Active UI Specs`** : aucun design system web n'est compatible. Qt Widgets **est** l'UI. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`
10. **Phase B (DB)** : applicable si base serveur, **lecture seule** sur base existante
11. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-pyside.md` documentant Python 3.12 + PySide6 6.11, **le choix PySide6 plutôt que PyQt6 et sa raison de licence**, et le mode de packaging retenu (PyInstaller)

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome).

- `dev-backend` **ne touche pas** au projet PySide — il code le backend séparé s'il est déclaré
- `dev-frontend` matérialise **tout** le projet PySide

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `src/{AppName}/ui/**` | `dev-frontend` |
| `src/{AppName}/domain/**` | `dev-frontend` (c'est le métier du client) |
| `src/{AppName}/data/**` | `dev-frontend` |
| `src/{AppName}/infrastructure/**` | `arch` (create) + `dev-frontend` |
| `src/{AppName}/__main__.py` | `arch` (create) + `dev-frontend` |
| `pyproject.toml` | `arch` (create) + `dev-frontend` (deps on-demand) |
| `pytest.ini` | `arch` exclusif |
| `tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

python -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)'

uv sync

test -f pyproject.toml
test -f src/{AppName}/__main__.py
test -f src/{AppName}/ui/main_window.py
test -f pytest.ini

# PySide6 et shiboken6 a la MEME version (cf. 2.3)
uv run python - <<'PY'
import PySide6, shiboken6, sys
if PySide6.__version__ != shiboken6.__version__:
    print(f"FAIL: PySide6 {PySide6.__version__} != shiboken6 {shiboken6.__version__}")
    sys.exit(1)
print("PySide6/shiboken6 alignes:", PySide6.__version__)
PY

# PyQt6 ne doit PAS etre present (licence GPL, cf. 2.3)
! uv run python -c "import PyQt6" 2>/dev/null

# CI headless (cf. 2.2)
grep -q "QT_QPA_PLATFORM=offscreen" pytest.ini

uv run ruff check .
uv run mypy src
QT_QPA_PLATFORM=offscreen uv run pytest

echo "smoke OK"
```
