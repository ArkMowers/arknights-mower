import { expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { setup as setupSsrStyles } from '@css-render/vue3-ssr'
import Component from './StageProgressButton.vue'

async function render(props) {
  const app = createSSRApp(Component, props)
  setupSsrStyles(app)
  return renderToString(app)
}

it.each([
  ['pending', '待执行', 'aria-pressed="false"'],
  ['completed', '已完成', 'aria-pressed="true"'],
  ['running', '正在执行', 'disabled'],
  ['attempted', '结算待确认', 'aria-haspopup="menu"'],
  ['failed', '执行失败', 'aria-haspopup="menu"']
])('displays the %s state with its corresponding control', async (status, label, attribute) => {
  const html = await render({ stage: 'OS-1', status })
  expect(html).toContain('OS-1 · ' + label)
  expect(html).toContain(attribute)
})

it('names the individual queue row and disables the control while saving', async () => {
  const html = await render({ subject: '第 2 项作业', status: 'completed', disabled: true })
  expect(html).toContain('aria-label="第 2 项作业 · 已完成"')
  expect(html).toContain('disabled')
})
