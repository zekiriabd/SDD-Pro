# Cookbook — Monolithe générique (fallback)

> **Fiche fallback** chargée par les agents reverse quand aucune fiche langage spécifique ne match le legacy détecté.
> **Périmètre** : heuristiques universelles valables sur tout langage / tout framework.
> Fiches plus spécifiques à venir : `dotnet-webforms.md`, `dotnet-mvc.md`, `java-jee.md`, `javascript-jquery.md`, `php-procedural.md`, `delphi.md`, etc. (V2).

## 1. Heuristiques universelles d'identification d'unités fonctionnelles

### 1.1 Page = surface utilisateur

Tout fichier qui aboutit en HTML rendu côté client (ASPX, JSP, PHP, .cshtml, .razor, .html dynamique) est une **page candidate** → contient potentiellement 1-4 unités fonctionnelles.

Signaux :
- Fichier avec `<html>`, `<body>`, ou template render
- Extension associée à un framework web (.aspx, .jsp, .php, .cshtml, .razor)
- Référencé par une route (URL pattern) ou un controller action

### 1.2 Code-behind = logique

Fichier compagnon contenant la logique d'événements et d'accès données :
- ASPX : `*.aspx.cs`, `*.aspx.vb`
- Razor : `*.razor.cs`, `*.cshtml.cs`
- JSP : Servlet/Controller Java associé
- PHP : block `<?php ?>` dans le même fichier
- Delphi : `.pas` associé au `.dfm`

### 1.3 Patterns d'unités fonctionnelles cross-langage

| Pattern observable | Type d'unité | Confidence |
|---|---|---|
| Tableau de données avec actions (edit, delete) | `grid-crud` | high |
| Formulaire principal de saisie/édition | `form-edit` | high |
| Formulaire avec input password | `form-login` | high |
| Navigation hiérarchique (menu, breadcrumb, tabs) | `navigation-menu` | high |
| Multi-étapes (wizard, stepper) | `wizard` | medium |
| Filtres au-dessus d'un grid (dropdown + textbox + button "Search") | `filter-panel` | medium |
| Modale de confirmation | `modal-action` (souvent partie du parent CRUD) | medium |
| Liste personnalisée (Repeater, ngFor) | `custom-list` | medium |
| Export Excel/PDF (lien ou bouton avec download) | `export-action` | medium |
| Upload de fichier | `file-upload` | high |
| Dashboard avec widgets | `dashboard` (souvent split en N unités) | low |

## 2. Identification de l'intention utilisateur

L'intention métier vient de **3 sources** :
1. **Labels UI** : `<h1>`, `<title>`, `<button>` text, `<label>` text
2. **Noms d'événements** : `OnRowEditing`, `BtnSearch_Click`, `Login1_Authenticate`, `save()`, `delete()`
3. **Patterns de données** : `SELECT * FROM Customer`, `customer.save()`, `repository.findAll()`

**Bias toward present** : si tu ne trouves pas l'intention dans le code, ne l'invente pas.

## 3. Patterns de Business Rules à grepper

| Pattern | Type de BR |
|---|---|
| `IF user.IsInRole(...)` | Permission |
| `UPDATE ... SET IsActive = 0` (au lieu de DELETE) | Soft delete |
| `validate()` methods avec checks | Validation métier |
| `if (price > 0 && quantity > 0)` | Règle de calcul |
| `if (status == "Pending")` puis `status = "Approved"` | Workflow d'état |
| `RequiredFieldValidator`, `@NotBlank`, `Validators.required` | Validation champ |
| `try { } catch (BusinessException)` | Exception métier |

## 4. Patterns de Acceptance Criteria à formuler

Pour chaque AC, partir d'une **action observable** + un **résultat observable**.

Exemples génériques (en français) :

```
- **AC-1** : Given un utilisateur connecté, When il clique sur Éditer une ligne du grid, Then le formulaire d'édition s'ouvre pré-rempli avec les données de la ligne
- **AC-2** : Given un formulaire d'édition ouvert, When l'utilisateur soumet sans remplir un champ obligatoire, Then une erreur de validation s'affiche et le formulaire n'est pas envoyé
- **AC-3** : Given un administrateur connecté, When il clique sur Supprimer, Then une confirmation s'affiche ; si confirmée, l'enregistrement passe à inactif et disparaît de la liste
```

L'AC doit être :
- Citable par evidence (`file:lines`)
- Testable (mesurable / observable)
- Atomique (1 comportement, pas plusieurs)

## 5. Détection des Acteurs (Roles)

Grep universel :
- `IsInRole`, `hasRole`, `@PreAuthorize`, `[Authorize(Roles=...)]`
- `session.role`, `$_SESSION['user_type']`
- `if (user.isAdmin())`

Si aucun pattern → **un seul acteur par défaut** : "Utilisateur final" (français).

## 6. Détection des Entités métier

Sources :
1. Schéma DB (si extrait par Phase 2 `db_schema_extractor.py`)
2. Classes avec `[Table]`, `@Entity`, `class Customer extends Model`
3. SELECT/INSERT/UPDATE/DELETE dans le code

**Anti-derive** : ne JAMAIS inventer une entité absente de la DB. Si la DB schema dit "Customer (Id, Name, Email)", la FEAT ne mentionne pas un champ "Phone" même si tu vois `<input id="phone">` dans le HTML (probablement champ non persisté ou champ dérivé).

## 7. Détection des Anti-patterns (pour tech audit Phase 2, informational)

À noter mais **ne pas mettre dans la FEAT** (descriptif factuel uniquement) :
- SQL inline dans le code-behind (vs ORM)
- Pas de validation server-side
- ViewState lourd > 50 KB
- Connection strings hardcodées
- Sessions non sécurisées
- jQuery 1.x EOL
- Bootstrap 3.x EOL

Ces signaux servent à Tech Lead pour choisir la stack cible (V2 reverse-tech-auditor).

## 8. Cas frontière : pas d'intention claire

Si l'unité ciblée n'a **pas d'intention utilisateur claire** (ex. fichier de config, classe utilitaire pure, helper sans UI) :
- STOP + ERROR `[REVERSE_NO_INTENT]`
- Le Tech Lead doit éditer `inventory.json` pour marquer cette unité `omit_suggested: true` puis relancer

## 9. Cas frontière : code legacy partiellement compréhensible

Si tu lis un fichier en VB6 / Cobol / Visual FoxPro ou autre langage exotique :
- Forcer `confidence: low` sur tous les items générés
- Ajouter la bannière humaine `⚠️ Revue humaine requise`
- Citer evidence avec moins de précision (file uniquement, pas lignes)
- Documenter dans `## Reverse Engineering Notes` les biais d'interprétation

## 10. Cas frontière : intention métier ambiguë multi-acteurs

Si le code semble servir plusieurs flux distincts (ex. une même page rend différemment selon le rôle) :
- **Préférer un split** : 2 FEATs distinctes (une par flux)
- Documenter dans `inventory.md` (proposition d'arbitrage Tech Lead)
- Si Tech Lead refuse le split, la FEAT unique doit avoir ≥ 2 AC pour les 2 flux

---

**FIN — Cookbook fallback (générique). Fiches langages spécifiques à venir en V2.**
