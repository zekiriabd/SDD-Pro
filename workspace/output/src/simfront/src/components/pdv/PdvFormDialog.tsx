/**
 * PdvFormDialog — formulaire création (AC-1) et modification (AC-2).
 *
 * - Validation react-hook-form + zodResolver (AC-5, AC-8)
 * - FormMessage sous chaque champ invalide (AC-5)
 * - Bouton submit bloqué tant que validation non verte (AC-5)
 * - Libellés des champs verbatim du HTML mockup 1-4-Gestion-PDV.html
 */
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { pdvSchema, type PdvFormValues } from '@/schemas/pdv'
import { usePdvCreateMutation, usePdvUpdateMutation } from '@/hooks/pdv/usePdvMutations'
import type { PdvDto } from '@/schemas/pdv.schema'

interface PdvFormDialogProps {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit'
  initialData?: PdvDto
  pdvId?: number
}

export function PdvFormDialog({
  open,
  onClose,
  mode,
  initialData,
  pdvId,
}: PdvFormDialogProps) {
  const form = useForm<PdvFormValues>({
    resolver: zodResolver(pdvSchema),
    defaultValues: {
      enseigne: '',
      format: '',
      typeDeLien: '',
      actif: 'Oui',
      adresse: '',
      complementAdresse: '',
      commune: '',
      departement: '',
      codePostal: '',
      telephone: '',
      fax: '',
      pays: 'France',
      surface: '',
      centraleDerattachement: '',
      codeTdlinx: '',
    },
    mode: 'onBlur',
  })

  // Pré-remplir en mode édition (AC-2)
  useEffect(() => {
    if (mode === 'edit' && initialData) {
      form.reset({
        enseigne: initialData.enseigne ?? '',
        format: initialData.format ?? '',
        typeDeLien: initialData.natureLien ?? '',
        actif: initialData.actif ? 'Oui' : 'Non',
        adresse: initialData.adresse ?? '',
        complementAdresse: initialData.complementAdresse ?? '',
        commune: initialData.commune ?? '',
        departement: initialData.departement ?? '',
        codePostal: initialData.codePostal ?? '',
        telephone: initialData.telephone ?? '',
        fax: initialData.fax ?? '',
        pays: initialData.pays ?? 'France',
        surface: initialData.surface !== null ? String(initialData.surface) : '',
        centraleDerattachement: initialData.centraleDerattachement ?? '',
        codeTdlinx: initialData.codeTdlinx ?? '',
      })
    } else if (mode === 'create') {
      form.reset({
        enseigne: '',
        format: '',
        typeDeLien: '',
        actif: 'Oui',
        adresse: '',
        complementAdresse: '',
        commune: '',
        departement: '',
        codePostal: '',
        telephone: '',
        fax: '',
        pays: 'France',
        surface: '',
        centraleDerattachement: '',
        codeTdlinx: '',
      })
    }
  }, [mode, initialData, open, form])

  const createMutation = usePdvCreateMutation({
    onSuccess: () => onClose(),
    fieldSetter: (field, msg) => form.setError(field, { message: msg }),
  })

  const updateMutation = usePdvUpdateMutation({
    pdvId: pdvId ?? 0,
    onSuccess: () => onClose(),
    fieldSetter: (field, msg) => form.setError(field, { message: msg }),
  })

  const isPending =
    mode === 'create' ? createMutation.isPending : updateMutation.isPending

  function onSubmit(values: PdvFormValues) {
    if (mode === 'create') {
      createMutation.mutate(values)
    } else {
      updateMutation.mutate(values)
    }
  }

  const title =
    mode === 'create' ? 'Créer un point de vente' : 'Modifier le point de vente'

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-[16px] font-semibold" style={{ color: 'var(--sim-ink)' }}>
            {title}
          </DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* Grille 2 colonnes — disposition identique à PdvInfoGenerales */}
            <div className="grid grid-cols-2 gap-[18px]">
              {/* Panel gauche — libellés verbatim */}
              <div
                className="rounded-[6px] border bg-white p-6 space-y-1"
                style={{ borderColor: 'var(--sim-line)' }}
              >
                <FormFieldRow
                  form={form}
                  name="enseigne"
                  label="Enseigne"
                  type="input"
                  required
                />
                <FormFieldRow
                  form={form}
                  name="format"
                  label="Format"
                  type="input"
                  required
                />
                <FormFieldRow
                  form={form}
                  name="typeDeLien"
                  label="Type de lien"
                  type="input"
                  required
                />
                <FormFieldRow
                  form={form}
                  name="surface"
                  label="Surface (m²)"
                  type="input"
                  inputType="text"
                />
                <FormFieldRow
                  form={form}
                  name="centraleDerattachement"
                  label="Centrale de rattachement"
                  type="input"
                />
                <FormFieldRow
                  form={form}
                  name="codeTdlinx"
                  label="Code TDlinx"
                  type="input"
                />
                <FormField
                  control={form.control}
                  name="actif"
                  render={({ field }) => (
                    <FormItem>
                      <div
                        className="grid items-center gap-4 py-2"
                        style={{ gridTemplateColumns: '180px 1fr' }}
                      >
                        <FormLabel className="text-[13px]" style={{ color: 'var(--sim-ink)' }}>
                          Actif <span className="text-destructive">*</span>
                        </FormLabel>
                        <div className="flex flex-col gap-1">
                          <Select
                            value={field.value}
                            onValueChange={field.onChange}
                          >
                            <SelectTrigger
                              className="h-8 text-[12px]"
                              style={{ borderColor: 'var(--sim-line)' }}
                            >
                              <SelectValue placeholder="Sélectionner..." />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="Oui">Oui</SelectItem>
                              <SelectItem value="Non">Non</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage className="text-xs" />
                        </div>
                      </div>
                    </FormItem>
                  )}
                />
              </div>

              {/* Panel droit — libellés verbatim */}
              <div
                className="rounded-[6px] border bg-white p-6 space-y-1"
                style={{ borderColor: 'var(--sim-line)' }}
              >
                <FormFieldRow
                  form={form}
                  name="adresse"
                  label="Adresse"
                  type="input"
                  required
                />
                <FormFieldRow
                  form={form}
                  name="complementAdresse"
                  label="Complément d'adresse"
                  type="input"
                />
                <FormFieldRow
                  form={form}
                  name="commune"
                  label="Commune"
                  type="input"
                  required
                />
                <FormFieldRow
                  form={form}
                  name="departement"
                  label="Département"
                  type="input"
                />
                <FormFieldRow
                  form={form}
                  name="codePostal"
                  label="Code postal"
                  type="input"
                  required
                />
                <FormFieldRow
                  form={form}
                  name="telephone"
                  label="Téléphone"
                  type="input"
                />
                <FormFieldRow
                  form={form}
                  name="fax"
                  label="Fax"
                  type="input"
                />
                <FormFieldRow
                  form={form}
                  name="pays"
                  label="Pays"
                  type="input"
                  required
                />
              </div>
            </div>

            <DialogFooter className="pt-4 gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={isPending}
                className="text-[12px]"
              >
                Annuler
              </Button>
              <Button
                type="submit"
                disabled={isPending || !form.formState.isValid}
                className="text-[12px]"
                style={{
                  backgroundColor: 'var(--sim-accent)',
                  color: '#fff',
                }}
              >
                {isPending
                  ? 'Enregistrement…'
                  : mode === 'create'
                  ? 'Créer'
                  : 'Enregistrer'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Helper interne : ligne de formulaire générique
// ---------------------------------------------------------------------------

import type { UseFormReturn, FieldPath } from 'react-hook-form'

interface FormFieldRowProps {
  form: UseFormReturn<PdvFormValues>
  name: FieldPath<PdvFormValues>
  label: string
  type: 'input'
  inputType?: string
  required?: boolean
}

function FormFieldRow({ form, name, label, inputType = 'text', required = false }: FormFieldRowProps) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <div
            className="grid items-center gap-4 py-2"
            style={{ gridTemplateColumns: '180px 1fr' }}
          >
            <FormLabel className="text-[13px]" style={{ color: 'var(--sim-ink)' }}>
              {label}
              {required && <span className="text-destructive ml-0.5">*</span>}
            </FormLabel>
            <div className="flex flex-col gap-1">
              <FormControl>
                <Input
                  {...field}
                  type={inputType}
                  value={field.value ?? ''}
                  className="h-8 text-[12px]"
                  style={{ borderColor: 'var(--sim-line)' }}
                />
              </FormControl>
              <FormMessage className="text-xs" />
            </div>
          </div>
        </FormItem>
      )}
    />
  )
}

export default PdvFormDialog
