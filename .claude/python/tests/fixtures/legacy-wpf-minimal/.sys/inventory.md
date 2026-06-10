# Inventaire — legacy-wpf-minimal

**Date scan** : 2026-06-10T21:10:47Z
**Durée scan** : 6 ms
**Langage principal** : `wpf-xaml`

## Langages détectés

| ID | Label | Confiance | Fichiers | LOC |
|---|---|---|---:|---:|
| `wpf-xaml` | WPF (.NET Framework + Core/.NET 5+) | high | 3 | 61 |
| `csharp` | C# (générique, hors MVC/WebForms) | low | 1 | 21 |

## Frameworks détectés

_Aucun framework signé._

## Pages (3)

- `App.xaml` — 11 LOC, lié à []
- `Views/LoginWindow.xaml` / code-behind `Views/LoginWindow.xaml.cs` — 26 LOC, lié à ['U-1']
- `Views/UsersListPage.xaml` — 24 LOC, lié à ['U-2']

## Unités fonctionnelles candidates (2)

- **U-1** — Formulaire Loginwindow _(suggéré: `Loginwindow`)_ — kind: form, confiance: medium
  - Seed : `Views/LoginWindow.xaml`, `Views/LoginWindow.xaml.cs`
  - Classes (1) — code-behind: LoginWindow
  - Rationale : Page Views/LoginWindow.xaml classified as form (score=1.40)
- **U-2** — Liste Userslistpage _(suggéré: `Userslistpage`)_ — kind: grid, confiance: medium
  - Seed : `Views/UsersListPage.xaml`
  - Rationale : Page Views/UsersListPage.xaml classified as grid (score=1.30)

## Synthèse technique (L1)

**Classes par rôle** : code-behind: 1
**Accès données** : 0 requête(s) SQL inline, 0 appel(s) de procédure, 0 procédure(s) stockée(s) définie(s).

