import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { UserMenu } from '@/components/UserMenu'

export function HeaderBar() {
  const { t } = useTranslation()

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 shrink-0">
      {/* Logo / App name */}
      <span className="text-sm font-semibold tracking-tight">SIM</span>

      {/* Bascule de plateforme */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-1">
            {t('nav.bascule')}
            <ChevronDown className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="center">
          <DropdownMenuItem disabled>
            {t('nav.placeholder')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Menu utilisateur */}
      <UserMenu />
    </header>
  )
}
