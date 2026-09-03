# Tech FEAT: winforms (desktop)

> §2.4 (Librairies) regeneree depuis `winforms.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id winforms`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque paquet résolu contre NuGet avec le filtre de stabilité strict de `desktop/wpf.md §2.3`. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `dotnet build` n'a tourné en CI (WinForms exige Windows). Non supporté commercialement en l'état.
Tech FEAT ID: tech-winforms
Scope: **client desktop Windows** — application **Windows Forms sur .NET 10** dans UN seul projet `{AppName}/`. Cible **Windows uniquement**. Pas de séparation `{BackendName}` / `{LibName}`.

> **Positionnement à connaître avant de choisir.** Ce stack existe pour **maintenir et étendre** un parc d'applications métier existant — il est immense. Pour un **nouveau** projet desktop Windows, `desktop/wpf.md` est le choix recommandé : data binding déclaratif, séparation MVVM, theming. Voir §8.

---

# 1. Architecture

## 1.1 Pattern applicatif — MVP, et non MVVM

**Application WinForms sur .NET 10**, structurée en **Model-View-Presenter** :

- **WinForms** — `Form` + contrôles Win32, concepteur visuel WYSIWYG
- **MVP** et non MVVM : WinForms n'a **pas** de data binding déclaratif comparable à XAML. Le `BindingSource` existe mais reste limité et impératif. Le Presenter porte donc la logique et pilote la vue à travers une interface.
- **Generic Host** — DI, configuration et logs câblés avant `Application.Run`
- **Serilog** — journal fichier local

Architecture cible :

```
{AppName}/
├── Program.cs                     ── Host + DI, puis Application.Run
├── Views/
│   ├── MainForm.cs · .Designer.cs
│   └── {Domaine}/{Name}Form.cs
├── Views/Interfaces/
│   └── I{Name}View.cs             ── contrat vue <-> presenter
├── Presenters/
│   └── {Domaine}/{Name}Presenter.cs
├── Models/
├── Services/                      ── logique metier, acces API/base
├── Controls/                      ── UserControls reutilisables
├── appsettings.json
└── {AppName}.csproj               ── net10.0-windows + UseWindowsForms
```

**Le principe du MVP ici** : la `Form` implémente `I{Name}View` (propriétés
simples + événements), le Presenter reçoit cette interface. Conséquence utile :
**le Presenter se teste sans instancier de `Form`**, en passant un faux
implémentant l'interface. C'est ce qui rend un projet WinForms testable, et
c'est exactement ce que la capability `unit-tests` sert à exploiter.

---

## 1.2 Couches

- **Views** (`Views/`) : `Form` + `.Designer.cs`. **Aucune logique** — la vue expose des propriétés et lève des événements.
- **View interfaces** (`Views/Interfaces/`) : le contrat. C'est la frontière qui rend le Presenter testable.
- **Presenters** (`Presenters/`) : logique de présentation. Ne référence **aucun** type WinForms — seulement l'interface de vue.
- **Services** (`Services/`) : logique métier, accès API et base. Injectés par interface.
- **Models** (`Models/`) : entités et DTOs.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Bootstrap | `Program.cs` (Host + DI + `Application.Run`) |
| Fenêtre principale | `Views/MainForm.cs` + `MainForm.Designer.cs` |
| Formulaire | `Views/{Domaine}/{Name}Form.cs` + `.Designer.cs` |
| **Interface de vue** | `Views/Interfaces/I{Name}View.cs` |
| Presenter | `Presenters/{Domaine}/{Name}Presenter.cs` |
| Service | `Services/{Name}Service.cs` + `I{Name}Service.cs` |
| Modèle | `Models/{Name}.cs` |
| UserControl | `Controls/{Name}Control.cs` + `.Designer.cs` |
| Configuration | `appsettings.json` |
| Test | projet séparé `{AppName}.Tests/` (TFM `net10.0`, **sans** `-windows`) |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune logique dans un gestionnaire d'événement.** Un `button_Click` lève un événement de vue ou appelle le Presenter, rien de plus. C'est la règle qui distingue un projet WinForms maintenable des `Form.cs` de 4 000 lignes que l'on trouve dans tout parc ancien.
- **Le Presenter ne référence aucun type WinForms** — pas de `Form`, `MessageBox`, `Control`. Il ne connaît que `I{Name}View`. C'est la condition de sa testabilité.
- **`.Designer.cs` est généré** — jamais édité à la main. Le concepteur le réécrit intégralement.
- **Aucun travail long dans le thread UI** : `async`/`await` et `Control.BeginInvoke` pour revenir au thread UI. Jamais `.Result` ni `.Wait()` — interblocage garanti.
- **Un contrôle n'est jamais touché depuis un thread secondaire** — WinForms l'interdit (`InvalidOperationException`, parfois différée et donc difficile à diagnostiquer).
- **`DataGridView` en mode virtuel** (`VirtualMode = true`) au-delà de quelques milliers de lignes : le mode par défaut matérialise chaque cellule.
- **DI par constructeur** pour les Presenters et les Services ; les `Form` sont résolues depuis le conteneur.
- **`Dispose` des ressources non managées** — les `Form` non modales fermées doivent être disposées.

