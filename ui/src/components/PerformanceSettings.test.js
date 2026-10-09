import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import PerformanceSettings from './PerformanceSettings.vue'

const state = vi.hoisted(() => ({ config: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))

let scope
function setup(overrides = {}) {
  state.config = reactive({
    performance_mode: 'auto',
    runtime_platform: 'darwin',
    screenshot_interval: 650,
    selection_poll_interval: 0.8,
    selection_transition_timeout: 9,
    run_order_delay: 12
  })
  const props = reactive({ observation: null, disabled: false, labelWidth: 158, ...overrides })
  scope = effectScope()
  let component
  scope.run(() => {
    component = PerformanceSettings.setup(props, { expose: () => {} })
  })
  return { component, props }
}
afterEach(() => scope?.stop())

it('displays a recommendation without changing the selection until adopted', () => {
  const { component } = setup({
    observation: { status: 'available', cpu_cores: 4, memory_mb: 3840, recommended_mode: 'high' }
  })
  expect(component.resourceLabel.value).toBe('CPU 4 核 · 内存 3.8 GiB')
  expect(component.recommendation.value).toBe('high')
  expect(state.config.performance_mode).toBe('auto')
  const before = { ...state.config }
  component.applyMode(component.recommendation.value)
  expect(state.config).toEqual({ ...before, performance_mode: 'high' })
})

it('keeps manual choices when information is unavailable or changes', () => {
  const { component, props } = setup({ observation: { status: 'unavailable' } })
  state.config.performance_mode = 'xhigh'
  expect(component.recommendation.value).toBe(null)
  expect(component.resourceLabel.value).toBe('')
  props.observation = {
    status: 'available',
    cpu_cores: 1,
    memory_mb: 1024,
    recommended_mode: 'low'
  }
  expect(component.recommendation.value).toBe('low')
  expect(state.config.performance_mode).toBe('xhigh')
})

it('preserves Android restrictions and rejects disabled or invalid choices', () => {
  const { component, props } = setup()
  state.config.runtime_platform = 'android'
  expect(component.options.value.map((item) => item.value)).toEqual(['auto', 'medium', 'low'])
  for (const mode of ['high', 'xhigh', undefined, 'unknown']) component.applyMode(mode)
  expect(state.config.performance_mode).toBe('auto')
  props.disabled = true
  component.applyMode('low')
  expect(state.config.performance_mode).toBe('auto')
  props.disabled = false
  component.applyMode('medium')
  expect(state.config.performance_mode).toBe('medium')
})
