import { afterEach, describe, expect, it } from 'vitest'
import { getMaaThemeOptions } from './maa_theme_options'
import { i18n } from '@/i18n'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

describe('MAA theme dropdown compatibility', () => {
  it('updates official theme labels and translates CN-only themes while preserving every theme task parameter', () => {
    const options = getMaaThemeOptions('用户自定义主题')
    const values = options.map(({ value }) => value)
    for (const [locale, silverfrost, hunt] of [
      ['zh-CN', '银凇', '出猎'],
      ['en-US', 'Silverfrost', 'The Hunt'],
      ['ja-JP', '銀氷', '狩り'],
      ['zh-TW', '銀淞', '出獵']
    ]) {
      i18n.global.locale.value = locale
      expect(options.find(({ value }) => value === '银凇').label).toBe(silverfrost)
      expect(options.find(({ value }) => value === '出猎').label).toBe(hunt)
      expect(options.map(({ value }) => value)).toEqual(values)
      expect(options.at(-1).value).toBe('用户自定义主题')
    }
  })
  it('uses game names as task parameters without duplicating saved known themes', () => {
    const options = getMaaThemeOptions('银凇')
    expect(options.filter((option) => option.value === '银凇')).toEqual([
      { label: '银凇', value: '银凇' }
    ])
    expect(options.every((option) => option.label === option.value)).toBe(true)
  })

  it('preserves a saved custom name without changing its task parameter', () => {
    expect(getMaaThemeOptions('后续新主题').at(-1)).toEqual({
      label: '后续新主题（已保存）',
      value: '后续新主题'
    })
    expect(getMaaThemeOptions().some((option) => option.value === '后续新主题')).toBe(false)
  })

  it('does not create an empty option after clearing the selection', () => {
    expect(getMaaThemeOptions('').some((option) => !option.value)).toBe(false)
  })
})