**Sécurité** :
- **Aucun secret dans le binaire ni dans `appsettings.json` livré** — un assembly .NET se décompile trivialement.
- **Jeton dans le Credential Manager Windows** (DPAPI), jamais dans `Properties.Settings` ni dans un `.config`.
- **Requêtes paramétrées** si accès direct à une base — l'injection SQL est le défaut le plus fréquent des applications de gestion de cette génération.
- **Binaire signé** Authenticode — sinon SmartScreen bloque.
- **`asInvoker`** dans le manifeste, pas d'élévation par défaut.
- **Mise à jour signée** si la capability `auto-update` est active.

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Base locale | capability `local-db` (EF Core + SQLite) |
| Base serveur | EF Core avec le pilote du `DatabaseType`, ou ODBC via la capability `legacy-interop` |
| Préférences | `appsettings.json` en lecture, `%APPDATA%` en écriture |
| **Secrets** | Credential Manager Windows (DPAPI) |
| Backend distant | capability `http-client` (Refit) |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C** si une base serveur est atteinte : aucun DDL par un agent sur une base existante.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-winforms`
- **Langage** : C# / .NET **10 LTS**
- **TFM** : `net10.0-windows` avec `<UseWindowsForms>true</UseWindowsForms>`
- **Pattern** : **MVP** (cf. §1.1)
- **Plateformes** : **Windows uniquement**
- **Package manager** : NuGet (`dotnet` CLI)
- **Runtime chez l'utilisateur** : .NET 10 Desktop Runtime, ou publication self-contained

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/{AppName}.csproj`
- **Run dev** : `dotnet run --project workspace/src/{AppName}`
- **Build** : `dotnet build workspace/src/{AppName} -c Debug`
- **Publish autonome** : `dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true`
- **Tests** : `dotnet test {AppName}.Tests`
- **Format** : `dotnet format`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && dotnet restore && dotnet build -c Debug --nologo)
test -f workspace/src/{AppName}/Program.cs
test -d workspace/src/{AppName}/Presenters
```

- **Smoke Timeout** : 240s (restore + build)

> ⚠️ **`dotnet build` échoue sur Linux/macOS.** `arch` doit émettre `[INFRA_BLOCKED]` ailleurs que sur Windows.
>
> **Le concepteur visuel exige Visual Studio** — il n'existe pas dans `dotnet` CLI ni dans VS Code. Les `.Designer.cs` sont donc soit repris d'un projet existant, soit écrits à la main (ce sont des `InitializeComponent` explicites), soit produits dans VS par le Tech Lead.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/{AppName}.csproj" ]; then

# STEP 0 — Gate d'hote, bloquant
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) : ;;
  *) echo "ERROR: arch {AppName} — stack winforms non scaffoldable"
     echo "CAUSE: [INFRA_BLOCKED] hote $(uname -s) — WinForms exige Windows (TFM net10.0-windows)"
     echo "FIX: executer le pipeline sur Windows, ou choisir un stack portable (desktop/qt-cpp, desktop/electron, desktop/javafx)"
     exit 3 ;;
esac
dotnet --version

# STEP 1 — Scaffold WinForms
dotnet new winforms -n {AppName} -o workspace/src/{AppName} --framework net10.0 --force
cd workspace/src/{AppName}

# STEP 2 — Dependances CORE (cf. 2.4.a)
dotnet add package Microsoft.Extensions.DependencyInjection --version 10.0.11
dotnet add package Microsoft.Extensions.Hosting --version 10.0.11
dotnet add package Microsoft.Extensions.Configuration.Json --version 10.0.11
dotnet add package Microsoft.Extensions.Logging --version 10.0.11
dotnet add package Serilog.Extensions.Hosting --version 10.0.0
dotnet add package Serilog.Sinks.File --version 7.0.0

# STEP 3 — Arborescence MVP (les interfaces de vue sont le pivot, cf. 1.1)
mkdir -p Views/Interfaces Presenters Models Services Controls

# STEP 4 — appsettings.json + CopyToOutputDirectory
cat > appsettings.json <<'JSON'
{
  "Api": { "BaseUrl": "https://localhost:5001", "Version": "v1" },
  "Serilog": { "MinimumLevel": "Information" }
}
JSON

python - <<'PY'
import pathlib, glob
p = pathlib.Path(glob.glob("*.csproj")[0])
s = p.read_text(encoding="utf-8")
if "appsettings.json" not in s:
    s = s.replace("</Project>", """  <ItemGroup>
    <None Update="appsettings.json">
      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
    </None>
  </ItemGroup>
</Project>""")
    p.write_text(s, encoding="utf-8")
PY

# STEP 5 — Program.cs : Host + DI AVANT Application.Run
cat > Program.cs <<'CS'
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace {AppNamespace};

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();

        // Le Host est construit AVANT Application.Run : c'est ce qui permet
        // de resoudre les Form depuis le conteneur (cf. 1.4).
        using var host = Host.CreateApplicationBuilder()
            .ConfigureServices()
            .Build();

        Application.Run(host.Services.GetRequiredService<Views.MainForm>());
    }
}
CS

# STEP 6 — Projet de tests : TFM net10.0 SANS suffixe -windows
#   Les Presenters ne referencent aucun type WinForms (cf. 1.4) : le projet
#   de test n'a donc pas besoin du suffixe, et reste executable sur un agent
#   CI Linux. C'est ce qui rend la regle verifiable mecaniquement.
dotnet new xunit -n {AppName}.Tests -o ../{AppName}.Tests --framework net10.0 --force
dotnet add ../{AppName}.Tests reference {AppName}.csproj

# STEP 7 — Gate
dotnet build -c Debug --nologo

fi
```

