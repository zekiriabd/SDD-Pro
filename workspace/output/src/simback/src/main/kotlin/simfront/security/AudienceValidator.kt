package simfront.security

import org.springframework.security.oauth2.core.OAuth2Error
import org.springframework.security.oauth2.core.OAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult
import org.springframework.security.oauth2.jwt.Jwt

/**
 * Validateur d'audience JWT.
 * Rejette tout token dont aucune audience ne correspond à la liste autorisée (AC-4, AC-7).
 */
class AudienceValidator(
    private val allowedAudiences: List<String>
) : OAuth2TokenValidator<Jwt> {

    override fun validate(jwt: Jwt): OAuth2TokenValidatorResult {
        val tokenAudiences = jwt.audience
        val hasValidAudience = tokenAudiences.any { it in allowedAudiences }

        return if (hasValidAudience) {
            OAuth2TokenValidatorResult.success()
        } else {
            OAuth2TokenValidatorResult.failure(
                OAuth2Error(
                    "invalid_token",
                    "The required audience is missing",
                    "https://datatracker.ietf.org/doc/html/rfc6750#section-3.1"
                )
            )
        }
    }
}
