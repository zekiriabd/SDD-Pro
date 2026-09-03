# Tech FEAT: maui (mobile)

> §2.4 (Librairies) regeneree depuis `maui.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id maui`).

Status: Experimental
Validation: 🟢 bench-validated runtime — Windows desktop (2026-06-05 — CalcABCMaui, MAUI workloads installés, cible `net9.0-windows10.0.19041.0` WinUI3, build 5.88s 0 err 4 warn (Frame obsolète), fenêtre WinUI3 PID 15972 246MB lancée, HttpClient → FastAPI :44329, AC-1/2/3 🟢. Cibles iOS/Android/macOS non testées sans toolchain. Bug fix : `-f net8.0` rejeté par template SDK 10 → `-f net9.0`. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`. **Rebase 2026-09-02** : le bench ci-dessus a tourne sur `net9.0` ; le stack cible desormais **`net10.0` (LTS active)** car .NET 9 est passe en support *maintenance*. Le runtime n'a pas ete re-benche sur net10 — la cible Windows reste le seul runtime observe. 3 references NuGet inexistantes ont ete retirees du catalog au meme audit, cf. §2.3.)
Tech FEAT ID: tech-maui
Scope: **mobile cross-platform** — application **.NET MAUI 10** (Multi-platform App UI) dans UN seul projet `{AppName}/`. Single codebase C# / XAML qui cible iOS + Android (+ macOS Catalyst + Windows en option). UI MAUI + MVVM + acces APIs natives + auth vivent dans le meme `.csproj`. Pas de separation `{BackendName}` / `{LibName}`.

> **Backend separe** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte declaree en `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`, `backend/node-express.md`). Pour un app purement client → Microsoft Graph / Azure Mobile Apps / BaaS via env vars.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application .NET MAUI 10 Multi-platform** cible iOS + Android (Windows + Mac Catalyst en TargetFramework optionnel) :

- **MAUI 10** sur **.NET 10 LTS** — single project multi-target (`net10.0-android;net10.0-ios`).
  .NET 9 est passe en support **maintenance** (cf. §2.3) : ne plus scaffolder de nouveau projet dessus.
- **MVVM source-gen** via **CommunityToolkit.Mvvm 8.4** — `[ObservableProperty]` + `[RelayCommand]` (zero boilerplate, code propre)
- **CommunityToolkit.Maui 11** — Behaviors, Converters, Popups, Snackbar, MediaElement, TouchBehavior — standard de facto
- **DI native MAUI** via `MauiAppBuilder.Services` (Microsoft.Extensions.DependencyInjection)
- **Navigation Shell** (`Microsoft.Maui.Controls.Shell`) ou page-stack `Navigation.PushAsync` selon complexite
- **Storage** : `Microsoft.Maui.Essentials.SecureStorage` (tokens) + `Preferences` (settings)
- **DB locale** : `sqlite-net-pcl` (top-1 SQLite ORM MAUI)
- **HTTP + Refit** : `Microsoft.Extensions.Http.Resilience` + `Refit` (top REST client wrapper typed)

Architecture cible (un seul `.csproj`) :

```
{AppName}/
├── {AppName}.csproj            ── multi-target (net10.0-android;net10.0-ios[;net10.0-maccatalyst;net10.0-windows10.0.19041.0])
├── MauiProgram.cs              ── bootstrap DI + register ViewModels/Services
├── App.xaml(.cs)               ── App entry point
├── AppShell.xaml(.cs)          ── Shell navigation (Tabs + flyout)
├── Pages/                      ── XAML pages
│   ├── LoginPage.xaml(.cs)
│   └── Dashboard/
├── ViewModels/                 ── MVVM ViewModels (CommunityToolkit.Mvvm)
├── Models/                     ── Data classes / DTOs
├── Services/                   ── Logique metier, API clients
├── Repositories/               ── DB locale (sqlite-net-pcl)
├── Converters/                 ── IValueConverter pour bindings
├── Behaviors/                  ── Behaviors XAML custom
├── Resources/
│   ├── Styles/                ── Colors.xaml + Styles.xaml (themes)
│   ├── Images/                ── icons / images multi-resolution
│   ├── Fonts/                 ── *.ttf custom
│   └── Raw/                   ── assets bruts
└── Platforms/
    ├── Android/               ── MainActivity.cs, AndroidManifest.xml
    └── iOS/                   ── AppDelegate.cs, Info.plist
```

**Difference vs `.sdd/stacks/frontend/blazor-webassembly.md`** :
- C# **compile en natif** (AOT iOS, JIT/AOT Android) — pas de WebView, pas de runtime web
- Acces direct APIs natives (`MainActivity.cs` Android, `AppDelegate.cs` iOS) via Platforms/
- XAML declaratif (pas de HTML/CSS)
- Distribution App Store / Play Store (apk/aab/ipa)

---

## 1.2 Couches

- **Pages** (`Pages/*.xaml` + `.xaml.cs`) : UI declarative XAML, code-behind minimal (uniquement event handlers UI purs, jamais de logique metier)
- **ViewModels** (`ViewModels/*ViewModel.cs`) : MVVM avec CommunityToolkit.Mvvm — `[ObservableObject]` / `[ObservableProperty]` / `[RelayCommand]`
- **Services** (`Services/*Service.cs`) : logique metier, contrat dans `Services/I*Service.cs`, impl scoped/singleton via DI
- **Repositories** (`Repositories/*Repository.cs`) : acces DB locale (sqlite-net-pcl) ou cache memoire
- **Models** (`Models/*.cs`) : data classes / DTOs (mappe vers DB entities ou DTOs API)
- **Converters** (`Converters/*Converter.cs`) : `IValueConverter` pour bindings XAML (`{Binding Date, Converter={StaticResource DateConverter}}`)
- **Behaviors** (`Behaviors/*Behavior.cs`) : `BehaviorBase<T>` pour comportements XAML reutilisables
- **Resources** : `Styles.xaml` (theme global), `Colors.xaml` (palette), `AppIcon` + `SplashScreen` config dans csproj

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas a ce stack**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

| Layer | Path |
|---|---|
| Project file | `workspace/src/{AppName}/{AppName}.csproj` |
| App entry | `workspace/src/{AppName}/MauiProgram.cs` |
| Application | `workspace/src/{AppName}/App.xaml` + `App.xaml.cs` |
| Shell | `workspace/src/{AppName}/AppShell.xaml` + `AppShell.xaml.cs` |
| Page | `workspace/src/{AppName}/Pages/{Domain}/{Name}Page.xaml` + `.xaml.cs` |
| Custom Control | `workspace/src/{AppName}/Controls/{Name}.xaml` + `.xaml.cs` |
| ViewModel | `workspace/src/{AppName}/ViewModels/{Domain}/{Name}ViewModel.cs` |
| Service interface | `workspace/src/{AppName}/Services/Interfaces/I{Domain}Service.cs` |
| Service impl | `workspace/src/{AppName}/Services/{Domain}Service.cs` |
| Repository | `workspace/src/{AppName}/Repositories/{Domain}Repository.cs` |
| Model / DTO | `workspace/src/{AppName}/Models/{Name}.cs` |
| Converter | `workspace/src/{AppName}/Converters/{Name}Converter.cs` |
| Behavior | `workspace/src/{AppName}/Behaviors/{Name}Behavior.cs` |
| Resources Styles | `workspace/src/{AppName}/Resources/Styles/Colors.xaml`, `Styles.xaml` |
| Images / Fonts | `workspace/src/{AppName}/Resources/Images/`, `Resources/Fonts/` |
| Localization (.resx) | `workspace/src/{AppName}/Resources/Strings/AppResources.{lang}.resx` |
| Platform Android | `workspace/src/{AppName}/Platforms/Android/` (`MainActivity.cs`, `AndroidManifest.xml`) |
| Platform iOS | `workspace/src/{AppName}/Platforms/iOS/` (`AppDelegate.cs`, `Info.plist`) |
| Config app | `workspace/src/{AppName}/appsettings.json` (peuple par arch — backend URL, JWT issuer, etc.) |

---

## 1.4 Principes non negociables

**Architecture MVVM strict** :
- **Aucune logique metier dans code-behind XAML** (`.xaml.cs`) — uniquement event handlers UI purs (`OnAppearing`, animations). Toute logique = ViewModel.
- **MVVM via source-gen `CommunityToolkit.Mvvm`** — pas de `INotifyPropertyChanged` manuel, pas de `RelayCommand` manuel. Annotations `[ObservableProperty]` + `[RelayCommand]` obligatoires.
- **DI systematique** via `MauiAppBuilder.Services.AddScoped/Singleton/Transient`. Constructor injection sur les ViewModels et Services. Pas de Service Locator. Pas de singleton statique.
- **ViewModels enregistrees Transient** (un par Page) — sauf `MainViewModel` qui peut etre Singleton si etat global
- **Services enregistres Singleton** (HttpClient, AuthService, DatabaseService)
- **Bindings explicites** via `x:DataType` (Compiled Bindings) — JAMAIS de binding non-typed (slow, runtime errors silencieux)
- **Async/await partout** sur les operations I/O — pas de `.Wait()`, pas de `.Result` (deadlock UI thread)
- **TargetFramework `net10.0-android` + `net10.0-ios`** par defaut. macOS + Windows en TargetFrameworks optionnels (capability `desktop-targets`)

**SOLID / Clean Code** : meme rigueur que `.sdd/stacks/fullstack/blazor-server.md §1.5` (heritage .NET).

**Performance mobile** :
- **`CollectionView`** plutot que `ListView` (deprecated en MAUI) — `CollectionView` est virtualise natif
- **`{x:Bind}` ou `x:DataType`** pour Compiled Bindings — sinon reflection runtime (slow)
- **Images `.svg` interdites** sans conversion — MAUI ne supporte pas SVG natif, utiliser **`MauiAsset` PNG multi-resolution** ou `SkiaSharp` pour vector
- **Pas de `Task.Run` sur UI thread main** — utiliser `MainThread.InvokeOnMainThreadAsync` pour update UI depuis worker thread

**Securite mobile-specific** :
- **Tokens JWT / OAuth** dans `SecureStorage` (Keychain iOS, Android Keystore) — JAMAIS dans `Preferences`
- **Pas de secret client-side** — utiliser backend proxy
- **Permissions runtime** demandees juste-a-temps (`Permissions.RequestAsync<Permissions.Camera>()`) — pas au demarrage
- **Certificate pinning** pour apps sensibles — via `HttpClientHandler.ServerCertificateCustomValidationCallback` (handler natif par plateforme). **Aucun paquet NuGet** : cf. §2.3, la capability `cert-pinning` du catalog pointait vers un paquet inexistant
- **Deep links signes** : Universal Links iOS (apple-app-site-association) / App Links Android (assetlinks.json) — pas de scheme custom seul (hijackable)

---

## 1.5 Couches persistantes (locales)

Ce stack est CLIENT mobile — la persistance "DB" reelle vit cote backend. Options locales :

| Type | Lib | Cas d'usage |
|---|---|---|
| Cle-valeur non sensible | `Microsoft.Maui.Storage.Preferences` (built-in Essentials) | Preferences UI, last screen |
| Cle-valeur sensible | `Microsoft.Maui.Storage.SecureStorage` (built-in Essentials) | Tokens JWT, credentials, PIN |
| DB SQLite locale | `sqlite-net-pcl` (top-1, simple) | Offline-first, gros datasets, queries SQL |
| DB SQLite EF Core | `Microsoft.EntityFrameworkCore.Sqlite` (capability `ef-sqlite`) | Si equipe deja sur EF Core / migrations |
| Cache HTTP | `MonkeyCache.LiteDB` (capability `monkeycache`) | Cache API responses cote client |
| File system | `Microsoft.Maui.Storage.FileSystem` (built-in) | Fichiers app data (e.g. downloads) |

**Mode par defaut** : SecureStorage + Preferences + sqlite-net-pcl. Suffisant pour 90% des apps.

---

## 1.6 Cible plateformes — matrice de decision

| Plateforme | TargetFramework | Par defaut |
|---|---|---|
| Android | `net10.0-android` | ✅ |
| iOS | `net10.0-ios` | ✅ |
| Mac Catalyst | `net10.0-maccatalyst` | ❌ (capability `desktop-targets`) |
| Windows | `net10.0-windows10.0.19041.0` | ❌ (capability `desktop-targets`) |

Single-target Android-only ou iOS-only → utiliser **Xamarin classic-style** = mauvais choix (deprecated 2024). Pour single-platform natif, preferer SwiftUI (iOS) ou Jetpack Compose (Android) direct.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-maui`
- **Langage** : C# 13
- **Runtime** : .NET 10 LTS (`net10.0-android36.0` + `net10.0-ios26.0`)
- **Framework** : .NET MAUI 10.0 (`Microsoft.Maui.Controls` 10.0.100)
- **MVVM** : CommunityToolkit.Mvvm 8.4 (source-gen)
- **UI Toolkit** : CommunityToolkit.Maui 11.0 (Behaviors, Converters, Popup, Snackbar, MediaElement)
- **Plateformes** : iOS 15.0+ / Android API 24+ (Android 7.0)
- **Namespace** : `{AppNamespace}`

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/{AppName}.csproj`
- **Build** : `dotnet build workspace/src/{AppName}/{AppName}.csproj -f net10.0-android --nologo` (build per-TargetFramework — sur Mac requis pour iOS)
- **Run Android (emulateur ouvert)** : `dotnet build -t:Run -f net10.0-android workspace/src/{AppName}/{AppName}.csproj`
- **Run iOS (simulateur — macOS uniquement)** : `dotnet build -t:Run -f net10.0-ios workspace/src/{AppName}/{AppName}.csproj`
- **Publish Android APK/AAB** : `dotnet publish -f net10.0-android -c Release -p:AndroidPackageFormat=apk` (ou `aab` pour Play Store)
- **Publish iOS IPA** : `dotnet publish -f net10.0-ios -c Release -p:ArchiveOnBuild=true` (macOS + Apple Developer certificate)
- **Smoke Command** :

```bash
dotnet restore workspace/src/{AppName}/{AppName}.csproj
dotnet build workspace/src/{AppName}/{AppName}.csproj -f net10.0-android --nologo --no-restore
test -d workspace/src/{AppName}/bin/Debug/net10.0-android
```

- **Smoke Timeout** : 300s (premiere build MAUI ~3-4min, incrementale ~30s)
- **Package manager** : NuGet
- **Type-check** : integre au build (Roslyn)
- **Lint / Format** : `dotnet format`

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/{AppName}.csproj" ]; then

# Pre-requis (verifies par arch en STEP 0) :
# - dotnet workload list | grep -q maui  (sinon : dotnet workload install maui)

# STEP 1 — Scaffold projet MAUI
mkdir -p workspace/src/{AppName}
dotnet new maui -n {AppName} -o workspace/src/{AppName} --framework net10.0 --force

# STEP 2 — Retarget TargetFrameworks (par defaut maui template inclut Windows + Mac que SDD_Pro skip)
# Edit {AppName}.csproj : <TargetFrameworks>net10.0-android;net10.0-ios</TargetFrameworks> (retirer maccatalyst + windows si non desires)
# Cet edit passe par Read+Edit du csproj (pattern Blazor Server §2.2.1) — pas via sed/rm bash.

# STEP 3 — Ajouter packages CORE (cf. §2.4)
cd workspace/src/{AppName}

dotnet add package CommunityToolkit.Mvvm --version 8.4.0
dotnet add package CommunityToolkit.Maui --version 11.0.0
dotnet add package CommunityToolkit.Maui.Markup --version 5.1.0
dotnet add package sqlite-net-pcl --version 1.9.172
dotnet add package SQLitePCLRaw.bundle_green --version 2.1.10
dotnet add package Microsoft.Extensions.Http --version 9.0.0
dotnet add package Microsoft.Extensions.Http.Resilience --version 9.0.0
dotnet add package Refit --version 8.0.0
dotnet add package Refit.HttpClientFactory --version 8.0.0
dotnet add package FluentValidation --version 11.10.0
dotnet add package Serilog.Extensions.Logging --version 9.0.0
dotnet add package Serilog.Sinks.Debug --version 3.0.0

# STEP 4 — Patch MauiProgram.cs (ajouter .UseMauiCommunityToolkit() + register services scaffold)
# (Edit via Read+Edit, pas via sed)

# STEP 5 — Creer arborescence applicative
mkdir -p \
  Pages \
  ViewModels \
  Models \
  Services/Interfaces \
  Repositories \
  Converters \
  Behaviors \
  Controls \
  Resources/Strings

# STEP 6 — Bootstrap appsettings.json (peuple par arch depuis stack.md)
cat > appsettings.json <<'JSON'
{
  "Api": {
    "BaseUrl": "(injectee par arch depuis ## Active Mobile Config)"
  },
  "Auth": {
    "Issuer": "(injectee par arch depuis ## Active Auth Specs)",
    "Audience": "(injectee par arch)"
  }
}
JSON

# Marquer comme MauiAsset pour qu'il soit packagé dans l'app bundle
# (Add <ItemGroup><MauiAsset Include="appsettings.json" /></ItemGroup> dans csproj — via Edit)

# STEP 7 — Restore + build sanity check
dotnet restore {AppName}.csproj
dotnet build {AppName}.csproj -f net10.0-android --nologo --no-restore || true

fi
```

---

## 2.3 Cible .NET et references NuGet (audit 2026-09-02)

### Pourquoi net10.0

| Channel | Etat support Microsoft | Verdict SDD_Pro |
|---|---|---|
| `net10.0` | **LTS — active** (runtime 10.0.11, SDK 10.0.400) | **cible du stack** |
| `net9.0` | STS — *maintenance* | ne plus scaffolder ; migration attendue |
| `net8.0` | LTS — *maintenance* | rejete par le template `dotnet new maui` (bench 2026-06-05) |
| `net11.0` | preview | interdit (cf. §5) |

Suffixes de plateforme retenus, alignes sur ceux publies par
`CommunityToolkit.Maui` 15.0.1 (paquet de reference du stack) :
`net10.0-android36.0`, `net10.0-ios26.0`, `net10.0-maccatalyst26.0`,
`net10.0-windows10.0.19041.0`.

### References NuGet corrigees

Trois entrees du catalog pointaient vers des paquets ou des versions qui
**n'existent pas sur nuget.org** — toute US declenchant la capability
concernee echouait au `dotnet restore` :

| Capability | Entree fautive | Realite nuget.org | Correction |
|---|---|---|---|
| `cert-pinning` | `Plugin.MauiCertPinning` 1.0.0 | **le paquet n'existe pas** (404) | Capability **supprimee** du catalog. Le pinning se fait sans dependance, via `HttpClientHandler.ServerCertificateCustomValidationCallback` par plateforme (cf. §1.4) |
| `biometric` | `Plugin.Fingerprint` 3.0.0 | derniere stable **2.1.5** ; la 3.0.0 n'existe qu'en `3.0.0-beta.1` | pin sur `2.1.5` |
| `in-app-rating` | `Plugin.Maui.AppRating` 2.0.0 | derniere publiee **1.3.0** | pin sur `1.3.0` |

Corrige aussi au meme passage :

- `LiveChartsCore.SkiaSharpView.Maui` : `2.0.0-rc4.1` → **`2.0.5`**, premiere
  release stable. C'etait le dernier `PRERELEASE` signale par
  `validate_libs_catalog.py` sur ce stack.
- `Sentry.Maui` : `5.3.0` → **`6.9.0`**. nuget.org expose egalement un
  `14.12.1-dump1` qui n'est pas une release Sentry — ne pas le prendre pour
  la derniere version.
- Ajout en CORE de `Microsoft.Extensions.Configuration.Json` : le manifest
  declarait `appsettings.json` et le STEP 6 de §2.2.1 le genere, mais aucun
  paquet ne savait le **lire**.
- Ajout de la capability `maui-unit-tests` (xUnit + NSubstitute + Shouldly) :
  le stack n'avait aucun moyen declare de tester ses ViewModels.

> `Plugin.Firebase` 4.2.1 ne publie que des assets `net9.0-*`. Il reste
> consommable depuis un projet `net10.0-*` par compatibilite NuGet, mais
> emet un warning de restore. Si l'US n'a besoin que de notifications
> locales, preferer la capability `local-notification`.

---


<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/maui.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id maui`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| CommunityToolkit.Mvvm | 8.4.2 | Source-gen MVVM (ObservableProperty + RelayCommand) — top-1 standard |
| CommunityToolkit.Maui | 15.0.1 | Toolkit officiel communautaire — Behaviors, Converters, Popup, Snackbar, MediaElement. Sert de reference d'alignement net10 pour ce stack |
| CommunityToolkit.Maui.Markup | 8.0.0 | Fluent C# markup (alternative XAML) |
| sqlite-net-pcl | 1.11.285 | ORM SQLite local — top-1 standard de facto MAUI |
| SQLitePCLRaw.bundle_green | 2.1.11 | Bundle SQLite native (peer sqlite-net-pcl) |
| Microsoft.Extensions.Http | 10.0.11 | HttpClientFactory DI-friendly |
| Microsoft.Extensions.Http.Resilience | 10.9.0 | Retry / circuit breaker / timeout (succede a Polly direct en .NET 8+) |
| Microsoft.Extensions.Options | 10.0.11 | Binding fortement type de appsettings.json vers des records d'options (IOptions<T>) |
| Microsoft.Extensions.Configuration.Json | 10.0.11 | Lecture de appsettings.json declare au manifest — sans ce paquet la config n'est pas chargee |
| Microsoft.Extensions.Logging.Debug | 10.0.11 | Provider ILogger vers la fenetre Debug de l'IDE |
| Refit | 15.2.0 | REST client typed — top-1 wrapper HttpClient C# |
| Refit.HttpClientFactory | 15.2.0 | Integration Refit + DI HttpClientFactory |
| FluentValidation | 12.1.1 | Validation forms / models |
| Serilog.Extensions.Logging | 10.0.0 | Logger structure (peer ILogger<T>) |
| Serilog.Sinks.Debug | 3.0.0 | Sink Debug (console IDE pendant dev) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| ef-sqlite | Microsoft.EntityFrameworkCore.Sqlite (alt) | 10.0.11 | ef-core, entity.*framework, ef-sqlite |
| msal | Microsoft.Identity.Client | 4.88.0 | msal, azure-ad, entra, auth-azure-ad, sso |
| charts | LiveChartsCore.SkiaSharpView.Maui | 2.0.5 | chart, graph, visualisation, courbe |
| charts | Microcharts.Maui (alt) | 2.0.0.3 | microcharts, chart.*simple |
| skia | SkiaSharp.Views.Maui.Controls | 4.151.1 | skia, dessin.*custom, canvas |
| barcode | ZXing.Net.Maui.Controls | 0.10.4 | barcode, qr.*code, scan.*qr |
| firebase-push | Plugin.Firebase | 4.2.1 | firebase, push.*notification, fcm, notification.*distante |
| local-notification | Plugin.LocalNotification | 14.1.1 | notification.*locale, rappel, reminder, notification.*planifiee |
| audio | Plugin.Maui.Audio | 4.0.0 | audio, lecture.*son, enregistrement.*audio |
| biometric | Plugin.Fingerprint | 2.1.5 | biometric, fingerprint, face-id, touch-id |
| in-app-rating | Plugin.Maui.AppRating | 1.3.0 | rating, app-store-rating, demande.*review |
| in-app-billing | Plugin.InAppBilling | 10.0.0 | in-app-purchase, abonnement, billing |
| maps | Microsoft.Maui.Controls.Maps | 10.0.100 | maps, carte, marker |
| stripe | Stripe.net | 52.4.1 | stripe, paiement, payment |
| sentry | Sentry.Maui | 6.9.0 | sentry, error.*tracking, monitoring.*erreurs |
| localization | Microsoft.Extensions.Localization | 10.0.11 | i18n, localization, multi.*langue |
| maui-unit-tests | xunit | 2.9.3 | tests.*unitaires, xunit, viewmodel.*test |
| maui-unit-tests | xunit.runner.visualstudio | 4.0.0 | tests.*unitaires, xunit |
| maui-unit-tests | Microsoft.NET.Test.Sdk | 18.9.0 | tests.*unitaires, xunit |
| maui-unit-tests | NSubstitute | 6.2.0 | mock, stub, substitute, tests.*unitaires |
| maui-unit-tests | Shouldly (alt) | 4.3.0 | assertions, should, tests.*unitaires |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — verifies par dev-* STEP 5.0. Toute violation = ERROR.

| Role | Pattern | Exemple |
|------|---------|---------|
| Page | `{Name}Page.xaml` + `.xaml.cs` (PascalCase) | `LoginPage.xaml`, `DashboardPage.xaml` |
| ViewModel | `{Name}ViewModel.cs` heritant `ObservableObject` (CommunityToolkit.Mvvm) | `LoginViewModel`, `DashboardViewModel` |
| Service interface | `I{Domain}Service.cs` | `IAuthService.cs` |
| Service impl | `{Domain}Service.cs` implementant `I{Domain}Service` | `AuthService.cs` |
| Repository | `{Domain}Repository.cs` (DB locale ou cache) | `UserRepository.cs` |
| Model | `{Name}.cs` (data class, jamais suffixe Dto) | `User.cs`, `Booking.cs` |
| Converter | `{Name}Converter.cs` implementant `IValueConverter` | `DateToStringConverter.cs` |
| Behavior | `{Name}Behavior.cs` heritant `Behavior<T>` | `MaxLengthBehavior.cs` |
| Custom Control | `{Name}.xaml` + `.xaml.cs` | `RatingStars.xaml` |
| API client (Refit) | `I{Domain}Api.cs` (interface annotee `[Get("...")]`) | `IUsersApi.cs` |

**Suffixes INTERDITS** :
- `Dto`, `InputDto`, `OutputDto`, `Request`, `Response`, `Result` — utiliser `Model` ou nom du domaine
- `Manager`, `Helper`, `Util` (sauf `Helpers/` strict pour pure static methods)
- `Impl` postfix sur l'interface (l'interface n'a pas de suffixe ; l'implementation l'a)

**Conventions de fichier** :
- C# : `PascalCase.cs`
- XAML : `PascalCase.xaml` + co-located `PascalCase.xaml.cs` (code-behind partial class)
- Resources XAML : `PascalCase.xaml` dans `Resources/Styles/`

---

## 3. Endpoints standard (cote backend separe)

Comme `react-native.md §3`, ce stack consomme un backend distinct. Les endpoints minimaux attendus cote backend :

| Endpoint backend | Role |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` ou `/api/auth/[...]` | flow auth |
| `GET /api/me` | user courant |

Cote app : **base URL** dans `appsettings.json` (`Api:BaseUrl`), peuple par arch depuis nouvelle section `## Active Mobile Config` du `stack.md` (convention `MOBILE_API_BASE_URL`).

---

## 4. Versioning des API consommees

Le backend expose `/api/v1/{domain}`. Cote MAUI : maintenir une **MinSupportedApiVersion** dans `appsettings.json` (`Api:MinVersion`). A chaque release mobile, valider que le backend deploye supporte cette version.

---

## 5. Interdits projet (maui)

**Architecture** :
- Logique metier dans code-behind XAML (`.xaml.cs`) — toujours ViewModel
- Acces direct DB ou HttpClient depuis ViewModel — toujours via Service injecte
- Mapping manuel dans ViewModel/Service — utiliser AutoMapper (capability) ou extension methods statiques
- `INotifyPropertyChanged` manuel ou `RelayCommand` ecrit a la main — toujours via CommunityToolkit.Mvvm source-gen
- `Application.Current.MainPage = new XPage()` partout — utiliser **Shell** (`AppShell.xaml`) avec `Shell.Current.GoToAsync("//route")`
- `Binding` sans `x:DataType` (Compiled Bindings) — sinon reflection runtime, slow, runtime errors silencieux
- `Task.Run` sur UI thread main — utiliser `MainThread.InvokeOnMainThreadAsync` pour update UI depuis worker
- `.Wait()` / `.Result` sur Task — deadlock UI thread garanti
- `ListView` (deprecated MAUI) — utiliser `CollectionView`
- Image SVG directement dans `<Image Source="...svg" />` — MAUI ne supporte pas SVG natif. Utiliser **`MauiImage`** (PNG multi-resolution) ou **SkiaSharp** pour vector dynamique

**Code quality** :
- `Console.WriteLine` → utiliser `ILogger<T>` injecte
- `async void` sauf event handlers UI (`Button_Clicked`)
- Methodes > 30 lignes — decomposer
- `dynamic` injustifie
- Imports stars `using System.*;` — toujours explicites
- `TODO`, `FIXME`, code commente

**Securite** :
- Token JWT dans `Preferences` (non chiffre) — toujours `SecureStorage`
- Secret hardcode dans `appsettings.json` versionne — utiliser `MauiAsset` + env vars + arch injection
- API key Stripe/Firebase secret cote client — toujours via backend proxy
- Cookies / WebView sans flags secure / sameSite
- Certificate pinning desactive sur app bancaire/sensible

**XAML** :
- `BindingContext` set en code-behind plutot que via DI Shell ou `<ContentPage.BindingContext>` direct
- Styles inline non extraits dans `Styles.xaml`
- Hardcoded colors `Color="#FF0000"` — utiliser ressources `StaticResource Primary`
- Iteration profonde `<CollectionView>` dans `<ScrollView>` — antipattern (double scroll, perf degradee)
- `ItemsSource` lie a une grosse collection non-virtualisee — utiliser `ObservableCollection<T>` + `CollectionView` (virtualise natif)

**Build / packaging** :
- Engager `bin/`, `obj/`, `*.user`, `.vs/` dans git
- Permissions excessives dans `Platforms/Android/AndroidManifest.xml` ou `Platforms/iOS/Info.plist` — demander juste-a-temps via `Permissions.RequestAsync<T>()`
- Pas de signed APK/AAB pour Play Store (build Release sans keystore)
- Pas de provisioning profile valide pour iOS App Store
- `<UseMaui>true</UseMaui>` absent du csproj
- Mix `TargetFramework` + `TargetFrameworks` (utiliser uniquement le plural)
- Cibler un TFM en **preview** (`net11.0-*`) — SDD_Pro ne scaffolde que sur un channel LTS `active` (cf. §2.3)
- Cibler `net9.0-*` sur un nouveau projet — channel passe en *maintenance* (cf. §2.3)
- Referencer un paquet NuGet sans avoir verifie qu'il existe et que la version est publiee : `Plugin.MauiCertPinning`, `Plugin.Fingerprint 3.0.0` et `Plugin.Maui.AppRating 2.0.0` etaient dans ce catalog et faisaient echouer `dotnet restore` (audit 2026-09-02)

---

## 6. Persistance locale — voir §1.5

Stack mobile → pas de "DB scaffolding" backend classique. Pour offline-first reel : capability `ef-sqlite` (EF Core Sqlite) ou sqlite-net-pcl (defaut CORE).

---

## 7. Temps reel

- **SignalR client** : `Microsoft.AspNetCore.SignalR.Client` (capability `signalr-client`) — connexion temps reel a un Hub backend ASP.NET Core
- **SSE** : pas natif, utiliser `HttpClient` + `Stream` reading (capability `sse-client`)
- **Push notifications** : `Plugin.Firebase` (capability `firebase-push`) — FCM Android + APNS iOS via Firebase

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Equipes .NET** qui veulent reutiliser leurs competences C# / XAML sur mobile
- **Apps internes d'entreprise** distribuees via MDM / Intune avec auth Azure AD
- **Apps cross-platform** ou Microsoft Stack (Outlook, Teams, Office 365) est central
- **Migrations depuis Xamarin.Forms** (MAUI = successeur direct)
- **Apps avec acces APIs Microsoft Graph** intensives

**NE PAS choisir si** :
- ❌ Equipe React / JavaScript — courbe d'apprentissage C# + XAML + MAUI specifics > React Native pour eux → `react-native.md`
- ❌ App avec performance graphique extreme (jeux 60fps, AR/VR) → Unity / Unreal / natif
- ❌ App single-platform optimale (UI extremement plateforme-specifique) → SwiftUI ou Jetpack Compose
- ❌ Budget tres serre pour iOS (Mac obligatoire pour build iOS) — RN/Expo offre EAS Build cloud
- ❌ Hot reload tres frequent en dev → `dotnet watch` XAML existe mais moins fluide que Metro/Fast Refresh RN
- ❌ Distribution OTA frequente (mises a jour quotidiennes UI sans rebuild store) → RN/Expo + EAS Update fait mieux

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `mobile-maui` + `auth-azure-ad` (MSAL) + backend `dotnet-minimalapi` + `qa-dotnet-xunit` (services) | 🟡 experimental | jamais valide end-to-end |
| `mobile-maui` + `auth-local` (JWT) + backend `node-express` + `qa-dotnet-xunit` | 🟡 experimental | viable, Refit + JWT mature |
| `mobile-maui` + Firebase Auth (capability `firebase-auth`) + backend Firebase / FaaS | 🟡 experimental | proto BaaS-style |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` contient `mobiles/maui.md` → reconnaitre comme stack **mobile-only**
2. **Le backend reste declare separement** dans `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`) — co-existent sous `workspace/src/`
3. **Pre-requis** : verifier `dotnet workload list` contient `maui`. Sinon : `dotnet workload install maui` (peut prendre 5-10min). Sur macOS : XCode + Apple Developer (free pour simulateur, payant pour TestFlight/App Store). Sur Linux : iOS impossible (build iOS exige Mac).
4. **Creer** `workspace/src/{AppName}/` via `dotnet new maui` (cf. §2.2.1)
5. **Composer** `appsettings.json` (MauiAsset) depuis `## Active Mobile Config` (`MOBILE_API_BASE_URL`) + `## Active Auth Specs`. **JAMAIS** ecrire les secrets en clair — utiliser plutot SecureStorage runtime + injection a la premiere connexion.
6. **`## Active UI Specs`** : aucun design system web n'est compatible (`shadcn`/`vuetify`/`radzen-blazor` → WARNING bloquant). MAUI utilise son propre theming via `Resources/Styles/`. Alternative : capability `syncfusion-maui` (suite Syncfusion commerciale).
7. **Phase B (DB)** : SKIP — pas de DB serveur. Si `ef-sqlite` capability → tables EF Core locale generees au premier run via `db.EnsureCreatedAsync()`.
8. **Phase C (ADRs)** : creer `ADR-{ts}-stack-mobile-maui.md` documentant .NET 10 LTS + MAUI 10 + CommunityToolkit 15 + sqlite-net-pcl

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de "backend interne". Convention :

- `dev-backend` **ne touche pas** au projet MAUI — il code le backend separe declare dans `## Active Tech Specs backend/*`
- `dev-frontend` materialise **tout** le projet MAUI : Pages, ViewModels, Services, Repositories, Models, Converters, Behaviors, Resources, Platforms

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/Pages/**` | `dev-frontend` |
| `workspace/src/{AppName}/ViewModels/**` | `dev-frontend` |
| `workspace/src/{AppName}/Services/**` | `dev-frontend` (toute la logique vit dans le projet MAUI) |
| `workspace/src/{AppName}/Repositories/**` | `dev-frontend` (DB locale) |
| `workspace/src/{AppName}/Models/**` | `dev-frontend` |
| `workspace/src/{AppName}/Converters/**` | `dev-frontend` |
| `workspace/src/{AppName}/Behaviors/**` | `dev-frontend` |
| `workspace/src/{AppName}/Controls/**` | `dev-frontend` |
| `workspace/src/{AppName}/Resources/**` | `dev-frontend` |
| `workspace/src/{AppName}/Platforms/**` | `arch` (create) + `dev-frontend` (augment permissions / manifest entries) |
| `workspace/src/{AppName}/MauiProgram.cs` | `arch` (create) + `dev-frontend` (augment services DI) |
| `workspace/src/{AppName}/App.xaml(.cs)` / `AppShell.xaml(.cs)` | `arch` (create) + `dev-frontend` (augment routes Shell) |
| `workspace/src/{AppName}/{AppName}.csproj` | `arch` (create) + `dev-frontend` (augment NuGet packages on-demand) |
| `workspace/src/{AppName}/appsettings.json` | `arch` (create exclusif — config) |

**Backend separe** : meme matrice ownership que pour son propre stack. Les 2 projets co-existent sous `workspace/src/{BackendName}/` et `workspace/src/{AppName}/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}
dotnet restore {AppName}.csproj
dotnet build {AppName}.csproj -f net10.0-android --nologo --no-restore
test -f MauiProgram.cs
test -f App.xaml
test -f AppShell.xaml
test -f appsettings.json
test -d Platforms/Android
test -d Platforms/iOS
grep -q "<UseMaui>true</UseMaui>" {AppName}.csproj
grep -q "CommunityToolkit.Mvvm" {AppName}.csproj
grep -q "CommunityToolkit.Maui" {AppName}.csproj
grep -q "sqlite-net-pcl" {AppName}.csproj
echo "smoke OK"
```

Smoke complet (~300s premiere build) : `dotnet build -f net10.0-android` doit produire `bin/Debug/net10.0-android/{AppName}.dll` + `.apk` debug. Run optionnel via Android Studio AVD ou `dotnet build -t:Run -f net10.0-android` apres avoir demarre un emulateur.