**Contrat post-init** :
- `{AppName}.csproj` cible `net10.0-windows` avec `<UseWindowsForms>true</UseWindowsForms>`
- `Program.cs` construit le Host **avant** `Application.Run`
- `Views/Interfaces/` existe (pivot du MVP)
- `appsettings.json` est marqué `CopyToOutputDirectory`
- `{AppName}.Tests` cible `net10.0` (**sans** `-windows`)
- `dotnet build` sort 0

---

## 2.3 Notes de construction

### `Microsoft.Windows.Compatibility` est la dépendance des migrations

C'est la raison principale pour laquelle ce stack existe. Une application
WinForms portée depuis .NET Framework 4.x s'appuie très souvent sur des APIs
Windows retirées de .NET moderne : registre, WMI, ACL, `System.Drawing`
étendu, ODBC, `System.Configuration`.

La capability `legacy-interop` (`Microsoft.Windows.Compatibility`) les ramène
en un seul paquet. **C'est le point de blocage n°1 d'un portage** : sans elle,
la compilation échoue sur des dizaines de types introuvables, et chaque
`using` manquant paraît être un problème distinct alors qu'il n'y en a qu'un.

Ses triggers sont donc volontairement larges (`registre`, `wmi`,
`framework.*4`, `migration.*legacy`, `odbc`, `api.*windows`).

### Même filtre de stabilité que `desktop/wpf`

`Serilog.Sinks.File` est pinné **7.0.0** : NuGet expose un
`8.0.0-nblumhardt-02322` sur le canal stable, dont le suffixe n'est pas
reconnu comme une prerelease par les filtres usuels. Le critère retenu est
strict — une version n'est stable que si elle matche `^\d+(\.\d+){1,3}$`.
Détail et liste complète dans `desktop/wpf.md §2.3`.

### Le TFM du projet de test rend la règle MVP vérifiable

Le projet applicatif cible `net10.0-windows`, le projet de test `net10.0`
**sans** suffixe. Conséquence directe : **si un Presenter référence un type
WinForms, le projet de test ne compile plus.** La règle « le Presenter ne
référence aucun type WinForms » (§1.4) n'est donc pas une convention à
surveiller à la relecture — elle est appliquée par le compilateur.

