/**
 * Hook TanStack Query — détail d'un PDV (AC-2).
 *
 * Route backend vérifiée : GET /api/v1/points-de-vente/{id}
 * (PointDeVenteController @GetMapping("/{id}"))
 */
import { useQuery } from '@tanstack/react-query'
import { getPdvById } from '@/api/pdv.api'
import type { PdvDto } from '@/schemas/pdv.schema'

export function pdvDetailQueryKey(pdvId: number) {
  return ['pointDeVente', pdvId] as const
}

/**
 * Hook principal : détail complet d'un PDV.
 *
 * - staleTime 30 s (back-office, données stables)
 * - enabled: false quand pdvId invalide (0 ou négatif)
 */
export function usePdvQuery(pdvId: number): {
  data: PdvDto | undefined
  isLoading: boolean
  isError: boolean
} {
  return useQuery({
    queryKey: pdvDetailQueryKey(pdvId),
    queryFn: () => getPdvById(pdvId),
    staleTime: 30_000,
    enabled: pdvId > 0,
  })
}
