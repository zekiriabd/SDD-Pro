package simfront.dto.input

import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.NotNull
import jakarta.validation.constraints.Size

/**
 * Input DTO for creating or updating a Point de Vente (AC-1, AC-2, AC-6, AC-7, AC-8).
 *
 * Jakarta Validation constraints enforce business rules consistently with the frontend (AC-8).
 * @Valid on the controller method triggers validation before any service/DB logic (AC-7).
 * Violations produce 400 with structured field errors via GlobalExceptionHandler (AC-6).
 *
 * Referential fields (enseigne, format, typeDeLien) are passed as string values.
 * natureLienId references the NatureLien referential table (mapped from typeDeLien concept).
 * formatId references the Format referential table.
 *
 * Hard delete only — no deletedAt / softDelete flag (AC-4).
 */
data class PointDeVenteInputDto(

    // --- Informations générales ---

    @field:NotBlank(message = "L'enseigne est obligatoire")
    @field:Size(max = 255, message = "L'enseigne ne peut pas dépasser 255 caractères")
    val enseigne: String,

    @field:NotNull(message = "Le format est obligatoire")
    val formatId: Long,

    @field:NotNull(message = "Le type de lien est obligatoire")
    val natureLienId: Long,

    val surface: Int? = null,

    @field:Size(max = 255, message = "La centrale de rattachement ne peut pas dépasser 255 caractères")
    val centraleDerattachement: String? = null,

    @field:Size(max = 50, message = "Le code TDLinx ne peut pas dépasser 50 caractères")
    val codeTdlinx: String? = null,

    @field:NotNull(message = "Le statut actif est obligatoire")
    val actif: Boolean = true,

    val motifInactiviteId: Long? = null,

    // --- Adresse ---

    @field:NotBlank(message = "L'adresse est obligatoire")
    @field:Size(max = 255, message = "L'adresse ne peut pas dépasser 255 caractères")
    val adresse: String,

    @field:Size(max = 255, message = "Le complément d'adresse ne peut pas dépasser 255 caractères")
    val complementAdresse: String? = null,

    @field:NotBlank(message = "La commune est obligatoire")
    @field:Size(max = 100, message = "La commune ne peut pas dépasser 100 caractères")
    val commune: String,

    @field:Size(max = 100, message = "Le département ne peut pas dépasser 100 caractères")
    val departement: String? = null,

    @field:Size(max = 5, message = "Le code postal ne peut pas dépasser 5 caractères")
    val codePostal: String? = null,

    @field:Size(max = 20, message = "Le téléphone ne peut pas dépasser 20 caractères")
    val telephone: String? = null,

    @field:Size(max = 20, message = "Le fax ne peut pas dépasser 20 caractères")
    val fax: String? = null,

    @field:Size(max = 100, message = "Le pays ne peut pas dépasser 100 caractères")
    val pays: String? = null
)
