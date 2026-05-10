import { useMsal } from '@azure/msal-react'

export interface UserProfile {
  displayName: string
  initials: string
  email: string
}

export function useUserProfile(): UserProfile {
  const { accounts } = useMsal()
  const account = accounts[0]

  const displayName = account?.name ?? account?.username ?? ''
  const email = account?.username ?? ''

  const initials = displayName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w: string) => w[0]?.toUpperCase() ?? '')
    .join('')
    || (email[0]?.toUpperCase() ?? '?')

  return { displayName, initials, email }
}
