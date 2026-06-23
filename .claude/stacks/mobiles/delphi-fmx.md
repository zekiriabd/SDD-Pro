# Tech FEAT: delphi-fmx (mobile / desktop cross-platform)

> §2.4 (Librairies) régénérée depuis `delphi-fmx.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id delphi-fmx`).

Status: Experimental
Validation: 🟡 experimental — Spec stack OK + `.libs.json` validé. Jamais exécuté end-to-end via `/sdd-full`. Stack ajouté 2026-06-21 sur demande utilisateur. Validation runtime à programmer (RAD Studio 13 Florence requis pour bench, MSBuild + Android SDK pour Android target, macOS host + XCode pour iOS target).
Tech FEAT ID: tech-delphi-fmx
Scope: **mobile + desktop cross-platform** — application **Delphi FireMonkey (FMX)** dans UN seul projet `{AppName}/`. Single codebase Object Pascal qui cible Android + iOS + Windows + macOS (+ Linux serveur sans UI). UI FMX déclarative `.fmx` + code-behind `.pas` + persistance + auth + accès APIs natives vivent dans le même `.dproj`. Pas de séparation `{BackendName}` / `{LibName}`.

> **Backend séparé** : ce stack est PUREMENT client (mobile + desktop UI). Il consomme une API backend distincte déclarée en `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`, `backend/node-express.md`). Pour un app purement client → REST API tierce ou BaaS via env vars.

> **HTML→FMX mapping** : ce stack utilise un référentiel de mapping HTML/CSS → FMX inliné en §13 (extrait de `workspace/input/ui/_legacy-style/HtmlToFmx.md` et `fmx-ui.md` v1.0, intégrés ici comme source de vérité du framework). Les mockups HTML sous `workspace/input/ui/{n}-{m}-{Name}.html` sont traduits par `dev-frontend` vers des formulaires natifs FMX (`.fmx` + `.pas`) — **jamais** vers un `TWebBrowser`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application Delphi FMX (FireMonkey) Multi-platform** cible Android + iOS + Windows + macOS (+ Linux serveur) :

- **RAD Studio 13 Florence** (recommandé) — supporte aussi 12 Athens / 11 Alexandria
- **Object Pascal 13** — single codebase `.pas`/`.fmx` qui compile en natif sur les 5 plateformes
- **FMX (FireMonkey)** — framework UI déclarative cross-platform (alternative au VCL Windows-only)
- **MVVM artisanal** via Spring4D DI + DSharp Bindings OU LiveBindings natifs (selon préférence équipe)
- **DI native** via **Spring4D Container** (`Spring.Container`) — `Container.RegisterType<IFooService, TFooService>`
- **Navigation FMX** via **TFrameStand** (frames empilés, pattern dominant communautaire) OU `Application.MainForm.Show` (stack-based natif)
- **Storage local** : `IniFile`/`TIniFile` (settings) + **Keychain iOS / Keystore Android** via `Kastri` ou `FMX.Platform.Save` (tokens)
- **DB locale** : **FireDAC + SQLite** (bundled RAD) — top-1 standard de facto
- **HTTP** : `THTTPClient` (System.Net.HttpClient bundled) OU `TIdHTTP` (Indy bundled) — JSON via **Neon** (sérialiseur typé) ou `JsonDataObjects` (rapide)
- **Skia** : `Skia4Delphi` bundled RAD 12+ — rendering texte HQ, SVG, Lottie animations

Architecture cible (un seul `.dproj`) :

```
{AppName}/
├── {AppName}.dproj            ── projet multi-target (Win32/Win64/Android/Android64/iOS/macOS)
├── {AppName}.dpr              ── point d'entrée (Application.CreateForm)
├── App.Bootstrap.pas          ── enregistrement DI Spring4D + setup Skia + theming
├── UI/                        ── Forms et Frames FMX (.fmx + .pas)
│   ├── Main.fmx + Main.pas
│   ├── Login.fmx + Login.pas
│   └── Dashboard/
├── ViewModels/                ── VMs (TInterfacedObject + propriétés observables via DSharp/LiveBindings)
├── Models/                    ── Records / classes data (DTOs serializés Neon)
├── Services/                  ── Logique métier (interface I*Service + impl T*Service)
│   ├── Interfaces/            ── I*Service.pas (contrats DI)
│   └── *Service.pas
├── Repositories/              ── Accès DB locale FireDAC + cache
├── Common/                    ── Helpers, exceptions, types partagés
├── Resources/                 ── Images PNG multi-res, fonts, styles .style
│   ├── Styles/               ── *.style (StyleBook FMX) + tokens.style
│   ├── Images/               ── PNG multi-resolution (@1x, @2x, @3x)
│   └── Fonts/                ── *.ttf custom
├── Platforms/
│   ├── Android/              ── AndroidManifest.template.xml, JNI brigdes
│   ├── iOS/                  ── Info.plist.TemplateiOS.xml, Entitlements
│   └── Windows/              ── Win32/Win64-specific
├── tests/                    ── Tests DUnitX (dev-backend skip, owned par qa)
│   └── {AppName}Tests.dproj
└── appsettings.json          ── Config app (peuplé par arch — backend URL, JWT issuer)
```

**Différence vs `react-native.md` / `maui.md`** :
- Object Pascal **compile en natif** sur les 5 plateformes (ARC ARM64 iOS, JVM ART Android, PE Windows, Mach-O macOS) — pas de runtime intermédiaire (vs JS bridge RN, .NET runtime MAUI)
- Accès direct APIs natives via **JNI** (Android) / **Objective-C runtime** (iOS) via les unités `Androidapi.JNI.*` et `iOSapi.*` bundled
- UI déclarative FMX (`.fmx` text format DFM-like) — pas de JSX, pas de XAML
- Distribution standard (Play Store .apk/.aab, App Store .ipa, MSI/MSIX Windows, .dmg macOS)
- **Hot Reload UI** disponible mais limité (vs Metro RN ultra-fluide)

---

## 1.2 Couches

- **Forms/Frames** (`UI/*.fmx` + `.pas`) : UI déclarative FMX, code-behind minimal (uniquement event handlers UI purs — `FormCreate`, `OnClick` qui appelle ViewModel)
- **ViewModels** (`ViewModels/*ViewModel.pas`) : héritent de `TInterfacedObject` + interface `I*ViewModel`. Propriétés observables via DSharp `Notify` ou LiveBindings natif (`TBindingsList`)
- **Services** (`Services/*Service.pas`) : logique métier, contrat dans `Services/Interfaces/I*Service.pas`, impl scoped/singleton via Spring4D Container
- **Repositories** (`Repositories/*Repository.pas`) : accès DB locale (FireDAC) ou cache mémoire (Spring.Collections.IDictionary)
- **Models** (`Models/*.pas`) : records / classes data (mappe vers DB entities ou DTOs API). Sérialisation JSON via Neon (`[NeonProperty('xxx')]`)
- **Common** (`Common/*.pas`) : types partagés, exceptions custom (`EUserCancelled`, `EApiError`), helpers statiques (units en `class function` only)
- **Resources** : `Styles/*.style` (StyleBook FMX), `Images/` (PNG multi-res), `Fonts/` (TTF custom)

---

## 1.3 Mapping couche → répertoire

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas à ce stack**. Arch lève WARNING `[STACK_MALFORMED]` si déclarés avec valeur non null.

| Layer | Path |
|---|---|
| Project file | `workspace/output/src/{AppName}/{AppName}.dproj` |
| App entry | `workspace/output/src/{AppName}/{AppName}.dpr` |
| Bootstrap | `workspace/output/src/{AppName}/App.Bootstrap.pas` |
| Form (Page) | `workspace/output/src/{AppName}/UI/{Domain}/{Name}.fmx` + `{Name}.pas` |
| Frame (Component) | `workspace/output/src/{AppName}/UI/{Domain}/{Name}Frame.fmx` + `{Name}Frame.pas` |
| ViewModel | `workspace/output/src/{AppName}/ViewModels/{Domain}/{Name}ViewModel.pas` |
| Service interface | `workspace/output/src/{AppName}/Services/Interfaces/I{Domain}Service.pas` |
| Service impl | `workspace/output/src/{AppName}/Services/{Domain}Service.pas` |
| Repository | `workspace/output/src/{AppName}/Repositories/{Domain}Repository.pas` |
| Model / DTO | `workspace/output/src/{AppName}/Models/{Name}.pas` |
| Common helpers | `workspace/output/src/{AppName}/Common/{Name}.pas` |
| Resources Styles | `workspace/output/src/{AppName}/Resources/Styles/tokens.style`, `App.style` |
| Images / Fonts | `workspace/output/src/{AppName}/Resources/Images/`, `Resources/Fonts/` |
| Platform Android | `workspace/output/src/{AppName}/Platforms/Android/AndroidManifest.template.xml` |
| Platform iOS | `workspace/output/src/{AppName}/Platforms/iOS/Info.plist.TemplateiOS.xml` |
| Config app | `workspace/output/src/{AppName}/appsettings.json` (peuplé par arch — backend URL, JWT issuer) |
| Tests DUnitX | `workspace/output/src/{AppName}.Tests/{AppName}Tests.dproj` (owned par qa) |

---

## 1.4 Principes non négociables

**Architecture MVVM strict** :
- **Aucune logique métier dans code-behind** (`*.pas` co-located avec `.fmx`) — uniquement event handlers UI purs (`FormCreate`, animations). Toute logique = ViewModel.
- **MVVM via Spring4D + DSharp** OU **LiveBindings natifs** — équipe choisit en début de projet, **jamais mix** dans un même projet.
- **DI systématique** via `Spring.Container` (`Container.RegisterType<IFooService, TFooService>(TLifetimeType.Singleton)`). Constructor injection sur les ViewModels et Services. Pas de Service Locator caché. Pas de singleton statique `class var`.
- **ViewModels enregistrés Transient** (un par Form/Frame) — sauf `MainViewModel` qui peut être Singleton si état global
- **Services enregistrés Singleton** (`HttpClient`, `IAuthService`, `IDatabaseService`)
- **Bindings explicites** via DSharp `Bind(@Source, 'Prop', @Target, 'Prop')` ou LiveBindings via designer — JAMAIS de copy manuel `Edit1.Text := ViewModel.Email`
- **Async via `TTask.Run`** sur opérations I/O — pas de `Synchronize` bloquant. Update UI via `TThread.Queue(nil, procedure begin … end)` ou `TThread.ForceQueue`
- **Cibles Android + iOS** par défaut. Windows + macOS + Linux en target optionnels (capability `desktop-targets`)

**SOLID / Clean Code** :
- Méthodes ≤ 30 lignes (sauf événements UI complexes documentés)
- Unités ≤ 500 lignes (sinon split en sous-unités cohérentes)
- Pas de `with … do` ambigu (toujours qualifier `Self.X`, `Sender as TButton`)
- Pas de `class var` hors constantes — utiliser Spring4D Container
- Interface segregation : `IFooService` ne doit pas exposer 15 méthodes — split par cas d'usage

**Performance mobile FMX** :
- **`TListView`** (mobile-optimized, virtualisé natif) plutôt que `TStringGrid` ou `TListBox` pour gros datasets
- **Compiled FMX styles** via `.style` chargés au démarrage (pas de styles inline) — un seul `StyleBook` global par projet
- **Images `.svg`** : utiliser **Skia4Delphi** (`TSkSvg`) — FMX natif ne supporte pas SVG fiable cross-platform
- **Pas de `TThread.Synchronize` lourd** dans loops — utiliser `TThread.Queue` (non-bloquant)
- **TFrameStand** pour modal/drawer/toast plutôt que `TForm.Show`/`Hide` empilées (gestion mémoire propre)

**Sécurité mobile-specific** :
- **Tokens JWT / OAuth** dans **Keychain iOS / Keystore Android** via Kastri (`TBiometric.SecureStorage`) — JAMAIS dans `TIniFile` clair
- **Pas de secret client-side** — utiliser backend proxy
- **Permissions runtime** demandées juste-à-temps (`PermissionsService.RequestPermissions(['android.permission.CAMERA'], …)`) — pas au démarrage
- **Certificate pinning** (capability `cert-pinning`) pour apps sensibles — via `THTTPClient.OnValidateServerCertificate` ou Indy `OnVerifyPeer`
- **Deep links signés** : Universal Links iOS (apple-app-site-association) / App Links Android (assetlinks.json) — pas de scheme custom seul

---

## 1.5 Couches persistantes (locales)

Ce stack est CLIENT — la persistance "DB" réelle vit côté backend. Options locales :

| Type | Lib | Cas d'usage |
|---|---|---|
| Clé-valeur non sensible | `System.IniFiles.TIniFile` (built-in) | Préférences UI, last screen |
| Clé-valeur sensible | `Kastri.Biometric` + `KeyChain iOS` / `KeyStore Android` | Tokens JWT, credentials, PIN |
| DB SQLite locale | **FireDAC + SQLite** (bundled RAD) — top-1 standard | Offline-first, gros datasets, requêtes SQL |
| DB alternative cross-platform | `ZeosLib` (capability `db-zeos`) | Si équipe préfère OSS pur, ou besoin Firebird |
| Cache mémoire typé | `Spring.Collections.IDictionary<T1,T2>` | Cache API responses runtime |
| File system | `System.IOUtils.TPath`/`TFile` (built-in) | Fichiers app data (e.g. downloads) |

**Mode par défaut** : Kastri.SecureStorage + TIniFile + FireDAC SQLite. Suffisant pour 90% des apps.

---

## 1.6 Cible plateformes — matrice de décision

| Plateforme | Target Delphi | Par défaut |
|---|---|---|
| Android (ARM 32 + ARM 64) | `Android` + `Android64` | ✅ |
| iOS Device 64-bit | `iOSDevice64` | ✅ (macOS host requis) |
| iOS Simulator ARM | `iOSSimARM64` | ✅ (macOS host + XCode) |
| Windows 32-bit | `Win32` | ❌ (capability `desktop-targets`) |
| Windows 64-bit | `Win64` | ❌ (capability `desktop-targets`) |
| macOS Universal | `OSX64` + `OSXARM64` | ❌ (capability `desktop-targets`, macOS host) |
| Linux 64-bit (CLI/serveur) | `Linux64` | ❌ (capability `linux-server`, FMX UI non supporté Linux) |

iOS exige obligatoirement un host macOS (PAServer) ou cloud Mac (MacInCloud) pour signature + déploiement.

---

# 2. Stack

## 2.1 Identité

