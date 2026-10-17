import { renderToString } from '@vue/server-renderer'
import { createSSRApp } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import TriggerEditor from './TriggerEditor.vue'
import { maintenance_trigger } from '@/utils/trigger_maintenance'

vi.mock('./TriggerString.vue', () => ({
  default: { props: ['data'], template: '<span>{{ data }}</span>' }
}))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  return {
    NTable: {
      setup:
        (_, { slots }) =>
        () =>
          h('table', slots.default?.())
    },
    NSelect: { render: () => h('span') },
    NAutoComplete: { render: () => h('span') },
    NInputNumber: {
      props: ['value'],
      setup: (props) => () => h('input', { value: props.value })
    }
  }
})

async function render(data) {
  return renderToString(createSSRApp(TriggerEditor, { data }))
}

describe('维护副表条件编辑', () => {
  it('renders a complete timing condition in one row', async () => {
    const html = await render(maintenance_trigger())
    expect(html.match(/<tr(?:\s[^>]*)?>/g)).toHaveLength(1)
    expect(html).toContain('定时条件')
    expect(html).toContain('停服大更新提前小时数')
    expect(html).toContain('小时内生效')
    expect(html).not.toContain('运算符')
  })

  it('preserves the saved advance value', async () => {
    const html = await render(maintenance_trigger(12))
    expect(html).toContain('value="12"')
  })

  it('preserves ordinary and nested conditions', async () => {
    const ordinary = { left: '1', operator: '==', right: '1' }
    expect(await render(ordinary)).toContain('运算符')
    const html = await render({ left: maintenance_trigger(), operator: 'and', right: ordinary })
    expect(html).toContain('定时条件')
    expect(html).toContain('运算符')
  })
})
