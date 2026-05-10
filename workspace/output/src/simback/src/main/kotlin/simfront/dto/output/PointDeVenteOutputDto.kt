package simfront.dto.output

/**
 * Output DTO for a single Point de Vente (list row and detail/edit form).
 *
 * Listing fields (AC-2 US 1-2): id, enseigne, format, codePostal, commune,
 * natureLien, surface, catp, pays, exploit, actif, motifInactivite, exploite.
 *
 * Edit pre-fill fields (AC-2 US 1-4): formatId, natureLienId, motifInactiviteId,
 * adresse, complementAdresse, departement, telephone, fax, centraleDerattachement,
 * codeTdlinx, updatedAt.
 *
 * exploite: true iff at least one active PerimetreExploitation exists (AC-7 US 1-2).
 */
data class PointDeVenteOutputDto(
    val id: Long,
    val enseigne: String?,
    // Referential label (display)
    val format: String?,
    // Referential id (edit pre-fill)
    val formatId: Long?,
    val codePostal: String?,
    val commune: String?,
    // Referential label (display)
    val natureLien: String?,
    // Referential id (edit pre-fill)
    val natureLienId: Long?,
    val surface: Int?,
    val catp: java.math.BigDecimal?,
    val pays: String?,
    val exploit: String?,
    val actif: Boolean,
    val motifInactivite: String?,
    val motifInactiviteId: Long?,
    val exploite: Boolean,
    // Address fields (edit pre-fill)
    val adresse: String?,
    val complementAdresse: String?,
    val departement: String?,
    val telephone: String?,
    val fax: String?,
    val centraleDerattachement: String?,
    val codeTdlinx: String?,
    val updatedAt: java.time.LocalDateTime?
)
