import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type PublicClientApplication, InteractionType } from '@azure/msal-browser'
import { MsalProvider, MsalAuthenticationTemplate } from '@azure/msal-react'
import { I18nextProvider } from 'react-i18next'

import './i18n/index'
import './index.css'
import i18n from './i18n/index'

import { routeTree } from './routeTree.gen'
import { getMsalInstance } from './auth/msalConfig'

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createRouter<typeof routeTree>>
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000,
    },
  },
})

/**
 * Bootstrap asynchrone :
 * 1. fetchAuthConfig() → fetch /api/config/auth → config MSAL en RAM
 * 2. new PublicClientApplication(config) — aucune valeur Azure AD hardcodée
 * 3. Mount <MsalProvider> + <QueryClientProvider> + <RouterProvider> + <I18nextProvider>
 * Obligatoire (azure-ad §5.2 Piège 4).
 */
async function bootstrap() {
  let msalInstance: PublicClientApplication

  try {
    msalInstance = await getMsalInstance()
  } catch (err) {
    // Backend non disponible — afficher un message clair (pas d'erreur MSAL obscure)
    document.getElementById('root')!.innerHTML =
      '<div style="padding:2rem;font-family:sans-serif;color:#c00">' +
      '<h2>Erreur de démarrage</h2>' +
      `<p>${String(err)}</p>` +
      '<p>Vérifier que le backend est démarré et accessible.</p>' +
      '</div>'
    return
  }

  const router = createRouter({ routeTree })

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <MsalAuthenticationTemplate interactionType={InteractionType.Redirect}>
          <QueryClientProvider client={queryClient}>
            <I18nextProvider i18n={i18n}>
              <RouterProvider router={router} />
            </I18nextProvider>
          </QueryClientProvider>
        </MsalAuthenticationTemplate>
      </MsalProvider>
    </StrictMode>,
  )
}

void bootstrap()
