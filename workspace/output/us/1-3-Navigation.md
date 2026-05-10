# US-3: Navigation

ID: 1-3-Navigation
Parent Spec: 1-pvlist
Status: Draft

## User Story
En tant qu'utilisateur connecté (via Azure AD)
Je veux accéder à un menu latéral de navigation, à un menu dropdown de bascule de plateforme dans l'en-tête et à un menu utilisateur avec avatar
Afin de naviguer entre les sections de l'application, basculer vers une autre plateforme et accéder à mon profil

## Acceptance Criteria
- AC-1: Les entrées de menu "Périmètre d'exploitation" et "Configuration de redevances" sont visibles dans le menu latéral et cliquables, mais redirigent vers des pages placeholders.
- AC-2: Le menu dropdown de bascule de plateforme est visible dans l'en-tête sur toutes les pages ; les liens ne redirigent vers aucune plateforme tierce dans cette livraison (hors scope).
- AC-3: Le menu utilisateur affiche l'avatar et donne accès à "Voir profil" et "Se déconnecter".
- AC-4: Le lien "Voir profil" est présent dans le menu utilisateur ; la page cible est hors scope et peut être un placeholder.

## Covers
- SFD-9
- SFD-10
- SFD-11
- AC-12
- AC-13
- AC-14
- FD-6
- FD-7
- FD-8

## Dependencies
- 1-1-Authentification
