import { createFileRoute } from '@tanstack/react-router'

import { ConfigurationRedevancesPage } from '@/pages/ConfigurationRedevancesPage'

export const Route = createFileRoute('/configuration-redevances/')({
  component: ConfigurationRedevancesPage,
})
