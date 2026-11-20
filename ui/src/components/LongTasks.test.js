import { renderToString } from '@vue/server-renderer'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { createTaskWorkflow, setTaskEnabled } from '@/task-workflow/model'
import LongTasks from './LongTasks.vue'

const state = vi.hoisted(() => ({
  updateEnabled: null,
  pickers: {},
  checks: {},
  days: {},
  buttons: {}
}))

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
    NCheckbox: {
      inheritAttrs: false,
      setup(_, { attrs, slots }) {
        state.checks[attrs['aria-label']] = attrs
        return () => h(library.NCheckbox, attrs, slots)
      }
    },
    NButton: {
      inheritAttrs: false,
      setup(_, { attrs, slots }) {
        state.buttons[attrs['aria-label']] = attrs
        return () => h(library.NButton, attrs, slots)
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
vi.mock('./WeeklyPlanDayCell.vue', async (original) => {
  const { default: cell } = await original()
  const { h } = await import('vue')
  return {
    default: {
      inheritAttrs: false,
      setup(_, { attrs, slots }) {
        state.days[attrs.label] = attrs
        return () => h(cell, attrs, slots)
      }
    }
  }
})

let store
let pinia

beforeEach(() => {
  state.updateEnabled = null
  state.pickers = {}
  state.checks = {}
  state.days = {}
  state.buttons = {}
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

it('shows the former daily windows for all seven days until the first weekly edit', async () => {
  const html = await renderLongTasks(true, {
    maa_rg_sleep_max: '08:05',
    maa_rg_sleep_min: '11:00',
    maa_long_task_extra_windows: [{ start: '22:00', end: '2:00' }]
  })
  expect(html).toContain('第1段开始时间')
  expect(html.indexOf('>周日<')).toBeLessThan(html.indexOf('>周一<'))
  expect(store.maa_long_task_weekly_windows).toBeNull()
  expect(state.days['第1段周日'].selected).toBe(true)
  expect(state.days['第2段周六'].selected).toBe(true)
  expect(html).toContain('aria-pressed="true" aria-label="第1段周日"')
  expect(html).toContain('✓')

  state.days['第1段周日'].onToggle()
  expect(store.maa_long_task_weekly_windows[0]).toEqual({
    start: '08:05',
    end: '11:00',
    weekdays: [0, 1, 2, 3, 4, 5]
  })
  state.pickers['第2段停止时间']('3:00')

  expect(store.maa_long_task_weekly_windows).toEqual([
    { start: '08:05', end: '11:00', weekdays: [0, 1, 2, 3, 4, 5] },
    { start: '22:00', end: '3:00', weekdays: [0, 1, 2, 3, 4, 5, 6] }
  ])
})

it('allows overlapping selections and adds new rows without enabling time', async () => {
  await renderLongTasks(true, {
    maa_long_task_weekly_windows: [
      { start: '8:00', end: '12:00', weekdays: [0] },
      { start: '10:00', end: '13:00', weekdays: [] }
    ]
  })
  state.days['第2段周一'].onToggle()
  expect(store.maa_long_task_weekly_windows.map((row) => row.weekdays)).toEqual([[0], [0]])
  state.checks['第2段全选']['onUpdate:checked'](true)
  expect(store.maa_long_task_weekly_windows[1].weekdays).toEqual([0, 1, 2, 3, 4, 5, 6])
  state.buttons['添加执行时段'].onClick()
  expect(store.maa_long_task_weekly_windows[2].weekdays).toEqual([])
  expect(state.buttons['删除第1段'].type).toBe('error')
  expect(state.buttons['删除第1段'].size).toBe(state.buttons['添加执行时段'].size)
  expect(state.buttons['删除第1段'].round).toBe(state.buttons['添加执行时段'].round)
  state.buttons['删除第1段'].onClick()
  expect(store.maa_long_task_weekly_windows[0]).toMatchObject({ start: '10:00', end: '13:00' })
})

it('keeps a cleared week empty on render', async () => {
  const html = await renderLongTasks(true, { maa_long_task_weekly_windows: [] })
  expect(html).toContain('未选执行时段')
  expect(html).not.toContain('第1段开始时间')
  expect(store.maa_long_task_weekly_windows).toEqual([])
})
