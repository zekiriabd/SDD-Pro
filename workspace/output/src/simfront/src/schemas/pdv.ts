/**
 * Schema Zod PDV — formulaire création / modification (AC-5, AC-8).
 *
 * Aligné sur les règles métier backend FluentValidation :
 *   - Champs obligatoires : enseigne, format, typeDeLien, actif, adresse, commune,
 *     codePostal, pays.
 *   - Champs optionnels : complementAdresse, departement, surface, centraleDerattachement,
 *     codeTdlinx, telephone, fax.
 * Messages d'erreur en français (AC-5).
 */
import { z } from 'zod'

export const pdvSchema = z.object({
  enseigne: z
    .string({ required_error: 'Enseigne obligatoire' })
    .min(1, 'Enseigne obligatoire')
    .max(255, 'Enseigne trop longue (max 255 caractères)'),

  format: z
    .string({ required_error: 'Format obligatoire' })
    .min(1, 'Format obligatoire'),

  typeDeLien: z
    .string({ required_error: 'Type de lien obligatoire' })
    .min(1, 'Type de lien obligatoire'),

  actif: z.enum(['Oui', 'Non'], {
    required_error: 'Actif obligatoire',
    invalid_type_error: 'Actif doit être Oui ou Non',
  }),

  adresse: z
    .string({ required_error: 'Adresse obligatoire' })
    .min(1, 'Adresse obligatoire')
    .max(255, 'Adresse trop longue (max 255 caractères)'),

  commune: z
    .string({ required_error: 'Commune obligatoire' })
    .min(1, 'Commune obligatoire')
    .max(100, 'Commune trop longue (max 100 caractères)'),

  codePostal: z
    .string({ required_error: 'Code postal obligatoire' })
    .regex(/^\d{5}$/, 'Code postal invalide (5 chiffres)'),

  pays: z
    .string({ required_error: 'Pays obligatoire' })
    .min(1, 'Pays obligatoire')
    .max(100, 'Pays trop long (max 100 caractères)')
    .default('France'),

  // Champs optionnels
  complementAdresse: z
    .string()
    .max(255, 'Complément d\'adresse trop long (max 255 caractères)')
    .optional()
    .or(z.literal('')),

  departement: z
    .string()
    .max(100, 'Département trop long (max 100 caractères)')
    .optional()
    .or(z.literal('')),

  surface: z
    .string()
    .optional()
    .or(z.literal('')),

  centraleDerattachement: z
    .string()
    .max(255, 'Centrale de rattachement trop longue (max 255 caractères)')
    .optional()
    .or(z.literal('')),

  codeTdlinx: z
    .string()
    .max(50, 'Code TDlinx trop long (max 50 caractères)')
    .optional()
    .or(z.literal('')),

  telephone: z
    .string()
    .max(20, 'Téléphone trop long (max 20 caractères)')
    .optional()
    .or(z.literal('')),

  fax: z
    .string()
    .max(20, 'Fax trop long (max 20 caractères)')
    .optional()
    .or(z.literal('')),
})

export type PdvFormValues = z.infer<typeof pdvSchema>
