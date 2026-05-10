package simfront.service

import org.springframework.data.domain.Sort
import org.springframework.stereotype.Service
import simfront.dto.output.ReferentielItemOutputDto
import simfront.mapper.toOutputDto
import simfront.repository.FormatRepository
import simfront.repository.MotifInactiviteRepository
import simfront.repository.NatureLienRepository

/**
 * Service for referential data endpoints (AC-11).
 * Items are sorted by libelle ascending.
 */
@Service
class ReferentielService(
    private val formatRepository: FormatRepository,
    private val natureLienRepository: NatureLienRepository,
    private val motifInactiviteRepository: MotifInactiviteRepository
) {

    fun findAllFormats(): List<ReferentielItemOutputDto> =
        formatRepository.findAll(Sort.by("libelle"))
            .map { it.toOutputDto() }

    fun findAllNatureLiens(): List<ReferentielItemOutputDto> =
        natureLienRepository.findAll(Sort.by("libelle"))
            .map { it.toOutputDto() }

    fun findAllMotifsInactivite(): List<ReferentielItemOutputDto> =
        motifInactiviteRepository.findAll(Sort.by("libelle"))
            .map { it.toOutputDto() }
}
