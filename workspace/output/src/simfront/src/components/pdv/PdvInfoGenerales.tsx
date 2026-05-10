/**
 * PdvInfoGenerales — section "Informations générales" en mode lecture (AC-2).
 *
 * 2 panneaux (Card) en grille 2 colonnes.
 * Libellés verbatim du HTML mockup 1-4-Gestion-PDV.html.
 * Chaque champ : Label + Input disabled.
 */
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import type { PdvDto } from '@/schemas/pdv.schema'

interface PdvInfoGeneralesProps {
  pdv: PdvDto
}

/** Champ en lecture seule avec libellé verbatim. */
function ReadField({ label, value }: { label: string; value: string | number | null | undefined }) {
  const display = value !== null && value !== undefined ? String(value) : ''
  return (
    <div
      className="grid items-center gap-4 py-2"
      style={{ gridTemplateColumns: '180px 1fr' }}
    >
      <Label className="text-[13px]" style={{ color: 'var(--sim-ink)' }}>
        {label}
      </Label>
      <Input
        disabled
        value={display}
        readOnly
        className="h-8 border text-[12px] px-3"
        style={{
          borderColor: 'var(--sim-line)',
          backgroundColor: 'var(--sim-bg-field, #faf9fd)',
          color: 'var(--sim-muted)',
        }}
      />
    </div>
  )
}

/** Panneau (Card) avec bordure et fond blanc. */
function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-[6px] border bg-white p-6"
      style={{ borderColor: 'var(--sim-line)' }}
    >
      {children}
    </div>
  )
}

export function PdvInfoGenerales({ pdv }: PdvInfoGeneralesProps) {
  const actifLabel = pdv.actif ? 'Oui' : 'Non'

  return (
    <div className="grid grid-cols-2 gap-[18px]">
      {/* Panel gauche — libellés verbatim */}
      <Panel>
        <ReadField label="PV ID" value={pdv.id} />
        <ReadField label="Enseigne" value={pdv.enseigne} />
        <ReadField label="Format" value={pdv.format} />
        <ReadField label="Type de lien" value={pdv.natureLien} />
        <ReadField label="Surface (m²)" value={pdv.surface} />
        <ReadField label="Centrale de rattachement" value={pdv.centraleDerattachement} />
        <ReadField label="Code TDlinx" value={pdv.codeTdlinx} />
        <ReadField label="Actif" value={actifLabel} />
      </Panel>

      {/* Panel droit — libellés verbatim */}
      <Panel>
        <ReadField label="Adresse" value={pdv.adresse} />
        <ReadField label="Complément d'adresse" value={pdv.complementAdresse} />
        <ReadField label="Commune" value={pdv.commune} />
        <ReadField label="Département" value={pdv.departement} />
        <ReadField label="Code postal" value={pdv.codePostal} />
        <ReadField label="Téléphone" value={pdv.telephone} />
        <ReadField label="Fax" value={pdv.fax} />
        <ReadField label="Pays" value={pdv.pays} />
      </Panel>
    </div>
  )
}

export default PdvInfoGenerales
