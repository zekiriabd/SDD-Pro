/**
 * Route /pdv/:pdvId — détail d'un Point de vente.
 *
 * AC-9 : protégée par authentification Azure AD (même guard que /pdv).
 * Extrait pdvId depuis l'URL et l'injecte dans PointDeVentePage.
 *
 * Pattern de protection : vérifie la présence d'un token MSAL en
 * sessionStorage (identique au guard de /pdv parent).
 */
import { useEffect } from 'react'
import { PointDeVentePage } from '@/pages/PointDeVentePage'

/** Extrait un entier depuis l'URL pathname /pdv/:id */
function extractPdvId(): number {
  const match = window.location.pathname.match(/\/pdv\/(\d+)/)
  return match ? parseInt(match[1], 10) : 0
}

/** Vérifie si un token MSAL est présent en sessionStorage. */
function hasMsalToken(): boolean {
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key && key.includes('accesstoken')) return true
  }
  return false
}

/**
 * Guard de route Azure AD (AC-9).
 * Redirige vers / si non authentifié.
 */
export function PdvDetailRoute() {
  const pdvId = extractPdvId()

  useEffect(() => {
    if (!hasMsalToken()) {
      window.location.replace('/')
    }
  }, [])

  if (!hasMsalToken()) {
    return null
  }

  if (!pdvId || pdvId <= 0) {
    return (
      <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
        <p>ID de point de vente invalide.</p>
        <a href="/pdv">Retour à la liste</a>
      </div>
    )
  }

  return <PointDeVentePage pdvId={pdvId} />
}

export default PdvDetailRoute
