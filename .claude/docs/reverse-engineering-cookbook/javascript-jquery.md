# Recette — JavaScript + jQuery (legacy front)

## Quand l'utiliser

Détection `javascript-jquery` dans `inventory.json.languagesDetected`. Présence `.js` avec `$(document).ready` + `$.ajax`. Souvent en combo avec un backend ASPX/JSP/PHP.

## Pré-conditions

- Au moins 1 fichier `.js` avec jQuery patterns
- HTML statique (`.html`/`.htm`) ou templates serveur (`.aspx`/`.jsp`/`.php`) référençant les `.js`
- (Idéalement) CSS associé pour Phase 4 UI

## Pièges connus

| Piège | Mitigation Phase 3 |
|---|---|
| **DOM-spaghetti** : selectors `$(".btn")` globaux | Capturer les actions par selector, pas par "fonction métier" idéale |
| **État implicite** dans le DOM | Pas d'extraction d'état (le bias toward present interdit) — capturer uniquement les transitions observables |
| **AJAX endpoints non documentés** | Lister tous les `$.ajax({url:...})` dans Phase 2 → matrice d'intégration backend |
| **Callbacks imbriqués** | Convertir le flow en ACs séquentiels (avant pyramidal hell) sans inventer la gestion d'erreur absente |
| **Confidence cap = `medium`** | Toujours — ne pas tenter `high` même si le code est clair |

## Heuristiques d'extraction

1. **1 page HTML qui charge des scripts jQuery ≈ 1 unité front** ; le backend qui sert les endpoints AJAX est une unité distincte
2. AC depuis :
   - `$("#btn").click(function(){ $.ajax(...) })` → 1 AC par action utilisateur
   - Callbacks `success`/`error` → 1 AC par chemin
3. BR depuis :
   - Validation côté client (`if (val.length < 3) return false;`)
   - Mais ⚠️ : ne pas confondre validation client avec règle métier — la BR est probablement aussi côté backend (cf. fiche backend correspondante)
4. **Pas d'entities côté front** — entities viennent du backend

## Recommandations Phase 5

- Vérifier que les endpoints AJAX listés ont leur contrepartie backend dans une autre FEAT reverse (sinon contract gap)
- `## Project Config` cible : `react` ou `vue` avec UI DS associé
- Cap `medium` propagé → revue manuelle obligatoire avant `/sdd-full` (gate `check_reverse_feat_for_full.py` exit 1)
- ⚠️ Sécurité : valider que toutes les BRs client sont AUSSI côté backend (sinon le `security-reviewer` Phase 6 va flagger)

## Exemple

Legacy `login.js` :
```javascript
$(document).ready(function() {
    $("#btnLogin").click(function(e) {
        e.preventDefault();
        var user = $("#txtUsername").val();
        var pwd = $("#txtPassword").val();
        if (user.length === 0 || pwd.length === 0) {
            $("#lblError").text("Champs requis");
            return;
        }
        $.ajax({
            url: "/api/login",
            method: "POST",
            data: { username: user, password: pwd },
            success: function(resp) {
                if (resp.success) { window.location.href = "/home"; }
                else { $("#lblError").text(resp.message); }
            },
            error: function() { $("#lblError").text("Erreur réseau"); }
        });
    });
});
```

Extrait FEAT :
```markdown
> ⚠️ FEAT générée par reverse engineering avec confiance MEDIUM (cap langage jQuery legacy).
> Revue humaine obligatoire avant /sdd-full.

- **AC-1** Given Username et Password remplis, when clic btnLogin, then POST /api/login envoyé avec body {username, password}. <!-- evidence: login.js:3-11 --> <!-- confidence: medium -->
- **AC-2** Given response.success == true, when callback success, then redirect /home. <!-- evidence: login.js:14 --> <!-- confidence: medium -->
- **AC-3** Given response.success == false, when callback success, then lblError affiche response.message. <!-- evidence: login.js:15 --> <!-- confidence: medium -->
- **AC-4** Given Username ou Password vide, when clic btnLogin, then "Champs requis" + pas d'appel /api/login. <!-- evidence: login.js:6-9 --> <!-- confidence: high -->
- **BR-1** Validation côté client : champs requis. ⚠️ Vérifier que cette BR existe AUSSI côté backend (sinon contournement trivial). <!-- evidence: login.js:6 --> <!-- confidence: medium -->
```

Cap : `medium` (jQuery cap forcé par `language_signatures.yml`).
