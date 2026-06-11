# Inventaire — legacy-api-minimal

**Date scan** : 2026-06-11T12:00:19Z
**Durée scan** : 2 ms
**Langage principal** : `csharp`

## Langages détectés

| ID | Label | Confiance | Fichiers | LOC |
|---|---|---|---:|---:|
| `csharp` | C# (générique, hors MVC/WebForms) | medium | 5 | 124 |

## Frameworks détectés

_Aucun framework signé._

## Pages (0)


## Unités fonctionnelles candidates (2)

- **U-1** — API Orders _(suggéré: `Orders`)_ — kind: api, confiance: medium
  - Seed : `Controllers/OrdersController.cs`
  - Evidence profonde (graphe) : `Models/OrderDto.cs`, `Services/OrderService.cs`, `Repositories/OrderRepository.cs`
  - Classes (4) — controller: OrdersController; dto: OrderDto; repository: OrderRepository; service: OrderService
  - Accès données : 2 requête(s) SQL, 0 appel(s) de procédure
    - `SELECT` sur ['Orders'] (`Repositories/OrderRepository.cs:19`)
    - `INSERT` sur ['Orders'] (`Repositories/OrderRepository.cs:37`)
  - Rationale : Controller OrdersController (Controllers/OrdersController.cs) — surface API/MVC, 4 classe(s) atteinte(s).
- **U-2** — Module Jobs _(suggéré: `Jobs`)_ — kind: module, confiance: medium
  - Seed : `Jobs/NightlyCleanupJob.cs`
  - Classes (1) — classic: NightlyCleanupJob
  - Rationale : Module backend `LegacyApi.Jobs` — 1 classe(s) métier (classic), aucune page UI rattachée. Ancre : NightlyCleanupJob.

## Synthèse technique (L1)

**Classes par rôle** : classic: 1, controller: 1, dto: 1, repository: 1, service: 1
**Accès données** : 2 requête(s) SQL inline, 0 appel(s) de procédure, 0 procédure(s) stockée(s) définie(s).

**Librairies à installer (1)** :
- `Dapper` 2.1.35 (nuget) — `LegacyApi.csproj:6`