- **Stack ID** : `delphi-fmx`
- **Langage** : Object Pascal (Delphi 13)
- **Runtime** : Natif (pas de VM) — compile via DCC32/DCC64/DCCAARM/DCCIOSARM64
- **Framework UI** : FireMonkey (FMX) RAD Studio 13 Florence
- **MVVM** : Spring4D DI Container + DSharp Bindings (OU LiveBindings natifs au choix)
- **Toolkit** : Skia4Delphi (rendering HQ) + Kastri (cross-platform helpers) + TFrameStand (navigation)
- **Plateformes** : iOS 15.0+ / Android API 24+ (Android 7.0)
- **Namespace racine** : `{AppNamespace}` (ex. `MyApp.UI.Login`)

---

## 2.2 Outils

- **IDE** : RAD Studio 13 Florence (Delphi Community/Pro/Enterprise/Architect editions)
- **Project file** : `workspace/output/src/{AppName}/{AppName}.dproj` (XML MSBuild)
- **Build CLI Win64** : `MSBuild.exe {AppName}.dproj /p:Config=Debug /p:Platform=Win64 /t:Build`
- **Build CLI Android** : `MSBuild.exe {AppName}.dproj /p:Config=Debug /p:Platform=Android64 /t:Build` (RAD Android SDK requis)
- **Build CLI iOS** : `MSBuild.exe {AppName}.dproj /p:Config=Debug /p:Platform=iOSDevice64 /t:Build` (PAServer macOS requis)
- **Smoke Command** :

```bash
# Pré-requis : Embarcadero Command Prompt (rsvars.bat exécuté pour exposer MSBuild + DCC32)
MSBuild "{AppName}.dproj" /p:Config=Debug /p:Platform=Win64 /t:Build /v:minimal
test -f "Win64/Debug/{AppName}.exe"
```

- **Smoke Timeout** : 180s (première compile RAD ~30-60s sur projet vide, incrémentale ~5s)
- **Package manager** : **GetIt** (officiel IDE-intégré) / **DPM** (CLI) / **Boss** (CLI npm-like) / clone manuel
- **Type-check** : intégré au compilateur Delphi (strict types par défaut)
- **Lint / Format** : `Pascal Analyzer` (commercial Peganza) OU `Delphi-Code-Format` (CLI OSS) — convention `JediCodeFormat` largement adoptée

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/output/src/{AppName}/{AppName}.dproj" ]; then

# Pre-requis (verifies par arch en STEP 0) :
# - RAD Studio 13 Florence installe (ou 12 Athens minimum)
# - Embarcadero Command Prompt dans PATH (rsvars.bat configure MSBuild + BDS)
# - Android SDK + NDK configures dans RAD Studio (Tools > Options > SDK Manager) pour cible Android
# - macOS host + XCode + PAServer pour cible iOS (sinon Android only)

# STEP 1 — Scaffold structure projet FMX (RAD genere via File > New > Multi-Device Application)
mkdir -p workspace/output/src/{AppName}/UI \
         workspace/output/src/{AppName}/ViewModels \
         workspace/output/src/{AppName}/Models \
         workspace/output/src/{AppName}/Services/Interfaces \
         workspace/output/src/{AppName}/Repositories \
         workspace/output/src/{AppName}/Common \
         workspace/output/src/{AppName}/Resources/Styles \
         workspace/output/src/{AppName}/Resources/Images \
         workspace/output/src/{AppName}/Resources/Fonts \
         workspace/output/src/{AppName}/Platforms/Android \
         workspace/output/src/{AppName}/Platforms/iOS \
         workspace/output/src/{AppName}/Platforms/Windows

# STEP 2 — Generer .dpr (point d'entree) + .dproj (XML MSBuild) + Main.fmx/.pas
# Via template arch (cf. .claude/templates/delphi-fmx/{AppName}.dproj.template + .dpr.template)
# Substitution {AppName}, {AppNamespace}, target platforms.

# STEP 3 — Installer librairies CORE via GetIt CLI (ou clone manuel cf. .libs.json)
# Skia4Delphi bundled depuis RAD 12 — verifier presence dans Lib\skia4delphi avant install
GetItCmd.exe -i=Skia4Delphi -force                          || \
  ( git clone https://github.com/skia4delphi/skia4delphi C:\Lib\Skia4Delphi && \
    Setup\Setup.exe install --library-paths )

# Spring4D — clone (pas dispo GetIt officiel)
git clone --branch v2.0.0 https://github.com/spring4d/spring4d C:\Lib\Spring4D 2>/dev/null || true

# DUnitX — bundled RAD depuis 11+, sinon clone
test -d "$BDSCommonDir\Lib\Win32\Release\DUnitX" || \
  git clone https://github.com/VSoftTechnologies/DUnitX C:\Lib\DUnitX

# Neon JSON Serializer
git clone https://github.com/paolo-rossi/delphi-neon C:\Lib\Neon 2>/dev/null || true

# TFrameStand + TSubjectStand
git clone https://github.com/andrea-magni/TFrameStand C:\Lib\TFrameStand 2>/dev/null || true
git clone https://github.com/andrea-magni/TSubjectStand C:\Lib\TSubjectStand 2>/dev/null || true

# STEP 4 — Patcher .dproj : ajouter Library Paths aux options globales du projet (via Edit du XML)
# IMPORTANT (cf. §15.4) : utiliser des chemins ABSOLUS en clair, JAMAIS d'env vars
# $(SPRING4D)/$(NEON)/etc. (cassent silencieusement si non setx-ées).
# IMPORTANT (cf. §15.9) : Spring4D nécessite 11 sous-dossiers explicites
# (le DCC ne récurse pas).
# IMPORTANT (cf. §15.8) : DCC_Namespace DOIT inclure 'Winapi' (sinon F2613 sur
# Spring.pas et autres libs Windows).
#
# Template <DCC_UnitSearchPath> :
#   C:\Lib\Spring4D\Source;C:\Lib\Spring4D\Source\Base;C:\Lib\Spring4D\Source\Base\Collections;
#   C:\Lib\Spring4D\Source\Base\Logging;C:\Lib\Spring4D\Source\Base\Patches;
#   C:\Lib\Spring4D\Source\Base\Patterns;C:\Lib\Spring4D\Source\Core;
#   C:\Lib\Spring4D\Source\Core\Container;C:\Lib\Spring4D\Source\Core\Interception;
#   C:\Lib\Spring4D\Source\Core\Logging;C:\Lib\Spring4D\Source\Core\Services;
#   C:\Lib\Neon\Source;
#   C:\Program Files (x86)\Embarcadero\Studio\37.0\source\Skia\Source;
#   $(DCC_UnitSearchPath)
#
# Template <DCC_Namespace> :
#   System;Xml;Data;Datasnap;Web;Soap;Winapi;Vcl;Vcl.Imaging;Vcl.Touch;Vcl.Samples;Vcl.Shell;FMX;FMX.Types;$(DCC_Namespace)
#
# (Edit via Read+Edit du .dproj, pas sed — XML sensible aux espaces)

# STEP 5 — Bootstrap appsettings.json (peuple par arch depuis stack.md)
cat > "workspace/output/src/{AppName}/appsettings.json" <<'JSON'
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

# STEP 6 — Compiler sanity check (Win64 — disponible sur tout host Windows sans toolchain mobile)
# Pre-condition cle (cf. §15.4 + §15.8 + §15.9) : .dproj patche en chemins absolus,
# Winapi present dans DCC_Namespace, 11 sous-dossiers Spring4D listes explicitement.
cd workspace/output/src/{AppName}
MSBuild "{AppName}.dproj" /p:Config=Debug /p:Platform=Win64 /t:Build /v:minimal || true

# STEP 7 — Validation post-scaffolding (cf. §15.10 récap, exit non-zero = STOP)
# (a) unit name == basename .pas (§15.7)
python -X utf8 - <<'PY' || exit 1
import pathlib, re, sys
root = pathlib.Path('.')
for p in root.rglob('*.pas'):
    text = p.read_bytes().decode('utf-8-sig', errors='replace')
    m = re.search(r'(?im)^\s*unit\s+([\w\.]+)\s*;', text)
    if m and (m.group(1) + '.pas').lower() != p.name.lower():
        print(f'[DELPHI_UNIT_NAME_MISMATCH] {p}: unit={m.group(1)}'); sys.exit(1)
PY

# (b) GUIDs interface : hex strict (§15.6)
! grep -rnE "\['\{[0-9A-Fa-f-]*[^0-9A-Fa-f\-\}']" --include="*.pas" \
  || { echo "[DELPHI_GUID_INVALID] GUID non-hex detecte"; exit 1; }

# (c) .fmx CRLF + zero commentaire (§15.1)
for f in UI/**/*.fmx; do
  grep -q $'\r' "$f" || { echo "[FMX_LF_LINE_ENDINGS] $f"; exit 1; }
done
! grep -rE '^\s*(\{[^$]|\(\*|//)' --include="*.fmx" \
  || { echo "[FMX_COMMENT_FORBIDDEN]"; exit 1; }

# (d) .fmx integer-only props sans float literal (§15.2)
! grep -rnE '^\s*(ClientHeight|ClientWidth|Left|Top|Width|Height|Tag|TabOrder)\s*=\s*[0-9]+\.[0-9]+' --include="*.fmx" \
  || { echo "[FMX_INT_PROP_FLOAT]"; exit 1; }

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de vérité : `.claude/stacks/mobiles/delphi-fmx.libs.json`. Ne pas éditer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id delphi-fmx`.

#### 2.4.a Librairies CORE (installées par arch en section 2.2.1, toujours)

| Lib | Version | Rôle |
|-----|---------|------|
| Skia4Delphi | 6.2.0 | Google Skia binding — text HQ, SVG, Lottie. Bundled RAD 12+ |
| Spring4D | 2.0.0 | DI container + collections génériques + Patterns SOLID |
| DUnitX | 1.6.0 | Tests unitaires modernes — successeur DUnit |
| Delphi-Neon | 1.8.0 | Sérialiseur JSON annotations-driven |
| TFrameStand | 1.6.0 | State management FMX — show/hide/animate frames empilés |
| TSubjectStand | 1.0.1 | Observer pattern companion TFrameStand |
| Indy | 10.6.3 | Réseau (HTTP/SMTP/FTP/TCP) bundled RAD |
| JsonDataObjects | 1.9.6 | Parser JSON ultra-rapide (3-5× System.JSON) |

#### 2.4.b Librairies ON-DEMAND (installées si l'US déclenche)

Triggers (regex case-insensitive) cherchés par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| ormot-orm | mORMot2 | 2.3.7 | ormot, mormot, soa.*framework, rest.*server |
| fmx-cross-platform-helpers | Kastri | 2025.06.01 | kastri, push.*notification, fcm, firebase, biometric, fingerprint, share.*sheet, in-app-purchase, ble, geolocation |
| barcode | ZXing.Delphi | 1.4.0 | barcode, qr.*code, scan.*qr |
| openssl | Delphi-OpenSSL | 1.2.0 | openssl, tls, crypto.*aes, x509 |
| method-hooking | DDetours | 2.5 | ddetours, method.*hook, mock.*runtime |
| pdf-generation | SynPDF | 2.3.7 | pdf.*generation, rapport.*pdf, export.*pdf |
| memory-manager | FastMM5 | 5.04 | fastmm, memory.*leak.*tracking |
| xml-parsing | OmniXML | 1.2 | omnixml, xml.*parsing, xml.*dom |
| mvvm-bindings | DSharp | 1.2 | dsharp, mvvm.*binding, two.*way.*binding |
| templating | Sempare.Template | 1.9.0 | template.*engine, sempare, mustache |
| charts | TeeChart-FMX-Standard | 2024.39 | teechart, chart, graph, courbe |
| reporting | FastReport-FMX | 2024.2.20 | fastreport, rapport, report.*generator |
| ui-controls-premium | TMS.FNC.UIPack | 5.0.1.0 | tms.*fnc, tms.*ui, premium.*controls |
| charts | TMS.FNC.Chart | 2.0.5.0 | tms.*chart, fnc.*chart |
| websockets | sgcWebSockets | 4.5.5 | websocket, socket.*temps.*reel, real.*time.*push |
| mqtt | Delphi.MQTT | 1.0.0 | mqtt, iot.*broker, mosquitto |
| redis | Delphi-Redis-Client | 0.7.0 | redis, cache.*distribue, key.*value.*store |
| db-universal | UniDAC | 11.0 | unidac, devart.*data.*access, multi-db |
| db-zeos | ZeosLib | 8.0.0 | zeos, zeoslib, db.*open.*source |
| jwt-auth | Delphi-JOSE-JWT | 3.2.0 | jwt, jose, json.*web.*token, bearer.*token |
| password-hashing | scrypt | 1.0 | scrypt, bcrypt, password.*hash |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — vérifiés par dev-* STEP 5.0. Toute violation = ERROR.

| Rôle | Pattern | Exemple |
|------|---------|---------|
| Form | `{Name}.fmx` + `{Name}.pas` (classe `T{Name}Form` ou `T{Name}`) | `Login.fmx` → `TLoginForm` |
| Frame | `{Name}Frame.fmx` + `{Name}Frame.pas` (classe `T{Name}Frame`) | `UserCardFrame.fmx` → `TUserCardFrame` |
| ViewModel | `{Name}ViewModel.pas` (classe `T{Name}ViewModel` impl `I{Name}ViewModel`) | `LoginViewModel.pas` → `TLoginViewModel` |
| Service interface | `Interfaces/I{Domain}Service.pas` (interface `I{Domain}Service`) | `IAuthService.pas` |
| Service impl | `{Domain}Service.pas` (classe `T{Domain}Service` impl `I{Domain}Service`) | `AuthService.pas` |
| Repository | `{Domain}Repository.pas` (DB locale ou cache) | `UserRepository.pas` |
| Model | `{Name}.pas` (record ou classe, jamais suffixe Dto) | `User.pas`, `Booking.pas` |
| Common helper | `{Name}.pas` dans `Common/` (class-only static methods) | `JsonHelpers.pas` |
| Custom Style | `{Name}.style` dans `Resources/Styles/` | `tokens.style`, `App.style` |

**Préfixes contrôles FMX dans formulaires** (cf. §13 HtmlToFMX mapping) :
`Edit`, `Memo`, `Btn`, `Lbl`, `Chk`, `Rad`, `Cbo`, `Sw`, `Img`, `Layout`, `Rect`, `Grid`, `List` — ex. `EditEmail`, `BtnLogin`, `LblTitle`, `RectCard`.

**Suffixes INTERDITS** :
- `Dto`, `InputDto`, `OutputDto`, `Request`, `Response` — utiliser nom du domaine
- `Manager`, `Helper`, `Util` (sauf `Common/` strict pour pure static class methods)
- `Impl` suffixe sur la classe (l'interface n'a pas de suffixe ; la classe ajoute pas non plus `Impl` — convention Delphi `T` préfixe suffit)

**Conventions de fichier** :
- Pascal : `PascalCase.pas`
- FMX : `PascalCase.fmx` + co-located `PascalCase.pas`
- Resources : `PascalCase.style`, `kebab-case.png` pour images
- Project : `{AppName}.dproj` + `{AppName}.dpr` (XML MSBuild + entry point Pascal)

---

## 3. Endpoints standard (côté backend séparé)

Comme `maui.md §3`, ce stack consomme un backend distinct. Les endpoints minimaux attendus côté backend :

| Endpoint backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` ou `/api/auth/[...]` | flow auth |
| `GET /api/me` | user courant |

