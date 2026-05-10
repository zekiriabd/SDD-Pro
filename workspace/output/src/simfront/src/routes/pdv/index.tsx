import { createFileRoute } from '@tanstack/react-router'
import { PdvListPage } from '@/pages/PdvListPage'

export const Route = createFileRoute('/pdv/')({
  component: PdvListPage,
})
