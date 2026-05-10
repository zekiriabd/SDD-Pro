---
us: 1-4-Gestion-PDV
family: backend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot
stack-auth: azure-ad
---

# Plan technique backend — 1-4-Gestion-PDV

## Files

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/dto/input/PointDeVenteInputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-1, AC-2, AC-6, AC-7, AC-8]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/dto/output/PointDeVenteOutputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-1, AC-2]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/entity/PointDeVente.kt
  operation: augment
  layer: Entity
  preserves: [PointDeVente, id]
  adds: [enseigne, format, typeDeLien, surface, centraleDerattachement, codeTdlinx, actif, adresse, complementAdresse, commune, departement, codePostal, telephone, fax, pays, updatedAt]
  covers_acs: [AC-4]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/mapper/PointDeVenteMapper.kt
  operation: create
  layer: Mapper
  covers_acs: [AC-1, AC-2]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/service/PointDeVenteService.kt
  operation: augment
  layer: Service
  preserves: [PointDeVenteService, findAll, findById]
  adds: [create, update, delete]
  covers_acs: [AC-1, AC-2, AC-3, AC-4, AC-7, AC-9]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/controller/PointDeVenteController.kt
  operation: augment
  layer: Controller
  preserves: [PointDeVenteController, getAll, getById]
  adds: [create, update, delete]
  covers_acs: [AC-1, AC-2, AC-3, AC-6, AC-9, AC-10]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/exception/ResourceNotFoundException.kt
  operation: create
  layer: Service
  covers_acs: [AC-10]

- path: workspace/output/src/simback/src/main/kotlin/com/sdd-pro/sim/advice/GlobalExceptionHandler.kt
  operation: augment
  layer: Middleware
  preserves: [GlobalExceptionHandler, handleNotFound, handleValidation]
  adds: [handleAccessDenied]
  covers_acs: [AC-6, AC-10]

(8 fichiers au total)

## ACs Coverage Summary

| AC | Files |
|----|-------|
| AC-1 | PointDeVenteInputDto.kt, PointDeVenteOutputDto.kt, PointDeVenteMapper.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-2 | PointDeVenteInputDto.kt, PointDeVenteOutputDto.kt, PointDeVenteMapper.kt, PointDeVenteService.kt, PointDeVenteController.kt |
| AC-3 | PointDeVenteService.kt, PointDeVenteController.kt |
| AC-4 | PointDeVenteService.kt, PointDeVente.kt (pas de soft-delete, suppression définitive) |
| AC-5 | Frontend uniquement — hors scope backend |
| AC-6 | PointDeVenteInputDto.kt (contraintes Jakarta Validation), PointDeVenteController.kt (@Valid), GlobalExceptionHandler.kt (400 + détail champs) |
| AC-7 | PointDeVenteService.kt (validation via @Valid interceptée avant logique métier, aucun accès DB si entrée invalide) |
| AC-8 | PointDeVenteInputDto.kt (règles identiques à celles documentées pour le frontend : obligatoire, longueur, type) |
| AC-9 | PointDeVenteController.kt (endpoints protégés par Spring Security Bearer — configuration SecurityConfig existante depuis US 1-1) |
| AC-10 | GlobalExceptionHandler.kt (401 → Spring Security, 400 → MethodArgumentNotValidException, 403 → AccessDeniedException) |

## Notes

### Champs du PointDeVente (déduits du mockup HTML + ACs)

Panel gauche (informations générales) :
- `enseigne` : String, obligatoire, enum/référentiel (ex. CARREFOUR) — select
- `format` : String, obligatoire, enum/référentiel (ex. HM) — select
- `typeDeLien` : String, obligatoire, enum/référentiel (ex. Franchisé) — select
- `surface` : Int?, optionnel (m²)
- `centraleDerattachement` : String?, optionnel
- `codeTdlinx` : String?, optionnel
- `actif` : Boolean, obligatoire (défaut true) — select Oui/Non

Panel droit (adresse) :
- `adresse` : String, obligatoire
- `complementAdresse` : String?, optionnel
- `commune` : String, obligatoire
- `departement` : String?, optionnel
- `codePostal` : String?, optionnel (max 5 car.)
- `telephone` : String?, optionnel
- `fax` : String?, optionnel
- `pays` : String?, optionnel

### Décisions notables

1. **Hard delete AC-4** : `DELETE /api/v1/pointsvente/{id}` appelle `repository.deleteById(id)`. Pas de colonne `deleted_at`, pas de soft-delete. L'US est explicite : "suppression définitive, aucun mécanisme de récupération automatique".

2. **Endpoint structure** : REST idiomatique Spring Boot.
   - `POST /api/v1/pointsvente` → 201 Created + Location header
   - `PUT /api/v1/pointsvente/{id}` → 200 OK + PointDeVenteOutputDto
   - `DELETE /api/v1/pointsvente/{id}` → 204 No Content

3. **Validation Jakarta** : `PointDeVenteInputDto` porte les contraintes `@field:NotBlank`, `@field:Size`, `@field:NotNull` selon les règles AC-8. Le Controller reçoit `@Valid @RequestBody` — Spring intercepte avant le service (AC-7). `GlobalExceptionHandler.handleValidation` retourne 400 + liste des erreurs par champ (AC-6, AC-10).

4. **Sécurité Azure AD** : les 3 endpoints sont protégés par Spring Security Bearer (configuré en US 1-1 — `SecurityConfig` existante). Pas de config sécurité nouvelle dans ce plan. `handleAccessDenied` (403) ajouté dans `GlobalExceptionHandler` pour compléter AC-10.

5. **Augment Entity** : `PointDeVente.kt` possiblement créée en US 1-2 pour le listing. Si les champs adresse/téléphone ne sont pas déjà présents, `augment` les ajoute. Le plan liste tous les champs dans `adds:` pour couvrir le cas où l'entity est partielle.

6. **Mapper en extension functions Kotlin** : `PointDeVenteMapper.kt` contient `PointDeVenteInputDto.toEntity()`, `PointDeVente.toOutputDto()`, `PointDeVenteInputDto.applyTo(entity: PointDeVente)` (pour le PUT — mise à jour champ par champ sans recréer l'entity).

7. **Aucune lib on-demand déclenchée** : aucun mot-clé redis/cache/excel/pdf dans l'US. STEP 5.bis skip.