C'est le même mécanisme que sur `desktop/wpf`, et c'est le principal bénéfice
structurel des deux stacks .NET du catalogue `desktop/`.

### Pas de concepteur visuel hors Visual Studio

Le concepteur WinForms n'existe ni dans `dotnet` CLI ni dans VS Code. Un agent
ne peut donc pas « dessiner » un formulaire : il écrit `InitializeComponent`
explicitement dans le `.Designer.cs`, ce qui est parfaitement valide (c'est
exactement ce que le concepteur génère) mais plus verbeux.

Conséquence pour `arch` : les `.Designer.cs` sont du code écrit, pas du code
généré par outil — mais ils restent **hors périmètre de relecture manuelle**
(§5), car un passage ultérieur dans Visual Studio les réécrira.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version **stable stricte** de chaque paquet (NuGet, 2026-09-02) | `dotnet build` / `dotnet test` |
| Cohérence `.md` ↔ `.libs.json` | Rendu d'un formulaire |
| — | Portage réel depuis .NET Framework |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/winforms.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id winforms`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Microsoft.Extensions.DependencyInjection | 10.0.11 | Conteneur DI — c'est ce qui permet d'injecter un Presenter dans un Form plutot que de l'instancier dans le constructeur |
| Microsoft.Extensions.Hosting | 10.0.11 | Generic Host : DI + configuration + logs cables au demarrage, avant Application.Run |
| Microsoft.Extensions.Configuration.Json | 10.0.11 |  |
| Microsoft.Extensions.Logging | 10.0.11 |  |
| Serilog.Extensions.Hosting | 10.0.0 |  |
| Serilog.Sinks.File | 7.0.0 | Journal local — pas de collecteur central sur un poste client. Pin 7.0.0 (la 8.0.0-nblumhardt-* est une prerelease) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| legacy-interop | Microsoft.Windows.Compatibility | 10.0.11 | registre, \bwmi\b, framework.*4, migration.*legacy, odbc, api.*windows |
| local-db | Microsoft.EntityFrameworkCore.Sqlite | 10.0.11 | base.*locale, sqlite, hors.*ligne |
| http-client | Refit.HttpClientFactory | 15.2.0 | appel.*api, backend, rest |
| validation | FluentValidation | 12.1.1 | validation, regle.*saisie, formulaire |
| mapping | AutoMapper | 16.2.0 | mapping, dto |
| charts | LiveChartsCore.SkiaSharpView.WPF | 2.0.5 | chart, graphique, courbe |
| webview | Microsoft.Web.WebView2 | 1.0.4191.47 | webview, contenu.*web, moderniser.*ecran |
| excel | ClosedXML | 0.105.1 | excel, xlsx, export.*tableur |
| pdf | QuestPDF | 2026.8.0 | \bpdf\b, impression |
| auto-update | Velopack | 1.2.0 | mise.*a.*jour, auto-update, installeur |
| unit-tests | xunit | 2.9.3 | tests.*unitaires, xunit, presenter.*test |
| unit-tests | NSubstitute | 6.2.0 | mock, substitute |
| unit-tests | Shouldly | 4.3.0 | assertions, should |
| ui-automation | FlaUI.UIA3 | 5.0.0 | test.*ui, automation, flaui |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Formulaire | `{Name}Form.cs` + `{Name}Form.Designer.cs` | `CustomerListForm.cs` |
| **Interface de vue** | `I{Name}View.cs` | `ICustomerListView.cs` |
| Presenter | `{Name}Presenter.cs` | `CustomerListPresenter.cs` |
| Service | `{Name}Service.cs` + `I{Name}Service.cs` | `CustomerService.cs` |
| Modèle | `{Name}.cs` | `Customer.cs` |
| UserControl | `{Name}Control.cs` | `SearchBoxControl.cs` |
| Contrôle dans le concepteur | `{role}{Type}` | `btnSave`, `txtCustomerName`, `grdCustomers` |
| Test | `{Name}PresenterTests.cs` | `CustomerListPresenterTests.cs` |

**Conventions** : C# standard. Un formulaire, son interface de vue et son Presenter partagent le **même préfixe** — `CustomerListForm` / `ICustomerListView` / `CustomerListPresenter`.

**INTERDITS** :
- Contrôle nommé par défaut (`button1`, `textBox2`, `dataGridView1`) — c'est le défaut le plus répandu de ce stack, et il rend le code illisible
- `Form` sans interface de vue correspondante (casse le MVP)
- Suffixe `Presenter` omis
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

Base URL et version lues depuis `appsettings.json` (section `Api`), jamais en
constante compilée. **CORS : sans objet** — l'application n'est pas un
navigateur.

---

## 4. Versioning et livraison

- **`<Version>`** du `.csproj` renseigné
- **Binaire signé** Authenticode
- **Deux modes de publication** : *self-contained* (~70 Mo, aucun prérequis) ou *framework-dependent* (~2 Mo, exige le .NET 10 Desktop Runtime). Sur un parc existant, le second est souvent imposé par la politique de déploiement.
- **`apiVersion`** dans `appsettings.json` si un backend est consommé — un poste client n'est pas mis à jour de façon synchrone

---

## 5. Interdits projet (winforms)

**Architecture** :
- Logique métier dans un gestionnaire d'événement (`button_Click`)
- Presenter référençant `Form`, `Control`, `MessageBox` ou tout type WinForms
- `Form` sans interface de vue — casse le MVP et la testabilité
- `.Designer.cs` édité à la main (il sera réécrit par le concepteur)
- `.Result` / `.Wait()` sur une `Task` — interblocage du thread UI
- Accès à un contrôle depuis un thread secondaire — passer par `BeginInvoke`
- `DataGridView` non virtuel au-delà de quelques milliers de lignes
- `new CustomerForm()` en dur là où la DI est disponible
- Variable statique portant l'état applicatif
- `Form` non modale fermée sans `Dispose`

**Code quality** :
- Contrôle nommé par défaut (§2.5)
- `Form.cs` de plus de 500 lignes — extraire des UserControls et remonter la logique dans le Presenter
- `async void` hors gestionnaire d'événement
- `catch (Exception) {}` silencieux
- `Console.WriteLine` / `MessageBox.Show` pour tracer — utiliser `ILogger<T>`
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Secret dans `appsettings.json` livré ou en constante
- Jeton dans `Properties.Settings` ou un `.config`
- Requête SQL concaténée
- Binaire non signé
- Manifeste `requireAdministrator` sans nécessité prouvée

**Build / packaging** :
- Committer `bin/`, `obj/`, `*.user`, `.vs/`
- TFM sans suffixe `-windows` sur le projet applicatif
- TFM **avec** `-windows` sur le projet de test (§2.3)
- `appsettings.json` sans `CopyToOutputDirectory`
- Installer un paquet en prerelease (§2.3)

---

## 6. Persistance — voir §1.5

EF Core + SQLite via la capability `local-db`. Phase B (DB) d'`arch` : **applicable** si une base serveur est déclarée, **lecture seule** sur une base existante.

---

## 7. Temps reel

- **Polling** : `System.Windows.Forms.Timer` + client Refit — le plus courant sur ce type d'application
- **SignalR client** — **non catalogué**, à instruire si le backend expose un Hub
- **Notifications système** : `NotifyIcon` — inclus dans WinForms

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est justifié pour :
- **Maintenir et étendre un parc WinForms existant** — c'est sa raison d'être. Le parc est immense, et une réécriture en WPF est une réécriture complète de l'UI.
- **Portage .NET Framework → .NET moderne** — la capability `legacy-interop` est faite pour ça (§2.3)
- **Écrans de saisie et grilles simples** livrés très vite par une équipe qui connaît déjà l'outil
- **Contrainte de compétence** : le vivier WinForms reste large

**NE PAS choisir si** :
- ❌ **C'est un nouveau projet** → `desktop/wpf`. Le data binding déclaratif, la séparation MVVM et le theming changent l'effort de maintenance à moyen terme. C'est le critère de rejet n°1.
- ❌ **Autre OS que Windows nécessaire, même à terme** — WinForms n'est pas portable
- ❌ **Interface moderne attendue** — WinForms n'a pas de système de theming. Un rendu contemporain demande des contrôles tiers, et le résultat reste en deçà de WPF ou d'Electron. La voie pragmatique de modernisation par incréments est la capability `webview` (héberger une vue web dans un `Form` existant).
- ❌ **Interface très interactive** (animations, mise en page fluide) — le modèle de layout WinForms est positionnel
- ❌ **Équipe web** → `desktop/electron` ; **Delphi** → `desktop/delphi-vcl` ; **Python** → `desktop/pyside`
- ❌ **CI/CD sur agents Linux uniquement** — la compilation exige Windows

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-winforms` autonome (capability `local-db`) | 🟡 experimental | jamais validé end-to-end |
| `desktop-winforms` + capability `legacy-interop` (portage .NET Framework) | 🟡 experimental | cas d'usage principal du stack |
| `desktop-winforms` + backend `dotnet-minimalapi` + `auth-local` | 🟡 experimental | affinité forte (même langage, DTOs partageables) |
| `desktop-winforms` + `qa/dotnet-xunit` | 🟡 experimental | tests de Presenters sur le projet `net10.0` séparé |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate d'hôte, bloquant.** WinForms exige Windows. Sinon STOP `[INFRA_BLOCKED]`.
2. **Signaler le positionnement** : si l'US décrit un **nouveau** projet desktop Windows sans parc existant, émettre un WARNING recommandant `desktop/wpf` (§8). Ce stack reste utilisable si le Tech Lead confirme.
3. **Détecter** `desktop/winforms.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
4. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** (`preflight.validate_stack_combo`)
5. **TFM `net10.0-windows` + `<UseWindowsForms>true</UseWindowsForms>`** sur le projet applicatif ; **`net10.0` sans suffixe** sur le projet de test — c'est ce qui rend la règle MVP vérifiable par le compilateur (§2.3)
6. **`Views/Interfaces/` fait partie du bootstrap** (STEP 3) : sans interfaces de vue, le MVP n'existe pas et les Presenters deviennent intestables
7. **Host construit avant `Application.Run`** (STEP 5)
8. **`appsettings.json` avec `CopyToOutputDirectory`** — sinon la configuration est vide au runtime
9. **Pas de concepteur visuel disponible** (§2.3) : les `.Designer.cs` sont écrits explicitement
10. **`## Active UI Specs`** : aucun design system web n'est compatible. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`
11. **Phase B (DB)** : applicable si base serveur, **lecture seule** sur base existante
12. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-winforms.md` documentant .NET 10 + WinForms + MVP, **et la raison de ne pas avoir retenu WPF** (parc existant, portage, compétence) — cette justification est le cœur de la décision

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome).

- `dev-backend` **ne touche pas** au projet WinForms — il code le backend séparé s'il est déclaré
- `dev-frontend` matérialise **tout** le projet WinForms

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `Views/**` (`.cs`) | `dev-frontend` |
| `Views/**` (`.Designer.cs`) | `dev-frontend` — **hors relecture manuelle** (réécrit par le concepteur) |
| `Views/Interfaces/**` | `dev-frontend` (c'est le contrat de la vue) |
| `Presenters/**` | `dev-frontend` |
| `Services/**`, `Models/**` | `dev-frontend` |
| `Controls/**` | `dev-frontend` |
| `Program.cs` | `arch` (create, Host + DI) + `dev-frontend` (enregistrements) |
| `appsettings.json` | `arch` (create) + `dev-frontend` (ajout de clés) |
| `{AppName}.csproj` | `arch` (create) + `dev-frontend` (deps on-demand) |
| `{AppName}.Tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) : ;; *) echo "SKIP: hote non-Windows"; exit 3 ;; esac

cd workspace/src/{AppName}
dotnet restore

test -f Program.cs
test -d Presenters
test -d Views/Interfaces               # pivot du MVP (cf. 1.1)

grep -q "net10.0-windows" {AppName}.csproj
grep -q "<UseWindowsForms>true</UseWindowsForms>" {AppName}.csproj

# Le projet de test NE doit PAS cibler -windows : c'est ce qui empeche un
# Presenter de referencer un type WinForms (cf. 2.3)
! grep -q "net10.0-windows" ../{AppName}.Tests/{AppName}.Tests.csproj

grep -q "CopyToOutputDirectory" {AppName}.csproj

# Aucune prerelease (cf. 2.3)
! grep -qE 'Version="[0-9.]+-[a-zA-Z]' {AppName}.csproj

dotnet build -c Debug --nologo
dotnet test ../{AppName}.Tests --nologo

echo "smoke OK"
```
