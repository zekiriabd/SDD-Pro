import { User, Lock, LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/auth/useAuth'

/**
 * Dropdown menu utilisateur.
 * Items verbatim depuis le HTML mockup (ordre exact) :
 * 1. icône User + nom utilisateur (depuis useAuth().user.name)
 * 2. icône Lock + "Admin"
 * 3. icône LogOut + "Déconnexion"
 * Clic "Déconnexion" → useAuth().logout() (AC-8).
 */
export function UserMenu() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()

  const displayName = user?.name ?? ''
  const initials = user?.initials ?? '?'

  function handleSignOut() {
    void logout()
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={displayName}
        className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Avatar
          className="size-9 cursor-pointer"
          style={{ backgroundColor: 'var(--sim-avatar)', color: '#fff' }}
        >
          <AvatarFallback
            className="text-[12px] font-bold"
            style={{ backgroundColor: 'var(--sim-avatar)', color: '#fff' }}
          >
            {initials}
          </AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[180px] py-1.5">
        {/* Item 1 : nom utilisateur */}
        <DropdownMenuItem className="gap-2.5 px-3.5 py-2.5 text-[13px] cursor-default hover:bg-[var(--sim-accent-softer)]">
          <User className="size-4 text-[var(--sim-ink)]" />
          <span>{displayName || t('nav.user.name')}</span>
        </DropdownMenuItem>

        {/* Item 2 : Admin */}
        <DropdownMenuItem className="gap-2.5 px-3.5 py-2.5 text-[13px] cursor-default hover:bg-[var(--sim-accent-softer)]">
          <Lock className="size-4 text-[var(--sim-ink)]" />
          <span>{t('nav.user.role')}</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        {/* Item 3 : Déconnexion */}
        <DropdownMenuItem
          onClick={handleSignOut}
          className="gap-2.5 px-3.5 py-2.5 text-[13px] cursor-pointer hover:bg-[var(--sim-accent-softer)]"
        >
          <LogOut className="size-4 text-[var(--sim-ink)]" />
          <span>{t('nav.logout')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
