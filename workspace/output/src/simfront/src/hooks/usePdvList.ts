/**
 * Hooks TanStack Query pour le domaine PDV.
 *
 * usePdvList  — liste paginée server-side (AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10)
 * useReferentiels — référentiels Format / Nature Lien / Motif Inactivité (AC-11)
 */
import { useQuery } from '@tanstack/react-query'
import { getPdvList, getReferentiels } from '@/api/pdv.api'
import type { PdvQueryParams } from '@/schemas/pdv.schema'

/**
 * Clé de requête stable pour la liste PDV.
 * Tout changement de params (page, pageSize, search, filtres) invalide et
 * déclenche une nouvelle requête — server-side pagination (AC-10).
 */
export function pdvListQueryKey(params: PdvQueryParams) {
  return ['pdv', 'list', params] as const
}

/**
 * Hook principal : liste paginée des PDV.
 *
 * - manualPagination / manualFiltering / manualSorting = true (géré côté backend)
 * - staleTime 30 s (évite refetch sur focus inutile en usage back-office)
 * - keepPreviousData: true → no flash de table vide entre pages (via placeholderData)
 */
export function usePdvList(params: PdvQueryParams) {
  return useQuery({
    queryKey: pdvListQueryKey(params),
    queryFn: () => getPdvList(params),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
}

/**
 * Hook référentiels : Format, Nature Lien, Motif Inactivité (AC-11).
 * Très stable → staleTime 5 min.
 */
export function useReferentiels() {
  return useQuery({
    queryKey: ['pdv', 'referentiels'] as const,
    queryFn: getReferentiels,
    staleTime: 5 * 60_000,
  })
}
