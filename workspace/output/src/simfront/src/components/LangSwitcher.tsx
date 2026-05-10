import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

/**
 * Flag FR reproduit en CSS gradient — identique au HTML source.
 */
function FlagFr({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-block rounded-[1px] overflow-hidden', className)}
      style={{
        width: '18px',
        height: '13px',
        background:
          'linear-gradient(to right, #002395 0 33.3%, #fff 33.3% 66.6%, #ED2939 66.6%)',
      }}
    />
  )
}

/**
 * Flag EN reproduit en CSS gradient — identique au HTML source.
 */
function FlagEn({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-block rounded-[1px]', className)}
      style={{
        width: '18px',
        height: '13px',
        background: [
          'linear-gradient(45deg, transparent 47%, #fff 47% 53%, transparent 53%)',
          'linear-gradient(-45deg, transparent 47%, #fff 47% 53%, transparent 53%)',
          'linear-gradient(45deg, transparent 48.5%, #C8102E 48.5% 51.5%, transparent 51.5%)',
          'linear-gradient(-45deg, transparent 48.5%, #C8102E 48.5% 51.5%, transparent 51.5%)',
          'linear-gradient(0deg, transparent 40%, #fff 40% 60%, transparent 60%)',
          'linear-gradient(90deg, transparent 40%, #fff 40% 60%, transparent 60%)',
          'linear-gradient(0deg, transparent 45%, #C8102E 45% 55%, transparent 55%)',
          'linear-gradient(90deg, transparent 45%, #C8102E 45% 55%, transparent 55%)',
          '#012169',
        ].join(', '),
      }}
    />
  )
}

const LANGS = [
  { code: 'fr', label: 'FR', Flag: FlagFr },
  { code: 'en', label: 'EN', Flag: FlagEn },
] as const

/**
 * Dropdown sélecteur de langue FR/EN.
 * Libellés verbatim depuis le HTML mockup : "FR", "EN".
 * Flags reproduits en CSS gradient (identiques au mockup).
 */
export function LangSwitcher() {
  const { i18n, t } = useTranslation()
  const currentLang = i18n.language.slice(0, 2)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-2 h-8 px-2.5 text-[13px] font-medium border-[var(--sim-line)] hover:bg-[var(--sim-accent-softer)]"
        >
          <FlagFr />
          <span>{t('lang.fr')}</span>
          <ChevronDown className="size-3 text-[var(--sim-muted)]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[90px] p-0 overflow-hidden">
        {LANGS.map(({ code, label, Flag }) => (
          <DropdownMenuItem
            key={code}
            onClick={() => void i18n.changeLanguage(code)}
            className={cn(
              'gap-2 px-3 py-2.5 text-[13px] cursor-pointer',
              currentLang === code
                ? 'bg-[var(--sim-accent-soft)] font-medium'
                : 'hover:bg-[var(--sim-accent-softer)]',
            )}
          >
            <Flag />
            <span>{label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
