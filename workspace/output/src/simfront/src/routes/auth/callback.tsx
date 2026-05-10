import { createFileRoute } from '@tanstack/react-router'
import { AuthCallback } from '@/auth/AuthCallback'

/**
 * Route TanStack Router file-based : /auth/callback
 * Route PUBLIQUE — pas de guard MSAL (azure-ad §5.2 Piège 5).
 */
export const Route = createFileRoute('/auth/callback')({
  component: AuthCallback,
})
