package simfront.mapper

import simfront.dto.input.PointDeVenteInputDto
import simfront.dto.output.PointDeVenteOutputDto
import simfront.entity.Format
import simfront.entity.MotifInactivite
import simfront.entity.NatureLien
import simfront.entity.PointDeVente
import java.time.LocalDateTime

/**
 * Extension functions for mapping PointDeVente entity ↔ DTO (AC-1, AC-2, AC-7).
 *
 * toOutputDto(): entity → output DTO (list + detail/edit pre-fill).
 *   exploite: computed as true iff at least one PerimetreExploitation with actif=true
 *   is present in the entity's collection (AC-7 US 1-2).
 *   Referential labels + ids both exposed for display and edit pre-fill respectively (AC-2 US 1-4).
 *
 * toEntity(): input DTO → new entity (for POST, AC-1).
 *   Referential entities are set by id-reference only (no fetch); the service
 *   passes proxy references via repository.getReferenceById.
 *
 * applyTo(): updates an existing entity in-place from input DTO (for PUT, AC-2).
 *   Preserves id and relationships not covered by input (perimetresExploitation).
 *   Sets updatedAt to LocalDateTime.now() (audit trail, AC-4).
 */

fun PointDeVente.toOutputDto(): PointDeVenteOutputDto =
    PointDeVenteOutputDto(
        id = this.id,
        enseigne = this.enseigne,
        format = this.format?.libelle,
        formatId = this.format?.id,
        codePostal = this.codePostal,
        commune = this.commune,
        natureLien = this.natureLien?.libelle,
        natureLienId = this.natureLien?.id,
        surface = this.surface,
        catp = this.catp,
        pays = this.pays,
        exploit = this.exploit,
        actif = this.actif,
        motifInactivite = this.motifInactivite?.libelle,
        motifInactiviteId = this.motifInactivite?.id,
        exploite = this.perimetresExploitation.any { it.actif },
        adresse = this.adresse,
        complementAdresse = this.complementAdresse,
        departement = this.departement,
        telephone = this.telephone,
        fax = this.fax,
        centraleDerattachement = this.centraleDerattachement,
        codeTdlinx = this.codeTdlinx,
        updatedAt = this.updatedAt
    )

fun PointDeVenteInputDto.toEntity(
    format: Format,
    natureLien: NatureLien,
    motifInactivite: MotifInactivite?
): PointDeVente = PointDeVente().apply {
    this.enseigne = this@toEntity.enseigne
    this.format = format
    this.natureLien = natureLien
    this.surface = this@toEntity.surface
    this.centraleDerattachement = this@toEntity.centraleDerattachement
    this.codeTdlinx = this@toEntity.codeTdlinx
    this.actif = this@toEntity.actif
    this.motifInactivite = motifInactivite
    this.adresse = this@toEntity.adresse
    this.complementAdresse = this@toEntity.complementAdresse
    this.commune = this@toEntity.commune
    this.departement = this@toEntity.departement
    this.codePostal = this@toEntity.codePostal
    this.telephone = this@toEntity.telephone
    this.fax = this@toEntity.fax
    this.pays = this@toEntity.pays
    this.updatedAt = LocalDateTime.now()
}

fun PointDeVenteInputDto.applyTo(
    entity: PointDeVente,
    format: Format,
    natureLien: NatureLien,
    motifInactivite: MotifInactivite?
) {
    entity.enseigne = this.enseigne
    entity.format = format
    entity.natureLien = natureLien
    entity.surface = this.surface
    entity.centraleDerattachement = this.centraleDerattachement
    entity.codeTdlinx = this.codeTdlinx
    entity.actif = this.actif
    entity.motifInactivite = motifInactivite
    entity.adresse = this.adresse
    entity.complementAdresse = this.complementAdresse
    entity.commune = this.commune
    entity.departement = this.departement
    entity.codePostal = this.codePostal
    entity.telephone = this.telephone
    entity.fax = this.fax
    entity.pays = this.pays
    entity.updatedAt = LocalDateTime.now()
}
