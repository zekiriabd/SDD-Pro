# FEAT 1 — Minimal

> Fixture E2E pour le nightly job (combo C1 — .NET + React + shadcn + Azure AD).
> Volontairement minimaliste pour valider la chaîne complète /sdd-full sans
> consommer plus de ~$2-3 d'Opus en CI.

## Objectif

Vérifier la santé du pipeline `/sdd-full` bout-en-bout sur le combo
validé C1 (dotnet-minimalapi + react + shadcn + dotnet-xunit + azure-ad).

## Acteurs

- **Visiteur** : utilisateur non authentifié qui consulte une page publique.

## Functional Needs

- SFD-1 : Afficher un message de bienvenue sur la page d'accueil.

## Functional Deliverables

- FD-1 : Page d'accueil React (`/`) avec composant `<WelcomeBanner />`.
- FD-2 : Endpoint backend GET `/api/welcome` qui renvoie `{ message: string }`.

## Business Rules

- BR-1 : Le message renvoyé par l'endpoint est en français : « Bienvenue ».

## Acceptance Criteria

- AC-1 : Quand un visiteur ouvre la page d'accueil, il voit le texte
  « Bienvenue » affiché à l'écran.
- AC-2 : Quand on appelle GET `/api/welcome`, la réponse a `status=200`
  et le body JSON `{ "message": "Bienvenue" }`.

## Risques / Hypothèses

Aucun. Cette FEAT existe uniquement pour valider la chaîne `/sdd-full`
en CI, pas pour un usage métier réel.

## Métrique de succès

Le pipeline `/sdd-full 1` complète sans intervention humaine en moins
de 10 minutes (1 US backend + 1 US frontend, ~$2-3 Opus).
