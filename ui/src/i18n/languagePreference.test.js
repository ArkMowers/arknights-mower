import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMowerI18n, getInterfaceLanguageOptions, i18n } from './index'
import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  isInterfaceLanguagePreference,
  readBrowserLanguages,
  resolveInterfaceLanguage
} from './languagePreference'

afterEach(() => {
  vi.unstubAllGlobals()
  i18n.global.locale.value = DEFAULT_LOCALE
})

describe('interface language preference resolution', () => {
  it.each([
    [['zh-Hant'], 'zh-TW'],
    [['zh-HK'], 'zh-TW'],
    [['zh-MO'], 'zh-TW'],
    [['zh-TW'], 'zh-TW'],
    [['zh-Hant-HK'], 'zh-TW'],
    [['zh-Hans'], 'zh-CN'],
    [['zh-SG'], 'zh-CN'],
    [['zh'], 'zh-CN'],
    [['JA-jp'], 'ja-JP'],
    [['en-GB'], 'en-US'],
    [['fr-FR', 'ja', 'en-US'], 'ja-JP'],
    [['de-DE', 'fr-FR'], 'zh-CN'],
    [[null, {}, 'invalid_', 'en_US'], 'zh-CN'],
    [[], 'zh-CN']
  ])('matches browser language list %j to %s', (languages, expected) => {
    expect(resolveInterfaceLanguage('system', languages)).toBe(expected)
  })

  it('keeps all explicit choices independent of browser languages and defaults unknown preferences', () => {
    for (const locale of SUPPORTED_LOCALES) {
      expect(resolveInterfaceLanguage(locale, ['ja-JP'])).toBe(locale)
      expect(isInterfaceLanguagePreference(locale)).toBe(true)
    }
    expect(resolveInterfaceLanguage('other', ['en-US'])).toBe('zh-CN')
    expect(isInterfaceLanguagePreference('system')).toBe(true)
    expect(isInterfaceLanguagePreference('en')).toBe(false)
  })

  it('uses navigator.language when its list is absent and falls back offline', () => {
    expect(readBrowserLanguages({ languages: ['ja-JP', 'en-US'], language: 'zh-CN' })).toEqual([
      'ja-JP',
      'en-US'
    ])
    expect(readBrowserLanguages({ languages: [], language: 'en-GB' })).toEqual(['en-GB'])
    expect(readBrowserLanguages({ language: 'zh-TW' })).toEqual(['zh-TW'])
    vi.stubGlobal('navigator', undefined)
    expect(readBrowserLanguages()).toEqual([])
    expect(resolveInterfaceLanguage('system')).toBe('zh-CN')
  })

  it('keeps system outside the actual locales and shares translated option labels', () => {
    const instance = createMowerI18n()
    expect(instance.global.availableLocales.sort()).toEqual([...SUPPORTED_LOCALES].sort())
    expect(instance.global.availableLocales).not.toContain('system')
    instance.dispose()
    for (const [locale, label] of [
      ['zh-CN', '跟随系统'],
      ['en-US', 'Follow System'],
      ['ja-JP', 'システムに従う'],
      ['zh-TW', '跟隨系統']
    ]) {
      i18n.global.locale.value = locale
      expect(getInterfaceLanguageOptions()[0]).toEqual({ value: 'system', label })
      expect(
        getInterfaceLanguageOptions()
          .slice(1)
          .map(({ value }) => value)
      ).toEqual(SUPPORTED_LOCALES)
    }
  })
})
