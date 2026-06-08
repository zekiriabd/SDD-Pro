# Spec: menu-principale

Status: Draft
Spec ID: spec-menu-principale

## Context
Une fois connecté à Demo, l'employé doit pouvoir naviguer entre les modules métiers de l'application et accéder à ses informations personnelles depuis n'importe quelle page. Aucun composant de navigation global n'existe aujourd'hui : les pages applicatives ne sont pas reliées entre elles. Cette spec décrit le menu principal — un panneau latéral (drawer) intégré au MainLayout, déclenché depuis un bouton hamburger, accessible uniquement aux employés authentifiés (cf. spec-connexion).

## Objective
L'employé connecté ouvre un menu latéral global depuis le MainLayout, voit ses informations personnelles, navigue en SPA vers les modules métiers (bébés, rapports, données, contrats) et peut se déconnecter à tout moment.

## Actors
- Employé connecté : assistante maternelle authentifiée, ayant un compte en table `Employee`. Aucun accès au menu en mode non connecté.

## User Stories
- L'utilisateur clique sur le bouton menu (icône hamburger) du MainLayout pour ouvrir le panneau latéral
- Le panneau affiche en haut la photo de profil de l'employé connecté à partir du champ `ImageUrl` de la table `Employee`
- Un avatar par défaut est affiché si `ImageUrl` est vide ou si l'image n'est pas accessible
- Le panneau affiche le nom et le prénom de l'employé connecté
- Le panneau affiche le numéro de téléphone de l'employé connecté
- Le panneau présente une liste de liens de navigation principale : "Mes bébés", "Rapports", "Mes données", "Mes contrats"
- Un clic sur "Mes bébés" navigue vers `/bebes` en SPA et ferme le menu
- Un clic sur "Rapports" navigue vers `/rapports` en SPA et ferme le menu
- Un clic sur "Mes données" navigue vers `/donnees` en SPA et ferme le menu
- Un clic sur "Mes contrats" navigue vers `/contrats` en SPA et ferme le menu
- Le panneau affiche en bas un bouton "Se déconnecter" toujours visible et accessible
- Un clic sur "Se déconnecter" supprime le token et la session côté client puis redirige vers `/login`
- Le panneau se ferme automatiquement au clic en dehors du panneau
- L'utilisateur non connecté qui tenterait d'accéder à une page protégée est renvoyé sur `/login` (couvert par spec-connexion) — le menu n'est donc jamais affiché en l'absence d'authentification

## Business Rules
- BR-1: aucun rendu du menu pour un utilisateur non connecté ; toute tentative d'accès en l'absence de token JWT valide redirige vers `/login`
- BR-2: la navigation entre les pages déclenchée par les items du menu DOIT utiliser le mécanisme SPA du framework actif (Blazor : `NavigationManager.NavigateTo()`) — l'usage de `<a href>` brut est interdit pour ces items
- BR-3: si le design system actif fournit un composant menu/drawer (Radzen : `RadzenSidebar`, `RadzenPanelMenu` ou équivalent), il DOIT être utilisé en priorité ; le CSS isolé ne complète que pour atteindre la fidélité visuelle de la maquette
- BR-4: la photo de profil utilise un avatar par défaut si `ImageUrl` est vide, null, ou si l'URL est inaccessible — aucun cassage de rendu autorisé
- BR-5: les informations utilisateur affichées (nom, prénom, téléphone, image) proviennent exclusivement de la table `Employee`, pour l'employé identifié par le token JWT en session
- BR-6: le bouton "Se déconnecter" est toujours visible quel que soit l'état de défilement du panneau

## Acceptance Criteria
- AC-1: le MainLayout contient un bouton menu (icône hamburger) qui ouvre le panneau latéral au clic
- AC-2: le panneau ouvert affiche en haut un bloc avec la photo, le nom + prénom et le numéro de téléphone de l'employé connecté
- AC-3: si `ImageUrl` est vide ou inaccessible, l'avatar par défaut est affiché à la place de la photo de profil
- AC-4: le panneau affiche les 4 items de navigation dans l'ordre : "Mes bébés", "Rapports", "Mes données", "Mes contrats"
- AC-5: un clic sur un item de navigation déclenche une transition SPA vers la route correspondante (`/bebes`, `/rapports`, `/donnees`, `/contrats`) sans rechargement complet de la page
- AC-6: le panneau se ferme automatiquement après un clic sur un item de navigation
- AC-7: le panneau se ferme au clic en dehors du panneau (overlay ou zone applicative)
- AC-8: le bouton "Se déconnecter" est positionné en bas du panneau et reste visible quel que soit l'état de défilement
- AC-9: un clic sur "Se déconnecter" supprime le token côté client et redirige vers `/login`
- AC-10: aucun rendu du menu n'est observable pour un utilisateur non connecté ; l'accès à une page protégée sans token redirige vers `/login`

## Dependencies
- spec-connexion : l'employé doit être connecté pour voir le menu, et la déconnexion réutilise le flux de retour à `/login` couvert par spec-connexion

## Functional Deliverables
- composant menu/drawer global intégré dans le MainLayout
- bouton hamburger dans le MainLayout pour ouvrir/fermer le panneau
- 3 blocs distincts dans le panneau : informations utilisateur (haut), navigation (milieu), déconnexion (bas)
- 4 routes de navigation SPA depuis le menu : `/bebes`, `/rapports`, `/donnees`, `/contrats`
- avatar par défaut servi en fallback quand `ImageUrl` est vide ou inaccessible

## Out of Scope
- les pages cibles `/bebes`, `/rapports`, `/donnees`, `/contrats` elles-mêmes (specs séparées à venir)
- édition des informations utilisateur depuis le menu (consultation seule)
- notifications / badges sur les items du menu
- thème dark/light, multi-langue
- rôles Admin / Parent (extensions futures)
- information assistantes maternelles connecté: nom prénom téléphone récupéré de variable sengloton de emploier connecté et affichier dans le header. 
