---
us: 1-2-Consultation-Liste-PDV
family: backend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: back-kotlin-spring
---

# Plan technique backend — 1-2-Consultation-Liste-PDV

## Files

- path: workspace/output/src/simback/src/main/kotlin/simback/dto/output/PagedOutputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-5, AC-6, AC-8, AC-9, AC-10]

- path: workspace/output/src/simback/src/main/kotlin/simback/dto/output/PointDeVenteOutputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-2, AC-7]

- path: workspace/output/src/simback/src/main/kotlin/simback/dto/output/ReferentielItemOutputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-11]

- path: workspace/output/src/simback/src/main/kotlin/simback/dto/input/PointDeVenteFilterInputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-3, AC-4, AC-5, AC-9]

- path: workspace/output/src/simback/src/main/kotlin/simback/repository/PointDeVenteRepository.kt
  operation: create
  layer: Service
  covers_acs: [AC-3, AC-4, AC-6, AC-7, AC-10]

- path: workspace/output/src/simback/src/main/kotlin/simback/service/PointDeVenteService.kt
  operation: create
  layer: Service
  covers_acs: [AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10]

- path: workspace/output/src/simback/src/main/kotlin/simback/service/ReferentielService.kt
  operation: create
  layer: Service
  covers_acs: [AC-11]

- path: workspace/output/src/simback/src/main/kotlin/simback/mapper/PointDeVenteMapper.kt
  operation: create
  layer: Service
  covers_acs: [AC-2, AC-7]

- path: workspace/output/src/simback/src/main/kotlin/simback/controller/PointDeVenteController.kt
  operation: create
  layer: Controller
  covers_acs: [AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10]

- path: workspace/output/src/simback/src/main/kotlin/simback/controller/ReferentielController.kt
  operation: create
  layer: Controller
  covers_acs: [AC-11]

## ACs Coverage Summary

| AC | Files |
|----|-------|
| AC-2 | PointDeVenteOutputDto.kt, PointDeVenteMapper.kt, PointDeVenteController.kt |
| AC-3 | PointDeVenteFilterInputDto.kt, PointDeVenteRepository.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-4 | PointDeVenteFilterInputDto.kt, PointDeVenteRepository.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-5 | PagedOutputDto.kt, PointDeVenteFilterInputDto.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-6 | PagedOutputDto.kt, PointDeVenteRepository.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-7 | PointDeVenteOutputDto.kt, PointDeVenteMapper.kt, PointDeVenteRepository.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-8 | PagedOutputDto.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-9 | PagedOutputDto.kt, PointDeVenteFilterInputDto.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-10 | PagedOutputDto.kt, PointDeVenteRepository.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-11 | ReferentielItemOutputDto.kt, ReferentielService.kt, ReferentielController.kt |

## Notes

### Entités source

Les entités JPA (scaffoldées par arch depuis la DB SqlServer) attendues :
- `PointDeVente` — table principale avec colonnes : id, enseigne, format (FK ref), codePostal, commune, natureLien (FK ref), surface, catp, pays, exploit, actif, motifInactivite (FK ref)
- `Format` (ou table de référence) — id, libelle
- `NatureLien` — id, libelle
- `MotifInactivite` — id, libelle
- `PerimetreExploitation` — id, pointDeVenteId, actif (booléen) — utilisée pour le calcul `exploite` (AC-7)

Si les entités ne sont pas encore scaffoldées, dev-backend créera des placeholders `@Entity` en se basant sur le schéma implicite de l'US.

### Endpoint principal

`GET /api/v1/points-de-vente` avec paramètres query :
- `page` (Int, défaut 0)
- `pageSize` (Int, défaut 25, valeurs autorisées : 10, 25, 50 ; rejet 400 si ≤ 0 ou > 1000)
- `search` (String?, recherche globale sur colonnes textuelles)
- `enseigne` (String?) — filtre colonne
- `format` (String?) — filtre colonne (valeur libellé de référentiel)
- `codePostal` (String?) — filtre colonne
- `commune` (String?) — filtre colonne
- `natureLien` (String?) — filtre colonne (valeur libellé de référentiel)
- `surfaceMin` (Int?) / `surfaceMax` (Int?) — filtre plage
- `pays` (String?) — filtre colonne
- `actif` (Boolean?) — filtre colonne
- `motifInactivite` (String?) — filtre colonne (valeur libellé de référentiel)
- `exploite` (Boolean?) — filtre colonne (calculé)

Retour : `PagedOutputDto<PointDeVenteOutputDto>` avec `totalCount` (avant filtrage, AC-6), `page`, `pageSize`, `items`.

### Calcul "Exploité" (AC-7)

Implémenté dans `PointDeVenteRepository` via JPQL/requête JPA :
```
EXISTS (SELECT 1 FROM PerimetreExploitation pe WHERE pe.pointDeVente = pdv AND pe.actif = true)
```
Exposé dans `PointDeVenteOutputDto.exploite: Boolean`.

### Validation AC-9

`PointDeVenteFilterInputDto.pageSize` annoté `@Min(1) @Max(1000)` via Bean Validation. Le `GlobalExceptionHandler` existant (produit par US-1 ou à créer) retourne un 400 ProblemDetail structuré.

### Référentiels (AC-11)

Trois endpoints dédiés (en lecture seule, triés par libellé) :
- `GET /api/v1/referentiels/formats`
- `GET /api/v1/referentiels/nature-liens`
- `GET /api/v1/referentiels/motifs-inactivite`

Retournent `List<ReferentielItemOutputDto>` (`id: Long, libelle: String`).

### Sécurité Azure AD

Tous les endpoints sont protégés par `@PreAuthorize("isAuthenticated()")` ou via la config Spring Security globale (Bearer JWT validé). Aucune logique de rôle/groupe spécifique demandée dans cette US.

### Repository — pagination serveur (AC-10)

`PointDeVenteRepository` étend `JpaRepository<PointDeVente, Long>` avec une méthode personnalisée utilisant `Specification<PointDeVente>` (JPA Criteria) ou `@Query` JPQL pour appliquer les filtres dynamiquement + `Pageable` pour la pagination côté DB. `Page<PointDeVente>` retourné, `Page.totalElements` = total avant filtrage.

### GlobalExceptionHandler

Si `advice/GlobalExceptionHandler.kt` n'existe pas encore (dépendance US-1), ce plan le crée également pour couvrir `MethodArgumentNotValidException` → 400 ProblemDetail (AC-9). Si déjà existant (augment), le `covers_acs` correspondant est ajouté.

**Note** : le fichier `GlobalExceptionHandler.kt` n'est pas listé dans les fichiers ci-dessus car il dépend de l'US-1 (Authentification). Si dev-backend détecte son absence au moment de la génération, il l'ajoutera en `create` ; sinon `augment`.