Côté app : **base URL** dans `appsettings.json` (`Api:BaseUrl`), peuplé par arch depuis nouvelle section `## Active Mobile Config` du `stack.md` (convention `MOBILE_API_BASE_URL`).

---

## 4. Versioning des API consommées

Le backend expose `/api/v1/{domain}`. Côté Delphi FMX : maintenir une **MinSupportedApiVersion** dans `appsettings.json` (`Api:MinVersion`). À chaque release mobile, valider que le backend déployé supporte cette version.

---

## 5. Interdits projet (delphi-fmx)

**Architecture** :
- Logique métier dans code-behind Form/Frame (`*.pas` co-located avec `.fmx`) — toujours ViewModel
- Accès direct DB ou `THTTPClient` depuis ViewModel — toujours via Service injecté Spring4D
- Mapping manuel répétitif dans ViewModel/Service — utiliser helpers ou Neon (`TNeon.ObjectToJsonString`)
- Pas de Spring4D Container — ne JAMAIS rouler avec `class var FInstance` ou Service Locator caché
- `Application.MainForm.Show` empilé profond — utiliser **TFrameStand** ou navigation explicite
- `Bindings designer` mélangés avec DSharp Bindings — choisir UNE approche par projet
- `Synchronize` bloquant dans loop — utiliser `TThread.Queue` non-bloquant
- `TStringGrid` pour datasets > 100 lignes — utiliser `TListView` (virtualisé)
- Images SVG directement dans `<TImage>` — utiliser `TSkSvg` (Skia4Delphi) ou `TPath`

**Code quality** :
- `Writeln`/`OutputDebugString` → utiliser `Logger` injecté (Spring4D ILogger)
- `try … except on E: Exception do … end` swallow silencieux — toujours log ou re-raise
- Méthodes > 30 lignes — décomposer en helpers privés
- `with … do` ambigu — toujours qualifier `Self.X`
- Imports stars `uses System;` — toujours unités explicites (`uses System.SysUtils, System.Classes;`)
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Token JWT dans `TIniFile` ou `String` mémoire long-lived — utiliser Kastri.SecureStorage
- Secret hardcodé dans `.pas` versionné — utiliser `appsettings.json` + arch injection
- API key Stripe/Firebase secret côté client — toujours via backend proxy
- `THTTPClient.SecureProtocols := []` — toujours TLS 1.2+ minimum
- Certificate pinning désactivé sur app bancaire/sensible

**FMX/UI** :
- Hardcoded colors `Fill.Color := $FFFF0000` dans code-behind — utiliser styles `.style` + `StyleLookup`
- Styles inline non extraits dans `StyleBook` global
- Itération profonde `TListView` dans `TScrollBox` — antipattern (double scroll, perf dégradée)
- `ItemsSource` lié grosse collection non-virtualisée — utiliser `TListView.AppearanceMode` + lazy load
- Police hardcodée `Font.Family := 'Arial'` — toujours via `StyledSettings` removal + style centralisé

**Build / packaging** :
- Engager `__history\`, `__recovery\`, `*.local`, `*.identcache`, `*.tvsconfig` dans git
- Permissions excessives dans `AndroidManifest.template.xml` ou `Info.plist.TemplateiOS.xml` — demander juste-à-temps via `PermissionsService`
- Pas de signed APK/AAB pour Play Store (keystore Embarcadero absent)
- Pas de provisioning profile valide pour iOS App Store
- **Library Paths référençant des env vars non-définies** (`$(SPRING4D)`, `$(NEON)`, `$(SKIA4DELPHI)`, `$(TFRAMESTAND)`) dans `.dproj` sans validation préalable — utiliser **chemins absolus en clair** (`C:\Lib\Spring4D\Source;...`) ou vérifier `setx SPRING4D ...` ET redémarrage RAD Studio AVANT toute build. L'env-var-substitution était la convention v1 — elle casse silencieusement quand l'utilisateur clone le repo sans setup préalable. Voir §15.4.
- Mix `Win32`+`Win64`+`Android32` simultané sans config explicite — toujours `<Platforms>...</Platforms>` filtré

**Format fichier FMX (`.fmx`) — pièges Object Pascal** :
- **Commentaires dans `.fmx`** — le format DFM/FMX (designer-serialized form) **n'accepte AUCUN commentaire**. Pas de `{ ... }`, pas de `(* ... *)`, pas de `// ...`. Toute insertion bloque l'ouverture en designer (`Identificateur attendu sur la ligne N`). Voir §15.1.
- **Line endings LF dans `.fmx`** — Pascal `.dfm`/`.fmx` parser exige **CRLF** sur Windows ; LF-only fait échouer la lecture sur certaines versions RAD Studio. Voir §15.1.
- **`ClientHeight`, `ClientWidth`, `Left`, `Top`, `Width`, `Height`, `Tag` en literal float** (`844.000000000000000000`) — ces propriétés sont **Integer** côté FMX. Utiliser `844` strict. `Size.Width`/`Size.Height`/`Position.X`/`Position.Y` restent en float. Voir §15.2.
- **`TabOrder` sur composant non-focusable** (`TLabel`, `TRectangle`, `TLayout`, `TPath`, `TImage`, `TCircle`, `TEllipse`, `TAniIndicator`, `TToolBar`, `TGridPanelLayout`, `TTimer`, `TOpenDialog`) — la propriété **n'existe pas** sur ces classes en FMX. Erreur runtime "La propriété TabOrder n'existe pas". `TabOrder` valide uniquement sur `TEdit`/`TButton`/`TCheckBox`/`TRadioButton`/`TComboBox`/`TMemo`/`TDateEdit`/`TTimeEdit`/`TVertScrollBox`/`TSwitch`/`TTrackBar`. Voir §15.3.

**Format fichier Pascal (`.pas`) — pièges commentaires** :
- **Docblock `{ ... }` contenant des placeholders `{Name}` / `{n}-{m}` / `{Domain}` / `{$macro}`** — les commentaires `{}` Pascal **ne nest PAS** : le premier `}` interne ferme le commentaire prématurément, le reste devient du code parasite (F2613, F2147, etc.). Toujours utiliser `(* ... *)` pour les docblocks multi-lignes (qui ne sont fermés que par `*)` explicite), ou `//` ligne par ligne. Voir §15.1.
- **Docblock `{ ... }` contenant des exemples JSON** (avec `{` `}` payload) — même piège. Convertir en `(* ... *)`.

---

## 6. Persistance locale — voir §1.5

Stack mobile/desktop → pas de "DB scaffolding" backend classique. Pour offline-first réel : **FireDAC + SQLite** bundled (capability core `firedac-sqlite`) ou `ZeosLib` (capability `db-zeos`).

---

## 7. Temps réel

- **WebSockets client/serveur** : `sgcWebSockets` (capability `websockets`) — connexion bidirectionnelle, sub-protocols (MQTT-over-WS, STOMP)
- **MQTT IoT broker** : `Delphi.MQTT` (capability `mqtt`) — pub/sub, QoS 0/1/2
- **SSE (Server-Sent Events)** : pas natif, utiliser `THTTPClient.Get` avec response stream lecture progressive
- **Push notifications** : `Kastri.Firebase` (capability `fmx-cross-platform-helpers`) — FCM Android + APNS iOS via Firebase

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Équipes Delphi historiques** qui veulent moderniser leur stack desktop VCL vers mobile cross-platform
- **Apps internes d'entreprise** avec besoin desktop + mobile unifié (un seul codebase 5 plateformes)
- **Logiciels métier verticaux** (médical, comptabilité, ERP) avec base Delphi installée
- **Migrations depuis VCL Windows** vers cross-platform (FMX = successeur naturel)
- **Performance native** sans JIT/interpreter (compile en code machine natif sur les 5 plateformes)

**NE PAS choisir si** :
- ❌ Équipe sans expérience Delphi/Pascal — courbe d'apprentissage très raide (langage rare 2026)
- ❌ App pure mobile sans desktop — RN/MAUI/Kotlin offrent écosystèmes plus modernes
- ❌ App avec UI très moderne (animations complexes, glassmorphism, design system 2026) — FMX rendering moins fluide qu'Compose/SwiftUI/RN
- ❌ Budget serré (RAD Studio Community Edition existe mais limitée 5K€ revenus/an — Pro Edition 1500€+/dev/an)
- ❌ Recrutement Delphi devs en 2026 difficile dans la plupart des marchés
- ❌ Distribution OTA fréquente — RN/Expo + EAS Update bien plus fluide
- ❌ Frontend Web inclus — Delphi n'a pas d'équivalent React/Vue (TMS WebCore existe mais niche)
- ❌ Hot Reload UI ultra-fluide en dev — `LiveReload` FMX existe mais moins mature que Metro/Vite

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `delphi-fmx` + `auth-local` (JWT via JOSE) + backend `dotnet-minimalapi` + `qa-delphi-dunitx` | 🟡 experimental | jamais validé end-to-end (stack ajouté 2026-06-21) |
| `delphi-fmx` + `auth-azure-ad` (MSAL via REST OAuth2 manuel) + backend `kotlin-spring-boot` | 🟡 experimental | viable, Indy/THTTPClient supportent OAuth2 PKCE |
| `delphi-fmx` + Firebase Auth (Kastri capability `fmx-cross-platform-helpers`) + backend Firebase/FaaS | 🟡 experimental | proto BaaS-style |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `## Active Tech Specs` contient `mobiles/delphi-fmx.md` → reconnaître comme stack **mobile/desktop FMX-only**
2. **Le backend reste déclaré séparément** dans `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`) — co-existent sous `workspace/output/src/`
3. **Pré-requis** : vérifier `MSBuild.exe` dans PATH (Embarcadero Command Prompt — `rsvars.bat` configure `BDS`, `MSBuild`, libs DCC). Vérifier RAD Studio installé (`HKLM\SOFTWARE\Embarcadero\BDS\<version>`). Pour Android : SDK + NDK configurés dans IDE. Pour iOS : macOS host + PAServer. Sur Linux : aucune cible UI FMX (Linux64 supporte seulement console/serveur Pascal).
4. **Créer** `workspace/output/src/{AppName}/` via templates (`.claude/templates/delphi-fmx/`) — pas de `dotnet new`/`expo init` équivalent, scaffolding manuel via templates substitués (`{AppName}`, `{AppNamespace}`).
5. **Composer** `appsettings.json` depuis `## Active Mobile Config` (`MOBILE_API_BASE_URL`) + `## Active Auth Specs`. **JAMAIS** écrire les secrets en clair — utiliser plutôt Kastri.SecureStorage runtime + injection à la première connexion.
6. **`## Active UI Specs`** : aucun design system web n'est compatible (`shadcn`/`vuetify`/`radzen-blazor` → WARNING bloquant). FMX utilise son propre theming via `Resources/Styles/*.style` (StyleBook FMX). Alternative : capability `ui-controls-premium` (TMS FNC UI Pack commercial).
7. **Phase B (DB)** : SKIP — pas de DB serveur scaffoldée par arch côté client. Si `firedac-sqlite` capability (par défaut) → tables SQLite locales créées au premier run via `FDConnection.ExecuteScript('CREATE TABLE IF NOT EXISTS …')`.
8. **Phase C (ADRs)** : créer `ADR-{ts}-stack-mobile-delphi-fmx.md` documentant RAD Studio 13 + FMX + Spring4D + Skia4Delphi + Kastri.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de "backend interne". Convention :

- `dev-backend` **ne touche pas** au projet Delphi FMX — il code le backend séparé déclaré dans `## Active Tech Specs backend/*`
- `dev-frontend` matérialise **tout** le projet Delphi FMX : Forms, Frames, ViewModels, Services, Repositories, Models, Common, Resources, Platforms

