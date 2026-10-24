import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import TaskSettings from './TaskSettings.vue'

vi.mock('@/task-workflow/TaskConfiguration.vue', () => ({
  default: defineComponent({
    setup: () => () => h('section', { 'data-task-configuration': true })
  })
}))

async function render(path = '/task-settings') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'log', component: { render: () => null } },
      { path: '/task-settings', name: 'task-settings', component: TaskSettings }
    ]
  })
  await router.push(path)
  const app = createSSRApp(TaskSettings)
  app.use(router)
  return { html: await renderToString(app), router }
}

describe('task configuration page', () => {
  it('renders the real configuration entry as a page without navigating on mount', async () => {
    const { html, router } = await render('/task-settings?token=demo#task-base')
    expect(html).not.toMatch(/<h1\b/)
    expect(html).toContain('aria-label="全部设置"')
    expect(html).toContain('data-task-configuration="true"')
    expect(router.currentRoute.value.fullPath).toBe('/task-settings?token=demo#task-base')
  })

  it('keeps the page name required by KeepAlive and omits the queue shortcut', async () => {
    const { html } = await render()
    expect(TaskSettings.name).toBe('TaskSettings')
    expect(html).not.toContain('查看待执行任务')
  })
})
