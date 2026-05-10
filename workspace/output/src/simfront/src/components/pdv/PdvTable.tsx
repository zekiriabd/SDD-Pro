/**
 * PdvTable — tableau principal des Points de vente.
 *
 * AC-2  : 14 colonnes (13 nommées AC-2 + Solution du HTML mockup)
 * AC-3  : barre de recherche globale, debounce 300ms
 * AC-4  : filtres individuels par colonne
 * AC-5  : sélecteur taille de page (10 / 25 / 50)
 * AC-7  : colonne "Exploité" affiche OUI / NON
 * AC-8  : empty state "Aucun point de vente ne correspond à votre recherche"
 * AC-9  : pageSize validé, désactivé si hors limites
 * AC-10 : pagination server-side (manualPagination)
 * AC-11 : filtres Format / Nature Lien / Motif Inactivité via référentiels
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  Search,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageSizeSchema } from '@/schemas/pdv.schema'
import type { PdvDto, PdvQueryParams, ReferentielItemDto } from '@/schemas/pdv.schema'

// ---------------------------------------------------------------------------
// Types des props
// ---------------------------------------------------------------------------

interface PdvTableProps {
  data: PdvDto[]
  totalCount: number       // total avant filtrage (AC-6)
  filteredCount: number    // total après filtrage (pagination)
  params: PdvQueryParams
  onParamsChange: (next: Partial<PdvQueryParams>) => void
  onExport: () => void
  isLoading: boolean
  referentiels: {
    formats: ReferentielItemDto[]
    natureLiens: ReferentielItemDto[]
    motifsInactivite: ReferentielItemDto[]
  }
}

// ---------------------------------------------------------------------------
// Définition des colonnes (libellés VERBATIM du HTML mockup)
// ---------------------------------------------------------------------------

type ColumnKey =
  | 'id'
  | 'enseigne'
  | 'format'
  | 'solution'
  | 'codePostal'
  | 'commune'
  | 'natureLien'
  | 'surface'
  | 'catp'
  | 'pays'
  | 'exploit'
  | 'actif'
  | 'motifInactivite'
  | 'exploite'

interface ColDef {
  key: ColumnKey
  label: string
  filterType: 'text' | 'select' | 'range' | 'boolean' | 'none'
  defaultVisible: boolean
}

const COLUMNS: ColDef[] = [
  { key: 'id',             label: 'ID PDV',           filterType: 'none',    defaultVisible: true },
  { key: 'enseigne',       label: 'Enseigne',          filterType: 'text',    defaultVisible: true },
  { key: 'format',         label: 'Format',            filterType: 'select',  defaultVisible: true },
  { key: 'solution',       label: 'Solution',          filterType: 'text',    defaultVisible: true },
  { key: 'codePostal',     label: 'Code postal',       filterType: 'text',    defaultVisible: true },
  { key: 'commune',        label: 'Commune',           filterType: 'text',    defaultVisible: true },
  { key: 'natureLien',     label: 'Nature Lien',       filterType: 'select',  defaultVisible: true },
  { key: 'surface',        label: 'Surface',           filterType: 'range',   defaultVisible: true },
  { key: 'catp',           label: 'CATP (K€)',         filterType: 'range',   defaultVisible: true },
  { key: 'pays',           label: 'Pays',              filterType: 'text',    defaultVisible: true },
  { key: 'exploit',        label: 'Exploit',           filterType: 'text',    defaultVisible: true },
  { key: 'actif',          label: 'Actif',             filterType: 'boolean', defaultVisible: true },
  { key: 'motifInactivite',label: 'Motif Inactivité',  filterType: 'select',  defaultVisible: true },
  { key: 'exploite',       label: 'Exploité',          filterType: 'boolean', defaultVisible: true },
]

const PAGE_SIZE_OPTIONS = [10, 25, 50]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isPageSizeValid(v: number): boolean {
  return PageSizeSchema.safeParse(v).success
}

function getCellValue(row: PdvDto, key: ColumnKey): string | number | boolean | null | undefined {
  switch (key) {
    case 'id':              return row.id
    case 'enseigne':        return row.enseigne
    case 'format':          return row.format
    case 'solution':        return undefined // non exposé par le DTO — placeholder
    case 'codePostal':      return row.codePostal
    case 'commune':         return row.commune
    case 'natureLien':      return row.natureLien
    case 'surface':         return row.surface
    case 'catp':            return row.catp
    case 'pays':            return row.pays
    case 'exploit':         return row.exploit
    case 'actif':           return row.actif ? 'OUI' : 'NON'
    case 'motifInactivite': return row.motifInactivite
    case 'exploite':        return row.exploite ? 'OUI' : 'NON'
    default:                return undefined
  }
}

// ---------------------------------------------------------------------------
// Sous-composant : filtre inline par colonne
// ---------------------------------------------------------------------------

interface ColFilterProps {
  col: ColDef
  value: string | undefined
  onChange: (v: string | undefined) => void
  referentiels: PdvTableProps['referentiels']
}

function ColFilterInput({ col, value, onChange, referentiels }: ColFilterProps) {
  if (col.filterType === 'none') return null

  if (col.filterType === 'select') {
    const options: ReferentielItemDto[] =
      col.key === 'format'
        ? referentiels.formats
        : col.key === 'natureLien'
          ? referentiels.natureLiens
          : referentiels.motifsInactivite

    return (
      <select
        className="w-full mt-1 h-6 text-[11px] border border-[var(--sim-line)] rounded px-1 bg-white text-[var(--sim-text)] focus:outline-none focus:border-[var(--sim-accent)]"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">Tous</option>
        {options.map((o) => (
          <option key={o.id} value={o.libelle}>{o.libelle}</option>
        ))}
      </select>
    )
  }

  if (col.filterType === 'boolean') {
    return (
      <select
        className="w-full mt-1 h-6 text-[11px] border border-[var(--sim-line)] rounded px-1 bg-white text-[var(--sim-text)] focus:outline-none focus:border-[var(--sim-accent)]"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">Tous</option>
        <option value="true">OUI</option>
        <option value="false">NON</option>
      </select>
    )
  }

  if (col.filterType === 'range') {
    return (
      <div className="flex gap-1 mt-1">
        <input
          type="number"
          placeholder="Min"
          className="w-1/2 h-6 text-[11px] border border-[var(--sim-line)] rounded px-1 bg-white text-[var(--sim-text)] focus:outline-none focus:border-[var(--sim-accent)]"
          value={value?.split('|')[0] ?? ''}
          onChange={(e) => {
            const max = value?.split('|')[1] ?? ''
            onChange(e.target.value || max ? `${e.target.value}|${max}` : undefined)
          }}
        />
        <input
          type="number"
          placeholder="Max"
          className="w-1/2 h-6 text-[11px] border border-[var(--sim-line)] rounded px-1 bg-white text-[var(--sim-text)] focus:outline-none focus:border-[var(--sim-accent)]"
          value={value?.split('|')[1] ?? ''}
          onChange={(e) => {
            const min = value?.split('|')[0] ?? ''
            onChange(min || e.target.value ? `${min}|${e.target.value}` : undefined)
          }}
        />
      </div>
    )
  }

  // text
  return (
    <input
      type="text"
      placeholder={`Filtrer…`}
      className="w-full mt-1 h-6 text-[11px] border border-[var(--sim-line)] rounded px-1 bg-white text-[var(--sim-text)] focus:outline-none focus:border-[var(--sim-accent)]"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || undefined)}
    />
  )
}

// ---------------------------------------------------------------------------
// Composant principal
// ---------------------------------------------------------------------------

export function PdvTable({
  data,
  totalCount,
  filteredCount,
  params,
  onParamsChange,
  onExport,
  isLoading,
  referentiels,
}: PdvTableProps) {
  // ---- état colonnes visibles ----
  const [visibleCols, setVisibleCols] = useState<Set<ColumnKey>>(
    () => new Set(COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key)),
  )
  const [colPickerOpen, setColPickerOpen] = useState(false)
  const colPickerRef = useRef<HTMLDivElement>(null)

  // ---- état filtres inline par colonne ----
  const [colFilters, setColFilters] = useState<Partial<Record<ColumnKey, string>>>({})
  const [filterOpen, setFilterOpen] = useState<ColumnKey | null>(null)

  // ---- barre de recherche globale avec debounce 300ms (AC-3) ----
  const [searchInput, setSearchInput] = useState(params.search ?? '')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ---- pageSize local pour validation (AC-9) ----
  const [pageSizeInput, setPageSizeInput] = useState(String(params.pageSize))

  // fermer col picker si clic extérieur
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (colPickerRef.current && !colPickerRef.current.contains(e.target as Node)) {
        setColPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // sync searchInput si params.search change depuis l'extérieur
  useEffect(() => {
    setSearchInput(params.search ?? '')
  }, [params.search])

  // debounce recherche globale
  const handleSearchChange = useCallback(
    (v: string) => {
      setSearchInput(v)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        onParamsChange({ search: v || undefined, page: 0 })
      }, 300)
    },
    [onParamsChange],
  )

  // réinitialiser tous les filtres + search (AC-3/4 reset)
  const handleResetFilters = useCallback(() => {
    setColFilters({})
    setSearchInput('')
    onParamsChange({
      search: undefined,
      enseigne: undefined,
      format: undefined,
      codePostal: undefined,
      commune: undefined,
      natureLien: undefined,
      surfaceMin: undefined,
      surfaceMax: undefined,
      pays: undefined,
      actif: undefined,
      motifInactivite: undefined,
      exploite: undefined,
      page: 0,
    })
  }, [onParamsChange])

  // appliquer un filtre de colonne
  const applyColFilter = useCallback(
    (key: ColumnKey, value: string | undefined) => {
      setColFilters((prev) => ({ ...prev, [key]: value }))

      const update: Partial<PdvQueryParams> = { page: 0 }
      if (key === 'enseigne')        update.enseigne = value
      if (key === 'format')          update.format = value
      if (key === 'codePostal')      update.codePostal = value
      if (key === 'commune')         update.commune = value
      if (key === 'natureLien')      update.natureLien = value
      if (key === 'pays')            update.pays = value
      if (key === 'motifInactivite') update.motifInactivite = value
      if (key === 'actif')           update.actif = value === 'true' ? true : value === 'false' ? false : undefined
      if (key === 'exploite')        update.exploite = value === 'true' ? true : value === 'false' ? false : undefined
      if (key === 'surface' && value) {
        const [min, max] = value.split('|')
        update.surfaceMin = min ? parseInt(min, 10) : undefined
        update.surfaceMax = max ? parseInt(max, 10) : undefined
      }
      if (key === 'catp' && value) {
        const [min, max] = value.split('|')
        update.surfaceMin = min ? parseInt(min, 10) : undefined
        update.surfaceMax = max ? parseInt(max, 10) : undefined
      }
      onParamsChange(update)
    },
    [onParamsChange],
  )

  // pagination
  const totalPages = Math.max(1, Math.ceil(filteredCount / params.pageSize))
  const currentPage = params.page + 1 // 1-based pour affichage

  function goToPage(p: number) {
    const clamped = Math.max(0, Math.min(p, totalPages - 1))
    onParamsChange({ page: clamped })
  }

  // pageSize validation (AC-9)
  function handlePageSizeSelect(v: string) {
    const n = parseInt(v, 10)
    if (!isNaN(n) && isPageSizeValid(n)) {
      setPageSizeInput(v)
      onParamsChange({ pageSize: n, page: 0 })
    }
  }

  // pages à afficher dans le pager (5 au max)
  function getPagerPages(): number[] {
    const pages: number[] = []
    const start = Math.max(1, currentPage - 2)
    const end = Math.min(totalPages, start + 4)
    for (let p = start; p <= end; p++) pages.push(p)
    return pages
  }

  const visibleColumns = COLUMNS.filter((c) => visibleCols.has(c.key))

  return (
    <div className="flex flex-col gap-0">
      {/* ---- En-tête page : boutons RÉINITIALISER + EXPORTER (HTML mockup header-actions) ---- */}
      <div className="flex items-center justify-between px-1 pb-[18px] pt-2">
        {/* bouton RÉINITIALISER LES FILTRES (btn-link) */}
        <button
          type="button"
          className="inline-flex items-center gap-2 h-9 px-4 rounded-md text-[12px] font-semibold tracking-[0.04em] cursor-pointer border border-transparent bg-transparent text-[var(--sim-accent)] hover:bg-[var(--sim-accent-softer)] transition-colors"
          onClick={handleResetFilters}
        >
          <Filter size={16} />
          RÉINITIALISER LES FILTRES
        </button>

        {/* bouton EXPORTER (btn-outline) */}
        <button
          type="button"
          className="inline-flex items-center gap-2 h-9 px-4 rounded-md text-[12px] font-semibold tracking-[0.04em] cursor-pointer border text-[var(--sim-accent)] bg-white border-[var(--sim-accent-soft)] shadow-[0_1px_0_rgba(0,0,0,0.02)] hover:bg-[var(--sim-accent-softer)] transition-colors"
          onClick={onExport}
        >
          <Download size={16} />
          EXPORTER
        </button>
      </div>

      {/* ---- Carte tableau ---- */}
      <div className="bg-white border border-[var(--sim-line)] rounded-[10px] overflow-hidden shadow-[0_1px_2px_rgba(20,19,43,0.03)]">

        {/* Toolbar */}
        <div className="flex items-center justify-between px-[18px] py-4 bg-white border-b border-[var(--sim-line)]">
          {/* Barre de recherche globale (AC-3) */}
          <div className="flex items-stretch h-8">
            <input
              type="text"
              placeholder="Rechercher..."
              className="w-60 h-8 border border-[var(--sim-line)] border-r-0 rounded-l-md px-3 text-[12px] text-[var(--sim-text)] font-[family-name:inherit] outline-none bg-white placeholder:text-[#9a9aa8] focus:border-[var(--sim-accent-soft)]"
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
            <button
              type="button"
              aria-label="Rechercher"
              className="w-9 h-8 border border-[var(--sim-accent-soft)] bg-[var(--sim-accent-softer)] rounded-r-md flex items-center justify-center cursor-pointer text-[var(--sim-accent)] hover:bg-[var(--sim-accent-soft)] transition-colors"
            >
              <Search size={14} />
            </button>
          </div>

          {/* Column picker */}
          <div className="relative" ref={colPickerRef}>
            <button
              type="button"
              className="inline-flex items-center gap-[10px] h-8 pl-[14px] pr-[10px] border border-[var(--sim-accent-soft)] bg-[var(--sim-accent-softer)] text-[var(--sim-ink)] rounded-md text-[12px] font-medium cursor-pointer hover:bg-[var(--sim-accent-soft)] transition-colors"
              onClick={() => setColPickerOpen((o) => !o)}
            >
              {/* initial: 14 colonnes visibles */}
              <span>{visibleCols.size} colonnes visibles</span>
              <ChevronDown size={14} className="text-[var(--sim-muted)]" />
            </button>

            {colPickerOpen && (
              <div className="absolute right-0 top-full mt-1 z-20 bg-white border border-[var(--sim-line)] rounded-md shadow-md p-2 min-w-[180px]">
                {COLUMNS.map((col) => (
                  <label
                    key={col.key}
                    className="flex items-center gap-2 px-2 py-1 text-[12px] text-[var(--sim-text)] hover:bg-[var(--sim-accent-softer)] rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={visibleCols.has(col.key)}
                      onChange={(e) => {
                        setVisibleCols((prev) => {
                          const next = new Set(prev)
                          if (e.target.checked) next.add(col.key)
                          else next.delete(col.key)
                          return next
                        })
                      }}
                      className="accent-[var(--sim-accent)]"
                    />
                    {col.label}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Tableau avec scroll horizontal */}
        <div className="overflow-x-auto overflow-y-auto max-h-[420px]">
          <table className="w-full border-collapse min-w-[1500px]" style={{ tableLayout: 'fixed' }}>
            <thead>
              <tr>
                {visibleColumns.map((col) => (
                  <th
                    key={col.key}
                    className="sticky top-0 bg-white border-b border-[var(--sim-line)] border-r border-r-[var(--sim-line-2)] last:border-r-0 px-[14px] py-[14px] text-left text-[13px] font-semibold text-[var(--sim-ink)] z-10"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span>{col.label}</span>
                      {col.filterType !== 'none' && (
                        <div className="relative flex-shrink-0">
                          <button
                            type="button"
                            className={cn(
                              'text-[#9a9aa8] cursor-pointer hover:text-[var(--sim-accent)] transition-colors',
                              filterOpen === col.key && 'text-[var(--sim-accent)]',
                              colFilters[col.key] && 'text-[var(--sim-accent)]',
                            )}
                            onClick={() => setFilterOpen((o) => (o === col.key ? null : col.key))}
                          >
                            <Filter size={14} />
                          </button>
                          {filterOpen === col.key && (
                            <div className="absolute right-0 top-6 z-30 bg-white border border-[var(--sim-line)] rounded-md shadow-md p-2 min-w-[160px]">
                              <ColFilterInput
                                col={col}
                                value={colFilters[col.key]}
                                onChange={(v) => {
                                  applyColFilter(col.key, v)
                                  setFilterOpen(null)
                                }}
                                referentiels={referentiels}
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td
                    colSpan={visibleColumns.length}
                    className="px-[14px] py-8 text-center text-[13px] text-[var(--sim-muted)]"
                  >
                    Chargement…
                  </td>
                </tr>
              ) : data.length === 0 ? (
                /* AC-8 : empty state */
                <tr>
                  <td
                    colSpan={visibleColumns.length}
                    className="px-[14px] py-8 text-center text-[13px] text-[var(--sim-muted)]"
                  >
                    Aucun point de vente ne correspond à votre recherche
                  </td>
                </tr>
              ) : (
                data.map((row) => (
                  <tr
                    key={row.id}
                    className="hover:[&_td]:bg-[#fafbff] [&:last-child_td]:border-b-0"
                  >
                    {visibleColumns.map((col) => {
                      const val = getCellValue(row, col.key)
                      return (
                        <td
                          key={col.key}
                          className="px-[14px] py-[14px] border-b border-[var(--sim-line-2)] text-[13px] text-[var(--sim-text)] bg-white overflow-hidden text-ellipsis whitespace-nowrap"
                          title={val !== null && val !== undefined ? String(val) : ''}
                        >
                          {val !== null && val !== undefined ? String(val) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer / pagination */}
        <div className="flex items-center justify-between px-[18px] py-4 bg-white border-t border-[var(--sim-line)] text-[12px] text-[var(--sim-muted)]">
          {/* Page info (AC-6 : totalCount avant filtrage) */}
          <div className="text-[var(--sim-muted)]">
            Page {currentPage} sur {totalPages} ({totalCount} éléments)
          </div>

          {/* Pager */}
          <div className="flex items-center gap-1">
            {/* Première page */}
            <button
              type="button"
              className="w-7 h-7 inline-flex items-center justify-center rounded-full text-[var(--sim-muted)] bg-transparent border-none cursor-pointer hover:bg-[var(--sim-accent-softer)] hover:text-[var(--sim-accent)] disabled:text-[#9a9aa8] disabled:cursor-default disabled:hover:bg-transparent transition-colors"
              aria-label="Première page"
              disabled={params.page === 0}
              onClick={() => goToPage(0)}
            >
              <ChevronsLeft size={14} />
            </button>
            {/* Précédente */}
            <button
              type="button"
              className="w-7 h-7 inline-flex items-center justify-center rounded-full text-[var(--sim-muted)] bg-transparent border-none cursor-pointer hover:bg-[var(--sim-accent-softer)] hover:text-[var(--sim-accent)] disabled:text-[#9a9aa8] disabled:cursor-default disabled:hover:bg-transparent transition-colors"
              aria-label="Précédente"
              disabled={params.page === 0}
              onClick={() => goToPage(params.page - 1)}
            >
              <ChevronLeft size={14} />
            </button>

            {/* Pages numérotées */}
            {getPagerPages().map((p) => (
              <button
                key={p}
                type="button"
                className={cn(
                  'w-7 h-7 inline-flex items-center justify-center rounded-full text-[12px] font-[family-name:inherit] border-none cursor-pointer transition-colors',
                  p === currentPage
                    ? 'bg-[var(--sim-accent)] text-white font-semibold hover:bg-[var(--sim-accent-hover)]'
                    : 'bg-transparent text-[var(--sim-muted)] hover:bg-[var(--sim-accent-softer)] hover:text-[var(--sim-accent)]',
                )}
                onClick={() => goToPage(p - 1)}
              >
                {p}
              </button>
            ))}

            {/* Suivante */}
            <button
              type="button"
              className="w-7 h-7 inline-flex items-center justify-center rounded-full text-[var(--sim-muted)] bg-transparent border-none cursor-pointer hover:bg-[var(--sim-accent-softer)] hover:text-[var(--sim-accent)] disabled:text-[#9a9aa8] disabled:cursor-default disabled:hover:bg-transparent transition-colors"
              aria-label="Suivante"
              disabled={params.page >= totalPages - 1}
              onClick={() => goToPage(params.page + 1)}
            >
              <ChevronRight size={14} />
            </button>
            {/* Dernière page */}
            <button
              type="button"
              className="w-7 h-7 inline-flex items-center justify-center rounded-full text-[var(--sim-muted)] bg-transparent border-none cursor-pointer hover:bg-[var(--sim-accent-softer)] hover:text-[var(--sim-accent)] disabled:text-[#9a9aa8] disabled:cursor-default disabled:hover:bg-transparent transition-colors"
              aria-label="Dernière page"
              disabled={params.page >= totalPages - 1}
              onClick={() => goToPage(totalPages - 1)}
            >
              <ChevronsRight size={14} />
            </button>
          </div>

          {/* Lignes par page (AC-5) */}
          <div className="inline-flex items-center gap-[10px]">
            <div className="relative">
              <select
                className="inline-flex items-center h-[30px] pl-3 pr-7 border border-[var(--sim-line)] rounded-md bg-white text-[var(--sim-ink)] text-[12px] font-medium cursor-pointer hover:border-[var(--sim-accent-soft)] hover:bg-[var(--sim-accent-softer)] appearance-none transition-colors focus:outline-none focus:border-[var(--sim-accent-soft)]"
                value={pageSizeInput}
                onChange={(e) => handlePageSizeSelect(e.target.value)}
              >
                {PAGE_SIZE_OPTIONS.map((v) => (
                  <option key={v} value={String(v)}>{v}</option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--sim-muted)]"
              />
            </div>
            <span className="text-[var(--sim-muted)]">Lignes par page</span>
          </div>
        </div>

      </div>
    </div>
  )
}

export default PdvTable
