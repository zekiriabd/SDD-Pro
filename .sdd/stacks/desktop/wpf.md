# Tech FEAT: wpf (desktop)

> §2.4 (Librairies) regeneree depuis `wpf.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id wpf`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque paquet résolu contre NuGet. **Trois prereleases** ont été écartées à la construction : NuGet les expose sur le canal stable avec des suffixes que les filtres usuels ne détectent pas (cf. §2.3). **Jamais exécuté end-to-end via `/sdd-full`** : aucun `dotnet build` n'a tourné en CI (WPF exige Windows). Non supporté commercialement en l'état.
Tech FEAT ID: tech-wpf
Scope: **client desktop Windows natif** — application **WPF sur .NET 10** dans UN seul projet `{AppName}/`. XAML déclaratif + data binding bidirectionnel, pattern MVVM. Cible **Windows uniquement**. Pas de séparation `{BackendName}` / `{LibName}`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application WPF MVVM sur .NET 10** :

- **XAML** — UI déclarative avec **data binding bidirectionnel**, ce qui est l'atout structurel de ce stack : la vue s'accroche aux propriétés du ViewModel, sans code de synchronisation
- **CommunityToolkit.Mvvm** — `[ObservableProperty]` et `[RelayCommand]` par source generators
- **Generic Host** — DI, configuration et logs câblés au démarrage, comme sur un projet ASP.NET
- **Serilog** — journal fichier local

Architecture cible :

```
{AppName}/
├── App.xaml · App.xaml.cs         ── bootstrap : Host, DI, ressources
├── Views/
│   ├── MainWindow.xaml
│   └── {Domaine}/{Name}View.xaml
├── ViewModels/
│   ├── MainViewModel.cs
│   └── {Domaine}/{Name}ViewModel.cs
├── Models/                        ── entites et DTOs
├── Services/                      ── logique metier, acces API/base
├── Controls/                      ── UserControls reutilisables
├── Converters/                    ── IValueConverter
├── Resources/                     ── styles, templates, dictionnaires
├── appsettings.json
└── {AppName}.csproj               ── net10.0-windows + UseWPF
```

**Différence vs `desktop/winforms`** : le data binding. WinForms n'a pas
d'équivalent déclaratif, ce qui impose le pattern MVP et beaucoup de code de
synchronisation à la main. C'est la raison pour laquelle WPF est le défaut
recommandé pour un **nouveau** projet desktop Windows.

**Différence vs `desktop/electron`** : rendu natif, démarrage instantané,
quelques dizaines de Mo de RAM — contre un Chromium embarqué. En échange, WPF
est Windows-only.

---

## 1.2 Couches

- **Views** (`Views/`) : XAML + code-behind **vide** (au plus un `InitializeComponent`).
- **ViewModels** (`ViewModels/`) : état et commandes de l'écran. Aucune référence à un type WPF — c'est ce qui les rend testables.
- **Services** (`Services/`) : logique métier, accès API et base. Injectés par interface.
- **Models** (`Models/`) : entités et DTOs.
- **Converters** (`Converters/`) : adaptation de types pour le binding (bool → Visibility…).

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Bootstrap | `App.xaml` + `App.xaml.cs` (Host + DI) |
| Fenêtre principale | `Views/MainWindow.xaml` |
| Vue | `Views/{Domaine}/{Name}View.xaml` |
| ViewModel | `ViewModels/{Domaine}/{Name}ViewModel.cs` |
| Service | `Services/{Name}Service.cs` + `I{Name}Service.cs` |
| Modèle | `Models/{Name}.cs` |
| UserControl | `Controls/{Name}Control.xaml` |
| Converter | `Converters/{Name}Converter.cs` |
| Styles / templates | `Resources/{Styles,Templates,Colors}.xaml` |
| Configuration | `appsettings.json` |
| Test | projet séparé `{AppName}.Tests/` (TFM `net10.0`, **sans** `-windows`) |

---

## 1.4 Principes non negociables

