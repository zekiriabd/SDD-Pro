# UI Design System: Vuetify (Vue.js)

Status: Draft  
UI Spec ID: vuetify  
Scope: design system Vuetify — composants UI pour applications Vue 3 (SPA, dashboards, applications métier)

---

## 1. Identité du design system

- Nom : Vuetify
- Framework cible : Vue.js (Vue 3 recommandé)
- Type : UI Component Framework basé sur Material Design
- Philosophie : composants prêts à l’emploi + cohérence UX globale
- Base design : Material Design (Google)

### Objectif pour l’IA

- Comprendre Vuetify comme un **design system complet**
- Utiliser les composants natifs avant toute solution custom
- Respecter les patterns Material Design
- Ne pas reconstruire des composants déjà existants

---

## 2. Principes fondamentaux

- UI standardisée basée sur Material Design
- Composants accessibles par défaut
- Design system cohérent (spacing, elevation, typography)
- Composition via slots et props
- Responsive design natif
- Theming centralisé (light/dark + variables)

Règles IA :

- Toujours privilégier un composant Vuetify existant
- Ne jamais remplacer un composant natif par du HTML brut
- Ne pas réinventer layout/navigation/forms
- Composer plutôt que reconstruire

---

## 3. Architecture UI Vuetify

### 3.1 Structure standard d’application

- App shell → v-app
- Layout global → v-app-bar + v-navigation-drawer + v-main
- Contenu → v-container / v-row / v-col

---

### 3.2 Organisation logique

- pages → vues principales (router views)
- components → composants réutilisables
- layouts → structures globales
- composables → logique réutilisable (Vue 3)
- stores → état global (Pinia recommandé)

---

## 4. Mapping fonctionnel → composants Vuetify

| Fonction UI | Composant Vuetify |
|-------------|------------------|
| application root | v-app |
| layout global | v-app-bar + v-navigation-drawer + v-main |
| navigation menu | v-list / v-navigation-drawer |
| bouton | v-btn |
| icône | v-icon |
| champ texte | v-text-field |
| zone texte | v-textarea |
| select | v-select |
| autocomplete | v-autocomplete |
| checkbox | v-checkbox |
| radio | v-radio-group |
| switch | v-switch |
| date picker | v-date-picker |
| formulaire | v-form |
| carte | v-card |
| tableau de données | v-data-table |
| pagination | v-pagination |
| dialog / modal | v-dialog |
| tooltip | v-tooltip |
| snackbar / toast | v-snackbar |
| alert | v-alert |
| tabs | v-tabs |
| chips | v-chip |
| avatar | v-avatar |
| progress | v-progress-linear / v-progress-circular |
| skeleton loading | v-skeleton-loader |

---

## 5. Data handling (patterns obligatoires)

### 5.1 v-data-table

Fonctionnalités natives :

- tri (sorting)
- pagination
- filtrage
- sélection de lignes
- slots personnalisés (cellules, headers)
- chargement serveur possible

Règles :

- activer server-side processing pour gros volumes
- ne jamais charger des datasets complets côté client si volumineux
- utiliser computed + API service layer

---

### 5.2 Forms

- toujours utiliser v-form comme conteneur
- validation via rules (functions)
- intégration recommandée avec VeeValidate ou equivalent
- champs contrôlés (v-model obligatoire)

Interdit :

- validation manuelle dispersée
- logique métier dans le template

---

## 6. Layout system

Vuetify impose un système layout basé sur flex + grid :

- v-container → wrapper principal
- v-row → ligne responsive
- v-col → colonnes

Layouts standards :

- Dashboard layout
- Auth layout
- Full page layout

---

## 7. Navigation

- v-navigation-drawer pour menu principal
- v-app-bar pour header global
- v-list pour items navigation

Règles :

- navigation centralisée (router-based)
- pas de navigation inline non structurée
- pas de duplication menu dans composants

---

## 8. Theming system

- basé sur Material Design tokens
- support dark/light mode natif
- configuration via theme global

Règles :

- jamais de styles inline non cohérents
- respecter palette theme (primary, secondary, error, success, warning)
- éviter overrides CSS profonds sauf cas exceptionnel

---

## 9. Interactions UI

- v-dialog pour modales
- v-snackbar pour notifications utilisateur
- v-tooltip pour aides contextuelles
- v-menu pour actions contextuelles

Règles :

- aucune modal HTML custom
- aucune notification custom hors v-snackbar
- interactions standardisées Vuetify uniquement

---

## 10. State management

Recommandé :

- Pinia (state global Vue 3)

Règles :

- état global uniquement dans store
- ne jamais stocker logique métier dans composants UI
- éviter duplication d’état local/global

---

## 11. Accessibilité et UX

