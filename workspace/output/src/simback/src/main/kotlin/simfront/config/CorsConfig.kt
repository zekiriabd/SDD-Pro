package simfront.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.web.cors.CorsConfiguration
import org.springframework.web.cors.CorsConfigurationSource
import org.springframework.web.cors.UrlBasedCorsConfigurationSource
import org.springframework.web.servlet.config.annotation.CorsRegistry
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer

/**
 * Configuration CORS pour permettre au frontend React d'envoyer
 * le header Authorization: Bearer vers ce backend (AC-6).
 * Les origines autorisées proviennent de la variable CORS_ALLOWED_ORIGINS.
 * Si absente, autorise localhost en développement.
 */
@Configuration
class CorsConfig {

    private fun resolveOrigins(): List<String> {
        val raw = System.getenv("CORS_ALLOWED_ORIGINS")
        return if (!raw.isNullOrBlank()) {
            raw.split(",").map { it.trim() }.filter { it.isNotBlank() }
        } else {
            listOf("http://localhost:3000", "http://localhost:5173", "http://localhost:5185")
        }
    }

    /**
     * Bean lu par Spring Security via http.cors(Customizer.withDefaults()) (SecurityConfig).
     * Source de vérité prioritaire pour Spring Security 6.
     */
    @Bean
    fun corsConfigurationSource(): CorsConfigurationSource {
        val config = CorsConfiguration().apply {
            allowedOrigins = resolveOrigins()
            allowedMethods = listOf("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            allowedHeaders = listOf("Authorization", "Content-Type", "Accept")
            allowCredentials = false
            maxAge = 3600
        }
        return UrlBasedCorsConfigurationSource().apply { registerCorsConfiguration("/**", config) }
    }

    /**
     * Fallback pour MVC quand Spring Security ne couvre pas (ex. ressources statiques).
     */
    @Bean
    fun corsConfigurer(): WebMvcConfigurer = object : WebMvcConfigurer {
        override fun addCorsMappings(registry: CorsRegistry) {
            registry.addMapping("/**")
                .allowedOrigins(*resolveOrigins().toTypedArray())
                .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                .allowedHeaders("Authorization", "Content-Type", "Accept")
                .allowCredentials(false)
                .maxAge(3600)
        }
    }
}
