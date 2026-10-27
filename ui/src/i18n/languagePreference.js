export const DEFAULT_LOCALE = 'zh-CN'
export const SYSTEM_LANGUAGE = 'system'
export const INTERFACE_LANGUAGES = Object.freeze([
  { value: 'zh-CN', label: '中文（简体）' },
  { value: 'en-US', label: 'English' },
  { value: 'ja-JP', label: '日本語' },
  { value: 'zh-TW', label: '繁體中文' }
])
export const SUPPORTED_LOCALES = Object.freeze(INTERFACE_LANGUAGES.map(({ value }) => value))
export const isSupportedLocale = (value) => SUPPORTED_LOCALES.includes(value)
export const isInterfaceLanguagePreference = (value) =>
  value === SYSTEM_LANGUAGE || isSupportedLocale(value)

export function readBrowserLanguages(browser = globalThis.navigator) {
  if (Array.isArray(browser?.languages) && browser.languages.length) return [...browser.languages]
  return browser?.language ? [browser.language] : []
}

export function resolveInterfaceLanguage(preference, languages = readBrowserLanguages()) {
  if (preference !== SYSTEM_LANGUAGE)
    return isSupportedLocale(preference) ? preference : DEFAULT_LOCALE
  for (const language of languages) {
    if (typeof language !== 'string' || !/^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/i.test(language)) continue
    const [base, ...parts] = language.toLowerCase().split('-')
    if (base === 'en') return 'en-US'
    if (base === 'ja') return 'ja-JP'
    if (base === 'zh') {
      if (parts.includes('hans')) return 'zh-CN'
      return parts.some((part) => ['hant', 'tw', 'hk', 'mo'].includes(part)) ? 'zh-TW' : 'zh-CN'
    }
  }
  return DEFAULT_LOCALE
}
