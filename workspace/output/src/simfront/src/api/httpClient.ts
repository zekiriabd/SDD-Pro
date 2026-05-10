import { getMsalInstance } from '@/auth/msalConfig'
import {
  InteractionRequiredAuthError,
} from '@azure/msal-browser'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:44328'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Acquiert un Bearer token via MSAL silent refresh.
 * Fallback vers redirect si interaction requise (AC-5).
 */
async function acquireBearerToken(): Promise<string> {
  const instance = await getMsalInstance()
  const accounts = instance.getAllAccounts()
  const account = accounts[0]

  if (!account) {
    await instance.loginRedirect()
    throw new ApiError(401, 'Redirecting to Azure AD login...')
  }

  const silentRequest = {
    scopes: [`api://${account.tenantId}/access_as_user`],
    account,
  }

  try {
    const result = await instance.acquireTokenSilent(silentRequest)
    return result.accessToken
  } catch (err) {
    if (err instanceof InteractionRequiredAuthError) {
      await instance.acquireTokenRedirect(silentRequest)
      throw new ApiError(401, 'Redirecting to Azure AD for token refresh...')
    }
    throw err
  }
}

/**
 * Client HTTP typé — fetch + Bearer token automatique (AC-3).
 * Sur 401 : relance acquireTokenSilent une fois, puis acquireTokenRedirect (AC-5).
 * Base URL depuis import.meta.env.VITE_API_BASE_URL (react.md §3.1).
 */
export async function apiFetch<TResponse>(
  input: string,
  init?: RequestInit,
): Promise<TResponse> {
  const url = input.startsWith('http') ? input : `${API_BASE_URL}${input}`

  const doFetch = async (token: string): Promise<Response> => {
    return fetch(url, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
        Authorization: `Bearer ${token}`,
      },
    })
  }

  let token: string
  try {
    token = await acquireBearerToken()
  } catch (err) {
    throw new ApiError(401, `Token acquisition failed: ${String(err)}`)
  }

  let response = await doFetch(token)

  // Retry une fois si 401 (token expiré côté serveur — AC-5)
  if (response.status === 401) {
    try {
      token = await acquireBearerToken()
      response = await doFetch(token)
    } catch {
      throw new ApiError(401, 'Unauthenticated after token refresh attempt')
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      `API error ${response.status} on ${url}`,
    )
  }

  if (response.status === 204) {
    return undefined as unknown as TResponse
  }

  return response.json() as Promise<TResponse>
}
