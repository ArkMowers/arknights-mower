import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import LogPage from './Log.vue'

const state = vi.hoisted(() => ({
  client: null,
  mower: null,
  config: null
}))

vi.mock('pinia', async (original) => ({
  ...(await original()),
  storeToRefs: (store) => store.refs
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: vi.fn(),
  onUnmounted: vi.fn(),
  provide: vi.fn()
}))
vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: vi.fn() }),
  useMessage: () => ({ error: vi.fn(), success: vi.fn() })
}))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/utils/screenshotPreview', () => ({
  createScreenshotPreview: () => ({ start: vi.fn(), stop: vi.fn() })
}))

describe('log layout reserve updates', () => {
  let scope

  beforeEach(() => {
    state.client = { get: vi.fn(), post: vi.fn() }
    state.mower = {
      refs: {
        log: ref(''),
        log_mobile: ref(''),
        running: ref(false),
        plan_condition: ref([]),
        log_lines: ref([]),
        task_list: ref([]),
        waiting: ref(false),
        get_task_id: ref(0)
      },
      get_tasks: vi.fn(),
      get_running: vi.fn()
    }
    state.config = { refs: { theme: ref('light') } }
    vi.stubGlobal('localStorage', { setItem: vi.fn(), getItem: vi.fn() })
    vi.stubGlobal('document', {
      hidden: false,
      querySelector: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    })
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
    vi.unstubAllGlobals()
  })

  it('reclamps panes when plan conditions appear after the initial layout pass', async () => {
    let conditionHeight = 0
    const setProperty = vi.fn()
    const container = {
      getBoundingClientRect: () => ({ top: 0, bottom: 620, height: 620 }),
      querySelector: (selector) => {
        if (selector === '.plan-condition') {
          return conditionHeight
            ? { getBoundingClientRect: () => ({ height: conditionHeight }) }
            : null
        }
        if (selector === '.action-container') {
          return { getBoundingClientRect: () => ({ height: 52 }) }
        }
        if (selector === '.task-table-scroll') {
          return { getBoundingClientRect: () => ({ top: 258 }) }
        }
        return null
      },
      style: { setProperty, removeProperty: vi.fn() }
    }

    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = container
    component.layout_preference.screenshot_height = 500
    component.layout_preference.task_height = 600
    component.apply_log_layout()
    const initialTaskHeight = setProperty.mock.calls.at(-1)[1]

    conditionHeight = 40
    state.mower.refs.plan_condition.value = ['副表一']
    await nextTick()
    await nextTick()

    expect(setProperty.mock.calls.length).toBeGreaterThan(2)
    expect(setProperty.mock.calls.at(-1)).toEqual(['--log-task-h', '142px'])
    expect(setProperty.mock.calls.at(-1)[1]).not.toBe(initialTaskHeight)
  })
})
