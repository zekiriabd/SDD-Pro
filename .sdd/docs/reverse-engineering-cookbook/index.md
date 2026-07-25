# Reverse Engineering Cookbook — Recettes par langage legacy

> Fiches pratiques pour réussir un reverse engineering sur des stacks legacy
> courantes. Compagnon opérationnel du design doc maître
> `.sdd/docs/reverse-engineering-workflow.md`.
>
> **Workflow général** (rappel) : Phase 0 dépôt → Phase 1 inventaire →
> Phase 2 audit (optionnel) → Phase 3 extraction FEAT par U-N → Phase 4 UI
> (optionnel) → Phase 5 revue humaine → Phase 6 `/sdd-full`.

## Recettes disponibles

| Stack | Fiche | Confidence cap typique | Difficultés courantes |
|---|---|:---:|---|
| Générique monolithe | [_generic-monolith.md](_generic-monolith.md) | medium | Couche métier mélangée à l'UI, dépendances cachées |
| ASP.NET WebForms | [dotnet-webforms.md](dotnet-webforms.md) | high | Code-behind volumineux, ViewState magique |
| ASP.NET MVC (classique) | [dotnet-mvc.md](dotnet-mvc.md) | high | Mapping route → ViewModel parfois implicite |
| Java EE (Servlet / JSP / JSF) | [java-jee.md](java-jee.md) | high | XML config dispersée, EJB legacy |
| JavaScript + jQuery (legacy) | [javascript-jquery.md](javascript-jquery.md) | medium | DOM-spaghetti, état implicite |
| PHP procédural (sans framework) | [php-procedural.md](php-procedural.md) | medium | SQL injection partout, sessions cookies |
| Delphi (source .pas + .dfm) | [delphi.md](delphi.md) | high | Composants visuels custom, BDD natifs Borland |

## Convention de lecture

Chaque fiche suit cette structure :

1. **Quand l'utiliser** : signaux qui déclenchent ce cas
2. **Pré-conditions** : ce qui doit être présent dans `workspace/old/{P}/`
3. **Pièges connus** : trous typiques, anti-patterns récurrents
4. **Heuristiques d'extraction** : comment Phase 3 doit prioriser le code observable
5. **Recommandations Phase 5** : ce que le Tech Lead doit vérifier avant `/sdd-full`
6. **Exemple courte** : 1 snippet legacy → extrait FEAT typique

## Pas de fiche pour ton stack ?

→ Démarrer avec `_generic-monolith.md` qui couvre les patterns transverses. Le
workflow reste fonctionnel sur tout langage signé dans `language_signatures.yml`
même sans fiche dédiée. Ouvrir une issue pour suggérer une nouvelle fiche
(le Tech Lead arbitre).
