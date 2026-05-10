# US-1: Authentification

ID: 1-1-Authentification
Parent Spec: 1-pvlist
Status: Draft

## User Story
En tant qu'utilisateur connecté (via Azure AD)
Je veux me connecter à la plateforme via une popup Azure AD et pouvoir me déconnecter depuis le menu utilisateur
Afin d'accéder de façon sécurisée aux fonctionnalités de la plateforme ou d'en sortir proprement

## Acceptance Criteria
- AC-1: Un utilisateur non authentifié est systématiquement redirigé vers la popup Azure AD avant tout accès à une page fonctionnelle.
- AC-2: Après authentification Azure AD réussie, l'utilisateur est redirigé vers la page "Points de vente".
- AC-3: Le Frontend Blazor lit le token Azure AD acquis à la connexion et l'ajoute automatiquement sur chaque requête sortante vers le Backend sous la forme d'en-tête `Authorization: Bearer <token>`.
- AC-4: Le Backend Minimal API expose un middleware d'authentification qui valide le JWT Azure AD à chaque requête entrante (signature, émetteur, audience, expiration) et rejette toute requête sans token valide avec un code 401.
- AC-5: Une requête vers le Backend dont le token est expiré ou invalide reçoit un code 401 sans atteindre la logique métier ; le Frontend déclenche alors une relance d'authentification silencieuse ou redirige vers la popup Azure AD.
- AC-6: Les endpoints Backend n'acceptent aucun appel anonyme ; toute tentative sans en-tête `Authorization` retourne 401 avant exécution.
- AC-7: Un utilisateur Azure AD authentifié mais hors tenant SDD-Pro ou hors groupe autorisé (claims tenant manquants ou incohérents) reçoit un code 403 sans fuite d'information sur la cause exacte.
- AC-8: Le clic sur "Se déconnecter" depuis le menu utilisateur termine la session et redirige vers l'écran d'authentification.

## Covers
- SFD-1
- SFD-15
- SFD-16
- SFD-17
- BR-1
- BR-8
- BR-9
- BR-10
- BR-11
- AC-1
- AC-2
- AC-15
- AC-16
- AC-17
- AC-18
- AC-19
- FD-1
- FD-9
- FD-10
- FD-11

## Dependencies
- NONE
