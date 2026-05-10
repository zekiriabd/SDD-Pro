# US-2: Consultation-Liste-PDV

ID: 1-2-Consultation-Liste-PDV
Parent Spec: 1-pvlist
Status: Draft

## User Story
En tant qu'admin retail
Je veux accéder à la page "Points de vente" et consulter la liste paginée, recherchable et filtrable des PDV sous contrat, avec le nombre total affiché dans le titre et le statut "Exploité" calculé automatiquement
Afin d'avoir une vision centralisée et navigable de l'ensemble du patrimoine retail

## Acceptance Criteria
- AC-1: Après authentification Azure AD réussie, l'utilisateur arrive sur la page "Points de vente".
- AC-2: Le tableau de la page "Points de vente" affiche les treize colonnes listées dans les SFD avec les libellés exacts indiqués (ID PDV, Enseigne, Format, Code postal, Commune, Nature Lien, Surface, CATP (K€), Pays, Exploit, Actif, Motif Inactivité, Exploité).
- AC-3: La barre de recherche globale filtre les lignes du tableau sur l'ensemble des colonnes textuelles pendant la frappe.
- AC-4: Chaque colonne du tableau expose un filtre individuel (texte, sélection ou plage selon le type de donnée).
- AC-5: Le sélecteur de taille de page propose au moins trois valeurs (ex. 10, 25, 50) et la valeur choisie est appliquée immédiatement.
- AC-6: Le titre de la page affiche le nombre total de points de vente sous la forme "Points de vente (N)", où N est le nombre total en base, avant filtrage.
- AC-7: La colonne "Exploité" affiche "OUI" dès qu'au moins un périmètre d'exploitation actif existe pour le PDV, sinon "NON".
- AC-8: Lorsque le tableau filtré ne retourne aucun résultat, un message explicite "Aucun point de vente ne correspond à votre recherche" est affiché ; le compteur dans le titre reste le total avant filtrage.
- AC-9: Une demande de pagination avec `pageSize` hors limites (0, négatif, supérieur à 1000) est rejetée par le Backend avec un code 400 structuré ; le Frontend applique la valeur par défaut et désactive l'envoi tant que la valeur est invalide.
- AC-10: La pagination est gérée côté serveur ; le Backend retourne la page demandée et n'expose jamais l'intégralité du dataset en mémoire Frontend.
- AC-11: Les libellés des colonnes Format, Nature Lien et Motif Inactivité proviennent d'une table de référence commune ; ils ne sont pas saisis en texte libre.

## Covers
- SFD-2
- SFD-3
- SFD-4
- SFD-5
- SFD-6
- SFD-7
- SFD-8
- BR-3
- BR-4
- BR-5
- BR-7
- AC-3
- AC-4
- AC-5
- AC-6
- AC-7
- AC-8
- FD-2

## Dependencies
- 1-1-Authentification
