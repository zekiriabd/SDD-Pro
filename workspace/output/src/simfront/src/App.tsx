/**
 * App.tsx — point d'entrée SPA simfront.
 *
 * Routing simple basé sur window.location.pathname (TanStack Router sera
 * configuré par arch lors d'un prochain /arch-init complet).
 * Pour l'US 1-2-Consultation-Liste-PDV, la route /pdv est disponible.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PdvRoute } from '@/routes/pdv'
import { PdvDetailRoute } from '@/routes/pdv-detail'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

function Router() {
  const path = window.location.pathname
  if (path.match(/^\/pdv\/\d+/)) {
    return <PdvDetailRoute />
  }
  if (path === '/pdv') {
    return <PdvRoute />
  }
  // Placeholder pour les autres routes (US 1-1 Authentification, etc.)
  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>SIM Frontend</h1>
      <nav>
        <a href="/pdv">Points de vente</a>
      </nav>
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router />
    </QueryClientProvider>
  )
}

export default App
