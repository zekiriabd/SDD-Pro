package simfront.dto.output

/**
 * Output DTO for referential list items (Format, NatureLien, MotifInactivite).
 * Used by AC-11: referential labels come from shared reference tables, not free text.
 */
data class ReferentielItemOutputDto(
    val id: Long,
    val libelle: String
)
