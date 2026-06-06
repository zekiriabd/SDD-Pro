# FEAT: Calc-A-B-C-MAUI

FEAT ID: 15-Calc-A-B-C-MAUI
Status: Draft

## Context
FEAT 12 a livré Kotlin Android natif (scaffold-only car Android SDK absent). MAUI workloads sont **installés** sur ce poste (`maui-windows`, `android`, `ios`, `maccatalyst`) → on peut **réellement builder** la cible Windows desktop natif (`net8.0-windows10.0.19041.0`) sans émulateur.

## Objective
Scaffolder + builder une application .NET MAUI cross-platform (cible Windows desktop) qui consomme le backend FastAPI :44329 via HttpClient. Démontre le pattern cross-platform .NET (1 codebase XAML/C# → Windows + iOS + Android + macOS).

## Quantified Goal
- Metric: app MAUI Windows compilée + exécutable + consomme backend FastAPI runtime
- Target: build réussi sur cible `net8.0-windows10.0.19041.0` + app lancée + Calculate fonctionnel
- Deadline: 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a
- Performance SLA: démarrage app < 5s (MAUI WinUI3 cold start)
- Data retention: n/a
- Compliance: n/a
- Integration: backend FastAPI :44329 via `HttpClient` (apps natives non soumises à CORS)
- Degraded mode: backend down → DisplayAlert "API non joignable"

## Actors
- Tech Lead
- Système Mobile/Desktop (MAUI): .NET 8 cross-platform XAML

## Functional Needs
- SFD-1: scaffold `dotnet new maui -f net8.0`
- SFD-2: page XAML `MainPage.xaml` avec 3 Entry (A, B, C readonly) + Button Calculate
- SFD-3: code-behind `MainPage.xaml.cs` avec HttpClient.PostAsJsonAsync vers `:44329/api/calc`
- SFD-4: target framework `net8.0-windows10.0.19041.0` (Windows desktop, pas d'émulateur requis)
- SFD-5: `appsettings.json` MauiAssets pour API base URL configurable

## Business Rules
- BR-1: A et B int (`int.TryParse` Entry.Text — sinon disabled)
- BR-2: calcul C exécuté côté backend FastAPI (preuve via HttpClient response)
- BR-3: pas d'authentification
- BR-4: .NET 8 LTS (MAUI workload installé)

## Acceptance Criteria
- AC-1: `dotnet build -f net8.0-windows10.0.19041.0` réussit (preuve scaffold + workloads OK)
- AC-2: `dotnet run -f net8.0-windows10.0.19041.0` lance la fenêtre WinUI3 avec form 3 champs + Button
- AC-3: clic Calculate → fetch :44329/api/calc → C affiché dans Entry C

## Dependencies
- 1-Calc-A-B-C (contrat HTTP cible)
- 13-Calc-Backend-Python (backend actif :44329)

## Functional Deliverables
- FD-1: scaffolding `dotnet new maui`
- FD-2: `MainPage.xaml` customisé
- FD-3: `MainPage.xaml.cs` avec HttpClient

## Out of Scope
- Cibles iOS/Android/macOS (Windows uniquement pour bench — émulateurs lourds)
- Authentification MSAL
- Persistance EF Core
- Tests xunit
