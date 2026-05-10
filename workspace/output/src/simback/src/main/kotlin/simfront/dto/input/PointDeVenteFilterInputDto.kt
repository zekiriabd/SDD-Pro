package simfront.dto.input

import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min

/**
 * Query parameters for GET /api/v1/points-de-vente.
 *
 * AC-3: search — global text search across all textual columns.
 * AC-4: per-column filters (enseigne, format, codePostal, commune,
 *        natureLien, surfaceMin/Max, pays, actif, motifInactivite, exploite).
 * AC-5: page / pageSize — server-side pagination selector.
 * AC-9: pageSize validated 1..1000 (400 on violation).
 */
data class PointDeVenteFilterInputDto(
    val page: Int = 0,

    @field:Min(value = 1, message = "pageSize doit être au minimum 1")
    @field:Max(value = 1000, message = "pageSize ne peut pas dépasser 1000")
    val pageSize: Int = 25,

    val search: String? = null,

    // Per-column filters (AC-4)
    val enseigne: String? = null,
    val format: String? = null,
    val codePostal: String? = null,
    val commune: String? = null,
    val natureLien: String? = null,
    val surfaceMin: Int? = null,
    val surfaceMax: Int? = null,
    val pays: String? = null,
    val actif: Boolean? = null,
    val motifInactivite: String? = null,
    val exploite: Boolean? = null
)
