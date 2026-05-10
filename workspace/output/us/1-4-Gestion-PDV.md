# US-4: Gestion-PDV

ID: 1-4-Gestion-PDV
Parent Spec: 1-pvlist
Status: Draft

## User Story
En tant qu'admin retail
Je veux créer, modifier et supprimer des points de vente depuis l'interface
Afin d'administrer le patrimoine PDV de façon complète depuis une seule interface

## Acceptance Criteria
- AC-1: La création d'un point de vente est accessible depuis la page liste via une action visible ; le formulaire rassemble les champs métier nécessaires.
- AC-2: La modification d'un point de vente est accessible depuis la page liste ligne par ligne ; le formulaire est pré-rempli avec les valeurs existantes.
- AC-3: La suppression d'un point de vente déclenche une boîte de dialogue de confirmation explicite ; l'action n'est exécutée qu'après validation explicite de l'utilisateur.
- AC-4: La suppression d'un point de vente est définitive ; aucun mécanisme de récupération automatique n'est prévu dans cette livraison.
- AC-5: Les formulaires de création et de modification côté Frontend affichent, pour chaque champ invalide, un message d'erreur explicite (champ obligatoire, format incorrect, longueur max dépassée) et bloquent l'envoi tant que la validation Frontend n'est pas verte.
- AC-6: Le Backend applique, dans le pipeline de la Minimal API, une validation automatique des paramètres d'entrée (corps JSON, query string, paramètres de route) ; toute requête invalide est rejetée avec un code 400 et une réponse structurée listant les champs en erreur.
- AC-7: La validation Backend s'exécute avant toute exécution de logique métier et avant tout accès à la base de données ; une entrée invalide ne déclenche jamais d'appel persistant.
- AC-8: Les règles de validation métier (champs obligatoires, longueurs, types, valeurs autorisées via référentiels) sont cohérentes entre Frontend et Backend et produisent le même verdict pour une même saisie.
- AC-9: Un utilisateur authentifié dans le périmètre de cette spec a les droits CRUD complets sur les points de vente, sans rôle intermédiaire.
- AC-10: Le Backend retourne un code 401 pour token absent ou invalide, 400 pour entrée mal formée ou champs invalides (avec détail par champ), 403 pour accès refusé.

## Covers
- SFD-12
- SFD-13
- SFD-14
- SFD-18
- SFD-19
- BR-2
- BR-6
- BR-12
- BR-13
- BR-14
- AC-9
- AC-10
- AC-11
- AC-20
- AC-21
- AC-22
- AC-23
- FD-3
- FD-4
- FD-5

## Dependencies
- 1-1-Authentification
- 1-2-Consultation-Liste-PDV
