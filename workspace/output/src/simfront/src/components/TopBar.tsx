import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { LangSwitcher } from '@/components/LangSwitcher'
import { ContextSwitcher } from '@/components/ContextSwitcher'
import { UserMenu } from '@/components/UserMenu'
import { cn } from '@/lib/utils'

/**
 * Logo brand en CSS gradient pur — identique au HTML mockup (aucun asset image).
 */
function BrandLogo() {
  return (
    <div
      className="size-[34px] shrink-0 rounded-full"
      style={{
        background: [
          'radial-gradient(circle at 30% 35%, #b3e0c8 0 28%, transparent 29%)',
          'radial-gradient(circle at 70% 65%, #f4c89a 0 28%, transparent 29%)',
          'linear-gradient(135deg, #c9e8d4, #f4d6b0)',
        ].join(', '),
      }}
    />
  )
}

/**
 * Barre de navigation principale — conforme au HTML mockup.
 * Structure :
 * - Brand : logo CSS gradient + "média" / "performances" (2 lignes)
 * - Nav : 3 liens "Points de vente" (active), "Périmètres d'exploitation",
 *         "Configuration des redevances"
 * - Droite : <LangSwitcher />, <ContextSwitcher />, <UserMenu />
 * Hauteur 64px, border-bottom — verbatim HTML .topbar.
 * Les <a> de nav traduits en <Link> TanStack Router.
 */
export function TopBar() {
  const { t } = useTranslation()

  return (
    <header
      className="flex h-16 items-center shrink-0 border-b bg-white"
      style={{
        borderBottomColor: 'var(--sim-line)',
        padding: '0 28px',
        gap: '36px',
      }}
    >
      {/* Brand */}
      <div
        className="flex items-center gap-2.5 font-semibold text-[14px] shrink-0"
        style={{ color: 'var(--sim-ink)', lineHeight: 1.1 }}
      >
        <BrandLogo />
        <div className="flex flex-col text-[13px]">
          <span className="font-semibold" style={{ color: 'var(--sim-ink)' }}>
            {t('brand.line1')}
          </span>
          <span className="font-semibold" style={{ color: 'var(--sim-ink)' }}>
            {t('brand.line2')}
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 items-center" style={{ gap: '28px' }}>
        <Link
          to="/pdv"
          className={cn(
            'text-[14px] no-underline px-0.5 py-2 relative',
            'font-normal',
          )}
          style={{ color: 'var(--sim-muted)' }}
          activeProps={{
            style: { color: 'var(--sim-accent)', fontWeight: 500 },
            className: 'nav-active',
          }}
          inactiveProps={{
            style: { color: 'var(--sim-muted)' },
          }}
        >
          {t('nav.pointsDeVente')}
        </Link>
        <Link
          to="/perimetre-exploitation"
          className="text-[14px] no-underline px-0.5 py-2 font-normal"
          style={{ color: 'var(--sim-muted)' }}
          activeProps={{
            style: { color: 'var(--sim-accent)', fontWeight: 500 },
            className: 'nav-active',
          }}
          inactiveProps={{
            style: { color: 'var(--sim-muted)' },
          }}
        >
          {t('nav.perimetres')}
        </Link>
        <Link
          to="/configuration-redevances"
          className="text-[14px] no-underline px-0.5 py-2 font-normal"
          style={{ color: 'var(--sim-muted)' }}
          activeProps={{
            style: { color: 'var(--sim-accent)', fontWeight: 500 },
            className: 'nav-active',
          }}
          inactiveProps={{
            style: { color: 'var(--sim-muted)' },
          }}
        >
          {t('nav.configuration')}
        </Link>
      </nav>

      {/* Droite : LangSwitcher + ContextSwitcher + UserMenu */}
      <div className="flex items-center" style={{ gap: '14px' }}>
        <LangSwitcher />
        <ContextSwitcher />
        <UserMenu />
      </div>
    </header>
  )
}
