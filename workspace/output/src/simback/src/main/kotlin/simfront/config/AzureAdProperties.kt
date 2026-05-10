package simfront.config

import jakarta.validation.constraints.NotBlank
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.validation.annotation.Validated

/**
 * Binding des variables d'environnement Azure AD depuis application.yml.
 * Fail-fast au démarrage si une variable obligatoire est absente (AC-4).
 */
@ConfigurationProperties(prefix = "azure.activedirectory")
@Validated
data class AzureAdProperties(
    @field:NotBlank val tenantId: String,
    @field:NotBlank val clientId: String,
    val instance: String = "https://login.microsoftonline.com/",
    val domain: String = "",
    val audiences: String = "",
    val feCallbackPath: String = "/auth/callback",
    val beCallbackPath: String = "/signin-oidc",
    val scopes: String = ""
) {
    /** Authority construite dynamiquement : instance + tenant */
    val authority: String
        get() = "${instance.trimEnd('/')}/$tenantId"

    /** Liste des audiences valides (séparées par virgule dans la variable) */
    val audienceList: List<String>
        get() = audiences.split(",")
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .plus(clientId)
            .plus("api://$clientId")
            .distinct()

    /** Scopes exposés au frontend */
    val scopeList: List<String>
        get() {
            val base = listOf("api://$clientId/access_as_user")
            val extra = scopes.split(" ")
                .map { it.trim() }
                .filter { it.isNotBlank() }
            return (base + extra).distinct()
        }
}
