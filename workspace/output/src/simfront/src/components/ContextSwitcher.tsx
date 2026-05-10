import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

/**
 * Items verbatim depuis le HTML mockup — ordre exact conservé.
 * La faute "Admnistration Opérations" est conservée verbatim (source = mockup).
 */
const CONTEXT_ITEMS = [
  { key: 'context.simPatrimoine',      label: 'SIM/Patrimoine' },
  { key: 'context.adminOperations',    label: 'Admnistration Opérations' },
  { key: 'context.operations',         label: 'Opérations' },
  { key: 'context.erp',                label: 'ERP' },
  { key: 'context.portailClient',      label: 'Portail Client' },
  { key: 'context.powerBi',            label: 'Power BI' },
  { key: 'context.administration',     label: 'Administration' },
  { key: 'context.portailEnseigne',    label: 'Portail Enseigne' },
] as const

/**
 * Dropdown sélecteur de contexte applicatif.
 * Item actif par défaut : "SIM/Patrimoine" (verbatim HTML).
 */
export function ContextSwitcher() {
  const { t } = useTranslation()
  const [active, setActive] = useState<string>('context.simPatrimoine')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          'inline-flex items-center gap-1.5 text-[13px] font-normal',
          'bg-transparent border-none cursor-pointer px-1 py-1.5',
          'text-[var(--sim-ink)] hover:text-[var(--sim-accent)]',
          'outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      >
        {t(active as Parameters<typeof t>[0])}
        <ChevronDown className="size-3 text-[var(--sim-muted)]" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[200px] py-1">
        {CONTEXT_ITEMS.map(({ key }) => (
          <DropdownMenuItem
            key={key}
            onClick={() => setActive(key)}
            className={cn(
              'px-3.5 py-2.5 text-[13px] cursor-pointer',
              active === key
                ? 'bg-[var(--sim-accent-soft)] text-[var(--sim-accent)] font-medium'
                : 'hover:bg-[var(--sim-accent-softer)]',
            )}
          >
            {t(key as Parameters<typeof t>[0])}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
