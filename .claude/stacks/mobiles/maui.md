# Tech FEAT: maui (mobile)

> §2.4 (Librairies) regeneree depuis `maui.libs.json` — ne pas editer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id maui`).

Status: Experimental
Validation: 🟢 bench-validated runtime — Windows desktop (2026-06-05 — CalcABCMaui, MAUI workloads installés, cible `net9.0-windows10.0.19041.0` WinUI3, build 5.88s 0 err 4 warn (Frame obsolète), fenêtre WinUI3 PID 15972 246MB lancée, HttpClient → FastAPI :44329, AC-1/2/3 🟢. Cibles iOS/Android/macOS non testées sans toolchain. Bug fix : `-f net8.0` rejeté par template SDK 10 → `-f net9.0`. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-maui
Scope: **mobile cross-platform** — application **.NET MAUI 9** (Multi-platform App UI) dans UN seul projet `{AppName}/`. Single codebase C# / XAML qui cible iOS + Android (+ macOS Catalyst + Windows en option). UI MAUI + MVVM + acces APIs natives + auth vivent dans le meme `.csproj`. Pas de separation `{BackendName}` / `{LibName}`.

> **Backend separe** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte declaree en `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`, `backend/node-express.md`). Pour un app purement client → Microsoft Graph / Azure Mobile Apps / BaaS via env vars.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application .NET MAUI 9 Multi-platform** cible iOS + Android (Windows + Mac Catalyst en TargetFramework optionnel) :

- **MAUI 9** sur **.NET 9 LTS** — single project multi-target (`net9.0-android;net9.0-ios`)
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
├── {AppName}.csproj            ── multi-target (net9.0-android;net9.0-ios[;net9.0-maccatalyst;net9.0-windows10.0.19041.0])
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

**Difference vs `.claude/stacks/frontend/blazor-webassembly.md`** :
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

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas a ce stack**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

| Layer | Path |
|---|---|
| Project file | `workspace/output/src/{AppName}/{AppName}.csproj` |
| App entry | `workspace/output/src/{AppName}/MauiProgram.cs` |
| Application | `workspace/output/src/{AppName}/App.xaml` + `App.xaml.cs` |
| Shell | `workspace/output/src/{AppName}/AppShell.xaml` + `AppShell.xaml.cs` |
| Page | `workspace/output/src/{AppName}/Pages/{Domain}/{Name}Page.xaml` + `.xaml.cs` |
| Custom Control | `workspace/output/src/{AppName}/Controls/{Name}.xaml` + `.xaml.cs` |
| ViewModel | `workspace/output/src/{AppName}/ViewModels/{Domain}/{Name}ViewModel.cs` |
| Service interface | `workspace/output/src/{AppName}/Services/Interfaces/I{Domain}Service.cs` |
| Service impl | `workspace/output/src/{AppName}/Services/{Domain}Service.cs` |
| Repository | `workspace/output/src/{AppName}/Repositories/{Domain}Repository.cs` |
| Model / DTO | `workspace/output/src/{AppName}/Models/{Name}.cs` |
| Converter | `workspace/output/src/{AppName}/Converters/{Name}Converter.cs` |
| Behavior | `workspace/output/src/{AppName}/Behaviors/{Name}Behavior.cs` |
| Resources Styles | `workspace/output/src/{AppName}/Resources/Styles/Colors.xaml`, `Styles.xaml` |
| Images / Fonts | `workspace/output/src/{AppName}/Resources/Images/`, `Resources/Fonts/` |
| Localization (.resx) | `workspace/output/src/{AppName}/Resources/Strings/AppResources.{lang}.resx` |
| Platform Android | `workspace/output/src/{AppName}/Platforms/Android/` (`MainActivity.cs`, `AndroidManifest.xml`) |
| Platform iOS | `workspace/output/src/{AppName}/Platforms/iOS/` (`AppDelegate.cs`, `Info.plist`) |
| Config app | `workspace/output/src/{AppName}/appsettings.json` (peuple par arch — backend URL, JWT issuer, etc.) |

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
- **TargetFramework `net9.0-android` + `net9.0-ios`** par defaut. macOS + Windows en TargetFrameworks optionnels (capability `desktop-targets`)

**SOLID / Clean Code** : meme rigueur que `.claude/stacks/fullstack/blazor-server.md §1.5` (heritage .NET).

**Performance mobile** :
- **`CollectionView`** plutot que `ListView` (deprecated en MAUI) — `CollectionView` est virtualise natif
- **`{x:Bind}` ou `x:DataType`** pour Compiled Bindings — sinon reflection runtime (slow)
- **Images `.svg` interdites** sans conversion — MAUI ne supporte pas SVG natif, utiliser **`MauiAsset` PNG multi-resolution** ou `SkiaSharp` pour vector
- **Pas de `Task.Run` sur UI thread main** — utiliser `MainThread.InvokeOnMainThreadAsync` pour update UI depuis worker thread

**Securite mobile-specific** :
- **Tokens JWT / OAuth** dans `SecureStorage` (Keychain iOS, Android Keystore) — JAMAIS dans `Preferences`
- **Pas de secret client-side** — utiliser backend proxy
- **Permissions runtime** demandees juste-a-temps (`Permissions.RequestAsync<Permissions.Camera>()`) — pas au demarrage
- **Certificate pinning** (capability `cert-pinning`) pour apps sensibles
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
| Android | `net9.0-android` | ✅ |
| iOS | `net9.0-ios` | ✅ |
| Mac Catalyst | `net9.0-maccatalyst` | ❌ (capability `desktop-targets`) |
| Windows | `net9.0-windows10.0.19041.0` | ❌ (capability `desktop-targets`) |

Single-target Android-only ou iOS-only → utiliser **Xamarin classic-style** = mauvais choix (deprecated 2024). Pour single-platform natif, preferer SwiftUI (iOS) ou Jetpack Compose (Android) direct.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-maui`
- **Langage** : C# 13
- **Runtime** : .NET 9 LTS (`net9.0-android` + `net9.0-ios`)
- **Framework** : .NET MAUI 9.0
- **MVVM** : CommunityToolkit.Mvvm 8.4 (source-gen)
- **UI Toolkit** : CommunityToolkit.Maui 11.0 (Behaviors, Converters, Popup, Snackbar, MediaElement)
- **Plateformes** : iOS 15.0+ / Android API 24+ (Android 7.0)
- **Namespace** : `{AppNamespace}`

