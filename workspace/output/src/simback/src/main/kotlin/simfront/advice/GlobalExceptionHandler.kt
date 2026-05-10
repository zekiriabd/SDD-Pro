package simfront.advice

import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.security.access.AccessDeniedException
import org.springframework.security.core.AuthenticationException
import org.springframework.security.oauth2.jwt.JwtValidationException
import org.springframework.web.bind.MethodArgumentNotValidException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.method.annotation.HandlerMethodValidationException
import simfront.exception.ResourceNotFoundException
import java.net.URI

private val log = LoggerFactory.getLogger(GlobalExceptionHandler::class.java)

/**
 * Gestionnaire global d'exceptions de sécurité.
 * Retourne des ProblemDetail RFC 9457 sans fuite d'information (AC-5, AC-7).
 * Les causes réelles sont loguées uniquement en DEBUG (jamais exposées au client).
 */
@RestControllerAdvice
class GlobalExceptionHandler {

    /**
     * Token JWT expiré ou invalide → 401 (AC-5).
     * Intercepté avant que la logique métier ne soit atteinte.
     */
    @ExceptionHandler(JwtValidationException::class)
    fun handleJwtValidation(ex: JwtValidationException): ProblemDetail {
        log.debug("JWT validation failed: {}", ex.message)
        return ProblemDetail.forStatusAndDetail(
            HttpStatus.UNAUTHORIZED,
            "Authentication token is invalid or expired"
        ).apply {
            type = URI.create("https://datatracker.ietf.org/doc/html/rfc6750#section-3.1")
        }
    }

    /**
     * Requête sans token ou avec token non parseable → 401 (AC-6).
     */
    @ExceptionHandler(AuthenticationException::class)
    fun handleAuthentication(ex: AuthenticationException): ProblemDetail {
        log.debug("Authentication failed: {}", ex.message)
        return ProblemDetail.forStatusAndDetail(
            HttpStatus.UNAUTHORIZED,
            "Authentication required"
        ).apply {
            type = URI.create("https://datatracker.ietf.org/doc/html/rfc6750#section-3.1")
        }
    }

    /**
     * Utilisateur authentifié mais hors tenant / groupes autorisés → 403 sans fuite (AC-7).
     * Le message générique ne révèle pas la cause exacte du refus.
     */
    @ExceptionHandler(AccessDeniedException::class)
    fun handleAccessDenied(ex: AccessDeniedException): ProblemDetail {
        log.debug("Access denied: {}", ex.message)
        return ProblemDetail.forStatusAndDetail(
            HttpStatus.FORBIDDEN,
            "Access denied"
        ).apply {
            type = URI.create("https://datatracker.ietf.org/doc/html/rfc7807")
        }
    }

    /**
     * Bean Validation failure on @Valid DTO fields (AC-9: pageSize hors limites → 400).
     * Formats all field errors into a structured ProblemDetail.
     */
    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleMethodArgumentNotValid(ex: MethodArgumentNotValidException): ProblemDetail {
        log.debug("Validation error: {}", ex.message)
        val detail = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST)
        detail.title = "Validation échouée"
        detail.detail = ex.bindingResult.fieldErrors
            .joinToString("; ") { "${it.field}: ${it.defaultMessage}" }
        return detail
    }

    /**
     * Validation failure on @ModelAttribute query params (AC-9: pageSize via Spring 6.1+ validation).
     */
    @ExceptionHandler(HandlerMethodValidationException::class)
    fun handleHandlerMethodValidation(ex: HandlerMethodValidationException): ProblemDetail {
        log.debug("Handler method validation error: {}", ex.message)
        val detail = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST)
        detail.title = "Paramètre invalide"
        detail.detail = ex.parameterValidationResults
            .flatMap { it.resolvableErrors }
            .joinToString("; ") { it.defaultMessage ?: "Valeur invalide" }
        return detail
    }

    /**
     * Requested resource not found → 404 (AC-10 US 1-4).
     * Triggered by service when a PDV, Format, NatureLien or MotifInactivite id is unknown.
     */
    @ExceptionHandler(ResourceNotFoundException::class)
    fun handleNotFound(ex: ResourceNotFoundException): ProblemDetail {
        log.debug("Resource not found: {}", ex.message)
        return ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            ex.message ?: "Resource not found"
        ).apply {
            type = URI.create("https://datatracker.ietf.org/doc/html/rfc9457")
        }
    }
}
