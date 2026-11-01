import { describe, expect, it } from 'vitest'
import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import SettingsSection from './SettingsSection.vue'
import { settingsSectionKey } from '@/composables/settingsNavigation'

async function renderSections(selected) {
  const app = createSSRApp({
    render: () =>
      h('div', [
        h(SettingsSection, { id: 'interface', title: '界面与窗口' }, () =>
          h('input', { value: '当前缩放草稿' })
        ),
        h(SettingsSection, { id: 'notifications', title: '通知与助手' }, () =>
          h('input', { value: '未保存邮箱草稿' })
        )
      ])
  })
  if (selected) app.provide(settingsSectionKey, selected)
  return renderToString(app)
}

function sectionOpening(html, id) {
  return html.match(new RegExp(`<section\\b[^>]*id="${id}"[^>]*>`))?.[0]
}

describe('settings category visibility', () => {
  it.each(['interface', 'notifications'])(
    'shows only %s while retaining the other category content',
    async (id) => {
      const html = await renderSections(ref(id))
      const other = id === 'interface' ? 'notifications' : 'interface'
      expect(sectionOpening(html, id)).not.toContain('display:none')
      expect(sectionOpening(html, other)).toContain('display:none')
      expect(html).toContain('value="当前缩放草稿"')
      expect(html).toContain('value="未保存邮箱草稿"')
      expect(html).not.toContain('settings-section-header')
      expect(sectionOpening(html, 'notifications')).toContain('aria-label="通知与助手"')
    }
  )

  it('keeps every category and its heading visible in the standalone layout', async () => {
    const html = await renderSections()
    expect(html).not.toContain('display:none')
    expect(html).toContain('aria-labelledby="interface-title"')
    expect(html).toContain('<h2 id="interface-title">界面与窗口</h2>')
    expect(html).toContain('<h2 id="notifications-title">通知与助手</h2>')
  })
})
