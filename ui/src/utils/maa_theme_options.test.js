import { describe, expect, it } from 'vitest'
import { getMaaThemeOptions } from './maa_theme_options'

describe('MAA theme dropdown compatibility', () => {
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
