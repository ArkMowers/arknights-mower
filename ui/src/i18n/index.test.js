import { afterEach, describe, expect, it } from 'vitest'
import { computed } from 'vue'
import { createMowerI18n, i18n, setInterfaceLocale } from './index'

afterEach(() => setInterfaceLocale('zh-CN'))

describe('interface translation', () => {
  it('updates observed messages and preserves interpolated user names', () => {
    const label = computed(() => i18n.global.t('menus.menuLabel', { label: '我的分组' }))
    expect(label.value).toBe('我的分组菜单')
    expect(setInterfaceLocale('en-US')).toBe(true)
    expect(label.value).toBe('我的分组 menu')
    expect(setInterfaceLocale('other')).toBe(false)
    expect(i18n.global.locale.value).toBe('en-US')
  })

  it('shows Chinese when the English translation is missing', () => {
    const instance = createMowerI18n()
    instance.global.setLocaleMessage('en-US', {})
    instance.global.locale.value = 'en-US'
    expect(instance.global.t('menus.view')).toBe('视图')
    instance.dispose()
  })
})