**File ownership** (override `ownership.md §1` Partie A) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/UI/**` (`.fmx` + `.pas`) | `dev-frontend` |
| `workspace/output/src/{AppName}/ViewModels/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Services/**` | `dev-frontend` (toute la logique vit dans le projet Delphi) |
| `workspace/output/src/{AppName}/Repositories/**` | `dev-frontend` (DB locale) |
| `workspace/output/src/{AppName}/Models/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Common/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Resources/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/Platforms/**` | `arch` (create) + `dev-frontend` (augment permissions / manifest entries) |
| `workspace/output/src/{AppName}/{AppName}.dpr` | `arch` (create) + `dev-frontend` (augment forms enregistrement) |
| `workspace/output/src/{AppName}/{AppName}.dproj` | `arch` (create) + `dev-frontend` (augment Library Paths via package on-demand) |
| `workspace/output/src/{AppName}/App.Bootstrap.pas` | `arch` (create) + `dev-frontend` (augment DI registrations) |
| `workspace/output/src/{AppName}/appsettings.json` | `arch` (create exclusif — config) |

**Backend séparé** : même matrice ownership que pour son propre stack. Les 2 projets co-existent sous `workspace/output/src/{BackendName}/` et `workspace/output/src/{AppName}/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}

# Pré-requis : rsvars.bat exécuté dans le shell pour exposer MSBuild + BDS env vars
MSBuild "{AppName}.dproj" /p:Config=Debug /p:Platform=Win64 /t:Build /v:minimal /nologo

test -f "Win64/Debug/{AppName}.exe"
test -f "{AppName}.dpr"
test -f "App.Bootstrap.pas"
test -f "appsettings.json"
test -d "UI"
test -d "ViewModels"
test -d "Services/Interfaces"
test -d "Platforms/Android"
test -d "Platforms/iOS"
test -d "Resources/Styles"

# Vérifier que Library Paths sont configurés dans .dproj
grep -q "Spring4D" "{AppName}.dproj"
grep -q "Skia4Delphi" "{AppName}.dproj"
grep -q "Neon" "{AppName}.dproj"

echo "smoke OK"
```

Smoke complet (~30-60s première build Win64) : `MSBuild ... /p:Platform=Win64` doit produire `Win64/Debug/{AppName}.exe`. Cible Android Smoke : `MSBuild ... /p:Platform=Android64` doit produire `Android64/Debug/{AppName}.apk` (≥ 5 min première compilation NDK).

---

## 13. HTML → FMX mapping (référentiel intégré)

> Source canonique pour la traduction des mockups HTML (`workspace/input/ui/{n}-{m}-{Name}.html`) vers les Forms FMX (`UI/{Name}.fmx` + `UI/{Name}.pas`). L'agent `dev-frontend` applique strictement ce mapping en STEP 5 (plan inline) et STEP 6 (génération). Pas d'invention — un élément HTML non listé → STOP + ERROR `[STACK_LIBRARY_MISSING]` avec demande d'extension du mapping.

### 13.1 Workflow (à suivre dans l'ordre)

1. **Scan** mockup `workspace/input/ui/{n}-{m}-{Name}.html`. Un mockup = un Form FMX (`T{Name}Form` dans `UI/{Name}.fmx` + `.pas`).
2. **Parse** le document en arbre DOM, résoudre les CSS par priorité croissante : `<link rel="stylesheet">` → `<style>` → `style=""` inline.
3. **Map structure** (§13.4 + §13.6) : pour chaque nœud, choisir le contrôle FMX.
4. **Map layout** (§13.5) : traduire CSS box model / flex / grid en `Align`, `Anchors`, `Margins`, `Padding`, `Position`, `TLayout`/`TFlowLayout`/`TGridPanelLayout`.
5. **Map style** (§13.7) : traduire propriétés CSS visuelles en propriétés FMX. Classes CSS réutilisées → centraliser dans un `TStyleBook`.
6. **Générer** deux fichiers nommés d'après le mockup (`login.html` → `UI/Login.fmx` + `UI/Login.pas`) :
   - `UI/Login.fmx` — définition FMX (format DFM-like, exemple §13.9.1)
   - `UI/Login.pas` — unité Pascal (classe + event stubs, exemple §13.9.2)
7. **Reporter** dans le rapport `dev-frontend` un tableau Markdown : nœud HTML | contrôle FMX | propriété(s) non mappable(s) (cf. §13.12 limitations).

### 13.2 Conventions de nommage des contrôles

| Source HTML | Nom FMX |
|---|---|
| `id="email"` | utiliser l'id → `EditEmail` |
| sans id, `<input type=text>` | `Edit` + rôle/index → `Edit1` |
| `<button>Login</button>` | `BtnLogin` (verbe + caption) |
| `<div class="card">` (container neutre) | `LayoutCard` |
| `<div class="card">` (avec bg/border) | `RectCard` |

Préfixes par type : `Edit`, `Memo`, `Btn`, `Lbl`, `Chk`, `Rad`, `Cbo`, `Sw`, `Img`, `Layout`, `Rect`, `Grid`, `List`. Classe Form = `T` + PascalCase template name + `Form` (`TLoginForm`).

### 13.3 Namespaces FMX utiles

| Unit FMX | Contenu | Usage |
|---|---|---|
| `FMX.StdCtrls` | TButton, TCheckBox, TRadioButton, TLabel, TTrackBar, TSwitch, TProgressBar, TSpeedButton, TCornerButton | Contrôles standards |
| `FMX.Edit` | TEdit | Champ texte mono-ligne |
| `FMX.NumberBox` | TNumberBox | Numérique sans spinner |
| `FMX.SpinBox` | TSpinBox | Numérique avec +/− |
| `FMX.SearchBox` | TSearchEdit | Recherche |
| `FMX.Memo` | TMemo | Multi-ligne |
| `FMX.ListBox` | TListBox, TListBoxItem, TComboBox | Listes / dropdowns |
| `FMX.ListView` | TListView | Listes riches mobiles (cellules, swipe) |
| `FMX.Grid` | TStringGrid, TGrid | Tableaux |
| `FMX.TreeView` | TTreeView | Hiérarchique |
| `FMX.Layouts` | TLayout, TGridLayout, TFlowLayout, TScaledLayout, TGridPanelLayout | Conteneurs |
| `FMX.ScrollBox` | TScrollBox, TVertScrollBox, THorzScrollBox | Défilants |
| `FMX.ExtCtrls` | TPanel, TExpander, TCalloutPanel | Panneaux, accordéons |
| `FMX.TabControl` | TTabControl, TTabItem | Onglets / bottom nav |
| `FMX.MultiView` | TMultiView | Drawer / hamburger |
| `FMX.Header` | THeaderControl | Barre d'en-tête section |
| `FMX.Objects` | TRectangle, TCircle, TEllipse, TLine, TPath, TText, TImage | Primitives 2D |
| `FMX.Colors` | TColorPanel, TColorComboBox | Sélecteur couleur |
| `FMX.Calendar` / `FMX.CalendarEdit` | TCalendar, TCalendarEdit | Calendrier |
| `FMX.DateTimeCtrls` | TDateEdit, TTimeEdit | Date/heure |
| `FMX.MaskEdit` | TMaskEdit | Masque saisie |
| `FMX.Menus` | TMenuBar, TPopupMenu, TMenuItem | Menus |
| `FMX.Effects` | TShadowEffect, TBlurEffect, TGlowEffect | Effets visuels |
| `FMX.Ani` | TFloatAnimation, TColorAnimation, TBitmapAnimation | Animations |
| `FMX.Media` | TMediaPlayerControl | Vidéo |
| `FMX.WebBrowser` | TWebBrowser | WebView (réservé cas explicite — sinon antipattern) |
| `Skia.FMX` (Skia4Delphi) | TSkLabel, TSkSvg, TSkAnimatedImage, TSkLottieAnimation | Rendering HQ + SVG + Lottie |

### 13.4 HTML element → FMX control map

| HTML element | FMX control | Notes |
|---|---|---|
| `<input type="text">` | `TEdit` | `placeholder` → `TextPrompt` |
| `<input type="password">` | `TEdit` | `Password := True` |
| `<input type="email">` | `TEdit` | `KeyboardType := vktEmailAddress` |
| `<input type="tel">` | `TEdit` | `KeyboardType := vktPhonePad` |
| `<input type="url">` | `TEdit` | `KeyboardType := vktURL` |
| `<input type="search">` | `TSearchEdit` | |
| `<input type="number">` | `TNumberBox` | ou `TSpinBox` si +/- |
| `<input type="range">` | `TTrackBar` | `min`/`max`/`step` → `Min`/`Max`/`Frequency` |
| `<input type="checkbox">` | `TCheckBox` | `checked` → `IsChecked` |
| `<input type="radio">` | `TRadioButton` | `name` → `GroupName` |
| `<input type="date">` | `TDateEdit` | |
| `<input type="time">` | `TTimeEdit` | |
| `<input type="datetime-local">` | `TDateEdit` + `TTimeEdit` | pas de contrôle unique |
| `<input type="color">` | `TColorComboBox` | |
| `<input type="file">` | `TButton` + sélecteur (`FMX.MediaLibrary`/`FMX.Pickers`) | dialog ouvert dans event |
| `<input type="submit\|button\|reset">` | `TButton` | submit → `Default := True` |
| `<textarea>` | `TMemo` | `TextSettings.WordWrap := True` |
| `<select>` / `<option>` | `TComboBox` | options → `Items` |
| `<select multiple>` | `TListBox` (multi) | `MultiSelect := True` |
| `<button>` | `TButton` (standard) / `TSpeedButton` (icône, état) / `TCornerButton` (rond, FAB) | |
| `<label>` | `TLabel` | |
| `<p>`, `<span>`, `<h1>`…`<h6>` | `TLabel` (ou `TSkLabel` pour rendering HQ) | headings → `Font.Size` plus grande |
| `<a href>` | `TLabel` stylé + `OnClick` (`URLOpen`) | pas de "link" natif FMX |
| `<img>` | `TImage` (bitmap statique) ou `TImageControl` (multi-res via TImageList) | `src` → `MultiResBitmap`/`Bitmap` |
| `<svg>` / icône vectorielle | `TSkSvg` (Skia4Delphi) ou `TPath` simple | `d` → `Data.Data` pour `TPath` |
| `<hr>` | `TLine` | `LineType := ltTop` |
| `<progress>` | `TProgressBar` | |
| `<meter>` | `TProgressBar` | |
| `<div>` (plain box) | `TLayout` | invisible grouping |
| `<div>` (avec bg/border) | `TRectangle` | bg/border via Fill/Stroke |
| `<form>` | `TVertScrollBox` ou `TLayout` | scroll si tall |
| `<fieldset>` + `<legend>` | `TPanel` + `TLabel` | (pas de `TGroupBox` idiomatique sur mobile FMX) |
| `<ul>`/`<ol>`/`<li>` simple | `TListBox` | items → `TListBoxItem` |
| liste riche mobile (avatar + titre + sous-titre + swipe) | `TListView` | data-bound, virtualisée |
| `<table>` (data) | `TGrid` / `TStringGrid` | statique → `TGridPanelLayout` |
| `<nav>` / tab bar | `TTabControl` | onglets → `TTabItem` (`TabPosition := Bottom` pour bottom-nav) |
| `<header>` (app bar) | `TToolBar` (`Align:=alTop`) + `TLabel` + `TSpeedButton` | |
| `<footer>` | `TToolBar` (`Align:=alBottom`) | |
| `<section>`, `<article>`, `<main>` | `TLayout` ou `TPanel` | regroupement |
| `<dialog>` / modal | `TPopup` ou sub-form via TFrameStand | |
| menu drawer / off-canvas | `TMultiView` (mode `Drawer`) | |
| accordéon | `TExpander` | |
| `<video>` | `TMediaPlayerControl` | |
| `<iframe>` / webview | `TWebBrowser` | (réservé cas explicite) |

> **Règle de pouce** : interactive → vrai contrôle ; structural → conteneur de layout ; décoratif (bg/border) → `TRectangle`.
> Doute entre `TLayout` et `TRectangle` : `TLayout` si pas de bg/border, `TRectangle` sinon.

### 13.5 Layout system : CSS → FMX

FMX n'a pas de layout en flow par défaut — chaque contrôle est positionné/aligné explicitement.

| CSS | FMX équivalent |
|---|---|
| `display:block` (enfants empilés) | parent = `TLayout` ; enfants `Align := alTop` dans l'ordre |
| `display:flex; flex-direction:row` | parent = `TLayout` ; enfants `Align := alLeft` (+ un `alClient` pour fill) — ou `TGridPanelLayout` 1 ligne |
| `display:flex; flex-direction:column` | enfants `Align := alTop` dans un `TLayout` / `TVertScrollBox` |
| `justify-content:center` / centré | child `Align := alCenter` ou `alHorzCenter` |
| `align-items:stretch` | `Align := alClient` / `Anchors` left+right |
| `flex-wrap:wrap` | parent = `TFlowLayout` |
| `flex:1` (grow fill) | le contrôle qui fill = `Align := alClient` |
| `display:grid` | parent = `TGridPanelLayout` (`ColumnCollection`/`RowCollection`, `%` widths) — grilles régulières uniquement |
| `gap` / spacing | enfants `Margins` (ou `Padding` sur parent) |
| `position:absolute; top;left` | `Align := alNone` ; `Position.X`/`Position.Y` |
| `position:fixed` header/footer | `Align := alTop` / `alBottom` |
| `overflow:auto\|scroll` (V) | wrap dans `TVertScrollBox` |
| `overflow:auto\|scroll` (H) | wrap dans `THorzScrollBox` |
| responsive `width:100%` | `Align := alClient` ou `Anchors := [akLeft,akTop,akRight]` |
| `margin:auto` (center block) | `Align := alCenter` |
| `overflow:hidden` (carte qui rogne) | `TRectangle` + `ClipChildren := True` |

Valeurs `Align` : `alTop, alBottom, alLeft, alRight, alClient, alCenter, alContents, alHorzCenter, alVertCenter, alFit, alScale, alNone`.
`Margins` et `Padding` = `TBounds` (Left, Top, Right, Bottom — floats).

### 13.6 `<input>` decision shortcut

```
input → has type? ──no──► TEdit (text)
                  └─yes─► switch(type):
                          text/email/tel/url/password → TEdit
                          number   → TNumberBox (ou TSpinBox si +/-)
                          range    → TTrackBar
                          checkbox → TCheckBox
                          radio    → TRadioButton
                          date     → TDateEdit
                          time     → TTimeEdit
                          color    → TColorComboBox
                          file     → TButton + sélecteur (FMX.MediaLibrary)
                          submit/button/reset → TButton
```

### 13.7 CSS property → FMX property map

| CSS | FMX target |
|---|---|
| `width` | `Width` (float) |
| `height` | `Height` (float) |
| `min/max-width/height` | ⚠ pas de prop directe — émuler via `Align`/`Anchors` (noter limitation) |
| `color` (texte) | `TextSettings.FontColor` *(retirer `FontColor` de `StyledSettings`)* |
| `font-family` | `TextSettings.Font.Family` |
| `font-size` | `TextSettings.Font.Size` |
| `font-weight:bold` | `TextSettings.Font.Style := [TFontStyle.fsBold]` |
| `font-style:italic` | ajouter `fsItalic` à `Font.Style` |
| `text-decoration:underline` | ajouter `fsUnderline` |
| `text-align:left\|center\|right` | `TextSettings.HorzAlign := TTextAlign.Leading/Center/Trailing` |
| `vertical-align` | `TextSettings.VertAlign` |
| `text-overflow:ellipsis` | `AutoSize := False` + `Trimming := TTextTrimming.Character/Word` |
| `white-space:nowrap` | `WordWrap := False` |
| `line-height` | ⚠ pas de prop directe (noter limitation) |
| `background-color` | wrap dans `TRectangle` ; `Fill.Color` (ou via TStyleBook) |
| `background-image` | `TRectangle.Fill.Kind := TBrushKind.Bitmap` OU `TImage` background |
| `border` / `border-width`/`color` | `TRectangle.Stroke.Color`, `Stroke.Thickness` |
| `border-style:none` | `Stroke.Kind := TBrushKind.None` |
| `border-radius` | `TRectangle.XRadius`, `YRadius` (+ `Corners := [...]`) |
| `border-X` (un seul côté) | `TRectangle.Sides := [TSide.Top, …]` |
| `padding` | `Padding` (TBounds) |
| `margin` | `Margins` (TBounds) |
| `opacity` | `Opacity` (0.0-1.0) |
| `display:none` / `visibility:hidden` | `Visible := False` |
| `box-shadow` | attach `TShadowEffect` enfant |
| `filter:blur(...)` | `TBlurEffect` |
| `linear-gradient` | `Fill.Kind := TBrushKind.Gradient` + `Fill.Gradient.Points` |
| `cursor:pointer` (desktop) | `Cursor := crHandPoint` |
| `z-index` | ordre de déclaration / `BringToFront`, `SendToBack` |
| `transform:rotate()` | `RotationAngle` |
| `transform:scale()` | `Scale.X` / `Scale.Y` |
| `transform:translate()` | `Position.X` / `Position.Y` |
| `transition` / `animation` | `TFloatAnimation` / `TColorAnimation` enfants (FMX.Ani) |

### 13.7.1 Couleurs CSS → `TAlphaColor` FMX

FMX utilise `$AARRGGBB`. Conversion :
- `#RRGGBB` → `$FFRRGGBB` (ex. `#FF0000` → `$FFFF0000`)
- `#RGB` → expansion puis préfixe `$FF`
- `rgba(r,g,b,a)` → `$` + hex(a·255) + hex(r) + hex(g) + hex(b)
- couleur CSS nommée → `claXxx` (`red` → `claRed`) ou son hex équivalent

### 13.7.2 ⚠ Le piège `StyledSettings` (à appliquer systématiquement)

`TLabel`/`TText`/`TButton` **ignorent** font/color custom tant qu'on ne **retire pas** le flag correspondant de `StyledSettings`. Pour honorer CSS `color`, faire :
```pascal
LblTitle.StyledSettings := [TStyledSetting.Family, TStyledSetting.Size, TStyledSetting.Style, TStyledSetting.Other];
// (FontColor retiré → maintenant LblTitle.TextSettings.FontColor est utilisé)
```
Pour honorer `font-size`, retirer `Size`. Pour `font-family`, retirer `Family`. Etc.

### 13.8 Styles réutilisables → TStyleBook

Si une classe CSS est utilisée sur plusieurs nœuds (boutons, cards…), **ne pas dupliquer** les propriétés inline. Créer un style custom dans un `TStyleBook` et définir `StyleLookup` du contrôle vers ce style.

Mapping : une classe CSS → un style FMX. Garder UN `StyleBook1` par form (ou un StyleBook projet partagé) et le référencer depuis `Form.StyleBook`.


Garder la clause `uses` minimale mais **complète** : ajouter l'unité déclarant chaque contrôle utilisé (`FMX.Edit` pour `TEdit`, `FMX.StdCtrls` pour `TButton`/`TLabel`/`TCheckBox`, `FMX.Objects` pour `TRectangle`/`TImage`/`TLine`, `FMX.Layouts` pour `TLayout`/`TFlowLayout`/scroll boxes, `FMX.ListBox`, `FMX.Memo`, `FMX.DateTimeCtrls`, `FMX.SpinBox`, `FMX.Colors`, `Skia.FMX` pour TSkSvg/TSkLabel…).

### 13.9 Règles de génération (toujours)

1. Un mockup HTML → un Form FMX (`.fmx` + `.pas`), nommé d'après le mockup.
2. **Jamais** émettre `TWebBrowser` (sauf demande explicite cas iframe / OAuth flow externe).
3. Utiliser **`Align` + `Margins` en priorité**, `Position` absolu seulement si CSS `position:absolute`.
4. Appliquer la règle `StyledSettings` removal dès qu'une font/color custom est définie.
5. Tout `<input>`/`<button>`/`<select>` avec `id` ou `name` devient un champ nommé ; générer event stubs pour `onclick`/`onsubmit` (`OnClick`, `OnChange`).
6. Classes CSS réutilisables → styles `TStyleBook`, pas duplication inline.
7. **Sizes float, mais Form props int**. `Size.Width`/`Size.Height`/`Position.X`/`Position.Y`/`Margins.*`/`Padding.*`/`XRadius`/`YRadius` = `40.000000000000000000` (float strict). MAIS `ClientHeight`/`ClientWidth`/`Left`/`Top`/`Width`/`Height` (au niveau Form) et `Tag` sont **Integer** → `844` strict, jamais `844.000000000000000000` (erreur "Valeur de propriété incorrecte"). Voir §15.2 pour la matrice complète.
8. Form responsive : préférer `Align`/`Anchors` plutôt que coordonnées fixes (téléphone + tablette + desktop).
9. **`TabOrder` UNIQUEMENT sur composants focusables** : `TEdit`, `TButton`, `TCheckBox`, `TRadioButton`, `TComboBox`, `TMemo`, `TDateEdit`, `TTimeEdit`, `TVertScrollBox`, `TSwitch`, `TTrackBar`, `TGroupBox`. **JAMAIS** sur `TLabel`/`TRectangle`/`TLayout`/`TPath`/`TImage`/`TCircle`/`TEllipse`/`TAniIndicator`/`TToolBar`/`TGridPanelLayout`/`TFlowLayout`/`TScaledLayout`/`TText`/`TLine`/`TPolygon`/`TArc`/`TSkLabel`/`TSkSvg` (propriété inexistante → "La propriété TabOrder n'existe pas"). Préserver l'ordre DOM source via TabOrder UNIQUEMENT sur les contrôles focusables. Voir §15.3.
10. Réutiliser **`TSkSvg` (Skia4Delphi)** dès qu'un SVG apparaît dans le mockup — fallback `TPath` si SVG trivial.
11. **Format `.fmx` strict** : (a) **aucun commentaire** (DFM/FMX format n'accepte ni `{}` ni `(* *)` ni `//`) — les docs vont dans le `.pas` co-located, jamais dans le `.fmx` ; (b) **encodage CRLF** obligatoire (LF-only fait échouer la lecture sur certaines versions RAD Studio). Voir §15.1.
12. **Format `.pas` — commentaires** : les docblocks d'en-tête multi-lignes utilisent **`(* ... *)`**, jamais `{ ... }`. Raison : tout placeholder `{Name}`/`{n}-{m}`/`{Domain}` ou exemple JSON `{ ... }` à l'intérieur d'un commentaire `{}` ferme prématurément le commentaire (F2613 cascade). Les single-line `{ TFoo }` (sans `{` à l'intérieur) sont tolérés mais `(* TFoo *)` est préféré pour cohérence. Voir §15.5.

### 13.10 Mapping rapide (lookup unique)

| Clé HTML/CSS | Classe FMX | Unit |
|---|---|---|
| `div`, `section`, `nav`, `header`, `footer`, `main` | `TLayout` | FMX.Layouts |
| `div` carte (bordure/fond/radius) | `TRectangle` | FMX.Objects |
| `display:flex` | `TGridPanelLayout` (1 ligne/col) ou `Align` manuel | FMX.Layouts |
| `flex-wrap:wrap` | `TFlowLayout` | FMX.Layouts |
| `display:grid` | `TGridPanelLayout` | FMX.Layouts |
| `overflow:auto` | `TScrollBox` / `TVertScrollBox` / `THorzScrollBox` | FMX.ScrollBox |
| menu drawer | `TMultiView` | FMX.MultiView |
| onglets / bottom nav | `TTabControl`, `TTabItem` | FMX.TabControl |
| accordéon | `TExpander` | FMX.ExtCtrls |
| app bar | `TToolBar` | FMX.ExtCtrls |
| `h1`…`h6`, `p`, `span`, `label` | `TLabel` / `TSkLabel` | FMX.StdCtrls / Skia.FMX |
| `a` (lien) | `TLabel` stylé + `OnClick` | FMX.StdCtrls |
| `input[type=text]` | `TEdit` | FMX.Edit |
| `input[type=password]` | `TEdit` (Password) | FMX.Edit |
| `input[type=number]` | `TNumberBox` / `TSpinBox` | FMX.NumberBox / FMX.SpinBox |
| `input[type=date]` | `TDateEdit` | FMX.DateTimeCtrls |
| `input[type=time]` | `TTimeEdit` | FMX.DateTimeCtrls |
| `input[type=checkbox]` | `TCheckBox` | FMX.StdCtrls |
| `input[type=radio]` | `TRadioButton` | FMX.StdCtrls |
| `input[type=range]` | `TTrackBar` | FMX.StdCtrls |
| toggle switch | `TSwitch` | FMX.StdCtrls |
| `select` | `TComboBox` | FMX.ListBox |
| `textarea` | `TMemo` | FMX.Memo |
| `button` | `TButton` / `TSpeedButton` / `TCornerButton` | FMX.StdCtrls |
| `progress` | `TProgressBar` | FMX.StdCtrls |
| `ul`/`li` | `TListBox` | FMX.ListBox |
| liste riche mobile | `TListView` | FMX.ListView |
| `table` | `TGrid` / `TStringGrid` | FMX.Grid |
| arbre | `TTreeView` | FMX.TreeView |
| `img` | `TImage` / `TImageControl` | FMX.Objects |
| `svg` | `TSkSvg` (preferred) / `TPath` | Skia.FMX / FMX.Objects |
| `video` | `TMediaPlayerControl` | FMX.Media |
| `iframe`/webview | `TWebBrowser` | FMX.WebBrowser |
| `border-radius` | `XRadius`/`YRadius` | (propriété TRectangle) |
| `box-shadow` | `TShadowEffect` | FMX.Effects |
| `opacity` | `Opacity` | (propriété TControl) |
| `transition`/`animation` | `TFloatAnimation` | FMX.Ani |

### 13.11 Limitations connues (à reporter à l'utilisateur)

- Pas de `min-width`/`max-width`/`line-height` direct — émuler ou noter TODO
- Ratios `flex` CSS approximés via `alClient` + ordre `alLeft`/`alTop`
- Pseudo-classes (`:hover`, `:focus`, `:active`), media queries et JS behavior **non générés** automatiquement — lister pour wiring manuel dans styles/code
- `background-image` / gradients mappent vers `TBrush` kinds mais stops exacts peuvent nécessiter ajustement
- Texte multi-styles (gras + italique + couleur différente dans un même `<span>`) : FMX ne supporte pas — composer plusieurs `TLabel` ou utiliser `TSkLabel` (Skia) qui supporte rich text
- `position:sticky` : non supporté
- CSS Grid avec colonnes/lignes hétérogènes par item : `TGridPanelLayout` ne couvre que grilles régulières

### 13.12 Checklist de sortie

- [ ] `.fmx` + `.pas` générés et nommés d'après le mockup
- [ ] Tous les éléments HTML interactifs mappés vers vrais contrôles FMX
- [ ] Layout via `Align`/`Anchors`/`Margins` ; absolu uniquement si requis
- [ ] Fonts/couleurs custom appliquées avec `StyledSettings` removal
- [ ] Classes réutilisées centralisées dans `TStyleBook`
- [ ] Clause `uses` complète pour chaque type de contrôle utilisé
- [ ] Rapport de mapping généré (nœud HTML → contrôle FMX → propriétés non mappées)

**Gates anti-régression FMX (à valider AVANT marquer l'US Done)** :

- [ ] **`.fmx` encodé en CRLF** (`file *.fmx` → `ASCII text, with CRLF line terminators`). Si LF-only, convertir : `unix2dos *.fmx` ou Python `text.replace('\n', '\r\n')`.
- [ ] **Aucun commentaire dans `.fmx`** — `grep -nE '^\s*\{|^\s*\(\*|^\s*//' *.fmx` doit retourner zéro ligne.
- [ ] **`ClientHeight`/`ClientWidth`/`Left`/`Top`/`Width`/`Height`/`Tag` en Integer literal** — `grep -nE '^\s*(ClientHeight|ClientWidth|Left|Top|Width|Height|Tag)\s*=\s*[0-9]+\.' *.fmx` doit retourner zéro ligne.
- [ ] **`TabOrder` uniquement sur composants focusables** — pour chaque ligne `TabOrder = N`, vérifier que le composant parent (line précédente avec `object ...:T...`) est dans la liste focusable §15.3.
- [ ] **`.pas` docblocks en `(* ... *)`** — `grep -lE '^\{$' *.pas` (recherche `{` seul sur sa ligne, signature d'un docblock `{}` mal-formé) doit retourner zéro fichier.
- [ ] **`.pas` directives `{$IFDEF}`/`{$R}` préservées** — ne PAS confondre avec les commentaires `{` lors d'une éventuelle réécriture automatique.
- [ ] **Library Paths en `.dproj`** — pas d'env var `$(SPRING4D)`/`$(NEON)`/`$(SKIA4DELPHI)` non-définie (voir §15.4). Préférer chemins absolus.

---

## 14. Sources et références

- DocWiki Embarcadero FMX (RAD 13 Florence) : https://docwiki.embarcadero.com/Libraries/Florence/en/FMX
- Skia4Delphi : https://github.com/skia4delphi/skia4delphi
- Spring4D : https://bitbucket.org/sglienke/spring4d
- DUnitX : https://github.com/VSoftTechnologies/DUnitX
- Delphi-Neon : https://github.com/paolo-rossi/delphi-neon
- TFrameStand : https://github.com/andrea-magni/TFrameStand
- Kastri (cross-platform helpers) : https://github.com/DelphiWorlds/Kastri
- mORMot 2 : https://github.com/synopse/mORMot2
- DPM (package manager) : https://github.com/DelphiPackageManager/DPM
- Boss (alt package manager) : https://github.com/HashLoad/boss

---

## 15. Anti-régressions — pièges de génération Delphi/FMX (source de vérité)

> **Important** : section ajoutée 2026-06-22 suite à un debugging session où chacun de ces 5 pièges a fait échouer l'ouverture / la build du projet `FMXNounouJob` généré. **Tout agent générant du Delphi FMX DOIT lire cette section.** Chaque sous-section décrit le piège, le symptôme observable (message d'erreur exact RAD Studio), et la règle de génération à appliquer pour ne plus le rencontrer.