---

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/{AppName}.csproj`
- **Build** : `dotnet build workspace/output/src/{AppName}/{AppName}.csproj -f net9.0-android --nologo` (build per-TargetFramework — sur Mac requis pour iOS)
- **Run Android (emulateur ouvert)** : `dotnet build -t:Run -f net9.0-android workspace/output/src/{AppName}/{AppName}.csproj`
- **Run iOS (simulateur — macOS uniquement)** : `dotnet build -t:Run -f net9.0-ios workspace/output/src/{AppName}/{AppName}.csproj`
- **Publish Android APK/AAB** : `dotnet publish -f net9.0-android -c Release -p:AndroidPackageFormat=apk` (ou `aab` pour Play Store)
- **Publish iOS IPA** : `dotnet publish -f net9.0-ios -c Release -p:ArchiveOnBuild=true` (macOS + Apple Developer certificate)
- **Smoke Command** :

```bash
dotnet restore workspace/output/src/{AppName}/{AppName}.csproj
dotnet build workspace/output/src/{AppName}/{AppName}.csproj -f net9.0-android --nologo --no-restore
test -d workspace/output/src/{AppName}/bin/Debug/net9.0-android
```

- **Smoke Timeout** : 300s (premiere build MAUI ~3-4min, incrementale ~30s)
- **Package manager** : NuGet
- **Type-check** : integre au build (Roslyn)
- **Lint / Format** : `dotnet format`

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/output/src/{AppName}/{AppName}.csproj" ]; then

# Pre-requis (verifies par arch en STEP 0) :
# - dotnet workload list | grep -q maui  (sinon : dotnet workload install maui)

# STEP 1 — Scaffold projet MAUI
mkdir -p workspace/output/src/{AppName}
dotnet new maui -n {AppName} -o workspace/output/src/{AppName} --framework net9.0 --force

# STEP 2 — Retarget TargetFrameworks (par defaut maui template inclut Windows + Mac que SDD_Pro skip)
# Edit {AppName}.csproj : <TargetFrameworks>net9.0-android;net9.0-ios</TargetFrameworks> (retirer maccatalyst + windows si non desires)
# Cet edit passe par Read+Edit du csproj (pattern Blazor Server §2.2.1) — pas via sed/rm bash.

# STEP 3 — Ajouter packages CORE (cf. §2.4)
cd workspace/output/src/{AppName}

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
dotnet build {AppName}.csproj -f net9.0-android --nologo --no-restore || true

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/mobiles/maui.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id maui`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| CommunityToolkit.Mvvm | 8.4.0 | Source-gen MVVM (ObservableProperty + RelayCommand) — top-1 standard 2024-2025 |
| CommunityToolkit.Maui | 11.0.0 | Toolkit officiel communautaire — Behaviors, Converters, Popup, Snackbar, MediaElement |
| CommunityToolkit.Maui.Markup | 5.1.0 | Fluent C# markup (alternative XAML) |
| sqlite-net-pcl | 1.9.172 | ORM SQLite local — top-1 standard de facto MAUI |
| SQLitePCLRaw.bundle_green | 2.1.10 | Bundle SQLite native (peer sqlite-net-pcl) |
| Microsoft.Extensions.Http | 9.0.0 | HttpClientFactory DI-friendly |
| Microsoft.Extensions.Http.Resilience | 9.0.0 | Retry / circuit breaker / timeout (succede a Polly direct en .NET 8+) |
| Refit | 8.0.0 | REST client typed — top-1 wrapper HttpClient C# |
| Refit.HttpClientFactory | 8.0.0 | Integration Refit + DI HttpClientFactory |
| FluentValidation | 11.10.0 | Validation forms / models |
| Serilog.Extensions.Logging | 9.0.0 | Logger structure (peer ILogger<T>) |
| Serilog.Sinks.Debug | 3.0.0 | Sink Debug (console IDE pendant dev) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| ef-sqlite | Microsoft.EntityFrameworkCore.Sqlite (alt) | 9.0.0 | ef-core, entity.*framework, ef-sqlite |
| msal | Microsoft.Identity.Client | 4.66.0 | msal, azure-ad, auth-azure-ad, sso |
| charts | LiveChartsCore.SkiaSharpView.Maui | 2.0.0-rc4.1 | chart, graph, visualisation, courbe |
| charts | Microcharts.Maui (alt) | 1.0.0 | microcharts, chart.*simple |
| skia | SkiaSharp.Views.Maui.Controls | 3.116.1 | skia, dessin.*custom, canvas |
| barcode | ZXing.Net.Maui.Controls | 0.4.0 | barcode, qr.*code, scan.*qr |
| firebase-push | Plugin.Firebase | 3.1.0 | firebase, push.*notification, fcm, notification |
| audio | Plugin.Maui.Audio | 3.0.1 | audio, lecture.*son, enregistrement.*audio |
| biometric | Plugin.Fingerprint | 3.0.0 | biometric, fingerprint, face-id, touch-id |
| in-app-rating | Plugin.Maui.AppRating | 2.0.0 | rating, app-store-rating, demande.*review |
| in-app-billing | Plugin.InAppBilling | 8.0.5 | in-app-purchase, abonnement, billing |
| maps | Microsoft.Maui.Controls.Maps | 9.0.40 | maps, carte, marker |
| stripe | Stripe.net | 47.1.0 | stripe, paiement, payment |
| sentry | Sentry.Maui | 5.3.0 | sentry, error.*tracking, monitoring.*erreurs |
| localization | Microsoft.Extensions.Localization | 9.0.0 | i18n, localization, multi.*langue |
| cert-pinning | Plugin.MauiCertPinning | 1.0.0 | cert-pinning, ssl-pinning |
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
2. **Le backend reste declare separement** dans `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`) — co-existent sous `workspace/output/src/`
3. **Pre-requis** : verifier `dotnet workload list` contient `maui`. Sinon : `dotnet workload install maui` (peut prendre 5-10min). Sur macOS : XCode + Apple Developer (free pour simulateur, payant pour TestFlight/App Store). Sur Linux : iOS impossible (build iOS exige Mac).
4. **Creer** `workspace/output/src/{AppName}/` via `dotnet new maui` (cf. §2.2.1)
5. **Composer** `appsettings.json` (MauiAsset) depuis `## Active Mobile Config` (`MOBILE_API_BASE_URL`) + `## Active Auth Specs`. **JAMAIS** ecrire les secrets en clair — utiliser plutot SecureStorage runtime + injection a la premiere connexion.
6. **`## Active UI Specs`** : aucun design system web n'est compatible (`shadcn`/`vuetify`/`radzen-blazor` → WARNING bloquant). MAUI utilise son propre theming via `Resources/Styles/`. Alternative : capability `syncfusion-maui` (suite Syncfusion commerciale).
7. **Phase B (DB)** : SKIP — pas de DB serveur. Si `ef-sqlite` capability → tables EF Core locale generees au premier run via `db.EnsureCreatedAsync()`.
8. **Phase C (ADRs)** : creer `ADR-{ts}-stack-mobile-maui.md` documentant .NET 9 + MAUI + CommunityToolkit + sqlite-net-pcl

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de "backend interne". Convention :

