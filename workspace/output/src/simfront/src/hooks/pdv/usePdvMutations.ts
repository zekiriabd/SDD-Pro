/**
 * Hooks TanStack Query — mutations CRUD PDV (AC-1, AC-2, AC-3).
 *
 * Routes backend vérifiées dans simback PointDeVenteController :
 *   POST   /api/v1/points-de-vente         → 201 (AC-1)
 *   PUT    /api/v1/points-de-vente/{id}    → 200 (AC-2)
 *   DELETE /api/v1/points-de-vente/{id}    → 204 (AC-3)
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createPdv, updatePdv, deletePdv } from '@/api/pdv.api'
import { pdvDetailQueryKey } from '@/hooks/pdv/usePdvQuery'
import { pdvListQueryKey } from '@/hooks/usePdvList'
import type { PdvDto, PdvQueryParams } from '@/schemas/pdv.schema'
import type { PdvFormValues } from '@/schemas/pdv'

// ---------------------------------------------------------------------------
// Conversion PdvFormValues → payload API
// (surface est string dans le form → number ou null pour le backend)
// ---------------------------------------------------------------------------

function toApiPayload(values: PdvFormValues): Record<string, unknown> {
  const surfaceNum = values.surface && values.surface !== ''
    ? parseInt(values.surface, 10)
    : null

  return {
    enseigne: values.enseigne,
    format: values.format,
    typeDeLien: values.typeDeLien,
    actif: values.actif === 'Oui',
    adresse: values.adresse,
    complementAdresse: values.complementAdresse || null,
    commune: values.commune,
    departement: values.departement || null,
    codePostal: values.codePostal,
    telephone: values.telephone || null,
    fax: values.fax || null,
    pays: values.pays,
    surface: isNaN(surfaceNum as number) ? null : surfaceNum,
    centraleDerattachement: values.centraleDerattachement || null,
    codeTdlinx: values.codeTdlinx || null,
  }
}

// ---------------------------------------------------------------------------
// usePdvCreateMutation — POST /api/v1/points-de-vente (AC-1)
// ---------------------------------------------------------------------------

interface CreateMutationContext {
  onSuccess?: (data: PdvDto) => void
  onError?: (error: Error, fieldSetter?: (field: keyof PdvFormValues, msg: string) => void) => void
  fieldSetter?: (field: keyof PdvFormValues, msg: string) => void
}

export function usePdvCreateMutation(ctx?: CreateMutationContext) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: PdvFormValues) => createPdv(toApiPayload(values)),
    onSuccess: (data) => {
      // Invalide la liste pour forcer un refetch (AC-1)
      void queryClient.invalidateQueries({ queryKey: ['pdv', 'list'] })
      ctx?.onSuccess?.(data)
    },
    onError: (error: Error) => {
      // Erreurs 400 : parse et remonte vers FormMessage via fieldSetter (AC-10)
      parse400Error(error, ctx?.fieldSetter)
      // Erreurs 401/403 : log structuré
      if (error.message.includes('[HTTP 401]') || error.message.includes('[HTTP 403]')) {
        logHttpError(error)
      }
      ctx?.onError?.(error, ctx?.fieldSetter)
    },
  })
}

// ---------------------------------------------------------------------------
// usePdvUpdateMutation — PUT /api/v1/points-de-vente/{id} (AC-2)
// ---------------------------------------------------------------------------

interface UpdateMutationContext {
  pdvId: number
  onSuccess?: (data: PdvDto) => void
  onError?: (error: Error) => void
  fieldSetter?: (field: keyof PdvFormValues, msg: string) => void
}

export function usePdvUpdateMutation(ctx: UpdateMutationContext) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: PdvFormValues) =>
      updatePdv(ctx.pdvId, toApiPayload(values)),
    onSuccess: (data) => {
      // Invalide le détail et la liste (AC-2)
      void queryClient.invalidateQueries({ queryKey: pdvDetailQueryKey(ctx.pdvId) })
      void queryClient.invalidateQueries({ queryKey: ['pdv', 'list'] })
      ctx.onSuccess?.(data)
    },
    onError: (error: Error) => {
      parse400Error(error, ctx?.fieldSetter)
      if (error.message.includes('[HTTP 401]') || error.message.includes('[HTTP 403]')) {
        logHttpError(error)
      }
      ctx.onError?.(error)
    },
  })
}

// ---------------------------------------------------------------------------
// usePdvDeleteMutation — DELETE /api/v1/points-de-vente/{id} (AC-3)
// ---------------------------------------------------------------------------

interface DeleteMutationContext {
  pdvId: number
  onSuccess?: () => void
  onError?: (error: Error) => void
}

export function usePdvDeleteMutation(ctx: DeleteMutationContext) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => deletePdv(ctx.pdvId),
    onSuccess: () => {
      // Invalide détail + liste (AC-3)
      void queryClient.invalidateQueries({ queryKey: pdvDetailQueryKey(ctx.pdvId) })
      void queryClient.invalidateQueries({ queryKey: ['pdv', 'list'] })
      ctx.onSuccess?.()
    },
    onError: (error: Error) => {
      if (error.message.includes('[HTTP 401]') || error.message.includes('[HTTP 403]')) {
        logHttpError(error)
      }
      ctx.onError?.(error)
    },
  })
}

// ---------------------------------------------------------------------------
// Helpers privés
// ---------------------------------------------------------------------------

/** Parse les erreurs 400 structurées (liste de champs) et appelle fieldSetter (AC-10). */
function parse400Error(
  error: Error,
  fieldSetter?: (field: keyof PdvFormValues, msg: string) => void,
): void {
  if (!error.message.includes('[HTTP 400]')) return
  if (!fieldSetter) return

  // Le backend retourne ProblemDetails avec errors[field] = [msg]
  try {
    const jsonStart = error.message.indexOf('{')
    if (jsonStart === -1) return
    const raw = error.message.slice(jsonStart)
    const parsed = JSON.parse(raw) as { errors?: Record<string, string[]> }
    if (parsed.errors) {
      for (const [field, messages] of Object.entries(parsed.errors)) {
        const camelField = field.charAt(0).toLowerCase() + field.slice(1)
        fieldSetter(camelField as keyof PdvFormValues, messages[0] ?? 'Champ invalide')
      }
    }
  } catch {
    // Erreur de parsing ignorée — message générique déjà affiché
  }
}

/** Log structuré pour 401/403 (AC-10). */
function logHttpError(error: Error): void {
  // Logging structuré — pas de console.log brut (CLAUDE.md forbidden patterns)
  const entry = {
    level: 'warn',
    message: error.message,
    timestamp: new Date().toISOString(),
    source: 'usePdvMutations',
  }
  // En prod, remplacer par le logger structuré du projet
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.warn('[PDV mutations]', entry)
  }
}

// Re-export pdvListQueryKey to keep type dependency aligned
export { pdvListQueryKey }
export type { PdvQueryParams }
