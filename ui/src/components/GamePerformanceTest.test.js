import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import GamePerformanceTest from './GamePerformanceTest.vue'

const state = vi.hoisted(() => ({ config: null, http: null, mounted: [], unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => state.http,
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
let scope
function setup() {
  state.config = reactive({
    device_profile: { last_serial: 'USB-123', screenshot_backend: 'adb_gzip' },
    performance_mode: 'auto',
    screenshot_interval: 500,
    selection_poll_interval: 0.1,
    selection_transition_timeout: 2.5,
    run_order_delay: 12,
    save_config: vi.fn().mockResolvedValue()
  })
  state.http = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
  state.mounted = []
  state.unmounted = []
  const props = reactive({ disabled: false })
  scope = effectScope()
  let component
  scope.run(() => {
    component = GamePerformanceTest.setup(props, { expose: () => {}, emit: vi.fn() })
  })
  return { component, props }
}
function passed(component) {
  component.job.value = {
    id: 'test',
    status: 'passed',
    recommended_mode: 'xhigh',
    device: { ...state.config.device_profile },
    timing: {
      screenshot_interval: 500,
      selection_poll_interval: 0.1,
      selection_transition_timeout: 2.5
    }
  }
}
afterEach(() => {
  scope?.stop()
  state.unmounted.forEach((callback) => callback())
  vi.useRealTimers()
})

it('adopts an actual xhigh result only on user action and preserves timings', () => {
  const { component } = setup()
  passed(component)
  expect(component.recommendation.value).toBe('xhigh')
  expect(state.config.performance_mode).toBe('auto')
  const before = { ...state.config }
  component.adopt()
  expect(state.config).toEqual({ ...before, performance_mode: 'xhigh' })
})
it('rejects stale device and timing results, disabled adoption and failed tests', () => {
  const { component, props } = setup()
  passed(component)
  state.config.device_profile.last_serial = 'other'
  expect(component.recommendation.value).toBeNull()
  component.adopt()
  expect(state.config.performance_mode).toBe('auto')
  passed(component)
  state.config.selection_poll_interval = 0.8
  expect(component.recommendation.value).toBeNull()
  state.config.selection_poll_interval = 0.1
  props.disabled = true
  component.adopt()
  expect(state.config.performance_mode).toBe('auto')
  component.job.value.status = 'failed'
  expect(component.recommendation.value).toBeNull()
})
it('saves current settings before starting and never adopts automatically', async () => {
  const { component } = setup()
  const order = []
  state.config.save_config.mockImplementation(async () => {
    order.push('save')
  })
  state.http.post.mockImplementation(async () => {
    order.push('start')
    return { data: { status: 'running', id: 'test' } }
  })
  await component.start()
  expect(order).toEqual(['save', 'start'])
  expect(component.running.value).toBe(true)
  expect(state.config.performance_mode).toBe('auto')
  await component.start()
  expect(state.http.post).toHaveBeenCalledTimes(1)
})
it('does not start when configuration save fails and exposes server errors', async () => {
  const { component } = setup()
  state.config.save_config.mockRejectedValue(new Error('保存失败'))
  await component.start()
  expect(state.http.post).not.toHaveBeenCalled()
  expect(component.error.value).toBe('保存失败')
})
it('cancels only the current test and keeps polling until cleanup ends', async () => {
  const { component } = setup()
  component.job.value = { status: 'running', id: 'test', phase: 'testing', mode: 'high', round: 2 }
  expect(component.progress.value).toContain('高档 · 第 2/3 轮')
  state.http.delete.mockResolvedValue({ data: { status: 'running', id: 'test', phase: 'cleanup' } })
  await component.cancel()
  expect(state.http.delete).toHaveBeenCalledWith('/device/performance-test', {
    data: { id: 'test' }
  })
  expect(component.running.value).toBe(true)
  expect(component.progress.value).toContain('取消暂选')
})
it('ignores a status response started before a newer start or cancellation', async () => {
  const { component } = setup()
  let resolve
  state.http.get.mockReturnValue(
    new Promise((done) => {
      resolve = done
    })
  )
  const old = component.readStatus()
  state.http.post.mockResolvedValue({ data: { status: 'running', id: 'new' } })
  await component.start()
  resolve({ data: { status: 'idle' } })
  await old
  await nextTick()
  expect(component.job.value.id).toBe('new')
})
