/**
 * Route /pdv — Points de vente.
 *
 * AC-1 : protégée par authentification Azure AD.
 * Sans TanStack Router initialisé (arch n'a pas configuré le plugin),
 * cette route est exportée comme composant protégé à monter dans App.tsx.
 *
 * Pattern de protection : vérifie la présence d'un token MSAL en
 * sessionStorage. Si absent → redirige vers /login (ou laisse MSAL gérer).
 * Le token est posé par le provider MSAL configuré dans src/auth/.
 */
import { useEffect } from 'react'
import { PdvListPage } from '@/pages/PdvListPage'

/** Vérifie si un token MSAL est présent en sessionStorage. */
function hasMsalToken(): boolean {
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key && key.includes('accesstoken')) return true
  }
  return false
}

/**
 * Guard de route Azure AD.
 * Redirige vers / (ou déclenche le flow MSAL) si non authentifié.
 */
export function PdvRoute() {
  useEffect(() => {
    if (!hasMsalToken()) {
      // MSAL gère la redirection vers Azure AD via le provider global.
      // En l'absence de provider, rediriger vers la racine.
      window.location.replace('/')
    }
  }, [])

  if (!hasMsalToken()) {
    return null
  }

  return <PdvListPage />
}

export default PdvRoute