**Architecture** :
- **Code-behind vide.** Un `.xaml.cs` contenant de la logique signale un binding manquant ou un behavior à écrire (`Microsoft.Xaml.Behaviors.Wpf`, en CORE).
- **ViewModel sans référence WPF** — pas de `Window`, `MessageBox` ni `Dispatcher` : passer par un service abstrait (`IDialogService`). C'est la condition pour tester le ViewModel sans UI.
- **`[ObservableProperty]` / `[RelayCommand]`** — jamais de `INotifyPropertyChanged` écrit à la main.
- **DI par constructeur**, ViewModels résolus depuis le conteneur ; pas de `new` sur un ViewModel dans une vue.
- **`ObservableCollection<T>`** pour les listes liées — une `List<T>` ne notifie rien, et l'UI ne se rafraîchit pas.
- **Virtualisation activée** sur les listes longues (`VirtualizingStackPanel.IsVirtualizing="True"`, actif par défaut sur `ListBox`/`DataGrid` mais **désactivé dès qu'on englobe la liste dans un `ScrollViewer`** — piège classique).
- **`async`/`await` sur tout appel long**, et retour au thread UI géré par le contexte de synchronisation. Jamais `.Result` ni `.Wait()` : c'est un interblocage garanti sur le thread UI.
- **`x:Bind` indisponible en WPF** (c'est du WinUI) — les bindings restent résolus au runtime, donc **une faute de frappe dans un `Binding` est silencieuse**. Activer les erreurs de binding en trace de debug.

**Sécurité** :
- **Aucun secret dans le binaire ni dans `appsettings.json` livré** — un assembly .NET se décompile trivialement (ILSpy). Toute clé sensible passe par le backend.
- **Jeton dans le Credential Manager Windows** (DPAPI), jamais dans `appsettings.json` ni dans les `Properties.Settings`.
- **Requêtes paramétrées** si accès direct à une base.
- **Binaire signé** Authenticode — sinon SmartScreen bloque.
- **`asInvoker`** dans le manifeste, pas d'élévation par défaut.
- **Mise à jour signée** si la capability `auto-update` est active : un canal de mise à jour non signé est un vecteur d'exécution de code arbitraire.

---

## 1.5 Persistance

| Besoin | Voie |
|---|---|
| Base locale | capability `local-db` (EF Core + SQLite) |
| Préférences | `appsettings.json` en lecture, `%APPDATA%` en écriture |
| **Secrets** | Credential Manager Windows (DPAPI) — **jamais** un fichier |
| Backend distant | capability `http-client` (Refit) |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C** si une base serveur est
> atteinte : aucun DDL par un agent sur une base existante.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `desktop-wpf`
- **Langage** : C# / .NET **10 LTS**
- **TFM** : `net10.0-windows` — le suffixe est **obligatoire** (§2.3)
- **Framework UI** : WPF (`<UseWPF>true</UseWPF>`)
- **Plateformes** : **Windows uniquement**
- **Package manager** : NuGet (`dotnet` CLI)
- **Runtime chez l'utilisateur** : .NET 10 Desktop Runtime, ou publication self-contained

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/{AppName}.csproj`
- **Run dev** : `dotnet run --project workspace/src/{AppName}`
- **Build** : `dotnet build workspace/src/{AppName} -c Debug`
- **Publish autonome** : `dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true`
- **Publish framework-dependent** : `dotnet publish -c Release -r win-x64 --self-contained false`
- **Tests** : `dotnet test {AppName}.Tests`
- **Format** : `dotnet format`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && dotnet restore && dotnet build -c Debug --nologo)
test -f workspace/src/{AppName}/{AppName}.csproj
test -f workspace/src/{AppName}/App.xaml
```

- **Smoke Timeout** : 240s (restore + build)

> ⚠️ **`dotnet build` échoue sur Linux/macOS** : le TFM `net10.0-windows` avec `UseWPF` n'est constructible que sur Windows. `arch` doit émettre `[INFRA_BLOCKED]` ailleurs.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/{AppName}.csproj" ]; then

# STEP 0 — Gate d'hote, bloquant
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) : ;;
  *) echo "ERROR: arch {AppName} — stack wpf non scaffoldable"
     echo "CAUSE: [INFRA_BLOCKED] hote $(uname -s) — WPF exige Windows (TFM net10.0-windows)"
     echo "FIX: executer le pipeline sur Windows, ou choisir un stack portable (desktop/qt-cpp, desktop/electron, desktop/javafx)"
     exit 3 ;;
esac
dotnet --version

# STEP 1 — Scaffold WPF
dotnet new wpf -n {AppName} -o workspace/src/{AppName} --framework net10.0 --force
cd workspace/src/{AppName}

