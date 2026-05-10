import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useMsal } from '@azure/msal-react'

/**
 * Composant rendu sur la route /auth/callback.
 * Route PUBLIQUE — sans guard MSAL (azure-ad §5.2 Piège 5).
 * Après callback réussi, redirige vers la page "Points de vente" (AC-2).
 */
export function AuthCallback() {
  const { instance, inProgress } = useMsal()
  const navigate = useNavigate()

  useEffect(() => {
    // handleRedirectPromise traite le hash MSAL du callback
    instance
      .handleRedirectPromise()
      .then((result) => {
        if (result !== null) {
          // Auth réussie — rediriger vers la page Points de vente (AC-2)
          void navigate({ to: '/pdv' })
        }
      })
      .catch((error: unknown) => {
        // Erreur auth — log structuré (react.md §12)
        if (import.meta.env.DEV) {
          // eslint-disable-next-line no-console
          console.error('[AuthCallback] handleRedirectPromise error:', error)
        }
      })
  }, [instance, navigate])

  if (inProgress !== 'none') {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-muted-foreground">Authentification en cours…</span>
      </div>
    )
  }

  return null
}
