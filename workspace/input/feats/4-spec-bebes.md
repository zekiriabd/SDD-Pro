# Spec: bebes

Status: Draft
Spec ID: spec-bebes

## Context
Une assistante maternelle (employé connecté) doit pouvoir consulter la liste des bébés qui lui sont attribués depuis son espace personnel Demo. Aucune page de gestion des bébés n'existe aujourd'hui : l'employé n'a pas de vue centralisée sur les enfants en cours de garde. Cette spec décrit la page `/bebes`, accessible depuis l'item "Mes bébés" du menu principal (cf. spec-menu-principale), et personnalisée selon l'employé connecté.

## Objective
L'employé connecté voit la liste des bébés filtrée selon son `EmployeeId`, accède rapidement au rapport de chaque bébé, et peut lancer l'ajout d'un nouvel enfant.

## Actors
- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Aucun accès à la page sans authentification.

## User Stories
- L'utilisateur accède à la page `/bebes` depuis l'item "Mes bébés" du menu principal
- La page récupère l'`EmployeeId` de l'employé connecté depuis la variable singleton de session et requête les bébés filtrés en table `Contrat WHERE EmployeeId = session.EmployeeId`
- Pendant le chargement, un loader est affiché à l'emplacement de la liste
- Une fois les données reçues, la page affiche la liste des bébés sous forme de cards
- Chaque card affiche l'image du bébé (champ `ImageUrl`), son nom + prénom, et sa date de naissance
- Si `ImageUrl` est vide ou inaccessible, un avatar par défaut est affiché à la place
- En mode desktop, les cards sont affichées en grille
- En mode mobile, les cards sont affichées en liste verticale
- Si la liste est vide, le message "Aucun enfant assigné" est affiché à la place des cards
- Chaque card contient une icône ✏️ "Rapport" qui, au clic, navigue en SPA vers la page rapport en passant l'ID du bébé
- Un bouton flottant (FAB) « + » est affiché en bas à droite de la page, toujours visible, et permet de naviguer en SPA vers la page de création d'un bébé — il remplace l'ancien bouton « Ajouter un enfant » en fin de liste et reproduit le style du FAB de l'onglet RDV de la fiche bébé
- L'icône 📞 (appel parents) peut figurer visuellement sur la card pour respecter la maquette mais reste sans action câblée — son comportement est défini dans une spec séparée à venir

## Business Rules
- BR-1: l'employé ne voit que les bébés dont la colonne `EmployeeId` correspond à son propre identifiant ; aucune donnée d'un autre employé n'est exposée
- BR-2: le filtrage par `EmployeeId` est appliqué côté serveur lors de la requête de liste, jamais uniquement côté UI
- BR-3: l'`EmployeeId` utilisé pour le filtrage provient exclusivement de la variable singleton de session de l'employé connecté ; aucun paramètre de requête utilisateur ne peut le surcharger
- BR-4: la navigation entre les pages déclenchée par les actions (icône rapport, FAB « + » d'ajout d'un bébé) DOIT utiliser le mécanisme SPA du framework actif (Blazor : `NavigationManager.NavigateTo()`) — l'usage de `<a href>` brut est interdit (l'attribut `href="#"` du FAB est purement de présentation ; la navigation passe par `onNavigate`/handler SPA)
- BR-5: si le design system actif fournit un composant card ou data-list Card , il DOIT être utilisé en priorité ; le CSS isolé ne complète que pour atteindre la fidélité visuelle de la maquette
- BR-6: l'image du bébé utilise un avatar par défaut si `ImageUrl` est vide, null, ou inaccessible — aucun cassage de rendu autorisé
- BR-7: l'icône 📞 (appel parents) peut être présente sur la card par fidélité à la maquette mais N'EST PAS câblée dans cette spec ; son comportement (lien `tel:` ou page contact) est couvert par une spec séparée à venir
- BR-8: aucune information technique (stack trace, identifiant interne, exception) n'est exposée dans les messages d'erreur visibles à l'utilisateur
- BR-9: aucun rendu de la liste pour un utilisateur non connecté ; la redirection vers `/login` en l'absence de session valide est gérée par spec-connexion

## Acceptance Criteria
- AC-1: la page `/bebes` est accessible depuis l'item "Mes bébés" du menu principal et n'est pas accessible sans session valide
- AC-2: la liste affichée contient uniquement les bébés dont `Contrat.EmployeeId == session.EmployeeId`
- AC-3: pendant le chargement initial des données, un loader est affiché à l'emplacement de la liste
- AC-4: chaque card affiche l'image du bébé, son nom + prénom et sa date de naissance
- AC-5: si `ImageUrl` est vide ou inaccessible, l'avatar par défaut est affiché à la place de la photo
- AC-6: l'affichage est en grille en mode desktop et en liste verticale en mode mobile
- AC-7: si l'employé n'a aucun bébé assigné, le message "Aucun enfant assigné" est affiché à la place des cards
- AC-8: chaque card affiche une icône ✏️ "Rapport" cliquable qui déclenche une navigation SPA vers la page rapport en passant l'ID du bébé
- AC-9: un bouton flottant (FAB) « + » est affiché en bas à droite de la page, reste visible quelque soit l'état de la liste (vide, normale, défilée) ; un clic déclenche une navigation SPA vers la page de création d'un bébé ; il remplace l'ancien bouton « Ajouter un enfant » de fin de liste et adopte le style FAB rond corail identique au FAB de l'onglet RDV de la fiche bébé
- AC-10: aucune information d'un bébé appartenant à un autre employé n'apparaît dans la réponse serveur, même en cas de manipulation des paramètres de requête côté client

## Dependencies
- spec-connexion : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; la redirection vers `/login` en l'absence de session valide est couverte par cette spec
- spec-menu-principale : la route `/bebes` est l'item de navigation principal vers cette page

## Functional Deliverables
- écran `/bebes` filtré par `EmployeeId` de l'employé connecté
- card par bébé avec image, nom + prénom, date de naissance, icône ✏️ rapport
- 3 états visuels : liste normale, liste vide ("Aucun enfant assigné"), chargement (loader)
- FAB « + » flottant en bas à droite, toujours visible, navigant en SPA vers la page de création d'un bébé (style aligné sur le FAB de l'onglet RDV de la fiche bébé)
- avatar par défaut servi en fallback quand `ImageUrl` est vide ou inaccessible
- responsive : grille desktop, liste verticale mobile

## Out of Scope
- comportement / câblage de l'icône 📞 (appel / contact parents) — couvert par une spec séparée à venir
- page rapport bébé (cible de l'icône ✏️ — spec séparée à venir)
- formulaire détaillé de création d'un bébé (cible du FAB « + » — spec séparée à venir)
- édition des informations d'un bébé depuis cette page (consultation seule)
- suppression / archivage / fin de contrat d'un bébé depuis cette page
- gestion / modification du lien parent ↔ enfant côté backend
- modification du schéma de la table `Bebes`
- recherche / filtrage / tri dans la liste
- pagination
- rôles Admin / Parent (extensions futures)