- composants Vuetify accessibles par défaut
- ARIA intégré dans composants natifs
- navigation clavier supportée
- focus management automatique dans dialogs

---

## 12. Règles de développement UI

### Obligatoire

- utiliser composants Vuetify natifs
- respecter structure layout Vuetify
- séparation UI / logique métier
- utiliser v-model pour binding
- composants réutilisables uniquement si nécessaire

---

### Interdit

- HTML brut pour remplacer un composant Vuetify
- reimplementation de DataTable, Dialog, Form
- CSS custom override structure layout
- duplication de composants existants
- logique métier dans template Vue
- mix de frameworks UI (Vuetify + autre UI kit)

---

## 13. Philosophie IA (usage agentic)

Ce design system doit être interprété comme :

- un framework UI complet
- une structure standardisée pour génération UI automatique
- un système basé sur composants déclaratifs

L’IA doit :

- privilégier Vuetify avant toute création custom
- respecter les patterns Material Design
- composer les UI via composants existants
- éviter toute réinvention UI inutile

---

## 14. Hors scope

- design system non-Material Design
- composants UI externes non Vuetify
- backend logic
- auth system
- design tokens custom avancés multi-brand
- animation complexe hors Vuetify transitions

---

## 15. Mapping HTML → composant Vuetify (depuis SDD_Pro v4)

Quand `dev-frontend` lit un mockup HTML statique
(`workspace/input/ui/{n}-{m}-*.html`), il **traduit chaque primitive HTML brute
vers son pendant Vuetify**.

### 15.1 Layout

| HTML source                              | Vuetify primitive                         |
|------------------------------------------|-------------------------------------------|
| `<header>` / barre top                   | `<v-app-bar>`                             |
| `<aside>` / sidebar                      | `<v-navigation-drawer>`                   |
| `<main>`                                 | `<v-main>`                                |
| `<footer>`                               | `<v-footer>`                              |
| `<div class="card">`                     | `<v-card>` + `<v-card-title>` + `<v-card-text>` |
| Grille responsive                        | `<v-container>` + `<v-row>` + `<v-col>`   |

### 15.2 Navigation

| HTML source                              | Vuetify primitive                         |
|------------------------------------------|-------------------------------------------|
| `<nav>` / liste de liens                 | `<v-list>` + `<v-list-item>`              |
| `<a href="...">`                         | `<router-link>` (Vue Router) ou `<v-btn :to="...">` |
| Onglets                                  | `<v-tabs>` + `<v-tab>`                    |

### 15.3 Actions et formulaires

| HTML source                              | Vuetify primitive                         |
|------------------------------------------|-------------------------------------------|
| `<button>`                               | `<v-btn>`                                 |
| `<button class="primary">`               | `<v-btn color="primary">`                 |
| `<input type="text">`                    | `<v-text-field>`                          |
| `<textarea>`                             | `<v-textarea>`                            |
| `<input type="number">`                  | `<v-text-field type="number">`            |
| `<select>`                               | `<v-select>`                              |
| Multi-select / autocomplete              | `<v-autocomplete>` ou `<v-combobox>`      |
| `<input type="checkbox">`                | `<v-checkbox>`                            |
| `<input type="radio">`                   | `<v-radio-group>` + `<v-radio>`           |
| `<input type="date">`                    | `<v-date-picker>` (dans `<v-menu>`)       |
| `<form>`                                 | `<v-form>`                                |
| `<label>`                                | propriété `label` du composant Vuetify    |

### 15.4 Données et affichage

| HTML source                              | Vuetify primitive                         |
|------------------------------------------|-------------------------------------------|
| `<table>`                                | `<v-data-table>` (avec `:headers` et `:items`, pagination/tri natifs) |
| `<dialog>` / modal                       | `<v-dialog>`                              |
| Drawer latéral                           | `<v-navigation-drawer>` (mode temporary)  |
| Toast/notification                       | `<v-snackbar>`                            |
| Tooltip                                  | `<v-tooltip>`                             |
| Badge                                    | `<v-chip>` ou `<v-badge>`                 |
| Avatar                                   | `<v-avatar>`                              |
| Progress                                 | `<v-progress-circular>` / `<v-progress-linear>` |
| Alert                                    | `<v-alert>`                               |

### 15.5 Règles de traduction

1. **Libellés verbatim** : repris tels quels (prop `label="..."`).
2. **Couleurs** : matérialisées via le theme Vuetify (`vuetify.config.ts`)
   ou via `--v-theme-*` overrides dans le CSS global.
3. **Icônes** : traduites en classes `mdi-*` (Material Design Icons).
4. **`v-data-table`** : activer `:items-per-page`, `:sort-by`,
   `:loading` selon les besoins exprimés dans le HTML (pagination,
   tri, filtres) plutôt que reproduire manuellement.