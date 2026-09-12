import { expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { NDynamicInput } from 'naive-ui'
import { completeMasterySupports } from './masteryRoute.js'

it.each([{ saved: [] }, { saved: [{ skill_level: 2, name: '赤冬' }] }])(
  'renders all three stages without add/remove buttons for partial routes: %j',
  async ({ saved }) => {
    const rows = completeMasterySupports(saved)
    const app = createSSRApp({
      render: () =>
        h(
          NDynamicInput,
          { value: rows, min: 3, max: 3 },
          {
            default: ({ value }) =>
              h('input', { 'data-level': value.skill_level, value: value.name }),
            action: () => h('span', { hidden: true })
          }
        )
    })
    const html = await renderToString(app)
    for (const level of [1, 2, 3]) expect(html).toContain(`data-level="${level}"`)
    expect(html).not.toContain('<button')
    if (saved.length) expect(html).toContain('value="赤冬"')
  }
)
