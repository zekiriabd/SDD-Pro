package simfront.dto.output

/**
 * DTO retourné par l'endpoint public /api/config/auth.
 * Utilisé par le frontend React pour initialiser MSAL avant tout rendu (AC-2, §5.1 azure-ad.md).
 * Aucune valeur sensible : uniquement les données nécessaires à MSAL côté SPA.
 */
data class AuthConfigOutputDto(
    /** Authority MSAL : https://login.microsoftonline.com/{tenantId} */
    val authority: String,
    /** Client ID de l'App Registration Azure AD */
    val clientId: String,
    /** Scopes à demander : api://{clientId}/access_as_user + supplémentaires */
    val scopes: List<String>,
    /** Redirect URI configurée côté frontend */
    val redirectUri: String
)
