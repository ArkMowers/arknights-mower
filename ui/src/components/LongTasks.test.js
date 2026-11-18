import { renderToString } from '@vue/server-renderer'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { createTaskWorkflow, setTaskEnabled } from '@/task-workflow/model'
import LongTasks from './LongTasks.vue'

const state = vi.hoisted(() => ({ updateEnabled: null }))

vi.mock('naive-ui', async (original) => {
  const library = await original()
  const { h } = await import('vue')
  const container = {
    setup(_, { slots }) {
      return () => h('div', [slots.header?.(), slots.label?.(), slots.default?.()])
    }
  }
  return {
    ...library,
    ...Object.fromEntries(
      ['NCard', 'NForm', 'NFormItem', 'NSelect', 'NTimePicker'].map((name) => [name, container])
    ),
    NSwitch: {
      inheritAttrs: false,
      setup(_, { attrs }) {
        state.updateEnabled = attrs['onUpdate:value']
        return () => h(library.NSwitch, attrs)
      }
    }
  }
})
vi.mock('./HelpText.vue', () => ({ default: { render: () => null } }))

let store
let pinia

beforeEach(() => {
  state.updateEnabled = null
})

afterEach(() => store?.$dispose())

async function renderLongTasks(value, overrides = {}) {
  const app = createSSRApp(LongTasks)
  pinia = createPinia()
  app.use(pinia)
  app.provide('loaded', ref(false))
  app.provide('mobile', ref(false))
  store = app.runWithContext(() => useConfigStore())
  Object.assign(store, { maa_rg_enable: value, maa_long_task_type: '', ...overrides })
  return renderToString(app)
}

describe('long-task switch across configuration layouts', () => {
  it.each([false, 0, true, 1])('displays the saved value %s consistently', async (value) => {
    const html = await renderLongTasks(value)
    expect(html).toContain(`aria-checked="${value === true || value === 1}"`)
    expect(store.maa_rg_enable).toBe(value)
  })

  it('keeps the waterfall switch enabled after enabling it in the checklist', async () => {
    await renderLongTasks(false)
    setTaskEnabled(store, 'long', true)

    const app = createSSRApp(LongTasks)
    app.use(pinia)
    app.provide('mobile', ref(false))
    const html = await renderToString(app)

    expect(html).toContain('aria-checked="true"')
    state.updateEnabled(false)
    expect(createTaskWorkflow(store).statuses.long).toBe(false)
    expect(store.maa_long_task_type).toBe('')
    state.updateEnabled(true)
    expect(createTaskWorkflow(store).statuses.long).toBe(true)
  })
})

it.each([0, 12])('shows the configured level farming limit of %i matches', async (match_limit) => {
  const html = await renderLongTasks(true, {
    maa_long_task_type: 'garrison',
    garrison: { mode: 'matches', match_limit, target_wins: 3, run_id: '' }
  })
  expect(html).toContain('刷取局数')
  expect(html).toContain('重新计数并继续')
  expect(store.garrison.match_limit).toBe(match_limit)
})
