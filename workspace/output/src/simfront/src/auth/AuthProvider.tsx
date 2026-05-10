import { type ReactNode } from 'react'
import { MsalProvider, MsalAuthenticationTemplate } from '@azure/msal-react'
import {
  type PublicClientApplication,
  InteractionType,
} from '@azure/msal-browser'
import { useLocation } from '@tanstack/react-router'

interface AuthProviderProps {
  instance: PublicClientApplication
  children: ReactNode
}

/**
 * Composant rendu quand l'utilisateur est authentifié mais non autorisé (403).
 * Aucune fuite d'information sur la cause exacte (AC-7).
 */
function AccessDenied() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4">
      <p className="text-sm text-muted-foreground">
        Vous n'avez pas accès à cette application.
      </p>
    </div>
  )
}

/**
 * Composant rendu pendant le chargement de l'état d'authentification.
 */
function AuthLoading() {
  return (
    <div className="flex h-screen items-center justify-center">
      <span className="text-sm text-muted-foreground">Connexion en cours…</span>
    </div>
  )
}

/**
 * Provider racine MSAL React.
 * Enveloppe l'app avec <MsalProvider> + <MsalAuthenticationTemplate interactionType=Redirect>
 * pour forcer la redirection Azure AD sur les routes protégées (azure-ad §5.2 Piège 5).
 * La route /auth/callback est exclue (publique).
 */
export function AuthProvider({ instance, children }: AuthProviderProps) {
  const location = useLocation()
  const isCallbackRoute = location.pathname === '/auth/callback'

  return (
    <MsalProvider instance={instance}>
      {isCallbackRoute ? (
        // Route callback publique — pas de guard (azure-ad §5.2 Piège 5)
        children
      ) : (
        <MsalAuthenticationTemplate
          interactionType={InteractionType.Redirect}
          loadingComponent={AuthLoading}
          errorComponent={AccessDenied}
        >
          {children}
        </MsalAuthenticationTemplate>
      )}
    </MsalProvider>
  )
}