### 15.1 Commentaires `.fmx` (interdits) + line endings CRLF

**Symptôme** : `Erreur à la création de la fiche dans X.fmx : Identificateur attendu sur la ligne N` au double-clic sur le `.fmx` dans Project Manager.

**Cause** : le format DFM/FMX (designer-serialized form) **n'accepte AUCUN commentaire** — ni `{ ... }`, ni `(* ... *)`, ni `// ...`. La grammar attend `<property> = <value>` ou `object X: TType ... end` uniquement. Aussi, certaines versions RAD Studio (≥ 12) refusent les `.fmx` en LF-only line endings.

**Règle de génération** :
1. **Zéro commentaire** dans le `.fmx`. Toute documentation va dans le `.pas` co-located, jamais dans la form file.
2. **Line endings CRLF** (`\r\n`) — sur générateur Python utiliser `f.write(text.replace('\n', '\r\n'))` ou écrire en `newline=''` mode + insertion explicite `\r\n`.
3. Si une explication contextuelle est nécessaire, l'écrire dans le `.pas` au-dessus du `class TXxxForm = class(TForm)` correspondant.

**Auto-check post-génération** (à inclure dans le hook `dev-frontend` post-step pour FMX) :
```bash
# (a) Aucun commentaire dans .fmx
if grep -lE '^\s*(\{|\(\*|//)' workspace/output/src/{AppName}/UI/**/*.fmx 2>/dev/null; then
  echo "[FMX_COMMENT_FORBIDDEN] commentaire détecté dans .fmx — strip obligatoire"; exit 1
fi

# (b) CRLF obligatoire
for f in workspace/output/src/{AppName}/UI/**/*.fmx; do
  grep -q $'\r' "$f" || { echo "[FMX_LF_LINE_ENDINGS] $f en LF — convertir CRLF"; exit 1; }
done
```

