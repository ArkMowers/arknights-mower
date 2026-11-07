import { shallowRef } from 'vue'

export const settingsNavigationKey = Symbol('settings-navigation')
export const settingsSectionKey = Symbol('settings-section')

// 分类与搜索由当前设置页提供，外层侧栏只负责显示和调用。
export function createSettingsNavigation() {
  const current = shallowRef(null)
  return {
    current,
    register(page) {
      current.value = page
      return () => {
        if (current.value === page) current.value = null
      }
    }
  }
}
