# Sections enrichies — Risques, Hypothèses, Cas Limites, Parties Prenantes, Modes de Défaillance

> Ce fichier est un **fragment de template** : il décrit les 5 sections
> que `/feat-deepen` ajoute en fin de FEAT après les techniques
> d'élicitation. Ne pas créer ce fichier manuellement — il est
> intégré par la commande.

---

## Risques Identifiés

> Issus de la technique **Pre-mortem** + **Red Team**. Liste les
> risques projet/feature classés par sévérité.

| ID | Risque | Sévérité | Mitigation |
|---|---|---|---|
| RISK-1 | <description courte> | low/medium/high | <action de mitigation ou "à valider"> |

---

## Hypothèses

> Issues de la technique **First Principles**. Hypothèses sur
> lesquelles repose la feature. Toute hypothèse non confirmée est un
> risque latent.

| ID | Hypothèse | Statut | Validation requise |
|---|---|---|---|
| ASS-1 | <hypothèse formulée comme une affirmation> | confirmée / à valider | <comment valider> |

---

## Cas Limites

> Issus de la technique **Red Team**. Cas limites et scénarios
> dégradés explicitement listés. Chaque cas limite devient candidat à
> une AC d'US ou à un comportement de robustesse.

| ID | Cas limite | Comportement attendu | Couvert par |
|---|---|---|---|
| EDGE-1 | <ex. utilisateur sans connexion> | <ex. message d'erreur clair> | AC-N de US-X / à ajouter |

---

## Parties Prenantes

> Issues de la technique **Stakeholder Mapping**. Qui est impacté, qui
> valide, qui est exclu.

| Acteur | Rôle vs feature | Niveau d'implication |
|---|---|---|
| <acteur> | sponsor / utilisateur / valideur / impacté | RACI : R/A/C/I |

---

## Modes de Défaillance

> Issus de la technique **Inversion**. Scénarios qui rendraient cette
> feature un échec — utiles pour définir des critères de succès en
> miroir.

| ID | Mode de défaillance | Indicateur de défaillance | Critère succès en miroir |
|---|---|---|---|
| FAIL-1 | <ex. taux d'abandon de la connexion > 20%> | <métrique observable> | <ex. taux abandon < 5%> |
