package simfront.controller

import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import simfront.config.AzureAdProperties
import simfront.dto.output.AuthConfigOutputDto

/**
 * Endpoint public exposant la configuration Azure AD au frontend.
 * Accessible sans authentification — utilisé par le SPA React pour
 * initialiser MSAL avant le premier rendu (AC-2, Piège 4 azure-ad.md §5.2).
 *
 * Route : GET /api/config/auth (déclarée publique dans SecurityConfig)
 */
@RestController
@RequestMapping("/api/config/auth")
class AuthConfigController(
    private val azureAdProperties: AzureAdProperties
) {

    @GetMapping
    fun getAuthConfig(): AuthConfigOutputDto = AuthConfigOutputDto(
        authority = azureAdProperties.authority,
        clientId = azureAdProperties.clientId,
        scopes = azureAdProperties.scopeList,
        redirectUri = azureAdProperties.feCallbackPath
    )
}
