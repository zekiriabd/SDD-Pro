package simfront.controller

import org.springframework.http.ResponseEntity
import org.springframework.security.access.prepost.PreAuthorize
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import simfront.dto.output.ReferentielItemOutputDto
import simfront.service.ReferentielService

/**
 * REST controller for referential data (AC-11).
 *
 * GET /api/v1/referentiels/formats
 * GET /api/v1/referentiels/nature-liens
 * GET /api/v1/referentiels/motifs-inactivite
 *
 * Returns List<ReferentielItemOutputDto> sorted by libelle.
 * Authenticated Azure AD Bearer JWT required.
 */
@RestController
@RequestMapping("/api/v1/referentiels")
@PreAuthorize("isAuthenticated()")
class ReferentielController(
    private val referentielService: ReferentielService
) {

    @GetMapping("/formats")
    fun getFormats(): ResponseEntity<List<ReferentielItemOutputDto>> =
        ResponseEntity.ok(referentielService.findAllFormats())

    @GetMapping("/nature-liens")
    fun getNatureLiens(): ResponseEntity<List<ReferentielItemOutputDto>> =
        ResponseEntity.ok(referentielService.findAllNatureLiens())

    @GetMapping("/motifs-inactivite")
    fun getMotifsInactivite(): ResponseEntity<List<ReferentielItemOutputDto>> =
        ResponseEntity.ok(referentielService.findAllMotifsInactivite())
}
