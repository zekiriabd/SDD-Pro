import { Outlet } from '@tanstack/react-router'

import { TopBar } from '@/components/TopBar'

/**
 * Layout principal — routes protégées (AC-2, AC-8).
 * Enveloppe l'app avec <TopBar /> + <main><Outlet /></main>.
 */
export function MainLayout() {
  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ backgroundColor: 'var(--sim-bg-page)' }}>
      <TopBar />
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
