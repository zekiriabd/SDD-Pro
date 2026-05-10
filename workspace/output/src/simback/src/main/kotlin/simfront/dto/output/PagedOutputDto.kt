package simfront.dto.output

/**
 * Generic paged response wrapper.
 *
 * - totalCount: total number of records in DB before any filter (AC-6, AC-8)
 * - filteredCount: total matching records after filters (for pagination controls)
 * - page: zero-based current page index (AC-5, AC-9)
 * - pageSize: number of items per page (AC-5, AC-9)
 * - items: current page payload (AC-10)
 */
data class PagedOutputDto<T>(
    val totalCount: Long,
    val filteredCount: Long,
    val page: Int,
    val pageSize: Int,
    val items: List<T>
)
