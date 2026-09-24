import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import LogPage from './Log.vue'

const state = vi.hoisted(() => ({ client: null, mower: null, config: null, warning: null }))

vi.mock('pinia', async (original) => ({
  ...(await original()),
  storeToRefs: (store) => store.refs
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.client : ref(false)),
  onMounted: vi.fn(),
  onUnmounted: vi.fn(),
  provide: vi.fn()
}))
vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: state.warning }),
  useMessage: () => ({ error: vi.fn(), success: vi.fn() })
}))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/utils/screenshotPreview', () => ({
  createScreenshotPreview: () => ({ start: vi.fn(), stop: vi.fn() })
}))

describe('running stop menu', () => {
  let scope

  beforeEach(() => {
    state.client = { get: vi.fn(), post: vi.fn() }
    state.warning = vi.fn()
    state.mower = {
      refs: {
        log: ref(''),
        log_mobile: ref(''),
        running: ref(true),
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
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
    vi.unstubAllGlobals()
  })

  it('runs both process actions directly through ProcessControl', async () => {
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const applySchedule = vi.fn()
    const restartResume = vi.fn()
    expect(component.stop_options.value[1].disabled).toBe(true)
    expect(component.stop_options.value[2].disabled).toBe(true)

    component.process_control.value = {
      canRunProcessAction: true,
      applySchedule,
      restartResume
    }
    await nextTick()
    expect(component.stop_options.value.map((option) => option.label)).toEqual([
      '停止MAA',
      '应用排班',
      '重启续接'
    ])
    expect(component.stop_options.value[1].disabled).toBe(false)
    expect(component.stop_options.value[2].disabled).toBe(false)

    component.select_stop_action('apply_schedule')
    component.select_stop_action('restart_resume')
    expect(applySchedule).toHaveBeenCalledOnce()
    expect(restartResume).toHaveBeenCalledOnce()
    expect(state.warning).not.toHaveBeenCalled()

    component.select_stop_action('maa')
    expect(state.client.get).toHaveBeenCalledWith('/stop-maa')
  })
})
