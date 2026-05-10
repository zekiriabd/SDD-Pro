/**
 * PointDeVentePage — page détail d'un PDV (AC-1, AC-2, AC-3, AC-5).
 *
 * - Breadcrumb "Points de vente » Points de vente #{id}" (libellés verbatim)
 * - Titre "Points de vente #{id} {NOM_PDV}" (libellé verbatim structuré)
 * - Tabs shadcn : "INFORMATIONS POINTS DE VENTE" / "PÉRIMÈTRES D'EXPLOITATION" / "MATÉRIELS"
 * - Sidebar PdvSidebar + contenu PdvInfoGenerales
 * - Bouton "MODIFIER" (variant outline, icône Pencil)
 * - "Dernière modification le {date}" avec date colorée (#4a8fd9)
 * - Orchestration dialogs création / modification / suppression
 */
import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { PdvSidebar } from '@/components/pdv/PdvSidebar'
import { PdvInfoGenerales } from '@/components/pdv/PdvInfoGenerales'
import { PdvFormDialog } from '@/components/pdv/PdvFormDialog'
import { PdvDeleteDialog } from '@/components/pdv/PdvDeleteDialog'
import { usePdvQuery } from '@/hooks/pdv/usePdvQuery'

// ---------------------------------------------------------------------------
// QueryClient isolé — à remplacer par le provider global (App.tsx)
// ---------------------------------------------------------------------------
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, refetchOnWindowFocus: false },
  },
})

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PointDeVentePageProps {
  /** ID du PDV extrait de la route (ex. parseInt(params.pdvId)) */
  pdvId: number
}

// ---------------------------------------------------------------------------
// Inner component (accès aux hooks Query)
// ---------------------------------------------------------------------------

