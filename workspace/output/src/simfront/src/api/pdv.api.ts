/**
 * Client HTTP typé pour le domaine PDV.
 *
 * Routes vérifiées dans simback :
 *   GET /api/v1/points-de-vente          → PagedOutputDto<PointDeVenteOutputDto>
 *   GET /api/v1/referentiels/formats
 *   GET /api/v1/referentiels/nature-liens
 *   GET /api/v1/referentiels/motifs-inactivite
 *
 * Auth : Bearer JWT depuis sessionStorage (MSAL pattern sans dépendance directe
 * au SDK MSAL — la clé est injectée par src/auth/ via le provider global).
 * LibStrategy: openapi-codegen → types importés depuis src/schemas/pdv.schema.ts.
 */
import type {
  PagedResponse,
  PdvDto,
  PdvQueryParams,
  PdvReferentiels,
} from '@/schemas/pdv.schema'

const API_BASE = `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`

/**
 * Récupère le Bearer token depuis sessionStorage (clé posée par le provider MSAL).
 * Si absent → retourne undefined (l'intercepteur global gérera le 401).
 */
function getBearerToken(): string | undefined {
  // Cherche le token MSAL dans sessionStorage selon la convention Azure AD
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key && key.includes('accesstoken')) {
      try {
        const entry = JSON.parse(sessionStorage.getItem(key) ?? '{}')
        if (entry.secret) return entry.secret as string
      } catch {
        // ignore parse errors
      }
    }
  }
  return undefined
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const token = getBearerToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers as Record<string, string> | undefined),
  }
  const response = await fetch(url, { ...options, headers })
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`[HTTP ${response.status}] ${response.statusText} — ${body}`)
  }
  return response.json() as Promise<T>
}

/**
 * Construit l'URL avec les query params de filtrage/pagination (AC-3, AC-4, AC-5, AC-9).
 * Les valeurs undefined/null sont omises.
 */
function buildPdvListUrl(params: PdvQueryParams): string {
  const url = new URL(`${API_BASE}/points-de-vente`, window.location.origin)
  const entries: [string, string][] = [
    ['page', String(params.page)],
    ['pageSize', String(params.pageSize)],
    ...(params.search ? [['search', params.search] as [string, string]] : []),
    ...(params.enseigne ? [['enseigne', params.enseigne] as [string, string]] : []),
    ...(params.format ? [['format', params.format] as [string, string]] : []),
    ...(params.codePostal ? [['codePostal', params.codePostal] as [string, string]] : []),
    ...(params.commune ? [['commune', params.commune] as [string, string]] : []),
    ...(params.natureLien ? [['natureLien', params.natureLien] as [string, string]] : []),
    ...(params.surfaceMin !== undefined ? [['surfaceMin', String(params.surfaceMin)] as [string, string]] : []),
    ...(params.surfaceMax !== undefined ? [['surfaceMax', String(params.surfaceMax)] as [string, string]] : []),
    ...(params.pays ? [['pays', params.pays] as [string, string]] : []),
    ...(params.actif !== undefined ? [['actif', String(params.actif)] as [string, string]] : []),
    ...(params.motifInactivite ? [['motifInactivite', params.motifInactivite] as [string, string]] : []),
    ...(params.exploite !== undefined ? [['exploite', String(params.exploite)] as [string, string]] : []),
  ]
  entries.forEach(([k, v]) => url.searchParams.set(k, v))
  return url.toString()
}

/**
 * GET /api/v1/points-de-vente — liste paginée filtrée (AC-3, AC-4, AC-5, AC-9, AC-10).
 */
export async function getPdvList(
  params: PdvQueryParams,
): Promise<PagedResponse<PdvDto>> {
  const url = buildPdvListUrl(params)
  return fetchJson<PagedResponse<PdvDto>>(url)
}

// ============================================================================
// CRUD PDV — US 1-4-Gestion-PDV (AC-1, AC-2, AC-3)
// Routes vérifiées dans simback PointDeVenteController :
//   GET    /api/v1/points-de-vente/{id}
//   POST   /api/v1/points-de-vente
//   PUT    /api/v1/points-de-vente/{id}
//   DELETE /api/v1/points-de-vente/{id}
// ============================================================================

/**
 * GET /api/v1/points-de-vente/{id} — détail d'un PDV (AC-2).
 */
export async function getPdvById(id: number): Promise<PdvDto> {
  const url = new URL(`${API_BASE}/points-de-vente/${id}`, window.location.origin)
  return fetchJson<PdvDto>(url.toString())
}

/**
 * POST /api/v1/points-de-vente — création d'un PDV (AC-1).
 * Retourne le PDV créé (201).
 */
export async function createPdv(payload: Record<string, unknown>): Promise<PdvDto> {
  const url = new URL(`${API_BASE}/points-de-vente`, window.location.origin)
  return fetchJson<PdvDto>(url.toString(), {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * PUT /api/v1/points-de-vente/{id} — modification d'un PDV (AC-2).
 * Retourne le PDV modifié (200).
 */
export async function updatePdv(id: number, payload: Record<string, unknown>): Promise<PdvDto> {
  const url = new URL(`${API_BASE}/points-de-vente/${id}`, window.location.origin)
  return fetchJson<PdvDto>(url.toString(), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

/**
 * DELETE /api/v1/points-de-vente/{id} — suppression d'un PDV (AC-3).
 * Retourne void (204).
 */
export async function deletePdv(id: number): Promise<void> {
  const token = getBearerToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const url = new URL(`${API_BASE}/points-de-vente/${id}`, window.location.origin)
  const response = await fetch(url.toString(), { method: 'DELETE', headers })
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`[HTTP ${response.status}] ${response.statusText} — ${body}`)
  }
}

/**
 * GET /api/v1/referentiels/* — référentiels Format, Nature Lien, Motif Inactivité (AC-11).
 */
export async function getReferentiels(): Promise<PdvReferentiels> {
  const [formats, natureLiens, motifsInactivite] = await Promise.all([
    fetchJson<{ id: number; libelle: string }[]>(
      new URL(`${API_BASE}/referentiels/formats`, window.location.origin).toString(),
    ),
    fetchJson<{ id: number; libelle: string }[]>(
      new URL(`${API_BASE}/referentiels/nature-liens`, window.location.origin).toString(),
    ),
    fetchJson<{ id: number; libelle: string }[]>(
      new URL(`${API_BASE}/referentiels/motifs-inactivite`, window.location.origin).toString(),
    ),
  ])
  return { formats, natureLiens, motifsInactivite }
}
