import { useCallback } from 'react'
import {
  useMsal,
  useIsAuthenticated,
  useAccount,
} from '@azure/msal-react'
import {
  InteractionRequiredAuthError,
  type SilentRequest,
} from '@azure/msal-browser'

export interface AuthUser {
  name: string
  email: string
  initials: string
}

export interface UseAuthResult {
  user: AuthUser | null
  isAuthenticated: boolean
  token: string | null
  getToken: () => Promise<string>
  logout: () => Promise<void>
}

/**
 * Hook useAuth() — expose user, token, getToken, logout.
 * Conforme azure-ad §5.2 : pas de décodage manuel du JWT,
 * pas de stockage manuel du token.
 */
export function useAuth(): UseAuthResult {
  const { instance, accounts } = useMsal()
  const isAuthenticated = useIsAuthenticated()
  const account = useAccount(accounts[0] ?? null)

  const displayName = account?.name ?? account?.username ?? ''
  const email = account?.username ?? ''
  const initials =
    displayName
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w: string) => w[0]?.toUpperCase() ?? '')
      .join('') || (email[0]?.toUpperCase() ?? '?')

  const user: AuthUser | null =
    account ? { name: displayName, email, initials } : null

  /**
   * Acquiert un Bearer token via silent refresh, avec fallback redirect.
   * AC-3 + AC-5.
   */
  const getToken = useCallback(async (): Promise<string> => {
    if (!account) {
      await instance.loginRedirect()
      throw new Error('Redirecting to Azure AD login...')
    }

    const silentRequest: SilentRequest = {
      scopes: [`api://${account.tenantId}/access_as_user`],
      account,
    }

    try {
      const result = await instance.acquireTokenSilent(silentRequest)
      return result.accessToken
    } catch (err) {
      if (err instanceof InteractionRequiredAuthError) {
        // Token expiré ou interaction requise — redirect (AC-5)
        await instance.acquireTokenRedirect(silentRequest)
        throw new Error('Redirecting to Azure AD for token refresh...')
      }
      throw err
    }
  }, [instance, account])

  /**
   * Déconnexion — termine la session et retourne vers Azure AD (AC-8).
   */
  const logout = useCallback(async (): Promise<void> => {
    await instance.logoutRedirect({
      account: account ?? undefined,
    })
  }, [instance, account])

  return {
    user,
    isAuthenticated,
    token: null, // token on-demand via getToken() — jamais stocké (azure-ad §8)
    getToken,
    logout,
  }
}
