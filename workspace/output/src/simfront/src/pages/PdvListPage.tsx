/**
 * PdvListPage — Page principale "Points de vente".
 *
 * AC-1  : protégée par auth Azure AD (route guard via /pdv route)
 * AC-2  : monte PdvTable avec les 14 colonnes
 * AC-3  : search state → params
 * AC-4  : filtres state → params
 * AC-5  : pageSize state → params
 * AC-6  : titre "Points de vente (N)" avec N = totalCount avant filtrage
 * AC-7  : délégué à PdvTable (OUI/NON)
 * AC-8  : délégué à PdvTable (empty state)
 * AC-9  : validation pageSize délégué à PdvTable + pdv.schema
 * AC-10 : pagination server-side via usePdvList
 */
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PdvTable } from '@/components/pdv/PdvTable'
import { usePdvList, useReferentiels } from '@/hooks/usePdvList'
import type { PdvQueryParams } from '@/schemas/pdv.schema'

// QueryClient isolé pour la page — en prod, remonter dans le provider global (App.tsx)
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

// ---------------------------------------------------------------------------
// Inner component (accès aux hooks Query)
// ---------------------------------------------------------------------------

function PdvListPageInner() {
  const [params, setParams] = useState<PdvQueryParams>({
    page: 0,
    pageSize: 10,
  })

  const { data, isLoading, isFetching } = usePdvList(params)
  const { data: referentiels } = useReferentiels()

  const totalCount = data?.totalCount ?? 0
  const filteredCount = data?.filteredCount ?? 0
  const items = data?.items ?? []

  const emptyReferentiels = { formats: [], natureLiens: [], motifsInactivite: [] }

  function handleParamsChange(next: Partial<PdvQueryParams>) {
    setParams((prev) => ({ ...prev, ...next }))
  }

  function handleExport() {
    // Export déclenché depuis la page — à brancher sur l'endpoint export backend si disponible
    const url = new URL('/api/v1/points-de-vente/export', window.location.origin)
    url.searchParams.set('search', params.search ?? '')
    window.open(url.toString(), '_blank')
  }

  return (
    // layout max-w-[1357px] fidèle au .page du HTML mockup
    <div className="max-w-[1357px] mx-auto px-8 py-8 bg-[var(--sim-bg-page)] min-h-screen">
      {/* Titre de page (AC-6) : "Points de vente (N)" */}
      <h1 className="text-[22px] font-semibold text-[var(--sim-ink)] tracking-[-0.01em] m-0 mb-4">
        Points de vente{totalCount > 0 ? ` (${totalCount})` : ''}
      </h1>

      <PdvTable
        data={items}
        totalCount={totalCount}
        filteredCount={filteredCount}
        params={params}
        onParamsChange={handleParamsChange}
        onExport={handleExport}
        isLoading={isLoading || isFetching}
        referentiels={referentiels ?? emptyReferentiels}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Export page avec QueryClientProvider (à remplacer par le provider global)
// ---------------------------------------------------------------------------

export function PdvListPage() {
  return (
    <QueryClientProvider client={queryClient}>
      <PdvListPageInner />
    </QueryClientProvider>
  )
}

export default PdvListPage
