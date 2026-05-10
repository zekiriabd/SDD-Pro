# UI Design System: Radzen (Blazor)

> MCP server disponible : le projet peut declarer un serveur MCP Radzen
> permettant d’acceder a la documentation officielle des composants.
> Si disponible, l’agent DOIT l’utiliser pour recuperer :
> - les proprietes exactes
> - les evenements
> - les types attendus
> Sinon, ce document devient la reference principale.

---

Status: Draft  
UI Spec ID: radzen-blazor  
Scope: design system Radzen.Blazor — composants UI pour applications Blazor Server et Blazor WebAssembly

---

## 1. Identite du design system

- Nom : Radzen.Blazor
- Framework cible : Blazor (Server et WebAssembly)
- Librairie UI complete basee sur composants
- Fournit :
  - composants UI riches
  - systeme de layout
  - navigation
  - services UX (dialog, notification, tooltip)

Objectif pour l’IA :

- Comprendre que Radzen est un **design system complet**
- Ne jamais reconstruire des composants existants
- Toujours utiliser les composants natifs Radzen

---

## 2. Mapping element UI fonctionnel → composant Radzen

L’agent DOIT utiliser exclusivement les composants Radzen suivants
selon l’intention fonctionnelle.

### Layout et structure

- Layout global → RadzenLayout
- Header → RadzenHeader
- Sidebar → RadzenSidebar
- Contenu principal → RadzenBody
- Footer → RadzenFooter
- Grille responsive → RadzenRow + RadzenColumn
- Carte / container → RadzenCard

---

### Navigation

- Menu principal → RadzenPanelMenu
- Item menu → RadzenPanelMenuItem
- Lien → RadzenLink
- Onglets → RadzenTabs

---

### Actions

- Bouton → RadzenButton
- Groupe boutons → RadzenSelectBar

---

### Formulaires et saisie

- Formulaire → RadzenTemplateForm
- Champ texte → RadzenTextBox
- Texte multi-ligne → RadzenTextArea
- Nombre → RadzenNumeric
- Checkbox → RadzenCheckBox
- Radio → RadzenRadioButtonList
- Liste deroulante → RadzenDropDown
- Multi-selection → RadzenDropDown (mode multiple)
- AutoComplete → RadzenAutoComplete
- Date → RadzenDatePicker

Validation :

- Champs obligatoires → RadzenRequiredValidator
- Contraintes numeriques → RadzenNumericRangeValidator

---

### Donnees et affichage

- Tableau de donnees → RadzenDataGrid
- Colonne → RadzenDataGridColumn
- Texte → RadzenText
- Label → RadzenLabel
- Icone → RadzenIcon

Fonctionnalites DataGrid a connaitre :

- pagination
- tri
- filtrage
- grouping
- chargement serveur
- selection
- templates (cellule, header, footer)

---

### Feedback utilisateur

- Notification → NotificationService
- Dialog → DialogService
- Tooltip → TooltipService
- Alerte → RadzenAlert
- Loader → RadzenProgressBar

---

### Elements divers

- Separateur → RadzenSeparator
- Image → RadzenImage

---

## 3. Conventions de pages Blazor + Radzen

### 3.1 Principes fondamentaux

- Une page Blazor orchestre les composants Radzen
- Aucun HTML natif si un composant Radzen existe
- Les composants Radzen sont utilises directement dans la page
- Ne pas encapsuler inutilement dans des composants custom

---

### 3.2 DataGrid (tableau)

L’agent DOIT savoir que RadzenDataGrid supporte :

- pagination native
- tri
- filtrage
- grouping
- chargement serveur

Regles :

- Toujours activer ces capacites si le cas d’usage le demande
- Ne jamais reimplementer ces mecanismes manuellement
- Pour gros volumes :
  - utiliser chargement serveur
  - ne jamais charger toute la liste

---

### 3.3 Formulaires

- Toujours utiliser RadzenTemplateForm
- Validation obligatoire via composants Radzen
- Ne jamais coder de validation manuelle
- Les champs sont lies a un modele typé

---

### 3.4 Services Radzen

L’agent doit connaitre l’existence de :

- DialogService → pour modales
- NotificationService → pour messages utilisateur
- TooltipService → pour aides contextuelles

Interdiction :

- ne jamais recreer ces comportements manuellement

---

### 3.5 Layout

- Layout global obligatoire via RadzenLayout
- Structure standard :
  - header
  - navigation (sidebar)
  - contenu
- Ne pas utiliser du CSS custom pour structurer la page