- `dev-backend` **ne touche pas** au projet MAUI — il code le backend separe declare dans `## Active Tech Specs backend/*`
- `dev-frontend` materialise **tout** le projet MAUI : Pages, ViewModels, Services, Repositories, Models, Converters, Behaviors, Resources, Platforms

**File ownership** (override `file-ownership.md §1`) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/Pages/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/ViewModels/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Services/**` | `dev-frontend` (toute la logique vit dans le projet MAUI) |
| `workspace/output/src/{AppName}/Repositories/**` | `dev-frontend` (DB locale) |
| `workspace/output/src/{AppName}/Models/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Converters/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Behaviors/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Controls/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Resources/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Platforms/**` | `arch` (create) + `dev-frontend` (augment permissions / manifest entries) |
| `workspace/output/src/{AppName}/MauiProgram.cs` | `arch` (create) + `dev-frontend` (augment services DI) |
| `workspace/output/src/{AppName}/App.xaml(.cs)` / `AppShell.xaml(.cs)` | `arch` (create) + `dev-frontend` (augment routes Shell) |
| `workspace/output/src/{AppName}/{AppName}.csproj` | `arch` (create) + `dev-frontend` (augment NuGet packages on-demand) |
| `workspace/output/src/{AppName}/appsettings.json` | `arch` (create exclusif — config) |

**Backend separe** : meme matrice ownership que pour son propre stack. Les 2 projets co-existent sous `workspace/output/src/{BackendName}/` et `workspace/output/src/{AppName}/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}
dotnet restore {AppName}.csproj
dotnet build {AppName}.csproj -f net9.0-android --nologo --no-restore
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

Smoke complet (~300s premiere build) : `dotnet build -f net9.0-android` doit produire `bin/Debug/net9.0-android/{AppName}.dll` + `.apk` debug. Run optionnel via Android Studio AVD ou `dotnet build -t:Run -f net9.0-android` apres avoir demarre un emulateur.