# STEP 2 — Dependances CORE (cf. 2.4.a)
dotnet add package CommunityToolkit.Mvvm --version 8.4.2
dotnet add package Microsoft.Extensions.DependencyInjection --version 10.0.11
dotnet add package Microsoft.Extensions.Hosting --version 10.0.11
dotnet add package Microsoft.Extensions.Configuration.Json --version 10.0.11
dotnet add package Microsoft.Extensions.Logging --version 10.0.11
dotnet add package Serilog.Extensions.Hosting --version 10.0.0
dotnet add package Serilog.Sinks.File --version 7.0.0
dotnet add package Microsoft.Xaml.Behaviors.Wpf --version 1.1.158

# STEP 3 — Arborescence MVVM
mkdir -p Views ViewModels Models Services Controls Converters Resources

# STEP 4 — appsettings.json copie a la sortie (sinon introuvable au runtime)
cat > appsettings.json <<'JSON'
{
  "Api": { "BaseUrl": "https://localhost:5001", "Version": "v1" },
  "Serilog": { "MinimumLevel": "Information" }
}
JSON

# `CopyToOutputDirectory` est OBLIGATOIRE : sans lui, appsettings.json reste
# dans le repertoire source et la configuration est vide a l'execution.
dotnet_csproj={AppName}.csproj
python - <<'PY'
import pathlib, re, glob
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

# STEP 5 — Projet de tests : TFM net10.0 SANS suffixe -windows
#   Un projet de test n'a pas besoin de WPF, et le suffixe -windows le
#   rendrait non executable sur un agent CI Linux.
dotnet new xunit -n {AppName}.Tests -o ../{AppName}.Tests --framework net10.0 --force
dotnet add ../{AppName}.Tests reference {AppName}.csproj

# STEP 6 — Gate
dotnet build -c Debug --nologo

