# UI Design System: Radzen (Blazor)

> §2.4 (Librairies) régénérée depuis `radzen-blazor.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id radzen-blazor`).

Status: Stable
Validation: 🟢 reference (validated combo — dotnet-minimalapi + blazor + radzen + azure-ad)
UI FEAT ID: radzen-blazor
Scope: design system Radzen — composants Blazor (Server + WebAssembly)

> Référence canonique : ce fichier `.md` + le catalogue machine
> `.libs.json` compagnon. La documentation officielle Radzen
> (https://blazor.radzen.com/) reste consultable manuellement par le
> Tech Lead pour récupérer propriétés / événements / types exacts d'un
> composant. **Pas de fetch automatique** par l'agent (v7.0.0 — l'ancien
> mécanisme MCP server Radzen a été retiré avec le sweep MCP du sweep
> dead-code C1, cf. `docs/CHANGELOG.md §[Unreleased]`).

---

UI FEAT ID: radzen-blazor
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

- Une page Blazor orchestre les composants Radzen **et** les
  containers HTML+CSS du mockup
- Containers de layout/positionnement du mockup → **HTML verbatim**
  (cf. §7.0 souveraine) ; le composant Razor encapsule le container
  HTML, pas l'inverse
- Pour le **contenu fonctionnel** (formulaires riches, grilles,
  dialogs, dropdowns data-driven) : aucun HTML natif si un composant
  Radzen existe — utiliser Radzen
- Pour les **éléments visuels simples** (boutons icône cosmétiques,
  toolbar SVG, liens nav, sélecteurs custom du mockup) : HTML verbatim
  + CSS mockup, pas de wrapping Radzen forcé (cf. §7.0.3 arbitrage)
- Les composants Radzen sont utilises directement dans la page **à
  l'intérieur** des containers HTML
- Encapsuler dans un composant Razor custom est ATTENDU pour isoler
  un container HTML+CSS mockup réutilisable (ex. `WizardTopBar.razor`)

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

### 3.5 Layout (révisé 2026-05-22 — voir §7.0)

- **Si mockup HTML présent** (`workspace/input/ui/{n}-{m}-*.html`) :
  layout = **HTML verbatim du mockup** + CSS porté dans `.razor.css`
  ou `MainLayout.razor.css`. **PAS** de `RadzenLayout`/`RadzenHeader`/
  `RadzenSidebar`/`RadzenFooter` qui écraseraient la structure du mockup
  (cf. post-mortem MainLayout CMSPrint 2026-05-22).
- **Si pas de mockup HTML** (cas rare en SDD_Pro) : `RadzenLayout`
  acceptable comme fallback générique.
- CSS custom pour structurer la page (`display:flex`, `grid`,
  `position`, classes mockup `.brand`, `.menu`, etc.) → **REQUIS**
  quand mockup présent.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/ui/radzen-blazor.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id radzen-blazor`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Radzen.Blazor | 5.5.7 | Design system Radzen complet pour Blazor (Server + WebAssembly) — composants UI, layout, navigation, services UX (Dialog/Notification/Tooltip). |
<!-- LIBS_CATALOG_END -->

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
    <script src="_framework/blazor.webassembly.js"></script>
</body>
```

⚠️ **Blazor WASM standalone — pas de syntaxe fingerprint** : utiliser
`_framework/blazor.webassembly.js` (sans `#[.{fingerprint}]`). Le placeholder
`#[.{fingerprint}]` est exclusif aux Blazor Web App server-rendered (substitué
par `MapStaticAssets()`) ; en WASM standalone il est servi littéralement → 404.
Détail : `stacks/frontend/blazor-webassembly.md §3.5`.

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

> ⚠️ **Lecture §7.0 prérequise** : les interdits ci-dessous portent
> sur le **contenu fonctionnel** des pages. Ils ne s'appliquent
> **PAS** aux containers HTML de layout (§7.0 souveraine : nav,
> header, aside, main, footer, section, divs de positionnement
> restent HTML verbatim).