### 15.2 Propriétés Integer vs Float dans `.fmx`

**Symptôme** : `Erreur lors de la lecture de XxxForm.ClientHeight: Valeur de propriété incorrecte. Ignorer cette erreur et continuer ?` à l'ouverture du `.fmx`.

**Cause** : certaines propriétés héritées du VCL/TForm sont **Integer** en FMX, mais les générateurs LLM par défaut émettent du float `844.000000000000000000` (héritage du designer FMX qui sérialise tout en float pour `Size.*`/`Position.*`).

**Matrice canonique** :

| Propriété | Type | Literal valide | Literal invalide |
|---|---|---|---|
| `ClientHeight` | Integer | `844` | ❌ `844.000000000000000000` |
| `ClientWidth` | Integer | `390` | ❌ `390.000000000000000000` |
| `Left` (TForm) | Integer | `0` | ❌ `0.000000000000000000` |
| `Top` (TForm) | Integer | `0` | ❌ `0.000000000000000000` |
| `Width` (TForm) | Integer | `390` | ❌ `390.000000000000000000` |
| `Height` (TForm) | Integer | `844` | ❌ `844.000000000000000000` |
| `Tag` | Integer | `0` | ❌ `0.000000000000000000` |
| `TabOrder` (focusable) | Integer | `0` | ❌ `0.000000000000000000` |
| `BorderIcons` | Set | `[biSystemMenu]` | n/a |
| `BorderStyle` | Enum | `bsSizeable` | n/a |
| **Float-OK** (toutes ci-dessous) | Float | `40.000000000000000000` | n/a |
| `Size.Width` / `Size.Height` | Float | ✓ | |
| `Position.X` / `Position.Y` | Float | ✓ | |
| `Margins.Left/Top/Right/Bottom` | Float | ✓ | |
| `Padding.Left/Top/Right/Bottom` | Float | ✓ | |
| `XRadius` / `YRadius` | Float | ✓ | |
| `Opacity` / `RotationAngle` / `Scale.X` / `Scale.Y` | Float | ✓ | |

**Règle de génération** : le LLM/template qui produit du `.fmx` DOIT consulter cette matrice avant d'émettre une valeur. Pas de "tout en float par défaut".

**Auto-check** :
```bash
grep -nE '^\s*(ClientHeight|ClientWidth|Left|Top|Width|Height|Tag|TabOrder|BorderIcons|BorderStyle)\s*=\s*[0-9]+\.[0-9]+' workspace/output/src/{AppName}/UI/**/*.fmx \
  && { echo "[FMX_INT_PROP_FLOAT] propriété Integer en literal float"; exit 1; }
```

### 15.3 `TabOrder` sur composants non-focusables

**Symptôme** : `Erreur lors de la lecture de XxxRect.TabOrder: La propriété TabOrder n'existe pas`.

**Cause** : `TabOrder` est défini sur `TStyledControl` UNIQUEMENT pour les contrôles `CanFocus = True`. Émettre `TabOrder = 0` sur `TLabel`/`TRectangle`/etc. = erreur de lecture.

**Composants où `TabOrder` est VALIDE (focusables)** :
`TEdit`, `TButton`, `TCheckBox`, `TRadioButton`, `TComboBox`, `TComboEdit`, `TMemo`, `TDateEdit`, `TTimeEdit`, `TCalendarEdit`, `TNumberBox`, `TSpinBox`, `TVertScrollBox`, `THorzScrollBox`, `TScrollBox`, `TSwitch`, `TTrackBar`, `TGroupBox`, `TExpander`, `TTabControl`, `TListBox`, `TListView`, `TGrid`, `TStringGrid`, `TTreeView`.

**Composants où `TabOrder` est INVALIDE (non-focusables)** :
`TLabel`, `TRectangle`, `TLayout`, `TPath`, `TImage`, `TImageControl`, `TCircle`, `TEllipse`, `TLine`, `TPolygon`, `TArc`, `TText`, `TSkLabel`, `TSkSvg`, `TSkAnimatedImage`, `TAniIndicator`, `TToolBar`, `TGridPanelLayout`, `TFlowLayout`, `TScaledLayout`, `TMultiView`, `TTabItem`, `TStyleBook`, `TTimer`, `TOpenDialog`, `TSaveDialog`, `TActionList`, `TPopupMenu`, `TMainMenu`.

**Règle de génération** : avant chaque émission de `TabOrder = N`, le générateur consulte le `TType` du composant courant. Si non-focusable → ne PAS émettre la ligne.

**Auto-check (script de validation block-aware, cf. fix appliqué 2026-06-22)** :
```python
# Walk .fmx tracking object/end stack, drop TabOrder when current TType in NON_FOCUSABLE set
NON_FOCUSABLE = {'TLabel','TRectangle','TLayout','TPath','TImage','TCircle','TEllipse',
                 'TLine','TPolygon','TArc','TText','TSkLabel','TSkSvg','TAniIndicator',
                 'TToolBar','TGridPanelLayout','TFlowLayout','TScaledLayout','TTimer',
                 'TOpenDialog','TSaveDialog'}
```

### 15.4 Library Paths — env vars vs chemins absolus

**Symptôme** : `[dcc64 Erreur fatale] F2613 Unité 'Spring.Container' non trouvée` malgré `C:\Lib\Spring4D` cloné sur disque.

**Cause** : le `.dproj` référence `$(SPRING4D)\Source` etc. (env vars Windows User-scope), mais : (a) les env vars n'ont jamais été `setx`-ées, OU (b) elles l'ont été mais RAD Studio a été démarré AVANT le `setx` (héritage env du parent au démarrage).

**Règle de génération `arch` Phase A** : au scaffolding `.dproj`, **NE PAS** émettre `$(SPRING4D)`/`$(NEON)`/`$(SKIA4DELPHI)`/`$(TFRAMESTAND)` en `<DCC_UnitSearchPath>`. À la place, émettre les **chemins absolus en clair** :

```xml
<DCC_UnitSearchPath>C:\Lib\Spring4D\Source;C:\Lib\Spring4D\Source\Base;C:\Lib\Spring4D\Source\Base\Collections;C:\Lib\Spring4D\Source\Base\Logging;C:\Lib\Spring4D\Source\Base\Patterns;C:\Lib\Spring4D\Source\Core;C:\Lib\Spring4D\Source\Core\Container;C:\Lib\Spring4D\Source\Core\Logging;C:\Lib\Spring4D\Source\Core\Services;C:\Lib\Neon\Source;C:\Program Files (x86)\Embarcadero\Studio\37.0\source\Skia\Source;$(DCC_UnitSearchPath)</DCC_UnitSearchPath>
```

Trade-off accepté : non portable cross-machine si les libs ne sont pas à `C:\Lib\`, mais **predictable build out-of-the-box** pour le mainteneur. La portabilité passe par documentation dans `CLAUDE.md` projet (sub-section "Pré-requis") :

> Cloner les libs aux emplacements suivants AVANT premier build :
> - `C:\Lib\Spring4D` ← `git clone https://bitbucket.org/sglienke/spring4d.git`
> - `C:\Lib\Neon` ← `git clone https://github.com/paolo-rossi/delphi-neon.git`
> - Skia bundled RAD 12+ : `C:\Program Files (x86)\Embarcadero\Studio\37.0\source\Skia`

Si chemins différents, éditer le `.dproj` `<DCC_UnitSearchPath>` (1 endroit).

**Variante env-var-only (non recommandée)** — si une équipe insiste sur la portabilité via env vars, le scaffolding DOIT générer dans CLAUDE.md projet un bloc PowerShell **exécutable** :
```powershell
[Environment]::SetEnvironmentVariable('SPRING4D', 'C:\Lib\Spring4D', 'User')
[Environment]::SetEnvironmentVariable('NEON', 'C:\Lib\Neon', 'User')
# IMPORTANT : redémarrer RAD Studio APRÈS ce setx (les env vars sont lues au process start)
```
Et un smoke test pré-build qui valide la présence des env vars (`[Environment]::GetEnvironmentVariable('SPRING4D','User')` non-null) avant `MSBuild`.

### 15.5 Docblocks `.pas` avec placeholders — `(*...*)` obligatoire

**Symptôme** : cascade de F2147/F2613/E2029 sur des lignes apparemment correctes ; le compilateur s'arrête à mi-fichier en signalant des identifiers manquants. Au check visuel, on voit `Container.RegisterType<I{Name}ViewModel, T{Name}ViewModel>;` à l'intérieur d'un docblock `{ ... }` Pascal.

**Cause** : Pascal `{ ... }` block comments **ne nest PAS**. Le premier `}` interne ferme le commentaire prématurément. Tout `{Name}`/`{n}-{m}`/`{Domain}`/exemple JSON `{ "key": "..." }` à l'intérieur casse le bloc. La suite est interprétée comme code → cascade de syntax errors.

**Règle de génération** :
1. **Tout docblock multi-lignes en tête de fichier** (`unit X;` puis docblock puis `interface`) DOIT utiliser `(* ... *)`. Les `(*` `*)` ne sont fermés que par `*)` explicite — les `{` `}` à l'intérieur sont du texte littéral.
2. Single-line `{ TFoo }` comments (sans `{` à l'intérieur, juste un titre de section avant une déclaration de classe) — tolérés. Mais `(* TFoo *)` est préféré pour cohérence.
3. **Directives compilateur** (`{$IFDEF X}`, `{$R *.res}`, `{$REGION 'Foo'}`, `{$IFOPT D+}`) — préservées telles quelles, ce sont des directives, pas des commentaires.
4. Ligne-comments `// ...` — toujours valides, jamais piégeux.

**Exemple correct** :
```pascal
unit App.Bootstrap;

(*
  App.Bootstrap.pas — enregistrement DI Spring4D.
  Pour chaque nouvelle US, dev-frontend étend RegisterServices avec :
    Container.RegisterType<IFooService, TFooService>.AsSingleton;
    Container.RegisterType<I{Name}ViewModel, T{Name}ViewModel>;  // {Name} OK ici
  Exemple JSON dans la doc — pas de problème :
    { "key": "value" }
*)

interface
...
```

**Exemple INCORRECT** :
```pascal
unit App.Bootstrap;

{                                                                  ← OUVRE comment level 1
  App.Bootstrap.pas — ...
    Container.RegisterType<I{Name}ViewModel, T{Name}ViewModel>;    ← ICI: 1er `}` ferme le comment
                              ↑              ↑                       (après `Name`)
  Lignes suivantes deviennent du code → ERREUR F2147/F2613
}                                                                  ← orphan, F2147

interface
...
```

**Auto-check** :
```bash
# Détection naive : "{" seul sur sa ligne (signature d'un docblock {} ouvrant)
grep -rlE '^\s*\{[^$].*$' workspace/output/src/{AppName}/ --include="*.pas" --include="*.dpr" 2>/dev/null \
  | xargs -I{} sh -c "head -n 30 '{}' | grep -qE '^\{[^\$]?\s*$' && echo 'DOCBLOCK_BAD: {}'"
# Tout fichier détecté → convertir le docblock { → (*  et } → *).
```

### 15.6 GUIDs d'interface Delphi — hex strict obligatoire

**Symptôme** : `error E2204: Syntaxe GUID incorrecte` sur `['{XXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}']` au compile.

**Cause** : les LLM générant du Pascal aiment encoder un mnémonique signifiant dans la 5e partie du GUID (`'{...-FMXAuthSrv01}'`, `'{...-FMXBabiesRp01}'`, etc.). MAIS un GUID Delphi (et un GUID Windows en général) DOIT être **strictement hexadécimal** : caractères `[0-9A-Fa-f]` uniquement. Les caractères `M`/`X`/`S`/`r`/`v`/`o`/`p`/`L`/`G`/`H`/`I`/`J`/`K`/`N`/`Q`/`R`/`T`/`U`/`W`/`Y`/`Z` sont **invalides**.

**Format canonique** : 8-4-4-4-12 hex (regex `^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$`).

**Règle de génération** : pour tout `interface ... ['{...}']` ou `ProjectGuid` `.dproj`, le LLM/template **NE DOIT PAS** essayer d'encoder un nom dans le GUID. Génération via `[guid]::NewGuid()` PowerShell, `uuid.uuid4()` Python, ou équivalent — toujours hex random standard. La traçabilité unit→GUID se fait via un commentaire `// {Name} interface` au-dessus, pas dans le GUID lui-même.

**Exemple correct** :
```pascal
IAuthService = interface  // FMXNounouJob auth interface
  ['{37DA6A1F-B13A-4D5E-AD9B-A76805E58F84}']  // hex random uuid4
  function Login(...): TAuthResult;
end;
```

**Exemple INCORRECT** :
```pascal
IAuthService = interface
  ['{B2C3D4E5-F6A7-4890-1234-FMXAuthSrv01}']  // ERREUR : `FMXAuthSrv` non hex
end;
```

**Auto-check** :
```bash
grep -rnE "\['\{[0-9A-Fa-f-]*[^0-9A-Fa-f\-\}']" workspace/output/src/{AppName}/ --include="*.pas" \
  && { echo "[DELPHI_GUID_INVALID] GUIDs non-hex détectés"; exit 1; }
```

### 15.7 Unit name = filename (avec les dots)

**Symptôme** : `error E1038: L'identificateur d'unité 'X.Y' ne correspond pas au nom de fichier` au compile.

**Cause** : Delphi exige que la déclaration `unit X.Y.Z;` corresponde au basename du fichier — **avec les dots préservés**. Un fichier `unit Common.AppConfig;` DOIT être nommé `Common.AppConfig.pas`, **PAS** `AppConfig.pas` même s'il est dans un sous-dossier `Common/`. La clause `in 'path'` du `.dpr` ne suffit pas à override cette règle ; elle aide seulement à localiser le fichier.

**Règle de génération** : pour chaque unit `X.Y.Z`, le nom de fichier physique sur disque est `X.Y.Z.pas`. Les sous-dossiers (`Common/`, `Models/`, `Services/Interfaces/`) servent à organiser visuellement mais ne participent PAS au unit name. Le `.dpr` doit déclarer :
```pascal
uses
  Common.AppConfig in 'Common\Common.AppConfig.pas',     (* ← répétition du basename *)
  Models.LoginRequest in 'Models\Models.LoginRequest.pas',
  ...
```
Et le `.dproj` doit avoir `<DCCReference Include="Common\Common.AppConfig.pas"/>` correspondant.

**Variante** : si l'équipe préfère des basenames courts (`AppConfig.pas` sans le `Common.` prefix), alors la déclaration `.pas` doit être `unit AppConfig;` (sans namespace). Mais cela perd la disambigüation (`Common.AppConfig` vs `UI.AppConfig` ne peuvent plus coexister).