fi
```

**Contrat post-init** :
- `{AppName}.csproj` cible `net10.0-windows` avec `<UseWPF>true</UseWPF>`
- `appsettings.json` est marqué `CopyToOutputDirectory`
- L'arborescence MVVM existe
- `{AppName}.Tests` cible `net10.0` (**sans** `-windows`)
- `dotnet build` sort 0

---

## 2.3 Notes de construction

### Le TFM `net10.0-windows` est load-bearing

```xml
<TargetFramework>net10.0-windows</TargetFramework>
<UseWPF>true</UseWPF>
```

Les deux vont ensemble. Sans le suffixe `-windows`, les assemblies WPF ne sont
pas référencées et la compilation échoue sur des symboles introuvables
(`Window`, `Application`) — un message qui ne mentionne pas le TFM.

**Corollaire pour le projet de test** : il cible `net10.0` **sans** suffixe. Un
test de ViewModel n'a pas besoin de WPF, et le suffixe le rendrait non
exécutable sur un agent CI Linux. C'est ce qui rend la règle « ViewModel sans
référence WPF » (§1.4) vérifiable mécaniquement : si le ViewModel référence
`Window`, le projet de test ne compile plus.

### Trois prereleases écartées

NuGet expose, sur le canal **stable**, des versions dont le suffixe n'est pas
reconnu par les filtres de prerelease habituels (`-alpha`, `-beta`, `-rc`) :

| Paquet | Ce que renvoie « latest » | Dernière **stable** réelle |
|---|---|---|
| `Serilog.Sinks.File` | `8.0.0-nblumhardt-02322` | **7.0.0** |
| `MaterialDesignThemes` | `5.3.3-ci1462` | **5.3.2** |
| `Velopack` | `1.2.110-ge826545` | **1.2.0** |

Le filtre retenu pour ce catalog est **strict** : une version n'est stable que
si elle matche `^\d+(\.\d+){1,3}$`. Toute étiquette — y compris un nom de
mainteneur ou un identifiant de build CI — la disqualifie. C'est
`rules/library-and-stack.md §5` (« pas de prerelease sans ADR ») appliqué à la
lettre.

### Un thème est quasi obligatoire

Le rendu WPF par défaut date de 2006. La capability `modern-theme` (`Wpf.Ui`,
thème Fluent/WinUI 3) n'est pas cosmétique : sans elle, une application neuve
paraît immédiatement datée. Elle est en on-demand plutôt qu'en CORE parce que
le choix du thème est un arbitrage produit, pas une contrainte technique.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version **stable stricte** de chaque paquet (NuGet, 2026-09-02) | `dotnet build` / `dotnet test` |
| Cohérence `.md` ↔ `.libs.json` | Rendu XAML réel |
| — | Publication et signature |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/desktop/wpf.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id wpf`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| CommunityToolkit.Mvvm | 8.4.2 | MVVM par source generators : [ObservableProperty] et [RelayCommand] remplacent le INotifyPropertyChanged ecrit a la main. Sans lui, chaque propriete liee coute une dizaine de lignes de boilerplate |
| Microsoft.Extensions.DependencyInjection | 10.0.11 | Conteneur DI — WPF n'en fournit aucun, les ViewModels seraient sinon instancies dans le code-behind |
| Microsoft.Extensions.Hosting | 10.0.11 | Generic Host : cycle de vie, configuration et DI cables ensemble au demarrage de l'App |
| Microsoft.Extensions.Configuration.Json | 10.0.11 | Lecture d'appsettings.json declare au manifest |
| Microsoft.Extensions.Logging | 10.0.11 |  |
| Serilog.Extensions.Hosting | 10.0.0 | Logs structures branches sur le Generic Host |
| Serilog.Sinks.File | 7.0.0 | Sink fichier — sur un client desktop il n'y a pas de collecteur central : le fichier local EST le journal de diagnostic. Pin 7.0.0 : nuget expose un 8.0.0-nblumhardt-* qui est une prerelease |
| Microsoft.Xaml.Behaviors.Wpf | 1.1.158 | Behaviors et triggers declaratifs — evite le code-behind pour brancher un evenement sur une commande |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| modern-theme | Wpf.Ui | 3.4.2.7 | theme, fluent, winui, apparence.*moderne, dark.*mode |
| modern-theme | MaterialDesignThemes (alt) | 5.3.2 | material.*design |
| control-library | HandyControl | 3.5.1 | controle.*avance, handycontrol, composant.*riche |
| charts | LiveChartsCore.SkiaSharpView.WPF | 2.0.5 | chart, graphique, courbe, visualisation.*donnees |
| local-db | Microsoft.EntityFrameworkCore.Sqlite | 10.0.11 | base.*locale, sqlite, hors.*ligne, donnees.*locales |
| http-client | Refit.HttpClientFactory | 15.2.0 | appel.*api, backend, rest, http |
| validation | FluentValidation | 12.1.1 | validation, formulaire, regle.*saisie |
| mapping | AutoMapper | 16.2.0 | mapping, dto.*vers.*viewmodel |
| webview | Microsoft.Web.WebView2 | 1.0.4191.47 | webview, contenu.*web, afficher.*page |
| excel | ClosedXML | 0.105.1 | excel, xlsx, export.*tableur |
| pdf | QuestPDF | 2026.8.0 | \bpdf\b, impression, export.*pdf |
| auto-update | Velopack | 1.2.0 | mise.*a.*jour, auto-update, installeur, deploiement.*poste |
| unit-tests | xunit | 2.9.3 | tests.*unitaires, xunit, viewmodel.*test |
| unit-tests | NSubstitute | 6.2.0 | mock, substitute, tests.*unitaires |
| unit-tests | Shouldly | 4.3.0 | assertions, should |
| ui-automation | FlaUI.UIA3 | 5.0.0 | test.*ui, automation, test.*bout.*en.*bout, flaui |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Vue | `{Name}View.xaml` → `partial class {Name}View` | `CustomerListView.xaml` |
| Fenêtre | `{Name}Window.xaml` | `MainWindow.xaml` |
| ViewModel | `{Name}ViewModel.cs` | `CustomerListViewModel.cs` |
| Service | `{Name}Service.cs` + `I{Name}Service.cs` | `CustomerService.cs` |
| Modèle | `{Name}.cs` | `Customer.cs` |
| UserControl | `{Name}Control.xaml` | `SearchBoxControl.xaml` |
| Converter | `{Name}Converter.cs` | `BoolToVisibilityConverter.cs` |
| Commande | propriété `{Verbe}Command` générée par `[RelayCommand]` sur `{Verbe}()` | `SaveCommand` ← `Save()` |
| Test | `{Name}ViewModelTests.cs` | `CustomerListViewModelTests.cs` |
| Élément XAML nommé | `x:Name="{role}{Type}"` | `x:Name="SaveButton"` |

