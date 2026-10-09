import { afterEach, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import PerformanceSettings from './PerformanceSettings.vue'

const state = vi.hoisted(() => ({ config: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('naive-ui', () => {
  const wrapper = {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
  return Object.fromEntries(
    ['NFormItem', 'NSpace', 'NRadioGroup', 'NFlex', 'NRadio', 'NText'].map((name) => [
      name,
      wrapper
    ])
  )
})
vi.mock('./HelpText.vue', () => ({
  default: {
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
}))
vi.mock('./GamePerformanceTest.vue', () => ({
  default: {
    props: ['disabled'],
    render() {
      return h('button', { disabled: this.disabled }, '游戏内性能测试')
    }
  }
}))

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

it('displays resources without recommending a hardware-derived mode', () => {
  const { component } = setup({
    observation: { status: 'available', cpu_cores: 4, memory_mb: 3840, recommended_mode: 'high' }
  })
  expect(component.resourceLabel.value).toBe('CPU 4 核 · 内存 3.8 GiB')
  expect(component).not.toHaveProperty('recommendation')
  expect(state.config.performance_mode).toBe('auto')
  const before = { ...state.config }
  component.applyMode('high')
  expect(state.config).toEqual({ ...before, performance_mode: 'high' })
})

it('keeps manual choices when information is unavailable or changes', () => {
  const { component, props } = setup({ observation: { status: 'unavailable' } })
  state.config.performance_mode = 'xhigh'
  expect(component.resourceLabel.value).toBe('')
  props.observation = {
    status: 'available',
    cpu_cores: 1,
    memory_mb: 1024,
    recommended_mode: 'low'
  }
  expect(component).not.toHaveProperty('recommendation')
  expect(state.config.performance_mode).toBe('xhigh')
})

it('opens every Android mode while rejecting disabled or invalid choices', () => {
  const { component, props } = setup()
  state.config.runtime_platform = 'android'
  expect(component.options.value.map((item) => item.value)).toEqual([
    'auto',
    'xhigh',
    'high',
    'medium',
    'low'
  ])
  for (const mode of ['high', 'xhigh']) {
    component.applyMode(mode)
    expect(state.config.performance_mode).toBe(mode)
  }
  state.config.performance_mode = 'auto'
  for (const mode of [undefined, 'unknown']) component.applyMode(mode)
  expect(state.config.performance_mode).toBe('auto')
  props.disabled = true
  component.applyMode('low')
  expect(state.config.performance_mode).toBe('auto')
  props.disabled = false
  component.applyMode('medium')
  expect(state.config.performance_mode).toBe('medium')
})

it.each(['android', 'darwin'])('renders an enabled game test for %s', async (platform) => {
  setup()
  state.config.runtime_platform = platform
  const app = createSSRApp(PerformanceSettings, { testEnabled: true })
  const html = await renderToString(app)
  expect(html).toMatch(/<button\b[^>]*>游戏内性能测试<\/button>/)
  expect(html).not.toMatch(/<button\b[^>]*disabled/)
  expect(html).toContain(`自动从${platform === 'android' ? '中' : '极高'}开始`)
})
