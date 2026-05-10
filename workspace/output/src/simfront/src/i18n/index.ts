import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import frTranslation from './fr/translation.json'
import enTranslation from './en/translation.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      fr: { translation: frTranslation },
      en: { translation: enTranslation },
    },
    fallbackLng: 'fr',
    interpolation: {
      escapeValue: false,
    },
  })

export default i18n