**Convention SDD_Pro adoptée** : **unit name = path-flat dotted name = basename** (la plus stricte). Permet la coexistence de noms identiques entre dossiers (`UI.Babies.BabyDetail` et `ViewModels.Babies.BabyDetailViewModel`).

**Auto-check** :
```python
# Pour chaque .pas : vérifier que basename == unit_name + '.pas'
for p in pathlib.Path(root).rglob('*.pas'):
    text = p.read_bytes().decode('utf-8', errors='replace').lstrip('﻿')
    m = re.search(r'(?im)^\s*unit\s+([\w\.]+)\s*;', text)
    if m and (m.group(1) + '.pas').lower() != p.name.lower():
        raise Error(f'[DELPHI_UNIT_NAME_MISMATCH] {p}: unit={m.group(1)} ≠ basename={p.stem}')
```

> **Piège connexe** : le BOM UTF-8 en tête de fichier (`﻿`) peut empêcher des regex naïfs de matcher `^unit X;` — toujours strip BOM avant parsing. Décoder via `read_bytes().decode('utf-8-sig')` (utf-8-sig = utf-8 + BOM stripping automatique).

### 15.8 `Winapi` dans `DCC_Namespace` (obligatoire pour Spring4D + libs Windows)

**Symptôme** : `error F2613: Unité 'Windows' non trouvée` sur une lib bundled (`Spring.pas`, `Spring.Patches.RSP*.pas`, `Spring.VirtualInterface.pas`, etc.).

**Cause** : les libs Delphi historiques (Spring4D, Indy, JCL/JVCL, etc.) référencent `uses Windows;` (nom court). Delphi moderne (XE2+) a renommé l'unité en `Winapi.Windows`. Le compilateur résout `Windows` → `Winapi.Windows` UNIQUEMENT si `Winapi` figure dans la liste `<DCC_Namespace>` du `.dproj`. Sans cette entrée, F2613.

**Règle de génération `arch`** : la chaîne `DCC_Namespace` du `.dproj` DOIT inclure **`Winapi`** dès qu'une lib externe (Spring4D, Neon, Skia, Indy, etc.) est listée en `<DCC_UnitSearchPath>`. Template canonique :
```xml
<DCC_Namespace>System;Xml;Data;Datasnap;Web;Soap;Winapi;Vcl;Vcl.Imaging;Vcl.Touch;Vcl.Samples;Vcl.Shell;FMX;FMX.Types;$(DCC_Namespace)</DCC_Namespace>
```

Ne PAS omettre `Winapi` même pour un projet FMX cross-platform — la plupart des libs ont des sections `{$IFDEF MSWINDOWS} uses Windows; {$ENDIF}` et le compile Win64 a besoin de la résolution.

### 15.9 Spring4D — sous-dossiers de search path complets

**Symptôme** : cascade `F2613` sur `Spring.Container.ProxyFactory.pas`, `Spring.Patches.RSP13163.pas`, etc.

**Cause** : Spring4D `Source/` éclate ses unités dans **8+ sous-dossiers**. Référencer seulement `$(SPRING4D)\Source` en `DCC_UnitSearchPath` est insuffisant — chaque sous-dossier doit être listé explicitement (le DCC ne récurse pas).

**Liste canonique des sous-dossiers Spring4D à inclure** :
```
C:\Lib\Spring4D\Source
C:\Lib\Spring4D\Source\Base
C:\Lib\Spring4D\Source\Base\Collections
C:\Lib\Spring4D\Source\Base\Logging
C:\Lib\Spring4D\Source\Base\Patches            ← Spring.Patches.RSP*.pas
C:\Lib\Spring4D\Source\Base\Patterns
C:\Lib\Spring4D\Source\Core
C:\Lib\Spring4D\Source\Core\Container
C:\Lib\Spring4D\Source\Core\Interception       ← Spring.Interception.pas
C:\Lib\Spring4D\Source\Core\Logging
C:\Lib\Spring4D\Source\Core\Services
```

**Règle de génération `arch`** : si Spring4D est dans les CORE libs (cf. `delphi-fmx.libs.json#core`), `arch` émet ces 11 entrées en `<DCC_UnitSearchPath>` sans exception. Pour Data/Persistence/Extensions Spring4D (capabilities ON-DEMAND), ajouter `Source\Data`, `Source\Extensions`, `Source\Persistence` à la demande.

### 15.10 Récap : ordre de validation post-génération FMX

Pour chaque US dev-frontend qui produit du Delphi FMX :

```
1.  (a) .fmx CRLF  +  (b) zéro commentaire dans .fmx           (§15.1)
2.  propriétés Integer en literal int                           (§15.2)
3.  TabOrder uniquement sur focusables                          (§15.3)
4.  .dproj DCC_UnitSearchPath en absolu + Winapi namespace      (§15.4, §15.8)
5.  Spring4D : 11 sous-dossiers dans UnitSearchPath             (§15.9)
6.  docblocks .pas en (* ... *)                                 (§15.5)
7.  GUIDs interface : hex strict (regex 8-4-4-4-12)            (§15.6)
8.  Unit name == basename .pas (avec les dots)                  (§15.7)
9.  .dpr préserve {FormName} (PAS de conversion {} → (* *))     (§15.5 + §15.13)
10. Spring4D : delegate factory passe à RegisterType<T>(…),
    PAS à AsSingleton(…)                                        (§15.11)
11. .dproj : chaîne de propagation <Base>true</Base> dans
    chaque Cfg_X_<Platform> PropertyGroup                       (§15.12)
12. MSBuild /p:Platform=Win64 /t:Build → 0 erreur dcc           (smoke §12)
13. Application.exe se lance + form principal apparaît          (manuel ou Playwright FMX si dispo)
```

Si une de ces étapes 1-11 échoue → STOP + ERROR avec préfixe approprié :
`[FMX_COMMENT_FORBIDDEN]`, `[FMX_LF_LINE_ENDINGS]`, `[FMX_INT_PROP_FLOAT]`, `[FMX_TABORDER_INVALID]`, `[DELPHI_LIBPATH_MISSING]`, `[DELPHI_DOCBLOCK_BRACE]`, `[DELPHI_GUID_INVALID]`, `[DELPHI_UNIT_NAME_MISMATCH]`, `[DELPHI_NAMESPACE_MISSING]`, `[DELPHI_DI_DELEGATE_API]`, `[DELPHI_DPROJ_BASE_CHAIN]`.

> Ces classes d'erreur sont **spécifiques delphi-fmx** ; elles peuvent à terme être hoistées dans `error-classification.md §1.X` quand le stack passe en `🟢 bench-validated runtime`.

### 15.11 Spring4D — delegate factory passe à `RegisterType<T>(…)`, PAS à `AsSingleton(…)`

