import { renderToString } from '@vue/server-renderer'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { createTaskWorkflow, setTaskEnabled } from '@/task-workflow/model'
import LongTasks from './LongTasks.vue'

const state = vi.hoisted(() => ({ updateEnabled: null, windows: null, pickers: {} }))

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
      ['NCard', 'NForm', 'NFormItem', 'NSelect'].map((name) => [name, container])
    ),
    NDynamicInput: {
      inheritAttrs: false,
      setup(_, { attrs, slots }) {
        state.windows = attrs
        return () => h(library.NDynamicInput, attrs, slots)
      }
    },
    NTimePicker: {
      setup(_, { attrs }) {
        state.pickers[attrs['aria-label']] = attrs['onUpdate:formattedValue']
        return () => h('input', { value: attrs['formatted-value'] })
      }
    },
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

it('edits daily windows with the shared add and remove controls and keeps the first pair in legacy settings', async () => {
  const html = await renderLongTasks(true, { maa_rg_sleep_max: '8:00', maa_rg_sleep_min: '12:00' })
  expect(html).toContain('第1段开始时间')
  expect(state.windows.min).toBe(1)
  const first = state.windows.value[0]
  const second = state.windows['on-create'](1)
  state.windows['onUpdate:value']([first, second])
  expect(store.maa_long_task_extra_windows).toEqual([{ start: '8:00', end: '12:00' }])

  const app = createSSRApp(LongTasks)
  app.use(pinia)
  app.provide('mobile', ref(false))
  expect(await renderToString(app)).toContain('第2段停止时间')
  state.pickers['第2段开始时间']('22:00')
  state.pickers['第2段停止时间']('2:00')
  expect(store.maa_rg_sleep_max).toBe('8:00')
  expect(store.maa_long_task_extra_windows).toEqual([{ start: '22:00', end: '2:00' }])
  state.windows['onUpdate:value'](store.maa_long_task_extra_windows)
  expect([store.maa_rg_sleep_max, store.maa_rg_sleep_min]).toEqual(['22:00', '2:00'])
  expect(store.maa_long_task_extra_windows).toEqual([])
})
