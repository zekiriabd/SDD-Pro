import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

interface NavItem {
  labelKey: string
  to: string
}

const NAV_ITEMS: NavItem[] = [
  { labelKey: 'nav.perimetreExploitation', to: '/perimetre-exploitation' },
  { labelKey: 'nav.configurationRedevances', to: '/configuration-redevances' },
]

export function AppSidebar() {
  const { t } = useTranslation()

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r bg-sidebar">
      <div className="flex h-14 items-center px-4 border-b">
        <span className="text-xs font-semibold uppercase tracking-widest text-sidebar-foreground/60">
          Navigation
        </span>
      </div>

      <Separator />

      <nav className="flex flex-1 flex-col gap-1 p-2" aria-label="Navigation principale">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.to}
            to={item.to as '/'}
            activeProps={{ className: 'bg-sidebar-primary text-sidebar-primary-foreground' }}
            inactiveProps={{
              className:
                'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
            }}
            className={cn(
              'block w-full rounded-md px-3 py-2 text-sm font-medium transition-colors text-left no-underline'
            )}
          >
            {t(item.labelKey)}
          </Link>
        ))}
      </nav>
    </aside>
  )
}