**Conventions** : C# standard (PascalCase pour les types et membres publics, `_camelCase` pour les champs privés). Une vue et son ViewModel portent le **même préfixe** — c'est ce qui permet une résolution par convention.

**INTERDITS** :
- Suffixe `VM` au lieu de `ViewModel`
- `Manager`, `Helper`, `Util`
- Vue et ViewModel de préfixes différents
- Élément XAML nommé `TextBox1`, `Button1`

---

## 3. Backend consomme (optionnel)

Ce stack fonctionne **soit** en autonome (capability `local-db`), **soit** en
client d'un backend déclaré en `## Active Tech Specs`.

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | authentification |
| `GET /api/me` | utilisateur courant |

Base URL et version lues depuis `appsettings.json` (section `Api`), **jamais**
en constante compilée.

---

## 4. Versioning et livraison

- **`<Version>`** du `.csproj` renseigné — c'est ce que lit l'utilisateur dans les propriétés du fichier
- **Binaire signé** Authenticode
- **Deux modes de publication** : *self-contained* (~70 Mo, aucun prérequis) ou *framework-dependent* (~2 Mo, exige le .NET 10 Desktop Runtime installé). Le choix est un arbitrage de déploiement à trancher **avant** la première livraison.
- **`apiVersion`** dans `appsettings.json` si un backend est consommé : un poste client n'est pas mis à jour de façon synchrone, le backend doit supporter les versions déployées

---

## 5. Interdits projet (wpf)

**Architecture** :
- Logique dans un `.xaml.cs` — utiliser un binding ou un behavior
- ViewModel référençant `Window`, `MessageBox`, `Dispatcher` ou tout type WPF
- `INotifyPropertyChanged` écrit à la main — utiliser `[ObservableProperty]`
- `List<T>` liée à un `ItemsSource` — utiliser `ObservableCollection<T>`
- `new MyViewModel()` dans une vue — passer par la DI
- `.Result` / `.Wait()` sur une `Task` — interblocage du thread UI
- Liste longue enveloppée dans un `ScrollViewer` — désactive la virtualisation
- `Dispatcher.Invoke` synchrone depuis un thread secondaire
- Ressource statique dupliquée au lieu d'un dictionnaire partagé

**Code quality** :
- `async void` hors gestionnaire d'événement
- `dynamic` injustifié
- Méthode de plus de 30 lignes
- `catch (Exception) {}` silencieux
- `Console.WriteLine` — utiliser `ILogger<T>`
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Secret dans `appsettings.json` livré ou en constante (un assembly .NET se décompile)
- Jeton persisté hors du Credential Manager
- Requête SQL concaténée
- Binaire non signé
- Manifeste `requireAdministrator` sans nécessité prouvée
- Canal de mise à jour non signé (capability `auto-update`)

**Build / packaging** :
- Committer `bin/`, `obj/`, `*.user`, `.vs/`
- TFM sans suffixe `-windows` sur le projet applicatif (§2.3)
- TFM **avec** `-windows` sur le projet de test
- `appsettings.json` sans `CopyToOutputDirectory` — configuration vide au runtime
- Publier en Debug
- Installer un paquet en prerelease (§2.3)

---

## 6. Persistance — voir §1.5

EF Core + SQLite via la capability `local-db`. Phase B (DB) d'`arch` : **applicable** si une base serveur est déclarée, **lecture seule** sur une base existante.

---

## 7. Temps reel

- **SignalR client** (`Microsoft.AspNetCore.SignalR.Client`) — **non catalogué**, à instruire si le backend expose un Hub
- **Polling** : `PeriodicTimer` + client Refit — suffisant dans la plupart des cas
- **Notifications système** : API Windows via `Microsoft.Windows.Compatibility` (capability du stack `winforms`) ou `CommunityToolkit`

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Applications métier Windows riches** — data binding, grilles complexes, formulaires denses
- **Équipes .NET** — le langage, l'outillage et les bibliothèques sont partagés avec `backend/dotnet-minimalapi`
- **Rendu natif + démarrage instantané** — quelques dizaines de Mo de RAM contre plusieurs centaines pour Electron
- **Nouveau projet desktop Windows** — c'est le défaut recommandé, devant WinForms

