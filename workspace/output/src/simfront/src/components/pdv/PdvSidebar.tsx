/**
 * PdvSidebar — navigation sections du PDV (AC-1, AC-2).
 *
 * H2 et items navigation verbatim depuis le HTML mockup 1-4-Gestion-PDV.html.
 * Styles Tailwind reflétant les tokens CSS --sim-accent, --sim-accent-soft,
 * --sim-accent-softer, --sim-muted extraits du mockup.
 */

interface PdvSidebarProps {
  activeSection: string
  onSectionChange: (section: string) => void
}

const SIDEBAR_SECTIONS = [
  'Informations générales',
  'Informations complémentaires',
  'Codes externes',
  'Périmètre actif',
  'Indicateur de performance',
] as const

export function PdvSidebar({ activeSection, onSectionChange }: PdvSidebarProps) {
  return (
    <aside
      className="border-r py-5"
      style={{ borderColor: 'var(--sim-line)', backgroundColor: 'var(--sim-bg-page)' }}
    >
      {/* H2 — libellé verbatim du HTML mockup */}
      <h2
        className="mx-4 mb-4 text-[14px] font-bold"
        style={{ color: 'var(--sim-ink)' }}
      >
        Informations points de vente
      </h2>

      <nav className="flex flex-col">
        {SIDEBAR_SECTIONS.map((section) => {
          const isActive = activeSection === section
          return (
            <div
              key={section}
              role="button"
              tabIndex={0}
              className="cursor-pointer px-4 py-[10px] text-[13px] border-l-[3px] transition-colors"
              style={{
                color: isActive ? 'var(--sim-accent)' : 'var(--sim-muted)',
                backgroundColor: isActive ? 'var(--sim-accent-soft)' : 'transparent',
                borderLeftColor: isActive ? 'var(--sim-accent)' : 'transparent',
                fontWeight: isActive ? 500 : 400,
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  ;(e.currentTarget as HTMLDivElement).style.backgroundColor =
                    'var(--sim-accent-softer)'
                  ;(e.currentTarget as HTMLDivElement).style.color = 'var(--sim-ink)'
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  ;(e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent'
                  ;(e.currentTarget as HTMLDivElement).style.color = 'var(--sim-muted)'
                }
              }}
              onClick={() => onSectionChange(section)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') onSectionChange(section)
              }}
            >
              {section}
            </div>
          )
        })}
      </nav>
    </aside>
  )
}

export default PdvSidebar
