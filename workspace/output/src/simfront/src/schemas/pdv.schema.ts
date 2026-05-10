import { z } from 'zod'

/**
 * Validation du pageSize côté client (AC-9).
 * pageSize valide : entier, 1..1000.
 * Valeurs hors limites (0, négatif, > 1000) → valeur par défaut appliquée,
 * envoi désactivé tant que la valeur est invalide.
 */
export const PageSizeSchema = z.number().int().min(1).max(1000)

export const PdvQueryParamsSchema = z.object({
  page: z.number().int().min(0).default(0),
  pageSize: PageSizeSchema.default(10),
  search: z.string().optional(),
  // Per-column filters (AC-4)
  enseigne: z.string().optional(),
  format: z.string().optional(),
  codePostal: z.string().optional(),
  commune: z.string().optional(),
  natureLien: z.string().optional(),
  surfaceMin: z.number().int().optional(),
  surfaceMax: z.number().int().optional(),
  pays: z.string().optional(),
  actif: z.boolean().optional(),
  motifInactivite: z.string().optional(),
  exploite: z.boolean().optional(),
})

export type PdvQueryParams = z.infer<typeof PdvQueryParamsSchema>

/** DTO correspondant à PointDeVenteOutputDto backend */
export interface PdvDto {
  id: number
  enseigne: string | null
  format: string | null
  formatId: number | null
  codePostal: string | null
  commune: string | null
  natureLien: string | null
  natureLienId: number | null
  surface: number | null
  catp: number | null
  pays: string | null
  exploit: string | null
  actif: boolean
  motifInactivite: string | null
  motifInactiviteId: number | null
  exploite: boolean
  // edit pre-fill fields
  adresse: string | null
  complementAdresse: string | null
  departement: string | null
  telephone: string | null
  fax: string | null
  centraleDerattachement: string | null
  codeTdlinx: string | null
  updatedAt: string | null
}

/** DTO de réponse paginée correspondant à PagedOutputDto<T> backend */
export interface PagedResponse<T> {
  totalCount: number
  filteredCount: number
  page: number
  pageSize: number
  items: T[]
}

/** DTO référentiel (format, nature lien, motif inactivité) */
export interface ReferentielItemDto {
  id: number
  libelle: string
}

/** Regroupement des référentiels (AC-11) */
export interface PdvReferentiels {
  formats: ReferentielItemDto[]
  natureLiens: ReferentielItemDto[]
  motifsInactivite: ReferentielItemDto[]
}
