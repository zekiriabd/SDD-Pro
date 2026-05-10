package simfront.exception

/**
 * Thrown when a requested resource cannot be found.
 * Mapped to HTTP 404 by GlobalExceptionHandler (AC-10).
 *
 * Usage: throw ResourceNotFoundException("PointDeVente", id)
 */
class ResourceNotFoundException(resourceName: String, id: Long) :
    RuntimeException("$resourceName with id $id not found")