- Utiliser HTML natif **pour le contenu fonctionnel** :
  - tableaux riches (tri/filtre/pagination) → `RadzenDataGrid`
  - formulaires avec validation → `RadzenTemplateForm` + `Radzen*Validator`
  - boutons d'**action complexe** (form submit, dialog trigger,
    busy state) → `RadzenButton`
  - dropdowns data-driven → `RadzenDropDown` / `RadzenAutoComplete`
- **EXCEPTION §7.0** : boutons d'icône cosmétiques avec SVG inline du
  mockup, liens nav, toolbar buttons, sélecteurs custom stylés par
  le mockup, containers de layout/positionnement → restent **HTML
  verbatim**. Ne PAS forcer en `RadzenButton`/`RadzenLink`/`RadzenMenu`.
- Reimplementer :
  - pagination
  - tri
  - filtrage
- Creer des composants custom inutiles autour de Radzen
  (exception : §7.3 — wrapper composant Razor qui isole un container
  HTML+CSS mockup, ex. `WizardTopBar.razor`, est ATTENDU)
- Faire du styling CSS interne aux composants Radzen
  (le CSS mockup des containers va dans `.razor.css` adjacent, pas
  en override de classes `.rz-*`)
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

## 7. Mapping HTML → composant Radzen (depuis SDD_Pro v4, **règle révisée 2026-05-22**)

### 7.0 Principe « Container HTML littéral, contenu Radzen » (load-bearing, audit 2026-05-22)

**Stratégie de traduction mockup → Blazor + Radzen** :

1. **Container / layout / positionnement = HTML+CSS VERBATIM du mockup**
   - `<nav>`, `<header>`, `<aside>`, `<main>`, `<footer>`, `<section>`,
     `<div class="...">` qui portent du `display:flex`, `grid`, `position`,
     `padding`, `margin`, `gap`, `border`, `box-shadow`, `background`
   - Le CSS du mockup (`<style>` du fichier HTML) est porté **verbatim**
     dans le `.razor.css` **adjacent** au composant qui possède le markup
     (Blazor scoped CSS — cf. `stacks/frontend/blazor-webassembly.md §3.7`)
   - **JAMAIS** déclarer ces classes dans le `.razor.css` d'une page parent
     qui consomme `<MonComposant />` — scope hash différent, CSS jamais
     appliqué (post-mortem CMSPrint 2026-05-22 : `Pages/CampagneInfosPage.razor.css`
     contenait `.section-title`/`.field` consommés par `Components/CampagneInfosForm.razor` →
     form non stylé en runtime)
   - **JAMAIS** essayer de mapper un `<nav class="nav" style="display:flex">`
     vers `RadzenSidebar` ou `RadzenLayout` — la perte de fidélité spatiale
     est garantie (cf. post-mortem MainLayout 2026-05-22 où `<nav class="nav">`
     horizontal → `RadzenSidebar` vertical, contradiction mockup)
   - Si le mockup utilise des classes CSS custom (`.brand`, `.menu`, `.country`,
     `.submenu`, `.stepper`), elles sont préservées dans le `.razor.css`
     adjacent au composant qui les consomme

2. **Éléments interactifs dans le container = composants Radzen**
   - À l'intérieur des containers HTML, les éléments fonctionnels riches
     (formulaires, grilles de données, dialogs, dropdowns avec données dynamiques)
     utilisent les composants Radzen :
     - `<input type="text">` → `RadzenTextBox`
     - `<table>` complexe → `RadzenDataGrid`
     - `<select>` dynamique → `RadzenDropDown`
     - `<dialog>` / `<div class="modal">` → `DialogService.OpenAsync<T>()`
     - Boutons d'**action** (submit, dialog trigger, etc.) → `RadzenButton`
   - **Exception** : éléments simples 100% visuels (boutons d'icône cosmétiques,
     boutons de toolbar avec SVG inline du mockup, liens nav) peuvent rester
     en `<button>`/`<a>` HTML natif si le mockup les définit ainsi
     (le styling vient du CSS verbatim)

