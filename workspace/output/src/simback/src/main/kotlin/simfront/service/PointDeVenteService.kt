package simfront.service

import org.slf4j.LoggerFactory
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import simfront.dto.input.PointDeVenteFilterInputDto
import simfront.dto.input.PointDeVenteInputDto
import simfront.dto.output.PagedOutputDto
import simfront.dto.output.PointDeVenteOutputDto
import simfront.exception.ResourceNotFoundException
import simfront.mapper.applyTo
import simfront.mapper.toEntity
import simfront.mapper.toOutputDto
import simfront.repository.FormatRepository
import simfront.repository.MotifInactiviteRepository
import simfront.repository.NatureLienRepository
import simfront.repository.PointDeVenteRepository
import simfront.repository.PointDeVenteSpecifications

private val log = LoggerFactory.getLogger(PointDeVenteService::class.java)

/**
 * Service for Points de Vente CRUD operations.
 *
 * findAll (AC-3, AC-4 US 1-2): applies dynamic filters via JPA Specifications.
 * findById (AC-2): returns a single PDV pre-filled for edit form.
 * create (AC-1): persists a new PDV, returns 201-ready output DTO.
 * update (AC-2): updates an existing PDV in-place, hard-validates existence first.
 * delete (AC-3, AC-4): hard deletes — no soft-delete, no recovery (AC-4).
 *
 * Validation (AC-7): @Valid on controller @RequestBody intercepts before service is reached.
 * All referential lookups throw ResourceNotFoundException (→ 404) on unknown ids.
 */
@Service
class PointDeVenteService(
    private val repository: PointDeVenteRepository,
    private val formatRepository: FormatRepository,
    private val natureLienRepository: NatureLienRepository,
    private val motifInactiviteRepository: MotifInactiviteRepository
) {

    // ---- Listing (US 1-2) ----

    fun findAll(filter: PointDeVenteFilterInputDto): PagedOutputDto<PointDeVenteOutputDto> {
        log.debug("findAll called with filter={}", filter)

        val totalCount = repository.countAll()

        val pageable = PageRequest.of(
            filter.page,
            filter.pageSize,
            Sort.by(Sort.Direction.ASC, "id")
        )
        val spec = PointDeVenteSpecifications.fromFilter(filter)
        val page = repository.findAll(spec, pageable)

        val items = page.content.map { it.toOutputDto() }

        return PagedOutputDto(
            totalCount = totalCount,
            filteredCount = page.totalElements,
            page = filter.page,
            pageSize = filter.pageSize,
            items = items
        )
    }

    // ---- CRUD (US 1-4) ----

    @Transactional(readOnly = true)
    fun findById(id: Long): PointDeVenteOutputDto {
        log.debug("findById called with id={}", id)
        val entity = repository.findById(id)
            .orElseThrow { ResourceNotFoundException("PointDeVente", id) }
        return entity.toOutputDto()
    }

    @Transactional
    fun create(input: PointDeVenteInputDto): PointDeVenteOutputDto {
        log.debug("create called with enseigne={}", input.enseigne)

        val format = formatRepository.findById(input.formatId)
            .orElseThrow { ResourceNotFoundException("Format", input.formatId) }
        val natureLien = natureLienRepository.findById(input.natureLienId)
            .orElseThrow { ResourceNotFoundException("NatureLien", input.natureLienId) }
        val motifInactivite = input.motifInactiviteId?.let {
            motifInactiviteRepository.findById(it)
                .orElseThrow { ResourceNotFoundException("MotifInactivite", it) }
        }

        val entity = input.toEntity(format, natureLien, motifInactivite)
        val saved = repository.save(entity)
        log.debug("created PointDeVente id={}", saved.id)
        return saved.toOutputDto()
    }

    @Transactional
    fun update(id: Long, input: PointDeVenteInputDto): PointDeVenteOutputDto {
        log.debug("update called with id={}", id)

        val entity = repository.findById(id)
            .orElseThrow { ResourceNotFoundException("PointDeVente", id) }

        val format = formatRepository.findById(input.formatId)
            .orElseThrow { ResourceNotFoundException("Format", input.formatId) }
        val natureLien = natureLienRepository.findById(input.natureLienId)
            .orElseThrow { ResourceNotFoundException("NatureLien", input.natureLienId) }
        val motifInactivite = input.motifInactiviteId?.let {
            motifInactiviteRepository.findById(it)
                .orElseThrow { ResourceNotFoundException("MotifInactivite", it) }
        }

        input.applyTo(entity, format, natureLien, motifInactivite)
        val saved = repository.save(entity)
        log.debug("updated PointDeVente id={}", saved.id)
        return saved.toOutputDto()
    }

    @Transactional
    fun delete(id: Long) {
        log.debug("delete called with id={}", id)
        if (!repository.existsById(id)) {
            throw ResourceNotFoundException("PointDeVente", id)
        }
        repository.deleteById(id)
        log.debug("deleted PointDeVente id={}", id)
    }
}