**NE PAS choisir si** :
- ❌ **Autre OS que Windows nécessaire, même à terme** — WPF n'est pas portable. Prendre `desktop/qt-cpp`, `desktop/electron` ou `desktop/javafx`.
- ❌ **Équipe front web déjà en place** → `desktop/electron` réutilise ses compétences
- ❌ **Parc WinForms existant à étendre** → `desktop/winforms` (une migration WinForms → WPF est une réécriture de l'UI)
- ❌ **Équipe Delphi** → `desktop/delphi-vcl` ; **équipe Python** → `desktop/pyside`
- ❌ **CI/CD sur agents Linux uniquement** — la compilation exige Windows
- ❌ **Interface très graphique** (dessin temps réel, 3D) — WPF rend correctement mais n'est pas conçu pour cela

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `desktop-wpf` autonome (capability `local-db`) | 🟡 experimental | jamais validé end-to-end |
| `desktop-wpf` + backend `dotnet-minimalapi` + `auth-azure-ad` | 🟡 experimental | combo à plus forte affinité (même langage, mêmes DTOs partageables) |
| `desktop-wpf` + backend `dotnet-minimalapi` + `auth-local` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `desktop-wpf` + `qa/dotnet-xunit` | 🟡 experimental | tests de ViewModels sur le projet `net10.0` séparé |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate d'hôte, bloquant.** WPF exige Windows. Sinon STOP `[INFRA_BLOCKED]` avec renvoi vers un stack portable.
2. **Détecter** `desktop/wpf.md` en `## Active Tech Specs` → `frontendKind=desktop`, projet unique
3. **`desktop/*` est exclusif de `mobiles/*` et de `frontend/*`** (`preflight.validate_stack_combo`)
4. **TFM `net10.0-windows` + `<UseWPF>true</UseWPF>`** sur le projet applicatif ; **`net10.0` sans suffixe** sur le projet de test (§2.3)
5. **`appsettings.json` avec `CopyToOutputDirectory`** (STEP 4) — sans quoi la configuration est vide au runtime, sans erreur explicite
6. **Propager** `Api:BaseUrl` et `Api:Version` depuis `stack.md` vers `appsettings.json`. **Aucun secret** n'y est écrit : un assembly .NET se décompile (§1.4)
7. **Ne pas installer de prerelease** — filtre strict `^\d+(\.\d+){1,3}$` (§2.3)
8. **`## Active UI Specs`** : aucun design system web n'est compatible. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`. L'équivalent ici est la capability `modern-theme`.
9. **Phase B (DB)** : applicable si base serveur, **lecture seule** sur base existante
10. **Phase C (ADRs)** : créer `ADR-{ts}-stack-desktop-wpf.md` documentant .NET 10 + WPF + MVVM (CommunityToolkit), le mode de publication retenu (self-contained ou non) et la contrainte Windows

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Ce stack n'a PAS de « backend interne »** (sauf mode autonome).

- `dev-backend` **ne touche pas** au projet WPF — il code le backend séparé s'il est déclaré
- `dev-frontend` matérialise **tout** le projet WPF

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `Views/**`, `Controls/**`, `Resources/**` | `dev-frontend` |
| `ViewModels/**` | `dev-frontend` |
| `Services/**`, `Models/**` | `dev-frontend` |
| `Converters/**` | `dev-frontend` |
| `App.xaml.cs` (Host + DI) | `arch` (create) + `dev-frontend` (enregistrements) |
| `appsettings.json` | `arch` (create) + `dev-frontend` (ajout de clés) |
| `{AppName}.csproj` | `arch` (create) + `dev-frontend` (deps on-demand) |
| `{AppName}.Tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) : ;; *) echo "SKIP: hote non-Windows"; exit 3 ;; esac

cd workspace/src/{AppName}
dotnet restore

test -f App.xaml
test -d ViewModels

# TFM : le suffixe -windows est load-bearing (cf. 2.3)
grep -q "net10.0-windows" {AppName}.csproj
grep -q "<UseWPF>true</UseWPF>" {AppName}.csproj

# Le projet de test NE doit PAS cibler -windows (cf. 2.3)
! grep -q "net10.0-windows" ../{AppName}.Tests/{AppName}.Tests.csproj

# Sans cela, la configuration est vide au runtime
grep -q "CopyToOutputDirectory" {AppName}.csproj

# Aucune prerelease (cf. 2.3)
! grep -qE 'Version="[0-9.]+-[a-zA-Z]' {AppName}.csproj

dotnet build -c Debug --nologo
dotnet test ../{AppName}.Tests --nologo

echo "smoke OK"
```