---

## 4. Librairies

- Radzen.Blazor

Role :

- Fournit tous les composants UI
- Fournit les services UX
- Standardise l’interface utilisateur

---

## 4.1 Bootstrap obligatoire dans wwwroot/index.html (post-mortem 2026-05-03)

Radzen.Blazor ship un script JS **et** un CSS qui DOIVENT etre charges dans
`wwwroot/index.html` du frontend Blazor. Sans ces ressources, les composants
Radzen tombent au runtime avec :
- `Could not find 'Radzen.preventArrows' ('Radzen' was undefined)` (RadzenTextBox, RadzenNumeric, RadzenDataGrid)
- `Could not find 'Radzen.openContextMenu'` (RadzenContextMenu)
- Affichage non stylise des composants (CSS manquant)

Lignes a injecter (ordre imperatif, **avant** `_framework/blazor.webassembly.js`) :

```html
<head>
    <!-- ... -->
    <link rel="stylesheet" href="_content/Radzen.Blazor/css/material-base.css" />
    <!-- ou material.css / standard-base.css / standard.css / dark-base.css selon theme -->
</head>
<body>
    <!-- ... -->
    <script src="_content/Radzen.Blazor/Radzen.Blazor.js"></script>
    <script src="_framework/blazor.webassembly#[.{fingerprint}].js"></script>
</body>
```

L'ordre `Radzen.Blazor.js` AVANT `blazor.webassembly.js` est requis : Radzen
expose un objet global `Radzen` que Blazor JS interop appelle au demarrage des
composants via `JSRuntime.InvokeVoidAsync("Radzen.preventArrows", ...)`. Si le
script Radzen n'est pas charge, la reference est `undefined` au premier
`OnAfterRenderAsync` d'un composant Radzen.

L'init script du stack frontend Blazor WASM (`.claude/stacks/frontend/blazor-webassembly.md`
STEP 3c) DOIT injecter ces deux lignes au scaffold initial quand
`.claude/stacks/ui/radzen-blazor.md` est dans `## Active UI Specs`.

---

## 5. Interdits projet (Radzen / UI)

- Utiliser HTML natif pour :
  - tableaux
  - formulaires
  - boutons
- Reimplementer :
  - pagination
  - tri
  - filtrage
- Creer des composants custom inutiles autour de Radzen
- Faire du styling CSS interne aux composants Radzen
- Melanger plusieurs design systems (ex : MudBlazor, Syncfusion)
- Gerer manuellement :
  - dialogs
  - notifications
  - tooltips
- Charger des listes completes pour affichage tableau volumineux
- Ignorer les capacites natives du DataGrid
- `wwwroot/index.html` SANS `<script src="_content/Radzen.Blazor/Radzen.Blazor.js"></script>` charge AVANT `_framework/blazor.webassembly.js` (voir §4.1)
- `wwwroot/index.html` SANS `<link rel="stylesheet" href="_content/Radzen.Blazor/css/material-base.css" />` (ou theme equivalent) — composants Radzen non stylises au runtime

---

## 6. Hors scope

- Personnalisation avancee du theme
- Dark mode custom
- Composants premium Radzen

---

## 7. Mapping HTML → composant Radzen (depuis SDD_Pro v4)

Quand `dev-frontend` lit un mockup HTML statique
(`workspace/input/ui/{n}-{m}-*.html`), il **traduit chaque primitive HTML brute
vers son pendant Radzen** selon la table ci-dessous. Le HTML brut
n'est jamais conservé tel quel dans le markup généré (sauf wrappers
de layout neutres autorisés explicitement).

### 7.1 Layout

| HTML source                              | Radzen primitive                          |
|------------------------------------------|-------------------------------------------|
| `<header>` / `<div class="header">`      | `RadzenHeader` dans `RadzenLayout`        |
| `<aside>` / `<nav class="sidebar">`      | `RadzenSidebar` dans `RadzenLayout`       |
| `<main>` / `<div class="content">`       | `RadzenBody` dans `RadzenLayout`          |
| `<footer>`                               | `RadzenFooter` dans `RadzenLayout`        |
| `<div class="card">`                     | `RadzenCard`                              |
| `<div class="row">` + `<div class="col">`| `RadzenRow` + `RadzenColumn`              |
| `<hr>`                                   | `RadzenSeparator`                         |

### 7.2 Navigation