3. **Règle d'arbitrage**
   - Question : "ce composant a-t-il besoin d'un comportement Radzen complexe
     (filtrage, pagination, validation, dialog stack) ?"
     - **Oui** → utiliser le composant Radzen, accepter son look natif (ou override CSS minimal)
     - **Non, c'est uniquement visuel** → HTML natif + CSS mockup verbatim
   - Question : "ce composant porte-t-il le positionnement (layout) ou le contenu
     (formulaire, données) ?"
     - **Layout** → toujours HTML+CSS verbatim, JAMAIS Radzen
     - **Contenu fonctionnel** → Radzen pour rich behavior, HTML pour purely visual

### 7.1 Exemples canoniques

| Cas | Container (HTML verbatim) | Contenu (Radzen) |
|---|---|---|
| Header app top bar | `<nav class="nav">` (mockup CSS flex 64px) | `RadzenButton` (si action complexe), `RadzenDropDown` (si combo data-driven). Boutons simples avec SVG du mockup = `<button>` natif. |
| Wizard stepper | `<nav class="submenu"><ol class="stepper"><li class="step">` (mockup verbatim) | Aucun — tout est CSS/HTML visuel |
| Page Campagne (form) | `<section class="form-section">` (mockup grid) | `RadzenDropDown`, `RadzenTextBox`, `RadzenDatePicker` à l'intérieur |
| Page Campagnes liste | `<div class="page-grid">` (mockup CSS) | `RadzenDataGrid` à l'intérieur (tri/filtre/pagination natifs Radzen) |
| Sélecteur de langue | `<button class="country">` (mockup verbatim) | Aucun Radzen — dropdown custom avec `<ul>` styled (le mockup définit le look) |
| Avatar utilisateur | `<div class="avatar">` (mockup gradient circulaire) | `DialogService.OpenAsync<T>` pour le popup (Radzen pour comportement modal) |

### 7.2 Anti-patterns (post-mortem 2026-05-22, CMSPrint)

- ❌ `<nav class="nav">` horizontal du mockup → `RadzenSidebar` (vertical) **ou** `RadzenLayout`
- ❌ `<div class="stepper">` du mockup → `RadzenSteps` (look natif Radzen différent)
- ❌ `<button class="country">` du mockup → `RadzenDropDown` (look button-style Radzen différent)
- ❌ Wrapper `RadzenStack Orientation="Horizontal"` à la place de `<nav class="nav">` (perte des classes mockup `.brand`, `.menu`, `.right`)
- ❌ Conserver SVG icons du mockup mais wrapper dans `RadzenIcon` (double rendering)

### 7.3 Quand la maquette a des classes spécifiques (load-bearing)

Si le mockup utilise des noms de classes signifiantes (`.brand`, `.country`,
`.menu`, `.submenu`, `.stepper`, `.step`, `.connector`, `.right`, `.icon-btn`,
`.help`, `.avatar`, etc.), elles deviennent le **vocabulaire CSS du composant
Blazor** et sont préservées. Le CSS du `<style>` du mockup est extrait verbatim
vers le `.razor.css` adjacent.

Cette stratégie a un coût :
- ✅ Fidélité visuelle 100% (le résultat ressemble pixel-pixel au mockup)
- ✅ Pas de bagarre avec les overrides Radzen
- ❌ Plus de CSS à maintenir (vs Radzen qui apporte son propre design system)
- ⚖️ Trade-off accepté : le mockup est source de vérité visuelle.

---

## 7.bis Tables de mapping HTML brut → composant (référence rapide, post-2026-05-22)

> ⚠️ **Lecture obligatoire de §7.0 d'abord** : si l'élément HTML est un
> CONTAINER de layout (porte CSS `display:flex/grid/position`), il reste
> HTML verbatim, JAMAIS mappé vers un composant Radzen. Les tables
> ci-dessous ne s'appliquent qu'aux **éléments de contenu** (formulaire,
> grille, dialog) inside les containers.

Quand `dev-frontend` lit un mockup HTML statique
(`workspace/input/ui/{n}-{m}-*.html`), il **traduit chaque primitive HTML brute
vers son pendant Radzen** selon la table ci-dessous. Le HTML brut
n'est jamais conservé tel quel dans le markup généré (sauf wrappers
de layout neutres autorisés explicitement).

### 7.1 Layout (DÉPRÉCIÉE 2026-05-22 — voir §7.0)

