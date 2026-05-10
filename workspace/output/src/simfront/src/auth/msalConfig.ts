import { type Configuration, PublicClientApplication } from '@azure/msal-browser'

export interface AuthConfig {
  authority: string
  clientId: string
  scopes: string[]
  redirectUri: string
}

const BACKEND_AUTH_CONFIG_URL = `${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:44328'}/api/config/auth`

/**
 * Fetch la configuration MSAL depuis le backend AVANT toute instanciation.
 * Obligatoire (azure-ad §5.2 Piège 4) — aucune valeur Azure AD hardcodée.
 */
export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(BACKEND_AUTH_CONFIG_URL)
  if (!res.ok) {
    throw new Error(
      `Endpoint /api/config/auth indisponible (${res.status}). ` +
        `Vérifier que le backend tourne sur ${BACKEND_AUTH_CONFIG_URL} ` +
        'et que les variables AZ_TENANTID, AZ_CLIENTID, AZ_DOMAIN sont définies.',
    )
  }
  return res.json() as Promise<AuthConfig>
}

/**
 * Construit l'instance PublicClientApplication à partir de la config fetchée.
 * À appeler depuis main.tsx après fetchAuthConfig().
 */
export function buildMsalConfig(config: AuthConfig): Configuration {
  return {
    auth: {
      clientId: config.clientId,
      authority: config.authority,
      redirectUri: config.redirectUri,
      postLogoutRedirectUri: config.redirectUri,
    },
    cache: {
      cacheLocation: 'sessionStorage',
    },
  }
}

export async function getMsalInstance(): Promise<PublicClientApplication> {
  const config = await fetchAuthConfig()
  const msalConfig = buildMsalConfig(config)
  const instance = new PublicClientApplication(msalConfig)
  await instance.initialize()
  return instance
}