| HTML source                              | Radzen primitive                          |
|------------------------------------------|-------------------------------------------|
| `<nav>` vertical (menu latéral)          | `RadzenPanelMenu` + `RadzenPanelMenuItem` |
| `<nav>` horizontal (menu top)            | `RadzenMenu` + `RadzenMenuItem`           |
| `<a href="...">`                         | `RadzenLink` (Path=...)                   |
| `<ul role="tablist">` / onglets          | `RadzenTabs` + `RadzenTabsItem`           |

### 7.3 Actions

| HTML source                              | Radzen primitive                          |
|------------------------------------------|-------------------------------------------|
| `<button>`                               | `RadzenButton` (Click="@...")             |
| `<button class="primary">`               | `RadzenButton ButtonStyle="Primary"`      |
| `<div class="btn-group">`                | `RadzenSelectBar`                         |

### 7.4 Formulaires

| HTML source                              | Radzen primitive                          |
|------------------------------------------|-------------------------------------------|
| `<form>`                                 | `RadzenTemplateForm` (TItem="...")        |
| `<input type="text">`                    | `RadzenTextBox` (@bind-Value=...)         |
| `<textarea>`                             | `RadzenTextArea`                          |
| `<input type="number">`                  | `RadzenNumeric<T>`                        |
| `<input type="checkbox">`                | `RadzenCheckBox`                          |
| `<input type="radio">`                   | `RadzenRadioButtonList`                   |
| `<select>` (single)                      | `RadzenDropDown`                          |
| `<select multiple>`                      | `RadzenDropDown` Multiple="true"          |
| `<input type="date">`                    | `RadzenDatePicker`                        |
| `<input list="...">` (autocomplete HTML5)| `RadzenAutoComplete`                      |
| Champ `required`                         | + `RadzenRequiredValidator`               |
| Numérique min/max                        | + `RadzenNumericRangeValidator`           |

### 7.5 Données et affichage

| HTML source                              | Radzen primitive                          |
|------------------------------------------|-------------------------------------------|
| `<table>` / `<thead>` / `<tbody>`        | `RadzenDataGrid` (avec `RadzenDataGridColumn` par colonne) |
| `<th>`                                   | `RadzenDataGridColumn Title="..."`        |
| Tableau avec pagination/tri              | `RadzenDataGrid AllowPaging="true" AllowSorting="true"` (capacités natives) |
| `<span>`, `<p>` (texte simple)           | `RadzenText` (TextStyle="...")            |
| `<label>`                                | `RadzenLabel`                             |
| `<i class="fa-...">` / icône inline      | `RadzenIcon Icon="..."`                   |

### 7.6 Feedback

| HTML source                              | Radzen primitive                          |
|------------------------------------------|-------------------------------------------|
| `<dialog>` / `<div class="modal">`       | `DialogService` (jamais HTML natif)       |
| `<div class="alert">`                    | `RadzenAlert`                             |
| `<progress>` / spinner                   | `RadzenProgressBar`                       |
| Toast/notification                       | `NotificationService`                     |
| `title="..."` (tooltip natif)            | `TooltipService`                          |

### 7.7 Règles de traduction

1. **Libellés verbatim** : le texte visible dans le HTML est repris
   tel quel dans le composant Radzen (pas de reformulation, pas de
   traduction).
2. **Couleurs** : les couleurs hex extraites du HTML (`style="..."`
   inline ou bloc `<style>`) sont matérialisées dans
   `wwwroot/css/theme.css` via les overrides `--rz-*` (cf. §5.4).
3. **Fonctionnalités natives** : si le HTML montre une `<table>` avec
   header sticky et pagination, activer `AllowPaging`, `AllowSorting`,
   `AllowFiltering` du `RadzenDataGrid` plutôt que reproduire le
   comportement manuellement.
4. **Attributs HTML standards** : `required`, `disabled`, `readonly`,
   `placeholder` sont traduits en propriétés Radzen équivalentes.
5. **Classes CSS custom** : ignorées (pas portées dans le markup
   Radzen — l'apparence vient des tokens `--rz-*` du theme).

### 7.8 Anti-derive

- Aucun `<table>`, `<button>`, `<input>`, `<select>`, `<form>`, `<dialog>`
  natif ne doit subsister dans le markup Razor généré (cf. §5
  Interdits). Tout doit être traduit.
- Si un élément HTML n'a pas d'équivalent Radzen documenté dans §2 ou
  §7, l'agent émet un WARNING et fallback sur HTML natif minimal +
  classe utilitaire `.custom-fallback` (à reviewer humain).
- Integration avec autres librairies UI