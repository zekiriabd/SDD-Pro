package simfront.controller

import jakarta.validation.Valid
import org.springframework.http.ResponseEntity
import org.springframework.security.access.prepost.PreAuthorize
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.ModelAttribute
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.servlet.support.ServletUriComponentsBuilder
import simfront.dto.input.PointDeVenteFilterInputDto
import simfront.dto.input.PointDeVenteInputDto
import simfront.dto.output.PagedOutputDto
import simfront.dto.output.PointDeVenteOutputDto
import simfront.service.PointDeVenteService

/**
 * REST controller for Points de Vente CRUD.
 *
 * GET    /api/v1/points-de-vente         → paged filtered list (US 1-2)
 * GET    /api/v1/points-de-vente/{id}    → single PDV detail for edit pre-fill (AC-2)
 * POST   /api/v1/points-de-vente         → create PDV → 201 Created + Location (AC-1)
 * PUT    /api/v1/points-de-vente/{id}    → update PDV → 200 OK (AC-2)
 * DELETE /api/v1/points-de-vente/{id}    → hard delete → 204 No Content (AC-3, AC-4)
 *
 * All endpoints require a valid Azure AD Bearer JWT (AC-9).
 * @Valid on @RequestBody triggers Jakarta Validation before service logic (AC-6, AC-7).
 * Validation failures → 400 via GlobalExceptionHandler.handleMethodArgumentNotValid (AC-10).
 * Auth failures → 401 via Spring Security (AC-10).
 * Missing resource → 404 via GlobalExceptionHandler.handleNotFound (AC-10).
 */
@RestController
@RequestMapping("/api/v1/points-de-vente")
@PreAuthorize("isAuthenticated()")
class PointDeVenteController(
    private val pointDeVenteService: PointDeVenteService
) {

    @GetMapping
    fun listPointsDeVente(
        @Valid @ModelAttribute filter: PointDeVenteFilterInputDto
    ): ResponseEntity<PagedOutputDto<PointDeVenteOutputDto>> {
        val result = pointDeVenteService.findAll(filter)
        return ResponseEntity.ok(result)
    }

    @GetMapping("/{id}")
    fun getById(
        @PathVariable id: Long
    ): ResponseEntity<PointDeVenteOutputDto> {
        val result = pointDeVenteService.findById(id)
        return ResponseEntity.ok(result)
    }

    @PostMapping
    fun create(
        @Valid @RequestBody input: PointDeVenteInputDto
    ): ResponseEntity<PointDeVenteOutputDto> {
        val created = pointDeVenteService.create(input)
        val location = ServletUriComponentsBuilder.fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(created.id)
            .toUri()
        return ResponseEntity.created(location).body(created)
    }

    @PutMapping("/{id}")
    fun update(
        @PathVariable id: Long,
        @Valid @RequestBody input: PointDeVenteInputDto
    ): ResponseEntity<PointDeVenteOutputDto> {
        val updated = pointDeVenteService.update(id, input)
        return ResponseEntity.ok(updated)
    }

    @DeleteMapping("/{id}")
    fun delete(
        @PathVariable id: Long
    ): ResponseEntity<Void> {
        pointDeVenteService.delete(id)
        return ResponseEntity.noContent().build()
    }
}
