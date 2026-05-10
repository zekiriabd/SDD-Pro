package simfront.repository

import jakarta.persistence.criteria.Predicate
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.domain.Specification
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.JpaSpecificationExecutor
import org.springframework.data.jpa.repository.Query
import org.springframework.stereotype.Repository
import simfront.dto.input.PointDeVenteFilterInputDto
import simfront.entity.PointDeVente

@Repository
interface PointDeVenteRepository :
    JpaRepository<PointDeVente, Long>,
    JpaSpecificationExecutor<PointDeVente> {

    /**
     * Total count of all PDV records before any filter (AC-6).
     * Used to populate the page title "Points de vente (N)".
     */
    @Query("SELECT COUNT(p) FROM PointDeVente p")
    fun countAll(): Long
}

/**
 * Factory for JPA Specifications built from filter DTO.
 * Each criterion is ANDed. Null criteria are ignored.
 *
 * AC-3: global search across textual columns.
 * AC-4: per-column filters.
 * AC-7: exploite = EXISTS active PerimetreExploitation.
 * AC-10: pagination is applied by Pageable (server-side).
 */
object PointDeVenteSpecifications {

    fun fromFilter(filter: PointDeVenteFilterInputDto): Specification<PointDeVente> =
        Specification { root, query, cb ->
            val predicates = mutableListOf<Predicate>()

            // AC-3 — global search over textual columns
            filter.search?.takeIf { it.isNotBlank() }?.let { term ->
                val like = "%${term.lowercase()}%"
                val searchPredicates = listOf(
                    cb.like(cb.lower(root.get("enseigne")), like),
                    cb.like(cb.lower(root.join<PointDeVente, Any>("format").get("libelle")), like),
                    cb.like(cb.lower(root.get("codePostal")), like),
                    cb.like(cb.lower(root.get("commune")), like),
                    cb.like(cb.lower(root.join<PointDeVente, Any>("natureLien").get("libelle")), like),
                    cb.like(cb.lower(root.get("pays")), like)
                )
                predicates.add(cb.or(*searchPredicates.toTypedArray()))
            }

            // AC-4 — per-column filters
            filter.enseigne?.takeIf { it.isNotBlank() }?.let {
                predicates.add(cb.like(cb.lower(root.get("enseigne")), "%${it.lowercase()}%"))
            }
            filter.format?.takeIf { it.isNotBlank() }?.let {
                val formatJoin = root.join<PointDeVente, Any>("format")
                predicates.add(cb.like(cb.lower(formatJoin.get("libelle")), "%${it.lowercase()}%"))
            }
            filter.codePostal?.takeIf { it.isNotBlank() }?.let {
                predicates.add(cb.like(cb.lower(root.get("codePostal")), "%${it.lowercase()}%"))
            }
            filter.commune?.takeIf { it.isNotBlank() }?.let {
                predicates.add(cb.like(cb.lower(root.get("commune")), "%${it.lowercase()}%"))
            }
            filter.natureLien?.takeIf { it.isNotBlank() }?.let {
                val nlJoin = root.join<PointDeVente, Any>("natureLien")
                predicates.add(cb.like(cb.lower(nlJoin.get("libelle")), "%${it.lowercase()}%"))
            }
            filter.surfaceMin?.let {
                predicates.add(cb.greaterThanOrEqualTo(root.get("surface"), it))
            }
            filter.surfaceMax?.let {
                predicates.add(cb.lessThanOrEqualTo(root.get("surface"), it))
            }
            filter.pays?.takeIf { it.isNotBlank() }?.let {
                predicates.add(cb.like(cb.lower(root.get("pays")), "%${it.lowercase()}%"))
            }
            filter.actif?.let {
                predicates.add(cb.equal(root.get<Boolean>("actif"), it))
            }
            filter.motifInactivite?.takeIf { it.isNotBlank() }?.let {
                val miJoin = root.join<PointDeVente, Any>("motifInactivite")
                predicates.add(cb.like(cb.lower(miJoin.get("libelle")), "%${it.lowercase()}%"))
            }

            // AC-7 — exploite filter via EXISTS on PerimetreExploitation
            filter.exploite?.let { exploiteFilter ->
                val subquery = query!!.subquery(Long::class.java)
                val peSub = subquery.from(simfront.entity.PerimetreExploitation::class.java)
                subquery.select(cb.literal(1L))
                    .where(
                        cb.equal(peSub.get<PointDeVente>("pointDeVente"), root),
                        cb.equal(peSub.get<Boolean>("actif"), true)
                    )
                val existsPredicate = cb.exists(subquery)
                predicates.add(if (exploiteFilter) existsPredicate else cb.not(existsPredicate))
            }

            if (predicates.isEmpty()) cb.conjunction() else cb.and(*predicates.toTypedArray())
        }
}