> ⛔ **Les containers de layout restent HTML verbatim** (§7.0 souveraine).
> Cette table est conservée comme **anti-référence** : les mappings
> ci-dessous ne s'appliquent **PAS** quand un mockup HTML existe — le
> mockup est source de vérité visuelle et son CSS conteneur est porté
> verbatim dans `.razor.css`. À n'utiliser **que** en l'absence
> totale de mockup HTML (cas hors `appType=back-front` + mockup).

| HTML source                              | ~~Radzen primitive (déprécié)~~           | Règle §7.0 (active) |
|------------------------------------------|-------------------------------------------|---------------------|
| `<header>` / `<div class="header">`      | ~~`RadzenHeader` dans `RadzenLayout`~~    | **HTML verbatim** + CSS mockup |
| `<aside>` / `<nav class="sidebar">`      | ~~`RadzenSidebar` dans `RadzenLayout`~~   | **HTML verbatim** + CSS mockup |
| `<main>` / `<div class="content">`       | ~~`RadzenBody` dans `RadzenLayout`~~      | **HTML verbatim** + CSS mockup |
| `<footer>`                               | ~~`RadzenFooter` dans `RadzenLayout`~~    | **HTML verbatim** + CSS mockup |
| `<div class="card">`                     | ~~`RadzenCard`~~                          | **HTML verbatim** sauf si contenu = grille riche + dialog modal (alors `RadzenCard` OK) |
| `<div class="row">` + `<div class="col">`| ~~`RadzenRow` + `RadzenColumn`~~          | **HTML verbatim** (CSS grid/flex du mockup) |
| `<hr>`                                   | `RadzenSeparator` OU `<hr>` verbatim     | indifférent — visuel pur |

### 7.2 Navigation (DÉPRÉCIÉE 2026-05-22 — voir §7.0)

> ⛔ **Les containers de navigation restent HTML verbatim** (§7.0
> souveraine). `<nav class="submenu">` avec stepper, `<nav class="nav">`
> top bar, sélecteurs custom du mockup ne sont **JAMAIS** mappés vers
> `RadzenMenu`/`RadzenPanelMenu`/`RadzenSidebar` (look natif Radzen
> incompatible avec le design mockup — cf. post-mortem CMSPrint
> 2026-05-22).

| HTML source                              | ~~Radzen primitive (déprécié)~~           | Règle §7.0 (active) |
|------------------------------------------|-------------------------------------------|---------------------|
| `<nav>` vertical (menu latéral)          | ~~`RadzenPanelMenu` + `RadzenPanelMenuItem`~~ | **HTML verbatim** + CSS mockup |
| `<nav>` horizontal (menu top)            | ~~`RadzenMenu` + `RadzenMenuItem`~~       | **HTML verbatim** + CSS mockup |
| `<a href="...">`                         | ~~`RadzenLink`~~                          | **`<a>` verbatim** + classes mockup |
| `<ul role="tablist">` / onglets          | `RadzenTabs` + `RadzenTabsItem` (si comportement Radzen complexe requis) OU HTML verbatim | arbitrage §7.0.3 |

### 7.3 Actions (arbitrage §7.0.3 obligatoire)

> Test : "ce bouton a-t-il un comportement Radzen complexe (dialog
> trigger, form submit avec validation Radzen, busy state, icon prop) ?"
> **Oui** → `RadzenButton`. **Non, c'est un bouton stylé par le mockup
> avec SVG inline** → `<button>` HTML verbatim + classes mockup
> (`.btn`, `.btn-primary`, `.is-disabled`, …).

| HTML source                              | Radzen primitive (si action complexe)     | HTML verbatim (si visuel mockup) |
|------------------------------------------|-------------------------------------------|----------------------------------|
| `<button>` simple (toolbar, SVG inline du mockup) | —                                | **`<button>` verbatim** + classes mockup |
| `<button>` form submit + validation      | `RadzenButton` (Click="@...")             | — |
| `<button class="primary">` action principale | `RadzenButton ButtonStyle="Primary"`   | OU `<button class="btn btn-primary">` verbatim selon mockup |
| `<div class="btn-group">` segmented      | `RadzenSelectBar` (si data-driven)        | OU HTML verbatim si purement visuel |

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
