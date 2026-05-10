package simfront.security

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.config.Customizer
import org.springframework.security.config.http.SessionCreationPolicy
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2TokenValidator
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.jwt.JwtDecoder
import org.springframework.security.oauth2.jwt.JwtIssuerValidator
import org.springframework.security.oauth2.jwt.JwtTimestampValidator
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer
import org.springframework.security.web.SecurityFilterChain
import simfront.config.AzureAdProperties

/**
 * Configuration Spring Security : OAuth2 Resource Server JWT.
 * - Toutes les routes nécessitent un Bearer token valide (AC-4, AC-6).
 * - /api/config/auth reste public (requis par le frontend pour bootstrap MSAL — §5.1 azure-ad.md).
 * - Token expiré/invalide → 401 avant toute logique métier (AC-5).
 * - Authentifié sans droits suffisants → 403 géré par GlobalExceptionHandler (AC-7).
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class SecurityConfig(
    private val azureAdProperties: AzureAdProperties
) {

    /**
     * Swagger UI / OpenAPI — bypass complet de la chaîne de sécurité (dev tooling).
     */
    @Bean
    fun webSecurityCustomizer(): WebSecurityCustomizer = WebSecurityCustomizer { web ->
        web.ignoring().requestMatchers(
            "/swagger",
            "/swagger/**",
            "/swagger-ui.html",
            "/swagger-ui/**",
            "/openapi",
            "/openapi/**",
            "/openapi.yaml",
            "/v3/api-docs",
            "/v3/api-docs/**"
        )
    }

    @Bean
    fun securityFilterChain(http: HttpSecurity): SecurityFilterChain {
        http
            .sessionManagement { it.sessionCreationPolicy(SessionCreationPolicy.STATELESS) }
            .cors(Customizer.withDefaults())
            .csrf { it.disable() }
            .authorizeHttpRequests { auth ->
                // Endpoint public : utilisé par le frontend pour récupérer la config MSAL (AC-2)
                auth.requestMatchers("/api/config/auth").permitAll()
                // Actuator health/info — accessible sans auth (monitoring)
                auth.requestMatchers("/actuator/health", "/actuator/info").permitAll()
                // Toutes les autres routes nécessitent un JWT valide (AC-4, AC-6)
                auth.anyRequest().authenticated()
            }
            .oauth2ResourceServer { oauth2 ->
                oauth2.jwt { jwt ->
                    jwt.decoder(jwtDecoder())
                }
            }

        return http.build()
    }

    /**
     * JwtDecoder avec validation d'audience et d'expiration explicites.
     * Spring Security valide automatiquement la signature via JWKS Azure AD.
     * La validation d'audience est ajoutée ici pour AC-7 (tenant + audience).
     */
    @Bean
    fun jwtDecoder(): JwtDecoder {
        val issuerUri = "https://login.microsoftonline.com/${azureAdProperties.tenantId}/v2.0"

        val decoder = NimbusJwtDecoder
            .withJwkSetUri("$issuerUri/keys")
            .build()

        val validators = mutableListOf<OAuth2TokenValidator<Jwt>>(
            JwtTimestampValidator(),
            JwtIssuerValidator(issuerUri),
            AudienceValidator(azureAdProperties.audienceList)
        )

        decoder.setJwtValidator(DelegatingOAuth2TokenValidator(validators))
        return decoder
    }
}