**Symptôme** : `[dcc64] App.Bootstrap.pas(NN): E2010 Types incompatibles : 'Spring.Container.Common.TRefCounting' et 'Procedure'` puis cascade `F2063 Impossible de compiler l'unité utilisée 'App.Bootstrap.pas'` et `F2613` apparents sur les uses suivants dans `.dpr` (le compilateur s'arrête à mi-fichier ce qui maquille la vraie cause).

**Cause** : confusion sur les overloads Spring4D. `TRegistration.AsSingleton` prend **uniquement** un `TRefCounting` optionnel ; il ne prend **JAMAIS** un delegate de fabrique :
```pascal
// Source/Core/Container/Spring.Container.Registration.pas:134
function AsSingleton(refCounting: TRefCounting = TRefCounting.Unknown): TRegistration;
```

C'est `TContainer.RegisterType<T>` qui a l'overload acceptant un `TActivatorDelegate<T>` :
```pascal
// Source/Core/Container/Spring.Container.pas:109-110
function RegisterType<TComponentType>(
  const delegate: TActivatorDelegate<TComponentType>): TRegistration; overload; inline;
```

**Anti-pattern (généré à éviter)** :
```pascal
Container.RegisterType<THTTPClient>.AsSingleton(   // ← AsSingleton(delegate) N'EXISTE PAS
  function: THTTPClient
  begin
    Result := THTTPClient.Create;
    Result.ConnectionTimeout := 10000;
  end
);
```

**Pattern correct** :
```pascal
Container.RegisterType<THTTPClient>(               // ← delegate passé à RegisterType<T>
  function: THTTPClient
  begin
    Result := THTTPClient.Create;
    Result.ConnectionTimeout := 10000;
  end
).AsSingleton;                                     // ← AsSingleton chaîné, sans argument
```

**Variantes (toutes valides)** :
```pascal
// 1. Registration simple (ctor par défaut) — pas de delegate
Container.RegisterType<IAuthService, TAuthService>.AsSingleton;

// 2. Registration avec service interface + delegate
Container.RegisterType<IFooService, TFooService>(
  function: TFooService begin Result := TFooService.Create(SomeConfig); end
).AsSingleton;

// 3. Registration Transient (par défaut) avec delegate
Container.RegisterType<TBarVM>(
  function: TBarVM begin Result := TBarVM.Create; end
);

// 4. Instance pré-construite — pas de RegisterType, c'est RegisterInstance
Container.RegisterInstance<TAppConfig>(Config);
```

**Règle de génération `arch` / `dev-frontend`** : toute génération de `App.Bootstrap.pas` ou d'un Service avec factory dans le `RegisterServices` DOIT placer le delegate **dans** `RegisterType<T>(…)` et chaîner `.AsSingleton` **sans argument** (ou laisser Transient par défaut). Aucun `.AsSingleton(function …)` autorisé.

**Détection** (post-génération `.pas`) :
```regex
\bAsSingleton\s*\(\s*(?!\s*TRefCounting\b)[^)]*\bfunction\b
```
Match → STOP + ERROR `[DELPHI_DI_DELEGATE_API]`.

> Source canonique : `Spring4D@master` (commit "Delphi 13 support") — `Source/Core/Container/Spring.Container.pas` et `Spring.Container.Registration.pas`. Compatible Delphi 11 Alexandria / 12 Athens / 13 Florence.

---

### 15.12 `.dproj` — chaîne de propagation `<Base>true</Base>` pour activation IDE

**Symptôme** : `[dcc64 Erreur fatale] {AppName}.dpr(NN): F2613 Unité 'Spring.Container' non trouvée.` **uniquement** quand le build est lancé depuis l'IDE RAD Studio (Project → Build). Le même `.dproj` builde **vert** via `msbuild` en ligne de commande (`rsvars.bat && msbuild /p:Config=Debug /p:Platform=Win64`). Le `DCC_UnitSearchPath` est pourtant correctement présent dans le `.dproj` et pointe sur des chemins existants.

**Cause** : RAD Studio IDE active les PropertyGroups en cascade via le mécanisme `'$(Config)'=='Cfg_X_<Platform>'`, **pas** en lisant `<Base>True</Base>` dans le PropertyGroup initial inconditionnel. Si la chaîne de propagation est incomplète, la variable `$(Base)` reste vide quand l'IDE résout `Cfg_1_Win64`, donc le PropertyGroup `Condition="'$(Base)'!=''"` (qui contient le `DCC_UnitSearchPath`) **ne s'active pas**, et le compilateur invoqué par l'IDE part avec un search path vide → `F2613` sur la première lib non-RTL.

MSBuild en ligne de commande, lui, traite le fichier top-down et voit `<Base>True</Base>` dans le 1er PropertyGroup avant d'évaluer la condition — d'où le faux signal "ça marche en CLI mais pas en IDE".

**Anti-pattern (généré à éviter)** :
```xml
<PropertyGroup>
    <Base>True</Base>          <!-- ← suffit pour MSBuild, PAS pour l'IDE -->
    <Config Condition="'$(Config)'==''">Debug</Config>
    <Platform Condition="'$(Platform)'==''">Win64</Platform>
</PropertyGroup>

<PropertyGroup Condition="'$(Base)'!=''">
    <DCC_UnitSearchPath>C:\Lib\Spring4D\...</DCC_UnitSearchPath>
</PropertyGroup>

<!-- ❌ MANQUE : groupes Cfg_X / Cfg_X_<Platform> avec propagation Base -->
<PropertyGroup Condition="'$(Cfg_1)'!=''">         <!-- Cfg_1 active sans propager Base -->
    <DCC_Define>DEBUG;$(DCC_Define)</DCC_Define>
</PropertyGroup>
```

**Pattern correct (style RAD-generated standard)** :
```xml
<PropertyGroup>
    <ProjectGuid>{...}</ProjectGuid>
    <Base>True</Base>          <!-- conservé pour MSBuild standalone -->
    <Config Condition="'$(Config)'==''">Debug</Config>
    <Platform Condition="'$(Platform)'==''">Win64</Platform>
</PropertyGroup>

<!-- Chaîne de propagation : chaque Cfg_X et Cfg_X_<Platform> re-déclare Base=true -->
<PropertyGroup Condition="'$(Config)'=='Base' or '$(Base)'!=''">
    <Base>true</Base>
</PropertyGroup>
<PropertyGroup Condition="'$(Config)'=='Base_Win64' or '$(Base_Win64)'!=''">
    <Base_Win64>true</Base_Win64>
    <CfgParent>Base</CfgParent>
    <Base>true</Base>
</PropertyGroup>
<PropertyGroup Condition="'$(Config)'=='Cfg_1' or '$(Cfg_1)'!=''">
    <Cfg_1>true</Cfg_1>
    <CfgParent>Base</CfgParent>
    <Base>true</Base>          <!-- ← propagation critique -->
</PropertyGroup>
<PropertyGroup Condition="'$(Config)'=='Cfg_1_Win64' or '$(Cfg_1_Win64)'!=''">
    <Cfg_1_Win64>true</Cfg_1_Win64>
    <CfgParent>Cfg_1</CfgParent>
    <Cfg_1>true</Cfg_1>
    <Base>true</Base>          <!-- ← propagation critique -->
</PropertyGroup>
<PropertyGroup Condition="'$(Config)'=='Cfg_2' or '$(Cfg_2)'!=''">
    <Cfg_2>true</Cfg_2>
    <CfgParent>Base</CfgParent>
    <Base>true</Base>
</PropertyGroup>
<PropertyGroup Condition="'$(Config)'=='Cfg_2_Win64' or '$(Cfg_2_Win64)'!=''">
    <Cfg_2_Win64>true</Cfg_2_Win64>
    <CfgParent>Cfg_2</CfgParent>
    <Cfg_2>true</Cfg_2>
    <Base>true</Base>
</PropertyGroup>

<!-- Le groupe Base qui porte DCC_UnitSearchPath/DCC_Namespace s'active désormais
     que la résolution vienne de CLI MSBuild OU de l'IDE -->
<PropertyGroup Condition="'$(Base)'!=''">
    <DCC_UnitSearchPath>C:\Lib\Spring4D\...</DCC_UnitSearchPath>
    <DCC_Namespace>System;...;Winapi;...;FMX;FMX.Types;$(DCC_Namespace)</DCC_Namespace>
    ...
</PropertyGroup>
```

**Règle de génération `arch`** : pour chaque target Platform déclaré (`Win32`, `Win64`, `Android64`, `iOSDevice64`, `OSX64ARM`), émettre la paire `Cfg_1_<Platform>` (Debug) + `Cfg_2_<Platform>` (Release) avec **propagation explicite de `<Base>true</Base>`** dans chaque PropertyGroup. Pour les targets multi-plateformes (Android + iOS + Windows), c'est 1 paire par plateforme = jusqu'à 8 PropertyGroups de propagation.

**Détection** (post-génération `.dproj`) :
```bash
# Compter les PropertyGroups Cfg_X qui activent et qui propagent Base
grep -c "Condition=\"'\$(Config)'=='Cfg_" {AppName}.dproj          # ≥ 4 (Cfg_1, Cfg_1_Win64, Cfg_2, Cfg_2_Win64)
grep -A3 "'\$(Cfg_" {AppName}.dproj | grep -c "<Base>true</Base>"  # doit ≥ nombre de Cfg_X groups
```
Si mismatch → STOP + ERROR `[DELPHI_DPROJ_BASE_CHAIN]`.

**Pourquoi pas seulement « duppliquer `DCC_UnitSearchPath` dans chaque Cfg_X_<Platform> »** : ferait gonfler le `.dproj` (× nombre de plateformes × nombre de configs), introduit du drift quand on patch un seul des duplicatas, casse l'override de Project Options par configuration. La propagation `<Base>true</Base>` est la convention RAD officielle.

**Reset après application du patch** :
```bash
# Côté Tech Lead, après que arch a réécrit le .dproj :
# 1. Fermer le projet dans RAD Studio (File → Close All)
# 2. Supprimer le cache .dcu obsolète :
rm -rf workspace/output/src/{AppName}/Win64
rm -rf workspace/output/src/{AppName}/__recovery
# 3. Rouvrir {AppName}.dproj → Project → Clean → Project → Build
```

> Source canonique : `.dproj` générés par File → New → Multi-Device Application dans RAD Studio 12+ (échantillon vérifié 2026-06-22). MSBuild 4.8 + DCC64 37.0 ne tolèrent pas la version « short » (sans chaîne de propagation) côté IDE.

---

### 15.13 Cas spécial — `.dpr` et le syntaxe `{FormName}`

**Symptôme** : le fichier `.dpr` perd l'association IDE entre l'unit et la Form après un sweep de conversion automatique des commentaires.

**Cause** : la grammaire `.dpr` utilise une construction qui RESSEMBLE à un commentaire `{}` mais qui est en fait du **syntaxe spécifique IDE** :
```pascal
uses
  UI.Main in 'UI\UI.Main.pas' {MainForm},      ← {MainForm} = alias form, PAS un commentaire
  UI.Auth.Login in 'UI\Auth\UI.Auth.Login.pas' {LoginForm};
```

Le compilateur tolère `{MainForm}` comme commentaire, mais l'IDE l'utilise pour associer la Form `MainForm` à l'unit `UI.Main`. **Le convertir en `(*MainForm*)` casse l'association IDE** (le designer ne peut plus ouvrir la Form depuis Project Manager) même si le compile passe.

**Règle de génération / conversion** : tout script qui fait du sweep `{ → (*` / `} → *)` sur des fichiers Pascal DOIT **whitelister** les fichiers `.dpr` ET les patterns `{Identifier}` qui suivent un `in 'path.pas'` (clause de mapping unit/path). Le pattern strict à préserver :
```
(?:in\s+'[^']+\.pas')\s*\{[A-Za-z_]\w*\}
```

Si la conversion `{} → (* *)` a déjà été faite sur un `.dpr`, restaurer manuellement :
```
sed -i "s|\.pas' (\*\([A-Za-z_][A-Za-z0-9_]*\)\*)|.pas' {\1}|g" *.dpr
```

### 15.14 Field labels vs placeholders — ne pas inventer de `TLabel` au-dessus des inputs

**Symptôme** : la maquette HTML ne contient AUCUN `<label>` au-dessus d'un input (le design délègue à un `placeholder=` ou à une icône leading dans la box), mais le `.fmx` généré contient un `TLabel` "Email" / "Mot de passe" / "Nom" / etc. juste avant le `TRectangle` de l'input. Résultat : doublon visuel (label texte + placeholder identique) qui pollue le mockup et trahit la fidélité.

**Cause** : confusion entre la classe CSS `.field label` **définie** dans le `<style>` et son utilisation **réelle** dans le markup `<body>`. Une classe `.field label{...}` peut être déclarée pour d'autres écrans, sans être instanciée sur celui-ci. La discipline HTML→FMX impose de regarder le **markup réel** (`<body>`), pas la stylesheet.

**Règle de génération** :

1. Pour CHAQUE `<input>` du markup, identifier le `<label>` associé en remontant l'arbre DOM :
   - `<label for="X">` ou `<label>...<input id="X">...</label>` (sibling/parent direct) → générer `TLabel` au-dessus du `TRectangle`.
   - `<input placeholder="X">` SANS `<label>` → générer **uniquement** `TRectangle + TEdit` avec `TextPrompt = 'X'`. **AUCUN `TLabel` au-dessus.**
   - Icône leading SVG (`<svg class="lead">` dans `.input`) → mapper en `TPath` enfant aligné `Left` du `TRectangle`, **pas** en label.
2. Hauteur `LayoutField*` : `52` (input seul) ou `78` (label + 6px gap + input). Le choix dépend du markup HTML réel, pas du CSS.
3. Anti-pattern formel : tout `TLabel` qui répète à l'identique le `TextPrompt` du `TEdit` adjacent est suspect. Audit grep recommandé en checklist post-génération §13.12 :
   ```bash
   grep -B2 "TextPrompt = '[A-Za-z]" *.fmx | grep -B1 "Text = '" | grep -i "Text = '\(Email\|Mot de passe\|Nom\|Adresse\)"
   ```

**Cas réel ayant motivé cette règle** (FMXNounouJob 1-Spec-Connexion, 2026-06-22) : `LblEmailLabel` + `LblPasswordLabel` générés alors que le HTML utilise seulement `<input placeholder="Email">` + icône SVG dans `.input`. Correction = retirer les deux `TLabel`, réduire `LayoutFieldEmail.Size.Height` 78 → 52.

---

### 15.15 `TButton` coloré custom — `StyleLookup` orphelin = couleur platform par défaut

**Symptôme** : un mockup HTML décrit un bouton primaire coloré (`background:var(--nj-coral-500)`) ; le `.fmx` généré contient `BtnLogin: TButton` avec `StyleLookup = 'nj.btn.primary'`, mais visuellement le bouton apparaît en gris/bleu platform-default (Windows : bleu système ; macOS : gris natif) au lieu de coral. La couleur du token est ignorée.

**Cause** : `TButton` est un `TStyledControl` dont le rendu est **entièrement piloté par un `TButtonStyleObject`** dans le `TStyleBook` actif. Référencer `StyleLookup = 'nj.btn.primary'` quand `tokens.style` ne contient qu'un `TBrushObject` du même nom (couleur seule) **ne suffit pas** — `TButton` n'utilise pas `TBrushObject` pour son fond. Le `StyleLookup` orphelin (pointant vers un nom inexistant ou incompatible) fait fallback sur le style platform-default.

**Règle de génération** (deux options, choisir en début d'US) :

**Option A — Pattern `TRectangle + TLabel` (recommandé pour boutons primaires brandés)** :

```pascal
object BtnLogin: TRectangle
  Align = Top
  Size.Height = 52.000000000000000000
  Fill.Color = xFFBE5060           { token nj.brand.primary depuis tokens.style }
  Fill.Kind = Solid
  Stroke.Kind = None
  XRadius = 14.000000000000000000
  YRadius = 14.000000000000000000
  HitTest = True
  Cursor = crHandPoint
  OnClick = BtnLoginClick

  object LblBtnLoginText: TLabel
    Align = Center
    HitTest = False
    StyledSettings = [Family, Other]
    TextSettings.HorzAlign = Center
    TextSettings.VertAlign = Center
    TextSettings.Font.Size = 15.000000000000000000
    TextSettings.Font.Style = [fsBold]
    TextSettings.FontColor = claWhite
    Text = 'Se connecter'
  end
end
```

Côté `.pas` : `BtnLogin: TRectangle` (pas `TButton`), `LblBtnLoginText: TLabel` séparé, mutations texte via `LblBtnLoginText.Text := '...'` (et non `BtnLogin.Text`). Visuel disabled = `BtnLogin.Opacity := 0.6` (TRectangle n'a pas d'état disabled platform-default visible). **Retirer `TabOrder`** sur `BtnLogin` car `TRectangle` n'est pas focusable (cf. §15.3).

**Option B — `TButton` + style complet dans `tokens.style`** : créer un `TButtonStyleObject` complet avec `background`, `text`, `glyph`, états `hot/pressed/disabled`. Lourd : ~80 lignes de style. À réserver aux design systems nombreux boutons (> 5 variantes) où la duplication d'Option A coûterait plus.

**Anti-règle** : ne JAMAIS référencer un `StyleLookup` qui pointe vers un `TBrushObject` seul (`nj.brand.primary`) en pensant que ça suffit à colorer un `TButton`. Si `tokens.style` n'a pas un `TButtonStyleObject` (ou `TStyleObject` couvrant tout le template `TButton`) du même nom, utiliser Option A.

**Audit post-génération** :
```bash
grep -E "StyleLookup\s*=\s*'nj\.btn\." *.fmx
# Pour chaque match : vérifier que tokens.style contient TStyleObject (PAS uniquement TBrushObject) avec ce StyleName
```

**Cas réel** : FMXNounouJob 1-Spec-Connexion (2026-06-22) — `BtnLogin: TButton StyleLookup = 'nj.btn.primary'` mais `tokens.style` ne contient que `TBrushObject StyleName = 'nj.brand.primary'`. Aucun `TStyleObject` `nj.btn.primary`. Résultat : bouton platform-default. Correction = conversion en `TRectangle + TLabel`.

---

### 15.16 `TCheckBox` — la couleur du check est non-customisable sans style complet

**Symptôme** : un mockup HTML décrit une checkbox avec un état coché coloré custom (ex. `.check input:checked+.check__box{background:var(--nj-coral-500)}`) ; le `.fmx` généré utilise `TCheckBox` standard, et visuellement le check apparaît avec l'accent platform-default (Windows : bleu système ; macOS : bleu natif) — **jamais coral**.

**Cause** : `TCheckBox` est un `TStyledControl` dont l'aspect visuel (case + check + accent quand `IsChecked`) est entièrement défini par le `TCheckBoxStyleObject` du `TStyleBook` actif. La propriété `TintColor` (introduite RAD 11) **n'est pas universellement respectée** sur toutes les plateformes (Android/iOS l'honorent partiellement, Windows VCL-style l'ignore). Aucune propriété simple `BoxColor` / `CheckColor` n'existe.

**Règle de génération** (deux options) :

**Option A — Pattern `TLayout + TRectangle + TPath + TLabel` (custom, fidèle au design)** :

```pascal
object LayoutRememberToggle: TLayout
  Align = Left
  Size.Width = 200.000000000000000000
  Size.Height = 24.000000000000000000
  Cursor = crHandPoint
  HitTest = True
  OnClick = LayoutRememberToggleClick

  object RectRememberBox: TRectangle
    Align = Left
    Size.Width = 20.000000000000000000
    Size.Height = 20.000000000000000000
    Margins.Top = 2.000000000000000000
    Fill.Color = xFFBE5060           { coral quand IsChecked = True ; xFFFFFFFF sinon }
    Fill.Kind = Solid
    Stroke.Color = xFFBE5060         { coral quand IsChecked = True ; xFFE5E2E8 sinon }
    Stroke.Thickness = 1.500000000000000000
    XRadius = 6.000000000000000000
    YRadius = 6.000000000000000000
    HitTest = False

    object PathRememberCheck: TPath
      Align = Center
      Size.Width = 12.000000000000000000
      Size.Height = 8.000000000000000000
      Stroke.Color = claWhite
      Stroke.Thickness = 2.000000000000000000
      Fill.Kind = None
      Data.Data = 'M 0 4 L 4 8 L 12 0'
      Visible = True             { masqué quand non coché }
      HitTest = False
    end
  end

  object LblRememberText: TLabel
    Align = Client
    Margins.Left = 10.000000000000000000
    StyledSettings = [Family, Style, Other]
    TextSettings.VertAlign = Center
    TextSettings.Font.Size = 13.000000000000000000
    TextSettings.FontColor = xFF666280
    Text = 'Rester connectee'
    HitTest = False
  end
end
```

Côté `.pas` : champ privé `FRememberChecked: Boolean` source de vérité (ou bind direct VM) ; `LayoutRememberToggleClick` toggle l'état + met à jour `RectRememberBox.Fill.Color` (coral si checked, blanc sinon), `RectRememberBox.Stroke.Color`, `PathRememberCheck.Visible`. Pas de `TCheckBox` du tout — donc pas de `TabOrder` (TLayout/TRectangle non focusables, cf. §15.3). Pour préserver l'accessibilité clavier : ajouter un `TSpeedButton` invisible qui capture Tab et délègue OnClick, OU rester sur Option B.

**Option B — `TCheckBox` standard, accepter le visuel platform-default** : utiliser quand la cohérence visuelle exacte avec le mockup n'est pas critique (ex. écrans internes / admin), OU quand `TabOrder` est requis. Le `TCheckBox` reste fonctionnel (`IsChecked`, `OnChange`) — seul l'accent du check ne sera pas coral. **Documenter explicitement** dans le rapport de fidélité de l'US ("checkbox utilise accent platform-default — color override `nj.brand.primary` non appliqué").

**Anti-règle** : ne JAMAIS prétendre dans un rapport de fidélité que `TCheckBox` standard rend `var(--nj-coral-500)` quand coché — c'est physiquement faux sur la majorité des plateformes. Soit Option A (custom layout), soit déclarer ouvertement le gap.

**Cas réel** : FMXNounouJob 1-Spec-Connexion (2026-06-22) — `ChkRememberMe: TCheckBox` avec `IsChecked = True` mais accent visuel platform-default (pas coral). Gap accepté et documenté ici, MD règle ajoutée pour ne plus reproduire la confusion silencieuse.

---

> Source du mapping HTML→FMX (§13) : référentiel `HtmlToFmx.md` v1.0 + skill `fmx-ui.md` v1.0 (Andrea Magni / DocWiki) — intégrés ici comme source de vérité du framework SDD_Pro pour le stack `delphi-fmx`.
