# Recette générique — Monolithe legacy

> Fallback quand aucune fiche spécifique au stack ne s'applique. Couvre les
> patterns transverses observables sur la majorité des monolithes anciens.

## Quand l'utiliser

- Langage détecté par `scan_legacy.py` mais sans fiche dédiée
- Stack hybride (ex. Coldfusion + JSP, ou Classic ASP + VBScript)
- Projet legacy issu d'un fork interne d'un framework éteint

## Pré-conditions

- `workspace/old/{P}/` contient des fichiers source lisibles (pas de binaire-only)
- Au moins un point d'entrée identifiable (router, contrôleur frontal, fichier `main.*`)

Si seuls des exécutables compilés sont présents → STOP `[REVERSE_BINARY_ONLY]` (hors-scope V3).

## Pièges connus

| Piège | Symptôme | Mitigation |
|---|---|---|
| Couche métier mélangée à l'UI | `Login.html` contient SQL + business rules | Phase 3 : split intention métier vs présentation ; bias toward present sur le SQL observable |
| Dépendances dynamiques (`include`/`require`) | Le scan voit des fichiers isolés | Phase 2 : `deps_graph_builder` détecte les `include()`/`require()` PHP, `<%@ include %>` ASP/JSP |
| Configuration éparpillée | `Web.config` + `.env` + variables d'env | Phase 1 : entry points listés ; Phase 5 : Tech Lead complète `## Project Config` manuellement |
| Hardcodés magiques | Chemins absolus, IPs, ports | Évidence dans la FEAT mais NE PAS transposer comme "convention" — la Phase 6 `arch` redéfinira |
| Sessions / cookies non chiffrés | `$_SESSION['user_id']` brut | BR-N "Session stockée en cookie non signé" avec evidence — sera durcie en Phase 6 par `security-reviewer` |

## Heuristiques d'extraction

1. **Lister les entry points** (Phase 1) : tout fichier réagissant à une URL HTTP
2. **Pour chaque entry point** : 1 unité fonctionnelle candidate (U-N)
3. **AC observables** dérivés du contrôle de flux :
   - `if (auth_ok)` → AC sur l'authent réussie
   - `if (form_valid)` → AC sur la validation
   - `redirect()` → AC sur le routage post-action
4. **BR observables** dérivés du SQL inline ou des regex de validation :
   - `WHERE email = ?` unique + `INSERT INTO users` → BR "Email unique"
   - `preg_match("/^\d{13}$/")` → BR format
5. **Entities** depuis `db_schema_extractor` (SQL DDL ou ORM annotations)

## Recommandations Phase 5

Avant `/sdd-full {n}` sur une FEAT reverse de monolithe :

- Vérifier que `## Project Config` est complété (stack cible, QAMode, CoverageMin)
- Si `confidence: low` ou `medium` : compléter les ACs manuellement où l'evidence est faible
- Si DB schema dégradé : éditer `## Functional Deliverables` pour clarifier les entities manuellement
- Vérifier les hardcodés non transposables (chemins absolus, IPs) — les retirer manuellement

## Exemple

**Legacy** (ASP classique fictif, `login.asp`) :
```vbscript
<%
If Request.Form("user") <> "" Then
    Set rs = conn.Execute("SELECT id FROM users WHERE name='" & Request.Form("user") & "'")
    If Not rs.EOF Then
        Session("uid") = rs("id")
        Response.Redirect "home.asp"
    Else
        msg = "Identifiants incorrects"
    End If
End If
%>
```

**Extrait FEAT** (Phase 3 attendue) :
```markdown
- **AC-1** Given un nom d'utilisateur existant en base, when l'utilisateur soumet le formulaire, then Session("uid") est créée et redirect vers home.asp. <!-- evidence: login.asp:4-7 --> <!-- confidence: high -->
- **AC-2** Given un nom inexistant, when soumission, then "Identifiants incorrects" s'affiche, Session reste vide. <!-- evidence: login.asp:8-10 --> <!-- confidence: high -->
- **BR-1** L'authentification ne vérifie PAS de mot de passe (vulnérabilité — à confirmer Phase 5). <!-- evidence: login.asp:4 (SQL ne contient que `WHERE name=`) --> <!-- confidence: medium -->
- **BR-2** Le SQL est concaténé en string (injection possible). <!-- evidence: login.asp:4 --> <!-- confidence: high -->
```

⚠️ `confidence: medium` sur BR-1 parce que l'absence de check password est une absence de code — bias toward present demande de signaler "non observable" plutôt qu'affirmer.