function PointDeVentePageInner({ pdvId }: PointDeVentePageProps) {
  const [activeSection, setActiveSection] = useState('Informations générales')
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)

  const { data: pdv, isLoading, isError } = usePdvQuery(pdvId)

  if (isLoading) {
    return (
      <div className="p-8 text-[13px]" style={{ color: 'var(--sim-muted)' }}>
        Chargement…
      </div>
    )
  }

  if (isError || !pdv) {
    return (
      <div className="p-8 text-[13px]" style={{ color: 'var(--sim-muted)' }}>
        Erreur lors du chargement du point de vente.
      </div>
    )
  }

  // Nom du PDV pour affichage
  const pdvName = pdv.enseigne ?? `PDV #${pdvId}`

  // Formatage de la date de dernière modification
  const lastMod = pdv.updatedAt
    ? new Date(pdv.updatedAt).toLocaleDateString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

  return (
    <div
      className="px-[26px] pb-10 pt-[14px]"
      style={{ backgroundColor: 'var(--sim-bg-page)' }}
    >
      {/* Breadcrumb — libellés verbatim du HTML mockup */}
      <div
        className="flex items-center gap-2 mb-2 text-[13px]"
        style={{ color: 'var(--sim-link, #7a3fb5)' }}
      >
        <a
          href="/pdv"
          className="hover:underline cursor-pointer"
          style={{ color: 'var(--sim-link, #7a3fb5)' }}
        >
          Points de vente
        </a>
        <span style={{ color: 'var(--sim-link, #7a3fb5)' }}>»</span>
        <a
          className="hover:underline cursor-pointer"
          style={{ color: 'var(--sim-link, #7a3fb5)' }}
        >
          Points de vente #{pdvId}
        </a>
      </div>

      {/* Titre — libellé verbatim structuré */}
      <div
        className="mb-[18px] text-[13px] font-bold"
        style={{ color: 'var(--sim-ink)' }}
      >
        Points de vente #{pdvId} {pdvName}
      </div>

      {/* Tabs shadcn — libellés verbatim */}
      <Tabs defaultValue="informations">
        <TabsList
          className="rounded-none border-b px-1 h-auto bg-transparent gap-7 justify-start"
          style={{ borderColor: 'var(--sim-line)' }}
        >
          <TabsTrigger
            value="informations"
            className="text-[12px] font-semibold tracking-[0.06em] pb-[14px] pt-[14px] px-1 rounded-none border-b-2 border-transparent data-[state=active]:border-b-[2px] data-[state=active]:text-[var(--sim-accent)] data-[state=active]:border-[var(--sim-accent)] bg-transparent shadow-none"
            style={{ color: 'var(--sim-muted)' }}
          >
            INFORMATIONS POINTS DE VENTE
          </TabsTrigger>
          <TabsTrigger
            value="perimetres"
            className="text-[12px] font-semibold tracking-[0.06em] pb-[14px] pt-[14px] px-1 rounded-none border-b-2 border-transparent bg-transparent shadow-none"
            style={{ color: 'var(--sim-muted)' }}
          >
            PÉRIMÈTRES D'EXPLOITATION
          </TabsTrigger>
          <TabsTrigger
            value="materiels"
            className="text-[12px] font-semibold tracking-[0.06em] pb-[14px] pt-[14px] px-1 rounded-none border-b-2 border-transparent bg-transparent shadow-none"
            style={{ color: 'var(--sim-muted)' }}
          >
            MATÉRIELS
          </TabsTrigger>
        </TabsList>

        {/* Onglet actif : Informations points de vente */}
        <TabsContent value="informations" className="mt-0">
          <div
            className="grid mt-0"
            style={{ gridTemplateColumns: '220px 1fr' }}
          >
            {/* Sidebar navigation */}
            <PdvSidebar
              activeSection={activeSection}
              onSectionChange={setActiveSection}
            />

            {/* Contenu principal */}
            <section
              className="px-7 py-5 pb-8 relative"
              style={{ backgroundColor: 'var(--sim-bg-page)' }}
            >
              {/* En-tête section */}
              <div className="flex items-start justify-between mb-6">
                <h1
                  className="text-[18px] font-semibold m-0"
                  style={{ color: 'var(--sim-ink)' }}
                >
                  Informations générales
                </h1>
                <div className="text-right">
                  {/* Bouton MODIFIER — libellé verbatim, icône Pencil lucide-react */}
                  <Button
                    variant="outline"
                    size="sm"
                    className="inline-flex items-center gap-[6px] h-[30px] px-[14px] text-[11px] font-semibold tracking-[0.06em] rounded-[5px] border bg-white"
                    style={{
                      color: 'var(--sim-accent)',
                      borderColor: 'var(--sim-accent-soft)',
                    }}
                    onClick={() => setIsEditOpen(true)}
                  >
                    <Pencil size={12} />
                    MODIFIER
                  </Button>
                  {/* Dernière modification */}
                  {lastMod && (
                    <div
                      className="text-[11px] mt-2"
                      style={{ color: 'var(--sim-muted)' }}
                    >
                      Dernière modification le{' '}
                      <span
                        className="font-medium"
                        style={{ color: '#4a8fd9' }}
                      >
                        {lastMod}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Grille informations générales */}
              <PdvInfoGenerales pdv={pdv} />
            </section>
          </div>
        </TabsContent>

        {/* Onglets en attente d'implémentation (US séparées) */}
        <TabsContent value="perimetres" className="mt-4">
          <div className="p-8 text-[13px]" style={{ color: 'var(--sim-muted)' }}>
            Périmètres d'exploitation — disponible dans une prochaine US.
          </div>
        </TabsContent>
        <TabsContent value="materiels" className="mt-4">
          <div className="p-8 text-[13px]" style={{ color: 'var(--sim-muted)' }}>
            Matériels — disponible dans une prochaine US.
          </div>
        </TabsContent>
      </Tabs>

      {/* Dialog modification (AC-2) */}
      <PdvFormDialog
        open={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        mode="edit"
        initialData={pdv}
        pdvId={pdvId}
      />

      {/* Dialog suppression (AC-3) */}
      <PdvDeleteDialog
        open={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        pdvId={pdvId}
        pdvName={pdvName}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Export page avec QueryClientProvider
// ---------------------------------------------------------------------------

export function PointDeVentePage({ pdvId }: PointDeVentePageProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <PointDeVentePageInner pdvId={pdvId} />
    </QueryClientProvider>
  )
}

export default PointDeVentePage
