/**
 * PdvDeleteDialog — confirmation de suppression (AC-3, AC-4).
 *
 * - Titre et description verbatim (AC-4 : suppression définitive, verbalisée)
 * - Boutons : "Annuler" + "Supprimer" (destructive)
 * - Consomme usePdvDeleteMutation
 */
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { usePdvDeleteMutation } from '@/hooks/pdv/usePdvMutations'

interface PdvDeleteDialogProps {
  open: boolean
  onClose: () => void
  pdvId: number
  pdvName: string
}

export function PdvDeleteDialog({
  open,
  onClose,
  pdvId,
  pdvName,
}: PdvDeleteDialogProps) {
  const deleteMutation = usePdvDeleteMutation({
    pdvId,
    onSuccess: () => onClose(),
  })

  function handleConfirm() {
    deleteMutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          {/* Titre verbatim (plan §notes) */}
          <DialogTitle className="text-[16px] font-semibold" style={{ color: 'var(--sim-ink)' }}>
            Supprimer le point de vente
          </DialogTitle>
        </DialogHeader>

        {/* Description — AC-4 verbalisé */}
        <div className="py-2 space-y-2">
          <p className="text-[13px]" style={{ color: 'var(--sim-text)' }}>
            Vous êtes sur le point de supprimer le point de vente{' '}
            <span className="font-semibold">{pdvName}</span>.
          </p>
          <p className="text-[13px]" style={{ color: 'var(--sim-muted)' }}>
            Cette action est définitive et irréversible. Aucune récupération automatique
            n'est prévue.
          </p>
        </div>

        <DialogFooter className="gap-2">
          {/* Annuler */}
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={deleteMutation.isPending}
            className="text-[12px]"
          >
            Annuler
          </Button>

          {/* Supprimer (destructive) */}
          <Button
            type="button"
            variant="destructive"
            onClick={handleConfirm}
            disabled={deleteMutation.isPending}
            className="text-[12px]"
          >
            {deleteMutation.isPending ? 'Suppression…' : 'Supprimer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default PdvDeleteDialog
